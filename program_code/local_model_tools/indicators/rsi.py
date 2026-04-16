"""STUB: RSI — computation moved to Rust openclaw_core::indicators::momentum."""
from __future__ import annotations

import logging
from typing import Any

from .base import IndicatorBase

logger = logging.getLogger(__name__)


class RSI(IndicatorBase):
    def __init__(self, period: int = 14) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"RSI({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period + 1

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("RSI stub: computation in Rust engine")
        return None


def compute_rsi(values: list[float], period: int = 14) -> float | None:
    return None


def compute_rsi_series(values: list[float], period: int = 14) -> list[float] | None:
    return None


__all__ = ["RSI", "compute_rsi", "compute_rsi_series"]
