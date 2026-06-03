"""funding-tilt 會計模型 — 協議 §3.0 雙面 funding（防雙重計入）。

MODULE_NOTE:
  模塊用途：算每筆 round-trip 的會計三項，**釘死 funding 雙面符號避免雙重計入**
    （協議紅線 3 + §3.0）。
  ★ 會計約定（§3.0，與 trend cost_model 不同）：
    ``net_edge = gross_price + funding_pnl − cost``，其中
      - ``gross_price`` = 純價格 open-to-open 報酬 × side（**不含 funding**）。
      - ``funding_pnl`` = 持有期跨越結算的 Σ (−side) × F_realized（**單獨一項**，可正可負，
        逐結算對齊**非均值**；負號=會計符號約定，見下）。
      - ``cost`` = fee + slippage（**不含 funding**）。
    為什麼 funding 要從 cost 提出來當獨立 PnL 項：本協議 funding **是信號本身**——若把
    它算成正成本（drag），會雙重懲罰；若 gross 已含 funding carry 而 cost 又扣一次，會
    雙重計入。故 funding 只進 funding_pnl 一次。
    符號：多單付正 funding → funding_pnl 為負；空單收正 funding → funding_pnl 為正。
  成本構成（協議 §3.1/§3.2）：
    - Fee：taker 5.5bps/side（保守 SSOT），RT=11bps；maker 情境 RT=4bps 作 upside。
    - Slippage：5bps/side 保守上限，RT=10bps。
  cap discipline（紅線 2）：funding 用已實現結算序列；本模塊不讀也不反推 funding cap。
  主要函數：``trading_cost_bps`` / ``funding_pnl_bps_for_settlements`` /
    ``carry_cost_ratio`` / ``carry_share``。
  硬邊界：純 math，無 DB / I/O；funding 結算缺值 → 該段不計入並標記（不偽造）。
  依賴：標準庫。import-time 零副作用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

# 協議 §3.1/§3.2 成本常數（bps）。
TAKER_FEE_BPS_PER_SIDE = 5.5
MAKER_FEE_BPS_PER_SIDE = 2.0  # maker upside 情境（RT=4bps）
SLIPPAGE_BPS_PER_SIDE = 5.0  # 保守上限

# carry 歸因門檻（協議 §3.5）。
CARRY_COST_RATIO_HEALTHY = 0.5
CARRY_COST_RATIO_ABANDON = 0.8


@dataclass
class TradeAccounting:
    """單筆 round-trip 會計三項（全部 bps，相對名目）— 協議 §3.0。"""

    gross_price_bps: float  # 純價格 open-to-open × side（不含 funding）
    funding_pnl_bps: float  # 跨結算 Σ (−side)×F（獨立項，>0=收 carry，<0=付 funding）
    cost_bps: float         # fee + slippage（不含 funding）
    net_bps: float          # gross_price + funding_pnl − cost
    side: int               # +1 long / -1 short
    n_settlements: int      # 持有期跨越的 funding 結算數
    funding_complete: bool   # 持有期 funding 結算是否全有覆蓋


def trading_cost_bps(
    *,
    maker: bool = False,
    fee_bps_per_side: Optional[float] = None,
    slippage_bps_per_side: float = SLIPPAGE_BPS_PER_SIDE,
) -> float:
    """round-trip 交易成本（bps）= fee_RT + slippage_RT（**不含 funding**，協議 §3.0）。

    協議 §3.1：taker 上限證明能 survive 最壞成本；maker=True 作 upside 敏感度。
    """
    if fee_bps_per_side is None:
        fee_bps_per_side = MAKER_FEE_BPS_PER_SIDE if maker else TAKER_FEE_BPS_PER_SIDE
    return 2.0 * fee_bps_per_side + 2.0 * slippage_bps_per_side


def funding_pnl_bps_for_settlements(
    side: int,
    settlement_rates: Sequence[float],
) -> tuple[float, int]:
    """逐結算對齊的 funding PnL（bps）— 協議 §3.3（非均值近似，相對 trend 的升級）。

    funding_pnl = Σ(持有期跨越的每個結算) (−side) × F_realized_settlement × 1e4。
    符號：多單（side=+1）付正 funding → funding_pnl 為負（成本）；空單（side=-1）在正
    funding 下收 funding → funding_pnl 為正（補貼/收割）。
    settlement_rates: 持有期內真實跨越的結算費率序列（分數），由 pnl 模塊用各 symbol
    各窗真實結算對齊提供（8h symbol 持 7 日=21 結算、4h=42 結算，協議 §2.2）。
    回 (funding_pnl_bps, n_settlements)。
    """
    n = len(settlement_rates)
    if n == 0:
        return 0.0, 0
    total = 0.0
    # funding_pnl = −side × F：多單（side=+1）付正 funding → 負；空單（side=-1）收 → 正。
    # 為什麼是 −side：funding rate 正 = 多頭付給空頭。持多單者支出（PnL 減），持空單者收入。
    for r in settlement_rates:
        total += -side * float(r) * 1e4
    return float(total), n


def carry_cost_ratio(cost_bps: float, funding_pnl_bps: Optional[float]) -> Optional[float]:
    """carry_cost_ratio = cost / funding_pnl（協議 §3.5），funding_pnl>0 時才有意義。

    <0.5 健康 / 0.5-0.8 marginal / ≥0.8 放棄（NO-GO-C）。
    funding_pnl ≤0 → 無意義（回 None，由 caller 標「carry 為負/收不到」更嚴重）。
    """
    if funding_pnl_bps is None or funding_pnl_bps <= 0:
        return None
    return float(cost_bps / funding_pnl_bps)


def classify_carry_cost_ratio(ratio: Optional[float]) -> str:
    """把 carry_cost_ratio 映射成 healthy / marginal / abandon / undefined。"""
    if ratio is None:
        return "undefined_or_funding_pnl_nonpositive"
    if ratio < CARRY_COST_RATIO_HEALTHY:
        return "healthy"
    if ratio < CARRY_COST_RATIO_ABANDON:
        return "marginal"
    return "abandon"


def carry_share(funding_pnl_bps: Optional[float], gross_price_bps: Optional[float]) -> Optional[float]:
    """carry 純度（協議 §3.5）：carry_share = funding_pnl / (funding_pnl + max(gross_price, 0))。

    為什麼：若 net 為正但 carry_share 低 → 偽裝成 carry 的 directional bet（須 regime
    gate §4b）；若 gross_price 顯著為負而 funding_pnl 為正抵銷 →「收 carry 但被價格反向
    吃」，淨 marginal。funding_pnl ≤0 → carry_share 無意義（回 None）。
    """
    if funding_pnl_bps is None or funding_pnl_bps <= 0:
        return None
    gp = max(gross_price_bps, 0.0) if gross_price_bps is not None else 0.0
    denom = funding_pnl_bps + gp
    if denom <= 0:
        return None
    return float(funding_pnl_bps / denom)
