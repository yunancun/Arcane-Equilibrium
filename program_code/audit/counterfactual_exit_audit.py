"""
Counterfactual Exit Audit — DUAL-TRACK-EXIT-1 Track P T5.
反事實退場審計 — DUAL-TRACK-EXIT-1 Track P T5。

MODULE_NOTE (EN): Reads closed positions from trading.fills + 1-min bars from
  market.klines, reconstructs the peak-to-exit trajectory, and simulates how
  Track P physical-optimum exit rules would have decided. Per-position delta
  (counterfactual vs real exit) is reported in bps. Results are a **lower
  bound on improvement** — 1-min granularity coarsens intra-bar spikes,
  the audit is post-hoc (no look-ahead but over-fitted by definition), and
  liquidity/slippage at the counterfactual lock moment is unmodelled. If
  market.klines is stale (> 24h) the audit degrades to fills-only mode
  (delta_bps=None, phys_reason="klines_stale_fallback").
MODULE_NOTE (中): 從 trading.fills 讀已平倉位 + market.klines 讀 1-min K 線，
  還原 peak-to-exit 軌跡，模擬 Track P 物理最優退場規則當時如何決策；逐倉位
  輸出 delta（反事實 vs 真實退場）bps。結論屬改進下界（1-min 粒度平滑 spike、
  事後歸因、未建模流動性/滑價）。market.klines 陳舊 (> 24h) 則降級為
  fills-only（delta_bps=None, phys_reason="klines_stale_fallback"）。

Usage / 使用:
    python -m program_code.audit.counterfactual_exit_audit \\
        --days 7 --strategy grid_trading --engine-mode demo \\
        --out /tmp/cf_audit_phys_lock.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Track P physical-lock rule defaults (conservative; calibrated by replay later)
# Track P 物理鎖倉規則預設值（保守；以後由 replay 校準）
# ---------------------------------------------------------------------------

# Minimum net edge floor (bps) below which we never evaluate a lock.
# 淨利底線（bps），低於此線不評估鎖倉。
_DEFAULT_MIN_NET_FLOOR_BPS: float = 10.0

# Minimum hold time (secs) before micro-profit lock considered (signal-dev grace).
# 微利鎖最短持倉秒數（給訊號發展期寬容）。
_DEFAULT_MIN_HOLD_SECS: int = 60

# Minimum peak_pnl_pct / atr_pct — don't lock tiny peaks that are likely noise.
# 最小 peak_pnl_pct / atr_pct — 不鎖可能是噪音的小峰值。
_DEFAULT_MIN_PEAK_ATR_NORM: float = 0.5

# Giveback threshold in ATR units (peak→current retracement ÷ atr_pct).
# giveback 閾值（ATR 單位）(peak→current 回吐 ÷ atr_pct)。
_DEFAULT_GIVEBACK_ATR_THRESHOLD: float = 0.6

# Secondary rule: "peak is stale and price is decaying" trigger.
# 次要規則：「峰值陳舊且價格下行」觸發器。
_DEFAULT_STALE_PEAK_MS: int = 90_000           # 90 sec

# ATR fallback when we cannot compute 1-min ATR from klines.
# 無法從 klines 計算 1-min ATR 時的 fallback。
_ATR_FALLBACK_PCT: float = 1.0

# Stale-kline guard threshold (24h in secs). If freshest kline is older,
# fall back to fills-only audit (no counterfactual).
# klines 陳舊守衛門檻（24h 秒數）。最新 kline 超過此時間則降為 fills-only。
_KLINE_STALE_THRESHOLD_SECS: int = 24 * 3600

# ATR lookback window (minutes) used when we do have klines.
# 有 klines 時用來計算 ATR 的回望窗口（分鐘）。
_ATR_LOOKBACK_MIN: int = 14


# ---------------------------------------------------------------------------
# Dataclasses / 資料類
# ---------------------------------------------------------------------------


@dataclass
class PhysLockConfig:
    """Track P physical lock rule thresholds.
    Track P 物理鎖倉規則門檻。
    """
    min_net_floor_bps: float = _DEFAULT_MIN_NET_FLOOR_BPS
    min_hold_secs: int = _DEFAULT_MIN_HOLD_SECS
    min_peak_atr_norm: float = _DEFAULT_MIN_PEAK_ATR_NORM
    giveback_atr_threshold: float = _DEFAULT_GIVEBACK_ATR_THRESHOLD
    stale_peak_ms: int = _DEFAULT_STALE_PEAK_MS
    atr_fallback_pct: float = _ATR_FALLBACK_PCT


@dataclass
class Position:
    """One closed position (entry + exit) to audit.
    一筆已平倉位（入場 + 出場）供審計。
    """
    strategy: str
    symbol: str
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    qty: float
    side: str                          # 'Buy' (long) | 'Sell' (short)
    entry_context_id: Optional[str]    # None => unpaired; audit will skip with warning


@dataclass
class KlineBar:
    """1-min OHLC bar.
    1-min OHLC K 線。
    """
    ts: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class PhysLockDecision:
    """Outcome of simulating Track P on one position.
    對一筆倉位模擬 Track P 的結果。
    """
    phys_rule_hit: bool                     # whether Track P would have locked
    phys_reason: str                        # human-readable reason
    cf_exit_ts: Optional[datetime]          # counterfactual exit timestamp
    cf_exit_price: Optional[float]          # counterfactual exit price


@dataclass
class AuditRecord:
    """Per-position audit record (serialised to JSON).
    逐倉位審計記錄（序列化為 JSON）。
    """
    strategy: str
    symbol: str
    entry_ts: str                           # ISO8601
    exit_ts: str                            # ISO8601
    real_exit_pnl_pct: float                # realised return (%, signed)
    cf_phys_exit_pnl_pct: Optional[float]   # counterfactual return (%) or None
    delta_bps: Optional[float]              # (cf - real) * 10000 in % → bps; None if fallback
    phys_rule_hit: bool
    phys_reason: str


# ---------------------------------------------------------------------------
# Database helpers (lazy psycopg2 import so tests never hit it)
# 資料庫輔助（延遲 import psycopg2；測試永遠不走這層）
# ---------------------------------------------------------------------------


def _get_db_conn() -> Any:
    """Open a psycopg2 connection using env vars. Raises on failure.
    使用環境變數建立 psycopg2 連接；失敗即 raise。

    Respects OPENCLAW_BASE_DIR-agnostic env conventions used elsewhere.
    與專案其他模組共用的環境變數慣例，無硬編碼路徑。
    """
    import psycopg2  # type: ignore[import]

    host = os.environ.get("PG_HOST", "127.0.0.1")
    port = int(os.environ.get("PG_PORT", "5432"))
    dbname = os.environ.get("PG_DB", "trading_ai")
    user = os.environ.get("PG_USER", "trading_admin")
    # Prefer PG_PASSWORD (realized_edge_stats.py convention) else PG_PASS (db_pool).
    password = os.environ.get("PG_PASSWORD") or os.environ.get("PG_PASS") or ""

    return psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        connect_timeout=5,
    )


# ---------------------------------------------------------------------------
# Exit-fill detection (consistent with realized_edge_stats.py) /
# 出場成交判斷（與 realized_edge_stats.py 一致）
# ---------------------------------------------------------------------------


def _is_exit_fill(strategy_name: str, realized_pnl: float) -> bool:
    """Return True when a fill row represents a position close.
    判斷一筆 fill 是否為平倉成交。

    Mirrors the heuristic in ml_training.realized_edge_stats._pair_round_trips:
    close if realized_pnl != 0 OR strategy_name is a known close-tag prefix.
    與 ml_training.realized_edge_stats._pair_round_trips 的啟發一致。
    """
    if realized_pnl != 0.0:
        return True
    name = strategy_name or ""
    return (
        name.startswith("risk_close")
        or name.startswith("stop_trigger")
        or name.startswith("strategy_close")
        or name.startswith("stop_")
        or name.startswith("time_stop")
    )


# ---------------------------------------------------------------------------
# Fills → position pairing / Fills → 倉位配對
# ---------------------------------------------------------------------------


def pair_fills_to_positions(
    fills: list[dict],
    *,
    strategy_filter: str,
    unpaired_warn: Optional[Callable[[str], None]] = None,
) -> list[Position]:
    """Pair entry+exit fills by entry_context_id into Positions.
    透過 entry_context_id 將入場+出場 fill 配對成 Position 列表。

    Contract (strict form): exit fill has non-null entry_context_id that
    matches the same-symbol entry fill's context_id. If entry_context_id is
    NULL on an exit row we emit a warning and skip the pair (a known bybit_sync
    shadow-path artefact; no counterfactual judgement possible).
    合約（嚴格版）：exit fill 的 entry_context_id 非空且對應到同 symbol 的
    entry fill 的 context_id。exit 的 entry_context_id 為 NULL 時發 warning
    並 skip（bybit_sync 影子路徑舊物，無從做反事實判斷）。
    """
    warn_fn = unpaired_warn or (lambda msg: logger.warning(msg))

    # Index entry fills by (symbol, context_id). Strategy filter applies only
    # to ENTRY rows — exit rows carry close-tag strategy names (e.g.
    # "strategy_close:tp") that never match the owner strategy; filtering here
    # would drop every pair.
    # 依 (symbol, context_id) 索引 entry fills。策略過濾只套用於 entry 行 —
    # exit 行帶 close-tag 名稱（如 "strategy_close:tp"），永遠不等於 owner
    # strategy；在此過濾會把每組 pair 都丟掉。
    entry_by_cid: dict[tuple[str, str], dict] = {}
    exits: list[dict] = []

    for fill in fills:
        sname = fill.get("strategy_name") or ""
        realized = float(fill.get("realized_pnl") or 0.0)
        if _is_exit_fill(sname, realized):
            exits.append(fill)
        else:
            # Apply strategy filter to entries only.
            # 策略過濾只套用於 entry。
            if strategy_filter and sname != strategy_filter:
                continue
            ctx = fill.get("context_id")
            if ctx:
                entry_by_cid[(fill["symbol"], ctx)] = fill

    positions: list[Position] = []
    for exit_fill in exits:
        ectx = exit_fill.get("entry_context_id")
        if not ectx:
            warn_fn(
                f"UNPAIRED exit fill (no entry_context_id): symbol={exit_fill.get('symbol')} "
                f"ts={exit_fill.get('ts')} strategy={exit_fill.get('strategy_name')} — skipping"
            )
            continue
        entry = entry_by_cid.get((exit_fill["symbol"], ectx))
        if entry is None:
            warn_fn(
                f"UNPAIRED exit fill (no matching entry): symbol={exit_fill.get('symbol')} "
                f"entry_context_id={ectx} — skipping"
            )
            continue

        # Side semantics: entry fill side determines long vs short.
        # side 語意：入場成交 side 決定多空。
        side = entry["side"]
        positions.append(
            Position(
                strategy=entry["strategy_name"],
                symbol=entry["symbol"],
                entry_ts=_as_utc(entry["ts"]),
                exit_ts=_as_utc(exit_fill["ts"]),
                entry_price=float(entry["price"]),
                exit_price=float(exit_fill["price"]),
                qty=float(entry["qty"]),
                side=side,
                entry_context_id=ectx,
            )
        )
    return positions


def _as_utc(ts: Any) -> datetime:
    """Coerce a timestamp to an aware UTC datetime. / 轉為帶時區的 UTC datetime。"""
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    raise TypeError(f"Unsupported timestamp type: {type(ts)}")


# ---------------------------------------------------------------------------
# Peak / ATR reconstruction from klines / 從 klines 還原 peak + ATR
# ---------------------------------------------------------------------------


def compute_peak(
    position: Position,
    bars: list[KlineBar],
) -> tuple[Optional[datetime], Optional[float]]:
    """(peak_ts, peak_price) for a position's favourable extreme.
    回傳倉位最有利極值的 (peak_ts, peak_price)。Long→argmax high, Short→argmin low.
    Bars outside [entry_ts, exit_ts] ignored. [entry_ts, exit_ts] 外忽略。
    """
    in_window = [b for b in bars if position.entry_ts <= b.ts <= position.exit_ts]
    if not in_window:
        return None, None
    if position.side.lower() == "buy":
        best = max(in_window, key=lambda b: b.high)
        return best.ts, best.high
    best = min(in_window, key=lambda b: b.low)
    return best.ts, best.low


def compute_atr_pct(bars: list[KlineBar], lookback: int = _ATR_LOOKBACK_MIN) -> float:
    """Simple ATR% approximation over last `lookback` 1-min bars.
    簡化版 ATR%（非 Wilder）：窗內 mean((high-low)/close) × 100。空 → 0.0。
    """
    if not bars:
        return 0.0
    ranges = [(b.high - b.low) / b.close for b in bars[-lookback:] if b.close > 0]
    if not ranges:
        return 0.0
    return sum(ranges) / len(ranges) * 100.0


# ---------------------------------------------------------------------------
# Track P rule simulation / Track P 規則模擬
# ---------------------------------------------------------------------------


def simulate_phys_lock(
    position: Position,
    bars: list[KlineBar],
    cfg: PhysLockConfig,
    *,
    fee_rate_bps: float = 10.0,
) -> PhysLockDecision:
    """Simulate whether Track P would have locked before real exit (design §三).
    模擬 Track P 是否會在真實退場前鎖倉（design §三）。

    Walks 1-min bars forward; per bar evaluates 4 gates (net floor, min hold,
    peak/ATR, giveback-or-stale-decay) and returns the first lock event.
    從入場向前走 1-min bar；每根 bar 評估 4 個 gate（淨利底線、最短持倉、
    峰值/ATR、giveback 或 peak 陳舊+衰減），回傳最早觸發事件。
    """
    window = [b for b in bars if position.entry_ts <= b.ts <= position.exit_ts]
    if not window:
        return PhysLockDecision(False, "no_klines_in_window", None, None)

    atr_pct = compute_atr_pct(window) or cfg.atr_fallback_pct
    is_long = position.side.lower() == "buy"
    peak_price = position.entry_price
    peak_ts = position.entry_ts
    prev_close: Optional[float] = None

    for b in window:
        # Update peak BEFORE gates (intra-bar optimism: extreme replaces prior
        # peak only when it improves it). 先更新 peak 再評估 gate。
        if is_long:
            if b.high > peak_price:
                peak_price, peak_ts = b.high, b.ts
            current_price = b.close
            pnl_pct = (current_price - position.entry_price) / position.entry_price * 100.0
            peak_pnl_pct = (peak_price - position.entry_price) / position.entry_price * 100.0
            giveback_pct = (peak_price - current_price) / position.entry_price * 100.0
        else:
            if b.low < peak_price:
                peak_price, peak_ts = b.low, b.ts
            current_price = b.close
            pnl_pct = (position.entry_price - current_price) / position.entry_price * 100.0
            peak_pnl_pct = (position.entry_price - peak_price) / position.entry_price * 100.0
            giveback_pct = (current_price - peak_price) / position.entry_price * 100.0

        # Net bps after both-side fees. 扣雙邊手續費後的淨 bps。
        est_net_bps = pnl_pct * 100.0 - 2.0 * fee_rate_bps

        # Gate 1 — net edge floor
        if est_net_bps <= cfg.min_net_floor_bps:
            prev_close = current_price
            continue

        # Gate 2 — min hold
        entry_age_secs = (b.ts - position.entry_ts).total_seconds()
        if entry_age_secs < cfg.min_hold_secs:
            prev_close = current_price
            continue

        # Gate 3 — peak height (ATR normalised)
        if atr_pct <= 0:
            atr_pct = cfg.atr_fallback_pct
        peak_atr_norm = peak_pnl_pct / atr_pct
        if peak_atr_norm < cfg.min_peak_atr_norm:
            prev_close = current_price
            continue

        # Gate 4 — giveback OR (stale peak + decaying roc)
        giveback_atr_norm = giveback_pct / atr_pct if atr_pct > 0 else 0.0
        giveback_triggered = giveback_atr_norm >= cfg.giveback_atr_threshold

        time_since_peak_ms = int((b.ts - peak_ts).total_seconds() * 1000)
        price_roc_short = 0.0
        if prev_close is not None and prev_close > 0:
            price_roc_short = (current_price - prev_close) / prev_close
        stale_and_decaying = (
            time_since_peak_ms >= cfg.stale_peak_ms and price_roc_short < 0.0
        )

        if giveback_triggered or stale_and_decaying:
            reason = (
                f"PHYS-LOCK: net={est_net_bps:.1f}bps peak={peak_pnl_pct:.2f}% "
                f"giveback_atr={giveback_atr_norm:.2f} age_s={int(entry_age_secs)} "
                f"roc={price_roc_short:.4f} "
                f"{'giveback' if giveback_triggered else 'stale_decay'}"
            )
            return PhysLockDecision(True, reason, b.ts, current_price)

        prev_close = current_price

    return PhysLockDecision(False, "no_gate_4_trigger_in_window", None, None)


# ---------------------------------------------------------------------------
# Position → AuditRecord / 倉位轉審計記錄
# ---------------------------------------------------------------------------


def compute_real_pnl_pct(position: Position) -> float:
    """Signed realised return of a position, in %.
    倉位的真實有符號收益，%。
    """
    if position.entry_price <= 0:
        return 0.0
    if position.side.lower() == "buy":
        return (position.exit_price - position.entry_price) / position.entry_price * 100.0
    else:
        return (position.entry_price - position.exit_price) / position.entry_price * 100.0


def audit_position(
    position: Position,
    bars: list[KlineBar],
    cfg: PhysLockConfig,
    *,
    kline_fresh: bool,
    fee_rate_bps: float = 10.0,
) -> AuditRecord:
    """Produce an AuditRecord for one position.
    為一筆倉位產出 AuditRecord。

    When kline_fresh is False we emit a fills-only record (delta_bps=None,
    phys_reason="klines_stale_fallback") so callers can still count positions.
    kline_fresh 為 False 時輸出 fills-only 記錄（delta_bps=None），供 caller
    仍可計數倉位。
    """
    real_pct = compute_real_pnl_pct(position)
    base = AuditRecord(
        strategy=position.strategy,
        symbol=position.symbol,
        entry_ts=position.entry_ts.isoformat(),
        exit_ts=position.exit_ts.isoformat(),
        real_exit_pnl_pct=real_pct,
        cf_phys_exit_pnl_pct=None,
        delta_bps=None,
        phys_rule_hit=False,
        phys_reason="",
    )

    if not kline_fresh:
        base.phys_reason = "klines_stale_fallback"
        return base

    decision = simulate_phys_lock(position, bars, cfg, fee_rate_bps=fee_rate_bps)
    base.phys_rule_hit = decision.phys_rule_hit
    base.phys_reason = decision.phys_reason

    if decision.phys_rule_hit and decision.cf_exit_price is not None:
        if position.side.lower() == "buy":
            cf_pct = (
                (decision.cf_exit_price - position.entry_price) / position.entry_price * 100.0
            )
        else:
            cf_pct = (
                (position.entry_price - decision.cf_exit_price) / position.entry_price * 100.0
            )
        base.cf_phys_exit_pnl_pct = cf_pct
        # delta_bps = (cf_pct - real_pct) * 100 (1 pct = 100 bps)
        base.delta_bps = (cf_pct - real_pct) * 100.0
    return base


# ---------------------------------------------------------------------------
# Summary statistics / 彙總統計
# ---------------------------------------------------------------------------


def summarise(records: list[AuditRecord]) -> dict:
    """Compute aggregate summary over a list of AuditRecord.
    對 AuditRecord 列表計算聚合摘要。
    """
    deltas: list[float] = [r.delta_bps for r in records if r.delta_bps is not None]
    n_hit = sum(1 for r in records if r.phys_rule_hit)
    n_better = sum(1 for d in deltas if d > 0)
    n_worse = sum(1 for d in deltas if d < 0)

    def _pct(arr: list[float], q: float) -> Optional[float]:
        if not arr:
            return None
        s = sorted(arr)
        k = max(0, min(len(s) - 1, int(round((len(s) - 1) * q))))
        return s[k]

    mean_delta = sum(deltas) / len(deltas) if deltas else None
    return {
        "delta_bps_mean": mean_delta,
        "delta_bps_p50": _pct(deltas, 0.5),
        "delta_bps_p25": _pct(deltas, 0.25),
        "delta_bps_p75": _pct(deltas, 0.75),
        "n_phys_would_lock": n_hit,
        "n_phys_better": n_better,
        "n_phys_worse": n_worse,
        "n_positions_with_delta": len(deltas),
    }


# ---------------------------------------------------------------------------
# Kline freshness guard / Klines 新鮮度守衛
# ---------------------------------------------------------------------------


def check_kline_freshness(
    latest_kline_ts: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    threshold_secs: int = _KLINE_STALE_THRESHOLD_SECS,
) -> bool:
    """Return True iff the freshest kline is within `threshold_secs` of `now`.
    最新 kline 在 `threshold_secs` 內則回 True。

    Used to degrade the audit to fills-only mode when MARKET-KLINES-STALE-1 is
    active. `now` is injectable for tests.
    當 MARKET-KLINES-STALE-1 仍在作用時用來降級為 fills-only；`now` 可於測試注入。
    """
    if latest_kline_ts is None:
        return False
    current = now or datetime.now(timezone.utc)
    if latest_kline_ts.tzinfo is None:
        latest_kline_ts = latest_kline_ts.replace(tzinfo=timezone.utc)
    age = (current - latest_kline_ts).total_seconds()
    return age <= threshold_secs


# ---------------------------------------------------------------------------
# DB-backed loaders (skipped by tests via dependency injection)
# DB 讀取（測試用注入避開）
# ---------------------------------------------------------------------------


_FILLS_QUERY = """
SELECT
    f.ts,
    f.symbol,
    COALESCE(f.strategy_name, 'unknown') AS strategy_name,
    f.side,
    f.qty,
    f.price,
    f.fee,
    f.realized_pnl,
    f.engine_mode,
    f.context_id,
    f.entry_context_id
