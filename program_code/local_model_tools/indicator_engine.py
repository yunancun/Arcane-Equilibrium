"""
STUB: Indicator Engine / 指标引擎 stub.

MODULE_NOTE (EN): Indicator computation runs in the Rust `openclaw_engine`
  tick pipeline. This Python class is retained only to keep
  `strategy_wiring.py` singleton instantiation working and to give
  `strategy_read_routes.py` a harmless Python fallback. All getters return
  empty data so callers fall back to the Rust reader.
MODULE_NOTE (中): 指标计算由 Rust `openclaw_engine` tick pipeline 承担。
  此 Python 类仅保留用于 `strategy_wiring.py` singleton 实例化与
  `strategy_read_routes.py` 降级备援；所有 getter 返回空值，让调用方
  自然落回 Rust reader。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from .indicators.base import IndicatorBase

logger = logging.getLogger(__name__)

IndicatorUpdateCallback = Callable[[str, str, dict[str, Any]], None]


class IndicatorEngine:
    def __init__(self, kline_manager: Any = None, indicators: list[IndicatorBase] | None = None) -> None:
        self._kline_manager = kline_manager
        self._indicators: list[IndicatorBase] = list(indicators or [])
        self._callbacks: list[IndicatorUpdateCallback] = []

    def register_indicator(self, indicator: IndicatorBase) -> None:
        self._indicators.append(indicator)

    def register_on_update(self, callback: IndicatorUpdateCallback) -> None:
        self._callbacks.append(callback)

    def get_indicators(self, symbol: str, timeframe: str) -> dict[str, Any]:
        return {}

    def get_indicator(self, symbol: str, timeframe: str, indicator_name: str) -> dict[str, Any] | None:
        return None

    def compute_now(self, symbol: str, timeframe: str) -> dict[str, Any]:
        return {}

    def get_all_cached(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_status(self) -> dict[str, Any]:
        return {
            "stub": True,
            "source": "rust_engine_primary",
            "indicators_registered": len(self._indicators),
        }

    def get_conservative_atr(self, symbol: str, timeframe: str = "1h") -> dict[str, float | None]:
        return {"atr": None, "atr_percent": None}

    def clear_cache(self) -> None:
        return None


__all__ = ["IndicatorEngine", "IndicatorUpdateCallback"]
