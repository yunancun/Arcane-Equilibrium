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
import json
import logging
import os
import signal
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


@dataclass
class WatchdogState:
    """Internal state of the watchdog / 看門狗內部狀態"""
    engine_alive: bool = True
    crash_timestamps: list[float] = field(default_factory=list)
    total_crashes: int = 0
    last_recovery_ts: float = 0.0
    rollback_triggered: bool = False


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


def on_engine_crash(state: WatchdogState, snapshot_age: float) -> str:
    """
    Handle engine crash detection.
    處理引擎崩潰檢測。

    Returns: action taken ("fallback" | "rollback" | "none")
    """
    if not state.engine_alive:
        return "none"  # Already in crash state / 已在崩潰狀態

    state.engine_alive = False
    state.total_crashes += 1
    state.crash_timestamps.append(time.time())

    logger.error(
        "ENGINE_CRASH detected — snapshot age=%.1fs, total crashes=%d "
        "/ 檢測到引擎崩潰 — 快照年齡=%.1f秒，總崩潰數=%d",
        snapshot_age, state.total_crashes, snapshot_age, state.total_crashes,
    )

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
    snapshot_path = Path(data_dir) / "pipeline_snapshot.json"
    state = WatchdogState()
    iteration = 0
    # Record startup time for grace period calculation / 記錄啟動時間用於寬限期計算
    start_time = time.time()

    logger.info(
        "Watchdog started — monitoring %s (threshold=%.1fs, poll=%.1fs, grace=%.1fs) "
        "/ 看門狗啟動 — 監控 %s（閾值=%.1f秒，輪詢=%.1f秒，寬限期=%.1f秒）",
        snapshot_path, stale_threshold, poll_interval, grace_period,
        snapshot_path, stale_threshold, poll_interval, grace_period,
    )

    while True:
        if max_iterations is not None and iteration >= max_iterations:
            break

        is_fresh, age = check_snapshot_freshness(snapshot_path, stale_threshold)

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
                action = on_engine_crash(state, age)
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
    獲取一次性狀態檢查（用於 API 端點整合）。
    """
    snapshot_path = Path(data_dir) / "pipeline_snapshot.json"
    is_fresh, age = check_snapshot_freshness(snapshot_path, stale_threshold)
    return {
        "engine_alive": is_fresh,
        "snapshot_age_seconds": round(age, 1) if age != float("inf") else None,
        "snapshot_path": str(snapshot_path),
        "stale_threshold_seconds": stale_threshold,
    }


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