FROM trading.fills f
WHERE f.ts >= %(since)s
  AND f.engine_mode = %(engine_mode)s
ORDER BY f.symbol, f.ts ASC
"""


_KLINES_QUERY = """
SELECT ts, open, high, low, close
FROM market.klines
WHERE symbol = %(symbol)s
  AND timeframe = '1m'
  AND ts >= %(start_ts)s
  AND ts <= %(end_ts)s
ORDER BY ts ASC
"""


_LATEST_KLINE_QUERY = """
SELECT MAX(ts) AS latest_ts
FROM market.klines
WHERE timeframe = '1m'
"""


def fetch_fills(conn: Any, days: int, engine_mode: str) -> list[dict]:
    """Load fills for last `days` days of `engine_mode`. / 讀 `days` 天 fills。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with conn.cursor() as cur:
        cur.execute(_FILLS_QUERY, {"since": since, "engine_mode": engine_mode})
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows]


def fetch_klines(
    conn: Any, symbol: str, start_ts: datetime, end_ts: datetime,
) -> list[KlineBar]:
    """Load 1-min klines in (start_ts, end_ts) for `symbol`. / 讀 1-min K 線。"""
    with conn.cursor() as cur:
        cur.execute(_KLINES_QUERY, {"symbol": symbol, "start_ts": start_ts, "end_ts": end_ts})
        rows = cur.fetchall()
    return [KlineBar(ts=_as_utc(r[0]), open=float(r[1]), high=float(r[2]),
                     low=float(r[3]), close=float(r[4])) for r in rows]


