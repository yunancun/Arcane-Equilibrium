"""PnL 與 trade 構造 — 協議 §2 執行紀律 + §3 成本 + §4 effective N。

MODULE_NOTE:
  模塊用途：把雙軌信號（leak-free / naive）轉成 trade 序列，套執行紀律 + 多日成本，
    產 per-trade gross/net edge、日報酬 Sharpe、方向翻轉次數（→ effective N）、
    多空 + regime 拆解。
  執行紀律（協議 §2）：進場 = 第 t 日**開盤 O_t**（信號在 t-1 收盤後算），出場 =
    出場日開盤；**禁用 t 日收盤執行 t 日信號**。本模塊用「t 日開盤→出場日開盤」的
    open-to-open 報酬，徹底避免「用算信號那根 bar 的收盤成交」的隱性 look-ahead。
  持有期變體（協議 §1，多日 vs intraday 的核心變數）：
    - variant 1「daily」：每日按信號方向再平衡（最高 turnover）。
    - variant 2「flip_hold_min」：信號翻轉才換倉 + 最短持有 H_min=5 日（最低 turnover）。
  effective N（協議 §4.1）：每信號每變體每 symbol 的實際**方向翻轉次數** → pooled →
    cluster 縮減（PCA N_eff，由 harness 套用）。effective N<60 → INCONCLUSIVE-A。
  主要函數：``build_trades`` / ``trade_metrics`` / ``daily_returns_from_positions``。
  硬邊界：純 math；信號 NaN（warmup / 不足）視為「無倉位」；上市前 signal=0 = 平倉。
  依賴：numpy + 本目錄 cost_model / stats。import-time 零副作用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import cost_model, stats

H_MIN_DAYS = 5  # 協議 §1 變體 2 的最短持有期。


@dataclass
class Trade:
    """單筆 round-trip：t_in 日開盤進、t_out 日開盤出。"""

    symbol: str
    side: int  # +1 long / -1 short
    t_in: int  # 進場 bar index（開盤執行）
    t_out: int  # 出場 bar index（開盤執行）
    holding_days: int
    gross_ret: float  # open-to-open 對數報酬 × side（未扣成本，分數）
    regime_in: Optional[str] = None


def _positions_daily(signal: np.ndarray) -> np.ndarray:
    """variant 1：position[t] = sign(signal[t-1])（t-1 收盤算的信號，t 日持有）。

    為什麼再 shift 一次：signal 已是 leak-free（用 C_{t-1}），但「持倉」是 t 日才建立。
    position[t] 表示「第 t 日開盤到 t+1 日開盤」持有的方向。signal NaN / 0 → flat(0)。
    """
    n = len(signal)
    pos = np.zeros(n, dtype=float)
    for t in range(1, n):
        s = signal[t - 1]
        if np.isfinite(s) and s != 0:
            pos[t] = 1.0 if s > 0 else -1.0
    return pos


def _positions_flip_hold(signal: np.ndarray, h_min: int = H_MIN_DAYS) -> np.ndarray:
    """variant 2：信號翻轉才換倉 + 最短持有 h_min 日（過濾 whipsaw，最低 turnover）。"""
    n = len(signal)
    pos = np.zeros(n, dtype=float)
    cur = 0.0
    held = 0
    for t in range(1, n):
        s = signal[t - 1]
        desired = 0.0
        if np.isfinite(s) and s != 0:
            desired = 1.0 if s > 0 else -1.0
        if cur == 0.0:
            cur = desired
            held = 1 if desired != 0 else 0
        elif desired != 0 and desired != cur and held >= h_min:
            cur = desired  # 翻轉（已滿最短持有）
            held = 1
        elif desired == 0:
            # 信號消失（如 vol scaled NaN / 上市前 0）：保守平倉。
            cur = 0.0
            held = 0
        else:
            held += 1
        pos[t] = cur
    return pos


def build_trades(
    symbol: str,
    signal: np.ndarray,
    open_px: np.ndarray,
    *,
    variant: str = "daily",
    regimes: Optional[list] = None,
) -> tuple[list[Trade], np.ndarray, int]:
    """從信號構造 trade 序列 + 每日持倉 + 方向翻轉次數。

    回傳 (trades, positions, n_direction_flips)。
    positions[t] = 第 t 日開盤到 t+1 日開盤的方向。trade 在連續同向持倉段的起訖建立，
    出場/進場都用**開盤價** open_px（協議 §2：禁 t 日收盤執行）。
    n_direction_flips = 倉位方向實際改變的次數（含 flat↔有倉），即 effective N 的原料。
    """
    if variant == "daily":
        pos = _positions_daily(signal)
    elif variant == "flip_hold_min":
        pos = _positions_flip_hold(signal)
    else:
        raise ValueError(f"unknown_holding_variant:{variant}")

    n = len(pos)
    trades: list[Trade] = []
    flips = 0
    prev = 0.0
    seg_start = None
    seg_side = 0.0

    for t in range(n):
        cur = pos[t]
        if cur != prev:
            flips += 1
            # 結束前一段（若有倉）。
            if seg_side != 0 and seg_start is not None:
                _close_segment(trades, symbol, seg_side, seg_start, t, open_px, regimes)
            # 開新段。
            seg_side = cur
            seg_start = t if cur != 0 else None
        prev = cur
    # 收尾：序列末仍有倉 → 用最後可用開盤平（保守，避免懸空）。
    if seg_side != 0 and seg_start is not None and seg_start < n - 1:
        _close_segment(trades, symbol, seg_side, seg_start, n - 1, open_px, regimes)

    return trades, pos, flips


def _close_segment(trades, symbol, side, t_in, t_out, open_px, regimes) -> None:
    """把一段持倉 [t_in, t_out) 收成一筆 Trade（open-to-open 報酬）。

    進場 = t_in 開盤、出場 = t_out 開盤。gross_ret = side × ln(O_out/O_in)。
    """
    if t_in >= t_out:
        return
    o_in = open_px[t_in]
    o_out = open_px[t_out]
    if not (np.isfinite(o_in) and np.isfinite(o_out)) or o_in <= 0 or o_out <= 0:
        return
    gross = float(side) * float(np.log(o_out / o_in))
    regime_in = None
    if regimes is not None and 0 <= t_in < len(regimes):
        regime_in = regimes[t_in]
    trades.append(Trade(
        symbol=symbol, side=int(side), t_in=t_in, t_out=t_out,
        holding_days=int(t_out - t_in), gross_ret=gross, regime_in=regime_in,
    ))


def daily_returns_from_positions(
    positions: np.ndarray,
    open_px: np.ndarray,
    per_8h_funding_rate: float,
    *,
    fee_bps_per_side: float = cost_model.TAKER_FEE_BPS_PER_SIDE,
    slippage_bps_per_side: float = cost_model.SLIPPAGE_BPS_PER_SIDE,
) -> tuple[np.ndarray, np.ndarray]:
    """逐日 gross / net 報酬（分數），用 open-to-open + 換倉日扣 fee/slip + 每日扣 funding。

    為什麼 open-to-open：position[t] 是「t 日開盤→t+1 日開盤」持有，故當日 gross =
    position[t]×ln(O_{t+1}/O_t)。換倉（position 改變）當日扣 round-trip fee+slip 的
    入場側（出場側在前一段已扣，這裡用「每次方向變動扣一次 side 成本」近似 turnover）。
    funding 每日按持倉方向 × 3 結算扣。回傳 (gross_daily, net_daily)，長度 n。
    """
    n = len(positions)
    gross = np.zeros(n, dtype=float)
    net = np.zeros(n, dtype=float)
    fee_side = fee_bps_per_side * 1e-4
    slip_side = slippage_bps_per_side * 1e-4
    fund_day = per_8h_funding_rate * cost_model.FUNDING_SETTLEMENTS_PER_DAY
    prev_pos = 0.0
    for t in range(n - 1):
        p = positions[t]
        o0, o1 = open_px[t], open_px[t + 1]
        g = 0.0
        if p != 0 and np.isfinite(o0) and np.isfinite(o1) and o0 > 0 and o1 > 0:
            g = float(p) * float(np.log(o1 / o0))
        gross[t] = g
        # 換倉成本：方向改變 → 扣一次 side fee+slip（turnover proxy）。
        turn_cost = 0.0
        if p != prev_pos:
            turn_cost = (fee_side + slip_side)
        # funding：多單付正、空單收正（side 符號）。
        fund_cost = float(p) * fund_day
        net[t] = g - turn_cost - fund_cost
        prev_pos = p
    return gross, net


def trade_metrics(trades: list[Trade], per_8h_funding_rate: float, *, maker: bool = False) -> dict:
    """per-trade gross/net edge（bps）+ 多空 + funding 拆解（協議 §3/§4）。

    每筆 trade 套 round_trip_cost（含該 side 的 funding 累積），net = gross − cost。
    """
    if not trades:
        return {"n_trades": 0}
    gross_bps = []
    net_bps = []
    long_gross, short_gross = [], []
    long_net, short_net = [], []
    funding_long, funding_short = [], []
    holding = []
    for tr in trades:
        cb = cost_model.round_trip_cost_bps(
            tr.side, float(tr.holding_days), per_8h_funding_rate, maker=maker,
        )
        g_bps = tr.gross_ret * 1e4
        n_bps = g_bps - cb.total_bps
        gross_bps.append(g_bps)
        net_bps.append(n_bps)
        holding.append(tr.holding_days)
        if tr.side > 0:
            long_gross.append(g_bps)
            long_net.append(n_bps)
            funding_long.append(cb.funding_bps)
        else:
            short_gross.append(g_bps)
            short_net.append(n_bps)
            funding_short.append(cb.funding_bps)

    def _m(a):
        return float(np.mean(a)) if a else None

    return {
        "n_trades": len(trades),
        "n_long": len(long_gross),
        "n_short": len(short_gross),
        "avg_holding_days": _m(holding),
        "gross_edge_bps_per_trade": _m(gross_bps),
        "net_edge_bps_per_trade": _m(net_bps),
        "long_gross_bps": _m(long_gross),
        "long_net_bps": _m(long_net),
        "short_gross_bps": _m(short_gross),
        "short_net_bps": _m(short_net),
        "avg_funding_bps_long": _m(funding_long),  # >0 = 多單 funding 成本
        "avg_funding_bps_short": _m(funding_short),  # <0 = 空單 funding 補貼
        "win_rate": float(np.mean([1.0 if x > 0 else 0.0 for x in net_bps])) if net_bps else None,
    }
