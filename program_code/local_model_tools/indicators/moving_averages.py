"""STUB: SMA/EMA — computation moved to Rust openclaw_core::indicators::trend."""
from __future__ import annotations

import logging
from typing import Any

from .base import IndicatorBase

logger = logging.getLogger(__name__)


class SMA(IndicatorBase):
    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"SMA({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("SMA stub: computation in Rust engine")
        return None


class EMA(IndicatorBase):
    def __init__(self, period: int = 12) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"EMA({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("EMA stub: computation in Rust engine")
        return None


def compute_sma(values: list[float], period: int) -> float | None:
    return None


def compute_ema(values: list[float], period: int) -> float | None:
    return None


def compute_sma_series(values: list[float], period: int) -> list[float] | None:
    return None


def compute_ema_series(values: list[float], period: int) -> list[float] | None:
    return None


__all__ = [
    "SMA",
    "EMA",
    "compute_sma",
    "compute_ema",
    "compute_sma_series",
    "compute_ema_series",
]
