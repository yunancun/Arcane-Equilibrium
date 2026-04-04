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
from .utils.time_utils import now_ms

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
    IPC relay + Agent callback container (RC-10/IPC-04 downgraded).
    IPC 中繼 + Agent 回調容器（RC-10/IPC-04 降級）。

    Previously: full tick processing bridge (KlineManager→Indicators→Signals→Strategies→Intents).
    Now: Rust engine handles ALL tick processing. This class is retained only for:
      1. Agent dependency injection (set_*() methods) — Scout/Strategist/Guardian etc.
      2. API state queries (get_stats(), _latest_prices fallback)
      3. Future Agent callback relay (on_tick_result from Rust IPC)
    Tick processing (on_tick) is DISABLED — self._active is never set to True (RC-10).

    之前：完整 tick 處理橋接。現在：Rust 引擎處理所有 tick。此類僅保留用於：
      1. Agent 依賴注入 2. API 狀態查詢 3. 未來 Agent 回調中繼
    """

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
        """DEPRECATED (IPC-04): No longer called in production (RC-10).
        已棄用（IPC-04）：生產環境不再調用（RC-10）。
        Activate the bridge and bootstrap historical data / 激活桥接器并引导历史数据"""
        self._active = True
        logger.info("PipelineBridge activated / 管线桥接器已激活")

        # Bootstrap in background thread to avoid blocking the async event loop.
        # Previously this ran synchronously and blocked ALL API requests during startup
        # (8-120+ HTTP calls to Bybit, each ~1-2s) — causing GUI freeze after restart.
        # 在背景線程中引導，避免阻塞 async 事件循環。
        # 之前同步執行會阻塞啟動時所有 API 請求（8-120+ 個 HTTP 調用）— 導致重啟後 GUI 卡死。
        import threading
        threading.Thread(
            target=self._bootstrap_historical_data,
            daemon=True,
            name="bridge-bootstrap",
        ).start()
        logger.info("Kline+ATR bootstrap started in background / K線+ATR 引導已在背景啟動")

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

        # 2. Bootstrap ATR price history from klines
        try:
            if self._engine and hasattr(self._engine, "risk_manager") and self._engine.risk_manager:
                tracker = self._engine.risk_manager._price_tracker
                bootstrapped_total = 0
                for symbol in (self._km.get_tracked_symbols() if hasattr(self._km, "get_tracked_symbols") else []):
                    buf = self._km.get_buffer(symbol, "5m")
                    if buf and len(buf) > 0:
                        klines_data = buf.latest(60)
                        count = tracker.bootstrap_from_klines(symbol, klines_data)
                        bootstrapped_total += count
                if bootstrapped_total > 0:
                    logger.info("ATR bootstrap seeded %d price points / ATR 引导注入 %d 个价格点", bootstrapped_total, bootstrapped_total)
        except Exception:
            logger.exception("ATR bootstrap failed (non-fatal) / ATR 引导失败（非致命）")

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
        DEPRECATED (IPC-04): Rust engine handles all tick processing.
        已棄用（IPC-04）：Rust 引擎處理所有 tick。

        This method is never called in production (RC-10 removed all activate() calls).
        Retained for backward compatibility with test mocks.
        此方法在生產環境中永不被調用（RC-10 移除了所有 activate() 調用）。
        保留��測試 mock 向後兼容。
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

    # ── Sub-method 2: Gate an individual intent ──
    # 子方法 2：對單個意圖進行門控檢查

    def _gate_intent(
        self,
        intent: Any,
        market_prices: dict[str, float],
        _local_stats: dict[str, int],
        _local_guardian: dict[str, int],
    ) -> tuple[float, float | None, float] | None:
        """
        Run all pre-submission gate checks on a single intent.
        對單個意圖執行所有提交前門控檢查。

        Gate pipeline (in order):
          1. Perception plane cognitive honesty check (Principle 10)
          2. H0 Gate deterministic filter — fail-closed (Principle 5: survival > profit)
          3. Governance Hub authorization — fail-closed
          4. Cost gate — ATR vs round-trip cost check — fail-open (Principle 13)
          5. Dynamic qty calculation + exchange rounding
          6. Guardian Agent verdict — fail-closed (DOC-01 §5.6)
          7. Edge filter — advisory only (logged, not blocking)

        門控管線（按順序）：
          1. 感知平面認知誠實檢查（原則 10）
          2. H0 確定性過濾 — fail-closed（原則 5：生存 > 利潤）
          3. 治理授權 — fail-closed
          4. 動態數量計算 + 交易所精度四捨五入
          5. Guardian 裁決 — fail-closed（DOC-01 §5.6）
          6. Edge 過濾 — 僅建議（記錄但不阻塞）

        Returns:
            (submit_qty, submit_leverage, effective_leverage) if approved.
            None if the intent was rejected by any gate (already logged + stats bumped).
        返回：
            若批准：(submit_qty, submit_leverage, effective_leverage)。
            若被任何門控拒絕：None（已記錄日誌並更新統計）。
        """
        def _bump(counter: dict, key: str, amount: int = 1) -> None:
            """Increment a local counter (no lock needed). / 累加本地计数器（无需锁）。"""
            counter[key] = counter.get(key, 0) + amount

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
                    _bump(_local_stats, "intents_rejected")
                    self._mark_intent(intent, "rejected_perception")
                    return None
            else:
                # Intent has no perception data marked (implicit FACT assumption for exchange data)
                # 意图无感知数据标记（假设交易所数据为 FACT）
                # This is acceptable for exchange-sourced signals
                pass

        # ── 0A-1: Apply learning feedback weights from StrategistAgent ──
        # 0A-1：應用 StrategistAgent 的學習反饋權重（模式洞察 → 策略偏好）
        # Pattern insights adjust strategy weights in [0.2, 2.0]; multiply into confidence.
        # Fail-open: if StrategistAgent unavailable, weight defaults to 1.0 (neutral).
        # 模式洞察調整策略權重 [0.2, 2.0]，乘入 confidence。
        # Fail-open：StrategistAgent 不可用時，權重默認 1.0（中性）。
        if self._strategist_agent is not None:
            try:
                _strategy_name = getattr(intent, "strategy_name", "") or ""
                _learning_weight = self._strategist_agent.get_strategy_weight(_strategy_name)
                if _learning_weight != 1.0:
                    _old_conf = getattr(intent, "confidence", None)
                    if _old_conf is not None and isinstance(_old_conf, (int, float)):
                        _new_conf = max(0.0, min(1.0, _old_conf * _learning_weight))
                        intent.confidence = _new_conf
                        logger.debug(
                            "0A-1: Learning weight applied to %s/%s: %.2f × %.2f = %.2f / "
                            "學習權重已應用：置信度 %.2f × 權重 %.2f = %.2f",
                            intent.symbol, _strategy_name,
                            _old_conf, _learning_weight, _new_conf,
                            _old_conf, _learning_weight, _new_conf,
                        )
            except Exception as _lw_err:
                # fail-open: learning weight error is non-fatal / 學習權重異常不阻塞
                logger.debug("0A-1: Learning weight lookup failed (fail-open): %s", _lw_err)

        # ── Sprint 5a: H0 Gate blocking — fail-closed (principle 5: survival > profit) ──
        # Sprint 5a：H0 Gate 阻擋模式 — fail-closed（根原則 5：生存 > 利潤）
        # H0 Gate blocking: stale data or unhealthy system state → reject intent entirely.
        # This is activated in Sprint 5a after H0 Gate SLA validation and Day 3 integration
        # confirmed the gate is safe to enforce. Previously warn-only (paper mode), now
        # fully blocking to protect against trading on bad market data.
        # H0 Gate 阻擋：數據過期或系統不健康時拒絕 intent，防止基於錯誤市場數據交易。
        # Sprint 5a 之前為 warn-only（paper 模式），現已切換為全面阻擋。
        if self._h0_gate is not None:
            try:
                _h0_category = (
                    intent.metadata.get("category", "linear")
                    if hasattr(intent, "metadata") and intent.metadata
                    else "linear"
                )
                _h0_result = self._h0_gate.check(intent.symbol, _h0_category)
                if not _h0_result.allowed:
                    # H0 Gate blocking — fail-closed to protect against stale/unhealthy market data
                    # H0 Gate 阻擋模式 — 數據過期或系統不健康時拒絕意圖，原則 5（生存 > 利潤）
                    _bump(_local_stats, "intents_h0_blocked")
                    logger.warning(
                        "H0Gate BLOCKED intent %s %s check=%s reason=%s latency=%dμs"
                        " / H0 門控已拒絕 intent：%s %s",
                        intent.symbol,
                        getattr(intent, "side", "?"),
                        _h0_result.check_name,
                        _h0_result.reason,
                        _h0_result.latency_us,
                        intent.symbol,
                        getattr(intent, "side", "?"),
                    )
                    self._mark_intent(intent, "blocked_h0")
                    return None  # skip this intent, do not submit
            except Exception as _h0_check_err:
                logger.warning(
                    "H0Gate check error (fail-open on exception, non-fatal): %s "
                    "/ H0 門控檢查異常（異常時 fail-open，非致命）",
                    _h0_check_err,
                )

        # Governance Hub authorization check / 治理集線器授權檢查
        if self._governance_hub:
            try:
                if not self._governance_hub.is_authorized():
                    logger.info(
                        "Intent rejected by governance: %s %s (not authorized) / 意图被治理拒絕",
                        intent.symbol, intent.side
                    )
                    _bump(_local_stats, "intents_rejected")
                    self._mark_intent(intent, "rejected_governance")
                    return None
            except Exception as exc:
                logger.error("Governance is_authorized error — fail-closed: %s", exc)
                _bump(_local_stats, "intents_rejected")
                self._mark_intent(intent, "rejected_governance")
                return None

        # ── U-04: Cost-aware entry gate (deterministic, fail-open) ──
        # U-04：成本感知入場門檻（確定性規則，數據缺失時 fail-open）
        # Reject entries where expected volatility (ATR%) is too low to cover round-trip costs.
        # 當預期波動率（ATR%）不足以覆蓋來回交易成本時拒絕開倉。
        if self._cost_gate_enabled:
            try:
                from local_model_tools.cost_gate import should_reject_for_cost
                _atr_pct = self._get_atr_pct_for_cost_gate(intent.symbol)
                _volume_24h = self._get_volume_24h(intent.symbol)
                _cost_reject, _cost_reason = should_reject_for_cost(
                    symbol=intent.symbol,
                    atr_pct=_atr_pct,
                    win_rate=0.5,  # default; future: dynamic from round-trip stats
                    daily_trade_count=self._daily_trade_count,
                    volume_24h=_volume_24h,
                )
                if _cost_reject:
                    _bump(_local_stats, "intents_cost_rejected")
                    logger.warning(
                        "Cost gate rejected %s %s: %s / 成本門檻拒絕",
                        intent.symbol, getattr(intent, "side", "?"), _cost_reason,
                    )
                    self._mark_intent(intent, "rejected_cost_gate")
                    return None
            except Exception as _cost_err:
                # Fail-open: cost gate error must not block trading
                # Fail-open：成本門檻異常不能阻塞交易
                logger.warning(
                    "Cost gate error (fail-open): %s / 成本門檻異常（fail-open）",
                    _cost_err,
                )

        # ── Batch 8: Guardian Agent as PRIMARY gate (fail-closed) ──
        # Batch 8：Guardian Agent 作为主门控（fail-closed）
        # Guardian verdict overrides all other filters (EX-06 §9).
        # If Guardian is unavailable → REJECTED (fail-closed, DOC-01 §5.6).
        # Original edge filter demoted to auxiliary reference (logged only).
        # Dynamic qty: recalculate based on current balance at submission time
        # 動態倉位：在提交時根據當前餘額重新計算
        _submit_qty = intent.qty
        if self._auto_deployer and market_prices.get(intent.symbol):
            try:
                _submit_qty = self._auto_deployer.compute_dynamic_qty(
                    intent.symbol, market_prices[intent.symbol]
                )
            except Exception:
                logger.debug("Dynamic qty fallback to intent.qty for %s", intent.symbol)

        # Round qty to exchange step precision (shared with Demo connector)
        # 統一四捨五入到交易所步長精度（與 Demo connector 共用）
        # Ensures Paper and Demo receive identical qty values.
        # INV-3: Pass category so inverse contracts round to integer contracts.
        # INV-3：傳入 category，確保 inverse 合約正確取整（整數張數）。
        try:
            from .bybit_demo_connector import round_qty_for_exchange
            _intent_category = (
                intent.metadata.get("category", "linear")
                if hasattr(intent, "metadata") and intent.metadata
                else "linear"
            )
            _submit_qty = round_qty_for_exchange(_submit_qty, category=_intent_category)
            if _submit_qty <= 0:
                logger.info("Qty rounds to zero for %s, skipping / qty 四捨五入為零，跳過", intent.symbol)
                self._mark_intent(intent, "rejected_qty_zero")
                return None
        except ImportError:
            pass  # Demo connector not available, use raw qty

        _submit_leverage = None  # may be overridden by Guardian MODIFIED verdict

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

                _bump(_local_guardian, "checked")

                if verdict.result == _RVR.REJECTED:
                    _bump(_local_guardian, "rejected")
                    _bump(_local_stats, "intents_rejected")
                    logger.info(
                        "Intent REJECTED by Guardian: %s %s (reason: %s, risk=%.2f) / "
                        "意图被 Guardian 拒绝",
                        intent.symbol, intent.side, verdict.reason, verdict.risk_score,
                    )
                    self._mark_intent(intent, "rejected_guardian")
                    return None

                elif verdict.result == _RVR.MODIFIED:
                    _bump(_local_guardian, "modified")
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
                    _bump(_local_guardian, "approved")
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
                _bump(_local_guardian, "errors")
                _bump(_local_stats, "intents_rejected")
                self._mark_intent(intent, "rejected_guardian")
                return None

        else:
            # P0-2 FIX: Guardian unavailable → fail-closed REJECT (DOC-01 §5.6)
            # Guardian 不可用 → fail-closed 拒绝
            logger.error(
                "Guardian unavailable — fail-closed REJECT: %s %s",
                getattr(intent, "symbol", "?"), getattr(intent, "side", "?")
            )
            _bump(_local_stats, "intents_rejected")
            self._mark_intent(intent, "rejected_no_guardian")
            return None

        # Resolve final effective leverage:
        # Guardian MODIFIED value > intent.metadata["leverage"] > intent.leverage attr > 1.0
        # 确定最终有效杠杆：Guardian 修改值 > metadata > intent 属性 > 默认 1.0
        _effective_leverage = float(
            _submit_leverage
            or (intent.metadata or {}).get("leverage")
            or getattr(intent, "leverage", None)
            or 1.0
        )

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

        return (_submit_qty, _submit_leverage, _effective_leverage)

    # ── Sub-method 3: Submit an approved intent to the paper engine ──
    # 子方法 3：將已批准的意圖提交到 Paper 引擎

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

    # ── Sub-method 4: Post-execution hooks ──
    # 子方法 4：執行後置鉤子

    def _post_execution_hooks(
        self,
        intent: Any,
        result: Any,
        _submit_qty: float,
        _effective_leverage: float,
        category: str,
        market_prices: dict[str, float],
        _local_stats: dict[str, int],
    ) -> None:
        """
        Handle everything after Paper engine submit_order() returns.
        處理 Paper 引擎 submit_order() 返回後的所有事項。

        Responsibilities:
          - Classify result as accepted/rejected and update stats + intent status
          - On accepted fill: track position open or detect round-trip close
          - Notify auto-deployer of fills (strategy position state sync)
          - Sync to Bybit Demo (mirror paper, fail-open for Demo errors)
          - Fire Telegram alert for market orders

        職責：
          - 將結果分類為已接受/已拒絕，更新統計和意圖狀態
          - 成交時：追蹤開倉或偵測交易回合完成
          - 通知自動部署器成交情況（策略倉位狀態同步）
          - 同步到 Bybit Demo（鏡像 Paper，Demo 錯誤 fail-open）
          - 市價單發送 Telegram 告警
        """
        def _bump(counter: dict, key: str, amount: int = 1) -> None:
            """Increment a local counter (no lock needed). / 累加本地计数器（无需锁）。"""
            counter[key] = counter.get(key, 0) + amount

        order = result.get("order", {}) if isinstance(result, dict) else {}
        rejected = result.get("rejected_reason") if isinstance(result, dict) else None

        if rejected:
            _bump(_local_stats, "intents_rejected")
            self._mark_intent(intent, "rejected_risk")
            logger.info(
                "Intent rejected: %s %s %s qty=%.6f reason=%s / 意图被拒",
                intent.symbol, intent.side, intent.order_type,
                intent.qty, rejected,
            )
            return

        _bump(_local_stats, "intents_accepted")
        # U-04: Increment daily trade counter for cost gate safety-valve
        # U-04：遞增每日成交計數器（成本門檻安全閥用）
        self._daily_trade_count += 1
        self._mark_intent(intent, "submitted")
        logger.info(
            "Intent submitted: %s %s %s qty=%.6f / 意图已提交",
            intent.symbol, intent.side, intent.order_type, intent.qty,
        )

        # ── Submit to Bybit Demo FIRST (before position tracking) ──
        # Demo 必須先於持倉追蹤提交，這樣 _on_position_open 才能查到 Demo 成交價
        # Demo submission must happen before position tracking so that
        # _on_position_open can query Demo's actual fill price for stop-loss.
        _demo_synced = False
        if self._demo_connector and self._demo_connector.is_enabled:
            # SPOT-DEMO: Bybit spot trades appear as wallet balance changes,
            # not as positions.  Comparing Paper spot positions against Demo
            # positions will always mismatch (Demo side is always empty).
            # Skip Demo submission for spot — track Paper-side only.
            # 现货交易在 Demo 端体现为余额变化而非持仓，跳过 Demo 提交，仅记录 Paper。
            if category == "spot":
                logger.debug(
                    "Skipping Demo submission for spot %s %s (spot=wallet-only on Demo) / "
                    "跳过现货 Demo 提交（现货体现为余额变化）",
                    intent.symbol, intent.side,
                )
                _bump(_local_stats, "demo_spot_skipped")
            else:
                try:
                    # Set leverage on Demo before placing the order so that
                    # margin math and PnL match Paper (Paper always uses
                    # _effective_leverage; Demo would otherwise keep whatever
                    # the Bybit account last had configured per-symbol).
                    # 在下单前先同步杠杆，确保 Demo 保证金计算与 Paper 一致。
                    self._demo_connector.set_leverage(
                        symbol=intent.symbol,
                        buy_leverage=_effective_leverage,
                        category=category,
                    )
                    demo_result = self._demo_connector.submit_order(
                        symbol=intent.symbol,
                        side=intent.side,
                        order_type="Market" if intent.order_type == "market" else "Limit",
                        qty=_submit_qty,
                        price=intent.price,
                        category=category,
                    )
                    if demo_result.get("retCode") == 0:
                        _demo_synced = True
                    else:
                        logger.warning(
                            "Demo order REJECTED: %s %s qty=%.6f reason=%s — Paper/Demo DIVERGED / "
                            "Demo 訂單被拒：Paper 已接受但 Demo 拒絕，數據已分歧",
                            intent.symbol, intent.side, _submit_qty,
                            demo_result.get("retMsg"),
                        )
                except Exception as _demo_err:
                    logger.warning(
                        "Demo connector error: %s %s — %s — Paper/Demo DIVERGED / "
                        "Demo 連接異常：數據已分歧",
                        intent.symbol, intent.side, _demo_err,
                    )
                # Track sync status in local counters (flushed at end)
                # 在本地计数器中追踪同步状态（最后一次性刷入）
                if _demo_synced:
                    _bump(_local_stats, "demo_synced")
                else:
                    _bump(_local_stats, "demo_diverged")

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
                # U-05: Extract close fee from fill record for round-trip cost accounting.
                # U-05：从成交记录提取平仓费用用于 round-trip 成本核算。
                _close_fee = fill.get("fee", 0.0)
                self._on_round_trip_complete(intent, fill_price, close_pnl, close_fee=_close_fee)
            else:
                # New position opened — start tracking
                # 新持仓开仓 — 开始追踪（用 rounded qty 確保與 Demo 一致）
                # ★ FIX: 從 Demo 取得真實成交價，用於交易所條件止損單
                # Query Demo position avgPrice for accurate stop-loss trigger.
                # Market orders fill instantly on Bybit; position avgPrice is available.
                _demo_fill = 0.0
                if _demo_synced:
                    try:
                        _pos_resp = self._demo_connector.get_positions(
                            category=category, symbol=intent.symbol,
                        )
                        _pos_list = _pos_resp.get("result", {}).get("list", [])
                        for _p in _pos_list:
                            if _p.get("symbol") == intent.symbol and float(_p.get("size", 0)) > 0:
                                _demo_fill = float(_p.get("avgPrice", 0))
                                break
                        if _demo_fill > 0:
                            logger.debug(
                                "Demo fill price for %s: %.8f (Paper: %.8f) / "
                                "Demo 成交價：%.8f（Paper：%.8f）",
                                intent.symbol, _demo_fill, fill_price,
                                _demo_fill, fill_price,
                            )
                    except Exception as _demo_price_err:
                        logger.debug(
                            "Could not get Demo fill price for %s: %s — using Paper price / "
                            "無法取得 Demo 成交價，使用 Paper 價格",
                            intent.symbol, _demo_price_err,
                        )
                self._on_position_open(
                    intent, fill_price, actual_qty=_submit_qty,
                    demo_fill_price=_demo_fill,
                )
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

        if self._telegram and intent.order_type == "market":
            price = market_prices.get(intent.symbol, 0)
            self._telegram.alert_trade(intent.symbol, intent.side, _submit_qty, price, getattr(intent, "reason", "")[:100])

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

                # ── Sync stop-loss to Demo (prevent ghost positions) ──
                # 止損同步到 Demo（防止幽靈倉位）
                if self._demo_connector and self._demo_connector.is_enabled:
                    try:
                        _demo_stop_qty = stop["qty"]
                        if _demo_stop_qty >= 1.0:
                            _demo_stop_qty = round(_demo_stop_qty)
                        else:
                            _demo_stop_qty = round(_demo_stop_qty, 3)
                        if _demo_stop_qty > 0:
                            demo_stop_result = self._demo_connector.submit_order(
                                symbol=stop["symbol"],
                                side=stop["side"],
                                order_type="Market",
                                qty=_demo_stop_qty,
                                reduce_only=True,
                            )
                            if demo_stop_result.get("retCode") == 0:
                                logger.info(
                                    "Demo stop-loss synced: %s %s qty=%.6f / Demo 止損已同步",
                                    stop["symbol"], stop["side"], _demo_stop_qty,
                                )
                            else:
                                logger.warning(
                                    "Demo stop-loss FAILED: %s reason=%s / Demo 止損失敗",
                                    stop["symbol"], demo_stop_result.get("retMsg"),
                                )
                    except Exception as _demo_stop_err:
                        logger.warning(
                            "Demo stop-loss error: %s %s (non-fatal) / Demo 止損異常",
                            stop["symbol"], _demo_stop_err,
                        )

                if self._telegram:
                    self._telegram.alert_stop(stop["symbol"], stop["stop_type"], stop["reason"])

                # ── FA-7 / Sprint 1a P1-1: Inject into Perception Plane via _emit_round_trip ──
                # Principle 12 (Continuous Evolution): every closed position — including
                # stop-loss exits — must reach the learning pipeline so the system can
                # learn from losses and improve strategy selection over time.
                # 原則 12（持續進化）：每個被止損平倉的倉位都必須進入學習管線，
                # 系統才能從虧損中學習並持續改進策略選擇。
                #
                # P1-1 Guard: only emit round_trip if the stop order was actually executed
                # (not rejected). A rejected order means no position was closed — emitting
                # a round_trip would inject a fabricated learning signal and corrupt the
                # learning pipeline with ghost trades.
                # P1-1 守衛：只有止損單真正成交才注入學習信號；若訂單被拒（rejected_reason
                # 存在），跳過 _emit_round_trip()，避免向學習管線注入虛假數據（幽靈交易）。
                #
                # _emit_round_trip() handles:
                #   1. _open_positions pop (position metadata cleanup)
                #   2. E1 observation_writer callback
                #   3. G1 auto_deployer.on_trade_result (consecutive-loss tracking)
                #   4. L1.01 trade attribution
                #   5. EX-05 learning tier auto-promotion check
                #   6. MessageBus ROUND_TRIP_COMPLETE → AnalystAgent
                #   7. PerceptionPlane.register_data() — feeds Layer 2 AI reasoning
                # _emit_round_trip() 一次性觸發 7 個學習/歸因回調，統一複用意圖路徑的邏輯。
                #
                # Safety fallback: if result is not a dict (e.g. None), isinstance() returns
                # False → _stop_order_rejected = False → we still attempt to emit.
                # This is the safe default: a non-dict result means we cannot confirm
                # rejection, so we treat it as executed to avoid dropping valid learning data.
                # 安全 fallback：若 result 非 dict（例如 None），無法確認拒絕，
                # 預設為已成交（不丟棄潛在有效學習數據）。
                _stop_order_rejected = isinstance(result, dict) and bool(
                    result.get("rejected_reason")
                )
                if not _stop_order_rejected:
                    # Only emit round_trip when the stop order was actually executed.
                    # 只有止損單真正成交時才注入學習信號。
                    try:
                        _stop_symbol = stop["symbol"]
                        _stop_strategy = stop.get("strategy_name", "unknown")
                        # exit_price: use current_price from StopManager (exact trigger price);
                        # fall back to latest_prices snapshot if field is missing.
                        # 出場價格：優先用 StopManager 記錄的觸發價，否則取最新行情快照。
                        _exit_price = float(
                            stop.get("current_price")
                            or market_prices.get(_stop_symbol, 0.0)
                        )
                        _entry_price = float(stop.get("entry_price", 0.0))
                        _qty = float(stop.get("qty", 0.0))
                        # stop["side"] is the CLOSE-side order direction:
                        #   "Sell" means the original position was long → pnl = (exit - entry) * qty
                        #   "Buy"  means the original position was short → pnl = (entry - exit) * qty
                        # stop["side"] 是平倉方向：Sell=多頭平倉（虧則為負），Buy=空頭平倉。
                        if stop["side"] == "Sell":
                            _close_pnl = (_exit_price - _entry_price) * _qty
                        else:
                            _close_pnl = (_entry_price - _exit_price) * _qty
                        # U-05: Extract close fee from stop order fill for round-trip cost.
                        # U-05：从止损单成交记录提取平仓费用。
                        _stop_close_fee = 0.0
                        if isinstance(result, dict):
                            _stop_fills = result.get("fills", [])
                            if _stop_fills:
                                _stop_close_fee = float(_stop_fills[0].get("fee", 0.0))
                        self._emit_round_trip(
                            symbol=_stop_symbol,
                            strategy_name=_stop_strategy,
                            exit_price=_exit_price,
                            close_pnl=_close_pnl,
                            close_fee=_stop_close_fee,
                        )
                    except Exception as _rt_err:
                        # Non-fatal: do not let learning pipeline injection block stop processing.
                        # 非致命：不允許學習管線注入阻擋止損單的正常流程。
                        logger.warning(
                            "Stop-loss round-trip emit error (non-fatal): %s %s / 止損 round-trip 觸發失敗",
                            stop.get("symbol"), _rt_err,
                        )

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

    def _try_l2_cron_trigger(self, now_ts: float) -> None:
        """
        Weekly schedule:
          Wednesday UTC 0:00 — brief report via 27B Ollama (AnalystAgent.analyze_patterns)
          Sunday    UTC 0:00 — detailed report via Claude L2 (Layer2Engine.run_session)
        每周计划：
          周三 UTC 0:00 — 简报（27B Ollama，AnalystAgent 模式发现）
          周日 UTC 0:00 — 详报（Claude L2 完整推理 session）
        """
        import asyncio
        import datetime
        try:
            utc_now = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
            weekday = utc_now.weekday()  # 2=Wednesday, 6=Sunday
            week_key = utc_now.strftime("%Y-W%W")

            # ── Wednesday UTC 0:xx : brief report (27B Ollama) ──────────────
            if weekday == 2 and utc_now.hour == 0:
                brief_key = "brief_" + week_key
                if getattr(self, "_last_l2_brief_week", None) != brief_key:
                    self._last_l2_brief_week = brief_key
                    logger.info("L2 Cron: Wednesday brief report triggered (27B Ollama) / 周三简报触发")
                    insight = self._analyst_agent.analyze_patterns(force=True)
                    if insight:
                        logger.info(
                            "Wednesday brief: %d winning, %d losing patterns / 周三简报: %d 获胜模式, %d 亏损模式",
                            len(insight.winning_patterns), len(insight.losing_patterns),
                            len(insight.winning_patterns), len(insight.losing_patterns),
                        )

            # ── Sunday UTC 0:xx : detailed report (Claude L2 session) ────────
            elif weekday == 6 and utc_now.hour == 0:
                detail_key = "detail_" + week_key
                if getattr(self, "_last_l2_detail_week", None) != detail_key:
                    self._last_l2_detail_week = detail_key
                    logger.info("L2 Cron: Sunday detailed report triggered (Claude L2) / 周日详报触发")
                    try:
                        from .layer2_routes import _get_engine
                        engine = _get_engine()
                        if not engine.is_running:
                            coro = engine.run_session(
                                trigger="weekly_cron_sunday",
                                symbol="BTCUSDT",
                                context="Weekly scheduled deep analysis. Analyze all accumulated patterns, regime transitions, and strategy performance. Generate actionable insights.",
                            )
                            asyncio.ensure_future(coro)
                            logger.info("Sunday detailed L2 session scheduled / 周日详报 L2 session 已调度")
                        else:
                            logger.info("Sunday L2 skipped: another session already running / 周日详报跳过：另一 session 运行中")
                    except Exception as _e:
                        logger.warning("Sunday L2 session schedule failed (non-fatal): %s / 周日详报调度失败（非致命）: %s", _e, _e)

        except Exception:
            logger.exception("L2 Cron trigger error (non-fatal) / L2 Cron 触发异常（非致命）")

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
            except Exception as e:
                # Non-fatal: regime is optional AI context enrichment; log for observability
                # 非致命：regime 是可选 AI 上下文富化字段；记录日志以备观测
                logger.debug("Regime fetch failed for %s (non-fatal, skipping enrichment): %s", symbol, e)

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
            except Exception as e:
                # Non-fatal: indicators are optional AI context enrichment; log for observability
                # 非致命：指标是可选 AI 上下文富化字段；记录日志以备观测
                logger.debug("Indicators fetch failed for %s (non-fatal, skipping enrichment): %s", symbol, e)

            context = (
                f"Symbol: {symbol}\n"
                f"Signal: {side} (strategy: {strategy}, confidence: {confidence})\n"
                f"Current price: {price:.4f}\n"
                f"Fee drag: ~0.11% round-trip (taker both sides)"
                f"{regime_info}"
                f"{indicator_info}"
            )

            resp = self._ollama_client.judge_edge(context, timeout=15)

            if not resp.success:
                logger.warning(
                    "Edge filter: Qwen error (%s), passing through / Qwen 出错，放行: %s",
                    resp.error, symbol,
                )
                with self._lock:
                    self._edge_filter_stats["errors"] += 1
                return True  # fail-open

            # Parse response / 解析响应
            # E5 NEW-S4: Use module-level _json_mod alias (consistency fix)
            # E5 NEW-S4：使用模塊級 _json_mod 別名（一致性修復）
            try:
                result = _json_mod.loads(resp.text)
                has_edge = result.get("has_edge", True)  # default: allow
                edge_confidence = result.get("confidence", 0.5)
                edge_reason = result.get("reason", "")
            except (_json_mod.JSONDecodeError, AttributeError):
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

    def _on_position_open(
        self, intent: Any, fill_price: float, actual_qty: float = 0.0,
        demo_fill_price: float = 0.0,
    ) -> None:
        """
        Called when a new position is opened.
        Record it in _open_positions and register with StopManager using ATR-based stop.
        新持仓开仓时调用。记录到 _open_positions 并用 ATR 动态止损注册到 StopManager。

        actual_qty: The rounded qty actually submitted (for Demo consistency).
                    If 0, falls back to intent.qty.
        demo_fill_price: Demo 的真實成交價，用於計算交易所端條件止損單的觸發價。
                         若為 0 則回退到 Paper fill_price（向後兼容）。
                         Demo's actual fill price for exchange conditional stop-loss trigger.
                         Falls back to Paper fill_price if 0 (backward compatible).
        """
        symbol = intent.symbol
        strategy_name = getattr(intent, "strategy_name", "unknown")
        side = "long" if intent.side == "Buy" else "short"
        qty = actual_qty if actual_qty > 0 else intent.qty
        regime = (intent.metadata or {}).get("_regime", "unknown") if intent.metadata else "unknown"
        key = f"{strategy_name}:{symbol}"

        # U-05: Capture entry fee from the fill record for accurate round-trip cost accounting.
        # U-05：从成交记录中获取开仓费用，用于精确的 round-trip 成本核算。
        _entry_fee = 0.0
        if self._engine:
            try:
                _state = self._engine.get_state()
                _fills = _state.get("fills", [])
                # Find the most recent fill for this symbol (entry fill).
                # 查找该 symbol 最近一次成交（开仓成交）。
                for _f in reversed(_fills):
                    if _f.get("symbol") == symbol:
                        _entry_fee = float(_f.get("fee", 0.0))
                        break
            except Exception:
                pass  # fail-open: missing fee won't block trading / 缺失费用不阻塞交易

        # U-05: Capture confidence from intent for param_snapshot.
        # U-05：从 intent 获取置信度用于参数快照。
        _confidence = getattr(intent, "confidence", 0.0) or 0.0
        _strategy = getattr(intent, "strategy_name", strategy_name) or strategy_name

        with self._lock:
            self._open_positions[key] = {
                "symbol": symbol,
                "strategy_name": strategy_name,
                "side": side,
                "entry_price": fill_price,
                "qty": qty,
                "entry_ts_ms": now_ms(),
                "regime": regime,
                # U-05: Entry fee for round-trip cost accounting (Principle 8 auditability).
                # U-05：开仓费用，用于 round-trip 成本审计（原则 8 可审计性）。
                "entry_fee": _entry_fee,
                # U-05: Signal confidence at entry time.
                # U-05：开仓时的信号置信度。
                "confidence": _confidence,
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

        # U-09: ATR dual-window stop — use max(ATR_fast, ATR_slow) for conservative estimate
        # U-09：ATR 双窗口止损 — 取 max(快窗口, 慢窗口) 作为保守估计
        # Fast window (5-period) reacts quicker to regime changes; slow (14) is stable.
        # 快窗口（5 期）对 regime 切换反应更快；慢窗口（14 期）更稳定。取大值更保守。
        atr_stop_pct = 5.0  # default hard stop / 默认硬止损
        if self._ie and fill_price > 0:
            try:
                atr_data = self._ie.get_conservative_atr(symbol, "1h")
                atr_raw = atr_data.get("atr_conservative")
                if atr_raw and atr_raw > 0:
                    atr_stop_pct = min(15.0, max(2.0, (atr_raw * 2.0 / fill_price) * 100))
            except Exception as e:
                # Log but allow fallback to default 5.0% stop (fail-closed)
                logger.error("Failed to compute ATR stop percentage for %s: %s; using default 5.0%%", symbol, e)

        # H1: register with StopManager using ATR-based dynamic stop + regime-adjusted time stop
        # H1：使用 ATR 动态止损 + 市场状态调整时间止损注册到 StopManager
        if self._stop_mgr:
            try:
                from local_model_tools.stop_manager import StopConfig
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

        # U-05: Snapshot dynamic parameters at entry time for round-trip auditing (Principle 8).
        # U-05：开仓时快照动态参数，用于 round-trip 审计回溯（原则 8 可审计性）。
        # These values are stored in _open_positions and written to round-trip records at close.
        # 这些值存储在 _open_positions 中，平仓时写入 round-trip 记录。
        _atr_pct = (atr_stop_pct / 2.0) if fill_price > 0 else 0.0  # ATR/price approx
        _trail_activation_pct = atr_stop_pct * 0.5  # trailing activates at 50% of stop distance
        _c_round_pct = 0.0
        if fill_price > 0 and qty > 0:
            # Estimate round-trip cost as 2x entry fee / notional
            # 估算 round-trip 成本 = 2 倍开仓费 / 名义金额
            _notional = fill_price * qty
            _c_round_pct = (2 * _entry_fee / _notional * 100) if _notional > 0 else 0.0

        with self._lock:
            if key in self._open_positions:
                self._open_positions[key]["param_snapshot"] = {
                    "atr_pct": round(_atr_pct, 4),
                    "stop_distance_pct": round(atr_stop_pct, 4),
                    "trail_activation_pct": round(_trail_activation_pct, 4),
                    "trail_distance_pct": round(trailing_pct if self._stop_mgr else 5.0, 4),
                    "c_round_pct": round(_c_round_pct, 6),
                    "regime": regime,
                    "strategy_name": strategy_name,
                    "confidence": round(_confidence, 4),
                }

        # ── Batch 11: Exchange conditional stop-loss (DOC-01 §5.9 dual defense) ──
        # Batch 11：交易所条件止损单（DOC-01 §5.9 双重防线）
        # fail-closed: if conditional order creation fails, log but do NOT block local stop-loss
        # 失败安全：条件单创建失败仅记录日志，不阻止本地止损
        if self._demo_connector and self._demo_connector.is_enabled and fill_price > 0:
            try:
                from .bybit_demo_connector import round_price_for_exchange
                # Close side is opposite of position side
                # 平仓方向与持仓方向相反
                close_side = "Sell" if side == "long" else "Buy"

                # ★ FIX: 使用 Demo 真實成交價計算止損觸發價（而非 Paper 模擬價）
                # Demo entry price may differ from Paper due to real orderbook vs simulated slippage.
                # Using Paper price caused PIPPINUSDT to round(0.056859, 2) = 0.06 ≈ market price,
                # triggering false stop loss within 19 seconds.
                # ★ FIX: Use Demo actual fill price for stop trigger (not Paper simulated price).
                _stop_base_price = demo_fill_price if demo_fill_price > 0 else fill_price

                _hard_stop_pct = atr_stop_pct
                if side == "long":
                    raw_trigger = _stop_base_price * (1 - _hard_stop_pct / 100)
                else:
                    raw_trigger = _stop_base_price * (1 + _hard_stop_pct / 100)

                # ★ FIX: 用交易所 tickSize 取整，而非硬編碼 round(..., 2)
                # round(..., 2) 對低價幣（$0.06）會把 0.056859 進位到 0.06 = 市價
                # ★ FIX: Round using exchange tick_size, not hardcoded round(..., 2).
                # round(..., 2) on low-price coins ($0.06) rounds 0.056859 UP to 0.06 = market price.
                tick_size = None
                if self._symbol_registry:
                    try:
                        tick_size = self._symbol_registry.get_tick_size(symbol)
                    except Exception:
                        pass  # fallback to 8dp
                trigger_price = round_price_for_exchange(raw_trigger, tick_size)

                cond_result = self._demo_connector.place_conditional_order(
                    symbol=symbol,
                    side=close_side,
                    qty=qty,
                    trigger_price=trigger_price,
                )
                if cond_result.get("retCode") == 0:
                    logger.info(
                        "Dual defense: exchange stop-loss created %s %s trigger=%s "
                        "(base_price=%s tick_size=%s) / "
                        "双重防线：交易所止损单已创建",
                        symbol, close_side, trigger_price,
                        _stop_base_price, tick_size,
                    )
                else:
                    logger.warning(
                        "Dual defense: exchange stop-loss FAILED %s reason=%s (local stop still active) / "
                        "双重防线：交易所止损单创建失败（本地止损仍然有效）",
                        symbol, cond_result.get("retMsg"),
                    )

                # 0B-2: Place TP (take-profit) conditional order alongside SL.
                # 0B-2：在 SL 旁邊同時掛 TP（止盈）條件單。
                # TP at 2× the SL distance (risk:reward ~1:2). Fail-open: TP failure doesn't block.
                # TP 距離 = 2× SL 距離（風險回報比 ~1:2）。TP 失敗不阻擋。
                try:
                    _tp_mult = 2.0  # TP = 2× SL distance for 1:2 R:R
                    if side == "long":
                        tp_raw = _stop_base_price * (1 + _hard_stop_pct * _tp_mult / 100)
                        tp_dir = 1  # Sell TP triggers on price rise
                    else:
                        tp_raw = _stop_base_price * (1 - _hard_stop_pct * _tp_mult / 100)
                        tp_dir = 2  # Buy TP triggers on price fall
                    tp_price = round_price_for_exchange(tp_raw, tick_size)
                    tp_result = self._demo_connector.place_conditional_order(
                        symbol=symbol,
                        side=close_side,
                        qty=qty,
                        trigger_price=tp_price,
                        trigger_direction=tp_dir,
                    )
                    if tp_result.get("retCode") == 0:
                        logger.info(
                            "0B-2: TP order created %s %s trigger=%s / 止盈單已創建",
                            symbol, close_side, tp_price,
                        )
                except Exception as _tp_err:
                    logger.debug("0B-2: TP order failed (SL still active): %s", _tp_err)

            except Exception as _cond_err:
                logger.warning(
                    "Dual defense: conditional order error %s: %s (local stop still active) / "
                    "双重防线：条件单创建异常（本地止损仍然有效）",
                    symbol, _cond_err,
                )

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

    def _emit_round_trip(
        self, symbol: str, strategy_name: str, exit_price: float, close_pnl: float,
        *, close_fee: float = 0.0,
    ) -> None:
        """
        Core round-trip completion handler — shared by intent-path and tick-path closes.
        Pops _open_positions, fires G1 + E1 callbacks, unregisters from StopManager.

        U-05: Now includes real fees_paid (entry_fee + close_fee) and param_snapshot in
        round-trip records for accurate cost attribution and parameter auditing (Principle 8).

        核心 round-trip 完成处理器 — 被意图路径和 tick 路径共用。
        弹出 _open_positions，触发 G1 + E1 回调，从 StopManager 取消注册。

        U-05：现在在 round-trip 记录中包含真实费用（开仓费 + 平仓费）和参数快照，
        用于精确的成本归因和参数审计（原则 8 可审计性）。
        """
        key = f"{strategy_name}:{symbol}"

        with self._lock:
            pos_info = self._open_positions.pop(key, None)

        hold_ms = 0
        regime = "unknown"
        entry_ts_ms = now_ms()
        entry_price = 0.0
        qty = 0.0
        entry_fee = 0.0
        param_snapshot: dict = {}

        if pos_info:
            hold_ms = now_ms() - pos_info.get("entry_ts_ms", now_ms())
            regime = pos_info.get("regime", "unknown")
            entry_ts_ms = pos_info.get("entry_ts_ms", now_ms())
            entry_price = pos_info.get("entry_price", 0.0)
            qty = pos_info.get("qty", 0.0)
            # U-05: Extract entry fee and param_snapshot stored at open time.
            # U-05：提取开仓时保存的入场费用和参数快照。
            entry_fee = pos_info.get("entry_fee", 0.0)
            param_snapshot = pos_info.get("param_snapshot", {})

        # U-05: Compute real round-trip fees = entry_fee + close_fee.
        # U-05：计算真实 round-trip 费用 = 开仓费 + 平仓费。
        fees_paid = entry_fee + close_fee

        # U-05: Compute slippage if entry_price is available.
        # Slippage = |exit_price - entry_price| normalized by entry_price.
        # For stop-loss exits this represents the actual price deviation.
        # U-05：如果有入场价格，计算滑点 = |出场价 - 入场价| / 入场价。
        slippage = 0.0
        slippage_estimated = True
        if entry_price > 0 and exit_price > 0:
            slippage = abs(exit_price - entry_price) / entry_price
            slippage_estimated = False

        # Untrack from StopManager (position is closed) / 从 StopManager 取消追踪
        if self._stop_mgr:
            try:
                self._stop_mgr.untrack_position(symbol, strategy_name)
            except Exception as e:
                # Critical path: position untracking should not silently fail
                logger.error("Failed to untrack position %s from StopManager: %s", symbol, e)

        # G1: notify auto-deployer for consecutive loss tracking
        # G1：通知自动部署器进行连续亏损追踪
        if self._auto_deployer:
            try:
                self._auto_deployer.on_trade_result(strategy_name, close_pnl)
            except Exception as e:
                # Log at warning: consecutive-loss tracking failure means auto-deployer
                # may not pause the strategy on drawdown — worth surfacing
                # 使用 warning 级别：连续亏损追踪失败意味着自动部署器可能无法在回撤时暂停策略
                logger.warning("Auto-deployer on_trade_result error for %s (consecutive-loss tracking may be stale): %s", strategy_name, e)

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

                exit_ts_ms = now_ms()
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
                    fees_paid=fees_paid,        # U-05: Real fees (entry + close)
                    slippage=slippage,          # U-05: Real price slippage
                    ai_cost=0.0,               # Could be enhanced with model costs
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
                        "timestamp_ms": now_ms(),
                        # U-05: Real fees and parameter snapshot for auditing (Principle 8).
                        # U-05：真实费用和参数快照用于审计（原则 8）。
                        "fees_paid": fees_paid,
                        "param_snapshot": param_snapshot,
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
            "Round-trip complete: %s %s pnl=%.4f fees=%.6f hold=%.1fh regime=%s / 交易完成",
            strategy_name, symbol, close_pnl, fees_paid, hold_ms / 3600000, regime,
        )

    def _on_round_trip_complete(
        self, intent: Any, exit_price: float, close_pnl: float,
        *, close_fee: float = 0.0,
    ) -> None:
        """
        Called when a position is closed via immediate market-order fill in submit_order().
        Delegates to _emit_round_trip.
        U-05: Now passes close_fee for accurate round-trip cost accounting.
        通过 submit_order() 即时成交路径平仓时调用，委托给 _emit_round_trip。
        U-05：现在传递平仓费用用于精确的 round-trip 成本核算。
        """
        symbol = intent.symbol
        strategy_name = getattr(intent, "strategy_name", "unknown")
        self._emit_round_trip(symbol, strategy_name, exit_price, close_pnl, close_fee=close_fee)

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
                # U-05: Pass close_fee for accurate round-trip cost accounting.
                # U-05：传递平仓费用用于精确的 round-trip 成本核算。
                self._emit_round_trip(symbol, strategy_name, fill_price, close_pnl, close_fee=close_fee)
                already_emitted.add(key)
                break  # one emit per tracked position per tick

    @staticmethod
    def _infer_category_from_symbol(symbol: str) -> str:
        """Infer Bybit V5 category from symbol naming convention.
        根據 Bybit V5 symbol 命名規則推斷品類。

        Rules (Bybit naming convention):
          - Ends with "USD" but not "USDT" or "USDC" → "inverse"  (e.g. BTCUSD, ETHUSD)
          - Contains "-" (option format, e.g. BTC-1JAN25-50000-C) → "option"
          - "USDT" / "USDC" perpetuals or spot share the same suffix; we default to "linear"
            because spot symbols are also tracked in market_scanner with category metadata.
            Callers that know the true category should pass it explicitly.
          - Fallback → "linear"

        規則（Bybit 命名慣例）：
          - 以 "USD" 結尾但不以 "USDT"/"USDC" 結尾 → inverse（如 BTCUSD、ETHUSD）
          - 包含 "-" → option（如 BTC-1JAN25-50000-C）
          - 其餘情況默認 linear；真正的 spot symbol 需呼叫端明確指定 category
        """
        sym = symbol.upper()
        if "-" in sym:
            return "option"
        if sym.endswith("USD") and not sym.endswith("USDT") and not sym.endswith("USDC"):
            return "inverse"
        # fallback：命名規則無法區分 linear 與 spot，可能推斷錯誤。
        # Fallback: naming convention cannot distinguish linear from spot; may be incorrect.
        # 呼叫端應通過 register_symbol_category() 或 SymbolCategoryRegistry 提供正確 category。
        # Callers should provide correct category via register_symbol_category() or SymbolCategoryRegistry.
        logger.warning(
            "Category inferred as linear for symbol=%s — may be incorrect for spot symbols. "
            "Register via StrategyAutoDeployer or SymbolCategoryRegistry to fix. "
            "/ symbol=%s 的 category 被推斷為 linear，對 spot symbol 可能錯誤",
            symbol, symbol,
        )
        return "linear"

    def _refresh_kline_volume(self) -> None:
        """
        Periodically fetch latest kline from REST API to get real volume data.
        定期从 REST API 获取最新 K线以获取真实成交量。

        Dynamically covers all tracked symbols, not just BTC/ETH.
        动态覆盖所有已追踪的交易对，不仅限于 BTC/ETH。

        SPOT-4: Category is now inferred per-symbol so Spot symbols query the correct
        endpoint. Bybit v5 /market/kline requires the correct category to return data.
        SPOT-4：現在為每個 symbol 推斷正確的 category，避免 spot symbol 查到錯誤端點。
        """
        import urllib.request
        # E5 NEW-S4: Use module-level _json_mod instead of local re-import
        # E5 NEW-S4：使用模塊級 _json_mod 而非局部重新導入

        tf_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}

        # Use all actively tracked symbols / 使用所有活跃追踪的交易对
        tracked = self._km.get_tracked_symbols() if hasattr(self._km, "get_tracked_symbols") else []
        if not tracked:
            tracked = list(self._latest_prices.keys())
        # Cap to 10 symbols per refresh to avoid rate limits / 限制每次最多 10 个以避免频率限制
        symbols = tracked[:10]

        for symbol in symbols:
            # Wave 7a 方案 B：優先從運行時映射查詢，fallback 到名稱推斷（可能不準確）。
            # Wave 7a Plan B: prefer runtime map; fallback to name inference (may be inaccurate
            # for spot symbols that share the same suffix as linear, e.g. BTCUSDT).
            kline_category = self._symbol_category_map.get(symbol) or self._infer_category_from_symbol(symbol)

            for tf, interval in tf_map.items():
                try:
                    url = (
                        f"https://api.bybit.com/v5/market/kline"
                        f"?category={kline_category}&symbol={symbol}&interval={interval}&limit=2"
                    )
                    req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = _json_mod.loads(resp.read().decode())

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

    def _fetch_single_funding_rate(self, symbol: str, category: str | None = None) -> tuple[float, int] | None:
        """Fetch funding rate for a single symbol from Bybit API.
        为单个品种从 Bybit API 获取 funding rate。

        Returns:
            (funding_rate, next_settle_ts_ms) or None if unavailable.
            返回 (funding_rate, next_settle_ts_ms)，不可用时返回 None。

        SPOT-4: Spot and option symbols have no funding rate — return None immediately.
        SPOT-4：現貨（spot）和期權（option）沒有資金費率，立即返回 None。
        """
        import urllib.request
        # E5 NEW-S4: Use module-level _json_mod instead of local re-import
        # E5 NEW-S4：使用模塊級 _json_mod 而非局部重新導入

        # SPOT-4: Funding rate only applies to perpetual contracts (linear / inverse).
        # Spot and option have no funding mechanism — skip API call entirely to avoid
        # spurious HTTP errors and unnecessary load on Bybit rate limits.
        # SPOT-4：資金費率只適用於永續合約（linear/inverse）。
        # Spot/option 沒有 funding 機制，直接跳過 API 調用，避免無效請求。
        # Wave 7a 方案 B：優先用呼叫端傳入的 category，其次查運行時映射，最後才用名稱推斷。
        # Wave 7a Plan B: explicit category arg > runtime map > name inference.
        resolved_category = category or self._symbol_category_map.get(symbol) or self._infer_category_from_symbol(symbol)
        if resolved_category in ("spot", "option"):
            logger.debug(
                "Skipping funding rate fetch for %s (category=%s, no funding rate) "
                "/ 跳過資金費率查詢：%s 品類無資金費率",
                symbol, resolved_category, symbol,
            )
            return None

        try:
            url = f"https://api.bybit.com/v5/market/tickers?category={resolved_category}&symbol={symbol}"
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json_mod.loads(resp.read().decode())

            if data.get("retCode") != 0:
                return None

            ticker_list = data.get("result", {}).get("list", [])
            if not ticker_list:
                return None

            ticker = ticker_list[0]
            funding_rate = float(ticker.get("fundingRate", 0))
            next_funding_ts = int(ticker.get("nextFundingTime", 0))

            if funding_rate == 0 or next_funding_ts == 0:
                return None

            return funding_rate, next_funding_ts
        except Exception:
            logger.debug("Funding rate fetch failed for %s / 获取失败: %s", symbol, symbol)
            return None

    def _check_funding_rates(self) -> None:
        """Fetch funding rate for each deployed FundingRate strategy's own symbol.
        为每个已部署的 FundingRate 策略获取其自身品种的 funding rate。

        Fix P0-A2: previously only fetched BTCUSDT/ETHUSDT and fed all strategies with
        wrong data. Now each strategy receives the rate for its own symbol.
        修复 P0-A2：此前只获取 BTCUSDT/ETHUSDT 并将错误数据喂给所有策略。
        现在每个策略接收其自身品种的 funding rate。
        """
        for strategy in self._orch._strategies.values():
            if not hasattr(strategy, "evaluate_funding_opportunity"):
                continue

            symbol = getattr(strategy, "_symbol", None) or getattr(strategy, "symbol", None)
            if not symbol:
                continue

            result = self._fetch_single_funding_rate(symbol)
            if result is None:
                continue

            funding_rate, next_funding_ts = result

            # B5: Pass spot/perp prices for basis risk calculation
            # B5：传递现货/永续价格供基差风险计算
            # Latest tick price serves as perp_price; spot is approximated as same
            # (until dedicated spot price feed is available).
            # 最新 tick 价格作为永续价格；现货近似为相同值
            # （在有专用现货价格源之前）。
            _latest_price = self._latest_prices.get(symbol)
            try:
                strategy.evaluate_funding_opportunity(
                    funding_rate=funding_rate,
                    next_settle_ts_ms=next_funding_ts,
                    spot_price=_latest_price,
                    perp_price=_latest_price,
                )
            except Exception:
                logger.exception("Funding rate eval error for %s / funding rate 评估异常: %s", symbol, symbol)

    def get_stats(self) -> dict[str, Any]:
        """Get bridge statistics / 获取桥接器统计"""
        with self._lock:
            return {
                "component": "pipeline_bridge",
                "active": self._active,
                **dict(self._stats),
            }
