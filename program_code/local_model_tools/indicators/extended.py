"""STUB: Extended indicators — computation moved to Rust openclaw_core::indicators."""
from __future__ import annotations

import logging
from typing import Any

from .base import IndicatorBase

logger = logging.getLogger(__name__)


class KAMA(IndicatorBase):
    def __init__(self, period: int = 10, fast_sc: int = 2, slow_sc: int = 30) -> None:
        self._period = period
        self._fast_sc = fast_sc
        self._slow_sc = slow_sc

    @property
    def name(self) -> str:
        return f"KAMA({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period + 1

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("KAMA stub: computation in Rust engine")
        return None


class ADX(IndicatorBase):
    def __init__(self, period: int = 14) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"ADX({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period * 2 + 1

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("ADX stub: computation in Rust engine")
        return None


class HurstIndicator(IndicatorBase):
    def __init__(self, min_lag: int = 10, max_lag: int = 50) -> None:
        self._min_lag = min_lag
        self._max_lag = max_lag

    @property
    def name(self) -> str:
        return "Hurst"

    @property
    def min_periods(self) -> int:
        return self._max_lag + 1

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("HurstIndicator stub: computation in Rust engine")
        return None


class EWMAVolIndicator(IndicatorBase):
    def __init__(self, timeframe: str = "1h") -> None:
        self._timeframe = timeframe

    @property
    def name(self) -> str:
        return f"EWMA_Vol({self._timeframe})"

    @property
    def min_periods(self) -> int:
        return 5

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("EWMAVolIndicator stub: computation in Rust engine")
        return None


class VolumeRatio(IndicatorBase):
    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"VolumeRatio({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("VolumeRatio stub: computation in Rust engine")
        return None


class DonchianChannel(IndicatorBase):
    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"Donchian({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        logger.debug("DonchianChannel stub: computation in Rust engine")
        return None


__all__ = [
    "KAMA",
    "ADX",
    "HurstIndicator",
    "EWMAVolIndicator",
    "VolumeRatio",
    "DonchianChannel",
]
