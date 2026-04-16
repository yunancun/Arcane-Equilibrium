"""
STUB: Strategy Auto-Deployer / 策略自动部署器 stub.

MODULE_NOTE (EN): Scanner-driven deployment, Kelly sizing, and evolution
  application all run in the Rust engine (scanner + orchestrator + strategy
  lifecycle). The Python class is retained purely for API surface
  compatibility: `strategy_read_routes.py`, `strategy_write_routes.py`,
  `evolution_routes.py`, and `strategy_wiring.py` continue to import and
  call it. All methods are no-ops or return empty data.
MODULE_NOTE (中): 扫描驱动部署、Kelly 倉位、演化应用均由 Rust engine 承担。
  Python 类仅保留 API 表面，让 read/write/evolution routes 与 wiring 正常
  import + 调用；方法全部空操作或返回空。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CATEGORY_PRIORITY_BONUS: dict[str, int] = {
    "funding_arb": 50,
    "grid": 20,
    "reversion": 10,
    "trend": 0,
    "breakout": 0,
}


class StrategyAutoDeployer:
    def __init__(
        self,
        orchestrator: Any,
        kline_manager: Any,
        paper_engine: Any = None,
        *,
        max_symbols: int = 25,
        risk_per_trade_pct: float = 3.0,
        min_qty_usdt: float = 10.0,
        max_qty_pct: float = 10.0,
        market_feed_add_fn: Any = None,
        pinned_symbols: list[str] | None = None,
        reserved_slots: dict[str, int] | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._km = kline_manager
        self._paper_engine = paper_engine
        self._max_symbols = max_symbols
        self._risk_pct = risk_per_trade_pct
        self._min_qty_usdt = min_qty_usdt
        self._max_qty_pct = max_qty_pct
        self._market_feed_add_fn = market_feed_add_fn
        self._pinned_symbols = list(pinned_symbols or [])
        self._reserved_slots = dict(reserved_slots or {})
        self._backtest_engine: Any = None
        self._min_sharpe: float = 0.0
        self._pipeline_bridge: Any = None
        self._dynamic_risk_enabled = False

    def set_backtest_engine(self, engine: Any, min_sharpe: float = 0.0) -> None:
        self._backtest_engine = engine
        self._min_sharpe = min_sharpe

    def on_scan_results(self, opportunities: list[Any]) -> None:
        # DEPRECATED 2026-04-10: scan-driven deployment moved to Rust scanner.
        return None

    def apply_evolution_result(self, result: dict) -> bool:
        return False

    def update_risk_from_sharpe(self) -> None:
        return None

    def get_dynamic_risk_status(self) -> dict[str, Any]:
        return {
            "stub": True,
            "enabled": self._dynamic_risk_enabled,
            "risk_pct": self._risk_pct,
        }

    def set_dynamic_risk_enabled(self, enabled: bool) -> None:
        self._dynamic_risk_enabled = bool(enabled)

    def compute_dynamic_qty(self, symbol: str, price: float) -> float:
        return 0.0

    def notify_fill(self, strategy_name: str, fill: dict, is_open: bool) -> None:
        return None

    def on_trade_result(self, strategy_name: str, close_pnl: float) -> None:
        return None

    def remove_stale_strategies(self, active_symbols: set[str]) -> None:
        return None

    def set_pipeline_bridge(self, bridge: Any) -> None:
        self._pipeline_bridge = bridge

    def get_deployed(self) -> list[dict[str, Any]]:
        return []

    def get_kelly_recommendations(self) -> dict[str, Any]:
        return {"stub": True, "recommendations": {}}

    def get_stats(self) -> dict[str, Any]:
        return {
            "stub": True,
            "source": "rust_engine_primary",
            "max_symbols": self._max_symbols,
            "risk_pct": self._risk_pct,
        }


__all__ = ["StrategyAutoDeployer", "CATEGORY_PRIORITY_BONUS"]
