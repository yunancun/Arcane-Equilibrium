"""
Pipeline Bridge — Core Mixin (lifecycle, tick processing, intent submission).
管線橋接器 — 核心 Mixin（生命週期、tick 處理、意圖提交）。

Split from pipeline_bridge.py (TD-01) to stay under 1200-line limit.
"""
from __future__ import annotations

import json as _json_mod
import logging
import os
import threading
import time
from typing import Any

from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


class _BridgeCoreMixin:
    """Core lifecycle, tick processing, and intent submission for PipelineBridge.

    # ── External dependencies injected via set_*() methods (E5 #25) ──
    # 通過 set_*() 方法注入的外部依賴（E5 #25）
    #
    # These dependencies are NOT passed in __init__ — they are set post-construction
    # by the startup wiring code (phase2_strategy_routes.py / main.py).
    # 這些依賴不在 __init__ 中傳入，而是由啟動階段接線代碼在構造後注入。
    #
    # Core execution pipeline / 核心執行管線:
    #   1. _governance_hub   (set_governance_hub)       — GovernanceHub: SM-01 auth + SM-02 lease + SM-04 risk
    #   2. _guardian_agent   (set_guardian_agent)        — GuardianAgent: primary trade gate (fail-closed)
    #   3. _h0_gate          (set_h0_gate)              — H0Gate: deterministic pre-trade filter (<1ms SLA)
    #   4. _demo_connector   (set_demo_connector)       — BybitDemoConnector: dual execution mirror
    #   5. _executor_agent   (set_executor_agent)       — ExecutorAgent: order execution + quality feedback
    #
    # Data & intelligence / 數據與情報:
    #   6. _ollama_client    (set_ollama_client)         — OllamaClient: L1 pre-trade edge filter (advisory)
    #   7. _scout_agent      (set_scout_agent)           — ScoutAgent: local market intelligence
    #   8. _strategist_agent (set_strategist_agent)      — StrategistAgent: AI-evaluated intents
    #   9. _analyst_agent    (set_analyst_agent)         — AnalystAgent: L2 pattern analysis cron
    #
    # Observability & learning / 可觀測性與學習:
    #  10. _perception_plane  (set_perception_plane)     — PerceptionPlane: cognitive honesty (Principle 10)
    #  11. _trade_attribution (set_trade_attribution)    — TradeAttributionEngine: trade attribution
    #  12. _message_bus       (set_message_bus)          — MessageBus: inter-agent communication
    #  13. _learning_tier_gate(set_learning_tier_gate)   — LearningTierGate: auto-promotion of learning tiers
    #
    # Alerting & deployment / 告警與部署:
    #  14. _telegram          (set_telegram)             — Telegram alerter: trade notifications
    #  15. _observation_writer(set_observation_writer)   — Callback: auto-observations on round-trip close
    #  16. _auto_deployer     (set_auto_deployer)        — StrategyAutoDeployer: consecutive-loss tracking
    #  17. _scanner_rate_limiter(set_scanner_rate_limiter) — ScannerRateLimiter: scan rate control
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
        self._last_l2_cron_ts: float = 0.0  # Batch 10: Last L2 cron trigger timestamp / L2 Cron 上次触发时间
        self._executor_agent = None  # Batch 11: Set externally for ExecutorAgent / 执行者代理
        self._h0_gate: Any = None  # P1-16: H0 deterministic gate / H0 確定性門控
        # Wave 7a 方案 B：運行時 symbol → category 映射，由 StrategyAutoDeployer 部署策略時填充。
        # Wave 7a Plan B: runtime symbol-to-category map, populated by StrategyAutoDeployer on
        # strategy deployment. Prevents _infer_category_from_symbol from guessing for known symbols.
        self._symbol_category_map: dict[str, str] = {}
        # tick_size 快取：symbol → float，用於 Demo 止損價精度取整
        # Tick size cache: symbol → float, for Demo stop-loss price rounding precision
        self._symbol_registry: Any = None  # SymbolCategoryRegistry（外部注入）

        # U-04: Cost-aware entry gate — reject trades where ATR < round-trip cost threshold
        # U-04：成本感知入場門檻 — ATR 低於來回成本閾值時拒絕開倉
        self._cost_gate_enabled: bool = True
        # Daily trade counter — reset on date change for safety-valve logic
        # 每日成交計數器 — 日期變更時重置，用於安全閥邏輯
        self._daily_trade_count: int = 0
        self._daily_trade_date: str = ""  # "YYYY-MM-DD" / 當日日期字串

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

    def set_ollama_client(self, client: Any) -> None:
        """
        Set OllamaClient for L1 pre-trade edge filter.
        设置 OllamaClient 用于 L1 交易前 edge 过滤。
        """
        self._ollama_client = client
        logger.info("OllamaClient set for pre-trade edge filter / 已设置 OllamaClient 用于交易前 edge 过滤")

    def set_analyst_agent(self, agent: Any) -> None:
        """
        Batch 10: Set AnalystAgent for L2 pattern analysis cron trigger.
        设置 AnalystAgent 用于 L2 模式分析 Cron 触发。
        """
        self._analyst_agent = agent
        logger.info("AnalystAgent set for L2 cron trigger / 已设置 AnalystAgent 用于 L2 Cron 触发")

    def set_executor_agent(self, agent: Any) -> None:
        """
        Batch 11: Set ExecutorAgent for order execution wrapping + quality feedback.
        设置 ExecutorAgent 用于订单执行包装 + 质量反馈。
        """
        self._executor_agent = agent
        logger.info("ExecutorAgent set for execution wrapping / 已设置 ExecutorAgent 用于执行包装")

    def set_h0_gate(self, gate: Any) -> None:
        """Set H0Gate for deterministic pre-trade filtering (P1-16).
        設置 H0 確定性門控以進行確定性交易前過濾（P1-16）。
        """
        self._h0_gate = gate

    def set_symbol_registry(self, registry: Any) -> None:
        """Set SymbolCategoryRegistry for tick_size lookup (price rounding).
        設置 SymbolCategoryRegistry 以查詢 tickSize（價格取整精度）。
        """
        self._symbol_registry = registry

    def register_symbol_category(self, symbol: str, category: str) -> None:
        """
        登記 symbol 的 Bybit API category，供 kline/funding 查詢使用。
        Register symbol's Bybit API category for use in kline/funding queries.

        由 StrategyAutoDeployer 在部署策略時調用，確保 category 來自掃描器的真相源。
        Called by StrategyAutoDeployer on strategy deployment; category comes from scanner,
        which is the authoritative source of truth for symbol classification.

        優先級高於 _infer_category_from_symbol() 的命名啟發式推斷。
        Takes precedence over _infer_category_from_symbol() heuristic name inference.
        """
        self._symbol_category_map[symbol] = category
        logger.debug("Registered symbol category: %s → %s / 登記 symbol 品類：%s → %s",
                     symbol, category, symbol, category)

    def activate(self) -> None:
        """DEPRECATED (RC-10 + RC-11): No longer called in production.
        已棄用（RC-10 + RC-11）：生產環境不再調用。

        Rust engine handles kline bootstrap via its own WebSocket connection.
        Rust 引擎通過自己的 WebSocket 連接處理 K 線引導。
        """
        self._active = True
        logger.info("PipelineBridge activated (DEPRECATED — Rust engine handles ticks) / "
                     "管线桥接器已激活（已棄用 — Rust 引擎處理 tick）")

    def _bootstrap_historical_data(self) -> None:
        """
        Bootstrap klines + ATR in background thread (non-blocking).
        在背景線程中引導 K 線 + ATR（不阻塞事件循環）。
        """
        # 1. Bootstrap historical klines
        try:
            results = self._km.bootstrap_from_rest(limit=200)
            total = sum(results.values()) if results else 0
            if total > 0:
                logger.info("Kline bootstrap loaded %d klines / K线引导加载了 %d 根", total, total)
        except Exception:
            logger.exception("Kline bootstrap failed (non-fatal) / K线引导失败（非致命）")

        # ARCH-RC1 1C-3-E: ATR bootstrap from Python RiskManager removed.
        # Rust engine owns ATR price tracking; Python RiskManager is now a 53-line
        # RiskViewClient shim with no _price_tracker attribute.
        # ARCH-RC1 1C-3-E: 已移除從 Python RiskManager bootstrap ATR 的死路徑，
        # ATR 由 Rust 引擎權威持有。

        logger.info("Background bootstrap complete / 背景引導完成")

        # Restore strategy state if available / 恢复策略状态
        try:
            if os.path.exists(self._strategy_state_path):
                with open(self._strategy_state_path, "r") as f:
                    saved = _json_mod.load(f)
                self._orch.restore_all_strategy_state(saved)
                logger.info("Strategy state restored from %s / 策略状态已恢复", self._strategy_state_path)
        except Exception:
            logger.exception("Strategy state restore failed (non-fatal) / 策略状态恢复失败")

    # DEAD-PY-1: deactivate() removed — no callers in production (RC-10 retired).
    # Strategy state persistence now handled by Rust engine.
    # deactivate() 已移除（RC-10 後無生產調用者），策略狀態持久化移至 Rust 引擎。

    @property
    def is_active(self) -> bool:
        return self._active

    def on_tick(self, event: Any) -> None:
        """
        DEPRECATED (RC-10 + RC-11): Never called in production — Rust engine handles ALL ticks.
        已棄用（RC-10 + RC-11）：生產環境永不調用 — Rust 引擎處理所有 tick。

        RC-10: All activate() calls removed — self._active is always False in production.
        RC-11: MarketDataDispatcher.engine.tick() also disabled — no Python tick path remains.
        Rust tick_pipeline handles: kline aggregation, indicators, signals, strategies,
        governance cascade, order matching, stop checks, PnL tracking.

        RC-10：所有 activate() 調用已移除 — self._active 在生產中始終為 False。
        RC-11：MarketDataDispatcher.engine.tick() 也已禁用 — 無 Python tick 路徑殘留。

        Method body retained for test coverage (tests set _active=True explicitly).
        方法體保留供測試覆蓋（測試顯式設置 _active=True）。
        """
        if not self._active:
            return

        with self._lock:
            self._stats["ticks_received"] += 1
            self._stats["last_tick_ts_ms"] = now_ms()

        # Extract event fields (including volume for dynamic slippage)
        # 提取事件欄位（含成交量，用於動態滑點計算）
        if isinstance(event, dict):
            symbol = event.get("symbol", "")
            price = float(event.get("last_price", 0.0))
            raw_ts = event.get("ts_ms")
            ts_ms = int(raw_ts) if raw_ts is not None and raw_ts != 0 else now_ms()
            _vol_24h = event.get("volume_24h")
        else:
            symbol = getattr(event, "symbol", "")
            price = float(getattr(event, "last_price", 0.0))
            raw_ts = getattr(event, "ts_ms", None)
            ts_ms = int(raw_ts) if raw_ts is not None and raw_ts != 0 else now_ms()
            _vol_24h = getattr(event, "volume_24h", None)

        if not symbol or price <= 0:
            return

        # Track latest prices for intent submission (fixes C1: positions is dict, not list)
        self._latest_prices[symbol] = price

        # Delegate to sub-methods / 委派给子方法
        self._tick_update_market_data(symbol, price, ts_ms, event, _vol_24h)
        self._tick_run_strategies(symbol, price, ts_ms)
        self._tick_check_risk(symbol, price, ts_ms)
        self._tick_update_stats(symbol, price, ts_ms)

    def _tick_update_market_data(self, symbol: str, price: float, ts_ms: int, event: Any, _vol_24h: Any) -> None:
        """
        Sub-method 1: price updates, kline feed, slippage cache, H0Gate, perception plane.
        子方法 1：价格更新、K线喂入、滑点缓存、H0Gate 时间戳、感知平面注册。
        """
        # Update dynamic slippage cache from WS volume data (non-critical, best-effort)
        # 從 WS 成交量數據更新動態滑點緩存（非關鍵路徑，盡力更新）
        if _vol_24h is not None and _vol_24h > 0:
            try:
                self._engine.update_slippage_cache({symbol: float(_vol_24h)})
            except Exception:
                pass  # Slippage update failure is non-fatal / 滑點更新失敗不影響主流程

        # P1-16: Update H0Gate price timestamp for freshness check
        # P1-16：更新 H0Gate 價格時間戳以供新鮮度檢查
        if self._h0_gate is not None:
            try:
                self._h0_gate.update_price_ts(symbol, ts_ms)
            except Exception as _h0_ts_err:
                logger.debug("H0Gate price_ts update error: %s", _h0_ts_err)

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

        # 3. Periodic volume refresh from REST API (every 60 real seconds, time-driven)
        # 定期从 REST API 刷新成交量（每 60 秒真实时间，时间驱动）
        # T2.07: Check scanner rate limiter before full market scan
        # NOTE: Runs in background thread to avoid blocking tick processing.
        # 注意：在背景線程中執行以避免阻塞 tick 處理管線。
        _now = time.time()
        if _now - self._last_volume_refresh_ts >= 60.0:
            self._last_volume_refresh_ts = _now
            if self._scanner_rate_limiter:
                can_scan, reason = self._scanner_rate_limiter.can_scan()
                if can_scan:
                    threading.Thread(
                        target=self._refresh_kline_volume, daemon=True,
                        name="bridge-volume-refresh",
                    ).start()
                    self._scanner_rate_limiter.record_scan_complete()
            else:
                threading.Thread(
                    target=self._refresh_kline_volume, daemon=True,
                    name="bridge-volume-refresh",
                ).start()

        # 4. Periodic funding rate check (every 300 real seconds = 5 minutes, time-driven)
        # 定期 funding rate 检查（每 300 秒真实时间 = 5 分钟，时间驱动）
        # NOTE: Runs in background thread to avoid blocking tick processing.
        # 注意：在背景線程中執行以避免阻塞 tick 處理管線。
        if _now - self._last_funding_check_ts >= 300.0:
            self._last_funding_check_ts = _now
            threading.Thread(
                target=self._check_funding_rates, daemon=True,
                name="bridge-funding-check",
            ).start()

    def _tick_run_strategies(self, symbol: str, price: float, ts_ms: int) -> None:
        """
        Sub-method 2: strategy on_tick calls, intent collection and submission.
        子方法 2：策略 on_tick 调用、意图收集与提交。
        """
        # 2. Feed tick-driven strategies (Grid Trading, etc.)
        try:
            self._orch.dispatch_tick(symbol, price, ts_ms)
        except Exception:
            logger.exception("Orchestrator dispatch_tick error / 编排器 dispatch_tick 异常")
            with self._lock:
                self._stats["errors"] += 1

        # 5. Process pending intents -> submit to paper engine
        if self._auto_submit:
            self._process_pending_intents()

    def _tick_check_risk(self, symbol: str, price: float, ts_ms: int) -> None:
        """
        Sub-method 3: stop-loss checks, risk monitoring.
        子方法 3：止损检查、风控监控。
        """
        # 6. Check stop-losses against current prices / 检查止损
        if self._stop_mgr and self._latest_prices:
            self._check_stops()

    def _tick_update_stats(self, symbol: str, price: float, ts_ms: int) -> None:
        """
        Sub-method 4: periodic scouts, analyst cron, dynamic risk adjustment, observability.
        子方法 4：定期 Scout 扫描、Analyst cron、动态风控调整、可观察性。
        """
        _now = time.time()

        # 4.5. Periodic Scout local scan (every 300s = 5 minutes, time-driven)
        # 定期 Scout 本地扫描（每 300 秒 = 5 分钟，时间驱动）
        if self._scout_agent and _now - self._last_scout_scan_ts >= 300.0:
            self._invoke_scout_scan(symbol, price)
            self._last_scout_scan_ts = _now

        # 4.6 Batch 10: L2 Cron trigger — every Sunday UTC 0:00, trigger Analyst L2 analysis
        # Batch 10：L2 Cron 触发器 — 每周日 UTC 0:00 触发 Analyst L2 分析
        if self._analyst_agent and _now - self._last_l2_cron_ts >= 3600.0:
            # Check once per hour; only fire if it's Sunday UTC 0:xx
            self._last_l2_cron_ts = _now
            self._try_l2_cron_trigger(_now)

        # 4.7 Dynamic risk adjustment: update risk_per_trade_pct from Sharpe (every 5 min)
        # 動態風控：根據 Sharpe 更新 risk_per_trade_pct（每 5 分鐘）
        if self._auto_deployer:
            try:
                self._auto_deployer.update_risk_from_sharpe()
            except Exception:
                pass  # Non-fatal / 非致命

    def _mark_intent(self, intent: Any, status: str) -> None:
        """
        Update intent history status via _history_ref (set by StrategyOrchestrator).
        On rejection, also notify the originating strategy to roll back optimistic state.
        通过 _history_ref 更新 intent 历史状态（由 StrategyOrchestrator 设置）。
        被拒时同时通知策略回滚乐观状态。
        """
        ref = getattr(intent, "_history_ref", None)
        if ref is not None:
            ref["status"] = status
        # Notify strategy to roll back on rejection / 拒绝时通知策略回滚
        if status.startswith("rejected") or status.startswith("blocked"):
            try:
                self._orch.notify_intent_rejected(intent)
            except Exception:
                pass  # Non-fatal: orchestrator may not support this yet / 非致命

    # ── U-04 helper: ATR% lookup for cost gate ──
    # U-04 輔助方法：從 IndicatorEngine 獲取 ATR% 用於成本門檻

    def _get_atr_pct_for_cost_gate(self, symbol: str) -> float | None:
        """
        Retrieve ATR% from IndicatorEngine cache for cost gate evaluation.
        從 IndicatorEngine 快取中獲取 ATR% 用於成本門檻評估。

        Returns ATR as percentage of price (e.g. 1.5 = 1.5%), or None if unavailable.
        返回 ATR 佔價格百分比（如 1.5 表示 1.5%），不可用時返回 None。
        """
        if not self._ie:
            return None
        try:
            # Try 1h timeframe first (most common for strategy decisions)
            # 先嘗試 1h 時間框架（策略決策最常用）
            atr_result = self._ie.get_indicator(symbol, "1h", "ATR(14)")
            if atr_result and "atr_percent" in atr_result:
                return float(atr_result["atr_percent"])
            # Fallback to 5m if 1h not available / 1h 不可用時回退到 5m
            atr_result = self._ie.get_indicator(symbol, "5m", "ATR(14)")
            if atr_result and "atr_percent" in atr_result:
                return float(atr_result["atr_percent"])
        except Exception:
            pass  # fail-open: return None → cost gate will pass through
        return None

    def _get_volume_24h(self, symbol: str) -> float:
        """
        Get cached 24h volume for a symbol (used by cost gate for slippage lookup).
        獲取快取的 24h 成交量（成本門檻用於滑點查找）。

        Returns 0.0 if unavailable (→ default slippage tier).
        不可用時返回 0.0（→ 使用默認滑點分級）。
        """
        if self._engine and hasattr(self._engine, "_volume_cache"):
            vol = self._engine._volume_cache.get(symbol, 0.0)
            return float(vol) if vol else 0.0
        return 0.0

    def _maybe_reset_daily_trade_count(self) -> None:
        """
        Reset daily trade counter on date change (UTC).
        日期變更時重置每日成交計數器（UTC）。
        """
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        if today != self._daily_trade_date:
            self._daily_trade_count = 0
            self._daily_trade_date = today

    def _process_pending_intents(self) -> None:
        """
        Orchestrator: collect intents, gate each one, submit approved, run post-execution hooks.
        編排器：收集意圖、逐個門控、提交已批准的、執行後置鉤子。

        APR01-HIGH-4 refactor: this method was a 462-line mega-method. Now delegates to
        four focused sub-methods while preserving exact behavioral semantics:
          1. _collect_pending_intents()    — gather + cap
          2. _gate_intent()               — H0 / governance / cost gate / Guardian / edge filter
          3. _submit_approved_intent()     — lease + OMS + Demo sync + stop registration
          4. _post_execution_hooks()       — round-trip / learning / deployer notify / Telegram

        APR01-HIGH-4 重構：原為 462 行巨型方法，現委派給四個專注子方法，完全保留原始行為語義。

        APR01-MEDIUM-12: Stats are accumulated in local counters and flushed
        once at the end, reducing lock acquisitions from ~27 per call to 1.
        APR01-MEDIUM-12：统计量先累积在本地计数器，最后一次性刷入共享 stats，
        将锁获取次数从每次调用约 27 次降至 1 次。

        Note: StrategistAgent.collect_pending_intents() was removed here (APR01-P1-3).
        It was deprecated in TD-2 (Wave 6 Sprint 2) — always returned [].
        StrategyAgent intents now flow via MessageBus → add_trade_intent() path.
        注意：已移除对 StrategistAgent.collect_pending_intents() 的调用（APR01-P1-3）。
        该方法在 TD-2 中已废弃（始终返回 []），策略意图现通过 MessageBus → add_trade_intent() 路径传递。
        """
        # U-04: Reset daily trade counter on date change (for safety-valve logic)
        # U-04：日期變更時重置每日成交計數器（用於安全閥邏輯）
        self._maybe_reset_daily_trade_count()

        intents = self._collect_pending_intents()
        if not intents:
            return

        # Get current market prices from tick history (fixes C1: positions is dict, not list)
        market_prices = dict(self._latest_prices)

        # APR01-MEDIUM-12: Local counters to batch stats updates — no lock needed until flush.
        # Reduces lock contention from ~27 acquisitions to 1 per method call.
        # APR01-MEDIUM-12：本地计数器批量累积统计更新 — 处理期间不需要锁，最后一次性刷入。
        _local_stats: dict[str, int] = {}
        _local_guardian: dict[str, int] = {}

        for intent in intents:
            try:
                # Phase 1: Gate checks (H0 + governance + Guardian + edge filter)
                # 階段 1：門控檢查（H0 + 治理 + Guardian + edge 過濾）
                gate_result = self._gate_intent(intent, market_prices, _local_stats, _local_guardian)
                if gate_result is None:
                    # Intent was rejected by one of the gates — skip to next intent
                    # 意圖被某個門控拒絕 — 跳到下一個意圖
                    continue

                _submit_qty, _submit_leverage, _effective_leverage = gate_result

                # Phase 2: Submit to paper engine + acquire lease
                # 階段 2：提交到 Paper 引擎 + 申請 lease
                result, category = self._submit_approved_intent(
                    intent, _submit_qty, _effective_leverage, market_prices, _local_stats,
                )
                if result is None:
                    # Lease acquisition failed — already counted in _local_stats
                    # Lease 申請失敗 — 已計入 _local_stats
                    continue

                # Phase 3: Post-execution hooks (round-trip, learning, Telegram)
                # 階段 3：後置鉤子（交易回合、學習、Telegram）
                self._post_execution_hooks(
                    intent, result, _submit_qty, _effective_leverage,
                    category, market_prices, _local_stats,
                )

            except Exception:
                logger.exception(
                    "Failed to submit intent: %s / 提交意图失败", intent,
                )
                _local_stats["errors"] = _local_stats.get("errors", 0) + 1

        # APR01-MEDIUM-12: Flush all accumulated stats in a single lock acquisition.
        # This replaces ~27 scattered `with self._lock` blocks with one batch update.
        # APR01-MEDIUM-12：一次性刷入所有累积的统计量，替代原来约 27 次分散的锁获取。
        if _local_stats or _local_guardian:
            with self._lock:
                for key, delta in _local_stats.items():
                    if key in ("intents_h0_blocked", "intents_lease_failed",
                               "intents_cost_rejected",
                               "demo_synced", "demo_diverged", "demo_spot_skipped"):
                        # These keys may not exist yet — use setdefault for first access
                        # 这些键可能尚不存在 — 首次访问时用 setdefault 初始化
                        self._stats.setdefault(key, 0)
                    self._stats[key] = self._stats.get(key, 0) + delta
                for key, delta in _local_guardian.items():
                    self._guardian_stats[key] = self._guardian_stats.get(key, 0) + delta

    # ── Sub-method 1: Collect and cap pending intents ──
    # 子方法 1：收集並限制待處理意圖

    def _collect_pending_intents(self) -> list:
        """
        Gather OrderIntents from orchestrator and apply the per-tick cap.
        從編排器收集 OrderIntent 並應用每 tick 上限。

        Returns a (possibly empty) list of intents capped to max_intents_per_tick.
        Orchestrator errors are caught and logged — returns [] on failure (fail-open
        for collection, since downstream gates will reject bad intents anyway).
        返回一個（可能為空的）意圖列表，已限制為 max_intents_per_tick。
        編排器錯誤會被捕獲並記錄 — 失敗時返回 []（收集階段 fail-open，
        因為下游門控會拒絕有問題的意圖）。
        """
        try:
            intents = self._orch.collect_pending_intents()
        except Exception:
            logger.exception("Failed to collect orchestrator intents / 收集编排器意图失败")
            intents = []

        if not intents:
            return []

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

        return intents

    def _submit_approved_intent(
        self,
        intent: Any,
        _submit_qty: float,
        _effective_leverage: float,
        market_prices: dict[str, float],
        _local_stats: dict[str, int],
    ) -> tuple[dict | None, str]:
        """
        Acquire Decision Lease, submit order to Paper engine, return result.
        申請 Decision Lease，將訂單提交到 Paper 引擎，返回結果。

        Handles:
          - Decision Lease acquisition (Principle 3: AI output != command)
          - Category extraction + unregistered symbol warning
          - Limit order price fallback
          - Paper engine submit_order() call

        處理：
          - Decision Lease 申請（原則 3：AI 輸出 != 命令）
          - 品類提取 + 未註冊 symbol 警告
          - Limit 單價格回退
          - Paper 引擎 submit_order() 調用

        Returns:
            (result_dict, category) on success; (None, category) if lease was denied.
        返回：
            成功時 (result_dict, category)；lease 被拒時 (None, category)。
        """
        def _bump(counter: dict, key: str, amount: int = 1) -> None:
            """Increment a local counter (no lock needed). / 累加本地计数器（无需锁）。"""
            counter[key] = counter.get(key, 0) + amount

        # H6: Acquire Decision Lease before execution (Principle 3: AI output ≠ command)
        # H6：執行前申請 Decision Lease，確保 Guardian 批准不直接等於執行命令（根原則 3）
        # fail-open when governance_hub is None (backward compat, no hub deployed)
        # fail-closed when hub exists but acquire_lease() returns None (hub denied the lease)
        # 若 governance_hub 為 None：fail-open（向後兼容，無 Hub 時不阻塞）
        # 若 Hub 存在但 acquire_lease 返回 None：fail-closed（Hub 拒絕，跳過此 intent）
        if self._governance_hub is not None:
            try:
                _intent_id_for_lease = (
                    getattr(intent, "intent_id", None)
                    or f"pb-{intent.symbol}-{intent.side}-{id(intent)}"
                )
                _lease_id = self._governance_hub.acquire_lease(
                    intent_id=_intent_id_for_lease,
                    scope="TRADE_ENTRY",
                    ttl_seconds=30,
                )
                if _lease_id is None:
                    # fail-closed: Guardian approved but lease acquisition failed
                    # 失敗默認收縮：Guardian 已批准但 lease 申請失敗，拒絕執行（DOC-01 §5.6）
                    logger.warning(
                        "pipeline_bridge: lease acquisition failed for intent %s %s, "
                        "skipping (fail-closed) / lease 申請失敗，跳過執行（fail-closed）",
                        intent.symbol, intent.side,
                    )
                    _bump(_local_stats, "intents_lease_failed")
                    self._mark_intent(intent, "rejected_lease")
                    return None, ""
            except Exception as _lease_err:
                # Lease acquisition error → fail-closed (DOC-01 §5.6)
                # Lease 申請異常 → fail-closed（不允許在治理狀態不明時執行）
                logger.error(
                    "pipeline_bridge: lease acquisition error — fail-closed: %s %s (%s) / "
                    "lease 申請異常 — fail-closed 拒絕",
                    intent.symbol, intent.side, _lease_err,
                )
                _bump(_local_stats, "intents_lease_failed")
                self._mark_intent(intent, "rejected_lease")
                return None, ""

        # Extract category from intent metadata (default: linear)
        # 从意图元数据提取品类（默认：linear）
        category = intent.metadata.get("category", "linear") if intent.metadata else "linear"
        # Wave 7a 方案 B：如果 category 是 fallback 且 symbol 未在運行時映射中登記，記錄 warning。
        # Wave 7a Plan B: warn when category defaults to linear for an unregistered symbol.
        # This helps detect symbols deployed without category registration.
        if category == "linear" and intent.symbol not in self._symbol_category_map:
            logger.warning(
                "Intent for %s has no explicit category and symbol is not in category map; "
                "defaulting to linear. Register via StrategyAutoDeployer to fix. "
                "/ intent 無明確 category 且 symbol 未在映射中登記，使用 linear 作 fallback：%s",
                intent.symbol,
                intent.symbol,
            )

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
            strategy_name=getattr(intent, "strategy_name", "") or "",
            leverage=_effective_leverage,  # propagate resolved leverage to Paper engine
        )

        _bump(_local_stats, "intents_submitted")

        return result, category
