"""
0B-3: Position Sizer — Kelly Fraction + Risk-Adjusted Sizing / Kelly 分數 + 風控調整倉位計算
=========================================================================================

MODULE_NOTE (中文):
  PositionSizer 實現 Kelly 四層倉位計算（報告 §5.1）：
  1. Kelly fraction：根據勝率、平均勝虧比計算最優下注比例
  2. Vol-adjusted：根據 ATR 調整倉位大小（波動大 → 減倉）
  3. Risk Parity：多品種風險平價權重分配
  4. P1 硬上限：單筆最大曝險不超過餘額 2%

  倉位建議 = min(kelly_qty, vol_adjusted_qty, max_allowed_qty)

  安全不變量：
  - 純計算，不直接修改任何交易狀態
  - Kelly 分數始終使用分數 Kelly（1/8~1/4），永不使用完整 Kelly
  - 交易次數不足時使用最保守的 1/8 Kelly
  - 所有計算失敗返回最小倉位（fail-closed）

MODULE_NOTE (English):
  PositionSizer implements Kelly four-layer position sizing (Report §5.1):
  1. Kelly fraction: optimal bet fraction from win rate and payoff ratio
  2. Vol-adjusted: ATR-scaled position size (higher vol → smaller position)
  3. Risk Parity: multi-symbol equal-risk weight distribution
  4. P1 hard cap: max single-trade exposure ≤ 2% of balance

  Recommended qty = min(kelly_qty, vol_adjusted_qty, max_allowed_qty)

  Safety invariants:
  - Pure computation, never modifies trading state directly
  - Always uses fractional Kelly (1/8 to 1/4), never full Kelly
  - Insufficient trade data → most conservative 1/8 Kelly
  - Any computation failure returns minimum position size (fail-closed)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SizingRecommendation:
    """
    Position sizing recommendation result.
    倉位大小建議結果。
    """
    kelly_fraction: float = 0.0       # Raw fractional Kelly (after sample-size adjustment)
    kelly_qty: float = 0.0            # Kelly-recommended qty in base currency
    vol_adjusted_qty: float = 0.0     # Volatility-adjusted qty
    max_allowed_qty: float = 0.0      # P1 hard cap qty
    recommended_qty: float = 0.0      # Final recommendation = min(kelly, vol, max)
    sample_size: int = 0              # Number of trades used for Kelly
    kelly_tier: str = "conservative"  # "conservative" (1/8) | "moderate" (1/6) | "normal" (1/4)
    win_rate: float = 0.0             # Win rate used in calculation
    payoff_ratio: float = 0.0         # avg_win / avg_loss ratio

    def to_dict(self) -> dict[str, Any]:
        return {
            "kelly_fraction": round(self.kelly_fraction, 6),
            "kelly_qty": round(self.kelly_qty, 6),
            "vol_adjusted_qty": round(self.vol_adjusted_qty, 6),
            "max_allowed_qty": round(self.max_allowed_qty, 6),
            "recommended_qty": round(self.recommended_qty, 6),
            "sample_size": self.sample_size,
            "kelly_tier": self.kelly_tier,
            "win_rate": round(self.win_rate, 4),
            "payoff_ratio": round(self.payoff_ratio, 4),
        }


class PositionSizer:
    """
    Kelly-based position sizing engine with risk parity and P1 caps.
    基於 Kelly 的倉位計算引擎，含風險平價和 P1 上限。

    Thread-safe: all methods are pure functions with no mutable state.
    線程安全：所有方法為純函數，無可變狀態。
    """

    def __init__(
        self,
        *,
        p1_max_pct: float = 2.0,       # P1 hard cap: max % of balance per trade
        risk_pct_default: float = 3.0,  # Default risk % when Kelly unavailable
    ) -> None:
        self._p1_max_pct = p1_max_pct
        self._risk_pct_default = risk_pct_default

    def compute_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        trade_count: int = 0,
    ) -> float:
        """
        Compute fractional Kelly criterion.
        計算分數 Kelly 準則。

        Uses sample-size-adjusted fractional Kelly:
          trade_count < 50  → 1/8 Kelly (highly conservative, minimal data)
          trade_count < 200 → 1/6 Kelly (moderate confidence)
          trade_count ≥ 200 → 1/4 Kelly (sufficient statistical basis)

        Full Kelly is NEVER used — even 1/2 Kelly is too aggressive for real trading.
        永不使用完整 Kelly — 即使 1/2 Kelly 在實際交易中也過於激進。

        Args:
            win_rate: Fraction of winning trades [0, 1].
            avg_win: Average winning trade in absolute terms (USDT).
            avg_loss: Average losing trade in absolute terms (USDT).
            trade_count: Number of completed trades for sample size adjustment.

        Returns:
            Fractional Kelly in [0, 1]. 0 means don't trade.
        """
        aw = abs(avg_win)
        al = abs(avg_loss)
        if aw <= 0 or al <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        # Kelly formula: f* = (b*p - q) / b where b=payoff ratio, p=win_rate, q=1-p
        b = aw / al
        f_star = (b * win_rate - (1 - win_rate)) / b
        f_star = max(0.0, f_star)

        # Sample-size-adjusted fractional Kelly / 根據樣本量調整分數 Kelly
        if trade_count < 50:
            return f_star / 8   # 1/8 Kelly — highly conservative / 高度保守
        elif trade_count < 200:
            return f_star / 6   # 1/6 Kelly — moderate / 中等
        else:
            return f_star / 4   # 1/4 Kelly — normal (still conservative vs full Kelly)

    def compute_volatility_adjusted_qty(
        self,
        balance: float,
        atr: float,
        price: float,
        risk_pct: float | None = None,
    ) -> float:
        """
        Compute volatility-adjusted position size based on ATR.
        根據 ATR 計算波動率調整的倉位大小。

        Formula: qty = (balance × risk_pct) / (atr × price)
        Higher ATR → smaller position (risk-adjusted).

        Args:
            balance: Account balance in USDT.
            atr: Average True Range of the asset.
            price: Current price of the asset.
            risk_pct: Risk percentage (default: self._risk_pct_default).

        Returns:
            Position size in base currency. 0 if inputs invalid.
        """
        if balance <= 0 or atr <= 0 or price <= 0:
            return 0.0
        rp = risk_pct if risk_pct is not None else self._risk_pct_default
        risk_usdt = balance * rp / 100.0
        qty = risk_usdt / (atr * price) if atr * price > 0 else 0.0
        return max(0.0, qty)

    def compute_risk_parity_weights(
        self,
        volatilities: dict[str, float],
    ) -> dict[str, float]:
        """
        Compute risk parity weights across multiple symbols.
        計算多品種風險平價權重。

        Each symbol gets weight inversely proportional to its volatility.
        每個品種的權重與其波動率成反比。

        Args:
            volatilities: {symbol: volatility_estimate} dict.

        Returns:
            {symbol: weight} dict, weights sum to 1.0. Empty if all zero.
        """
        if not volatilities:
            return {}

        # Inverse volatility weights / 逆波動率權重
        inv_vols = {}
        for sym, vol in volatilities.items():
            if vol > 0:
                inv_vols[sym] = 1.0 / vol

        total = sum(inv_vols.values())
        if total <= 0:
            return {}

        return {sym: iv / total for sym, iv in inv_vols.items()}

    def compute_max_allowed_qty(
        self,
        balance: float,
        price: float,
    ) -> float:
        """
        Compute P1 hard cap on position size.
        計算 P1 硬上限倉位大小。

        Max single-trade exposure = p1_max_pct × balance.
        Converted to base currency qty at current price.

        Args:
            balance: Account balance in USDT.
            price: Current price of the asset.

        Returns:
            Maximum allowed qty in base currency. 0 if price is invalid.
        """
        if balance <= 0 or price <= 0:
            return 0.0
        return balance * self._p1_max_pct / 100.0 / price

    def compute_recommendation(
        self,
        *,
        balance: float,
        price: float,
        win_rate: float = 0.0,
        avg_win: float = 0.0,
        avg_loss: float = 0.0,
        trade_count: int = 0,
        atr: float = 0.0,
    ) -> SizingRecommendation:
        """
        Compute full position sizing recommendation.
        計算完整倉位大小建議。

        Combines Kelly, volatility adjustment, and P1 cap.
        Final recommendation = min(kelly_qty, vol_adjusted_qty, max_allowed_qty).
        If any component is 0 (insufficient data), uses default risk sizing.

        結合 Kelly、波動率調整和 P1 上限。
        最終建議 = min(kelly_qty, vol_adjusted_qty, max_allowed_qty)。
        任一組件為 0（數據不足）時使用默認風險倉位。

        Args:
            balance: Account balance in USDT.
            price: Current price.
            win_rate, avg_win, avg_loss, trade_count: For Kelly calculation.
            atr: For volatility adjustment.

        Returns:
            SizingRecommendation with all computed values.
        """
        rec = SizingRecommendation()
        rec.sample_size = trade_count
        rec.win_rate = win_rate

        if balance <= 0 or price <= 0:
            return rec

        # 1. Kelly fraction / Kelly 分數
        rec.kelly_fraction = self.compute_kelly_fraction(
            win_rate, avg_win, avg_loss, trade_count,
        )
        if avg_loss > 0:
            rec.payoff_ratio = abs(avg_win) / abs(avg_loss)

        # Kelly tier label / Kelly 層級標籤
        if trade_count < 50:
            rec.kelly_tier = "conservative"
        elif trade_count < 200:
            rec.kelly_tier = "moderate"
        else:
            rec.kelly_tier = "normal"

        # Kelly qty / Kelly 倉位
        if rec.kelly_fraction > 0:
            rec.kelly_qty = balance * rec.kelly_fraction / price
        else:
            # No edge → use minimum position for learning / 無優勢 → 用最小倉位學習
            rec.kelly_qty = balance * 0.005 / price  # 0.5% for learning

        # 2. Vol-adjusted qty / 波動率調整倉位
        if atr > 0:
            rec.vol_adjusted_qty = self.compute_volatility_adjusted_qty(
                balance, atr, price,
            )
        else:
            # No ATR data → use default risk sizing / 無 ATR 數據 → 用默認風險倉位
            rec.vol_adjusted_qty = balance * self._risk_pct_default / 100.0 / price

        # 3. P1 hard cap / P1 硬上限
        rec.max_allowed_qty = self.compute_max_allowed_qty(balance, price)

        # 4. Final recommendation = min of all valid components / 最終建議 = 所有有效組件最小值
        valid_qtys = [
            q for q in [rec.kelly_qty, rec.vol_adjusted_qty, rec.max_allowed_qty]
            if q > 0
        ]
        rec.recommended_qty = min(valid_qtys) if valid_qtys else 0.0

        return rec
