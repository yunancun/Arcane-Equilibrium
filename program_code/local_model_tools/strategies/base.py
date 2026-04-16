"""
STUB: Strategy base class / 策略基类 stub.

MODULE_NOTE (EN): Strategy implementations live in Rust
  `rust/openclaw_engine/src/strategies/`. The Python abstract base is
  retained only for legacy type hints / imports. All behavior is no-op.
MODULE_NOTE (中): 策略实现已迁移至 Rust `openclaw_engine::strategies`。
  Python 抽象基类仅为兼容旧 import 与类型标注保留，行为全部无操作。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

STRATEGY_IDLE = "idle"
STRATEGY_ACTIVE = "active"
STRATEGY_PAUSED = "paused"
STRATEGY_STOPPED = "stopped"


class OrderIntent:
    __slots__ = (
        "symbol",
        "side",
        "order_type",
        "qty",
        "price",
        "strategy_name",
        "reason",
        "confidence",
        "metadata",
        "_history_ref",
    )

    def __init__(
        self,
        symbol: str,
        side: str,
        order_type: str = "limit",
        qty: float = 0.0,
        price: float | None = None,
        strategy_name: str = "",
        reason: str = "",
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.qty = qty
        self.price = price
        self.strategy_name = strategy_name
        self.reason = reason
        self.confidence = confidence
        self.metadata = dict(metadata) if metadata else {}
        self._history_ref = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "qty": self.qty,
            "price": self.price,
            "strategy_name": self.strategy_name,
            "reason": self.reason,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"<OrderIntent stub {self.symbol} {self.side} qty={self.qty} "
            f"strat={self.strategy_name}>"
        )


class StrategyBase(ABC):
    def __init__(self) -> None:
        self._state = STRATEGY_IDLE
        self._registered_name = ""
        self._pending_intents: list[OrderIntent] = []

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def registered_name(self) -> str:
        return self._registered_name or self.name

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    def state(self) -> str:
        return self._state

    def activate(self) -> None:
        self._state = STRATEGY_ACTIVE

    def pause(self) -> None:
        self._state = STRATEGY_PAUSED

    def stop(self) -> None:
        self._state = STRATEGY_STOPPED

    def on_signal(self, signal: Any) -> None:
        return None

    def on_tick(self, symbol: str, price: float, ts_ms: int) -> None:
        return None

    def on_fill(self, fill: dict, is_open: bool) -> None:
        return None

    def get_pending_intents(self) -> list[OrderIntent]:
        drained, self._pending_intents = self._pending_intents, []
        return drained

    @property
    def pending_intent_count(self) -> int:
        return len(self._pending_intents)

    def on_intent_rejected(self, intent: OrderIntent) -> None:
        return None

    def _emit_intent(self, intent: OrderIntent) -> None:
        self._pending_intents.append(intent)

    def record_trade_result(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        exit_price: float,
        fee: float = 0.0,
        reason: str = "",
    ) -> None:
        return None

    def get_pnl_summary(self) -> dict[str, Any]:
        return {"stub": True, "net_pnl": 0.0, "trades": 0}

    def get_persistent_state(self) -> dict[str, Any]:
        return {}

    def restore_persistent_state(self, saved: dict[str, Any]) -> None:
        return None

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        ...


__all__ = [
    "STRATEGY_IDLE",
    "STRATEGY_ACTIVE",
    "STRATEGY_PAUSED",
    "STRATEGY_STOPPED",
    "OrderIntent",
    "StrategyBase",
]
