"""PnL 與 trade 構造 — 協議 §1.2/§2.4 執行紀律 + §3.0 會計 + §3.3 per-leg 分解。

MODULE_NOTE:
  模塊用途：把雙軌信號（leak-free / naive）轉成 trade 序列，套 open-to-open 執行紀律
    + §3.0 會計三項（gross_price / funding_pnl / cost），產 per-trade net edge、日報酬
    Sharpe、方向翻轉次數（→ effective N）、**per-leg（long/short）分解**。
  ★ per-leg 分解（MIT 強制，協議 §3.3 + cheap pre-check caveat）：
    分報 long-leg vs short-leg 的 ``funding_pnl`` + 各腿 ``gross_price_bps`` + carry_share
    by leg。為什麼最關鍵：MIT 實測 ~68% gross carry 來自 short-top leg，long-bottom leg
    幾乎不收（40.5% 時間其實是正 funding=付費）。aggregate 正 net 會藏住「單邊擠壓風險」
    ——短-top leg 的 gross_price_bps（價格反向吃 carry 嗎=squeeze）是核心問題。
  執行紀律（協議 §2.4）：進場 = 進場日**開盤 O_t**（信號在前一結算後算），出場 = 出場日
    開盤；open-to-open 報酬，徹底避免隱性 look-ahead。
  持有期變體（協議 §1.2）：
    - variant 1「daily」：每日按信號再平衡（最高 turnover）。
    - variant 2「flip_hold_min」：信號 tertile 翻轉才換倉 + 最短持有 H_min（低 turnover，
      operator「低 turnover 多日 carry 攤薄成本」逃逸論點的直接實作）。
  ★ funding_pnl 逐結算對齊（協議 §3.3）：每筆 trade 收集持有窗 [open_ts_in, open_ts_out)
    內該 symbol 真實跨越的 funding 結算費率序列，per-settlement 算（非均值）。8h symbol
    持 7 日=21 結算、4h=42 結算（interval 由 data_loader 推導，§2.2）。
  主要函數：``build_trades`` / ``trade_metrics_with_legs`` /
    ``daily_returns_from_positions``。
  硬邊界：純 math；信號 NaN（不足）視為「無倉位」；上市前 signal=0 = 平倉。
  依賴：numpy + bisect + 本目錄 cost_model。import-time 零副作用。
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import cost_model

H_MIN_DAYS_DEFAULT = 7  # 協議 §1.2 變體 2 的最短持有期（≥21 結算 @ 8h）。


@dataclass
class Trade:
    """單筆 round-trip：t_in 日開盤進、t_out 日開盤出（協議 §3.0 會計三項）。"""

    symbol: str
    side: int  # +1 long / -1 short
    t_in: int
    t_out: int
    holding_days: int
    gross_price_bps: float  # open-to-open 純價格 × side（不含 funding），bps
    funding_pnl_bps: float  # 跨結算 Σ side×F（逐結算對齊），bps
    n_settlements: int
    regime_in: Optional[str] = None


def _positions_daily(signal: np.ndarray) -> np.ndarray:
    """variant 1：position[t] = sign(signal[t-1])（t-1 算的信號，t 日開盤持有）。

    為什麼再 shift 一次：signal 已是 leak-free（用 funding_ts<open−ε），但「持倉」是 t 日
    才建立。position[t] 表示「第 t 日開盤到 t+1 日開盤」持有方向。signal NaN/0 → flat。
    """
    n = len(signal)
    pos = np.zeros(n, dtype=float)
    for t in range(1, n):
        s = signal[t - 1]
        if np.isfinite(s) and s != 0:
            pos[t] = 1.0 if s > 0 else -1.0
    return pos


def _positions_flip_hold(signal: np.ndarray, h_min: int) -> np.ndarray:
    """variant 2：信號翻轉才換倉 + 最短持有 h_min 日（低 turnover，協議 §1.2 變體 2）。"""
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
            cur = 0.0  # 信號消失（上市前 0 / extreme 退出）→ 保守平倉
            held = 0
        else:
            held += 1
        pos[t] = cur
    return pos


def _settlements_in_window(
    funding_ts: list,
    funding_rate: np.ndarray,
    open_ts_in,
    open_ts_out,
) -> np.ndarray:
    """收集持有窗 [open_ts_in, open_ts_out) 內該 symbol 真實跨越的結算費率（協議 §3.3）。

    為什麼 [in, out)：持倉從 t_in 開盤到 t_out 開盤；跨越的結算 = funding_ts 落在此半開
    區間者（出場開盤同時的結算不計，保守）。逐結算對齊（非均值），8h/4h symbol 自然得到
    正確結算數（funding_ts 真實序列已含各自 interval）。
    """
    if not funding_ts:
        return np.array([], dtype=float)
    lo = bisect.bisect_left(funding_ts, open_ts_in)
    hi = bisect.bisect_left(funding_ts, open_ts_out)
    if hi <= lo:
        return np.array([], dtype=float)
    return funding_rate[lo:hi]


def build_trades(
    symbol: str,
    signal: np.ndarray,
    open_px: np.ndarray,
    open_ts_utc: np.ndarray,
    funding_ts: list,
    funding_rate: np.ndarray,
    *,
    variant: str = "daily",
    h_min: int = H_MIN_DAYS_DEFAULT,
    regimes: Optional[list] = None,
) -> tuple[list, np.ndarray, int]:
    """從信號構造 trade 序列 + 每日持倉 + 方向翻轉次數（協議 §2.4 + §3.0/§3.3）。

    回 (trades, positions, n_direction_flips)。trade 在連續同向持倉段的起訖建立，
    出場/進場都用**開盤價** open_px（協議 §2.4）；funding_pnl 逐結算對齊持有窗。
    n_direction_flips = 倉位方向實際改變次數（含 flat↔有倉），effective N 原料。
    """
    if variant == "daily":
        pos = _positions_daily(signal)
    elif variant == "flip_hold_min":
        pos = _positions_flip_hold(signal, h_min)
    else:
        raise ValueError(f"unknown_holding_variant:{variant}")

    n = len(pos)
    trades: list = []
    flips = 0
    prev = 0.0
    seg_start = None
    seg_side = 0.0

    for t in range(n):
        cur = pos[t]
        if cur != prev:
            flips += 1
            if seg_side != 0 and seg_start is not None:
                _close_segment(trades, symbol, seg_side, seg_start, t, open_px,
                               open_ts_utc, funding_ts, funding_rate, regimes)
            seg_side = cur
            seg_start = t if cur != 0 else None
        prev = cur
    if seg_side != 0 and seg_start is not None and seg_start < n - 1:
        _close_segment(trades, symbol, seg_side, seg_start, n - 1, open_px,
                       open_ts_utc, funding_ts, funding_rate, regimes)

    return trades, pos, flips


def _close_segment(trades, symbol, side, t_in, t_out, open_px, open_ts_utc,
                   funding_ts, funding_rate, regimes) -> None:
    """把一段持倉 [t_in, t_out) 收成一筆 Trade（協議 §3.0 會計三項）。

    gross_price = side × ln(O_out/O_in)；funding_pnl = 逐結算對齊持有窗 Σ side×F。
    """
    if t_in >= t_out:
        return
    o_in = open_px[t_in]
    o_out = open_px[t_out]
    if not (np.isfinite(o_in) and np.isfinite(o_out)) or o_in <= 0 or o_out <= 0:
        return
    gross_price_bps = float(side) * float(np.log(o_out / o_in)) * 1e4
    rates = _settlements_in_window(funding_ts, funding_rate,
                                   open_ts_utc[t_in], open_ts_utc[t_out])
    funding_pnl_bps, n_settle = cost_model.funding_pnl_bps_for_settlements(int(side), rates)
    regime_in = None
    if regimes is not None and 0 <= t_in < len(regimes):
        regime_in = regimes[t_in]
    trades.append(Trade(
        symbol=symbol, side=int(side), t_in=t_in, t_out=t_out,
        holding_days=int(t_out - t_in), gross_price_bps=gross_price_bps,
        funding_pnl_bps=funding_pnl_bps, n_settlements=n_settle, regime_in=regime_in,
    ))


def daily_returns_from_positions(
    positions: np.ndarray,
    open_px: np.ndarray,
    open_ts_utc: np.ndarray,
    funding_ts: list,
    funding_rate: np.ndarray,
    *,
    fee_bps_per_side: float = cost_model.TAKER_FEE_BPS_PER_SIDE,
    slippage_bps_per_side: float = cost_model.SLIPPAGE_BPS_PER_SIDE,
    include_funding: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """逐日 gross_price / net 報酬（分數），open-to-open + 換倉日扣 fee/slip + 每日對齊 funding。

    協議 §3.0：net = gross_price + funding_pnl − (fee+slip)。position[t] 是「t 日開盤→
    t+1 日開盤」持有，當日 gross_price = position[t]×ln(O_{t+1}/O_t)。換倉（position 改變）
    當日扣一次 side fee+slip（turnover proxy）。funding_pnl 逐日對齊 [open_ts[t], open_ts[t+1])
    內真實結算（符號：side×F，多付空收）。include_funding=False → 純 gross_price（leak/naive
    look-ahead 診斷用，§2.1 純看 price-side look-ahead 不混 funding）。
    回 (gross_price_daily, net_daily)，長度 n。
    """
    n = len(positions)
    gross = np.zeros(n, dtype=float)
    net = np.zeros(n, dtype=float)
    fee_side = fee_bps_per_side * 1e-4
    slip_side = slippage_bps_per_side * 1e-4
    prev_pos = 0.0
    for t in range(n - 1):
        p = positions[t]
        o0, o1 = open_px[t], open_px[t + 1]
        g = 0.0
        if p != 0 and np.isfinite(o0) and np.isfinite(o1) and o0 > 0 and o1 > 0:
            g = float(p) * float(np.log(o1 / o0))
        gross[t] = g
        turn_cost = (fee_side + slip_side) if p != prev_pos else 0.0
        # funding_pnl 逐日對齊：[open_ts[t], open_ts[t+1]) 內真實結算，−side×F（多付空收，§3.0）。
        fund_pnl = 0.0
        if include_funding and p != 0:
            rates = _settlements_in_window(funding_ts, funding_rate,
                                           open_ts_utc[t], open_ts_utc[t + 1])
            for r in rates:
                fund_pnl += -float(p) * float(r)
        net[t] = g + fund_pnl - turn_cost
        prev_pos = p
    return gross, net


def trade_metrics_with_legs(trades: list, *, maker: bool = False) -> dict:
    """per-trade 會計三項 + **per-leg（long/short）分解**（協議 §3.0/§3.3，MIT 強制）。

    每筆套 round-trip 交易成本（fee+slip，不含 funding），net = gross_price + funding_pnl
    − cost。**分報 long-leg / short-leg 的 funding_pnl + gross_price + net + carry_share**，
    使「~68% carry 來自 short-top leg」與「short leg 價格反向吃 carry=squeeze」一目了然。
    """
    if not trades:
        return {"n_trades": 0}
    cost_rt = cost_model.trading_cost_bps(maker=maker)

    def _agg(side_trades):
        if not side_trades:
            return {
                "n": 0, "gross_price_bps": None, "funding_pnl_bps": None,
                "cost_bps": None, "net_bps": None, "carry_share": None,
                "carry_cost_ratio": None, "carry_cost_class": "undefined_or_funding_pnl_nonpositive",
                "avg_holding_days": None, "avg_n_settlements": None,
            }
        gp = [t.gross_price_bps for t in side_trades]
        fp = [t.funding_pnl_bps for t in side_trades]
        net = [t.gross_price_bps + t.funding_pnl_bps - cost_rt for t in side_trades]
        hold = [t.holding_days for t in side_trades]
        nset = [t.n_settlements for t in side_trades]
        mean_gp = float(np.mean(gp))
        mean_fp = float(np.mean(fp))
        cshare = cost_model.carry_share(mean_fp, mean_gp)
        ccr = cost_model.carry_cost_ratio(cost_rt, mean_fp)
        return {
            "n": len(side_trades),
            "gross_price_bps": round(mean_gp, 4),
            "funding_pnl_bps": round(mean_fp, 4),
            "cost_bps": round(cost_rt, 4),
            "net_bps": round(float(np.mean(net)), 4),
            "carry_share": round(cshare, 4) if cshare is not None else None,
            "carry_cost_ratio": round(ccr, 4) if ccr is not None else None,
            "carry_cost_class": cost_model.classify_carry_cost_ratio(ccr),
            "avg_holding_days": round(float(np.mean(hold)), 2),
            "avg_n_settlements": round(float(np.mean(nset)), 2),
            "win_rate": round(float(np.mean([1.0 if x > 0 else 0.0 for x in net])), 4),
        }

    long_trades = [t for t in trades if t.side > 0]
    short_trades = [t for t in trades if t.side < 0]
    all_net = [t.gross_price_bps + t.funding_pnl_bps - cost_rt for t in trades]
    all_fp = float(np.mean([t.funding_pnl_bps for t in trades]))
    all_gp = float(np.mean([t.gross_price_bps for t in trades]))
    agg_cshare = cost_model.carry_share(all_fp, all_gp)
    agg_ccr = cost_model.carry_cost_ratio(cost_rt, all_fp)

    return {
        "n_trades": len(trades),
        "cost_rt_bps": round(cost_rt, 4),
        "aggregate": {
            "gross_price_bps": round(all_gp, 4),
            "funding_pnl_bps": round(all_fp, 4),
            "cost_bps": round(cost_rt, 4),
            "net_bps": round(float(np.mean(all_net)), 4),
            "carry_share": round(agg_cshare, 4) if agg_cshare is not None else None,
            "carry_cost_ratio": round(agg_ccr, 4) if agg_ccr is not None else None,
            "carry_cost_class": cost_model.classify_carry_cost_ratio(agg_ccr),
            "win_rate": round(float(np.mean([1.0 if x > 0 else 0.0 for x in all_net])), 4),
            "avg_holding_days": round(float(np.mean([t.holding_days for t in trades])), 2),
        },
        # ★ per-leg：aggregate 正 net 不可藏單邊擠壓風險（MIT 強制）。
        "long_leg": _agg(long_trades),
        "short_leg": _agg(short_trades),
    }
