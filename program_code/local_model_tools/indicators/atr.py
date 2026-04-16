"""STUB: ATR — computation moved to Rust openclaw_core::indicators::volatility."""
from __future__ import annotations

import logging
from typing import Any

from .base import IndicatorBase

logger = logging.getLogger(__name__)


class ATR(IndicatorBase):
    def __init__(self, period: int = 14) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"ATR({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("ATR stub: computation in Rust engine")
        return None


def compute_true_range(
    highs: list[float], lows: list[float], closes: list[float]
) -> list[float] | None:
    return None


def compute_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    return None


def compute_atr_percent(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    return None


__all__ = ["ATR", "compute_true_range", "compute_atr", "compute_atr_percent"]
