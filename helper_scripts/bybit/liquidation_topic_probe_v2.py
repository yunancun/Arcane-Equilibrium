#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────
# MODULE_NOTE
# 模組目的：W-AUDIT-8a C1 v2 韌性探針。v1 (`liquidation_topic_probe.py`) 在 2026-05-15
#          5h 觀察後 FAIL_CONNECTION（單連線無 reconnect）。v2 對應 RCA：
#            1) 指數退避 reconnect（1→2→4→8→16→32→60s cap）
#            2) TCP keepalive (SO_KEEPALIVE/TCP_KEEPIDLE/TCP_KEEPINTVL/TCP_KEEPCNT)
#            3) Ping interval 縮 20s → 10s
#            4) Per-hour checkpoint JSON 寫 progress + samples
#            5) 3 次 session restart 上限（連續 5 attempt fail = 觸 restart）
#            6) 24h 容差 PASS：uptime_ratio ≥ 0.95 + 觀察 ≥ 23h
#          設計權威：docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md
#
# 與 v1 差異：
#   - v1 = 單連線「break-on-any-error」最小可達；證實 Bybit WS topic 不 reject
#   - v2 = 24h 級韌性，可承受 mid-run 連線中斷自動恢復
#   - v1 保留不動（control comparison / 歷史證據）
#
# 使用：
#   python3 helper_scripts/bybit/liquidation_topic_probe_v2.py --dry-run
#   python3 helper_scripts/bybit/liquidation_topic_probe_v2.py --duration-sec 60          # smoke
#   python3 helper_scripts/bybit/liquidation_topic_probe_v2.py --duration-sec 86400 \
#       --enable-reconnect --max-restart 3 --checkpoint-interval-sec 3600 \
#       --session-id c1_v2_$(date -u +%Y%m%dT%H%M%SZ)
#
# Exit codes：
#   0 = PASS_C1_PROOF_CANDIDATE (≥23h + uptime_ratio≥0.95 + 0 poison) 或 dry-run / smoke pass
#   1 = FAIL_*（任何 deterministic 失敗 verdict，含 reconnect/restart 用盡）
#   2 = FATAL（dependency 缺失 / runtime fatal）
# ─────────────────────────────────────────────────────────
"""Bybit liquidation topic standalone probe v2 — resilient 24h harness.

The script intentionally uses an isolated public WS connection with reconnect
tolerance. It must never be imported by production runtime topic builders.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── 常量 ─────────────────────────────────────────────────────────────────
# 預設 WS endpoint 與 topic 與 v1 一致；保留 PROBE 名稱不撞 production builder
DEFAULT_URL = "wss://stream.bybit.com/v5/public/linear"
DEFAULT_TOPIC = "allLiquidation.BTCUSDT"
DEFAULT_CANARY_SYMBOL = "BTCUSDT"
OFFICIAL_DOC_URL = "https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation"

# Control topics（保 4 個與 v1 一致；v2 PASS gate 放寬到「≥3 alive」見 §3.5）
CONTROL_TEMPLATES = (
    "tickers.{symbol}",
    "orderbook.50.{symbol}",
    "publicTrade.{symbol}",
    "kline.1.{symbol}",
)

# Poison pattern：Bybit error response 識別
POISON_PATTERNS = (
    "handler not found",
    "too many visits",
    "rate limit",
    "rate-limit",
    "access too frequent",
    "rejected",
)

# 指數退避序列；attempt index >= 6 後 cap 60s
RECONNECT_BACKOFF_SEC = (1, 2, 4, 8, 16, 32)
RECONNECT_BACKOFF_CAP_SEC = 60
# 連續 6 attempt 仍 fail = 觸發 session restart 計數
RECONNECT_MAX_ATTEMPTS_PER_SESSION = 6

# TCP keepalive 參數（per design §3.2）
TCP_KEEPIDLE_SEC = 60
TCP_KEEPINTVL_SEC = 10
TCP_KEEPCNT = 3

# Ping interval（v1=20s → v2=10s 更快發現 server-side close）
DEFAULT_PING_INTERVAL_SEC = 10.0

# 24h tolerance：observed ≥ 23h + uptime_ratio ≥ 0.95
PASS_MIN_OBSERVED_SEC = 23 * 3600
PASS_MIN_UPTIME_RATIO = 0.95

# Checkpoint 寫入相對 path（OPENCLAW_DATA_DIR 子目錄）
CHECKPOINT_FILE_NAME = "c1_proof_progress.json"


# ── 資料結構 ─────────────────────────────────────────────────────────────

@dataclass
class ReconnectEvent:
    """單次 reconnect attempt 紀錄；attempt 從 1 起算。"""
    attempt: int
    started_at_utc: str
    backoff_sec: float
    reason: str
    success: bool
    error_text: str | None = None


@dataclass
class RestartEvent:
    """單次 session restart 紀錄；restart 從 1 起算（restart 0 = initial）。"""
    restart_index: int
    triggered_at_utc: str
    reason: str           # RECONNECT_EXHAUSTED / CONTROL_SILENT / WATCHDOG_REVIVE
    elapsed_sec_at_trigger: float
    uptime_sec_at_trigger: float


@dataclass
class ProbeV2Stats:
    """v2 探針執行統計；對應 design §3.3 checkpoint schema + 最終 report."""

    # ── 基本 ──
    session_id: str
    started_at_utc: str
    finished_at_utc: str | None = None
    url: str = DEFAULT_URL
    candidate_topic: str = DEFAULT_TOPIC
    control_topics: list[str] = field(default_factory=list)

    # ── 目標 vs 觀察 ──
    target_sec: int = 0
    elapsed_sec: float = 0.0       # wall-clock since session start（含 reconnect 等待）
    uptime_sec: float = 0.0        # 累計 connection 真實在線時間
    uptime_ratio: float = 0.0      # uptime_sec / elapsed_sec

    # ── reconnect 統計 ──
    reconnect_attempts: int = 0
    reconnect_successes: int = 0
    reconnect_failures: int = 0
    reconnect_events: list[ReconnectEvent] = field(default_factory=list)
    last_reconnect_reason: str | None = None

    # ── restart 統計 ──
    restart_count: int = 0
    restart_events: list[RestartEvent] = field(default_factory=list)
    max_restart_budget: int = 3

    # ── 訊息計數 ──
    subscribe_success_count: int = 0
    subscribe_failure_count: int = 0
    pings_sent: int = 0
    pongs_seen: int = 0
    raw_message_count: int = 0
    topic_message_counts: dict[str, int] = field(default_factory=dict)
    last_seen_by_topic_utc: dict[str, str] = field(default_factory=dict)
    candidate_messages_seen: int = 0
    candidate_samples: list[dict[str, Any]] = field(default_factory=list)

    # ── 錯誤 / poison ──
    poison_events: list[str] = field(default_factory=list)
    connection_errors: list[str] = field(default_factory=list)

    # ── 結論 ──
    verdict: str = "UNKNOWN"
    interim_verdict: str = "INIT"
    c1_proof_eligible: bool = False
    c1_blocker: str | None = None
    blocker_if_aborted_now: str | None = None


# ── 工具函數 ─────────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    """回傳 UTC ISO-8601 字串（秒級）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_output_dir() -> Path:
    """探針輸出目錄；遵循 OPENCLAW_DATA_DIR env var（Mac/Linux 跨平台）。"""
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "audit" / "liquidation_topic_probe"