def fetch_latest_kline_ts(conn: Any) -> Optional[datetime]:
    """Most recent 1-min kline ts (any symbol) or None. / 任一 symbol 最新 1-min ts。"""
    with conn.cursor() as cur:
        cur.execute(_LATEST_KLINE_QUERY)
        row = cur.fetchone()
    return _as_utc(row[0]) if row and row[0] is not None else None


# ---------------------------------------------------------------------------
# Orchestration / 主流程
# ---------------------------------------------------------------------------


def run_audit(
    *,
    days: int,
    strategy: str,
    engine_mode: str,
    cfg: Optional[PhysLockConfig] = None,
    conn_factory: Callable[[], Any] = _get_db_conn,
    now: Optional[datetime] = None,
) -> dict:
    """Core audit entry point (library-usable; CLI wraps this).
    核心審計入口（可作為 library 使用；CLI 包裝此函式）。
    """
    cfg = cfg or PhysLockConfig()
    now_utc = now or datetime.now(timezone.utc)

    conn = conn_factory()
    try:
        latest_kline_ts = fetch_latest_kline_ts(conn)
        kline_fresh = check_kline_freshness(latest_kline_ts, now=now_utc)
        if not kline_fresh:
            logger.warning(
                "WARNING: market.klines latest ts=%s is stale (> 24h old). "
                "Degrading to fills-only audit (delta_bps=None). "
                "警告：market.klines 最新 ts=%s 已陳舊（超過 24h），降級為 fills-only 審計。",
                latest_kline_ts, latest_kline_ts,
            )

        fills = fetch_fills(conn, days, engine_mode)
        positions = pair_fills_to_positions(fills, strategy_filter=strategy)

        records: list[AuditRecord] = []
        for p in positions:
            if kline_fresh:
                bars = fetch_klines(conn, p.symbol, p.entry_ts, p.exit_ts)
            else:
                bars = []
            records.append(
                audit_position(p, bars, cfg, kline_fresh=kline_fresh)
            )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return _assemble_output(
        records,
        mode="counterfactual" if kline_fresh else "fills_only",
        kline_fresh=kline_fresh,
    )


