"""
Strategy Base Class / 策略基类

MODULE_NOTE (中文):
  所有交易策略的抽象基类。定义统一的策略生命周期接口：
  - on_signal(): 接收信号，决定是否行动
  - on_tick(): 定时检查（用于 Grid、Funding Rate 等需要主动检查的策略）
  - get_orders_to_submit(): 返回待提交的订单列表
  - get_status(): 返回策略当前状态

  策略不直接提交订单到 Paper Trading Engine。
  策略生成 OrderIntent（订单意图），由 Strategy Orchestrator 统一管理、
  风控检查后再提交。

  策略状态：
  - idle: 策略已注册但未启用
  - active: 策略正在运行，监听信号和行情
  - paused: 策略暂停（保留状态但不产生新订单意图）
  - stopped: 策略已停止（可清理状态后移除）

MODULE_NOTE (English):
  Abstract base class for all trading strategies. Defines a unified strategy
  lifecycle interface:
  - on_signal(): receive signals, decide whether to act
  - on_tick(): periodic check (for strategies needing proactive checks like Grid, Funding Rate)
  - get_orders_to_submit(): return list of pending order intents
  - get_status(): return current strategy state

  Strategies do NOT submit orders directly to Paper Trading Engine.
  Strategies generate OrderIntents, managed by Strategy Orchestrator,
  risk-checked, then submitted.

  Strategy states:
  - idle: registered but not enabled
  - active: running, listening to signals and market data
  - paused: paused (retains state but no new order intents)
  - stopped: stopped (can clean up and remove)

Safety invariant / 安全不变量:
  - 策略只产生 OrderIntent，不直接执行交易 / Strategies only generate OrderIntents
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Strategy States / 策略状态
# =============================================================================

STRATEGY_IDLE = "idle"
STRATEGY_ACTIVE = "active"
STRATEGY_PAUSED = "paused"
STRATEGY_STOPPED = "stopped"


# =============================================================================
# OrderIntent — What a strategy wants to do / 策略想要执行的操作
# =============================================================================

class OrderIntent:
    """
    A strategy's intention to place an order.
    策略下单意图。

    This is NOT an actual order — it's a request that will go through
    the Strategy Orchestrator → Risk Manager → Paper Trading Engine pipeline.
    这不是实际订单 — 它是一个请求，将经过策略编排器 → 风控管理器 → Paper Trading Engine 的管线。

    Attributes:
      symbol       — trading pair / 交易对
      side         — "Buy" or "Sell" / 买卖方向
      order_type   — "market", "limit", "conditional" / 订单类型
      qty          — order quantity / 数量
      price        — limit price (None for market) / 限价（市价单为 None）
      strategy_name — which strategy generated this / 生成此意图的策略
      reason       — human-readable reason / 人类可读的理由
      confidence   — signal confidence that triggered this / 触发的信号置信度
      metadata     — extra data / 额外数据
    """
    __slots__ = (
        "symbol", "side", "order_type", "qty", "price",
        "strategy_name", "reason", "confidence", "metadata",
    )

    def __init__(
        self,
        symbol: str,
        side: str,
        order_type: str = "market",
        qty: float = 0.0,
        price: float | None = None,
        strategy_name: str = "",
        reason: str = "",
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.symbol = symbol
        self.side = side  # "Buy" or "Sell"
        self.order_type = order_type
        self.qty = qty
        self.price = price
        self.strategy_name = strategy_name
        self.reason = reason
        self.confidence = confidence
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "qty": self.qty,
            "price": self.price,
            "strategy_name": self.strategy_name,
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"OrderIntent({self.symbol} {self.side} {self.order_type} "
            f"qty={self.qty} price={self.price} src={self.strategy_name})"
        )


# =============================================================================
# StrategyBase — Abstract Base / 策略抽象基类
# =============================================================================

class StrategyBase(ABC):
    """
    Abstract base class for all trading strategies.
    所有交易策略的抽象基类。
    """

    def __init__(self) -> None:
        self._state = STRATEGY_IDLE
        self._pending_intents: list[OrderIntent] = []
        self._intent_lock = threading.RLock()  # RLock: reentrant, allows on_signal to hold lock while calling _emit_intent / 可重入锁
        self._realized_pnl: float = 0.0
        self._unrealized_pnl: float = 0.0
        self._total_fees: float = 0.0
        self._trade_history: list[dict[str, Any]] = []
        self._max_trade_history: int = 200

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name / 策略名称"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Strategy description (Chinese + English) / 策略描述"""
        ...

    @property
    def state(self) -> str:
        """Current strategy state / 当前策略状态"""
        return self._state

    def activate(self) -> None:
        """Activate the strategy (from idle or paused) / 激活策略（从 idle 或 paused）"""
        if self._state == STRATEGY_STOPPED:
            logger.warning(
                "Cannot activate stopped strategy, re-register instead / "
                "无法激活已停止的策略，请重新注册"
            )
            return
        self._state = STRATEGY_ACTIVE

    def pause(self) -> None:
        """Pause the strategy (from active) / 暂停策略（从 active）"""
        if self._state != STRATEGY_ACTIVE:
            logger.warning(
                "Cannot pause non-active strategy (state=%s) / "
                "无法暂停非活跃策略（状态=%s）", self._state, self._state,
            )
            return
        self._state = STRATEGY_PAUSED

    def stop(self) -> None:
        """Stop the strategy / 停止策略"""
        self._state = STRATEGY_STOPPED
        with self._intent_lock:
            self._pending_intents.clear()

    def on_signal(self, signal: Any) -> None:
        """
        Handle a trading signal / 处理交易信号

        Override to implement signal-based strategy logic.
        重写以实现基于信号的策略逻辑。

        Args:
          signal — Signal object from SignalEngine / 来自 SignalEngine 的信号对象
        """
        pass  # Default: do nothing / 默认：不做任何事

    def on_tick(self, symbol: str, price: float, ts_ms: int) -> None:
        """
        Handle a price tick / 处理价格 tick

        Override for strategies that need periodic checks (Grid, Funding Rate).
        重写给需要定期检查的策略（Grid、Funding Rate）。

        Args:
          symbol — trading pair / 交易对
          price  — current price / 当前价格
          ts_ms  — timestamp in ms / 毫秒时间戳
        """
        pass  # Default: do nothing / 默认：不做任何事

    def get_pending_intents(self) -> list[OrderIntent]:
        """
        Get and clear pending order intents / 获取并清空待处理的订单意图

        Thread-safe: protected by _intent_lock.
        线程安全：受 _intent_lock 保护。

        Returns:
          List of OrderIntents generated since last call / 上次调用后生成的 OrderIntent 列表
        """
        with self._intent_lock:
            intents = list(self._pending_intents)
            self._pending_intents.clear()
        return intents

    @property
    def pending_intent_count(self) -> int:
        """Number of pending intents / 待处理意图数量"""
        with self._intent_lock:
            return len(self._pending_intents)

    def _emit_intent(self, intent: OrderIntent) -> None:
        """
        Internal: add an order intent to the pending queue / 内部：添加订单意图到待处理队列

        Only emits if strategy is active. Thread-safe.
        仅在策略激活状态时生效。线程安全。
        """
        if self._state == STRATEGY_ACTIVE:
            with self._intent_lock:
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
        """
        Record a completed trade result for PnL tracking.
        记录已完成的交易结果用于 PnL 跟踪。
        """
        if side.lower() in ("buy", "long"):
            pnl = (exit_price - entry_price) * qty - fee
        else:
            pnl = (entry_price - exit_price) * qty - fee

        self._realized_pnl += pnl
        self._total_fees += fee

        record = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": round(pnl, 4),
            "fee": round(fee, 4),
            "reason": reason,
            "ts_ms": int(time.time() * 1000),
        }
        self._trade_history.append(record)
        if len(self._trade_history) > self._max_trade_history:
            self._trade_history = self._trade_history[-self._max_trade_history:]

    def get_pnl_summary(self) -> dict[str, Any]:
        """Get strategy PnL summary / 获取策略 PnL 摘要"""
        wins = [t for t in self._trade_history if t["pnl"] > 0]
        losses = [t for t in self._trade_history if t["pnl"] <= 0]
        return {
            "realized_pnl": round(self._realized_pnl, 4),
            "total_fees": round(self._total_fees, 4),
            "net_pnl": round(self._realized_pnl - self._total_fees, 4),
            "trade_count": len(self._trade_history),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(self._trade_history), 4) if self._trade_history else 0.0,
            "avg_win": round(sum(t["pnl"] for t in wins) / len(wins), 4) if wins else 0.0,
            "avg_loss": round(sum(t["pnl"] for t in losses) / len(losses), 4) if losses else 0.0,
        }

    def get_persistent_state(self) -> dict[str, Any]:
        """
        Get strategy state that should survive restarts.
        获取需要在重启后保留的策略状态。

        Override in subclasses to include strategy-specific state.
        子类重写以包含策略特定状态。
        """
        return {
            "name": self.name,
            "state": self._state,
            "realized_pnl": self._realized_pnl,
            "total_fees": self._total_fees,
        }

    def restore_persistent_state(self, saved: dict[str, Any]) -> None:
        """
        Restore strategy state from a previous save.
        从之前的保存中恢复策略状态。

        Override in subclasses to restore strategy-specific state.
        子类重写以恢复策略特定状态。
        """
        if saved.get("state") == STRATEGY_ACTIVE:
            self._state = STRATEGY_ACTIVE
        self._realized_pnl = saved.get("realized_pnl", 0.0)
        self._total_fees = saved.get("total_fees", 0.0)

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Get strategy-specific status / 获取策略特定状态"""
        ...