def build_topics(candidate_topic: str, canary_symbol: str) -> list[str]:
    """構造 subscribe 主題列表：候選 topic + 4 control topics（dedup）。"""
    topics = [candidate_topic]
    topics.extend(t.format(symbol=canary_symbol) for t in CONTROL_TEMPLATES)
    seen: set[str] = set()
    deduped: list[str] = []
    for topic in topics:
        if topic not in seen:
            seen.add(topic)
            deduped.append(topic)
    return deduped


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析 CLI args；v2 新增 reconnect / restart / checkpoint / session-id 旗標。"""
    parser = argparse.ArgumentParser(
        description="Run a resilient isolated Bybit public WS liquidation-topic probe (v2).",
    )
    # v1 兼容旗標
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--canary-symbol", default=DEFAULT_CANARY_SYMBOL)
    parser.add_argument("--duration-sec", type=int, default=86_400)
    parser.add_argument("--recv-timeout-sec", type=float, default=5.0)
    parser.add_argument(
        "--ping-interval-sec",
        type=float,
        default=DEFAULT_PING_INTERVAL_SEC,
        help="WS application-level ping interval（v2 預設 10s，v1 為 20s）",
    )
    parser.add_argument(
        "--proof-min-duration-sec",
        type=int,
        default=PASS_MIN_OBSERVED_SEC,
        help="觀察時長最小門檻（v2 = 23h 容差，design §3.5）",
    )
    parser.add_argument(
        "--proof-min-uptime-ratio",
        type=float,
        default=PASS_MIN_UPTIME_RATIO,
        help="uptime_sec / elapsed_sec 最小門檻（v2 預設 0.95）",
    )
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())

    # v2 新增旗標
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session 識別字串；未給時自動生成 c1_v2_<UTC>",
    )
    parser.add_argument(
        "--enable-reconnect",
        action="store_true",
        help="啟用指數退避 reconnect；未給 = v1 行為（break on error）",
    )
    parser.add_argument(
        "--max-restart",
        type=int,
        default=3,
        help="連續 reconnect 用盡時的 session restart 上限（design §3.4 = 3）",
    )
    parser.add_argument(
        "--checkpoint-interval-sec",
        type=int,
        default=3600,
        help="Per-hour checkpoint JSON 寫入間隔（design §3.3 = 3600）",
    )
    parser.add_argument(
        "--start-utc-midnight",
        action="store_true",
        help="若設，等到下一個 UTC 00:00:00 + 30s buffer 才開始 (design §3.6)",
    )
    parser.add_argument(
        "--max-candidate-samples",
        type=int,
        default=20,
        help="儲存 candidate topic 樣本上限（用於 MIT schema delta pre-review）",
    )

    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


# ── Payload 分類（與 v1 同樣語意，本副本保 v2 self-contained）─────────

def classify_payload(
    payload: dict[str, Any],
    stats: ProbeV2Stats,
    max_candidate_samples: int,
) -> None:
    """單筆 payload 統計 + poison 偵測 + topic 計數。

    與 v1 classify_payload 行為對齊；故意保 v2 私有副本避免跨檔耦合風險。
    """
    stats.raw_message_count += 1

    # Poison pattern 比對：序列化整個 payload 做全文掃描
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    lower_text = text.lower()
    if any(pattern in lower_text for pattern in POISON_PATTERNS):
        stats.poison_events.append(text[:1000])

    # subscribe response（success: True / False）
    success = payload.get("success")
    if success is True:
        stats.subscribe_success_count += 1
    elif success is False:
        stats.subscribe_failure_count += 1

    # Pong response
    if payload.get("op") == "pong" or payload.get("ret_msg") == "pong":
        stats.pongs_seen += 1

    # Topic-bearing message
    topic = payload.get("topic")
    if isinstance(topic, str):
        stats.topic_message_counts[topic] = stats.topic_message_counts.get(topic, 0) + 1
        stats.last_seen_by_topic_utc[topic] = _utc_now_iso()
        if topic == stats.candidate_topic:
            stats.candidate_messages_seen += 1
            if len(stats.candidate_samples) < max_candidate_samples:
                stats.candidate_samples.append(payload)


# ── TCP keepalive 加固（per design §3.2）───────────────────────────────

def _apply_tcp_keepalive(ws_sock: Any) -> str | None:
    """對 WS 底層 socket 套用 SO_KEEPALIVE + TCP_KEEPIDLE/INTVL/CNT。

    回傳 None = 成功；str = 警告訊息（適用平台不支援的 sockopt）。
    Mac (Darwin) 對 TCP_KEEPIDLE 名稱不同（TCP_KEEPALIVE），用 try/except 容錯。
    Linux 全部支援。
    """
    try:
        raw_sock = getattr(ws_sock, "sock", None)
        if raw_sock is None:
            return "no_underlying_socket"
        raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError as exc:
        return f"SO_KEEPALIVE_failed: {exc}"

    # TCP_KEEPIDLE（Linux）/ TCP_KEEPALIVE（Mac/Darwin）
    keepidle_name = "TCP_KEEPIDLE" if hasattr(socket, "TCP_KEEPIDLE") else "TCP_KEEPALIVE"
    try:
        keepidle_const = getattr(socket, keepidle_name, None)
        if keepidle_const is not None:
            raw_sock.setsockopt(socket.IPPROTO_TCP, keepidle_const, TCP_KEEPIDLE_SEC)
    except OSError as exc:
        return f"{keepidle_name}_failed: {exc}"

    try:
        if hasattr(socket, "TCP_KEEPINTVL"):
            raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, TCP_KEEPINTVL_SEC)
    except OSError as exc:
        return f"TCP_KEEPINTVL_failed: {exc}"

    try:
        if hasattr(socket, "TCP_KEEPCNT"):
            raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, TCP_KEEPCNT)
    except OSError as exc:
        return f"TCP_KEEPCNT_failed: {exc}"

    return None


# ── 連線 + 訂閱 helper ───────────────────────────────────────────────────

def _open_subscribed_connection(args: argparse.Namespace, topics: list[str], websocket_module: Any) -> tuple[Any, str | None]:
    """嘗試開單次連線並訂閱 topics；回傳 (ws_handle, keepalive_warning)。

    任何例外向上拋；caller 負責 reconnect 邏輯。
    """
    ws = websocket_module.create_connection(args.url, timeout=args.recv_timeout_sec)
    keepalive_warning = _apply_tcp_keepalive(ws)
    ws.send(json.dumps({"op": "subscribe", "args": topics}))
    return ws, keepalive_warning


def _close_connection_quietly(ws: Any) -> None:
    """安靜關閉 WS；reconnect / shutdown 都用此 helper。"""
    try:
        ws.close()
    except Exception:  # noqa: BLE001
        # 關閉錯誤不影響後續；intentional broad except for safety
        pass


# ── Reconnect 退避時長計算 ──────────────────────────────────────────────

def _backoff_for_attempt(attempt: int) -> float:
    """attempt: 1-based；前 6 attempt 用 sequence，第 7+ 用 60s cap。

    對應 design §3.2 序列 1/2/4/8/16/32/60(cap)。
    """
    if attempt < 1:
        return 0.0
    if attempt <= len(RECONNECT_BACKOFF_SEC):
        return float(RECONNECT_BACKOFF_SEC[attempt - 1])
    return float(RECONNECT_BACKOFF_CAP_SEC)


# ── Checkpoint 寫入 ─────────────────────────────────────────────────────

def _write_checkpoint(stats: ProbeV2Stats, output_dir: Path) -> Path:
    """寫入 checkpoint JSON 至 OPENCLAW_DATA_DIR/audit/.../c1_proof_progress.json。

    每 60min 與 final report 階段呼叫；overwrite 同檔。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / CHECKPOINT_FILE_NAME
    payload = json.dumps(asdict(stats), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    checkpoint_path.write_text(payload, encoding="utf-8")
    return checkpoint_path


# ── 主迴圈：單 session run（內含 reconnect loop）────────────────────────

def _run_session(
    args: argparse.Namespace,
    stats: ProbeV2Stats,
    websocket_module: Any,
    session_start_mono: float,
    output_dir: Path,
) -> str:
    """執行單個 session 直到下列條件之一：
        1. 達 target_sec wall-clock          → 'COMPLETED'
        2. 連續 6 attempt reconnect 失敗     → 'RECONNECT_EXHAUSTED'
        3. shutdown signal (KeyboardInterrupt) → 'INTERRUPTED'

    Session 內 reconnect loop：任何 recv 例外 → 增 attempt → 退避 → 重連 + 重訂。
    Reconnect 成功 = attempt counter 歸零。

    回傳 'COMPLETED' / 'RECONNECT_EXHAUSTED' / 'INTERRUPTED'。
    """
    topics = build_topics(args.topic, args.canary_symbol)
    if not stats.topic_message_counts:
        # 初始化 topic counters（重啟 session 時不重置已累計）
        for topic in topics:
            stats.topic_message_counts.setdefault(topic, 0)

    next_checkpoint_at = session_start_mono + args.checkpoint_interval_sec
    target_deadline_mono = session_start_mono + args.duration_sec

    # 初始連線
    try:
        ws, keepalive_warn = _open_subscribed_connection(args, topics, websocket_module)
    except Exception as exc:  # noqa: BLE001
        stats.connection_errors.append(f"initial_connect_failed: {type(exc).__name__}: {exc}")
        return "RECONNECT_EXHAUSTED"

    if keepalive_warn is not None:
        # 非致命：keepalive 部分套用失敗仍可運行（紀錄到 connection_errors 不算 fatal）
        stats.connection_errors.append(f"keepalive_warning: {keepalive_warn}")

    # Connection-on 時段起點（uptime 累計）
    conn_on_mono = time.monotonic()
    next_ping = conn_on_mono + args.ping_interval_sec
    consecutive_reconnect_attempt = 0  # 連續 fail attempts；reconnect 成功 = 歸零

    try:
        while True:
            now_mono = time.monotonic()
            if now_mono >= target_deadline_mono:
                # 累計這段 conn-on uptime
                stats.uptime_sec += now_mono - conn_on_mono
                _close_connection_quietly(ws)
                return "COMPLETED"

            # ── Checkpoint 寫入 ──
            # 設計：不修改 stats.uptime_sec（仍是「已 disconnect 段累計」），
            # 改在 checkpoint 寫入時臨時計入當前 conn-on 段，並在寫入完成
            # 後還原 stats.uptime_sec。disconnect 路徑也用 (now - conn_on_mono)
            # 累計同一段，二者公式一致不會重複計算。
            if now_mono >= next_checkpoint_at:
                stats.elapsed_sec = now_mono - session_start_mono
                current_segment = now_mono - conn_on_mono
                saved_uptime = stats.uptime_sec
                stats.uptime_sec = saved_uptime + current_segment
                stats.uptime_ratio = (
                    stats.uptime_sec / stats.elapsed_sec if stats.elapsed_sec > 0 else 0.0
                )
                stats.interim_verdict = _interim_verdict(stats)
                stats.blocker_if_aborted_now = (
                    "Duration shorter than 24h; SMOKE_PASS_NOT_C1_PROOF if abort"
                )
                _write_checkpoint(stats, output_dir)
                # 還原；disconnect path 會在實際斷線時加回當前段
                stats.uptime_sec = saved_uptime
                next_checkpoint_at = now_mono + args.checkpoint_interval_sec

            # ── Application-level ping ──
            if now_mono >= next_ping:
                try:
                    ws.send(json.dumps({"op": "ping"}))
                    stats.pings_sent += 1
                except Exception as exc:  # noqa: BLE001
                    # Ping 失敗即視為連線異常觸 reconnect
                    stats.connection_errors.append(f"ping_send_failed: {type(exc).__name__}: {exc}")
                    # 累計這段 conn-on uptime 後嘗試 reconnect
                    stats.uptime_sec += now_mono - conn_on_mono
                    _close_connection_quietly(ws)
                    if not args.enable_reconnect:
                        return "RECONNECT_EXHAUSTED"
                    reconnect_result = _try_reconnect(
                        args, stats, websocket_module, topics,
                        consecutive_reconnect_attempt,
                        f"ping_failed: {type(exc).__name__}",
                    )
                    if reconnect_result is None:
                        return "RECONNECT_EXHAUSTED"
                    ws, conn_on_mono, next_ping, consecutive_reconnect_attempt = reconnect_result
                    continue
                next_ping = now_mono + args.ping_interval_sec

            # ── 訊息接收 ──
            try:
                raw = ws.recv()
            except websocket_module.WebSocketTimeoutException:
                # recv timeout 是 OK 路徑（control flow），不觸 reconnect
                continue
            except Exception as exc:  # noqa: BLE001
                stats.connection_errors.append(f"recv_failed: {type(exc).__name__}: {exc}")
                # 累計這段 conn-on uptime
                stats.uptime_sec += now_mono - conn_on_mono
                _close_connection_quietly(ws)
                if not args.enable_reconnect:
                    return "RECONNECT_EXHAUSTED"
                reconnect_result = _try_reconnect(
                    args, stats, websocket_module, topics,
                    consecutive_reconnect_attempt,
                    f"recv_failed: {type(exc).__name__}",
                )
                if reconnect_result is None:
                    return "RECONNECT_EXHAUSTED"
                ws, conn_on_mono, next_ping, consecutive_reconnect_attempt = reconnect_result
                continue

            # 收到訊息 → reconnect attempt 計數歸零（穩定 stream 證明）
            if consecutive_reconnect_attempt > 0:
                consecutive_reconnect_attempt = 0

            # ── JSON 解析 ──
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                stats.connection_errors.append(f"non_json_message: {raw[:200]}")
                continue
            if isinstance(payload, dict):
                classify_payload(payload, stats, args.max_candidate_samples)

    except KeyboardInterrupt:
        stats.uptime_sec += time.monotonic() - conn_on_mono
        _close_connection_quietly(ws)
        return "INTERRUPTED"


def _try_reconnect(
    args: argparse.Namespace,
    stats: ProbeV2Stats,
    websocket_module: Any,
    topics: list[str],
    consecutive_attempt: int,
    reason: str,
) -> tuple[Any, float, float, int] | None:
    """嘗試 reconnect；回傳 (新 ws, 新 conn_on_mono, 新 next_ping, 新 consecutive_attempt)。

    None = 連續 6 attempt 用盡仍 fail，session 該 RESTART。
    """
    # consecutive_attempt 是「呼叫前 attempt 計數」；本次 attempt = consecutive_attempt + 1
    for sub_attempt in range(1, RECONNECT_MAX_ATTEMPTS_PER_SESSION + 1):
        attempt_global = consecutive_attempt + sub_attempt
        if attempt_global > RECONNECT_MAX_ATTEMPTS_PER_SESSION:
            # 安全保護：consecutive_attempt 異常傳入 > 0
            break
        backoff = _backoff_for_attempt(attempt_global)
        time.sleep(backoff)
        stats.reconnect_attempts += 1
        event = ReconnectEvent(
            attempt=attempt_global,
            started_at_utc=_utc_now_iso(),
            backoff_sec=backoff,
            reason=reason,
            success=False,
        )
        try:
            new_ws, keepalive_warn = _open_subscribed_connection(args, topics, websocket_module)
        except Exception as exc:  # noqa: BLE001
            event.error_text = f"{type(exc).__name__}: {exc}"
            stats.reconnect_events.append(event)
            stats.reconnect_failures += 1
            stats.last_reconnect_reason = reason
            # 若這次仍失敗且已達 attempt 6 → 觸 session restart
            if attempt_global >= RECONNECT_MAX_ATTEMPTS_PER_SESSION:
                return None
            continue
        # 成功
        event.success = True
        stats.reconnect_events.append(event)
        stats.reconnect_successes += 1
        stats.last_reconnect_reason = reason
        if keepalive_warn is not None:
            stats.connection_errors.append(f"keepalive_warning_on_reconnect: {keepalive_warn}")
        now = time.monotonic()
        return new_ws, now, now + args.ping_interval_sec, 0

    return None


# ── 中間 verdict 評估（checkpoint 用）────────────────────────────────────

def _interim_verdict(stats: ProbeV2Stats) -> str:
    """checkpoint 時的 interim verdict。"""
    if stats.poison_events:
        return "FAIL_TOPIC_POISON_DETECTED"
    if stats.uptime_ratio < 0.5 and stats.elapsed_sec > 3600:
        return "DEGRADED_UPTIME_LOW"
    if stats.reconnect_failures >= 2:
        return "DEGRADED_RECONNECT_UNSTABLE"
    return "IN_PROGRESS_HEALTHY"


# ── 主 run_probe：含 multi-session restart loop ────────────────────────

def run_probe(args: argparse.Namespace) -> ProbeV2Stats:
    """v2 探針主入口。內含：
        - dependency 檢查（websocket-client）
        - optional UTC midnight 啟動對齊
        - multi-session restart loop（restart 上限 = args.max_restart）
        - 最終 assess() 設 verdict
    """
    # ── websocket-client dependency ──
    try:
        import websocket  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        stats = ProbeV2Stats(
            session_id=args.session_id or f"c1_v2_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            started_at_utc=_utc_now_iso(),
            url=args.url,
            candidate_topic=args.topic,
            control_topics=build_topics(args.topic, args.canary_symbol)[1:],
            target_sec=args.duration_sec,
            max_restart_budget=args.max_restart,
        )
        stats.connection_errors.append(f"websocket-client unavailable: {exc}")
        stats.verdict = "FATAL_DEPENDENCY_MISSING"
        stats.c1_blocker = "Install websocket-client in the runtime environment."
        return stats

    # ── Optional UTC midnight 啟動對齊（design §3.6）──
    if args.start_utc_midnight:
        _wait_until_next_utc_midnight()

    # ── Stats 初始化 ──
    session_id = args.session_id or f"c1_v2_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    topics = build_topics(args.topic, args.canary_symbol)
    stats = ProbeV2Stats(
        session_id=session_id,
        started_at_utc=_utc_now_iso(),
        url=args.url,
        candidate_topic=args.topic,
        control_topics=topics[1:],
        target_sec=args.duration_sec,
        topic_message_counts={topic: 0 for topic in topics},
        max_restart_budget=args.max_restart,
    )

    output_dir = args.output_dir

    # ── Session restart loop（design §3.4）──
    overall_start_mono = time.monotonic()
    # 第一個 session = restart_index 0
    while True:
        session_start_mono = time.monotonic()
        # 預估本 session 應跑時長（剩餘目標時間）
        remaining_target = args.duration_sec - (session_start_mono - overall_start_mono)
        if remaining_target <= 0:
            break
        # 動態調整本 session args.duration_sec 給 _run_session 識別
        original_duration = args.duration_sec
        args.duration_sec = int(remaining_target)

        outcome = _run_session(args, stats, websocket, session_start_mono, output_dir)

        # 還原 args.duration_sec 給後續邏輯
        args.duration_sec = original_duration

        if outcome in ("COMPLETED", "INTERRUPTED"):
            break

        # outcome == "RECONNECT_EXHAUSTED" → 觸 restart
        stats.restart_count += 1
        elapsed = time.monotonic() - overall_start_mono
        restart_event = RestartEvent(
            restart_index=stats.restart_count,
            triggered_at_utc=_utc_now_iso(),
            reason="RECONNECT_EXHAUSTED",
            elapsed_sec_at_trigger=elapsed,
            uptime_sec_at_trigger=stats.uptime_sec,
        )
        stats.restart_events.append(restart_event)

        if stats.restart_count > args.max_restart:
            # restart budget 用盡
            stats.connection_errors.append(
                f"restart_budget_exhausted: count={stats.restart_count} > max={args.max_restart}"
            )
            break

        # 暫停 60s 再 restart（design §3.4）
        time.sleep(60)

    # ── 最終 stats 收尾 ──
    stats.elapsed_sec = time.monotonic() - overall_start_mono
    stats.uptime_ratio = (
        stats.uptime_sec / stats.elapsed_sec if stats.elapsed_sec > 0 else 0.0
    )
    stats.finished_at_utc = _utc_now_iso()
    assess(stats, args)
    # 最終 checkpoint flush（覆寫進度檔，方便 BB sign-off 走同檔）
    _write_checkpoint(stats, output_dir)
    return stats


def _wait_until_next_utc_midnight() -> None:
    """阻塞直到下一個 UTC 00:00:00 + 30s buffer（design §3.6）。"""
    while True:
        now = datetime.now(timezone.utc)
        # 已過午夜且在 30s buffer 內 → 直接開始
        if now.hour == 0 and now.minute == 0 and now.second <= 30:
            time.sleep(max(0, 30 - now.second))
            return
        # 距下次 midnight 還多久
        next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if next_midnight <= now:
            # 加一天
            from datetime import timedelta
            next_midnight = next_midnight + timedelta(days=1)
        wait_sec = (next_midnight - now).total_seconds()
        # 大 sleep 切片 30s；避免 OS-level 長 sleep 不可中斷
        time.sleep(min(wait_sec, 30))


# ── 最終 verdict assessment ──────────────────────────────────────────────

def assess(stats: ProbeV2Stats, args: argparse.Namespace) -> None:
    """設置 stats.verdict + c1_proof_eligible + c1_blocker。

    v2 PASS gate（design §3.5）：
        - observed_sec ≥ args.proof_min_duration_sec（預設 23h）
        - uptime_ratio ≥ args.proof_min_uptime_ratio（預設 0.95）
        - 0 poison_events
        - ≥ 3 control topics seen
        - restart_count ≤ args.max_restart
    """
    stats.c1_proof_eligible = (
        stats.elapsed_sec >= args.proof_min_duration_sec
        and stats.uptime_ratio >= args.proof_min_uptime_ratio
    )

    # 優先序：poison > restart budget > reconnect exhausted > canary silent > smoke
    if stats.poison_events:
        stats.verdict = "FAIL_TOPIC_POISON"
        stats.c1_blocker = "Bybit returned a poison/rejection/rate-limit message."
        return

    if stats.restart_count > args.max_restart:
        stats.verdict = "FAIL_RESTART_BUDGET_EXHAUSTED"
        stats.c1_blocker = (
            f"Session restart budget exhausted: {stats.restart_count} > {args.max_restart}."
        )
        return

    # reconnect exhausted 但未達 restart budget = 中斷 + 未跑滿
    if (
        stats.connection_errors
        and stats.elapsed_sec < args.proof_min_duration_sec
        and not stats.c1_proof_eligible
    ):
        # 區分 v1-style「無 reconnect」與「reconnect 嘗試但用盡」
        if not args.enable_reconnect:
            stats.verdict = "FAIL_CONNECTION"
            stats.c1_blocker = "The isolated WS connection did not complete the requested window (no reconnect)."
        else:
            stats.verdict = "FAIL_RECONNECT_EXHAUSTED"
            stats.c1_blocker = (
                "Reconnect attempts exhausted before reaching proof window."
            )
        return

    # Control topic 觀察
    control_seen = {
        topic: stats.topic_message_counts.get(topic, 0) > 0 for topic in stats.control_topics
    }
    control_alive_count = sum(1 for seen in control_seen.values() if seen)
    any_control_seen = control_alive_count > 0

    # 24h proof 通過邏輯（v2 = ≥3 control alive，design §3.5）
    if stats.c1_proof_eligible:
        if control_alive_count < 3:
            stats.verdict = "FAIL_CANARY_SILENT"
            missing = [topic for topic, seen in control_seen.items() if not seen]
            stats.c1_blocker = (
                f"Control topics silent during proof window: alive={control_alive_count}/4 missing={missing}"
            )
            return
        stats.verdict = "PASS_C1_PROOF_CANDIDATE"
        stats.c1_blocker = None
        return

    # 未達 proof 時長 → smoke 路徑
    if not any_control_seen:
        stats.verdict = "FAIL_SMOKE_CANARY_SILENT"
        stats.c1_blocker = "Short smoke saw no control-market data."
        return

    stats.verdict = "SMOKE_PASS_NOT_C1_PROOF"
    stats.c1_blocker = (
        f"Duration {stats.elapsed_sec:.0f}s < required {args.proof_min_duration_sec}s; keep C1 blocked until full proof."
    )


# ── Markdown / JSON 報告渲染 ─────────────────────────────────────────────

def render_markdown(stats: ProbeV2Stats) -> str:
    """渲染 Markdown 摘要報告；BB / MIT sign-off 用。"""
    result = asdict(stats)
    lines = [
        "# Bybit Liquidation Topic Probe v2",
        "",
        f"- Session ID: `{stats.session_id}`",
        f"- Generated: `{_utc_now_iso()}`",
        f"- Verdict: `{stats.verdict}`",
        f"- C1 proof eligible: `{stats.c1_proof_eligible}`",
        f"- C1 blocker: `{stats.c1_blocker or 'none'}`",
        f"- URL: `{stats.url}`",
        f"- Candidate topic: `{stats.candidate_topic}`",
        f"- Official docs: {OFFICIAL_DOC_URL}",
        f"- Target sec: `{stats.target_sec}`",
        f"- Observed elapsed sec: `{stats.elapsed_sec:.1f}`",
        f"- Cumulative uptime sec: `{stats.uptime_sec:.1f}`",
        f"- Uptime ratio: `{stats.uptime_ratio:.4f}`",
        f"- Reconnect attempts / success / failure: `{stats.reconnect_attempts}` / `{stats.reconnect_successes}` / `{stats.reconnect_failures}`",
        f"- Restart count / budget: `{stats.restart_count}` / `{stats.max_restart_budget}`",
        f"- Subscribe success/failure: `{stats.subscribe_success_count}` / `{stats.subscribe_failure_count}`",
        f"- Ping/pong: `{stats.pings_sent}` / `{stats.pongs_seen}`",
        f"- Candidate messages seen: `{stats.candidate_messages_seen}`",
        "",
        "## Topic Counts",
        "",
        "| Topic | Count | Last seen UTC |",
        "|---|---:|---|",
    ]
    for topic, count in sorted(stats.topic_message_counts.items()):
        last_seen = stats.last_seen_by_topic_utc.get(topic, "")
        lines.append(f"| `{topic}` | {count} | `{last_seen}` |")

    if stats.reconnect_events:
        lines.extend(["", "## Reconnect Events (last 20)", "", "| Attempt | UTC | Backoff(s) | Reason | Success | Error |", "|---:|---|---:|---|---|---|"])
        for ev in stats.reconnect_events[-20:]:
            err = (ev.error_text or "").replace("|", "\\|")
            lines.append(
                f"| {ev.attempt} | `{ev.started_at_utc}` | {ev.backoff_sec:.1f} | {ev.reason} | {ev.success} | `{err[:120]}` |"
            )

    if stats.restart_events:
        lines.extend(["", "## Restart Events", "", "| Index | UTC | Reason | Elapsed(s) | Uptime(s) |", "|---:|---|---|---:|---:|"])
        for re_ev in stats.restart_events:
            lines.append(
                f"| {re_ev.restart_index} | `{re_ev.triggered_at_utc}` | {re_ev.reason} | {re_ev.elapsed_sec_at_trigger:.1f} | {re_ev.uptime_sec_at_trigger:.1f} |"
            )

    if stats.poison_events:
        lines.extend(["", "## Poison Events (first 10)", ""])
        for event in stats.poison_events[:10]:
            lines.append(f"- `{event}`")

    if stats.connection_errors:
        lines.extend(["", "## Connection Errors (last 20)", ""])
        for err in stats.connection_errors[-20:]:
            lines.append(f"- `{err}`")

    if stats.candidate_samples:
        lines.extend(["", f"## Candidate Samples (count={len(stats.candidate_samples)})", "", "```json"])
        lines.append(json.dumps(stats.candidate_samples, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")

    lines.extend(["", "## Raw JSON", "", "```json"])
    lines.append(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    return "\n".join(lines) + "\n"


def write_reports(stats: ProbeV2Stats, output_dir: Path) -> tuple[Path, Path]:
    """寫入 latest + dated JSON + MD 報告；回傳 (latest_md_path, dated_md_path)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    latest_json = output_dir / "liquidation_topic_probe_v2_latest.json"
    dated_json = output_dir / f"liquidation_topic_probe_v2_{stamp}.json"
    latest_md = output_dir / "liquidation_topic_probe_v2_latest.md"
    dated_md = output_dir / f"liquidation_topic_probe_v2_{stamp}.md"

    payload = json.dumps(asdict(stats), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(stats)
    for path in (latest_json, dated_json):
        path.write_text(payload, encoding="utf-8")
    for path in (latest_md, dated_md):
        path.write_text(markdown, encoding="utf-8")
    return latest_md, dated_md


# ── Main entrypoint ─────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    """v2 探針 CLI 入口。"""
    args = parse_args(argv)
    topics = build_topics(args.topic, args.canary_symbol)

    if args.dry_run:
        # Dry-run：印 plan 不開連線
        plan = {
            "url": args.url,
            "candidate_topic": args.topic,
            "control_topics": topics[1:],
            "duration_sec": args.duration_sec,
            "ping_interval_sec": args.ping_interval_sec,
            "enable_reconnect": args.enable_reconnect,
            "max_restart": args.max_restart,
            "checkpoint_interval_sec": args.checkpoint_interval_sec,
            "start_utc_midnight": args.start_utc_midnight,
            "session_id": args.session_id or "(auto-generated at run time)",
            "proof_min_duration_sec": args.proof_min_duration_sec,
            "proof_min_uptime_ratio": args.proof_min_uptime_ratio,
            "official_doc_url": OFFICIAL_DOC_URL,
            "note": "dry-run only; no WS connection opened",
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    stats = run_probe(args)
    latest_md, dated_md = write_reports(stats, args.output_dir)
    print(f"verdict={stats.verdict}")
    print(f"session_id={stats.session_id}")
    print(f"latest_report={latest_md}")
    print(f"dated_report={dated_md}")
    print(f"checkpoint={args.output_dir / CHECKPOINT_FILE_NAME}")

    # Exit code mapping
    if stats.verdict.startswith("PASS") or stats.verdict.startswith("SMOKE_PASS"):
        return 0
    if stats.verdict.startswith("FATAL"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
