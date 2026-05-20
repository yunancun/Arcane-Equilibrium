#!/usr/bin/env python3
"""
MODULE_NOTE (English):
  Engine Watchdog (R07-6) — monitors Rust engine health via pipeline_snapshot.json
  staleness. On engine crash (stale > threshold), triggers Python fallback:
  activates hard stops, logs ENGINE_CRASH event. On recovery (fresh snapshot),
  yields back to Rust. Three consecutive crashes within 1h trigger runtime rollback.

MODULE_NOTE (中文):
  引擎看門狗（R07-6）— 通過 pipeline_snapshot.json 過期時間監控 Rust 引擎健康。
  引擎崩潰時（過期 > 閾值），觸發 Python 降級：啟動硬止損，記錄 ENGINE_CRASH 事件。
  恢復時（新鮮快照），讓位給 Rust。1 小時內連續 3 次崩潰觸發運行時回滾。

Usage:
  python engine_watchdog.py                    # Run with defaults
  python engine_watchdog.py --stale-threshold 45 --grace-period 120 --poll-interval 1
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# tomllib (3.11+) or tomli fallback / TOML 解析模組（3.11+ 內建，否則回退 tomli）
try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(levelname)s %(message)s",
)
logger = logging.getLogger("engine_watchdog")

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

STALE_THRESHOLD_SECONDS = 45.0  # Snapshot older than this = engine dead / 超過此時間 = 引擎死亡
POLL_INTERVAL_SECONDS = 2.0     # Check frequency / 檢查頻率
STRIKE_WINDOW_SECONDS = 3600.0  # 3-strike window (1 hour) / 三振窗口（1 小時）
MAX_STRIKES = 3                 # Consecutive crashes before rollback / 回滾前最大連續崩潰數
GRACE_PERIOD_SECONDS = 120.0    # Startup grace period — ignore stale snapshots during this window / 啟動寬限期 — 在此窗口內忽略過期快照

# ═══════════════════════════════════════════════════════════════════════════════
# Fix 2 (2026-04-14): auto-restart configuration / 自動重啟配置
# ═══════════════════════════════════════════════════════════════════════════════

# Exponential backoff table (seconds) keyed by consecutive_failures.
# Extra failures beyond the table clamp to the last value.
# 指數退避表（秒），依 consecutive_failures 索引。超出表長的失敗次數夾在最後一個值。
RESTART_BACKOFF_SECONDS: list[float] = [60.0, 120.0, 300.0, 600.0, 3600.0]
# Consecutive failures before circuit-breaking (stop trying + alert).
# circuit-break 前最大連續失敗次數（超過則停止嘗試 + 升級告警）。
MAX_CONSECUTIVE_FAILURES = 5
# Restart command — invoked via subprocess with timeout.
# 重啟命令 — 透過 subprocess 呼叫帶 timeout。
RESTART_COMMAND = ["bash", "helper_scripts/restart_all.sh", "--engine-only"]
RESTART_TIMEOUT_SECONDS = 120.0
# File paths (under OPENCLAW_DATA_DIR) / 檔案路徑（於 OPENCLAW_DATA_DIR 下）
MAINTENANCE_FLAG = "engine_maintenance.flag"
WATCHDOG_LOCK_FILE = "watchdog.lock"
WATCHDOG_STATE_FILE = "watchdog_state.json"
CANARY_EVENTS_FILE = "canary_events.jsonl"
ENGINE_LOG_FILENAME = "engine.log"
ENGINE_LOG_ROTATED_DIRNAME = "engine_logs"
ENGINE_LOG_ROTATED_GLOB = "engine-*.log"

# ═══════════════════════════════════════════════════════════════════════════════
# WATCHDOG-DNS-CLASSIFY-1 (2026-04-20): classify infrastructure-level failures
# (DNS/HTTP transport outages) vs real engine crashes (panic/assertion).
# Origin: P0-9 RCA — 2026-04-16 power outage produced 30 "ENGINE_CRASH" events
# that were all DNS resolution failures with zero panics; strikes accumulated
# toward 21d stability clock reset. Infrastructure events must not reset it.
# 來源：P0-9 RCA — 停電誤計 30 次 crash；基礎設施事件不應重置 21d 時鐘。
# ═══════════════════════════════════════════════════════════════════════════════

ENGINE_LOG_TAIL_LINES = 20
NETWORK_OUTAGE_MIN_CONSECUTIVE = 5
NETWORK_OUTAGE_RECENT_SECONDS = 15 * 60
NETWORK_OUTAGE_ROTATED_MAX_FILES = 5
# Case-insensitive substrings; ≥NETWORK_OUTAGE_MIN_CONSECUTIVE consecutive matching
# tail lines → classify as network_outage (do not count as strike).
# 不分大小寫子字串；tail 連續 ≥N 條匹配判為 network_outage（不計 strike）。
NETWORK_OUTAGE_PATTERNS: tuple[str, ...] = (
    "temporary failure in name resolution",
    "failed to lookup address information",
    "http transport error",
    "connection refused",
    "dns error",
)
# If ANY tail line contains one of these, override back to engine_crash.
# Panic / assertion is always a real bug, even amid a network outage.
# 若 tail 任一行含以下子字串，強制回到 engine_crash（panic/assertion 一定是 bug）。
CRASH_INDICATOR_PATTERNS: tuple[str, ...] = (
    "panic",
    "assertion failed",
    "stack backtrace",
)
# Cap tail scan cost — engine.log can grow large before rotation.
# 上限 256 KB，避免 log 未輪替時讀取過慢。
ENGINE_LOG_MAX_READ_BYTES = 256 * 1024


@dataclass
class WatchdogState:
    """Internal state of the watchdog / 看門狗內部狀態"""
    engine_alive: bool = True
    crash_timestamps: list[float] = field(default_factory=list)
    total_crashes: int = 0
    last_recovery_ts: float = 0.0
    rollback_triggered: bool = False
    # WATCHDOG-DNS-CLASSIFY-1 (2026-04-20): DNS/transport-outage counters.
    # Separate from crash_timestamps — outages do not count toward 3-strike rule.
    # 網路中斷計數；獨立於 crash_timestamps，不計入三振規則。
    total_network_outages: int = 0
    network_outage_timestamps: list[float] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Core Logic / 核心邏輯
# ═══════════════════════════════════════════════════════════════════════════════


def check_snapshot_freshness(snapshot_path: Path, threshold: float) -> tuple[bool, float]:
    """
    Check if the snapshot file is fresh.
    檢查快照文件是否新鮮。

    Returns: (is_fresh, age_seconds)
    """
    try:
        mtime = snapshot_path.stat().st_mtime
        age = time.time() - mtime
        return age < threshold, age
    except FileNotFoundError:
        return False, float("inf")
    except OSError as e:
        logger.warning("Failed to stat snapshot: %s / 無法獲取快照狀態：%s", e, e)
        return False, float("inf")


def prune_old_strikes(state: WatchdogState, window: float) -> None:
    """Remove crash timestamps outside the strike window / 移除窗口外的崩潰時間戳"""
    cutoff = time.time() - window
    state.crash_timestamps = [ts for ts in state.crash_timestamps if ts > cutoff]


# ═══════════════════════════════════════════════════════════════════════════════
# WATCHDOG-DNS-CLASSIFY-1 (2026-04-20): engine failure classifier
# ═══════════════════════════════════════════════════════════════════════════════


def _read_log_tail(log_path: Path, n_lines: int) -> list[str]:
    """
    Read the last n_lines from log_path without loading the whole file.
    讀取 log_path 最後 n_lines 行，不載入整個檔案。
    Bounded by ENGINE_LOG_MAX_READ_BYTES for cost.
    Raises OSError on unreadable/missing file (caller handles).
    """
    file_size = log_path.stat().st_size
    read_bytes = min(file_size, ENGINE_LOG_MAX_READ_BYTES)
    with open(log_path, "rb") as f:
        if file_size > read_bytes:
            f.seek(file_size - read_bytes)
            f.readline()  # discard partial line at seek boundary / 丟棄 seek 邊界半行
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-n_lines:] if len(lines) > n_lines else lines


def _candidate_failure_log_paths(log_path: Path, now: float | None = None) -> list[Path]:
    """Return active engine.log plus recent rotated logs, newest first.

    `restart_all.sh` moves the pre-restart death log to
    `$OPENCLAW_DATA_DIR/engine_logs/engine-<ts>.log`. A watchdog restart can
    therefore create a fresh `engine.log` whose tail no longer contains the
    outage lines that caused the stale snapshot. Keep the active log first, then
    scan a small recent rotation window for the actual failure context.
    """
    paths: list[Path] = [log_path]
    logs_dir = log_path.parent / ENGINE_LOG_ROTATED_DIRNAME
    now_ts = time.time() if now is None else now

    try:
        candidates = []
        for rotated in logs_dir.glob(ENGINE_LOG_ROTATED_GLOB):
            try:
                stat = rotated.stat()
            except OSError:
                continue
            if not rotated.is_file():
                continue
            age = max(0.0, now_ts - stat.st_mtime)
            if age <= NETWORK_OUTAGE_RECENT_SECONDS:
                candidates.append((stat.st_mtime, rotated))
    except OSError:
        candidates = []

    for _mtime, rotated in sorted(candidates, key=lambda item: item[0], reverse=True)[
        :NETWORK_OUTAGE_ROTATED_MAX_FILES
    ]:
        if rotated not in paths:
            paths.append(rotated)
    return paths


def classify_engine_failure(
    log_path: Path,
    tail_lines: int = ENGINE_LOG_TAIL_LINES,
    min_consecutive: int = NETWORK_OUTAGE_MIN_CONSECUTIVE,
) -> str:
    """
    Classify engine failure by inspecting active and recent rotated engine logs.
    通過檢查 active engine.log 與最近輪替日誌分類引擎故障。

    Returns:
      "network_outage"  iff scanned tails contain NO CRASH_INDICATOR_PATTERNS AND
                         at least one tail has a run of ≥min_consecutive lines
                         all matching any NETWORK_OUTAGE_PATTERNS
                         (case-insensitive).
      "engine_crash"    otherwise (conservative default on I/O error or empty log).
    """
    saw_readable_tail = False
    saw_network_outage = False
    read_errors: list[OSError] = []

    for candidate in _candidate_failure_log_paths(log_path):
        try:
            tail = _read_log_tail(candidate, tail_lines)
        except OSError as e:
            read_errors.append(e)
            continue

        if not tail:
            continue
        saw_readable_tail = True
        lower = [line.lower() for line in tail]

        # (a) crash-indicator override — panic/assertion is always a real bug
        # (a) panic/assertion 強制覆蓋為 engine_crash
        for line in lower:
            if any(pat in line for pat in CRASH_INDICATOR_PATTERNS):
                return "engine_crash"

        # (b) longest run of consecutive network-outage lines within this tail
        # (b) 此 tail 內連續 network-outage 行的最長連續段
        longest_run = 0
        current_run = 0
        for line in lower:
            if any(pat in line for pat in NETWORK_OUTAGE_PATTERNS):
                current_run += 1
                if current_run > longest_run:
                    longest_run = current_run
            else:
                current_run = 0

        if longest_run >= min_consecutive:
            saw_network_outage = True

    if saw_network_outage:
        return "network_outage"
    if not saw_readable_tail and read_errors:
        e = read_errors[0]
        logger.warning(
            "classify_engine_failure: log read failed (%s) — defaulting to engine_crash "
            "/ 日誌讀取失敗（%s）— 預設 engine_crash", e, e,
        )
    return "engine_crash"


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 2 helpers (2026-04-14): auto-restart with circuit breaker / 自動重啟含熔斷
# ═══════════════════════════════════════════════════════════════════════════════


def _state_path(data_dir: str) -> Path:
    return Path(data_dir) / WATCHDOG_STATE_FILE


def load_state(data_dir: str) -> dict:
    """Read persisted restart state. Missing/corrupt file → empty defaults."""
    try:
        with open(_state_path(data_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(data_dir: str, state: dict) -> None:
    """Atomically persist restart state via tmp+rename. Failure is logged, not raised."""
    path = _state_path(data_dir)
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("Failed to save watchdog state: %s / 無法保存看門狗狀態：%s", e, e)


def compute_backoff(consecutive_failures: int) -> float:
    """Index into RESTART_BACKOFF_SECONDS; clamp to last entry for overflow."""
    if consecutive_failures <= 0:
        return RESTART_BACKOFF_SECONDS[0]
    idx = min(consecutive_failures - 1, len(RESTART_BACKOFF_SECONDS) - 1)
    return RESTART_BACKOFF_SECONDS[idx]


def _append_canary_event(data_dir: str, event: dict) -> None:
    """Best-effort append to canary_events.jsonl for external alerting."""
    try:
        path = Path(data_dir) / CANARY_EVENTS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError as e:
        logger.warning("Failed to append canary event: %s", e)


def should_restart(data_dir: str, now: float) -> tuple[bool, str]:
    """
    Decide whether an auto-restart is allowed right now.
    Returns (allowed, reason). Reason is human-readable for logs + canary events.
    決定此刻是否允許自動重啟。
    """
    # Safeguard #2: maintenance flag → operator intent wins / 維護旗標 → 尊重 operator 意圖
    flag_path = Path(data_dir) / MAINTENANCE_FLAG
    if flag_path.exists():
        return False, f"maintenance flag present at {flag_path}"

    state = load_state(data_dir)
    if state.get("circuit_broken", False):
        return False, (
            f"circuit broken after {state.get('consecutive_failures', 0)} consecutive failures "
            "— manual intervention required"
        )

    next_allowed = float(state.get("next_allowed_restart_ts", 0.0))
    if now < next_allowed:
        remaining = next_allowed - now
        return False, f"backoff window active, {remaining:.0f}s remaining"

    return True, "ok"


def trigger_restart(data_dir: str) -> bool:
    """
    Invoke RESTART_COMMAND with a timeout. Updates state regardless of outcome:
    success → reset consecutive_failures; failure → increment + maybe circuit-break.
    Returns True on success, False on any failure.
    呼叫重啟命令並更新狀態。成功清零連續失敗次數；失敗遞增並可能熔斷。
    """
    state = load_state(data_dir)
    consecutive = int(state.get("consecutive_failures", 0))
    now = time.time()

    logger.warning(
        "Triggering auto-restart (attempt %d, timeout=%.0fs) / 觸發自動重啟（嘗試 %d，超時 %.0f秒）",
        consecutive + 1, RESTART_TIMEOUT_SECONDS, consecutive + 1, RESTART_TIMEOUT_SECONDS,
    )

    success = False
    failure_reason = ""
    try:
        # cwd must be repo root so restart_all.sh can resolve its own relative paths.
        # cwd 必須為 repo 根以讓 restart_all.sh 解析相對路徑。
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            RESTART_COMMAND,
            cwd=str(repo_root),
            timeout=RESTART_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            success = True
        else:
            failure_reason = f"exit={result.returncode} stderr={result.stderr[-500:]}"
    except subprocess.TimeoutExpired:
        failure_reason = f"restart command exceeded {RESTART_TIMEOUT_SECONDS}s timeout"
    except (OSError, subprocess.SubprocessError) as e:
        failure_reason = f"subprocess error: {e}"

    if success:
        state["consecutive_failures"] = 0
        state["last_restart_success_ts"] = now
        state["circuit_broken"] = False
        state["next_allowed_restart_ts"] = 0.0
        state["last_failure_reason"] = ""
        save_state(data_dir, state)
        logger.info("Auto-restart succeeded / 自動重啟成功")
        _append_canary_event(data_dir, {
            "ts": now, "event": "RESTART_SUCCESS",
            "consecutive_failures_before": consecutive,
        })
        return True

    # Failure path / 失敗路徑
    consecutive += 1
    state["consecutive_failures"] = consecutive
    state["last_restart_failure_ts"] = now
    state["last_failure_reason"] = failure_reason
    backoff = compute_backoff(consecutive)
    state["next_allowed_restart_ts"] = now + backoff

    if consecutive >= MAX_CONSECUTIVE_FAILURES:
        state["circuit_broken"] = True
        logger.critical(
            "CIRCUIT BROKEN — %d consecutive restart failures, manual intervention required "
            "/ 熔斷觸發 — %d 次連續重啟失敗，需人工介入",
            consecutive, consecutive,
        )
        _append_canary_event(data_dir, {
            "ts": now, "event": "RESTART_CIRCUIT_BROKEN",
            "consecutive_failures": consecutive, "reason": failure_reason,
        })
    else:
        logger.error(
            "Auto-restart failed (%d/%d): %s — next attempt allowed in %.0fs "
            "/ 自動重啟失敗（%d/%d）：%s — 下次允許 %.0f 秒後",
            consecutive, MAX_CONSECUTIVE_FAILURES, failure_reason, backoff,
            consecutive, MAX_CONSECUTIVE_FAILURES, failure_reason, backoff,
        )
        _append_canary_event(data_dir, {
            "ts": now, "event": "RESTART_FAILED",
            "consecutive_failures": consecutive, "backoff_seconds": backoff,
            "reason": failure_reason,
        })

    save_state(data_dir, state)
    return False


def on_engine_crash(
    state: WatchdogState,
    snapshot_age: float,
    data_dir: str = "",
    log_path: Optional[Path] = None,
) -> str:
    """
    Handle engine crash detection.
    處理引擎崩潰檢測。

    Returns: action taken ("fallback" | "rollback" | "network_outage" | "none")

    WATCHDOG-DNS-CLASSIFY-1 (2026-04-20): when log_path is given, inspect the
    engine.log tail; a pure DNS/transport outage (no panic/assertion + ≥5
    consecutive network-error lines) classifies as `network_outage` — no strike
    is counted, no auto-restart is attempted (restart can't fix DNS and would
    burn the circuit-breaker). engine_alive still flips to False so that the
    recovery path fires normally once the network comes back.
    """
    if not state.engine_alive:
        return "none"  # Already in crash state / 已在崩潰狀態

    # Classify first. A null log_path preserves the pre-DNS-CLASSIFY-1 behavior
    # (always engine_crash), keeping existing callers unaffected.
    # 先分類；log_path=None 時維持舊行為（總是 engine_crash）以不影響既有呼叫者。
    classification = "engine_crash"
    if log_path is not None:
        classification = classify_engine_failure(log_path)

    if classification == "network_outage":
        state.engine_alive = False
        state.total_network_outages += 1
        state.network_outage_timestamps.append(time.time())
        logger.warning(
            "NETWORK_OUTAGE classified — snapshot age=%.1fs, total outages=%d "
            "(strike NOT counted, auto-restart skipped) "
            "/ 網路中斷分類 — 快照年齡=%.1f秒，總次數=%d（不計 strike，跳過自動重啟）",
            snapshot_age, state.total_network_outages,
            snapshot_age, state.total_network_outages,
        )
        if data_dir:
            _append_canary_event(data_dir, {
                "ts": time.time(),
                "event": "NETWORK_OUTAGE",
                "snapshot_age_seconds": snapshot_age,
                "total_outages": state.total_network_outages,
            })
        return "network_outage"

    state.engine_alive = False
    state.total_crashes += 1
    state.crash_timestamps.append(time.time())

    logger.error(
        "ENGINE_CRASH detected — snapshot age=%.1fs, total crashes=%d "
        "/ 檢測到引擎崩潰 — 快照年齡=%.1f秒，總崩潰數=%d",
        snapshot_age, state.total_crashes, snapshot_age, state.total_crashes,
    )

    # Fix 2 (2026-04-14): attempt auto-restart BEFORE strike logic. Rationale:
    # a successful restart yields a fresh snapshot on the next poll, which
    # naturally transitions us back via on_engine_recovery(). Strike counting
    # remains as a secondary safety net for restart-storm scenarios.
    # 修復 2：嘗試自動重啟先於 strike 判定。成功重啟後下次 poll 會看到新鮮快照，
    # 自然走 on_engine_recovery() 復原；strike 計數作為重啟風暴的次級安全網。
    if data_dir:
        now = time.time()
        allowed, reason = should_restart(data_dir, now)
        if allowed:
            trigger_restart(data_dir)
        else:
            logger.warning(
                "Auto-restart skipped: %s / 跳過自動重啟：%s", reason, reason,
            )
            _append_canary_event(data_dir, {
                "ts": now, "event": "RESTART_SKIPPED", "reason": reason,
            })

    # Check 3-strike rule / 檢查三振規則
    prune_old_strikes(state, STRIKE_WINDOW_SECONDS)
    if len(state.crash_timestamps) >= MAX_STRIKES:
        logger.critical(
            "3-STRIKE TRIGGERED — %d crashes in %.0fs window → runtime rollback "
            "/ 三振觸發 — %d 次崩潰在 %.0f 秒窗口內 → 運行時回滾",
            len(state.crash_timestamps), STRIKE_WINDOW_SECONDS,
            len(state.crash_timestamps), STRIKE_WINDOW_SECONDS,
        )
        state.rollback_triggered = True
        return "rollback"

    logger.warning(
        "Activating Python fallback (strike %d/%d) "
        "/ 啟動 Python 降級（第 %d/%d 振）",
        len(state.crash_timestamps), MAX_STRIKES,
        len(state.crash_timestamps), MAX_STRIKES,
    )
    return "fallback"


def on_engine_recovery(state: WatchdogState) -> None:
    """
    Handle engine recovery detection.
    處理引擎恢復檢測。
    """
    if state.engine_alive:
        return  # Already alive / 已恢復

    state.engine_alive = True
    state.last_recovery_ts = time.time()
    logger.info(
        "ENGINE_RECOVERED — Rust engine snapshot is fresh again "
        "/ 引擎已恢復 — Rust 引擎快照恢復新鮮",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# P0-ENGINE-HALTSESSION-STUCK-FIX Layer B (2026-05-19): Trading inert probe
# 業務心跳探測 — 區分「engine 活著但交易停滯」與「engine 崩潰」兩個不同維度
# 來源：spec v0.2 §4；獨立於 ENGINE_CRASH 路徑，severity=WARNING，不重啟 engine
# ═══════════════════════════════════════════════════════════════════════════════

# Per-env threshold config 預設值（spec §4.3 fold-in）
# 當 TOML 缺檔或 engine label 無對應節時，落 default（demo 保守值）。
# Live 配置最敏感（15min/10min）；Demo 最 relaxed（60min/20min）；
# LiveDemo 中間（30min/15min）；Paper 沿用 demo（dormant default）。
INERT_PROBE_DEFAULTS = {
    "default": {
        "paper_paused_threshold_seconds": 3600.0,
        "intents_zero_delta_window_seconds": 1200.0,
    },
    "paper": {
        "paper_paused_threshold_seconds": 3600.0,
        "intents_zero_delta_window_seconds": 1200.0,
    },
    "demo": {
        "paper_paused_threshold_seconds": 3600.0,
        "intents_zero_delta_window_seconds": 1200.0,
    },
    "live_demo": {
        "paper_paused_threshold_seconds": 1800.0,
        "intents_zero_delta_window_seconds": 900.0,
    },
    "live": {
        "paper_paused_threshold_seconds": 900.0,
        "intents_zero_delta_window_seconds": 600.0,
    },
}

INERT_PROBE_TOML = "watchdog_inert_probe.toml"
INERT_STATE_FILE = "watchdog_inert_state.json"


@dataclass
class InertState:
    """
    Per-engine inert probe state. 看門狗 inert probe 每引擎獨立狀態。

    為什麼 per-engine：spec B-7 要求 demo halt 不影響 live alarm。
    為什麼 in-memory：watchdog restart 即重置（state 持久化 optional via
    INERT_STATE_FILE，僅 best-effort recover incident_active）。
    """
    # 何時開始 paper_paused（None = 當前未 paused）
    paper_paused_since: Optional[float] = None
    # 最近 intent timestamp_ms（snapshot.recent_intents max；0 = 從未見過 intent）
    last_intent_ts_ms: int = 0
    # 最近 alarm 時間 + trigger（cooldown 用）
    last_alarm_ts: Optional[float] = None
    last_alarm_trigger: Optional[str] = None
    # incident 進行中（與 last_alarm_* 配對；clear 後 reset 為 False）
    incident_active: bool = False


def load_inert_probe_config(config_path: Path) -> dict:
    """
    讀取 watchdog_inert_probe.toml。
    為什麼 fail-soft：缺檔 / 壞檔不應令 watchdog 啟動失敗（degradation = use defaults）；
    parse error 例外 RAISE（per spec §4.3 末段 fail-loud RAISE on TOML parse error）。

    Returns merged config: defaults dict ∪ TOML overrides。
    """
    config: dict = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}
    if tomllib is None:
        logger.warning(
            "tomllib unavailable (Python <3.11 and no tomli) — using inert probe defaults "
            "/ tomllib 不可用（Python<3.11 且無 tomli）— 使用 inert probe 預設值",
        )
        return config

    if not config_path.exists():
        logger.info(
            "Inert probe TOML not found at %s — using defaults / 找不到 TOML，使用預設",
            config_path,
        )
        return config

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        # spec §4.3 末段：parse error fail-loud RAISE
        # 為什麼 RAISE 而非 swallow：壞 TOML 表 operator 編輯錯誤，
        # 靜默 fallback 會讓 operator 以為配置生效，造成隱性風險。
        logger.critical("Inert probe TOML parse error at %s: %s", config_path, e)
        raise

    for env_label, overrides in data.items():
        if not isinstance(overrides, dict):
            continue
        slot = config.setdefault(env_label, dict(INERT_PROBE_DEFAULTS["default"]))
        for key, val in overrides.items():
            if key in ("paper_paused_threshold_seconds", "intents_zero_delta_window_seconds"):
                try:
                    parsed = float(val)
                except (TypeError, ValueError):
                    logger.warning(
                        "Inert probe TOML [%s].%s value invalid: %r — falling back to default",
                        env_label, key, val,
                    )
                    continue
                # Round 2 LOW-1：拒收 <=0 threshold
                # 為什麼：負值/0 會令 elapsed_seconds 永遠 >= threshold 觸 always-alarm；
                # 比起靜默接受誤配置，fallback default + warning 更安全（spec §6 uncertainty
                # defaults conservative）。
                if parsed <= 0:
                    logger.warning(
                        "Inert probe TOML [%s].%s must be > 0, got %r — falling back to default",
                        env_label, key, val,
                    )
                    continue
                slot[key] = parsed
    return config


def resolve_engine_label_for_snapshot(snapshot_path: Path, snapshot_data: Optional[dict]) -> str:
    """
    從 snapshot 路徑 + JSON 內容解析 engine label。

    為什麼以檔案 basename 為主鍵：spec §4.3 + §4.8 — watchdog 監控
    `pipeline_snapshot_<engine>.json` per-engine fan-out，basename 是 deterministic
    engine identity；snapshot 內 `trading_mode` field 為 `pipeline_kind`（paper/
    demo/live）不含 endpoint，因此 LiveDemo 與 Live 無法從 snapshot 區分。

    Lookup chain:
      1. file basename 含 `_paper` / `_demo` / `_live` → 對應 label
      2. compat path `pipeline_snapshot.json` → 讀 JSON.trading_mode
      3. fallback "default"
    """
    name = snapshot_path.name
    if name == "pipeline_snapshot_paper.json":
        return "paper"
    if name == "pipeline_snapshot_demo.json":
        return "demo"
    if name == "pipeline_snapshot_live.json":
        return "live"
    # compat 主檔：讀 snapshot 內 trading_mode 字段
    # 為什麼讀 trading_mode：Rust pipeline_types.rs serializes `pipeline_kind` as
    # `trading_mode` for backward compat（snake_case → "paper"/"demo"/"live"）。
    if snapshot_data is not None:
        mode = snapshot_data.get("trading_mode")
        if isinstance(mode, str) and mode in ("paper", "demo", "live"):
            return mode
    return "default"


def read_snapshot_json(snapshot_path: Path) -> Optional[dict]:
    """
    讀取 pipeline_snapshot JSON。

    為什麼 fail-soft：snapshot 短暫 stale / partial write / 缺檔對 inert probe
    都是「無證據可判斷」即跳過此次 poll，不報 alarm；engine_alive 由
    check_snapshot_freshness 獨立判定。
    """
    try:
        with open(snapshot_path, "rb") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.debug(
            "Inert probe: snapshot read fail %s: %s / 快照讀取失敗",
            snapshot_path, e,
        )
    return None


def detect_paper_paused_stuck(
    snapshot: dict, state: InertState, threshold_seconds: float, now: float
) -> bool:
    """
    探測 paper_paused 持續超過 threshold（spec §4.3 condition 1）。

    為什麼 mode_snapshots 優先：spec §4.8 多引擎 — 每 engine 一份
    ModeStateSnapshot，內含 paper_paused / halt_kind / halt_set_ts_ms；頂層
    paper_paused 是 compat fallback。優先讀巢狀以確保 per-engine 正確。

    Side effect: state.paper_paused_since 跟隨 paper_paused transitions 更新。
    """
    paper_paused = _read_paper_paused(snapshot)
    if not paper_paused:
        state.paper_paused_since = None
        return False

    # 第一次見到 paper_paused=true：record 起始時間
    # halt_set_ts_ms 若存在則用 engine 端起點，否則用 watchdog 觀察起點
    if state.paper_paused_since is None:
        halt_set_ts_ms = _read_halt_set_ts_ms(snapshot)
        if halt_set_ts_ms > 0:
            # 用 engine 端 wall-clock 起點，跨 watchdog restart 一致
            # 為什麼：spec §4.8 + Layer A halt_set_ts_ms 已寫入 snapshot；
            # 用此 anchor 避免 watchdog restart 重置 incident 起點。
            state.paper_paused_since = halt_set_ts_ms / 1000.0
        else:
            state.paper_paused_since = now

    elapsed = now - state.paper_paused_since
    return elapsed >= threshold_seconds


def _read_paper_paused(snapshot: dict) -> bool:
    """從 mode_snapshots 或頂層讀 paper_paused（priority: mode_snapshot > top-level）。"""
    mode_snapshots = snapshot.get("mode_snapshots")
    if isinstance(mode_snapshots, dict):
        # 取任一 mode_snapshot 的 paper_paused（per-engine snapshot 應只含 1 個 mode）
        for mode_state in mode_snapshots.values():
            if isinstance(mode_state, dict) and "paper_paused" in mode_state:
                return bool(mode_state.get("paper_paused", False))
    return bool(snapshot.get("paper_paused", False))


def _read_halt_set_ts_ms(snapshot: dict) -> int:
    """從 mode_snapshots 或頂層讀 halt_set_ts_ms。"""
    mode_snapshots = snapshot.get("mode_snapshots")
    if isinstance(mode_snapshots, dict):
        for mode_state in mode_snapshots.values():
            if isinstance(mode_state, dict):
                val = mode_state.get("halt_set_ts_ms", 0)
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return 0
    val = snapshot.get("halt_set_ts_ms", 0)
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def detect_intents_zero_delta(
    snapshot: dict, state: InertState, window_seconds: float, now: float
) -> bool:
    """
    探測 recent_intents 滾動窗口無增長（spec §4.3 condition 2）。

    為什麼用 max(timestamp_ms)：snapshot.recent_intents 是 ring buffer（max 50 entries）；
    若引擎一直推新 intent，max 持續往前；若停滯，max 不變超過 window 即 inert。

    注意：spec §4.3 範例碼用 `i.get("ts_ms", 0)` 但 Rust schema 實際是
    `timestamp_ms`（pipeline_types.rs TimestampedIntent::timestamp_ms）。
    本實作以實際 schema 為準。
    """
    intents = snapshot.get("recent_intents", [])
    if not isinstance(intents, list):
        return False
    # boot 期無 intent 不算 inert（避免冷啟動 false-positive）
    if not intents:
        return False

    latest_ts_ms = 0
    for entry in intents:
        if isinstance(entry, dict):
            ts = entry.get("timestamp_ms", 0)
            try:
                ts_int = int(ts)
            except (TypeError, ValueError):
                continue
            if ts_int > latest_ts_ms:
                latest_ts_ms = ts_int

    if latest_ts_ms == 0:
        return False

    state.last_intent_ts_ms = latest_ts_ms
    now_ms = int(now * 1000)
    elapsed_ms = now_ms - latest_ts_ms
    return elapsed_ms >= window_seconds * 1000


def evaluate_inert_probe(
    snapshot_path: Path,
    snapshot: dict,
    state: InertState,
    config: dict,
    now: float,
    data_dir: str,
) -> Optional[str]:
    """
    主 probe evaluator — 每 poll cycle 對每 engine 跑一次。

    Returns:
      "paper_paused_stuck"     condition 1 fired
      "intents_zero_delta"     condition 2 fired
      "cleared"                先前 incident_active 但兩個 condition 都不滿足
      None                     正常 / 無事件

    為什麼 condition 1 優先：spec §4.3 combined trigger = condition_1 OR
    condition_2；當兩個都觸發時用 paper_paused 較強訊號（halt-driven）。

    Cooldown：incident_active=True 期間不重發 alarm，直到 cleared transition。
    """
    engine = resolve_engine_label_for_snapshot(snapshot_path, snapshot)
    env_cfg = config.get(engine) or config.get("default") or INERT_PROBE_DEFAULTS["default"]
    pp_threshold = float(env_cfg.get("paper_paused_threshold_seconds", 3600.0))
    iz_window = float(env_cfg.get("intents_zero_delta_window_seconds", 1200.0))

    cond_paused = detect_paper_paused_stuck(snapshot, state, pp_threshold, now)
    cond_intents = detect_intents_zero_delta(snapshot, state, iz_window, now)

    if cond_paused or cond_intents:
        trigger = "paper_paused_stuck" if cond_paused else "intents_zero_delta"
        if state.incident_active:
            # cooldown — 已 alarm 過此 incident，不重發
            return None
        # 第一次 fire：寫 alarm 並 mark incident_active
        state.incident_active = True
        state.last_alarm_ts = now
        state.last_alarm_trigger = trigger
        _emit_inert_alarm(snapshot_path, snapshot, state, engine, env_cfg, trigger, now, data_dir)
        return trigger

    # 兩個 condition 都不滿足 — 若先前 incident_active，寫 CLEARED + reset
    if state.incident_active:
        _emit_inert_cleared(state, engine, now, data_dir)
        state.incident_active = False
        state.last_alarm_ts = None
        state.last_alarm_trigger = None
        return "cleared"
    return None


def _emit_inert_alarm(
    snapshot_path: Path,
    snapshot: dict,
    state: InertState,
    engine: str,
    env_cfg: dict,
    trigger: str,
    now: float,
    data_dir: str,
) -> None:
    """寫 watchdog.log + canary_events.jsonl alarm（spec §4.4）。"""
    halt_kind = _read_halt_kind(snapshot)
    halt_set_ts_ms = _read_halt_set_ts_ms(snapshot)
    halt_ttl_remaining_ms = snapshot.get("halt_ttl_remaining_ms")
    paper_paused_since = state.paper_paused_since or now
    elapsed_seconds = now - paper_paused_since if trigger == "paper_paused_stuck" else (
        (now * 1000 - state.last_intent_ts_ms) / 1000.0 if state.last_intent_ts_ms > 0 else 0.0
    )
    threshold_seconds = float(
        env_cfg.get("paper_paused_threshold_seconds")
        if trigger == "paper_paused_stuck"
        else env_cfg.get("intents_zero_delta_window_seconds")
    )

    logger.warning(
        "TRADING_INERT_PROLONGED detected trigger=%s engine=%s elapsed=%.1fs "
        "halt_kind=%s halt_set_ts_ms=%s halt_ttl_remaining_ms=%s threshold=%.0fs snapshot=%s "
        "/ 業務停滯告警 觸發=%s 引擎=%s 持續=%.1fs",
        trigger, engine, elapsed_seconds,
        halt_kind, halt_set_ts_ms, halt_ttl_remaining_ms, threshold_seconds, snapshot_path,
        trigger, engine, elapsed_seconds,
    )
    if data_dir:
        _append_canary_event(data_dir, {
            "ts": now,
            "event": "TRADING_INERT_PROLONGED",
            "trigger": trigger,
            "engine": engine,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "halt_kind": halt_kind,
            "halt_set_ts_ms": halt_set_ts_ms,
            "halt_ttl_remaining_ms": halt_ttl_remaining_ms,
            "threshold_seconds": threshold_seconds,
            "snapshot_path": str(snapshot_path),
        })


def _emit_inert_cleared(state: InertState, engine: str, now: float, data_dir: str) -> None:
    """寫 TRADING_INERT_CLEARED log + jsonl（spec §4.5）。

    Round 2 LOW-2：previous_trigger 為 None 時 fallback "no_trigger_recorded"
    （非 "unknown"），明確告訴 audit reader 是 state 載入時即缺，而非新 incident。
    為什麼：state.json corruption / partial load 場景下 last_alarm_trigger 可能
    為 None；保留語義 marker 讓 7d observation operator 能區分 normal vs
    degraded state。
    """
    alarm_ts = state.last_alarm_ts or now
    duration = now - alarm_ts
    previous_trigger = state.last_alarm_trigger or "no_trigger_recorded"
    logger.info(
        "TRADING_INERT_CLEARED engine=%s previous_trigger=%s duration=%.1fs "
        "/ 業務停滯解除 engine=%s 持續=%.1fs",
        engine, previous_trigger, duration,
        engine, duration,
    )
    if data_dir:
        _append_canary_event(data_dir, {
            "ts": now,
            "event": "TRADING_INERT_CLEARED",
            "engine": engine,
            "previous_alarm_ts": alarm_ts,
            "previous_trigger": previous_trigger,
            "alarm_duration_seconds": round(duration, 1),
        })


def _read_halt_kind(snapshot: dict) -> Optional[str]:
    """從 mode_snapshots 或頂層讀 halt_kind。"""
    mode_snapshots = snapshot.get("mode_snapshots")
    if isinstance(mode_snapshots, dict):
        for mode_state in mode_snapshots.values():
            if isinstance(mode_state, dict) and "halt_kind" in mode_state:
                kind = mode_state.get("halt_kind")
                return kind if isinstance(kind, str) or kind is None else None
    kind = snapshot.get("halt_kind")
    return kind if isinstance(kind, str) or kind is None else None


def load_inert_state(data_dir: str) -> dict[str, InertState]:
    """
    讀取 inert state 持久化檔（best-effort）。
    為什麼持久化：spec B-5 — watchdog restart 不重置 incident 狀態；
    為什麼 best-effort：state 缺失最壞 = 重新偵測一輪 alarm；不影響正確性。

    Round 2 HIGH-1 修補：每 engine 條目用 inner try-except 包 InertState 構造，
    type-mismatch JSON（例如 `last_intent_ts_ms="not_int"`）會被 catch 並 skip
    該 engine 條目而非 raise 致 watchdog 啟動 crash。其餘 engine 條目保留。
    為什麼 partial recovery 優於全空：watchdog 是 critical canary process，
    不可因單一 engine 壞 state 全失 incident 跨 restart 連續性。
    """
    path = Path(data_dir) / INERT_STATE_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, InertState] = {}
    for engine, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        try:
            result[engine] = InertState(
                paper_paused_since=payload.get("paper_paused_since"),
                last_intent_ts_ms=int(payload.get("last_intent_ts_ms", 0)),
                last_alarm_ts=payload.get("last_alarm_ts"),
                last_alarm_trigger=payload.get("last_alarm_trigger"),
                incident_active=bool(payload.get("incident_active", False)),
            )
        except (TypeError, ValueError) as exc:
            # 為什麼 warning 而非 raise：spec B-5 best-effort；壞 state 條目
            # 損失 = 重新偵測一輪 alarm（cold-start 等效），不應整體 fail-closed。
            logger.warning(
                "Inert state for engine=%s has bad type, skipping entry: %s "
                "/ 引擎 %s 持久化 state 型別異常，跳過該條目",
                engine, exc, engine,
            )
            continue
    return result


def _serialize_inert_states(states: dict[str, InertState]) -> dict:
    """純函數：把 InertState dict 轉成 JSON-serializable dict。
    為什麼抽出：transition-only write 需在 save 前先做 diff 比較，diff 對
    serializable shape 比對更穩（避免不同 dataclass instance 但內容同被誤判 dirty）。"""
    return {
        engine: {
            "paper_paused_since": s.paper_paused_since,
            "last_intent_ts_ms": s.last_intent_ts_ms,
            "last_alarm_ts": s.last_alarm_ts,
            "last_alarm_trigger": s.last_alarm_trigger,
            "incident_active": s.incident_active,
        }
        for engine, s in states.items()
    }


def save_inert_state(
    data_dir: str,
    states: dict[str, InertState],
    last_written: Optional[dict] = None,
) -> Optional[dict]:
    """
    原子寫 inert state 持久化檔（Round 2 MEDIUM-1：transition-only write）。

    為什麼加 last_written 參數：spec §B-5 持久化目的是跨 restart 連續性；
    每 poll 寫盤每小時 ~1800 次（POLL_INTERVAL=2s），但實際 state 99%+ poll
    無變化。caller 傳上次寫入的 serializable snapshot；本函數比對 new vs
    last_written，相等則 skip 寫盤 + 直接 return last_written。

    Args:
        data_dir: 持久化目錄
        states: 當前 inert states
        last_written: 上次寫盤的 serializable dict；None = first write

    Returns:
        當次寫盤後的 serializable snapshot（caller 應更新 last_written 為此值）；
        寫盤失敗時 return last_written（caller 下次 poll 仍會重試比對）。
    """
    new_serialized = _serialize_inert_states(states)
    # 為什麼 dict equality：transition 必伴隨 dataclass 字段 mutate；equality
    # 比對輕量（dict-level 雜湊），相等表 state 無變動可 skip 寫盤。
    if last_written is not None and new_serialized == last_written:
        return last_written

    path = Path(data_dir) / INERT_STATE_FILE
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_serialized, f, indent=2)
        os.replace(tmp, path)
        return new_serialized
    except OSError as e:
        logger.warning("Failed to save inert state: %s", e)
        # 為什麼 return last_written 而非 None：寫盤失敗下次 poll 仍應比對舊
        # 快取避免 dirty=True 反覆 retry；磁盤恢復後自然 transition 觸發寫。
        return last_written


def run_inert_probe_once(
    snapshot_paths: list[Path],
    inert_states: dict[str, InertState],
    config: dict,
    data_dir: str,
    now: float,
) -> dict[Path, Optional[str]]:
    """
    對所有 fresh snapshot 跑一次 inert probe。
    回傳每路徑的事件結果（trigger / "cleared" / None）。

    為什麼僅對 fresh snapshot 跑：spec §4.8 simplification — stale snapshot 走
    on_engine_crash 路徑優先，inert probe 只看活著但停滯。
    """
    events: dict[Path, Optional[str]] = {}
    for sp in snapshot_paths:
        # 為什麼用 STALE_THRESHOLD_SECONDS：與 run_watchdog 一致；fresh 才探 inert
        is_fresh, _ = check_snapshot_freshness(sp, STALE_THRESHOLD_SECONDS)
        if not is_fresh:
            continue
        snapshot = read_snapshot_json(sp)
        if snapshot is None:
            continue
        engine = resolve_engine_label_for_snapshot(sp, snapshot)
        state = inert_states.setdefault(engine, InertState())
        events[sp] = evaluate_inert_probe(sp, snapshot, state, config, now, data_dir)
    return events


def run_watchdog(
    data_dir: str,
    stale_threshold: float = STALE_THRESHOLD_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    max_iterations: Optional[int] = None,
    grace_period: float = GRACE_PERIOD_SECONDS,
    inert_probe_enabled: bool = True,
    inert_probe_config_path: Optional[Path] = None,
) -> WatchdogState:
    """
    Main watchdog loop. Monitors snapshot freshness and triggers fallback/rollback.
    主看門狗循環。監控快照新鮮度並觸發降級/回滾。

    Args:
        data_dir: Directory containing pipeline_snapshot.json
        stale_threshold: Seconds before snapshot is considered stale
        poll_interval: Seconds between checks
        max_iterations: Stop after N iterations (None = run forever, for testing)
        grace_period: Seconds after startup during which stale snapshots are ignored / 啟動後寬限期秒數，期間忽略過期快照
        inert_probe_enabled: P0-ENGINE-HALTSESSION-STUCK-FIX Layer B — enable
            business heartbeat probe（spec §4）；預設 enabled，可由 CLI 關閉
        inert_probe_config_path: 顯式指定 inert probe TOML 路徑；None 走預設
            `helper_scripts/canary/watchdog_inert_probe.toml`
    """
    data_path = Path(data_dir)
    # 3E-5: monitor per-engine + compat snapshots — system alive if ANY engine is fresh.
    # 3E-5：監控每引擎 + 兼容快照 — 任一引擎新鮮即視為存活。
    snapshot_paths = [
        data_path / "pipeline_snapshot.json",
        data_path / "pipeline_snapshot_paper.json",
        data_path / "pipeline_snapshot_demo.json",
        data_path / "pipeline_snapshot_live.json",
    ]
    # WATCHDOG-DNS-CLASSIFY-1: engine.log tail drives outage-vs-crash classification.
    # Missing file is fine — classifier falls back to "engine_crash" on OSError.
    # 引擎日誌路徑；檔案缺失時分類器回退為 engine_crash。
    engine_log_path = data_path / ENGINE_LOG_FILENAME
    state = WatchdogState()

    # P0-ENGINE-HALTSESSION-STUCK-FIX Layer B 初始化：載 TOML + 持久化 state
    # 為什麼 startup 載 state：spec B-5 — watchdog restart 不重置 incident
    inert_states: dict[str, InertState] = {}
    inert_config: dict = {}
    # Round 2 MEDIUM-1：上次寫盤 serializable snapshot 快取，作 transition-only diff 基準
    inert_last_written: Optional[dict] = None
    if inert_probe_enabled:
        if inert_probe_config_path is None:
            inert_probe_config_path = Path(__file__).resolve().parent / INERT_PROBE_TOML
        inert_config = load_inert_probe_config(inert_probe_config_path)
        inert_states = load_inert_state(data_dir)
        # 為什麼從 load 後 state 初始化 last_written：cold start 寫一次後與 disk 對齊，
        # 之後 poll 比對才能正確判斷 transition；若不對齊則 first save 會被誤判 skip。
        inert_last_written = _serialize_inert_states(inert_states)
        logger.info(
            "Inert probe enabled — config=%s loaded_state_engines=%s "
            "/ Inert probe 啟用 — 配置=%s 已載入引擎狀態=%s",
            inert_probe_config_path, list(inert_states.keys()),
            inert_probe_config_path, list(inert_states.keys()),
        )

    iteration = 0
    # Record startup time for grace period calculation / 記錄啟動時間用於寬限期計算
    start_time = time.time()

    logger.info(
        "Watchdog started — monitoring %s (threshold=%.1fs, poll=%.1fs, grace=%.1fs) "
        "/ 看門狗啟動 — 監控 %s（閾值=%.1f秒，輪詢=%.1f秒，寬限期=%.1f秒）",
        data_path, stale_threshold, poll_interval, grace_period,
        data_path, stale_threshold, poll_interval, grace_period,
    )

    while True:
        if max_iterations is not None and iteration >= max_iterations:
            break

        # Check all snapshot files — alive if ANY is fresh (3E-5)
        # 檢查所有快照文件 — 任一新鮮即存活
        best_age = float("inf")
        is_fresh = False
        for sp in snapshot_paths:
            sp_fresh, sp_age = check_snapshot_freshness(sp, stale_threshold)
            if sp_fresh:
                is_fresh = True
            if sp_age < best_age:
                best_age = sp_age
        age = best_age

        if is_fresh:
            on_engine_recovery(state)
        else:
            # Grace period: ignore stale snapshots during startup window, do not count strikes
            # 寬限期：啟動窗口內忽略過期快照，不計入 strike 計數
            elapsed = time.time() - start_time
            if elapsed < grace_period:
                logger.info(
                    "GRACE_PERIOD: snapshot stale (age=%.1fs) but within grace period "
                    "(%.1f/%.1fs elapsed), ignoring "
                    "/ 寬限期：快照過期（年齡=%.1f秒）但仍在寬限期內"
                    "（已過 %.1f/%.1f 秒），忽略",
                    age, elapsed, grace_period,
                    age, elapsed, grace_period,
                )
            else:
                action = on_engine_crash(
                    state, age, data_dir=str(data_path), log_path=engine_log_path,
                )
                if action == "rollback":
                    logger.critical("Initiating runtime rollback... / 啟動運行時回滾...")
                    break

        # Layer B：對所有 fresh snapshot 跑 inert probe（spec §4）
        # 為什麼放在 ENGINE_CRASH 判定之後：spec §4.8 — stale 走 crash 路徑優先；
        # inert probe 僅看 fresh-but-inert 維度
        if inert_probe_enabled:
            run_inert_probe_once(
                snapshot_paths, inert_states, inert_config, str(data_path), time.time(),
            )
            # 持久化（best-effort；失敗不影響主循環）
            # Round 2 MEDIUM-1：傳 inert_last_written 進 save，相等則 skip 寫盤
            inert_last_written = save_inert_state(
                str(data_path), inert_states, inert_last_written,
            )

        iteration += 1
        time.sleep(poll_interval)

    return state


# ═══════════════════════════════════════════════════════════════════════════════
# Status Report / 狀態報告
# ═══════════════════════════════════════════════════════════════════════════════


def get_watchdog_status(data_dir: str, stale_threshold: float = STALE_THRESHOLD_SECONDS) -> dict:
    """
    Get a one-shot status check (for API endpoint integration).
    3E-5: checks per-engine snapshots + compat primary.
    engine_alive is true if any compat or per-engine snapshot is fresh.
    獲取一次性狀態檢查（含每引擎快照）。
    任一兼容或每引擎快照新鮮即視為 engine_alive。
    """
    data_path = Path(data_dir)
    # Primary (compat) snapshot / 主（兼容）快照
    primary_path = data_path / "pipeline_snapshot.json"
    is_fresh, age = check_snapshot_freshness(primary_path, stale_threshold)

    # Per-engine snapshots (3E-5) / 每引擎快照
    engines: dict[str, dict] = {}
    per_engine_ages: dict[str, float | None] = {}
    any_engine_fresh = is_fresh
    for eng in ("paper", "demo", "live"):
        eng_path = data_path / f"pipeline_snapshot_{eng}.json"
        eng_fresh, eng_age = check_snapshot_freshness(eng_path, stale_threshold)
        if eng_age != float("inf"):
            engines[eng] = {
                "alive": eng_fresh,
                "age_seconds": round(eng_age, 1),
            }
            per_engine_ages[f"{eng}_age_seconds"] = round(eng_age, 1)
            any_engine_fresh = any_engine_fresh or eng_fresh
        else:
            engines[eng] = {"alive": False, "status": "not_running"}
            per_engine_ages[f"{eng}_age_seconds"] = None

    result = {
        "engine_alive": any_engine_fresh,
        "snapshot_age_seconds": round(age, 1) if age != float("inf") else None,
        "snapshot_path": str(primary_path),
        "stale_threshold_seconds": stale_threshold,
        "engines": engines,
    }
    result.update(per_engine_ages)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / 命令行接口
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Engine Watchdog — monitor Rust engine health")
    parser.add_argument("--data-dir", default=os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"),
                        help="Data directory with pipeline_snapshot.json")
    parser.add_argument("--stale-threshold", type=float, default=STALE_THRESHOLD_SECONDS,
                        help="Staleness threshold in seconds")
    parser.add_argument("--poll-interval", type=float, default=POLL_INTERVAL_SECONDS,
                        help="Poll interval in seconds")
    # Startup grace period — stale snapshots during this window won't count as strikes
    # 啟動寬限期 — 在此窗口內的過期快照不計入 strike
    parser.add_argument("--grace-period", type=float, default=GRACE_PERIOD_SECONDS,
                        help="Startup grace period in seconds (stale snapshots ignored during this window)")
    parser.add_argument("--status", action="store_true",
                        help="Print one-shot status and exit")
    # P0-ENGINE-HALTSESSION-STUCK-FIX Layer B (2026-05-19): inert probe control.
    # 為什麼預設 enabled：spec §4 deploy gate；可由 CLI disable 用於急救回滾。
    parser.add_argument("--disable-inert-probe", action="store_true",
                        help="Disable Layer B trading inert probe (spec §4) / 關閉 Layer B 業務心跳探測")
    parser.add_argument("--inert-probe-config", default=None,
                        help="Override inert probe TOML path / 覆寫 inert probe 配置路徑")
    args = parser.parse_args()

    if args.status:
        status = get_watchdog_status(args.data_dir, args.stale_threshold)
        print(json.dumps(status, indent=2))
        sys.exit(0 if status["engine_alive"] else 1)

    # Fix 2 (2026-04-14): single-instance enforcement via fcntl.flock.
    # Two watchdogs racing to restart would double-kill and corrupt engine state.
    # 修復 2：透過 fcntl.flock 強制單例。兩個看門狗競相重啟會雙殺並污染引擎狀態。
    lock_path = Path(args.data_dir) / WATCHDOG_LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.critical(
            "Another watchdog already holds %s — exiting / 另一看門狗持有 %s — 退出",
            lock_path, lock_path,
        )
        sys.exit(3)
    lock_fd.write(f"{os.getpid()}\n")
    lock_fd.flush()

    # Handle SIGTERM/SIGINT gracefully / 優雅處理 SIGTERM/SIGINT
    def _shutdown(sig, frame):
        logger.info("Watchdog shutting down (signal %d) / 看門狗關閉（信號 %d）", sig, sig)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    inert_probe_config_path = (
        Path(args.inert_probe_config) if args.inert_probe_config else None
    )
    state = run_watchdog(
        data_dir=args.data_dir,
        stale_threshold=args.stale_threshold,
        poll_interval=args.poll_interval,
        grace_period=args.grace_period,
        inert_probe_enabled=not args.disable_inert_probe,
        inert_probe_config_path=inert_probe_config_path,
    )

    if state.rollback_triggered:
        logger.critical("Watchdog exiting — runtime rollback triggered / 看門狗退出 — 運行時回滾已觸發")
        sys.exit(2)


if __name__ == "__main__":
    main()
