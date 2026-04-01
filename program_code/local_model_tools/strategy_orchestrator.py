"""
Strategy Orchestrator — Agent's Strategy Management Hub
策略编排器 — Agent 策略管理中枢

MODULE_NOTE (中文):
  策略编排器是 Phase 2 的顶层控制器，统一管理所有交易策略的生命周期。
  它连接四大组件：
  1. KlineManager — K线数据（通过 IndicatorEngine 间接连接）
  2. IndicatorEngine — 技术指标
  3. SignalEngine — 交易信号
  4. 各策略实例 — MA Crossover / BB Reversion / Funding Rate / Grid Trading

  职责：
  - 管理策略的注册、激活、暂停、停止
  - 将信号分发给相关策略
  - 收集策略产生的 OrderIntent
  - 统一的状态查询和统计
  - 为未来的 Paper Trading Engine 集成提供接口

  Agent 自主权体现：
  - Agent 可自由选择启用/停用哪些策略
  - Agent 可调整策略参数（在用户设定的风控上限内）
  - Agent 可根据市场 regime 动态切换策略组合

  数据流：
    WebSocket tick
      → KlineManager → IndicatorEngine → SignalEngine
        → StrategyOrchestrator.on_signal() → 各策略
          → OrderIntents 收集
            → [未来] Paper Trading Engine

MODULE_NOTE (English):
  The Strategy Orchestrator is the top-level controller for Phase 2,
  managing the lifecycle of all trading strategies.
  It connects four major components:
  1. KlineManager — kline data (via IndicatorEngine)
  2. IndicatorEngine — technical indicators
  3. SignalEngine — trading signals
  4. Strategy instances — MA Crossover / BB Reversion / Funding Rate / Grid Trading

  Responsibilities:
  - Manage strategy registration, activation, pause, stop
  - Dispatch signals to relevant strategies
  - Collect OrderIntents from strategies
  - Unified status query and statistics
  - Interface for future Paper Trading Engine integration

  Agent autonomy:
  - Agent freely chooses which strategies to enable/disable
  - Agent adjusts strategy parameters (within user-set risk limits)
  - Agent dynamically switches strategy mix based on market regime

Safety invariant / 安全不变量:
  - 编排器本身不直接下单 / Orchestrator does not place orders directly
  - 所有 OrderIntent 需经风控检查 / All OrderIntents must pass risk checks
  - system_mode = read_only 不变 / system_mode remains read_only
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from .signal_generator import Signal, SignalEngine
from .indicator_engine import IndicatorEngine
from .kline_manager import KlineManager
from .strategies.base import StrategyBase, OrderIntent, STRATEGY_ACTIVE

logger = logging.getLogger(__name__)


# =============================================================================
# StrategyOrchestrator / 策略编排器
# =============================================================================

class StrategyOrchestrator:
    """
    Top-level strategy management hub.
    顶层策略管理中枢。

    Orchestrates the full pipeline:
      KlineManager → IndicatorEngine → SignalEngine → Strategies → OrderIntents
    编排完整管线：
      K线管理器 → 指标引擎 → 信号引擎 → 策略 → 订单意图

    Usage:
      # Create components / 创建组件
      km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m", "5m", "1h"])
      ie = IndicatorEngine(kline_manager=km)
      se = SignalEngine()
      ie.register_on_update(se.on_indicators_update)

      # Create orchestrator / 创建编排器
      orch = StrategyOrchestrator(
          kline_manager=km, indicator_engine=ie, signal_engine=se,
      )

      # Register strategies / 注册策略
      orch.register_strategy(MACrossoverStrategy(symbol="BTCUSDT"))
      orch.register_strategy(GridTradingStrategy(symbol="BTCUSDT", ...))

      # Activate a strategy / 激活策略
      orch.activate_strategy("MA_Crossover")

      # Feed data — everything flows automatically / 输入数据 — 一切自动流转
      km.on_price_event(price_event)

      # Collect pending order intents / 收集待处理订单意图
      intents = orch.collect_pending_intents()
    """

    def __init__(
        self,
        kline_manager: KlineManager,
        indicator_engine: IndicatorEngine,
        signal_engine: SignalEngine,
        intent_history_capacity: int = 500,
    ) -> None:
        self._km = kline_manager
        self._ie = indicator_engine
        self._se = signal_engine
        self._lock = threading.Lock()

        # Registered strategies: name → StrategyBase
        # 注册的策略：名称 → 策略实例
        self._strategies: dict[str, StrategyBase] = {}

        # Auto-incrementing strategy ID counter / 自增策略编号计数器
        self._next_strategy_id: int = 1

        # Collected order intents / 收集的订单意图
        self._pending_intents: list[OrderIntent] = []

        # Intent history (for audit) — bounded deque / 意图历史（审计用）— 有界 deque
        self._intent_history: deque[dict[str, Any]] = deque(maxlen=intent_history_capacity)

        # Current regime context (cached from Regime_Detector signals)
        # 当前 regime 上下文（从 Regime_Detector 信号缓存）
        self._current_regime: str = "unknown"
        self._current_regime_ts_ms: int = 0

        # AI consultation (optional Layer 2 engine reference)
        # AI 咨询（可选的 Layer 2 引擎引用）
        self._ai_engine: Any = None
        self._ai_consultation_enabled: bool = False

        # Statistics / 统计
        self._stats = {
            "signals_dispatched": 0,
            "intents_collected": 0,
            "strategies_activated": 0,
        }

        # Wire up: signal engine → orchestrator.on_signal
        # 连接：信号引擎 → 编排器.on_signal
        self._se.register_on_signal(self._on_signal)

        logger.info("StrategyOrchestrator initialized / 策略编排器初始化完成")

    # ── Strategy Management / 策略管理 ──

    def register_strategy(self, strategy: StrategyBase, name: str | None = None) -> None:
        """
        Register a strategy instance / 注册策略实例

        The strategy starts in idle state. Call activate_strategy() to enable it.
        策略以 idle 状态注册。调用 activate_strategy() 激活。

        Args:
          strategy — strategy instance / 策略实例
          name     — optional custom registration key. If provided, sets
                     strategy._custom_name so registered_name reflects it.
                     可选的自定义注册键。若提供，会设置 strategy._custom_name。
        """
        if name is not None:
            strategy._custom_name = name
        key = strategy.registered_name
        with self._lock:
            old = self._strategies.get(key)
            if old is not None:
                logger.warning(
                    "Strategy %s already registered, stopping old + replacing / 策略 %s 已注册，停止旧策略并替换",
                    key, key,
                )
                # Preserve the existing ID when replacing / 替换时保留旧编号
                strategy.strategy_id = old.strategy_id
                old.stop()
            else:
                # Assign new auto-incrementing ID / 分配新的自增编号
                strategy.strategy_id = self._next_strategy_id
                self._next_strategy_id += 1
            self._strategies[key] = strategy
        logger.info("Registered strategy #%d / 注册策略 #%d: %s", strategy.strategy_id, strategy.strategy_id, key)

    def activate_strategy(self, name: str) -> bool:
        """
        Activate a registered strategy / 激活已注册的策略

        Returns True if successful, False if strategy not found.
        成功返回 True，未找到策略返回 False。
        """
        with self._lock:
            strategy = self._strategies.get(name)
            if strategy is None:
                logger.warning("Strategy not found / 策略未找到: %s", name)
                return False
            strategy.activate()
            self._stats["strategies_activated"] += 1
        logger.info("Activated strategy / 激活策略: %s", name)
        return True

    def pause_strategy(self, name: str) -> bool:
        """Pause a running strategy / 暂停运行中的策略"""
        with self._lock:
            strategy = self._strategies.get(name)
            if strategy is None:
                return False
            strategy.pause()
        logger.info("Paused strategy / 暂停策略: %s", name)
        return True

    def stop_strategy(self, name: str) -> bool:
        """Stop a strategy / 停止策略"""
        with self._lock:
            strategy = self._strategies.get(name)
            if strategy is None:
                return False
            strategy.stop()
        logger.info("Stopped strategy / 停止策略: %s", name)
        return True

    def remove_strategy(self, name: str) -> bool:
        """Remove a strategy from registration / 移除注册的策略"""
        with self._lock:
            if name in self._strategies:
                self._strategies[name].stop()
                del self._strategies[name]
                logger.info("Removed strategy / 移除策略: %s", name)
                return True
        return False

    # ── Signal Dispatch / 信号分发 ──

    def _on_signal(self, signal: Signal) -> None:
        """
        Internal: dispatch a signal to all active strategies.
        内部：将信号分发给所有活跃策略。

        Called by SignalEngine via callback.
        由 SignalEngine 通过回调调用。
        """
        with self._lock:
            active_strategies = [
                s for s in self._strategies.values()
                if s.state == STRATEGY_ACTIVE
            ]
            self._stats["signals_dispatched"] += 1

            # Cache regime info for strategy use / 缓存 regime 信息供策略使用
            if signal.source == "Regime_Detector" and signal.metadata:
                self._current_regime = signal.metadata.get("regime", "unknown")
                self._current_regime_ts_ms = signal.ts_ms

            # Enrich signal with current regime context / 用当前 regime 上下文丰富信号
            # Fix P0-A1: use `is not None` instead of truthiness check — empty dict {} is falsy
            # but is a valid metadata container that needs _regime injection.
            # 修复 P0-A1：改用 `is not None` 而非真值检查 — 空字典 {} 为 falsy，
            # 但它是有效的 metadata 容器，需要注入 _regime。
            if hasattr(signal, "metadata") and signal.metadata is not None and self._current_regime != "unknown":
                signal.metadata["_regime"] = self._current_regime

        for strategy in active_strategies:
            try:
                strategy.on_signal(signal)
            except Exception:
                logger.exception(
                    "Strategy signal handling error / 策略信号处理异常: %s",
                    strategy.name,
                )

    def dispatch_tick(self, symbol: str, price: float, ts_ms: int) -> None:
        """
        Dispatch a price tick to all active strategies.
        将价格 tick 分发给所有活跃策略。

        Used for tick-driven strategies (Grid Trading, etc.).
        用于 tick 驱动的策略（网格交易等）。

        Args:
          symbol — trading pair / 交易对
          price  — current price / 当前价格
          ts_ms  — timestamp / 时间戳
        """
        with self._lock:
            active_strategies = [
                s for s in self._strategies.values()
                if s.state == STRATEGY_ACTIVE
            ]

        for strategy in active_strategies:
            try:
                strategy.on_tick(symbol, price, ts_ms)
            except Exception:
                logger.exception(
                    "Strategy tick handling error / 策略 tick 处理异常: %s",
                    strategy.name,
                )

    # ── Intent Collection / 意图收集 ──

    def collect_pending_intents(self) -> list[OrderIntent]:
        """
        Collect all pending OrderIntents from all strategies.
        从所有策略收集待处理的 OrderIntent。

        Returns the intents and clears them from the strategies.
        返回意图并从策略中清除。

        Each intent gets a `_history_ref` attribute pointing to its history dict,
        allowing PipelineBridge to update status after processing.
        每个 intent 获得 `_history_ref` 属性，指向历史记录 dict，
        允许 PipelineBridge 在处理后更新状态。
        """
        all_intents: list[OrderIntent] = []

        with self._lock:
            for strategy in self._strategies.values():
                intents = strategy.get_pending_intents()
                all_intents.extend(intents)

            # Record in history (deque auto-trims at maxlen) / 记录到历史（deque 自动裁剪）
            # Attach history dict ref to each intent for downstream status updates
            # 将历史 dict 引用附加到每个 intent，供下游更新状态
            now_ms = int(time.time() * 1000)
            for intent in all_intents:
                history_entry = {
                    **intent.to_dict(),
                    "collected_ts_ms": now_ms,
                    "status": "pending",
                }
                self._intent_history.append(history_entry)
                intent._history_ref = history_entry

            # Detect conflicting intents for same symbol (different strategies, opposite sides)
            # 检测同一交易对的冲突意图（不同策略、相反方向）
            symbols_sides: dict[str, set[str]] = {}
            for intent in all_intents:
                sides = symbols_sides.setdefault(intent.symbol, set())
                sides.add(intent.side)
            for sym, sides in symbols_sides.items():
                if len(sides) > 1:
                    logger.warning(
                        "Conflicting intents for %s: %s from different strategies / "
                        "交易对 %s 存在冲突意图: %s", sym, sides, sym, sides,
                    )

            self._stats["intents_collected"] += len(all_intents)

        return all_intents

    # ── Query Interface / 查询接口 ──

    def get_strategy_status(self, name: str) -> dict[str, Any] | None:
        """Get status of a specific strategy / 获取指定策略的状态"""
        with self._lock:
            strategy = self._strategies.get(name)
            if strategy is None:
                return None
            status = strategy.get_status()
            status["strategy_id"] = strategy.strategy_id
            return status

    def get_all_strategies_status(self) -> list[dict[str, Any]]:
        """Get status of all registered strategies / 获取所有注册策略的状态"""
        with self._lock:
            result = []
            for s in self._strategies.values():
                status = s.get_status()
                status["strategy_id"] = s.strategy_id
                result.append(status)
            return result

    def notify_intent_rejected(self, intent: "OrderIntent") -> None:
        """
        Notify the originating strategy that its intent was rejected by pipeline gates.
        通知原始策略其 intent 被管线门控拒绝，以便策略回滚乐观状态。
        """
        strategy_name = getattr(intent, "strategy_name", "")
        if not strategy_name:
            return
        with self._lock:
            strategy = self._strategies.get(strategy_name)
            if strategy is not None:
                try:
                    strategy.on_intent_rejected(intent)
                except Exception as e:
                    logger.warning("on_intent_rejected error for %s: %s", strategy_name, e)

    def get_intent_history(self, n: int = 50) -> list[dict[str, Any]]:
        """Get recent OrderIntent history / 获取最近的 OrderIntent 历史"""
        with self._lock:
            history_list = list(self._intent_history)
            return history_list[-n:]

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive orchestrator status / 获取编排器综合状态"""
        with self._lock:
            strategies_info = {}
            for name, strategy in self._strategies.items():
                strategies_info[name] = {
                    "state": strategy.state,
                    "type": type(strategy).__name__,
                }
            return {
                "component": "strategy_orchestrator",
                "strategies": strategies_info,
                "active_count": sum(
                    1 for s in self._strategies.values()
                    if s.state == STRATEGY_ACTIVE
                ),
                "total_registered": len(self._strategies),
                "pending_intents": sum(
                    s.pending_intent_count for s in self._strategies.values()
                ),
                "stats": dict(self._stats),
                "kline_manager_status": self._km.get_status(),
                "indicator_engine_status": self._ie.get_status(),
                "signal_engine_status": self._se.get_stats(),
            }

    def compute_indicators(self, symbol: str, timeframe: str) -> None:
        """Trigger indicator computation for a symbol/timeframe. 为指定品种/时间框架触发指标计算。"""
        self._ie.compute_now(symbol, timeframe)

    def get_indicators(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """
        Get cached indicator values for a symbol + timeframe.
        获取指定交易对+时间框架的缓存指标值。

        Strategies can use this to check higher timeframe trends.
        策略可用此查看高时间框架趋势。
        """
        return self._ie.get_indicators(symbol, timeframe)

    def get_current_regime(self) -> str:
        """Get the latest detected market regime / 获取最新检测到的市场 regime"""
        return self._current_regime

    def save_all_strategy_state(self) -> dict[str, Any]:
        """Save persistent state of all strategies / 保存所有策略的持久化状态"""
        with self._lock:
            return {
                name: strategy.get_persistent_state()
                for name, strategy in self._strategies.items()
                if hasattr(strategy, 'get_persistent_state')
            }

    def restore_all_strategy_state(self, saved: dict[str, Any]) -> None:
        """Restore persistent state of all strategies / 恢复所有策略的持久化状态"""
        with self._lock:
            for name, state in saved.items():
                strategy = self._strategies.get(name)
                if strategy and hasattr(strategy, 'restore_persistent_state'):
                    try:
                        strategy.restore_persistent_state(state)
                        logger.info("Restored state for %s / 恢复策略状态: %s", name, name)
                    except Exception:
                        logger.exception("Failed to restore state for %s / 恢复失败", name)

    def list_available_strategies(self) -> list[str]:
        """List all registered strategy names / 列出所有注册的策略名称"""
        with self._lock:
            return list(self._strategies.keys())

    # ── AI Consultation / AI 咨询 ──

    def set_ai_engine(self, engine: Any) -> None:
        """Set Layer 2 AI engine for strategy consultation / 设置 L2 AI 引擎供策略咨询"""
        self._ai_engine = engine
        self._ai_consultation_enabled = engine is not None
        logger.info("AI consultation %s / AI 咨询%s",
                    "enabled" if engine else "disabled",
                    "已启用" if engine else "已禁用")

    def request_ai_analysis(self, query: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """
        Request AI analysis from Layer 2 engine (non-blocking stub).
        请求 L2 AI 引擎分析（非阻塞 stub）。

        This is a synchronous stub that returns cached/recent analysis if available,
        or queues a request for async processing.
        同步 stub，返回缓存/最近分析（如有），或排队异步处理。

        Returns analysis result dict or None if unavailable.
        """
        if not self._ai_consultation_enabled or self._ai_engine is None:
            return None

        # For now, return a stub response. Full async integration is Phase 4.
        # 当前返回 stub。完整异步集成在 Phase 4。
        return {
            "status": "ai_available_but_not_queried",
            "reason": "Sync AI consultation is a stub. Use POST /api/v1/layer2/analyze for async.",
            "engine_running": getattr(self._ai_engine, 'is_running', False),
        }
