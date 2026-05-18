"""Cron heartbeat sentinel healthchecks [75]-[79].

MODULE_NOTE:
  P1-CRON-INSTALL-WAVE-1（2026-05-18）— 5 個 cron wrapper 已 source/test
  closed 但 crontab 尚未 install。每個 wrapper 在啟動時 touch
  ``${OPENCLAW_DATA_DIR:-/tmp/openclaw}/cron_heartbeat/<name>.last_fire``
  sentinel；本套哨兵以 sentinel mtime 推斷 cron 是否「按時 fire」。

  為什麼 touch-at-start 而非 touch-at-end：``wave9_replay_no_live_mutation_watch.sh``
  以 ``exec python3 - <<PYEOF`` 結尾把 shell 替換成 Python，後面再 append
  ``touch`` 不會執行。改為 start-time touch 即「cron 被排程觸發」的證據，與
  operator 提出的 "verifies cron fires every Nmin" 語意一致；whether the
  workload 自己 succeeded 是各 cron 自己的 exit code + log，不在本哨兵範圍。

  本套哨兵預設 WARN（缺失 / 過時）而非 FAIL：cron infra 不是 promotion-blocking
  surface（operator 明示 2026-05-18 dispatch）。OPENCLAW_CRON_HEARTBEAT_REQUIRED=1
  可升 WARN → FAIL 進入 fail-closed 模式。

  Threshold 設計（heartbeat staleness）：
    [75] panel_aggregator_health        每 5min  → stale > 7min  → WARN
    [76] wave9_replay_no_live_mutation  每 60min → stale > 75min → WARN
    [77] replay_key_rotation_check      每日     → stale > 25h   → WARN
    [78] feature_baseline_writer        每日     → stale > 25h   → WARN
    [79] blocked_symbols_30d_unblock    每週     → stale > 8d    → WARN

  Sentinel 缺失 → WARN「heartbeat file missing — cron not installed or
  has never fired」；過時 → WARN「heartbeat stale (age=<s>s, threshold=<s>s)
  — cron likely stopped firing」；新鮮 → PASS。
"""

from __future__ import annotations

import os
import time
from pathlib import Path


# 預設 sentinel 根目錄；可由 OPENCLAW_CRON_HEARTBEAT_DIR 覆蓋（方便測試）
_DEFAULT_HEARTBEAT_SUBDIR = "cron_heartbeat"
_REQUIRED_ENV = "OPENCLAW_CRON_HEARTBEAT_REQUIRED"
_TRUE_VALUES = {"1", "true", "yes", "on", "required"}


def _resolve_heartbeat_dir() -> Path:
    """解析 sentinel 目錄。優先讀 OPENCLAW_CRON_HEARTBEAT_DIR；否則
    OPENCLAW_DATA_DIR/cron_heartbeat；最後 fallback /tmp/openclaw/cron_heartbeat。
    """
    explicit = os.environ.get("OPENCLAW_CRON_HEARTBEAT_DIR", "").strip()
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip()
    return Path(data_dir) / _DEFAULT_HEARTBEAT_SUBDIR


def _required_mode() -> bool:
    return os.environ.get(_REQUIRED_ENV, "").strip().lower() in _TRUE_VALUES


def _age_seconds(sentinel: Path, now: float) -> float | None:
    """回傳 sentinel 的年齡秒數；不存在或 stat 失敗回 None。"""
    try:
        return max(0.0, now - sentinel.stat().st_mtime)
    except OSError:
        return None


def _format_age(age_s: float) -> str:
    """人類可讀的年齡格式：< 60s 用秒、< 3600 用分、其餘用小時。"""
    if age_s < 60.0:
        return f"{age_s:.0f}s"
    if age_s < 3600.0:
        return f"{age_s / 60.0:.1f}min"
    if age_s < 86400.0:
        return f"{age_s / 3600.0:.1f}h"
    return f"{age_s / 86400.0:.2f}d"


