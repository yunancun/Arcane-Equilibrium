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


def run_watchdog(
    data_dir: str,
    stale_threshold: float = STALE_THRESHOLD_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    max_iterations: Optional[int] = None,
    grace_period: float = GRACE_PERIOD_SECONDS,
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

    state = run_watchdog(
        data_dir=args.data_dir,
        stale_threshold=args.stale_threshold,
        poll_interval=args.poll_interval,
        grace_period=args.grace_period,
    )

    if state.rollback_triggered:
        logger.critical("Watchdog exiting — runtime rollback triggered / 看門狗退出 — 運行時回滾已觸發")
        sys.exit(2)


if __name__ == "__main__":
    main()
