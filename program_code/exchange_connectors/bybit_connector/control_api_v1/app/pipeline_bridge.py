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
        stop_manager: Any = None,
        *,
        auto_submit_intents: bool = True,
        max_intents_per_tick: int = 20,
    ) -> None:
        self._km = kline_manager
        self._ie = indicator_engine
        self._se = signal_engine
        self._orch = orchestrator
        self._engine = paper_engine
        self._stop_mgr = stop_manager
        self._auto_submit = auto_submit_intents
        self._max_intents_per_tick = max_intents_per_tick
        self._lock = threading.Lock()

        self._stats = {
            "ticks_received": 0,
            "intents_submitted": 0,
            "intents_accepted": 0,
            "intents_rejected": 0,
            "stops_triggered": 0,
            "errors": 0,
            "last_tick_ts_ms": 0,
        }

        self._active = False
        self._latest_prices: dict[str, float] = {}
        logger.info("PipelineBridge initialized / 管线桥接器初始化完成")

    def activate(self) -> None:
        """Activate the bridge and bootstrap historical data / 激活桥接器并引导历史数据"""
        self._active = True
        logger.info("PipelineBridge activated / 管线桥接器已激活")

        # Bootstrap historical klines on activation (eliminates cold-start blind period)
        # 激活时引导历史 K线（消除冷启动盲期）
        try:
            results = self._km.bootstrap_from_rest(limit=200)
            total = sum(results.values()) if results else 0
            if total > 0:
                logger.info(
                    "Kline bootstrap loaded %d klines / K线引导加载了 %d 根",
                    total, total,
                )
        except Exception:
            logger.exception("Kline bootstrap failed (non-fatal) / K线引导失败（非致命）")

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

        # Track latest prices for intent submission (fixes C1: positions is dict, not list)
        self._latest_prices[symbol] = price

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

        # 3. Periodic funding rate check (every 100 ticks, ~5 minutes at medium attention)
        # 定期 funding rate 检查（每 100 个 tick，中等注意力下约 5 分钟）
        if self._stats["ticks_received"] % 100 == 0:
            self._check_funding_rates()

        # 4. Process pending intents -> submit to paper engine
        if self._auto_submit:
            self._process_pending_intents()

        # 5. Check stop-losses against current prices / 检查止损
        if self._stop_mgr and self._latest_prices:
            self._check_stops()

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

        # Get current market prices from tick history (fixes C1: positions is dict, not list)
        market_prices = dict(self._latest_prices)

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
                        self._stats["intents_accepted"] += 1
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

    def _check_stops(self) -> None:
        """Check stop-losses and submit close orders if triggered / 检查止损并提交平仓"""
        try:
            triggered = self._stop_mgr.check_stops(self._latest_prices)
        except Exception:
            logger.exception("StopManager check error / 止损检查异常")
            return

        market_prices = dict(self._latest_prices)
        for stop in triggered:
            try:
                result = self._engine.submit_order(
                    symbol=stop["symbol"],
                    side=stop["side"],
                    order_type="market",
                    qty=stop["qty"],
                    market_prices=market_prices,
                )
                with self._lock:
                    self._stats["stops_triggered"] += 1
                logger.warning(
                    "STOP ORDER SUBMITTED: %s %s %.6f — %s / 止损单已提交",
                    stop["symbol"], stop["side"], stop["qty"], stop["reason"],
                )
            except Exception:
                logger.exception("Stop order submit failed / 止损单提交失败: %s", stop)

    def _check_funding_rates(self) -> None:
        """Fetch funding rate data and feed to FundingRate strategy / 获取 funding rate 并喂给策略"""
        import urllib.request
        import json as _json

        for symbol in ["BTCUSDT", "ETHUSDT"]:
            try:
                url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
                req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = _json.loads(resp.read().decode())

                if data.get("retCode") != 0:
                    continue

                ticker_list = data.get("result", {}).get("list", [])
                if not ticker_list:
                    continue

                ticker = ticker_list[0]
                funding_rate = float(ticker.get("fundingRate", 0))
                next_funding_ts = int(ticker.get("nextFundingTime", 0))

                if funding_rate == 0 or next_funding_ts == 0:
                    continue

                # Find FundingRate strategy in orchestrator and call evaluate
                # 在编排器中找到 FundingRate 策略并调用评估
                for strategy in self._orch._strategies.values():
                    if hasattr(strategy, "evaluate_funding_opportunity"):
                        try:
                            strategy.evaluate_funding_opportunity(
                                funding_rate=funding_rate,
                                next_settle_ts_ms=next_funding_ts,
                            )
                        except Exception:
                            logger.exception("Funding rate eval error / funding rate 评估异常")
            except Exception:
                logger.debug("Funding rate fetch failed for %s / 获取失败", symbol)

    def get_stats(self) -> dict[str, Any]:
        """Get bridge statistics / 获取桥接器统计"""
        with self._lock:
            return {
                "component": "pipeline_bridge",
                "active": self._active,
                **dict(self._stats),
            }