def _classify(
    check_id: str,
    sentinel_name: str,
    cadence_label: str,
    threshold_seconds: float,
    now: float | None = None,
) -> tuple[str, str]:
    """共用 PASS/WARN 判斷邏輯。WARN-by-default；required mode 升 FAIL。"""
    now_ts = time.time() if now is None else now
    sentinel = _resolve_heartbeat_dir() / sentinel_name
    warn_severity = "FAIL" if _required_mode() else "WARN"
    age = _age_seconds(sentinel, now_ts)

    base = (
        f"{check_id} {sentinel_name} cron heartbeat — "
        f"cadence={cadence_label}, threshold={_format_age(threshold_seconds)}, "
        f"sentinel={sentinel}"
    )

    if age is None:
        return (
            warn_severity,
            base
            + "; heartbeat file missing — cron not installed or has never fired",
        )
    if age > threshold_seconds:
        return (
            warn_severity,
            base
            + f"; heartbeat stale age={_format_age(age)} ({age:.0f}s) "
            "— cron likely stopped firing",
        )
    return (
        "PASS",
        base + f"; heartbeat fresh age={_format_age(age)} ({age:.0f}s)",
    )


# ---------------------------------------------------------------------------
# 5 個 healthcheck 公開函數，runner.py 直接登記。
# 為什麼公開五個小函數而非一個 loop：runner.py 既有風格是「一個 check_id 一個
# 函數」，便於 results 列表逐項追蹤；也方便 follow-up wave 改 threshold 時各
# 自獨立。
# ---------------------------------------------------------------------------


def check_75_panel_aggregator_health_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[75] panel_aggregator_health_cron 5min cadence heartbeat。

    cron 由 W1 sub-task 3（E1-γ, 2026-05-11）建立但尚未 install 到 crontab；
    threshold 7min = cadence 5min + 2min grace（與 [66] panel freshness 對齊）。
    """
    return _classify(
        check_id="[75]",
        sentinel_name="panel_aggregator_health.last_fire",
        cadence_label="*/5 * * * *",
        threshold_seconds=7 * 60,
        now=now,
    )


def check_76_wave9_replay_no_live_mutation_watch_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[76] wave9_replay_no_live_mutation_watch hourly heartbeat。

    REF-20 Wave 9 R20-W9-T1 — 14d gradient observation；hourly cron 但尚未
    install。threshold 75min = cadence 60min + 15min grace（cron 起跑延遲常見）。
    """
    return _classify(
        check_id="[76]",
        sentinel_name="wave9_replay_no_live_mutation_watch.last_fire",
        cadence_label="0 * * * *",
        threshold_seconds=75 * 60,
        now=now,
    )


def check_77_replay_key_rotation_check_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[77] replay_key_rotation_check daily heartbeat。

    REF-20 P2a-S1 — daily probe of 90d HMAC key rotation；尚未 install。
    threshold 25h = cadence 24h + 1h grace（DST / drift / leap 容差）。
    """
    return _classify(
        check_id="[77]",
        sentinel_name="replay_key_rotation_check.last_fire",
        cadence_label="0 9 * * *",
        threshold_seconds=25 * 3600,
        now=now,
    )


def check_78_feature_baseline_writer_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[78] feature_baseline_writer daily heartbeat。

    W-AUDIT-4b runtime apply wrapper；daily cron 但尚未 install。
    threshold 25h = cadence 24h + 1h grace。
    """
    return _classify(
        check_id="[78]",
        sentinel_name="feature_baseline_writer.last_fire",
        cadence_label="41 4 * * *",
        threshold_seconds=25 * 3600,
        now=now,
    )


def check_79_blocked_symbols_30d_unblock_check_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[79] blocked_symbols_30d_unblock_check weekly heartbeat。

    W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 — 每週日 04:00 UTC 跑 30d cycle；
    尚未 install。threshold 8d = cadence 7d + 1d grace；配對 [64]
    unblock_candidates_drift（每週日 05:00 UTC，1h 後驗 cron 寫入結果）。
    """
    return _classify(
        check_id="[79]",
        sentinel_name="blocked_symbols_30d_unblock_check.last_fire",
        cadence_label="0 4 * * 0",
        threshold_seconds=8 * 86400,
        now=now,
    )


__all__ = [
    "check_75_panel_aggregator_health_cron_fires",
    "check_76_wave9_replay_no_live_mutation_watch_cron_fires",
    "check_77_replay_key_rotation_check_cron_fires",
    "check_78_feature_baseline_writer_cron_fires",
    "check_79_blocked_symbols_30d_unblock_check_cron_fires",
]
