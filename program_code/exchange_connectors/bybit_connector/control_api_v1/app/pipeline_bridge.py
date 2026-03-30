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

from .risk_manager import REGIME_TIME_MULTIPLIERS

# T2.07: Import Scout-related enums for local market scanning
# Lazy import pattern to avoid circular dependencies
# 懒惰导入模式避免循环依赖
try:
    from .multi_agent_framework import DataQualityLevel, SentimentScore
except ImportError:
    # If multi_agent_framework is not available, define fallback enums
    class DataQualityLevel:  # type: ignore
        FACT = "fact"
        INFERENCE = "inference"
        HYPOTHESIS = "hypothesis"

    class SentimentScore:  # type: ignore
        POSITIVE = "positive"
        NEGATIVE = "negative"
        NEUTRAL = "neutral"

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
        self._governance_hub = None  # Set externally for governance integration
        self._perception_plane = None  # T2.02: Set externally for cognitive honesty checks / 感知平面
        self._scanner_rate_limiter = None  # T2.07: Set externally for rate limiting / 扫描速率限制器
        self._trade_attribution = None  # L1.01: Set externally for trade attribution / 交易归因引擎
        self._scout_agent = None  # T2.07: Set externally for ScoutAgent local market intelligence / Scout 代理
        self._message_bus = None  # T2.07: Set externally for inter-agent communication / 消息总线
        self._learning_tier_gate = None  # EX-05 §3: Set externally for learning tier auto-promotion / 学习等级自动晋升门控
        self._strategist_agent = None  # Batch 7: Set externally for StrategistAgent intents / 策略师代理
        self._guardian_agent = None  # Batch 8: Set externally for GuardianAgent verdict gate / 守卫代理
        self._analyst_agent = None  # Batch 9: Set externally for AnalystAgent trade analysis / 分析师代理
        self._ollama_client = None  # B5-B: Set externally for L1 pre-trade edge filter / L1 交易前 edge 过滤器
        self._edge_filter_enabled = True  # Can be toggled at runtime / 可在运行时切换
        self._edge_filter_stats = {"checked": 0, "passed": 0, "rejected": 0, "errors": 0}
        # Batch 8: Guardian verdict stats / Guardian 裁决统计
        self._guardian_stats = {"checked": 0, "approved": 0, "rejected": 0, "modified": 0, "errors": 0}

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
        self._last_scout_scan_ts: float = 0.0  # T2.07: Scout local scan timestamp / Scout 本地扫描时间戳
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
        # EX-05: Track trade outcomes for learning tier gate metrics / EX-05：追踪交易结果用于学习等级门控指标
        self._learning_stats = {
            "total_trades": 0,
            "winning_trades": 0,
        }
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

    def set_governance_hub(self, hub: Any) -> None:
        """Set GovernanceHub for governance state machine integration / 设置治理集線器"""
        self._governance_hub = hub

    def set_perception_plane(self, plane: Any) -> None:
        """Set PerceptionPlane for cognitive honesty checks / 设置感知平面用于认知诚实检查"""
        self._perception_plane = plane

    def set_scanner_rate_limiter(self, limiter: Any) -> None:
        """Set ScannerRateLimiter for rate limiting scans / 设置扫描速率限制器"""
        self._scanner_rate_limiter = limiter

    def set_trade_attribution(self, attribution_engine: Any) -> None:
        """Set TradeAttributionEngine for trade attribution / 设置交易归因引擎"""
        self._trade_attribution = attribution_engine

    def set_scout_agent(self, agent: Any) -> None:
        """Set ScoutAgent for local market intelligence / 设置 Scout 代理用于本地市场情报"""
        self._scout_agent = agent

    def set_message_bus(self, bus: Any) -> None:
        """Set MessageBus for inter-agent communication / 设置消息总线用于代理间通信"""
        self._message_bus = bus

    def set_learning_tier_gate(self, gate: Any) -> None:
        """
        Set LearningTierGate for auto-promotion of learning tiers.
        为学习等级自动晋升设置 LearningTierGate。
        """
        self._learning_tier_gate = gate

    def set_strategist_agent(self, agent: Any) -> None:
        """
        Set StrategistAgent for collecting AI-evaluated intents.
        设置 StrategistAgent 用于收集 AI 评估后的 intent。
        """
        self._strategist_agent = agent
        logger.info("StrategistAgent set for intent collection / 已设置 StrategistAgent 用于 intent 收集")

    def set_guardian_agent(self, agent: Any) -> None:
        """
        Batch 8: Set GuardianAgent as primary trade gate (fail-closed).
        Guardian reviews every intent; unavailable → REJECTED.
        Batch 8：设置 GuardianAgent 为主交易门控（fail-closed）。
        Guardian 审查每个 intent；不可用 → 拒绝。
        """
        self._guardian_agent = agent
        logger.info("GuardianAgent set as primary gate (fail-closed) / 已设置 GuardianAgent 为主门控")

    def set_analyst_agent(self, agent: Any) -> None:
        """
        Batch 9: Set AnalystAgent for trade result analysis and LearningTierGate updates.
        Batch 9：设置 AnalystAgent 用于交易结果分析和 LearningTierGate 指标更新。
        """
        self._analyst_agent = agent
        logger.info("AnalystAgent set for trade analysis / 已设置 AnalystAgent 用于交易分析")

    def set_ollama_client(self, client: Any) -> None:
        """
        Set OllamaClient for L1 pre-trade edge filter.
        设置 OllamaClient 用于 L1 交易前 edge 过滤。
        """
        self._ollama_client = client
        logger.info("OllamaClient set for pre-trade edge filter / 已设置 OllamaClient 用于交易前 edge 过滤")

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

        # 1.5 Batch 9: Register kline/price data as FACT in Perception Plane (EX-07 §1)
        # Batch 9：将 K线/价格数据注册为 FACT 到感知平面（认知诚实）
        if self._perception_plane:
            try:
                from .perception_data_plane import DataSourceType, CognitiveLevel
                self._perception_plane.register_data(
                    source_type=DataSourceType.EXCHANGE_WS,
                    content={"symbol": symbol, "price": price, "ts_ms": ts_ms},
                    source_detail="bybit_ws_ticker",
                    cognitive_level=CognitiveLevel.FACT,
                    symbols=[symbol],
                    marked_by="PipelineBridge.on_tick",
                    marking_reason="Exchange WebSocket price data = FACT (EX-07 §1)",
                    metadata={"data_type": "price"},
                )
            except Exception:
                pass  # Perception registration is non-fatal / 感知注册失败不影响主流程

        # 2. Feed tick-driven strategies (Grid Trading, etc.)
        try:
            self._orch.dispatch_tick(symbol, price, ts_ms)
        except Exception:
            logger.exception("Orchestrator dispatch_tick error / 编排器 dispatch_tick 异常")
            with self._lock:
                self._stats["errors"] += 1

        # 3. Periodic volume refresh from REST API (every 60 real seconds, time-driven)
        # 定期从 REST API 刷新成交量（每 60 秒真实时间，时间驱动）
        # T2.07: Check scanner rate limiter before full market scan
        _now = time.time()
        if _now - self._last_volume_refresh_ts >= 60.0:
            # Check if rate limiter permits scan
            if self._scanner_rate_limiter:
                can_scan, reason = self._scanner_rate_limiter.can_scan()
                if can_scan:
                    self._refresh_kline_volume()
                    self._scanner_rate_limiter.record_scan_complete()
                    self._last_volume_refresh_ts = _now
                # else: skip scan due to rate limit, will try again next tick
            else:
                # No rate limiter installed, allow scan by default
                self._refresh_kline_volume()
                self._last_volume_refresh_ts = _now

        # 4. Periodic funding rate check (every 300 real seconds = 5 minutes, time-driven)
        # 定期 funding rate 检查（每 300 秒真实时间 = 5 分钟，时间驱动）
        if _now - self._last_funding_check_ts >= 300.0:
            self._check_funding_rates()
            self._last_funding_check_ts = _now

        # 4.5. Periodic Scout local scan (every 300s = 5 minutes, time-driven)
        # 定期 Scout 本地扫描（每 300 秒 = 5 分钟，时间驱动）
        if self._scout_agent and _now - self._last_scout_scan_ts >= 300.0:
            self._invoke_scout_scan(symbol, price)
            self._last_scout_scan_ts = _now

        # 5. Process pending intents -> submit to paper engine
        if self._auto_submit:
            self._process_pending_intents()

        # 6. Check stop-losses against current prices / 检查止损
        if self._stop_mgr and self._latest_prices:
            self._check_stops()

    def _process_pending_intents(self) -> None:
        """
        Collect OrderIntents from orchestrator AND StrategistAgent, submit to paper engine.
        从编排器和 StrategistAgent 收集 OrderIntent 并提交到纸上交易引擎。

        Batch 7: Extended to also collect intents from StrategistAgent
        (AI-evaluated intents that passed Guardian review or shadow=False).
        """
        try:
            intents = self._orch.collect_pending_intents()
        except Exception:
            logger.exception("Failed to collect orchestrator intents / 收集编排器意图失败")
            intents = []

        # Batch 7: Also collect from StrategistAgent (non-shadow intents)
        # Batch 7：同时从 StrategistAgent 收集（非 shadow 模式下的 intent）
        if self._strategist_agent:
            try:
                strategist_intents = self._strategist_agent.collect_pending_intents()
                if strategist_intents:
                    logger.info(
                        "Collected %d intents from StrategistAgent / 从 StrategistAgent 收集了 %d 个 intent",
                        len(strategist_intents), len(strategist_intents),
                    )
                    # Convert TradeIntent to OrderIntent-compatible format
                    # 将 TradeIntent 转换为与 OrderIntent 兼容的格式
                    for ti in strategist_intents:
                        try:
                            # Create a minimal OrderIntent-like object from TradeIntent
                            # This bridges the multi-agent TradeIntent → legacy OrderIntent
                            _side = "Buy" if ti.direction == "long" else "Sell"
                            _intent_obj = type("StrategyIntent", (), {
                                "symbol": ti.symbol,
                                "side": _side,
                                "order_type": "market",
                                "qty": ti.size,
                                "price": None,
                                "metadata": ti.metadata,
                                "perception_data_id": None,
                            })()
                            intents.append(_intent_obj)
                        except Exception as _si_e:
                            logger.warning("Failed to convert StrategistAgent intent: %s / 转换 StrategistAgent intent 失败", _si_e)
            except Exception as _strat_e:
                logger.warning("Failed to collect StrategistAgent intents: %s / 收集 StrategistAgent intent 失败", _strat_e)

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
                # T2.02: Cognitive honesty check (perception plane validation)
                # 认知诚实检查（感知平面验证）
                if self._perception_plane:
                    data_id = getattr(intent, "perception_data_id", None)
                    if data_id:
                        # Intent references perception data — validate before proceeding
                        # 意图引用了感知数据 — 在继续前验证
                        eligible, reason = self._perception_plane.validate_for_decision(data_id)
                        if not eligible:
                            logger.info(
                                "Intent rejected by perception honesty: %s %s (reason: %s) / 意图被感知拒絕",
                                intent.symbol, intent.side, reason
                            )
                            with self._lock:
                                self._stats["intents_rejected"] += 1
                            continue
                    else:
                        # Intent has no perception data marked (implicit FACT assumption for exchange data)
                        # 意图无感知数据标记（假设交易所数据为 FACT）
                        # This is acceptable for exchange-sourced signals
                        pass

                # Governance Hub authorization check / 治理集線器授權檢查
                if self._governance_hub:
                    try:
                        if not self._governance_hub.is_authorized():
                            logger.info(
                                "Intent rejected by governance: %s %s (not authorized) / 意图被治理拒絕",
                                intent.symbol, intent.side
                            )
                            with self._lock:
                                self._stats["intents_rejected"] += 1
                            continue
                    except Exception as exc:
                        logger.error("Governance is_authorized error — fail-closed: %s", exc)
                        with self._lock:
                            self._stats["intents_rejected"] += 1
                        continue

                # ── Batch 8: Guardian Agent as PRIMARY gate (fail-closed) ──
                # Batch 8：Guardian Agent 作为主门控（fail-closed）
                # Guardian verdict overrides all other filters (EX-06 §9).
                # If Guardian is unavailable → REJECTED (fail-closed, DOC-01 §5.6).
                # Original edge filter demoted to auxiliary reference (logged only).
                _submit_qty = intent.qty
                _submit_leverage = None

                if self._guardian_agent:
                    try:
                        from .multi_agent_framework import TradeIntent as _TI, RiskVerdictResult as _RVR

                        # Sync active positions to Guardian for context
                        # 同步活跃仓位到 Guardian 用于上下文判断
                        if self._open_positions:
                            self._guardian_agent.update_active_positions(self._open_positions)

                        # Build TradeIntent from OrderIntent / 从 OrderIntent 构建 TradeIntent
                        _direction = "long" if intent.side == "Buy" else "short"
                        _strategy = (
                            intent.metadata.get("strategy_name", "unknown")
                            if intent.metadata else "unknown"
                        )
                        _ti = _TI(
                            symbol=intent.symbol,
                            strategy=_strategy,
                            direction=_direction,
                            size=intent.qty,
                            params={"leverage": getattr(intent, "leverage", 1.0) or 1.0},
                            confidence=getattr(intent, "confidence", 0.5) or 0.5,
                        )

                        verdict = self._guardian_agent.review_intent(_ti)

                        with self._lock:
                            self._guardian_stats["checked"] += 1

                        if verdict.result == _RVR.REJECTED:
                            with self._lock:
                                self._guardian_stats["rejected"] += 1
                                self._stats["intents_rejected"] += 1
                            logger.info(
                                "Intent REJECTED by Guardian: %s %s (reason: %s, risk=%.2f) / "
                                "意图被 Guardian 拒绝",
                                intent.symbol, intent.side, verdict.reason, verdict.risk_score,
                            )
                            continue

                        elif verdict.result == _RVR.MODIFIED:
                            with self._lock:
                                self._guardian_stats["modified"] += 1
                            # Apply modifications: adjust qty and/or leverage
                            # 应用修改：调整数量和/或杠杆
                            if "size" in verdict.modified_params:
                                _submit_qty = float(verdict.modified_params["size"])
                            if "leverage" in verdict.modified_params:
                                _submit_leverage = float(verdict.modified_params["leverage"])
                            logger.info(
                                "Intent MODIFIED by Guardian: %s %s (qty %.6f→%.6f, reason: %s) / "
                                "意图被 Guardian 修改",
                                intent.symbol, intent.side, intent.qty, _submit_qty, verdict.reason,
                            )
                        else:
                            # APPROVED
                            with self._lock:
                                self._guardian_stats["approved"] += 1
                            logger.debug(
                                "Intent APPROVED by Guardian: %s %s / 意图被 Guardian 批准",
                                intent.symbol, intent.side,
                            )

                    except Exception as _guardian_err:
                        # Guardian error → fail-closed: REJECT (DOC-01 §5.6)
                        # Guardian 错误 → fail-closed：拒绝
                        logger.error(
                            "Guardian error — fail-closed REJECT: %s %s (%s) / "
                            "Guardian 异常 — fail-closed 拒绝",
                            intent.symbol, intent.side, _guardian_err,
                        )
                        with self._lock:
                            self._guardian_stats["errors"] += 1
                            self._stats["intents_rejected"] += 1
                        continue

                # 5-B: L1 Pre-trade edge filter (auxiliary reference — logged but not blocking)
                # L1 交易前 edge 过滤（辅助参考 — 仅记录，不阻塞）
                # Batch 8: Guardian is now the primary gate; edge filter demoted to advisory
                # Batch 8：Guardian 已成为主门控；edge filter 降级为参考
                if self._ollama_client and self._edge_filter_enabled:
                    edge_ok = self._check_edge_filter(intent, market_prices)
                    if not edge_ok:
                        logger.info(
                            "Edge filter advisory: would reject %s %s (Guardian already approved) / "
                            "Edge 过滤器建议：会拒绝 %s %s（Guardian 已批准）",
                            intent.symbol, intent.side, intent.symbol, intent.side,
                        )
                        # Note: no longer blocking — Guardian verdict is authoritative
                        # 注意：不再阻塞 — Guardian 裁决为权威

                # Extract category from intent metadata (default: linear)
                # 从意图元数据提取品类（默认：linear）
                category = intent.metadata.get("category", "linear") if intent.metadata else "linear"

                # B6: For limit orders without explicit price, use current market price
                # B6：limit 单如无明确价格，使用当前市场价
                submit_price = intent.price
                if intent.order_type == "limit" and submit_price is None:
                    submit_price = market_prices.get(intent.symbol)

                result = self._engine.submit_order(
                    symbol=intent.symbol,
                    side=intent.side,
                    order_type=intent.order_type,
                    qty=_submit_qty,  # Batch 8: may be modified by Guardian / 可能被 Guardian 修改
                    price=submit_price,
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
                # Guard: skip if position was already closed by RiskManager in the same tick.
                # Without this check, submitting a close-side order on a gone position would
                # open a new opposite-direction position — a silent bug.
                # 防止双重止损：若 RiskManager 已平仓，跳过此止损单，避免开出反向仓位。
                try:
                    engine_state = self._engine.get_state()
                    if not engine_state.get("positions", {}).get(stop["symbol"]):
                        logger.debug(
                            "Stop skipped — position already closed: %s / 止损跳过，仓位已平",
                            stop["symbol"],
                        )
                        self._stop_mgr.untrack_position(
                            stop["symbol"], stop.get("strategy_name", "unknown")
                        )
                        continue
                except Exception:
                    pass  # If state read fails, proceed with stop order (safe default)

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

    def _invoke_scout_scan(self, symbol: str, price: float) -> None:
        """T2.07 Plan A2: Scout local market scan — volume anomaly + funding rate spike detection.
        Scout 本地市场扫描 — 成交量异常 + 资金费率尖峰检测。
        """
        try:
            if not self._scout_agent or self._scout_agent.state.value != "running":
                return

            # --- Volume anomaly check ---
            try:
                vol_data = self._km.get_volume_profile(symbol) if hasattr(self._km, 'get_volume_profile') else None
                if vol_data and isinstance(vol_data, dict):
                    vol_ratio = vol_data.get("volume_ratio", 1.0)
                    if vol_ratio > 2.0:  # 2x average volume = anomaly
                        self._scout_agent.produce_intel(
                            source=f"local_volume_scan:{symbol}",
                            content=f"Volume anomaly detected: {vol_ratio:.1f}x average for {symbol}",
                            symbols=[symbol],
                            data_quality=DataQualityLevel.FACT,
                            sentiment=SentimentScore.NEUTRAL,
                            relevance_score=min(0.9, vol_ratio / 5.0),
                            metadata={"volume_ratio": vol_ratio, "price": price},
                        )
            except Exception:
                pass  # Volume check is non-fatal

            # --- Funding rate spike check ---
            try:
                if hasattr(self._km, 'get_latest_funding_rate'):
                    fr = self._km.get_latest_funding_rate(symbol)
                    if fr is not None and abs(fr) > 0.01:  # >1% funding = spike
                        severity = "high" if abs(fr) > 0.03 else "medium"
                        self._scout_agent.produce_event_alert(
                            event_type="funding_rate_spike",
                            severity=severity,
                            affected_symbols=[symbol],
                            description=f"Funding rate spike: {fr*100:.2f}% for {symbol}",
                            metadata={"funding_rate": fr, "price": price},
                        )
            except Exception:
                pass  # Funding check is non-fatal

            self._scout_agent.record_scan()

        except Exception:
            logger.exception("Scout local scan error (non-fatal) / Scout 本地扫描异常（非致命）")

    def _check_edge_filter(self, intent: Any, market_prices: dict[str, float]) -> bool:
        """
        L1 pre-trade edge filter: ask Qwen if the signal has enough edge to trade.
        L1 交易前 edge 过滤器：询问 Qwen 当前信号是否有足够的交易优势。

        Returns True if intent should proceed, False if it should be rejected.
        返回 True 表示允许交易，False 表示拒绝。

        Design principle: fail-OPEN (if Ollama is unavailable or errors, allow the trade).
        设计原则：失败时放行（Ollama 不可用或出错时允许交易通过）。
        This is conservative in a different sense — we don't want the edge filter
        to become a single point of failure that blocks all trading.
        """
        with self._lock:
            self._edge_filter_stats["checked"] += 1

        try:
            if not self._ollama_client.is_available():
                logger.debug("Edge filter: Ollama unavailable, passing through / Ollama 不可用，放行")
                with self._lock:
                    self._edge_filter_stats["errors"] += 1
                return True  # fail-open

            # Build market context for Qwen / 为 Qwen 构建市场上下文
            symbol = intent.symbol
            side = intent.side
            price = market_prices.get(symbol, 0.0)
            strategy = intent.metadata.get("strategy_name", "unknown") if intent.metadata else "unknown"
            confidence = getattr(intent, "confidence", None) or (
                intent.metadata.get("confidence", "N/A") if intent.metadata else "N/A"
            )

            # Gather additional context from KlineManager if available
            regime_info = ""
            try:
                if hasattr(self._km, 'get_regime'):
                    regime = self._km.get_regime(symbol)
                    if regime:
                        regime_info = f"\nMarket regime: {regime}"
            except Exception:
                pass

            indicator_info = ""
            try:
                if hasattr(self._km, 'get_latest_indicators'):
                    indicators = self._km.get_latest_indicators(symbol)
                    if indicators and isinstance(indicators, dict):
                        # Only include key indicators
                        keys = ["rsi_14", "atr_14", "bb_width", "macd_histogram", "volume_ratio"]
                        parts = [f"{k}={indicators[k]:.4f}" for k in keys if k in indicators]
                        if parts:
                            indicator_info = f"\nIndicators: {', '.join(parts)}"
            except Exception:
                pass

            context = (
                f"Symbol: {symbol}\n"
                f"Signal: {side} (strategy: {strategy}, confidence: {confidence})\n"
                f"Current price: {price:.4f}\n"
                f"Fee drag: ~0.11% round-trip (taker both sides)"
                f"{regime_info}"
                f"{indicator_info}"
            )

            resp = self._ollama_client.judge_edge(context, timeout=10)

            if not resp.success:
                logger.warning(
                    "Edge filter: Qwen error (%s), passing through / Qwen 出错，放行: %s",
                    resp.error, symbol,
                )
                with self._lock:
                    self._edge_filter_stats["errors"] += 1
                return True  # fail-open

            # Parse response / 解析响应
            import json as _json
            try:
                result = _json.loads(resp.text)
                has_edge = result.get("has_edge", True)  # default: allow
                edge_confidence = result.get("confidence", 0.5)
                edge_reason = result.get("reason", "")
            except (_json.JSONDecodeError, AttributeError):
                # If Qwen returns non-JSON, try heuristic
                text_lower = resp.text.lower()
                has_edge = "true" in text_lower or "yes" in text_lower
                edge_confidence = 0.5
                edge_reason = resp.text[:200]

            logger.info(
                "Edge filter: %s %s has_edge=%s confidence=%.2f reason=%s latency=%.0fms / "
                "edge 过滤: %s %s has_edge=%s",
                symbol, side, has_edge, edge_confidence, edge_reason[:80], resp.latency_ms,
                symbol, side, has_edge,
            )

            if has_edge:
                with self._lock:
                    self._edge_filter_stats["passed"] += 1
                return True
            else:
                with self._lock:
                    self._edge_filter_stats["rejected"] += 1
                return False

        except Exception as e:
            logger.warning("Edge filter exception (fail-open): %s / edge 过滤异常（放行）: %s", e, intent.symbol)
            with self._lock:
                self._edge_filter_stats["errors"] += 1
            return True  # fail-open — never block trading due to filter errors

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

        # Write regime to paper engine position so RiskManager can use it for stop/TP/time scaling
        # 将市场状态写入纸上交易引擎持仓，让 RiskManager 用于止损/止盈/时间缩放
        if self._engine and regime != "unknown":
            try:
                store = self._engine.store
                def _inject_regime(state: dict) -> dict:
                    if symbol in state.get("positions", {}):
                        state["positions"][symbol]["regime"] = regime
                    return state
                store.mutate(_inject_regime)
            except Exception:
                logger.debug("Could not write regime to position (non-fatal): %s", symbol)

        # H1: register with StopManager using ATR-based dynamic stop + regime-adjusted time stop
        # H1：使用 ATR 动态止损 + 市场状态调整时间止损注册到 StopManager
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
                # Regime-adjusted time stop / 市场状态调整时间止损
                time_stop_hours = 48.0 * REGIME_TIME_MULTIPLIERS.get(regime, 1.0)
                # B6: Dynamic trailing stop = max(5%, 2×ATR/price*100)
                # B6：动态追踪止损 = max(5%, 2×ATR/价格*100)，避免噪音触发
                trailing_pct = 5.0  # floor: never tighter than 5%
                try:
                    indics_trail = self._km.get_latest_indicators(symbol) if hasattr(self._km, 'get_latest_indicators') else None
                    atr_val = indics_trail.get("atr") if indics_trail else None
                    if atr_val and atr_val > 0 and fill_price > 0:
                        atr_trail_pct = (atr_val * 2.0 / fill_price) * 100
                        trailing_pct = max(5.0, min(15.0, atr_trail_pct))
                except Exception:
                    pass  # fallback to 5% floor
                self._stop_mgr.track_position(
                    symbol=symbol,
                    side=side,
                    entry_price=fill_price,
                    qty=qty,
                    strategy_name=strategy_name,
                    stop_config=StopConfig(
                        hard_stop_pct=atr_stop_pct,
                        trailing_stop_pct=trailing_pct,
                        time_stop_hours=time_stop_hours,
                    ),
                )
                logger.info(
                    "Tracking position %s %s atr_stop=%.2f%% time_stop=%.1fh regime=%s / 追踪持仓",
                    strategy_name, symbol, atr_stop_pct, time_stop_hours, regime,
                )
            except Exception:
                logger.exception("StopManager track error (non-fatal) / 止损追踪异常（非致命）")

    def _try_learning_promotion(self, close_pnl: float) -> None:
        """
        EX-05 §3: Attempt to promote learning tier based on trade outcome.
        根据交易结果尝试晋升学习等级。

        This is called after each round-trip completion to:
        1. Record the trade outcome (win/loss) and update local stats
        2. Update tier metrics (observation_count, win_rate, etc.)
        3. Check for promotion eligibility and auto-promote if eligible

        L1→L2 promotion requires:
          - observation_count >= 500
          - win_rate >= 20%

        Non-fatal if gate is not set or if promotion fails.

        在每个 round-trip 完成后调用以：
        1. 记录交易结果（赢/亏）并更新本地统计
        2. 更新等级指标（观察计数、胜率等）
        3. 检查晋升资格并在符合条件时自动晋升

        L1→L2 晋升需要：
          - 观察计数 >= 500
          - 胜率 >= 20%

        如果未设置门控或晋升失败，则为非致命。

        Args:
            close_pnl: Closed PnL of the completed trade (positive = win, negative/zero = loss)
        """
        if not self._learning_tier_gate:
            return

        try:
            # Determine win/loss: close_pnl > 0 means win, otherwise loss
            # 确定 win/loss：close_pnl > 0 表示赢，否则表示亏
            win = close_pnl > 0

            # Update local learning stats for this bridge instance
            # 更新此桥接器实例的本地学习统计
            with self._lock:
                self._learning_stats["total_trades"] += 1
                if win:
                    self._learning_stats["winning_trades"] += 1
                total = self._learning_stats["total_trades"]
                wins = self._learning_stats["winning_trades"]

            # Calculate win_rate from local stats
            # 从本地统计计算胜率
            win_rate = wins / total if total > 0 else 0.0

            # Update metrics in the gate
            # 更新门控中的指标
            self._learning_tier_gate.update_metrics(
                observation_count=total,
                win_rate=win_rate,
            )

            # Attempt promotion to next tier if eligible
            # 如果符合条件，尝试晋升到下一个等级
            next_tier_method = getattr(self._learning_tier_gate, '_next_tier', None)
            if next_tier_method:
                from .learning_tier_gate import LearningTier
                current = self._learning_tier_gate.current_tier
                next_tier = next_tier_method(current)

                if next_tier > current:
                    eligible, reasons = self._learning_tier_gate.check_tier_eligibility(next_tier)
                    if eligible:
                        try:
                            self._learning_tier_gate.promote_tier(
                                next_tier,
                                initiator="LearningGate",
                                reason=f"auto_promotion from {current.name} to {next_tier.name}",
                            )
                            logger.info(
                                "Learning tier auto-promoted: %s → %s / 学习等级自动晋升",
                                current.name,
                                next_tier.name,
                            )
                        except Exception as e:
                            logger.debug("Learning tier promotion error (non-fatal): %s", e)
        except Exception as e:
            logger.debug("Learning tier gate error (non-fatal): %s", e)

    def _emit_round_trip(self, symbol: str, strategy_name: str, exit_price: float, close_pnl: float) -> None:
        """
        Core round-trip completion handler — shared by intent-path and tick-path closes.
        Pops _open_positions, fires G1 + E1 callbacks, unregisters from StopManager.
        核心 round-trip 完成处理器 — 被意图路径和 tick 路径共用。
        弹出 _open_positions，触发 G1 + E1 回调，从 StopManager 取消注册。
        """
        key = f"{strategy_name}:{symbol}"

        with self._lock:
            pos_info = self._open_positions.pop(key, None)

        hold_ms = 0
        regime = "unknown"
        entry_ts_ms = int(time.time() * 1000)
        entry_price = 0.0
        qty = 0.0

        if pos_info:
            hold_ms = int(time.time() * 1000) - pos_info.get("entry_ts_ms", int(time.time() * 1000))
            regime = pos_info.get("regime", "unknown")
            entry_ts_ms = pos_info.get("entry_ts_ms", int(time.time() * 1000))
            entry_price = pos_info.get("entry_price", 0.0)
            qty = pos_info.get("qty", 0.0)

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

        # L1.01: Trade Attribution / L1.01：交易归因
        # 当交易完成时，分解交易为归因因子（ALPHA/TIMING/SIZING/EXECUTION/COST/LUCK）
        # When trade completes, decompose into attribution factors
        if self._trade_attribution and entry_price > 0 and qty > 0:
            try:
                import datetime
                import uuid

                exit_ts_ms = int(time.time() * 1000)
                entry_dt = datetime.datetime.fromtimestamp(entry_ts_ms / 1000.0, tz=datetime.timezone.utc)
                exit_dt = datetime.datetime.fromtimestamp(exit_ts_ms / 1000.0, tz=datetime.timezone.utc)
                trade_id = f"{strategy_name}:{symbol}:{uuid.uuid4().hex[:8]}"

                # Calculate gross PnL from entry/exit prices and quantity
                # 从入场/出场价格和数量计算毛利润
                gross_pnl = (exit_price - entry_price) * qty

                # Call attribution engine with minimal required parameters
                # 用最少必需的参数调用归因引擎
                attribution_result = self._trade_attribution.attribute_trade(
                    trade_id=trade_id,
                    symbol=symbol,
                    strategy=strategy_name,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=qty,
                    entry_timestamp=entry_dt,
                    exit_timestamp=exit_dt,
                    market_prices_at_entry={},  # Empty dict as default
                    market_prices_at_exit={},   # Empty dict as default
                    fees_paid=0.0,              # Could be enhanced with actual fees
                    slippage=0.0,               # Could be enhanced with actual slippage
                    ai_cost=0.0,                # Could be enhanced with model costs
                )

                # Log attribution results for learning_tier
                # 将归因结果记录到学习层
                logger.info(
                    "Trade attribution: %s → skill=%.2f%% luck=%.2f%% alpha=%.4f / 交易归因: skill=%.2f%% luck=%.2f%%",
                    trade_id,
                    attribution_result.skill_pct * 100,
                    attribution_result.luck_pct * 100,
                    attribution_result.attribution_scores[0].score if attribution_result.attribution_scores else 0.0,
                )
            except Exception as e:
                logger.debug("Trade attribution error (non-fatal): %s", e)

        # EX-05 §3: Learning Tier Auto-Promotion / EX-05 §3：学习等级自动晋升
        # Record trade outcome and check for promotion eligibility
        # 记录交易结果并检查晋升资格
        self._try_learning_promotion(close_pnl)

        # Batch 9: Emit ROUND_TRIP_COMPLETE to MessageBus for AnalystAgent
        # Batch 9：通过消息总线发送 ROUND_TRIP_COMPLETE 给 AnalystAgent
        if self._message_bus:
            try:
                from .multi_agent_framework import AgentMessage, AgentRole, MessageType
                rt_msg = AgentMessage(
                    sender=AgentRole.EXECUTOR,
                    receiver=AgentRole.ANALYST,
                    message_type=MessageType.ROUND_TRIP_COMPLETE,
                    priority=5,
                    payload={
                        "trade_id": f"{strategy_name}:{symbol}:{int(time.time())}",
                        "symbol": symbol,
                        "strategy": strategy_name,
                        "direction": "long" if pos_info and pos_info.get("side") == "Buy" else "short",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": close_pnl,
                        "hold_ms": hold_ms,
                        "regime": regime,
                        "timestamp_ms": int(time.time() * 1000),
                    },
                )
                self._message_bus.send(rt_msg)
            except Exception as _rt_err:
                logger.debug("MessageBus ROUND_TRIP_COMPLETE send error (non-fatal): %s", _rt_err)

        # Batch 9: Register trade result as INFERENCE in Perception Plane
        # Batch 9：将交易结果注册为 INFERENCE 到感知平面
        if self._perception_plane:
            try:
                from .perception_data_plane import DataSourceType, CognitiveLevel
                self._perception_plane.register_data(
                    source_type=DataSourceType.LEARNING_HISTORY,
                    content={"symbol": symbol, "strategy": strategy_name, "pnl": close_pnl, "regime": regime},
                    source_detail="round_trip_complete",
                    cognitive_level=CognitiveLevel.INFERENCE,
                    symbols=[symbol],
                    marked_by="PipelineBridge._emit_round_trip",
                    marking_reason="Trade result analysis = INFERENCE (learning data)",
                )
            except Exception:
                pass  # Non-fatal / 非致命

        logger.info(
            "Round-trip complete: %s %s pnl=%.4f hold=%.1fh regime=%s / 交易完成",
            strategy_name, symbol, close_pnl, hold_ms / 3600000, regime,
        )

    def _on_round_trip_complete(self, intent: Any, exit_price: float, close_pnl: float) -> None:
        """
        Called when a position is closed via immediate market-order fill in submit_order().
        Delegates to _emit_round_trip.
        通过 submit_order() 即时成交路径平仓时调用，委托给 _emit_round_trip。
        """
        symbol = intent.symbol
        strategy_name = getattr(intent, "strategy_name", "unknown")
        self._emit_round_trip(symbol, strategy_name, exit_price, close_pnl)

    def on_tick_result(self, tick_result: dict) -> None:
        """
        Called by MarketDataDispatcher after engine.tick() produced fills.
        Detects positions closed via tick path (risk_auto_close, time stop, soft stop)
        and fires E1/G1 hooks that the submit_order path would otherwise miss.

        由 MarketDataDispatcher 在 engine.tick() 产生成交后调用。
        检测通过 tick 路径平仓的仓位（risk_auto_close/时间止损/软止损），
        触发 submit_order 路径本会遗漏的 E1/G1 回调。
        """
        fills = tick_result.get("fills", [])
        if not fills:
            return

        # Snapshot tracked open positions to avoid holding lock during callbacks
        with self._lock:
            tracked = dict(self._open_positions)

        if not tracked:
            return

        already_emitted: set = set()

        for fill in fills:
            symbol = fill.get("symbol", "")
            fill_side = fill.get("side", "")   # "Buy" or "Sell"
            fill_price = fill.get("price", 0.0)
            close_fee = fill.get("fee", 0.0)

            if not symbol or fill_price <= 0:
                continue

            # Find a tracked open position for this symbol with a matching close direction
            for key, pos_info in tracked.items():
                if pos_info.get("symbol") != symbol:
                    continue
                if key in already_emitted:
                    continue

                pos_side = pos_info.get("side", "")  # "long" or "short"
                is_close = (
                    (pos_side == "long" and fill_side == "Sell") or
                    (pos_side == "short" and fill_side == "Buy")
                )
                if not is_close:
                    continue

                # Approximate close_pnl from entry/exit price (entry fee already sunk)
                entry_price = pos_info.get("entry_price", 0.0)
                qty = pos_info.get("qty", 0.0)
                if entry_price > 0 and qty > 0:
                    raw_pnl = (fill_price - entry_price) * qty if pos_side == "long" \
                        else (entry_price - fill_price) * qty
                    close_pnl = raw_pnl - close_fee
                else:
                    close_pnl = 0.0

                strategy_name = pos_info.get("strategy_name", "unknown")
                self._emit_round_trip(symbol, strategy_name, fill_price, close_pnl)
                already_emitted.add(key)
                break  # one emit per tracked position per tick

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
