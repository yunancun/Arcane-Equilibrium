"""多日成本模型（含 funding 累積）— 協議 §3。

MODULE_NOTE:
  模塊用途：算每筆 round-trip 持倉的全成本 = fee + slippage + funding 累積。
    多日 trend 的樞紐命題：funding 按**時間累積**（非按交易次數攤薄），故持有越久
    funding drag 越高 → 多日成本可能比 intraday 更高（協議 §3 樞紐）。
  成本構成（協議 §3）：
    - Fee：taker 5.5bps/side（保守 SSOT），RT=11bps；maker 情境 RT=4bps 作 upside。
    - Slippage：5bps/side 保守上限，RT=10bps。
    - Funding：Σ(持有期跨越的每個 8h 結算) position_side × F_settlement。
      做多付正 funding（雙重成本）、做空收正 funding（部分補貼）。
      F_settlement 取**已實現** history（NOT cap 反推——funding_short_v2 教訓）。
  ⚠ funding 覆蓋限制（本 runtime 實況）：market.funding_rates 僅 ~58 天
    （2026-04-05→2026-06-02），遠短於 730 天信號窗 → 成本模型用「per-symbol 已實現
    funding 代表性均值」套用全窗，並在 harness 標 funding INCONCLUSIVE-on-coverage。
  主要函數：``round_trip_cost_bps`` / ``funding_cost_bps_for_holding`` /
    ``cost_edge_ratio``。
  硬邊界：純 math，無 DB / I/O；funding rate 缺值 → 該段 funding=0 並標記（不偽造）。
  依賴：標準庫。import-time 零副作用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# 協議 §3 成本常數（bps）。
TAKER_FEE_BPS_PER_SIDE = 5.5
MAKER_FEE_BPS_PER_SIDE = 2.0  # maker upside 情境（RT=4bps）
SLIPPAGE_BPS_PER_SIDE = 5.0  # 保守上限

# funding 每日結算次數（Bybit perp：每 8h 一次 → 3 次/日）。
FUNDING_SETTLEMENTS_PER_DAY = 3

# cost_edge_ratio 判定門檻（協議 §3.cost_edge_ratio / §5）。
COST_EDGE_RATIO_HEALTHY = 0.5
COST_EDGE_RATIO_ABANDON = 0.8


@dataclass
class CostBreakdown:
    """單筆 round-trip 成本拆解（全部 bps，相對名目）。"""

    fee_bps: float
    slippage_bps: float
    funding_bps: float  # 已含符號：>0 = 淨成本（多單付）、<0 = 淨補貼（空單收）
    total_bps: float
    holding_days: float
    funding_settlements: int
    side: int  # +1 long / -1 short
    funding_complete: bool  # 持有期 funding rate 是否全有覆蓋


def funding_cost_bps_for_holding(
    side: int,
    holding_days: float,
    mean_funding_rate_per_8h: float,
    *,
    coverage_complete: bool = False,
) -> tuple[float, int]:
    """算持有期內 funding 累積成本（bps）。

    協議 §3：funding_cost = Σ(跨越的 8h 結算) side × F_settlement。
    做多（side=+1）付正 funding → 正成本；做空（side=-1）在正 funding 下收 funding →
    負成本（補貼）。用 per-symbol 已實現均值 × 結算次數近似（因 funding 覆蓋僅 ~58 天，
    無法逐結算對齊 730 天窗——這是誠實近似，coverage_complete 標記是否可信）。

    回傳 (funding_bps, n_settlements)。funding_bps 已含 side 符號。
    mean_funding_rate_per_8h 是「分數」（如 0.0001=1bp），轉 bps 後乘結算次數。
    """
    n_settlements = max(0, int(round(holding_days * FUNDING_SETTLEMENTS_PER_DAY)))
    # side × rate：多單付正 funding（成本為正），空單收正 funding（成本為負）。
    rate_bps = mean_funding_rate_per_8h * 1e4
    funding_bps = side * rate_bps * n_settlements
    return float(funding_bps), n_settlements


def round_trip_cost_bps(
    side: int,
    holding_days: float,
    mean_funding_rate_per_8h: float,
    *,
    maker: bool = False,
    fee_bps_per_side: Optional[float] = None,
    slippage_bps_per_side: float = SLIPPAGE_BPS_PER_SIDE,
    funding_coverage_complete: bool = False,
) -> CostBreakdown:
    """單筆 round-trip 全成本（bps）：fee_RT + slippage_RT + funding 累積。

    協議 §3：多日 trend 用 taker 上限證明能 survive 最壞成本；maker=True 作 upside。
    """
    if fee_bps_per_side is None:
        fee_bps_per_side = MAKER_FEE_BPS_PER_SIDE if maker else TAKER_FEE_BPS_PER_SIDE
    fee_rt = 2.0 * fee_bps_per_side
    slip_rt = 2.0 * slippage_bps_per_side
    funding_bps, n_settle = funding_cost_bps_for_holding(
        side, holding_days, mean_funding_rate_per_8h,
        coverage_complete=funding_coverage_complete,
    )
    total = fee_rt + slip_rt + funding_bps
    return CostBreakdown(
        fee_bps=fee_rt,
        slippage_bps=slip_rt,
        funding_bps=funding_bps,
        total_bps=total,
        holding_days=holding_days,
        funding_settlements=n_settle,
        side=side,
        funding_complete=funding_coverage_complete,
    )


def cost_edge_ratio(cost_rt_bps: float, gross_edge_per_trade_bps: Optional[float]) -> Optional[float]:
    """cost_edge_ratio = cost_RT / gross_edge_per_trade（協議 §3）。

    <0.5 健康 / 0.5-0.8 marginal / ≥0.8 放棄（NO-GO-C）。
    gross_edge ≤0 → 無意義（回 None，由 caller 標「gross 已負」更嚴重）。
    """
    if gross_edge_per_trade_bps is None or gross_edge_per_trade_bps <= 0:
        return None
    return float(cost_rt_bps / gross_edge_per_trade_bps)


def classify_cost_edge_ratio(ratio: Optional[float]) -> str:
    """把 cost_edge_ratio 映射成 healthy / marginal / abandon / undefined。"""
    if ratio is None:
        return "undefined_or_gross_negative"
    if ratio < COST_EDGE_RATIO_HEALTHY:
        return "healthy"
    if ratio < COST_EDGE_RATIO_ABANDON:
        return "marginal"
    return "abandon"
