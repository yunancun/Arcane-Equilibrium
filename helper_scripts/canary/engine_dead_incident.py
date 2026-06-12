#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：external watchdog 的 `engine_dead` notify-only producer。
主要函數：
  - maybe_emit_notify_only：在 heartbeat stale 且 respawn 失敗至少一次後，發
    ENGINE_DEAD_NOTIFY_ONLY canary event + 既有 engine-down alert。
  - emit_resolved_if_active：引擎恢復時寫 ENGINE_DEAD_RESOLVED 並清 producer marker。
依賴：純標準庫；I/O / alert / state 由 engine_watchdog 以 callback 注入，避免 circular import。
硬邊界：notify-only，只發通知與本地 canary event；不餵 C4 AllFail，不做 Defensive /
  auth / order / DB / risk mutation。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


ENGINE_DEAD_EVENT = "ENGINE_DEAD_NOTIFY_ONLY"
ENGINE_DEAD_RESOLVED_EVENT = "ENGINE_DEAD_RESOLVED"
ENGINE_DEAD_ALERT_KEY = "engine_dead_notify_only"
ENGINE_DEAD_MIN_STALE_SECONDS = 30.0

_ACTIVE_KEY = "engine_dead_notify_active"
_FIRST_TS_KEY = "engine_dead_notify_first_ts"
_EMIT_TS_KEY = "engine_dead_notify_emit_ts"
_FAILURES_AT_EMIT_KEY = "engine_dead_notify_failures_at_emit"

StateLoader = Callable[[str], dict[str, Any]]
StateSaver = Callable[[str, dict[str, Any]], None]
CanaryAppender = Callable[[str, dict[str, Any]], None]
EngineDownEmitter = Callable[[str, str, str, str, float], bool]


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_min = int(seconds // 60)
    return f"{total_min // 60}h {total_min % 60}m"


def _build_notify_payload(
    now: float,
    snapshot_age_seconds: float,
    consecutive_failures: int,
    last_failure_reason: str,
    first_observed_ts: float,
) -> tuple[str, str]:
    duration = _format_duration(now - first_observed_ts)
    subject = "OpenClaw engine DEAD — notify-only"
    body = (
        "incident_class: engine_dead\n"
        "mode: notify_only (no C4 AllFail, no Defensive arm)\n"
        f"snapshot stale for: {snapshot_age_seconds:.1f}s\n"
        f"down for: {duration}\n"
        f"respawn failures since recovery: {consecutive_failures}\n"
        f"last failure: {last_failure_reason or 'unknown'}\n"
        "action: ssh trade-core; check engine.log; manual restart_all"
    )
    return subject, body


def maybe_emit_notify_only(
    data_dir: str,
    now: float,
    snapshot_age_seconds: float,
    load_state: StateLoader,
    save_state: StateSaver,
    append_canary_event: CanaryAppender,
    emit_engine_down_alert: EngineDownEmitter,
) -> bool:
    """Emit `engine_dead` notify-only once per down episode.

    Gate:
      1. heartbeat/snapshot stale for at least 30s;
      2. restart state shows at least one failed respawn (`consecutive_failures >= 1`);
      3. circuit breaker has not already produced the stronger `circuit_broken` alert.

    The generic engine-down alert path is reused for Telegram/webhook/local sink delivery,
    while this module owns the class-specific `ENGINE_DEAD_NOTIFY_ONLY` canary event.
    """
    if snapshot_age_seconds < ENGINE_DEAD_MIN_STALE_SECONDS:
        return False

    state = load_state(data_dir)
    if state.get(_ACTIVE_KEY):
        return False
    if state.get("last_engine_down_alert_key") == ENGINE_DEAD_ALERT_KEY:
        state[_ACTIVE_KEY] = True
        state.setdefault(_FIRST_TS_KEY, _as_float(state.get("engine_down_since_ts"), now))
        save_state(data_dir, state)
        return False

    consecutive_failures = _as_int(state.get("consecutive_failures"))
    if consecutive_failures < 1:
        return False
    if bool(state.get("circuit_broken", False)):
        return False

    first_observed_ts = _as_float(state.get("engine_down_since_ts"), now)
    last_failure_reason = str(state.get("last_failure_reason") or "")
    subject, body = _build_notify_payload(
        now, snapshot_age_seconds, consecutive_failures, last_failure_reason, first_observed_ts,
    )
    emitted = emit_engine_down_alert(data_dir, ENGINE_DEAD_ALERT_KEY, subject, body, now)
    if not emitted:
        return False

    state = load_state(data_dir)
    state[_ACTIVE_KEY] = True
    state[_FIRST_TS_KEY] = first_observed_ts
    state[_EMIT_TS_KEY] = now
    state[_FAILURES_AT_EMIT_KEY] = consecutive_failures
    save_state(data_dir, state)
    append_canary_event(data_dir, {
        "ts": now,
        "event": ENGINE_DEAD_EVENT,
        "incident_class": "engine_dead",
        "dispatch_mode": "notify_only",
        "c4_all_fail_fed": False,
        "snapshot_age_seconds": round(snapshot_age_seconds, 1),
        "consecutive_failures": consecutive_failures,
        "alert_key": ENGINE_DEAD_ALERT_KEY,
    })
    return True


def emit_resolved_if_active(
    data_dir: str,
    now: float,
    load_state: StateLoader,
    save_state: StateSaver,
    append_canary_event: CanaryAppender,
) -> bool:
    """Write an `ENGINE_DEAD_RESOLVED` event when a prior notify-only episode clears."""
    state = load_state(data_dir)
    if not state.get(_ACTIVE_KEY):
        return False

    first_ts = _as_float(state.get(_FIRST_TS_KEY), now)
    emit_ts = _as_float(state.get(_EMIT_TS_KEY), first_ts)
    failures_at_emit = _as_int(state.get(_FAILURES_AT_EMIT_KEY))
    append_canary_event(data_dir, {
        "ts": now,
        "event": ENGINE_DEAD_RESOLVED_EVENT,
        "incident_class": "engine_dead",
        "dispatch_mode": "notify_only",
        "duration_seconds": round(max(0.0, now - first_ts), 1),
        "notify_age_seconds": round(max(0.0, now - emit_ts), 1),
        "failures_at_emit": failures_at_emit,
    })

    for key in (_ACTIVE_KEY, _FIRST_TS_KEY, _EMIT_TS_KEY, _FAILURES_AT_EMIT_KEY):
        state.pop(key, None)
    save_state(data_dir, state)
    return True
