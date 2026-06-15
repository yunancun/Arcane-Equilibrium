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
import hashlib
import hmac
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
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

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import（cwd 漂移防護）
import alert_sink  # 耐久 sink + 告警 redactor 正本（本檔 pre-existing 超 2000 行硬頂，只留薄調用）
import engine_dead_incident  # external engine_dead notify-only producer（薄接線）
import canary_audit_common  # audit_events direct fail-soft write 正本（薄調用；本檔超 2000 行硬頂）
import watchdog_liveness_crosscheck  # B1 破壞性重啟前 IPC 存活交叉檢查正本（薄調用；本檔超 2000 行硬頂）

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
# WATCHDOG-INERT-STORM-FIX-1 (2026-06-05): 重啟後沉降窗口（秒）。
# 為什麼需要：restart_all 退出 0（引擎進程已起）但引擎保持 INERT（快照永不刷新）時，
# 每次重啟都「成功」→ trigger_restart 清零 consecutive_failures + next_allowed_restart_ts=0
# （無退避）→ 下個 2s poll 快照仍 stale → 立即再重啟 → 風暴（2026-06-05 實測 6× RESTART_SUCCESS
# 重疊開機，退出碼熔斷因每次都「成功」永不觸發）。沉降窗口在每次 trigger_restart 後強制
# 間隔，讓 booting 引擎有時間寫出第一個快照，不被殺在開機途中。90s = 引擎開機 + 首個快照所需。
POST_RESTART_SETTLE_SECONDS = 90.0
# WATCHDOG-INERT-STORM-FIX-1 (2026-06-05): 無恢復（inert）熔斷上限。
# 為什麼獨立於 MAX_CONSECUTIVE_FAILURES：退出碼熔斷只在重啟「失敗」（exit≠0）時累計，
# 但 inert 風暴是重啟「成功」（exit=0）卻引擎不活，退出碼熔斷永不到 5。此計數在每次
# trigger_restart 都遞增（不論退出碼），達上限即熔斷並告警，把風暴在 ~3 次無恢復後止住
# （配 90s 沉降約 4.5 分鐘），而非永遠空轉。只在 on_engine_recovery（真恢復）歸零。
INERT_RESTART_LIMIT = 3
# Prolonged-down re-alert cadence (seconds). While the circuit stays broken,
# re-ping at most once per this window (key changes per window → dedup allows one).
# 持續宕機重發告警間隔（秒）。熔斷期間每個窗口最多重發一次（key 隨窗口變化）。
# 預設 4h；2026-06-05 incident 引擎 down ~20h 無人知，4h 重發可在長宕機時持續提醒。
RE_ALERT_INTERVAL_SECONDS = 14400.0
# Restart command — invoked via subprocess with timeout.
# 重啟命令 — 透過 subprocess 呼叫帶 timeout。
RESTART_COMMAND = ["bash", "helper_scripts/restart_all.sh", "--engine-only"]
RESTART_TIMEOUT_SECONDS = 120.0
# File paths (under OPENCLAW_DATA_DIR) / 檔案路徑（於 OPENCLAW_DATA_DIR 下）
MAINTENANCE_FLAG = "engine_maintenance.flag"
WATCHDOG_LOCK_FILE = "watchdog.lock"
WATCHDOG_STATE_FILE = "watchdog_state.json"
CANARY_EVENTS_FILE = "canary_events.jsonl"
# GUI-configurable alert credentials, shared with the FastAPI app's alert_config.py.
# GUI 可配置告警憑證檔，與 app 的 alert_config.py 共用同一 schema / key 名。
# watchdog 端內聯讀取（不 import app，維持零 app 依賴）。
ALERT_CONFIG_FILE = "alert_config.json"
# Alert HTTP timeout — stricter than the app's 10s; the watchdog must never stall.
# 告警 HTTP 超時 — 比 app 的 10s 更嚴；watchdog 絕不可被告警卡住。
ALERT_HTTP_TIMEOUT_SECONDS = 5.0
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
# 不分大小寫子字串；tail 連續 ≥N 條匹配判為 network_outage（不計 strike）。
NETWORK_OUTAGE_PATTERNS: tuple[str, ...] = (
    "temporary failure in name resolution",
    "failed to lookup address information",
    "http transport error",
    "connection refused",
    "dns error",
)
# 若 tail 任一行含以下子字串，強制回到 engine_crash（panic/assertion 一定是 bug）。
CRASH_INDICATOR_PATTERNS: tuple[str, ...] = (
    "panic",
    "assertion failed",
    "stack backtrace",
)

# ═══════════════════════════════════════════════════════════════════════════════
# WATCHDOG-NETOUTAGE-CLASSIFIER-FIX (2026-05-21): interleaved + cross-rotation
# evidence support — rotated 或 interleaved log 場景下也能正確判 net-outage。
#
# 背景：DNS-CLASSIFY-1 只支援「單檔內連續 ≥5 條 network-error」。實務中
#   (1) interleaved：DNS error 中間夾雜 heartbeat/metric/lifecycle 行 → 連續 run 斷
#   (2) cross-rotation：DNS error 散落跨 active engine.log + 多份 rotated 死檔
# 兩種情境都會被誤判 engine_crash → 三振計數 → restart storm（與 v55 #5 同類更廣）。
#
# 強化策略（保守，仍以 engine_crash 為 fail-closed default）：
#   - 保留 (b) 單檔連續 ≥5 fast-path（與舊行為向後相容）
#   - 新增 (c) 單檔 interleaved：tail 內總 match 數 ≥ MIN_INTERLEAVED **且**
#     match/total 比例 ≥ MIN_RATIO **且** 無 ambiguous-source line
#   - 新增 (d) cross-rotation aggregate：把 active + recent rotated 各 file 的
#     tail 合併後重評 (c)；解決證據跨檔散落
#
# False positive guard：若任何 candidate tail 含 ambiguous-source line
#   (PG / disk / OOM / engine-side bug 跡象) → 降級回 engine_crash，
#   防止把純 PG 故障或 disk-full 誤標為 network_outage。
# ═══════════════════════════════════════════════════════════════════════════════

# Interleaved gate：tail 內 network-error 行的最低總數（不要求連續）。
# 5/20 = 25% 比例已遠超隨機噪音水平；同時要求 (c-2) ratio gate 進一步壓抑誤報。
NETWORK_OUTAGE_MIN_INTERLEAVED = 5
# Interleaved gate：tail 中 network-match 行佔比下限（25%）。
# 為什麼 0.25：DNS-CLASSIFY-1 原連續 ≥5/20 (25%) 設定為設計基準；保持等價門檻避免
# 放寬靈敏度。若 tail 不滿 20 行（log 剛 rotated 或剛啟動），按實際讀到行數算分母。
#
# 已知盲區（MEDIUM-1 R2 注釋；OQ-NETOUTAGE-2 留 PM 後續決定）：
#   ratio gate 假設 tail 20 行涵蓋幾分鐘範圍（每秒幾行的引擎輸出速率下成立）。
#   在 engine idle / paused / heavily throttled 階段 log 寫入速率可低於每分鐘 1 行，
#   tail 可能跨越數小時。此時 5/20=25% ratio 命中可能反映「過去數小時內偶發 DNS
#   error」而非真實當下持續 outage。
#   - 風險場景：稀疏 log（如 5 條 DNS error 散落在 4 小時內 + 15 條 heartbeat）
#     會被誤判 network_outage，跳過 strike 計數 + auto-restart。
#   - 緩解假設：production engine 正常情況下 tail 20 行通常 ≤5min；engine paused
#     時 watchdog 通常已被 Layer B inert-probe 或 freshness check 攔截。
#   - 上游既有時間窗保護：`NETWORK_OUTAGE_RECENT_SECONDS = 15min` mtime filter 已
#     在 `_candidate_failure_log_paths` 過濾掉 >15min 未更新的 rotated log（檔案
#     級別時間窗）；但 active engine.log 本身只要 mtime 在 15min 內就會被掃，
#     不保證 tail 內所有行都在 15min 內。
#   - OQ-NETOUTAGE-2（待 PM 決定）：未來是否補 5min rolling timestamp window
#     gate（解析 Rust tracing RFC3339 timestamp，限制只看 5min 內的行）。
#     trade-off：增加 timestamp parsing brittle 風險 vs 消除 sparse-log 盲區。
NETWORK_OUTAGE_MIN_RATIO = 0.25
# Cross-rotation aggregate gate：active + rotated 各 tail 合併後總行數上限與 match 下限。
# MIN_INTERLEAVED 相同數值（5 行）但分母可達 N_FILES × TAIL_LINES（最壞 6 × 20 = 120）。
NETWORK_OUTAGE_AGGREGATE_MIN_MATCHES = 5
NETWORK_OUTAGE_AGGREGATE_MIN_RATIO = 0.10