def _assemble_output(
    records: list[AuditRecord],
    *,
    mode: str,
    kline_fresh: bool,
) -> dict:
    """Assemble the final JSON output dict (pure, easy to test).
    組裝最終 JSON 輸出（純函式，易測）。
    """
    return {
        "meta": {
            "mode": mode,
            "kline_fresh": kline_fresh,
            "n_positions": len(records),
            "n_phys_would_lock": sum(1 for r in records if r.phys_rule_hit),
            "note": (
                "lower bound on improvement: 1-min granularity + post-hoc replay "
                "+ unmodeled liquidity/slippage. 結論為改進下界：1-min 粒度 + 事後重播 "
                "+ 未建模的流動性/滑價。"
            ),
        },
        "summary": summarise(records),
        "records": [asdict(r) for r in records],
    }


# ---------------------------------------------------------------------------
# CLI entry / CLI 入口
# ---------------------------------------------------------------------------


def _default_base_dir() -> str:
    """Resolve OPENCLAW_BASE_DIR (or fall back to repo root).
    解析 OPENCLAW_BASE_DIR（否則 fallback 到 repo 根目錄）。
    """
    base = os.environ.get("OPENCLAW_BASE_DIR")
    if base:
        return base
    # program_code/audit/counterfactual_exit_audit.py → repo root is parents[2].
    return str(Path(__file__).resolve().parents[2])


