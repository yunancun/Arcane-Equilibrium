"""
Pipeline Bridge -- Connects Strategy Pipeline to Paper Trading Engine
管线桥接器 -- 连接策略管线与纸上交易引擎

MODULE_NOTE (中文):
  本模块是 Phase 3a 的核心组件，解决策略管线与纸上交易管线之间的断裂问题。

  职责：
  1. Tick Fan-Out：将 WebSocket tick 同时分发给 KlineManager 和 StrategyOrchestrator
  2. Intent→Order Bridge：将策略产生的 OrderIntent 提交到 PaperTradingEngine
  3. 执行回调：将成交结果反馈给策略，让策略知道其意图是否被执行

  数据流：
    WebSocket tick
      → MarketDataDispatcher._on_price_event()
        → PipelineBridge.on_tick(event)
          → KlineManager.on_price_event(event)  [K线聚合]
          → Orchestrator.dispatch_tick(...)       [Grid/Funding 等 tick 策略]
          → bridge.process_pending_intents()      [收集意图 → 提交订单]

MODULE_NOTE (English):
  Core Phase 3a component that bridges the strategy pipeline and paper trading pipeline.

  Responsibilities:
  1. Tick Fan-Out: distribute WebSocket ticks to KlineManager and StrategyOrchestrator
  2. Intent→Order Bridge: submit strategy-generated OrderIntents to PaperTradingEngine
  3. Execution feedback: route fill results back to strategies

Safety invariant:
  - system_mode = read_only (unchanged)
  - All orders go through RiskManager via PaperTradingEngine.submit_order()
  - All data marked is_simulated=True
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class PipelineBridge:
    """
    Bridges the strategy pipeline (KlineManager->Indicators->Signals->Strategies->Intents)
    to the paper trading pipeline (PaperTradingEngine).
    """

    def __init__(
        self,
        kline_manager: Any,
        indicator_engine: Any,
        signal_engine: Any,
        orchestrator: Any,
        paper_engine: Any,
        *,
        auto_submit_intents: bool = True,
        max_intents_per_tick: int = 20,
    ) -> None:
        self._km = kline_manager
        self._ie = indicator_engine
        self._se = signal_engine
        self._orch = orchestrator
        self._engine = paper_engine
        self._auto_submit = auto_submit_intents
        self._max_intents_per_tick = max_intents_per_tick
        self._lock = threading.Lock()

        self._stats = {
            "ticks_received": 0,
            "intents_submitted": 0,
            "intents_filled": 0,
            "intents_rejected": 0,
            "errors": 0,
            "last_tick_ts_ms": 0,
        }

        self._active = False
        logger.info("PipelineBridge initialized / 管线桥接器初始化完成")

    def activate(self) -> None:
        """Activate the bridge / 激活桥接器"""
        self._active = True
        logger.info("PipelineBridge activated / 管线桥接器已激活")

    def deactivate(self) -> None:
        """Deactivate the bridge / 停用桥接器"""
        self._active = False
        logger.info("PipelineBridge deactivated / 管线桥接器已停用")

    @property
    def is_active(self) -> bool:
        return self._active

    def on_tick(self, event: Any) -> None:
        """
        Called by MarketDataDispatcher on every (non-throttled) price event.
        由 MarketDataDispatcher 在每次（未被节流的）价格事件时调用。

        This is the main fan-out entry point:
        1. Feed KlineManager (triggers indicator computation on kline close)
        2. Feed StrategyOrchestrator.dispatch_tick (for tick-driven strategies)
        3. Process pending intents (submit to paper engine)
        """
        if not self._active:
            return

        with self._lock:
            self._stats["ticks_received"] += 1
            self._stats["last_tick_ts_ms"] = int(time.time() * 1000)

        # Extract event fields
        if isinstance(event, dict):
            symbol = event.get("symbol", "")
            price = float(event.get("last_price", 0.0))
            ts_ms = int(event.get("ts_ms", 0) or time.time() * 1000)
        else:
            symbol = getattr(event, "symbol", "")
            price = float(getattr(event, "last_price", 0.0))
            ts_ms = int(getattr(event, "ts_ms", 0) or time.time() * 1000)

        if not symbol or price <= 0:
            return

        # 1. Feed KlineManager -> triggers IndicatorEngine -> triggers SignalEngine -> triggers Orchestrator.on_signal
        try:
            self._km.on_price_event(event)
        except Exception:
            logger.exception("KlineManager tick error / K线管理器 tick 异常")
            with self._lock:
                self._stats["errors"] += 1

        # 2. Feed tick-driven strategies (Grid Trading, etc.)
        try:
            self._orch.dispatch_tick(symbol, price, ts_ms)
        except Exception:
            logger.exception("Orchestrator dispatch_tick error / 编排器 dispatch_tick 异常")
            with self._lock:
                self._stats["errors"] += 1

        # 3. Process pending intents -> submit to paper engine
        if self._auto_submit:
            self._process_pending_intents()

    def _process_pending_intents(self) -> None:
        """
        Collect OrderIntents from orchestrator and submit to paper engine.
        从编排器收集 OrderIntent 并提交到纸上交易引擎。
        """
        try:
            intents = self._orch.collect_pending_intents()
        except Exception:
            logger.exception("Failed to collect intents / 收集意图失败")
            return

        if not intents:
            return

        # Limit intents per tick to prevent flooding
        if len(intents) > self._max_intents_per_tick:
            logger.warning(
                "Too many intents (%d > %d), processing first %d / "
                "意图过多，只处理前 %d 个",
                len(intents), self._max_intents_per_tick,
                self._max_intents_per_tick,
                self._max_intents_per_tick,
            )
            intents = intents[: self._max_intents_per_tick]

        # Get current market prices for order submission
        market_prices: dict[str, float] = {}
        try:
            state = self._engine.get_state()
            # Extract latest prices from paper engine state if available
            for pos in state.get("positions", []):
                if pos.get("symbol"):
                    mp = pos.get("mark_price") or pos.get("entry_price", 0)
                    if mp:
                        market_prices[pos["symbol"]] = mp
        except Exception:
            pass

        for intent in intents:
            try:
                result = self._engine.submit_order(
                    symbol=intent.symbol,
                    side=intent.side,
                    order_type=intent.order_type,
                    qty=intent.qty,
                    price=intent.price,
                    market_prices=market_prices,
                )

                with self._lock:
                    self._stats["intents_submitted"] += 1

                order = result.get("order", {}) if isinstance(result, dict) else {}
                rejected = result.get("rejected_reason") if isinstance(result, dict) else None

                if rejected:
                    with self._lock:
                        self._stats["intents_rejected"] += 1
                    logger.info(
                        "Intent rejected: %s %s %s qty=%.6f reason=%s / 意图被拒",
                        intent.symbol, intent.side, intent.order_type,
                        intent.qty, rejected,
                    )
                else:
                    with self._lock:
                        self._stats["intents_filled"] += 1
                    logger.info(
                        "Intent submitted: %s %s %s qty=%.6f / 意图已提交",
                        intent.symbol, intent.side, intent.order_type, intent.qty,
                    )

            except Exception:
                logger.exception(
                    "Failed to submit intent: %s / 提交意图失败", intent,
                )
                with self._lock:
                    self._stats["errors"] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get bridge statistics / 获取桥接器统计"""
        with self._lock:
            return {
                "component": "pipeline_bridge",
                "active": self._active,
                **dict(self._stats),
            }
