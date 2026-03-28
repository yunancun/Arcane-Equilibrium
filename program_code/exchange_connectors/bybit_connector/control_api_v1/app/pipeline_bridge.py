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

import json as _json_mod
import logging
import os
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
        self._telegram = None  # Set externally if available
        self._demo_connector = None  # Set externally if available

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
        # Time-based refresh timestamps (replaces tick-count modulo triggers)
        # 时间驱动刷新时间戳（替代基于 tick 计数的模运算触发器）
        self._last_volume_refresh_ts: float = 0.0
        self._last_funding_check_ts: float = 0.0
        self._strategy_state_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "runtime", "strategy_state.json"
        )
        # E1: observation writer callback fn(symbol, strategy_name, close_pnl, hold_ms, regime)
        # E1：观察写入回调，在每次持仓关闭时触发
        self._observation_writer = None
        # G1: auto-deployer for consecutive-loss auto-exit / G1：自动部署器，用于连续亏损自动退出
        self._auto_deployer = None
        # H1: track open positions so StopManager can fire / H1：追踪开仓用于止损
        # {"{strategy}:{symbol}": {"side": ..., "entry_price": ..., "qty": ..., "entry_ts_ms": ..., "regime": ...}}
        self._open_positions: dict[str, dict[str, Any]] = {}
        logger.info("PipelineBridge initialized / 管线桥接器初始化完成")

    def set_telegram(self, alerter: Any) -> None:
        """Set Telegram alerter for notifications / 设置 Telegram 告警器"""
        self._telegram = alerter

    def set_observation_writer(self, fn: Any) -> None:
        """Set callback for auto-observations on round-trip close / 设置交易回合结束时的自动观察回调"""
        self._observation_writer = fn

    def set_auto_deployer(self, deployer: Any) -> None:
        """Set auto-deployer for consecutive-loss tracking / 设置自动部署器用于连续亏损追踪"""
        self._auto_deployer = deployer

    def set_demo_connector(self, connector: Any) -> None:
        """Set Bybit Demo connector for dual execution / 设置 Bybit Demo 连接器"""
        self._demo_connector = connector

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

        # Restore strategy state if available / 恢复策略状态
        try:
            if os.path.exists(self._strategy_state_path):
                with open(self._strategy_state_path, "r") as f:
                    saved = _json_mod.load(f)
                self._orch.restore_all_strategy_state(saved)
                logger.info("Strategy state restored from %s / 策略状态已恢复", self._strategy_state_path)
        except Exception:
            logger.exception("Strategy state restore failed (non-fatal) / 策略状态恢复失败")

    def deactivate(self) -> None:
        """Deactivate the bridge / 停用桥接器"""
        # Save strategy state before deactivation / 停用前保存策略状态
        try:
            saved = self._orch.save_all_strategy_state()
            os.makedirs(os.path.dirname(self._strategy_state_path), exist_ok=True)
            with open(self._strategy_state_path, "w") as f:
                _json_mod.dump(saved, f, indent=2)
            logger.info("Strategy state saved to %s / 策略状态已保存", self._strategy_state_path)
        except Exception:
            logger.exception("Strategy state save failed / 策略状态保存失败")

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
            raw_ts = event.get("ts_ms")
            ts_ms = int(raw_ts) if raw_ts is not None and raw_ts != 0 else int(time.time() * 1000)
        else:
            symbol = getattr(event, "symbol", "")
            price = float(getattr(event, "last_price", 0.0))
            raw_ts = getattr(event, "ts_ms", None)
            ts_ms = int(raw_ts) if raw_ts is not None and raw_ts != 0 else int(time.time() * 1000)

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

        # 3. Periodic volume refresh from REST API (every 60 real seconds, time-driven)
        # 定期从 REST API 刷新成交量（每 60 秒真实时间，时间驱动）
        _now = time.time()
        if _now - self._last_volume_refresh_ts >= 60.0:
            self._refresh_kline_volume()
            self._last_volume_refresh_ts = _now

        # 4. Periodic funding rate check (every 300 real seconds = 5 minutes, time-driven)
        # 定期 funding rate 检查（每 300 秒真实时间 = 5 分钟，时间驱动）
        if _now - self._last_funding_check_ts >= 300.0:
            self._check_funding_rates()
            self._last_funding_check_ts = _now

        # 5. Process pending intents -> submit to paper engine
        if self._auto_submit:
            self._process_pending_intents()

        # 6. Check stop-losses against current prices / 检查止损
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
                # Extract category from intent metadata (default: linear)
                # 从意图元数据提取品类（默认：linear）
                category = intent.metadata.get("category", "linear") if intent.metadata else "linear"

                result = self._engine.submit_order(
                    symbol=intent.symbol,
                    side=intent.side,
                    order_type=intent.order_type,
                    qty=intent.qty,
                    price=intent.price,
                    market_prices=market_prices,
                    category=category,
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

                    # H1: track position or detect close for E1/G1 hooks
                    # H1：追踪持仓，或检测关闭触发 E1/G1
                    fills = result.get("fills", []) if isinstance(result, dict) else []
                    close_pnl = result.get("close_pnl", 0.0) if isinstance(result, dict) else 0.0
                    if fills:
                        fill = fills[0]
                        fill_price = fill.get("price", market_prices.get(intent.symbol, 0.0))
                        is_open_fill = close_pnl == 0.0
                        if close_pnl != 0.0:
                            # Position closed — round-trip complete
                            # 持仓已关闭 — 一轮交易完成
                            self._on_round_trip_complete(intent, fill_price, close_pnl)
                        else:
                            # New position opened — start tracking
                            # 新持仓开仓 — 开始追踪
                            self._on_position_open(intent, fill_price)
                        # Sync strategy position state via on_fill callback
                        # 通过 on_fill 回调同步策略仓位状态，防止意图态漂移
                        if self._auto_deployer:
                            strategy_name = getattr(intent, "strategy_name", None)
                            if strategy_name:
                                fill_for_callback = {
                                    "symbol": intent.symbol,
                                    "side": intent.side,
                                    "qty": intent.qty,
                                    "price": fill_price,
                                    "strategy_name": strategy_name,
                                }
                                self._auto_deployer.notify_fill(strategy_name, fill_for_callback, is_open_fill)

                # Also submit to Bybit Demo if connector is available
                # 同时提交到 Bybit Demo（如果连接器可用）
                if self._demo_connector and self._demo_connector.is_enabled:
                    try:
                        demo_result = self._demo_connector.submit_order(
                            symbol=intent.symbol,
                            side=intent.side,
                            order_type="Market" if intent.order_type == "market" else "Limit",
                            qty=intent.qty,
                            price=intent.price,
                            category=category,
                        )
                        if demo_result.get("retCode") != 0:
                            logger.warning("Demo order failed: %s", demo_result.get("retMsg"))
                    except Exception:
                        logger.debug("Demo connector error (non-fatal)")
                    if self._telegram and intent.order_type == "market":
                        price = market_prices.get(intent.symbol, 0)
                        self._telegram.alert_trade(intent.symbol, intent.side, intent.qty, price, intent.reason[:100])

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
                if self._telegram:
                    self._telegram.alert_stop(stop["symbol"], stop["stop_type"], stop["reason"])
            except Exception:
                logger.exception("Stop order submit failed / 止损单提交失败: %s", stop)

    def _on_position_open(self, intent: Any, fill_price: float) -> None:
        """
        Called when a new position is opened.
        Record it in _open_positions and register with StopManager using ATR-based stop.
        新持仓开仓时调用。记录到 _open_positions 并用 ATR 动态止损注册到 StopManager。
        """
        symbol = intent.symbol
        strategy_name = getattr(intent, "strategy_name", "unknown")
        side = "long" if intent.side == "Buy" else "short"
        qty = intent.qty
        regime = (intent.metadata or {}).get("_regime", "unknown") if intent.metadata else "unknown"
        key = f"{strategy_name}:{symbol}"

        with self._lock:
            self._open_positions[key] = {
                "symbol": symbol,
                "strategy_name": strategy_name,
                "side": side,
                "entry_price": fill_price,
                "qty": qty,
                "entry_ts_ms": int(time.time() * 1000),
                "regime": regime,
            }

        # H1: register with StopManager using ATR-based dynamic stop
        # H1：使用 ATR 动态止损注册到 StopManager
        if self._stop_mgr:
            try:
                from local_model_tools.stop_manager import StopConfig
                # Try to get ATR from indicator engine for dynamic stop distance
                # 尝试从指标引擎获取 ATR 用于动态止损距离
                atr_stop_pct = 5.0  # default hard stop
                if self._ie and fill_price > 0:
                    try:
                        indics = self._ie.get_indicators(symbol, "1h")
                        atr = indics.get("atr") if indics else None
                        if atr and atr > 0:
                            # ATR-based stop: use 2x ATR as stop distance
                            # ATR 动态止损：使用 2倍 ATR 作为止损距离
                            atr_stop_pct = min(15.0, max(2.0, (atr * 2.0 / fill_price) * 100))
                    except Exception:
                        pass
                self._stop_mgr.track_position(
                    symbol=symbol,
                    side=side,
                    entry_price=fill_price,
                    qty=qty,
                    strategy_name=strategy_name,
                    stop_config=StopConfig(
                        hard_stop_pct=atr_stop_pct,
                        trailing_stop_pct=3.0,
                        time_stop_hours=48.0,
                    ),
                )
                logger.info(
                    "Tracking position %s %s atr_stop=%.2f%% / 追踪持仓",
                    strategy_name, symbol, atr_stop_pct,
                )
            except Exception:
                logger.exception("StopManager track error (non-fatal) / 止损追踪异常（非致命）")

    def _on_round_trip_complete(self, intent: Any, exit_price: float, close_pnl: float) -> None:
        """
        Called when a position is closed (round-trip complete).
        Writes auto-observation (E1) and notifies auto-deployer for loss tracking (G1).
        持仓关闭（一轮交易完成）时调用。
        写入自动观察（E1）并通知自动部署器进行亏损追踪（G1）。
        """
        symbol = intent.symbol
        strategy_name = getattr(intent, "strategy_name", "unknown")
        key = f"{strategy_name}:{symbol}"

        with self._lock:
            pos_info = self._open_positions.pop(key, None)

        hold_ms = 0
        regime = "unknown"
        if pos_info:
            hold_ms = int(time.time() * 1000) - pos_info.get("entry_ts_ms", int(time.time() * 1000))
            regime = pos_info.get("regime", "unknown")

        # Untrack from StopManager (position is closed) / 从 StopManager 取消追踪
        if self._stop_mgr:
            try:
                self._stop_mgr.untrack_position(symbol, strategy_name)
            except Exception:
                pass

        # G1: notify auto-deployer for consecutive loss tracking
        # G1：通知自动部署器进行连续亏损追踪
        if self._auto_deployer:
            try:
                self._auto_deployer.on_trade_result(strategy_name, close_pnl)
            except Exception:
                logger.debug("Auto-deployer on_trade_result error (non-fatal)")

        # E1: write auto-observation
        # E1：写入自动观察
        if self._observation_writer:
            try:
                self._observation_writer(
                    symbol=symbol,
                    strategy_name=strategy_name,
                    close_pnl=close_pnl,
                    hold_ms=hold_ms,
                    regime=regime,
                )
            except Exception:
                logger.debug("Observation writer error (non-fatal)")

        logger.info(
            "Round-trip complete: %s %s pnl=%.4f hold=%.1fh regime=%s / 交易完成",
            strategy_name, symbol, close_pnl, hold_ms / 3600000, regime,
        )

    def _refresh_kline_volume(self) -> None:
        """
        Periodically fetch latest kline from REST API to get real volume data.
        定期从 REST API 获取最新 K线以获取真实成交量。

        Dynamically covers all tracked symbols, not just BTC/ETH.
        动态覆盖所有已追踪的交易对，不仅限于 BTC/ETH。
        """
        import urllib.request
        import json as _json

        tf_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}

        # Use all actively tracked symbols / 使用所有活跃追踪的交易对
        tracked = self._km.get_tracked_symbols() if hasattr(self._km, "get_tracked_symbols") else []
        if not tracked:
            tracked = list(self._latest_prices.keys())
        # Cap to 10 symbols per refresh to avoid rate limits / 限制每次最多 10 个以避免频率限制
        symbols = tracked[:10]

        for symbol in symbols:
            for tf, interval in tf_map.items():
                try:
                    url = (
                        f"https://api.bybit.com/v5/market/kline"
                        f"?category=linear&symbol={symbol}&interval={interval}&limit=2"
                    )
                    req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = _json.loads(resp.read().decode())

                    if data.get("retCode") != 0:
                        continue

                    klines = data.get("result", {}).get("list", [])
                    if not klines:
                        continue

                    # Bybit returns newest first; we want the most recently CLOSED kline (index 1)
                    # The kline at index 0 is still forming
                    if len(klines) >= 2:
                        closed = klines[1]  # [startTime, open, high, low, close, volume, turnover]
                        volume = float(closed[5]) if len(closed) > 5 else 0.0
                        # Update the last closed bar's volume in KlineManager
                        buf = self._km.get_buffer(symbol, tf)
                        if buf and len(buf) > 0:
                            last_bar = buf._bars[-1]  # Access internal deque
                            if last_bar.volume == 0 and volume > 0:
                                last_bar.volume = volume
                                last_bar.turnover = float(closed[6]) if len(closed) > 6 else 0.0
                except Exception:
                    pass  # Non-critical, silently skip

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
