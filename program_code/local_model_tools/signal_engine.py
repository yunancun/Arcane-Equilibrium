"""
STUB: Signal Engine / 信号引擎 stub.

MODULE_NOTE (EN): Signal evaluation and routing live in Rust
  `openclaw_core::signals`. This Python class is retained only for legacy
  wiring in `strategy_wiring.py` and the Python-fallback branches of
  `strategy_read_routes.py`. All getters return empty data.
MODULE_NOTE (中): 信号评估与路由已迁移至 Rust `openclaw_core::signals`。
  此 Python 类仅为 `strategy_wiring.py` 旧 wiring 与
  `strategy_read_routes.py` 降级备援保留；所有 getter 返回空值。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _get_signal_types():  # pragma: no cover - lazy to avoid import cycle
    from .signal_generator import Signal, SignalRule, SIGNAL_HISTORY_CAPACITY

    return Signal, SignalRule, SIGNAL_HISTORY_CAPACITY


SignalCallback = Callable[[Any], None]


class SignalEngine:
    def __init__(self, rules: list[Any] | None = None, history_capacity: int | None = None) -> None:
        _, _, default_cap = _get_signal_types()
        self._rules: list[Any] = list(rules or [])
        self._history_capacity = history_capacity if history_capacity is not None else default_cap
        self._callbacks: list[SignalCallback] = []

    def register_rule(self, rule: Any) -> None:
        self._rules.append(rule)

    def register_on_signal(self, callback: SignalCallback) -> None:
        self._callbacks.append(callback)

    def on_indicators_update(
        self, symbol: str, timeframe: str, indicators: dict[str, Any]
    ) -> list[Any]:
        return []

    def get_latest_signals(
        self, symbol: str | None = None, n: int = 20
    ) -> list[dict[str, Any]]:
        return []

    def get_latest_for_symbol(self, symbol: str) -> dict[str, dict[str, Any]]:
        return {}

    def get_signal_summary(self, symbol: str) -> dict[str, Any]:
        # consensus_direction preserves legacy route contract; fallback path has
        # no signals so we always report "neutral".
        # 保留舊路由契約鍵名 consensus_direction；stub 無信號恆回 neutral。
        return {
            "symbol": symbol,
            "stub": True,
            "source": "rust_engine_primary",
            "signals": [],
            "consensus_direction": "neutral",
            "long_score": 0.0,
            "short_score": 0.0,
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "stub": True,
            "source": "rust_engine_primary",
            "rules_registered": len(self._rules),
            "history_capacity": self._history_capacity,
        }

    def clear_history(self) -> None:
        return None


__all__ = ["SignalEngine", "SignalCallback"]
