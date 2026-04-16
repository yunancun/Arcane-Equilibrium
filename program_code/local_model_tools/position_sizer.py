"""
STUB: Position Sizer / 倉位計算 stub.

MODULE_NOTE (EN): Kelly sizing and risk-adjusted qty calc live in Rust
  `openclaw_engine::position_manager` + `risk_checks`. Python class retained
  for `strategy_auto_deployer.py` compatibility; methods return zero qty
  so Rust sizing remains authoritative.
MODULE_NOTE (中): Kelly 倉位與風險調整計算已遷移至 Rust
  `openclaw_engine::position_manager` 與 `risk_checks`。Python 類保留以兼容
  `strategy_auto_deployer.py`，方法返回零值，真值源仍是 Rust。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SizingRecommendation:
    kelly_fraction: float = 0.0
    kelly_qty: float = 0.0
    vol_adjusted_qty: float = 0.0
    max_allowed_qty: float = 0.0
    recommended_qty: float = 0.0
    sample_size: int = 0
    kelly_tier: str = "conservative"
    win_rate: float = 0.0
    payoff_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kelly_fraction": self.kelly_fraction,
            "kelly_qty": self.kelly_qty,
            "vol_adjusted_qty": self.vol_adjusted_qty,
            "max_allowed_qty": self.max_allowed_qty,
            "recommended_qty": self.recommended_qty,
            "sample_size": self.sample_size,
            "kelly_tier": self.kelly_tier,
            "win_rate": self.win_rate,
            "payoff_ratio": self.payoff_ratio,
            "stub": True,
        }


class PositionSizer:
    def __init__(
        self,
        *,
        p1_max_pct: float = 2.0,
        risk_pct_default: float = 3.0,
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
        return 0.0

    def compute_volatility_adjusted_qty(
        self,
        balance: float,
        atr: float,
        price: float,
        risk_pct: float | None = None,
    ) -> float:
        return 0.0

    def compute_risk_parity_weights(
        self, volatilities: dict[str, float]
    ) -> dict[str, float]:
        return {}

    def compute_max_allowed_qty(self, balance: float, price: float) -> float:
        return 0.0

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
        unrealized_pnl: float = 0.0,
    ) -> SizingRecommendation:
        return SizingRecommendation(sample_size=trade_count, win_rate=win_rate)


__all__ = ["SizingRecommendation", "PositionSizer"]
