"""
STUB: BacktestEngine / 回测引擎 stub.

MODULE_NOTE (EN): Backtest is authoritative in Rust `openclaw_core::backtest`.
  This Python class exists only so `backtest_routes.py`, `evolution_engine.py`
  and `evolution_auto_scheduler.py` can still import + instantiate without
  crashing. `run()` returns a zero-filled BacktestResult with a warning,
  giving downstream evolution code a deterministic no-op.
MODULE_NOTE (中): 回测真值源在 Rust `openclaw_core::backtest`。Python 类仅
  为让 `backtest_routes.py`、`evolution_engine.py`、`evolution_auto_scheduler.py`
  继续能 import + 实例化；`run()` 返回带 warning 的零值 BacktestResult，下游
  演化代码能得到确定性的空操作结果。
"""
from __future__ import annotations

import logging
from typing import Any

from .backtest_types import (
    ANNUALIZATION_FACTORS,
    MIN_BARS_REQUIRED,
    MIN_TRADES_FOR_STATS,
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
)

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(
        self,
        kline_manager: Any = None,
        indicator_engine: Any = None,
        signal_engine: Any = None,
    ) -> None:
        self._kline_manager = kline_manager
        self._indicator_engine = indicator_engine
        self._signal_engine = signal_engine
        self._last_result: BacktestResult | None = None

    def run(
        self,
        config: BacktestConfig,
        ohlcv_data: dict[str, list[float]] | None = None,
    ) -> BacktestResult:
        if not getattr(config, "backtest_mode", False):
            raise ValueError("BacktestConfig.backtest_mode must be True")
        logger.debug(
            "BacktestEngine stub: returning empty result for %s/%s (%s)",
            config.symbol,
            config.timeframe,
            config.strategy_name,
        )
        result = BacktestResult(
            symbol=config.symbol,
            timeframe=config.timeframe,
            strategy_name=config.strategy_name,
            initial_capital=config.initial_capital,
            final_capital=config.initial_capital,
            config=config,
            warning="backtest stubbed — run in Rust openclaw_core::backtest",
        )
        self._last_result = result
        return result

    def get_last_result(self) -> BacktestResult | None:
        return self._last_result

    def get_status(self) -> dict[str, Any]:
        return {
            "stub": True,
            "source": "rust_engine_primary",
            "last_result_available": self._last_result is not None,
        }


__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "ANNUALIZATION_FACTORS",
    "MIN_BARS_REQUIRED",
    "MIN_TRADES_FOR_STATS",
]
