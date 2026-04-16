"""
STUB: Strategy Orchestrator / 策略编排器 stub.

MODULE_NOTE (EN): Strategy lifecycle and intent collection are authoritative
  in Rust `openclaw_engine::orchestrator` + `::strategies`. Python class kept
  only so `strategy_wiring.py` can still create the ORCHESTRATOR singleton
  and `strategy_read_routes.py` / `strategy_write_routes.py` have a harmless
  fallback. All getters return empty, all write methods are no-ops.
MODULE_NOTE (中): 策略生命周期与 intent 收集真值源在 Rust
  `openclaw_engine::orchestrator` + `::strategies`。Python 类仅为 wiring
  singleton 与 read/write routes 降级备援保留；getter 返回空，写方法空操作。
"""
from __future__ import annotations

import logging
from typing import Any

from .strategies.base import (
    STRATEGY_ACTIVE,
    STRATEGY_IDLE,
    STRATEGY_PAUSED,
    STRATEGY_STOPPED,
    OrderIntent,
    StrategyBase,
)

logger = logging.getLogger(__name__)


class StrategyOrchestrator:
    def __init__(
        self,
        kline_manager: Any,
        indicator_engine: Any,
        signal_engine: Any,
        intent_history_capacity: int = 500,
    ) -> None:
        self._km = kline_manager
        self._ie = indicator_engine
        self._se = signal_engine
        self._intent_history_capacity = intent_history_capacity
        self._strategies: dict[str, StrategyBase] = {}
        self._ai_engine: Any = None
        self._ai_consultation_enabled = False

    def register_strategy(
        self, strategy: StrategyBase, name: str | None = None
    ) -> None:
        key = name or getattr(strategy, "name", str(id(strategy)))
        self._strategies[key] = strategy

    def activate_strategy(self, name: str) -> bool:
        strat = self._strategies.get(name)
        if strat is None:
            return False
        strat.activate()
        return True

    def pause_strategy(self, name: str) -> bool:
        strat = self._strategies.get(name)
        if strat is None:
            return False
        strat.pause()
        return True

    def stop_strategy(self, name: str) -> bool:
        strat = self._strategies.get(name)
        if strat is None:
            return False
        strat.stop()
        return True

    def remove_strategy(self, name: str) -> bool:
        return self._strategies.pop(name, None) is not None

    def collect_pending_intents(self) -> list[OrderIntent]:
        return []

    def get_strategy_status(self, name: str) -> dict[str, Any] | None:
        strat = self._strategies.get(name)
        if strat is None:
            return None
        try:
            return strat.get_status()
        except Exception:
            return {"name": name, "state": strat.state, "stub": True}

    def get_all_strategies_status(self) -> list[dict[str, Any]]:
        return []

    def notify_intent_rejected(self, intent: OrderIntent) -> None:
        return None

    def get_intent_history(self, n: int = 50) -> list[dict[str, Any]]:
        return []

    def get_status(self) -> dict[str, Any]:
        def _sub(obj: Any) -> dict[str, Any]:
            getter = getattr(obj, "get_status", None) or getattr(obj, "get_stats", None)
            if callable(getter):
                try:
                    return getter()
                except Exception:
                    return {"stub": True}
            return {"stub": True}

        return {
            "component": "strategy_orchestrator",
            "stub": True,
            "source": "rust_engine_primary",
            "registered_strategies": len(self._strategies),
            "strategies": [],
            "intent_history_size": 0,
            "kline_manager_status": _sub(self._km),
            "indicator_engine_status": _sub(self._ie),
            "signal_engine_status": _sub(self._se),
        }

    def compute_indicators(self, symbol: str, timeframe: str) -> None:
        return None

    def get_indicators(self, symbol: str, timeframe: str) -> dict[str, Any]:
        return {}

    def get_current_regime(self) -> str:
        return "unknown"

    def save_all_strategy_state(self) -> dict[str, Any]:
        return {}

    def restore_all_strategy_state(self, saved: dict[str, Any]) -> None:
        return None

    def list_available_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    def set_ai_engine(self, engine: Any) -> None:
        self._ai_engine = engine

    def request_ai_analysis(
        self, query: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        return None

    def dispatch_tick(self, symbol: str, price: float, ts_ms: int) -> None:
        return None

    def _on_signal(self, signal: Any) -> None:
        return None


__all__ = ["StrategyOrchestrator"]
