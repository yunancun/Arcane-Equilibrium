"""STUB: MACD — computation moved to Rust openclaw_core::indicators::momentum."""
from __future__ import annotations

import logging
from typing import Any

from .base import IndicatorBase

logger = logging.getLogger(__name__)


class MACD(IndicatorBase):
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> None:
        self._fast = fast_period
        self._slow = slow_period
        self._signal = signal_period

    @property
    def name(self) -> str:
        return f"MACD({self._fast},{self._slow},{self._signal})"

    @property
    def min_periods(self) -> int:
        return self._slow + self._signal

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("MACD stub: computation in Rust engine")
        return None


def compute_macd(
    values: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, Any] | None:
    return None


__all__ = ["MACD", "compute_macd"]