# Ambiguous-source patterns：tail 出現以下 token 時 evidence 模糊（可能 PG/disk/OOM
# 而非單純 DNS/HTTP），保守降級回 engine_crash。為什麼這些 token：
#   - "postgres" / "sqlx" / "pgconnection"：sqlx 層失敗也會吐 "connection
#     refused" / "connection error" 字樣與 NETWORK_OUTAGE_PATTERNS 衝突
#   - "pg pool" / "pool timed out" / "db_pool"：openclaw_engine::database::pool
#     層的真實 production 失敗格式（HIGH-1 R2 補；E2 R1 用 production engine.log
#     第 4 行 reproduce false-positive）；prefix 涵蓋：
#       * "PG pool connect failed — DB writes disabled / 連接失敗"
#       * "PG pool unavailable / 連接池不可用"
#       * "db_pool unavailable, BudgetTracker not started"
#       * "error=pool timed out while waiting for an open connection"（sqlx 內部錯誤訊息）
#   - "disk full" / "no space left"：disk 故障 ≠ network outage
#   - "out of memory" / "killed (oom)"：OOM ≠ network outage
#   - "watchdog timeout" / "deadlock"：engine 內部死鎖 ≠ network outage
# 命中任一 token，本次 classification 直接回 engine_crash（保守原則）。
#
# 維護規範（HIGH-1 R2 教訓）：token list 必須對照 production engine.log empirical
# 取樣（`grep -i 'pool\|memory\|disk\|panic\|db_' <OPENCLAW_DATA_DIR>/engine.log`），
# 不可純推測。新增前先 grep 驗證真實字樣，避免遺漏實際格式。Mac dev 路徑通常為
# `~/.openclaw_runtime/`；Linux runtime 路徑依 `OPENCLAW_DATA_DIR` env / restart_all.sh。
AMBIGUOUS_SOURCE_PATTERNS: tuple[str, ...] = (
    "postgres",
    "pgconnection",
    "sqlx",
    "pg pool",
    "pool timed out",
    "db_pool",
    "disk full",
    "no space left",
    "out of memory",
    "killed (oom)",
    "watchdog timeout",
    "deadlock detected",
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
    # B1 liveness cross-check (2026-06-15): snapshot stale 但 IPC 證明引擎仍活時，
    # 抑制破壞性重啟的計數狀態。max-hold 上限以此計數封頂（避免無限期抑制）。
    # liveness_suppress_cycles：連續抑制的週期數（每 stale-but-alive poll +1，恢復歸零）。
    # liveness_first_suppress_ts：首次抑制的時間戳（None=尚未抑制；恢復歸零），供 wall-clock 上限。
    liveness_suppress_cycles: int = 0
    liveness_first_suppress_ts: Optional[float] = None


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


def _count_network_matches(lower_lines: list[str]) -> int:
    """計算 tail 中匹配 NETWORK_OUTAGE_PATTERNS 的行數（不要求連續）。

    為什麼抽出來：(c) interleaved 單檔評估與 (d) cross-rotation aggregate 共用同一
    計數邏輯；helper 抽出避免雙重維護。
    """
    return sum(
        1
        for line in lower_lines
        if any(pat in line for pat in NETWORK_OUTAGE_PATTERNS)
    )


def _longest_consecutive_network_run(lower_lines: list[str]) -> int:
    """計算 tail 中連續 network-outage 行的最長 run（fast-path 用）。"""
    longest_run = 0
    current_run = 0
    for line in lower_lines:
        if any(pat in line for pat in NETWORK_OUTAGE_PATTERNS):
            current_run += 1
            if current_run > longest_run:
                longest_run = current_run
        else:
            current_run = 0
    return longest_run


def _has_ambiguous_source(lower_lines: list[str]) -> bool:
    """檢查 tail 是否含 PG/disk/OOM 等模糊來源 token。

    命中即視為 ambiguous evidence → 上游分類器降級回 engine_crash。
    保守原則：寧可漏報 net-outage（多計 strike），不可錯把 PG/disk 故障標為
    network_outage 而跳過 strike 計數導致真正 bug 被吞掉。
    """
    return any(
        any(pat in line for pat in AMBIGUOUS_SOURCE_PATTERNS)
        for line in lower_lines
    )


def classify_engine_failure(
    log_path: Path,
    tail_lines: int = ENGINE_LOG_TAIL_LINES,
    min_consecutive: int = NETWORK_OUTAGE_MIN_CONSECUTIVE,
    min_interleaved: int = NETWORK_OUTAGE_MIN_INTERLEAVED,
    min_ratio: float = NETWORK_OUTAGE_MIN_RATIO,
) -> str:
    """檢查 active engine.log 與最近輪替日誌，分類引擎故障。

    為什麼分四層 gate（按優先序）：
      (a) crash-indicator override：tail 含 panic/assertion/stack-backtrace →
          一定是 engine bug，即使同時有 DNS 風暴也判 engine_crash。panic 必須
          算 strike。
      (b) per-file consecutive run ≥ min_consecutive：DNS-CLASSIFY-1 原 fast-path，
          保持向後兼容。
      (c) per-file interleaved：tail 內 match 數 ≥ min_interleaved 且 match/total
          比例 ≥ min_ratio。處理 DNS error 中間夾雜 heartbeat/metric 的散落情境。
      (d) cross-rotation aggregate：active + rotated 各 file 的 tail 合併後重評
          (c)。處理證據跨檔散落的 rotation 情境（v55 #5 watchdog RCA 同類更廣）。

    False positive guard：任何 candidate tail 含 AMBIGUOUS_SOURCE_PATTERNS（PG /
    disk / OOM / 死鎖）→ **整體** 降級回 engine_crash（保守原則）。寧可漏報 net-
    outage 多計 strike，也不可錯把 PG/disk 失敗標為 network_outage 跳過 strike。

    Returns:
      "network_outage"  通過 gate (b)/(c)/(d) 任一且無 (a)/ambiguous 命中。
      "engine_crash"    其餘所有情況（含 I/O error、空 log、ambiguous evidence）。
    """
    saw_readable_tail = False
    saw_per_file_outage = False
    saw_ambiguous = False
    aggregate_lower: list[str] = []
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
        aggregate_lower.extend(lower)

        # (a) crash-indicator override — panic/assertion 即時 short-circuit
        for line in lower:
            if any(pat in line for pat in CRASH_INDICATOR_PATTERNS):
                return "engine_crash"

        # False positive guard：ambiguous source 命中暫存，等掃完所有 candidate
        # 後再決定（不在這裡 short-circuit；後面 aggregate gate 也要受此抑制）。
        if _has_ambiguous_source(lower):
            saw_ambiguous = True

        # (b) 單檔連續 run（fast-path，向後兼容 DNS-CLASSIFY-1）
        if _longest_consecutive_network_run(lower) >= min_consecutive:
            saw_per_file_outage = True
            continue

        # (c) 單檔 interleaved：總 match 數 ≥ MIN_INTERLEAVED **且** 比例達標
        match_count = _count_network_matches(lower)
        if (
            match_count >= min_interleaved
            and len(lower) > 0
            and (match_count / len(lower)) >= min_ratio
        ):
            saw_per_file_outage = True

    # Ambiguous evidence 整體降級 — 保守原則優先於 net-outage 強化
    if saw_ambiguous:
        return "engine_crash"

    if saw_per_file_outage:
        return "network_outage"

    # (d) cross-rotation aggregate：active + rotated 合併後重評 interleaved
    # 為什麼用較寬鬆 ratio（0.10 vs 0.25）：cross-file 場景的分母被 unrelated
    # rotation lines 拉大屬正常；MIN_MATCHES 絕對下限維持 5 提供噪音底線。
    # MEDIUM-2 R2：抽 agg_matches 變數，避免重複呼叫 `_count_network_matches`。
    if len(aggregate_lower) > 0:
        agg_matches = _count_network_matches(aggregate_lower)
        if (
            agg_matches >= NETWORK_OUTAGE_AGGREGATE_MIN_MATCHES
            and (agg_matches / len(aggregate_lower))
            >= NETWORK_OUTAGE_AGGREGATE_MIN_RATIO
        ):
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


def _emit_audit_event_best_effort(
    canary_event: str,
    detection_ts: float,
    summary: str,
    details: dict,
    notes: str,
) -> None:
    """ENGINE-AUDIT-VISIBILITY (2026-06-15)：direct fail-soft write 一行 audit_events。

    為什麼薄包一層：watchdog 偵測到的 ENGINE_CRASH / NETWORK_OUTAGE / ENGINE_RECOVERED
    要讓 operator 在 PG `audit_events` 查得到（表存在但 0 row）。本函數把 canary 事件名
    映射成 (event_type, severity)、嵌確定性 dedup_key（與 bridge 共用同形）、補 hostname，
    再走 canary_audit_common.write_audit_event_best_effort（自開連線 5s timeout + 冪等
    INSERT + 全程吞沒例外）。

    硬邊界：絕不在重啟「之前」呼叫——恢復是第一要務，DB 寫入不得延遲重啟；任何 DB 問題
    都被 common 層吞沒，不會拋進偵測/重啟/分類邏輯。
    """
    try:
        mapped = canary_audit_common.map_canary_to_audit(canary_event)
        if mapped is None:
            return
        event_type, severity = mapped
        dedup_key = canary_audit_common.build_dedup_key(event_type, detection_ts)
        full_details = dict(details)
        full_details.setdefault("hostname", canary_audit_common.hostname())
        row = canary_audit_common.build_audit_row(
            event_type=event_type,
            severity=severity,
            summary=summary,
            event_details=full_details,
            notes=notes,
            dedup_key=dedup_key,
        )
        canary_audit_common.write_audit_event_best_effort(row)
    except Exception as exc:  # noqa: BLE001 — 任何組裝/寫入錯誤都不得拋進 watchdog 偵測/重啟邏輯
        logger.warning(
            "audit emit best-effort failed (non-fatal): %s / audit 事件寫入失敗（吞沒）",
            exc,
        )


def _emit_snapshot_stall_engine_alive(
    data_dir: str,
    detection_ts: float,
    snapshot_age: float,
    probe_reason: str,
    hold_cycles: int,
    hold_seconds: float,
) -> None:
    """B1（2026-06-15）：snapshot 過期但 IPC 交叉檢查證明引擎仍活、已抑制破壞性重啟。

    為什麼是獨立事件而非沿用 ENGINE_CRASH：這「不是」crash——引擎活著（仍 serve IPC、
    處理 tick），只是 snapshot-writer task 停寫快照。沿用 ENGINE_CRASH 會污染 crash 計數 /
    三振 / 21d 穩定時鐘並誤導 operator。本事件三路落地（canary + alert + audit_events），
    讓 operator 知道「watchdog 擋掉了一次會平倉的誤殺重啟」且 snapshot-writer 退化中。

    硬邊界：全程 best-effort fail-soft，任何寫入問題都不得拋進偵測/重啟邏輯。canary 帶
    確定性 dedup_key（與 audit direct write 同形），供 backstop bridge 補洞。
    """
    try:
        dedup_key = canary_audit_common.build_dedup_key(
            "snapshot_stall_engine_alive", detection_ts
        )
        _append_canary_event(data_dir, {
            "ts": detection_ts,
            "event": "SNAPSHOT_STALL_ENGINE_ALIVE",
            "snapshot_age_seconds": snapshot_age,
            "probe_reason": probe_reason,
            "hold_cycles": hold_cycles,
            "hold_seconds": round(hold_seconds, 1),
            "dedup_key": dedup_key,
        })
        subject = "OpenClaw snapshot STALLED but engine ALIVE — destructive restart suppressed"
        body = (
            "engine: rust openclaw_engine\n"
            f"snapshot stale: {snapshot_age:.1f}s (writer task stalled)\n"
            f"ipc cross-check: ALIVE ({probe_reason})\n"
            f"action taken: SIGTERM/market-close SUPPRESSED (hold cycle {hold_cycles})\n"
            "note: engine still serving IPC + processing ticks; only snapshot-writer "
            "stalled. A1/A2 track fixes the stall itself.\n"
            "action: ssh trade-core; check engine.log snapshot-writer task; no manual "
            "restart needed unless this persists"
        )
        # severity=WARNING：避免誤殺的正向事件，非引擎故障；不可用 CRITICAL 淹沒真 down 告警。
        _send_alert_best_effort(subject, body, "WARNING", data_dir)
        _emit_audit_event_best_effort(
            "SNAPSHOT_STALL_ENGINE_ALIVE",
            detection_ts,
            f"snapshot stalled {snapshot_age:.1f}s but engine alive via IPC "
            f"({probe_reason}); destructive restart suppressed (hold cycle {hold_cycles})",
            {
                "snapshot_age_seconds": snapshot_age,
                "classification": "snapshot_stall_engine_alive",
                "probe_reason": probe_reason,
                "hold_cycles": hold_cycles,
                "hold_seconds": round(hold_seconds, 1),
            },
            "B1 liveness cross-check: IPC responsive; SIGTERM/market-close suppressed",
        )
    except Exception as exc:  # noqa: BLE001 — 任何組裝/寫入錯誤都不得拋進 watchdog 偵測/重啟邏輯
        logger.warning(
            "snapshot-stall-engine-alive emit failed (non-fatal): %s / 事件寫入失敗（吞沒）",
            exc,
        )


def emit_restart_skipped_if_new(
    data_dir: str, reason_key: str, reason_detail: str, now: float
) -> bool:
    """RESTART_SKIPPED canary 去重寫入（FINDING #2 2026-06-05 + HIGH-1 修正）。

    為什麼節流：on_engine_crash 的 retry 改 LEVEL-triggered 後，每次處於
    engine_crash 狀態的 stale poll（POLL_INTERVAL=2s）只要 should_restart 回 False
    就會想寫一條 RESTART_SKIPPED。一旦 circuit_broken=True（終態，可持續數小時，
    參 2026-06-05 incident 引擎 down ~20h），等於每天約 4.3 萬條 RESTART_SKIPPED
    灌進 canary_events.jsonl，把我們真正要看的那一條 RESTART_CIRCUIT_BROKEN 淹沒
    （該檔無 rotation，是未來告警要保持乾淨的訊號源）。

    HIGH-1 去重必須用 reason_KEY 而非人類字串：should_restart 的 backoff 分支
    detail 內含 per-poll 遞減的倒數秒（"300s remaining"→"298s…"），每 poll 都不同，
    若用 detail 去重則整段 backoff window 每 poll 都寫一條（實測 300s 灌 150 條、
    熔斷前約 540 條），等於對正常爬升到熔斷的路徑完全失去節流。改用穩定的 key
    去重：同一狀態整段窗口只發 ≤1 條；key 變化（backoff→circuit_broken→maintenance）
    才再發一條。marker 持久化在 watchdog_state.json 的 last_restart_skipped_reason
    （存的是 KEY），跨 poll 比對。成功重啟 / 引擎恢復時由 clear_restart_skipped_marker
    清掉，讓之後真正的 skip 能再發一次（避免吞掉新事件）。

    注意：reason_detail 仍寫進 canary event payload（保留人類可讀資訊），per-poll
    的 logger.warning 也由 caller 用 detail 輸出（log 會 rotate，本地可見性無虞）。
    本函數只節流 JSONL append；RESTART_FAILED（天然 1/backoff-window）與
    RESTART_CIRCUIT_BROKEN（one-shot）不在此節流，照舊由 trigger_restart 寫。

    Args:
        reason_key: should_restart 回的穩定分類鍵，去重判定唯一依據。
        reason_detail: 人類可讀字串，寫進 event payload（不參與去重）。

    Returns:
        True  本次有寫 JSONL（key 為新）；False 去重 skip。
    """
    state = load_state(data_dir)
    last_key = state.get("last_restart_skipped_reason")
    if last_key == reason_key:
        return False
    state["last_restart_skipped_reason"] = reason_key
    state["last_restart_skipped_emit_ts"] = now
    save_state(data_dir, state)
    _append_canary_event(data_dir, {
        "ts": now, "event": "RESTART_SKIPPED",
        "reason_key": reason_key, "reason": reason_detail,
    })
    return True


def clear_restart_skipped_marker(data_dir: str) -> None:
    """清掉 RESTART_SKIPPED 去重 marker（FINDING #2 2026-06-05）。

    為什麼要清：成功重啟或引擎恢復後，下一輪若再進入 skip 狀態應重新發一條
    RESTART_SKIPPED（而非因 marker 殘留被永久去重吞掉）。在 trigger_restart 成功
    分支與 on_engine_recovery 呼叫，標誌一個 skip-emit 週期的結束。
    只在 marker 實際存在時才寫盤，避免無謂 I/O。
    """
    state = load_state(data_dir)
    if state.get("last_restart_skipped_reason") is None and \
            "last_restart_skipped_emit_ts" not in state:
        return
    state.pop("last_restart_skipped_reason", None)
    state.pop("last_restart_skipped_emit_ts", None)
    save_state(data_dir, state)


# ═══════════════════════════════════════════════════════════════════════════════
# WATCHDOG-ALERT-WIRE (2026-06-05): engine-down 非靜默告警
# 為什麼在 watchdog 內聯（而非 import app alerter）：watchdog 是恢復元件，必須維持
# 零 app 依賴（不得把 FastAPI / sqlx / governance 拉進恢復迴圈）。憑證來源與 app 的
# alert_config.py 完全共用 —— 讀同一個 <data_dir>/alert_config.json（file-primary，
# env-fallback），故 schema / key 名單一來源。此處只內聯 ~15 行讀取拷貝 + stdlib
# urllib 送出，不依賴 app 套件。
# 失敗隔離（load-bearing）：所有送出皆 daemon thread fire-and-forget + 5s timeout +
# catch-all；告警呼叫一律在 restart/recovery 邏輯「之後」，絕不在重啟關鍵路徑上。
# 監控迴圈的正確性不依賴任何告警成功。
# ═══════════════════════════════════════════════════════════════════════════════

# 一次性「無通道」警告旗標 —— 未配置時只 warn 一次，避免每次 poll 灌 log。
_alert_unconfigured_warned = False


def _load_alert_creds(data_dir: str) -> dict:
    """讀 alert_config.json 的告警憑證（file-primary，env-fallback；best-effort，永不拋）。

    這是 app alert_config.load_alert_config 的內聯精簡拷貝（只讀，不含 save/validate/mask），
    維持 watchdog 零 app 依賴。壞檔 / 缺檔回安全空殼後套 env-fallback。
    回傳 {"telegram":{enabled,bot_token,chat_id}, "webhook":{enabled,urls,secret}}。
    """
    cfg = {
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "webhook": {"enabled": False, "urls": [], "secret": ""},
    }
    raw = None
    try:
        with open(Path(data_dir) / ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        raw = None
    except Exception:  # noqa: BLE001 - 憑證讀取必須 fail-safe
        raw = None

    if isinstance(raw, dict):
        tg = raw.get("telegram")
        if isinstance(tg, dict):
            cfg["telegram"]["bot_token"] = tg.get("bot_token", "") if isinstance(tg.get("bot_token"), str) else ""
            cfg["telegram"]["chat_id"] = tg.get("chat_id", "") if isinstance(tg.get("chat_id"), str) else ""
            cfg["telegram"]["enabled"] = bool(tg.get("enabled", False))
        wh = raw.get("webhook")
        if isinstance(wh, dict):
            urls_raw = wh.get("urls")
            urls = [u.strip() for u in urls_raw if isinstance(u, str) and u.strip()] if isinstance(urls_raw, list) else []
            cfg["webhook"]["urls"] = urls
            cfg["webhook"]["secret"] = wh.get("secret", "") if isinstance(wh.get("secret"), str) else ""
            cfg["webhook"]["enabled"] = bool(wh.get("enabled", False))

    # env-fallback（back-compat）：檔內憑證為空時，從既有 env 變量補。
    if not cfg["telegram"]["bot_token"] and not cfg["telegram"]["chat_id"]:
        env_token = os.getenv("OPENCLAW_TELEGRAM_BOT_TOKEN", "").strip()
        env_chat = os.getenv("OPENCLAW_TELEGRAM_CHAT_ID", "").strip()
        # LOW-1 (E2 2026-06-05) 對齊 app alert_config._apply_env_fallback：閘用 OR
        # （任一非空就吸收），enabled 由「雙非空」推導。今日兩寫法等價（只 token 或只
        # chat 時 tg_active 仍 False = 不送），但對齊可消除 drift，避免日後語義分叉。
        if env_token or env_chat:
            cfg["telegram"] = {
                "enabled": bool(env_token and env_chat),
                "bot_token": env_token,
                "chat_id": env_chat,
            }
    if not cfg["webhook"]["urls"]:
        env_urls = [u.strip() for u in os.getenv("OPENCLAW_WEBHOOK_URLS", "").split(",") if u.strip()]
        if env_urls:
            cfg["webhook"] = {
                "enabled": True, "urls": env_urls,
                "secret": os.getenv("OPENCLAW_WEBHOOK_SECRET", "").strip(),
            }
    return cfg


def _post_telegram_alert(token: str, chat_id: str, text: str) -> None:
    """stdlib urllib 送一則 Telegram 訊息；catch-all，永不拋（在 daemon thread 內呼叫）。"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=ALERT_HTTP_TIMEOUT_SECONDS):
            pass
    except Exception as exc:  # noqa: BLE001 - 告警失敗不得影響 watchdog
        logger.debug("Telegram alert send failed (non-fatal): %s", exc)


def _post_webhook_alert(urls: list, secret: str, body_obj: dict) -> None:
    """stdlib urllib 送 webhook（多端點扇出）；HMAC-SHA256 簽名（鏡像 webhook_alerter._sign）。

    catch-all per-URL，永不拋（在 daemon thread 內呼叫）。
    """
    try:
        body = json.dumps(body_obj, default=str).encode("utf-8")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if secret else ""
        for url in urls:
            try:
                headers = {"Content-Type": "application/json"}
                if signature:
                    headers["X-OpenClaw-Signature"] = signature
                req = urllib.request.Request(url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=ALERT_HTTP_TIMEOUT_SECONDS):
                    pass
            except Exception as exc:  # noqa: BLE001
                logger.debug("Webhook alert send failed (non-fatal): %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Webhook alert build failed (non-fatal): %s", exc)


def _send_alert_best_effort(subject: str, body: str, severity: str, data_dir: str = "") -> None:
    """best-effort 發告警：file/env 讀憑證，daemon thread fire-and-forget，5s timeout，catch-all。

    為什麼 fire-and-forget + 永不拋：告警必須與 watchdog 恢復迴圈完全解耦 —— 任何
    掛起 / 失敗 / 缺端點都不得拖住 poll 或阻塞重啟。憑證只讀進記憶體，絕不寫進
    canary_events.jsonl / log / payload（log 通道名，不 log token）。
    WATCHDOG-ALERT-SINK（正本 alert_sink.py）：先 redact（E3 MED-1）再於遠端通道前無條件落耐久 sink。
    消費者註記：incident_sentinel.py（P2p 哨兵）sibling-import 本函數發告警——改簽名須同步該檔與其簽名 smoke 測試。
    """
    global _alert_unconfigured_warned
    resolved_dir = data_dir or os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    try:
        creds = _load_alert_creds(resolved_dir)
    except Exception as exc:  # noqa: BLE001 - 憑證讀取必須 fail-safe
        logger.debug("alert creds load failed (non-fatal): %s", exc)
        alert_sink.redact_and_sink(resolved_dir, subject, body, severity, [])  # 耐久線無條件成立
        return

    tg = creds["telegram"]
    wh = creds["webhook"]
    tg_active = bool(tg["enabled"]) and bool(tg["bot_token"]) and bool(tg["chat_id"])
    wh_active = bool(wh["enabled"]) and len(wh["urls"]) > 0

    subject, body, sink_ok = alert_sink.redact_and_sink(  # E3 MED-1 唯一脫敏入口：遠送/log 必用回傳文本
        resolved_dir, subject, body, severity,
        [c for c, on in (("telegram", tg_active), ("webhook", wh_active)) if on])

    if not tg_active and not wh_active:
        if not _alert_unconfigured_warned:
            logger.warning(
                "Alert channels unconfigured — engine-down alerts disabled "
                "/ 告警通道未配置 — engine-down 告警停用",
            )
            _alert_unconfigured_warned = True
        logger.log(logging.INFO if sink_ok else logging.WARNING,  # W-2 觀測面據實：失敗不謊稱 recorded
                   "alert recorded to local sink only (channels unconfigured): %s" if sink_ok else
                   "alert LOST: sink write failed and no channels configured: %s", subject)
        return

    text = f"[{severity}] {subject}\n{body}"
    if tg_active:
        threading.Thread(
            target=_post_telegram_alert,
            args=(tg["bot_token"], tg["chat_id"], text),
            daemon=True,
        ).start()
    if wh_active:
        body_obj = {
            "type": "system", "event": subject, "severity": severity,
            "detail": body, "timestamp_ms": int(time.time() * 1000),
        }
        threading.Thread(
            target=_post_webhook_alert,
            args=(list(wh["urls"]), wh["secret"], body_obj),
            daemon=True,
        ).start()


def emit_engine_down_alert_if_new(
    data_dir: str, alert_key: str, subject: str, body: str, now: float
) -> bool:
    """engine-down 告警去重發送（鏡像 emit_restart_skipped_if_new 語義）。

    比對穩定的 alert_key 與持久化的 last_engine_down_alert_key（存於 watchdog_state.json）；
    key 不變則去重 return False（同一狀態整段窗口只發 ≤1 條）。新 key 時：寫 marker +
    last_engine_down_alert_ts，記錄 engine_down_since_ts（首次 down-alert 才記，供算宕機時長），
    透過 _send_alert_best_effort 送出，並 append ENGINE_DOWN_ALERT_SENT canary 供稽核。

    為什麼用 key 去重而非時間：circuit_broken 終態可持續數小時（2026-06-05 down ~20h），
    若每 poll 都發等於灌爆告警通道；prolonged-down 的 key 隨窗口變化，故每窗口仍能恰好
    重發一次（neither spam nor miss）。

    Returns:
        True 本次有送（key 為新）；False 去重 skip。
    """
    state = load_state(data_dir)
    if state.get("last_engine_down_alert_key") == alert_key:
        return False
    state["last_engine_down_alert_key"] = alert_key
    state["last_engine_down_alert_ts"] = now
    # 首次 down-alert 記下 down-since，供 payload 與恢復訊息算宕機時長；已有則不覆蓋。
    if "engine_down_since_ts" not in state:
        state["engine_down_since_ts"] = now
    save_state(data_dir, state)
    _send_alert_best_effort(subject, body, "CRITICAL", data_dir)
    _append_canary_event(data_dir, {
        "ts": now, "event": "ENGINE_DOWN_ALERT_SENT", "alert_key": alert_key,
    })
    return True


def clear_engine_down_alert_marker(data_dir: str) -> None:
    """清掉 engine-down 告警去重 marker（鏡像 clear_restart_skipped_marker）。

    為什麼要清：引擎恢復後，未來再次 down-transition 應能重新發告警（而非被殘留 marker
    永久去重吞掉）。只在 marker 實際存在時寫盤，避免無謂 I/O。同時清 engine_down_since_ts。
    """
    state = load_state(data_dir)
    if (
        state.get("last_engine_down_alert_key") is None
        and "last_engine_down_alert_ts" not in state
        and "engine_down_since_ts" not in state
    ):
        return
    state.pop("last_engine_down_alert_key", None)
    state.pop("last_engine_down_alert_ts", None)
    state.pop("engine_down_since_ts", None)
    save_state(data_dir, state)


def _format_down_duration(seconds: float) -> str:
    """把秒數格式化成 "<H>h <M>m"（供 payload 人類可讀）。"""
    if seconds < 0:
        seconds = 0
    total_min = int(seconds // 60)
    return f"{total_min // 60}h {total_min % 60}m"


def _build_engine_down_payload(data_dir: str, now: float) -> tuple[str, str]:
    """從 watchdog_state.json 既有欄位組裝 engine-down 告警 payload（subject, body）。

    不讀任何憑證 / 硬邊界；只用 consecutive_failures / last_failure_reason / down-since。
    """
    state = load_state(data_dir)
    consecutive = state.get("consecutive_failures", 0)
    last_reason = state.get("last_failure_reason", "") or "unknown"
    down_since = state.get("engine_down_since_ts", now)
    duration = _format_down_duration(now - down_since)
    subject = "OpenClaw engine DOWN — manual intervention required"
    body = (
        "engine: rust openclaw_engine\n"
        f"down for: {duration}\n"
        f"auto-restart: circuit broken after {consecutive} consecutive failures\n"
        f"last failure: {last_reason}\n"
        "action: ssh trade-core; check engine.log; manual restart_all"
    )
    return subject, body


def _build_inert_down_payload(
    data_dir: str, restarts_since_recovery: int, now: float
) -> tuple[str, str]:
    """INERT 熔斷的 engine-down 告警 payload（subject, body）。

    與 _build_engine_down_payload 區隔：inert 風暴是「重啟一直成功(exit=0)但引擎從不變健康」，
    措辭強調「重啟 N 次卻從未恢復、自愈放棄、需人工介入」，與「連續 N 次重啟失敗」語義不同。
    不讀任何憑證 / 硬邊界；只用 restarts_since_recovery / last_failure_reason / down-since。
    """
    state = load_state(data_dir)
    last_reason = state.get("last_failure_reason", "") or "engine started but stayed inert"
    down_since = state.get("engine_down_since_ts", now)
    duration = _format_down_duration(now - down_since)
    subject = "OpenClaw engine INERT — manual intervention required"
    body = (
        "engine: rust openclaw_engine\n"
        f"down for: {duration}\n"
        f"engine restarted {restarts_since_recovery} times but never became healthy "
        "— auto-recovery gave up, manual intervention required\n"
        f"last failure: {last_reason}\n"
        "action: ssh trade-core; check engine.log; verify snapshot freshness; manual restart_all"
    )
    return subject, body


def _emit_inert_circuit_broken(
    data_dir: str, restarts_since_recovery: int, now: float
) -> None:
    """INERT 熔斷的 canary + engine-down 告警（WATCHDOG-INERT-STORM-FIX-1 2026-06-05）。

    為什麼獨立於 RESTART_CIRCUIT_BROKEN：inert 熔斷的觸發維度不同（重啟成功但引擎不活，
    非連續重啟失敗），canary event 名 INERT_CIRCUIT_BROKEN 區隔，供告警消費者分辨成因。
    告警走既有 B 路徑 emit_engine_down_alert_if_new，key="inert_circuit_broken"（與 exit-code
    熔斷的 "circuit_broken" key 不同，故兩者各自去重、互不淹沒）。呼叫端須先 save_state 落盤
    （payload 內 load_state 讀 last_failure_reason / down-since）。
    """
    last_reason = load_state(data_dir).get("last_failure_reason", "") or "inert"
    logger.critical(
        "INERT CIRCUIT BROKEN — engine restarted %d times but never became healthy, "
        "auto-recovery gave up / INERT 熔斷 — 重啟 %d 次引擎仍未健康，自愈放棄，需人工介入",
        restarts_since_recovery, restarts_since_recovery,
    )
    _append_canary_event(data_dir, {
        "ts": now, "event": "INERT_CIRCUIT_BROKEN",
        "restarts_since_recovery": restarts_since_recovery,
        "last_failure_reason": last_reason,
    })
    subject, body = _build_inert_down_payload(data_dir, restarts_since_recovery, now)
    emit_engine_down_alert_if_new(data_dir, "inert_circuit_broken", subject, body, now)


def should_restart(data_dir: str, now: float) -> tuple[bool, str, str]:
    """
    Decide whether an auto-restart is allowed right now.
    決定此刻是否允許自動重啟。

    回傳 (allowed, reason_key, reason_detail)：
      - reason_key 是 STABLE 分類鍵（"maintenance"/"circuit_broken"/"backoff"/"ok"），
        per-poll 不變，給 RESTART_SKIPPED 去重節流用（FINDING #2-HIGH-1 2026-06-05）。
      - reason_detail 是人類可讀字串，給 log + canary event payload 用。
    為什麼要拆 key/detail：backoff 分支的 detail 內含 per-poll 遞減的倒數秒
    （"300s remaining"→"298s remaining"…），每 2s poll 都產生不同字串。若節流
    去重用 detail，整個 backoff window 每 poll 都會寫一條 RESTART_SKIPPED
    （實測 300s 窗口灌 150 條），把 RESTART_CIRCUIT_BROKEN 訊號淹沒。改用 key
    去重後，同一狀態整段窗口只發 ≤1 條，狀態切換（backoff→circuit_broken）才再發。
    """
    # Safeguard #2: maintenance flag → operator intent wins / 維護旗標 → 尊重 operator 意圖
    flag_path = Path(data_dir) / MAINTENANCE_FLAG
    if flag_path.exists():
        return False, "maintenance", f"maintenance flag present at {flag_path}"

    state = load_state(data_dir)
    if state.get("circuit_broken", False):
        return False, "circuit_broken", (
            f"circuit broken after {state.get('consecutive_failures', 0)} consecutive failures "
            "— manual intervention required"
        )

    # WATCHDOG-INERT-STORM-FIX-1 (2026-06-05): 重啟後沉降窗口。
    # 為什麼放在 circuit_broken 之後、backoff 之前：circuit_broken 是終態必須優先回報；
    # 沉降是暫態間隔閘。inert 風暴的成功路徑下 backoff 被清成 0（無退避），沉降是此情境下
    # 唯一還在強制間隔的閘——若 now 仍在沉降窗口內，拒絕本次重啟，讓 booting 引擎能寫快照。
    settle_until = float(state.get("post_restart_settle_until", 0.0))
    if now < settle_until:
        remaining = settle_until - now
        # detail 保留 per-poll 倒數秒供 log/payload；節流由穩定的 "settle" key 去重。
        return False, "settle", f"post-restart settle, {remaining:.0f}s remaining"

    next_allowed = float(state.get("next_allowed_restart_ts", 0.0))
    if now < next_allowed:
        remaining = next_allowed - now
        # detail 保留 per-poll 倒數秒供 log/payload；節流由穩定的 "backoff" key 去重。
        return False, "backoff", f"backoff window active, {remaining:.0f}s remaining"

    return True, "ok", "ok"


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

    # WATCHDOG-INERT-STORM-FIX-1 (2026-06-05): 每次 trigger_restart（不論退出碼）都
    # 設沉降窗口 + 遞增 restarts_since_recovery。
    # 為什麼無條件：inert 風暴的成功路徑（exit=0）下，下面的成功分支會清 next_allowed_restart_ts=0
    # （無退避），若不在這裡設沉降，下個 2s poll 快照仍 stale 就會立即再重啟 → 風暴。沉降在
    # 成功與失敗兩條路徑都恢復了「最小間隔」。restarts_since_recovery 計「自上次真恢復以來的
    # 重啟次數」，是 inert 熔斷的計數（退出碼熔斷的 consecutive_failures 只算失敗，抓不到 inert）。
    restarts_since_recovery = int(state.get("restarts_since_recovery", 0)) + 1
    state["restarts_since_recovery"] = restarts_since_recovery
    state["post_restart_settle_until"] = now + POST_RESTART_SETTLE_SECONDS

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
        # WATCHDOG-BINDHOST-SANITIZE-1 (2026-06-05): 為什麼必須在這裡正規化
        # OPENCLAW_BIND_HOST——若 watchdog 自身 env 帶著 resolver 會 exit=2 硬拒
        # 的值，子進程會繼承它，restart_all.sh 內 `resolve_openclaw_api_bind_host`
        # （helper_scripts/lib/api_bind_host.sh）直接 exit=2 拒絕，導致每次重啟都
        # 失敗 → 自愈永久卡死（2026-06-05 incident：引擎 down ~20h 的成因之一）。
        #
        # 正規化集合 = resolver 會 exit=2 硬拒的 bind-host 值集合（all-interfaces
        # 0.0.0.0/:: + 空 + tailscale-unavailable {tailscale, tailscale-ip, ts}）→
        # auto，確保自愈子程序不被 bind-host 卡死；具體 IP / 合法值原樣放行；
        # 不繞過/不削弱安全守衛。malformed host:port 形式由 resolver `*)` 負責，
        # 非本集合範圍。
        #
        # 為什麼用 auto 當正規化目標：auto 永不 exit=2——resolver 在 tailscale
        # 不可用時 fallback 127.0.0.1，可用時綁 tailscale IP，因此 watchdog 的重啟
        # 子進程不可能被一個 resolver 會拒絕的 bind-host 值卡死。
        # 關鍵紀律：此處只動「自愈子進程自己的 recovery env」——把危險值正規化成
        # 安全的 auto 餵給守衛，而非繞過或弱化守衛；不碰 api_bind_host.sh /
        # restart_all.sh。operator 手動發起的重啟（manual restart / deploy / API）
        # 仍照舊在 0.0.0.0 / tailscale-unavailable 上 fail-closed-and-loud。
        # 為什麼把 {tailscale, tailscale-ip, ts} 也納入（FINDING #1 2026-06-05）：
        # 這幾個值在 tailscale 不在 PATH / 無 IPv4 時同樣 exit=2，會像 0.0.0.0 一樣
        # 卡死自愈；故 watchdog 的 recovery 子進程一律降到 never-fail 的 auto。
        sanitized_env = dict(os.environ)
        # resolver 的 exit=2 拒絕集合（與 api_bind_host.sh case 分支對齊）。
        DANGEROUS_BIND_HOSTS = {"0.0.0.0", "::", "", "tailscale", "tailscale-ip", "ts"}
        if "OPENCLAW_BIND_HOST" in sanitized_env:
            if sanitized_env.get("OPENCLAW_BIND_HOST", "").strip() in DANGEROUS_BIND_HOSTS:
                logger.warning(
                    "Sanitizing dangerous inherited OPENCLAW_BIND_HOST=%r → 'auto' for restart "
                    "/ 正規化被污染的 OPENCLAW_BIND_HOST=%r → 'auto' 以解除自愈卡死",
                    sanitized_env.get("OPENCLAW_BIND_HOST"),
                    sanitized_env.get("OPENCLAW_BIND_HOST"),
                )
                sanitized_env["OPENCLAW_BIND_HOST"] = "auto"
        result = subprocess.run(
            RESTART_COMMAND,
            cwd=str(repo_root),
            env=sanitized_env,
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
        # 退出碼語義：exit=0 重啟「成功」，清退出碼維度的失敗計數（consecutive_failures）。
        # 為什麼 NOT 清 restarts_since_recovery：這是 inert 維度，只有「真恢復」（on_engine_recovery
        # 看到新鮮快照）才算數。exit=0 但引擎 inert 時 restarts_since_recovery 持續累計到熔斷。
        state["consecutive_failures"] = 0
        state["last_restart_success_ts"] = now
        state["circuit_broken"] = False
        state["next_allowed_restart_ts"] = 0.0
        state["last_failure_reason"] = ""
        # FINDING #2：成功重啟結束一個 skip-emit 週期，清 marker 讓之後真正的
        # skip 能再發一次（同一 dict 內清，不另開 load/save）。
        state.pop("last_restart_skipped_reason", None)
        state.pop("last_restart_skipped_emit_ts", None)
        # WATCHDOG-INERT-STORM-FIX-1：成功(exit=0)路徑也檢 inert 熔斷——這正是 2026-06-05
        # 風暴的成因（每次重啟都 exit=0、退出碼熔斷永不觸發，但快照從不刷新）。達 INERT_RESTART_LIMIT
        # 即在剛被清為 False 的 circuit_broken 上覆寫回 True，止住風暴。
        inert_break = restarts_since_recovery >= INERT_RESTART_LIMIT
        if inert_break:
            state["circuit_broken"] = True
        save_state(data_dir, state)
        logger.info("Auto-restart succeeded / 自動重啟成功")
        _append_canary_event(data_dir, {
            "ts": now, "event": "RESTART_SUCCESS",
            "consecutive_failures_before": consecutive,
        })
        if inert_break:
            _emit_inert_circuit_broken(data_dir, restarts_since_recovery, now)
            return False
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

    # WATCHDOG-ALERT-WIRE：熔斷（自動恢復放棄）才告警 —— 這是真正需要人工介入的訊號。
    # 必須在 save_state 之後：emit 內以 load_state 讀 consecutive_failures / last_failure_reason
    # 組裝 payload，需先落盤才正確。key="circuit_broken" 確保整段熔斷期只發一次（去重）。
    # 不在 RESTART_FAILED 路徑告警（那是退避中自癒的暫態，會在正常重啟循環中刷屏）。
    if state.get("circuit_broken"):
        subject, body = _build_engine_down_payload(data_dir, now)
        emit_engine_down_alert_if_new(data_dir, "circuit_broken", subject, body, now)

    return False


def _maybe_suppress_destructive_restart(
    state: WatchdogState, snapshot_age: float, data_dir: str
) -> Optional[str]:
    """B1（2026-06-15）：snapshot stale 時對引擎 IPC 做存活交叉檢查，決定是否抑制重啟。

    回傳：
      - "fallback"（非 None）= 已抑制破壞性重啟（引擎活、只是 snapshot-writer 停寫）；
        caller 應立即 return 此值，不做 crash 計數 / 重啟 / 平倉，僅已發
        SNAPSHOT_STALL_ENGINE_ALIVE 事件。
      - None = 未抑制（IPC 不活 / 含糊 / 達 max-hold 上限）；caller 照常走重啟路徑。

    fail toward restart：probe_engine_ipc 對任何含糊一律回 alive=False；
    decide_restart_suppression 只在 alive=True 且未達 max-hold 上限才回 suppress=True。
    本函數任何意外都吞沒並回 None（= 倒向重啟），不得拋進 watchdog 偵測/重啟邏輯。
    """
    try:
        probe = watchdog_liveness_crosscheck.probe_engine_ipc()
        now = time.time()
        decision = watchdog_liveness_crosscheck.decide_restart_suppression(
            probe,
            prior_hold_cycles=state.liveness_suppress_cycles,
            first_suppress_ts=state.liveness_first_suppress_ts,
            now=now,
        )
        if not decision.suppress:
            # 不抑制：IPC 不活/含糊（真重啟）或達 max-hold 上限（升級重啟）。
            # 達上限時 log 一條 critical 讓 operator 知道「曾抑制但已放棄、即將平倉」。
            if decision.reason.startswith("max_hold_"):
                logger.critical(
                    "B1 max-hold reached (%s): snapshot stalled %.1fs, IPC alive but "
                    "suppressed %d cycles / %.0fs — escalating to destructive restart "
                    "/ B1 max-hold 上限：抑制 %d 週期後升級重啟",
                    decision.reason, snapshot_age, decision.hold_cycles,
                    decision.hold_seconds, decision.hold_cycles,
                )
            return None

        # 抑制成立：引擎活著，只是 snapshot-writer 停寫。更新連續抑制計數狀態。
        first_ts = state.liveness_first_suppress_ts
        if first_ts is None:
            first_ts = now
            state.liveness_first_suppress_ts = first_ts
        state.liveness_suppress_cycles = decision.hold_cycles
        logger.warning(
            "B1 liveness cross-check: snapshot stale %.1fs but engine ALIVE via IPC (%s) — "
            "SUPPRESSING destructive restart (hold cycle %d, %.0fs) "
            "/ B1 交叉檢查：快照過期但引擎仍活，抑制破壞性重啟",
            snapshot_age, probe.reason, decision.hold_cycles, decision.hold_seconds,
        )
        # 只在「首次抑制」那一刻發事件（avoid 每 2s poll 灌爆 canary/alert）。dedup_key
        # 以首次抑制時間戳算，重複 poll 不重發；恢復後 streak 歸零，下次新 stall 才再發。
        if decision.hold_cycles == 1:
            _emit_snapshot_stall_engine_alive(
                data_dir, first_ts, snapshot_age, probe.reason,
                decision.hold_cycles, decision.hold_seconds,
            )
        return "fallback"
    except Exception as exc:  # noqa: BLE001 — 交叉檢查自身任何意外都倒向重啟（fail-safe）
        logger.warning(
            "B1 liveness cross-check errored (failing toward restart): %s / "
            "B1 交叉檢查出錯（倒向重啟）",
            exc,
        )
        return None


def on_engine_crash(
    state: WatchdogState,
    snapshot_age: float,
    data_dir: str = "",
    log_path: Optional[Path] = None,
) -> str:
    """
    Handle engine crash detection.
    處理引擎崩潰檢測。

    Returns: action taken ("fallback" | "rollback" | "network_outage")

    WATCHDOG-DNS-CLASSIFY-1 (2026-04-20) + NETOUTAGE-CLASSIFIER-FIX
    (2026-05-21): when log_path is given, inspect the engine.log tail; a pure
    DNS/transport outage classifies as `network_outage` via four gates:
      (b) ≥5 consecutive network-error lines（向後兼容）
      (c) tail 內 ≥5 interleaved network-error 行且比例 ≥25%
      (d) cross-rotation aggregate（active + rotated tail 合併重評）
    panic/assertion override (a) 強制 engine_crash；PG/disk/OOM token 觸發
    ambiguous-evidence guard 也保守降級 engine_crash。
    no strike is counted, no auto-restart is attempted (restart can't fix DNS
    and would burn the circuit-breaker). engine_alive still flips to False so
    that the recovery path fires normally once the network comes back.

    WATCHDOG-RETRY-LEVELTRIGGER-1 (2026-06-05): 為什麼移除舊的
    `if not state.engine_alive: return "none"` 早退——那是 2026-06-05 incident
    的死鎖成因之二。舊邏輯下一旦 engine_alive 翻 False（首次偵測 stale）且重啟
    持續失敗，就不會再寫出新鮮快照，on_engine_recovery 永遠不會把 engine_alive
    翻回 True，於是之後每次 poll 都在這裡早退「none」，永遠不再重試重啟，讓引擎
    卡在第一次失敗，連 should_restart 的退避 + MAX_CONSECUTIVE_FAILURES=5 熔斷都
    永遠到不了 5。
    修正後語義（嚴格區分兩個維度）：
      - 計數（COUNTING）維持 EDGE-triggered：total_crashes / crash_timestamps /
        total_network_outages / engine_alive=False 翻轉，只在「下行轉移」那一刻
        發生（即 state.engine_alive 仍為 True 時），重複 poll 不重複計數。
      - 重啟重試（RETRY）改為 LEVEL-triggered：每次處於 engine_crash 狀態的 stale
        poll 都呼叫 should_restart→trigger_restart。should_restart 已以退避窗口 +
        circuit_broken 為閘，故不會 storm——依 [60,120,300,600,3600] 排程重試，
        滿 5 次熔斷後停止。
      - network_outage 維持原設計：永不 trigger_restart（重啟治不了 DNS，且會
        燒掉熔斷計數）；每次 poll 重新分類沒問題，只是 network_outage 永不重啟。
    """
    # 記錄進入本次 poll 前的存活狀態，用於區分 edge（下行轉移）vs level（持續 down）。
    # 為什麼先存：下面會無條件把 engine_alive 設 False，必須在那之前抓到「是否為轉移」。
    was_alive = state.engine_alive

    # Classify first. A null log_path preserves the pre-DNS-CLASSIFY-1 behavior
    # (always engine_crash), keeping existing callers unaffected.
    # 先分類；log_path=None 時維持舊行為（總是 engine_crash）以不影響既有呼叫者。
    # 為什麼每次 poll 都重分類：log tail 可能變化（DNS 恢復後出現 panic 等）；
    # 重分類安全，network_outage 分支本就不重啟。
    classification = "engine_crash"
    if log_path is not None:
        classification = classify_engine_failure(log_path)

    if classification == "network_outage":
        # 計數只在下行轉移時做一次（edge）；已 down 的重複 poll 不重複計數。
        if was_alive:
            # 單一 detection_ts：canary 事件的 `ts` 與 audit dedup_key 必須用同一時間戳，
            # 否則 backstop bridge 由 canary 算出的 key 與 direct write 的 key 不一致。
            outage_ts = time.time()
            state.engine_alive = False
            state.total_network_outages += 1
            state.network_outage_timestamps.append(outage_ts)
            logger.warning(
                "NETWORK_OUTAGE classified — snapshot age=%.1fs, total outages=%d "
                "(strike NOT counted, auto-restart skipped) "
                "/ 網路中斷分類 — 快照年齡=%.1f秒，總次數=%d（不計 strike，跳過自動重啟）",
                snapshot_age, state.total_network_outages,
                snapshot_age, state.total_network_outages,
            )
            if data_dir:
                outage_dedup_key = canary_audit_common.build_dedup_key(
                    "network_outage", outage_ts
                )
                _append_canary_event(data_dir, {
                    "ts": outage_ts,
                    "event": "NETWORK_OUTAGE",
                    "snapshot_age_seconds": snapshot_age,
                    "total_outages": state.total_network_outages,
                    # bridge 直接讀此 key 去 NOT EXISTS 比對（與 direct write 同形）。
                    "dedup_key": outage_dedup_key,
                })
                # NETWORK_OUTAGE 無重啟路徑，故 direct write 在 canary append 之後即可。
                _emit_audit_event_best_effort(
                    "NETWORK_OUTAGE",
                    outage_ts,
                    f"engine network outage detected (snapshot stale {snapshot_age:.1f}s)",
                    {
                        "snapshot_age_seconds": snapshot_age,
                        "total_outages": state.total_network_outages,
                        "classification": "network_outage",
                    },
                    "DNS/transport outage; no strike, no auto-restart",
                )
        # network_outage 永不重啟（每次 poll 都 return，不落到下面的 retry 區塊）。
        return "network_outage"

    # ── engine_crash 分支 ──
    # B1 liveness cross-check (2026-06-15)：在把 stale 判定升級為「破壞性重啟（SIGTERM
    # → 以市價平掉所有未平倉位）」之前，先向第二個獨立訊號（引擎 IPC socket）求證引擎
    # 是否仍活。RCA：~21/21 次這類重啟其實引擎活著（仍 serve IPC、處理 tick），只是
    # snapshot-writer task 停寫——等於 ~2×/天 對活引擎誤殺平倉。A1/A2 軌修 stall 本身；
    # B1 是 defence-in-depth：無論根因為何，先擋掉這個破壞性的誤判重啟。
    #
    # fail toward restart（鐵則）：唯有 IPC 在緊湊 timeout 內「明確」回正確 reply 才抑制
    # 重啟；連不上 / socket 不存在 / 認證失敗 / 逾時 / 亂碼 / RPC error 一律當「沒有明確
    # 存活證據」→ 照舊重啟（存活優先於避免平倉）。抑制亦有 max-hold 上限（連續週期 +
    # 硬性 10 分鐘牆），達上限即升級重啟——永久停寫快照的 writer 本身就是故障。
    #
    # 為什麼放在 crash 計數「之前」：抑制成立時引擎其實活著，不應污染 total_crashes /
    # crash_timestamps / 三振 / 21d 穩定時鐘。故先探測、決策；抑制則直接 return「不計數、
    # 不翻 engine_alive、不重啟、不平倉」，僅發 SNAPSHOT_STALL_ENGINE_ALIVE。
    if data_dir and watchdog_liveness_crosscheck.liveness_crosscheck_enabled():
        crosscheck_action = _maybe_suppress_destructive_restart(state, snapshot_age, data_dir)
        if crosscheck_action is not None:
            return crosscheck_action

    # 計數 / strike bookkeeping 只在下行轉移時做一次（edge）。
    # crash_ts：本次 crash 轉移的偵測時間戳（只在 edge 設）；用於稍後在重啟「之後」
    # 寫 canary 事件 + audit_events，且 dedup_key 跨兩條路徑用同一時間戳。
    crash_ts: Optional[float] = None
    if was_alive:
        crash_ts = time.time()
        state.engine_alive = False
        state.total_crashes += 1
        state.crash_timestamps.append(crash_ts)
        logger.error(
            "ENGINE_CRASH detected — snapshot age=%.1fs, total crashes=%d "
            "/ 檢測到引擎崩潰 — 快照年齡=%.1f秒，總崩潰數=%d",
            snapshot_age, state.total_crashes, snapshot_age, state.total_crashes,
        )
    # 走到此（未被 B1 抑制）= IPC 不活/含糊/達 max-hold/交叉檢查關閉 → 重啟照舊。
    # 抑制計數歸零：本次既然要重啟，連續抑制 streak 結束。
    state.liveness_suppress_cycles = 0
    state.liveness_first_suppress_ts = None

    # WATCHDOG-RETRY-LEVELTRIGGER-1 (2026-06-05): 重啟重試改為 LEVEL-triggered，
    # 每次 engine_crash 狀態的 stale poll 都跑（含已 down 的重複 poll），不再被
    # 早退吞掉。should_restart 已用退避窗口 + circuit_broken 閘，故不會 storm。
    # 維持 Fix 2 (2026-04-14) rationale：成功重啟後下次 poll 看到新鮮快照，自然走
    # on_engine_recovery() 復原；strike 計數作為重啟風暴的次級安全網。
    # restart_outcome：記錄本次 poll 的重啟結果，供稍後寫進 audit_events 的 event_details
    # （spec：restart outcome if known）。allowed=True 才真 trigger；其餘記跳過原因。
    restart_outcome = "not_attempted"
    if data_dir:
        now = time.time()
        allowed, reason_key, reason_detail = should_restart(data_dir, now)
        if allowed:
            restart_ok = trigger_restart(data_dir)
            restart_outcome = "restart_success" if restart_ok else "restart_failed"
        else:
            restart_outcome = f"restart_skipped:{reason_key}"
            # logger.warning 用 detail 保留 per-poll 本地可見性（log 會 rotate）。
            logger.warning(
                "Auto-restart skipped: %s / 跳過自動重啟：%s",
                reason_detail, reason_detail,
            )
            # FINDING #2-HIGH-1：RESTART_SKIPPED canary 用穩定的 reason_key 去重，
            # 避免 backoff 倒數秒每 poll 變字串而失去節流（detail 仍寫進 payload）；
            # circuit_broken 終態下也不會每 2s 灌一條把 RESTART_CIRCUIT_BROKEN 淹沒。
            emit_restart_skipped_if_new(data_dir, reason_key, reason_detail, now)

        # ENGINE-AUDIT-VISIBILITY (2026-06-15)：重啟觸發「之後」才寫 audit_events
        # （恢復優先；DB 寫入絕不延遲重啟）。只在 crash 下行轉移那一刻（crash_ts 非 None）
        # 寫一條 —— 一個 crash 事件對應一行，重複 poll 不重寫。canary 事件同時帶 dedup_key
        # 供 backstop bridge 補洞（ENGINE_CRASH 先前無 canary 事件，bridge 才有東西可 tail）。
        if crash_ts is not None:
            crash_dedup_key = canary_audit_common.build_dedup_key(
                "engine_crash", crash_ts
            )
            _append_canary_event(data_dir, {
                "ts": crash_ts,
                "event": "ENGINE_CRASH",
                "snapshot_age_seconds": snapshot_age,
                "total_crashes": state.total_crashes,
                "restart_outcome": restart_outcome,
                "dedup_key": crash_dedup_key,
            })
            _emit_audit_event_best_effort(
                "ENGINE_CRASH",
                crash_ts,
                f"engine crash detected (snapshot stale {snapshot_age:.1f}s, "
                f"total crashes={state.total_crashes})",
                {
                    "snapshot_age_seconds": snapshot_age,
                    "total_crashes": state.total_crashes,
                    "classification": "engine_crash",
                    "restart_outcome": restart_outcome,
                },
                f"auto-restart {restart_outcome}; strike bookkeeping applied",
            )

        # incident_policy E1-E：engine_dead 是 engine 外 watchdog producer。引擎死時
        # Rust 進程內的 C4 sender 不可用，因此此處只做 notify-only（不餵 AllFail）。
        engine_dead_incident.maybe_emit_notify_only(
            data_dir,
            time.time(),
            snapshot_age,
            load_state,
            save_state,
            _append_canary_event,
            emit_engine_down_alert_if_new,
        )

        # WATCHDOG-ALERT-WIRE：持續宕機重發告警（level-triggered）。
        # 為什麼需要：2026-06-05 引擎 down ~20h；熔斷後 circuit_broken 是終態，初次
        # 告警之後不會再有狀態轉移觸發新告警。這裡每 RE_ALERT_INTERVAL_SECONDS 窗口
        # 重發一次提醒（key 隨整數小時變化 → 去重恰好每窗口一條，不每 poll 刷屏）。
        # 閘在 circuit_broken：退避中（未熔斷）仍可能自癒，不重發。
        _state = load_state(data_dir)
        if _state.get("circuit_broken"):
            last_alert_ts = _state.get("last_engine_down_alert_ts", 0.0)
            if now - last_alert_ts >= RE_ALERT_INTERVAL_SECONDS:
                down_since = _state.get("engine_down_since_ts", now)
                hours_down = int((now - down_since) // 3600)
                subject, body = _build_engine_down_payload(data_dir, now)
                emit_engine_down_alert_if_new(
                    data_dir, f"circuit_broken_reping_{hours_down}", subject, body, now,
                )

    # 3-strike 回滾檢查維持 edge-triggered（與 crash 計數綁定）：只在剛發生轉移時評估。
    # 為什麼綁 was_alive：crash_timestamps 只在轉移時 append，已 down 的重複 poll 不應
    # 重新觸發 rollback 判定（避免在持續 down 期間每次 poll 都報 rollback）。
    if was_alive:
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


def on_engine_recovery(state: WatchdogState, data_dir: str = "") -> None:
    """
    Handle engine recovery detection.
    處理引擎恢復檢測。

    FINDING #2 (2026-06-05)：data_dir 給定時，恢復也清 RESTART_SKIPPED 去重 marker。
    為什麼：恢復可能來自 operator 手動重啟引擎或網路回復（非 watchdog 自身成功重啟），
    這條路徑 trigger_restart 不會跑成功分支，仍需在這裡結束 skip-emit 週期，
    讓之後若再進入 skip 能重新發一次事件。

    WATCHDOG-INERT-STORM-FIX-1 (2026-06-05)：真恢復（看到新鮮快照）必須「完全 re-arm」
    重啟狀態機——歸零 restarts_since_recovery / post_restart_settle_until / circuit_broken /
    consecutive_failures / next_allowed_restart_ts。為什麼：恢復＝引擎再次健康，未來若再宕機
    應從乾淨狀態重新計數（含 inert 與 exit-code 兩個熔斷維度）。這也讓「部署撞車觸發 inert
    熔斷後，部署完成 + 引擎恢復」時 watchdog 自動 re-arm（無需人工 reset）。

    B1 (2026-06-15)：snapshot 重新新鮮即 reset 存活交叉檢查的連續抑制計數。為什麼放在
    `if state.engine_alive` 早退「之前」：B1 抑制路徑不翻 engine_alive=False（引擎其實
    一直活著），故抑制後 snapshot 恢復新鮮時 engine_alive 仍是 True、會走早退；若把
    reset 放在早退之後就永遠執行不到，max-hold streak 會跨越多次獨立 stall 累積誤觸上限。
    """
    # B1：snapshot 恢復新鮮 = snapshot-writer 重新運作，連續抑制 streak 結束（恢復也是
    # 非轉移路徑，故必須在早退前歸零）。
    state.liveness_suppress_cycles = 0
    state.liveness_first_suppress_ts = None

    if state.engine_alive:
        return  # Already alive / 已恢復

    state.engine_alive = True
    state.last_recovery_ts = time.time()
    if data_dir:
        clear_restart_skipped_marker(data_dir)
        # 完全 re-arm 重啟狀態機（見 docstring）。單獨 load/save，與下方告警 marker 清理解耦。
        _rearm = load_state(data_dir)
        _rearm["restarts_since_recovery"] = 0
        _rearm["post_restart_settle_until"] = 0.0
        _rearm["circuit_broken"] = False
        _rearm["consecutive_failures"] = 0
        _rearm["next_allowed_restart_ts"] = 0.0
        save_state(data_dir, _rearm)
        engine_dead_incident.emit_resolved_if_active(
            data_dir, time.time(), load_state, save_state, _append_canary_event,
        )
        # WATCHDOG-ALERT-WIRE：恢復全清告警 —— 僅在先前確實發過 down-alert 時才發。
        # 為什麼有條件：若引擎一直健康（從未告警），恢復路徑不應憑空發 INFO；只有走過
        # 熔斷 / 宕機告警的恢復才值得通知「已恢復」。讀 marker（含 down-since）後再清，
        # 順序不可顛倒（先清會丟失宕機時長）。
        _down_state = load_state(data_dir)
        if _down_state.get("last_engine_down_alert_key") is not None:
            now = time.time()
            down_since = _down_state.get("engine_down_since_ts", now)
            duration = _format_down_duration(now - down_since)
            _send_alert_best_effort(
                "OpenClaw engine RECOVERED",
                f"snapshot fresh again (was down {duration})",
                "INFO",
                data_dir,
            )
        clear_engine_down_alert_marker(data_dir)
        # ENGINE-AUDIT-VISIBILITY (2026-06-15)：恢復轉移寫一條 audit_events（severity=info）
        # + canary 事件（先前無，bridge 才能 backstop 恢復事件）。只在轉移那一刻寫一次
        # （上方 `if state.engine_alive: return` 已保證非轉移不進此處）。無重啟路徑，順序無約束。
        recovery_ts = state.last_recovery_ts
        recovery_dedup_key = canary_audit_common.build_dedup_key(
            "engine_recovered", recovery_ts
        )
        _append_canary_event(data_dir, {
            "ts": recovery_ts,
            "event": "ENGINE_RECOVERED",
            "total_crashes": state.total_crashes,
            "dedup_key": recovery_dedup_key,
        })
        _emit_audit_event_best_effort(
            "ENGINE_RECOVERED",
            recovery_ts,
            "engine recovered — snapshot fresh again",
            {
                "total_crashes": state.total_crashes,
                "classification": "engine_recovered",
            },
            "recovery transition; restart state re-armed",
        )
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
            on_engine_recovery(state, data_dir=str(data_path))
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
        # Exit code 10：single-instance lock contention（10-19 為 startup/lock 區段）。
        # 原為 3；P1-WATCHDOG-EXIT-CODE-CLARIFY 重排語意供 systemd / 上層觀察區分。
        sys.exit(10)
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
        # Exit code 20：runtime rollback triggered（20-29 為 runtime/rollback 區段）。
        # 原為 2；P1-WATCHDOG-EXIT-CODE-CLARIFY 重排語意供 systemd / 上層觀察區分。
        sys.exit(20)


if __name__ == "__main__":
    main()