def _build_argparser() -> argparse.ArgumentParser:
    """Construct the argparse parser.
    建立 argparse 解析器。
    """
    p = argparse.ArgumentParser(
        description="Track P counterfactual exit audit (DUAL-TRACK-EXIT-1 T5)",
    )
    p.add_argument("--days", type=int, default=7,
                   help="Lookback window in days / 回看天數")
    p.add_argument("--strategy", type=str, required=True,
                   help="owner_strategy (== fills.strategy_name) to audit / 要審計的策略名")
    p.add_argument(
        "--engine-mode", dest="engine_mode", type=str, default="demo",
        choices=("paper", "demo", "live_demo", "live"),
        help="engine_mode filter / engine_mode 過濾",
    )
    p.add_argument(
        "--out", type=str,
        default=None,
        help="JSON output path (default: $OPENCLAW_BASE_DIR/cf_audit_phys_lock.json)",
    )
    p.add_argument("--log-level", type=str, default="INFO",
                   choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return p


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. Returns the process exit code.
    CLI 入口；回傳 process exit code。
    """
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    out_path = args.out or os.path.join(_default_base_dir(), "cf_audit_phys_lock.json")

    try:
        output = run_audit(
            days=args.days,
            strategy=args.strategy,
            engine_mode=args.engine_mode,
        )
    except Exception as exc:
        logger.error("Audit failed: %s", exc, exc_info=True)
        return 2

    # Atomic write to avoid half-written files under Ctrl-C.
    # 原子寫入避免 Ctrl-C 造成半寫檔。
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fp:
        json.dump(output, fp, indent=2, default=str)
    os.replace(tmp_path, out_path)
    logger.info(
        "Counterfactual audit written to %s (mode=%s, n_positions=%d)",
        out_path, output["meta"]["mode"], output["meta"]["n_positions"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
