"""STUB: Bollinger Bands — computation moved to Rust openclaw_core::indicators::volatility."""
from __future__ import annotations

import logging
from typing import Any

from .base import IndicatorBase

logger = logging.getLogger(__name__)


class BollingerBands(IndicatorBase):
    def __init__(self, period: int = 20, std_dev_multiplier: float = 2.0) -> None:
        self._period = period
        self._std_dev_multiplier = std_dev_multiplier

    @property
    def name(self) -> str:
        return f"BB({self._period},{self._std_dev_multiplier})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("BollingerBands stub: computation in Rust engine")
        return None


def compute_bollinger_bands(
    values: list[float],
    period: int = 20,
    std_dev_multiplier: float = 2.0,
) -> dict[str, Any] | None:
    return None


def compute_stddev(values: list[float], period: int) -> float | None:
    return None


__all__ = ["BollingerBands", "compute_bollinger_bands", "compute_stddev"]
