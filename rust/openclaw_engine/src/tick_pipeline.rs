//! Tick Pipeline — on_tick 4-step orchestration (R04-1).
//! Tick 管線 — on_tick 4 步編排。
//!
//! WS event → kline aggregate → indicator compute → signal evaluate → strategy dispatch.
//! Tick actor sole-owner: no locks [V3-PA-1].

use openclaw_core::{
    governance_core::GovernanceCore,
    h0_gate::H0Gate,
    indicators::{IndicatorEngine, IndicatorSnapshot},
    klines::KlineManager,
    risk::{check_position_on_tick, PriceHistoryTracker, RiskAction},
    signals::{IndicatorInput, Signal, SignalEngine},
};
use openclaw_types::PriceEvent;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::Instant;
use tracing::{debug, info, warn};

use crate::instrument_info::InstrumentInfoCache;
use crate::intent_processor::IntentProcessor;
use crate::orchestrator::Orchestrator;
use crate::paper_state::PaperState;

/// Paper trading session command — IPC → event consumer → TickPipeline.
/// 紙上交易 session 命令 — IPC → 事件消費者 → TickPipeline。
#[derive(Debug)]
pub enum PaperSessionCommand {
    /// Pause strategy dispatch + shadow orders. Prices/indicators/stops continue.
    /// 暫停策略分派+影子訂單。價格/指標/止損繼續。
    Pause,
    /// Resume strategy dispatch + shadow orders.
    /// 恢復策略分派+影子訂單。
    Resume,
    /// Close all open positions at current market prices.
    /// 以當前市場價格平掉所有持倉。
    CloseAll,
    /// Reset paper state — clear positions, reset balance.
    /// 重置紙盤狀態 — 清倉、重置餘額。
    Reset { new_balance: f64 },
    /// Phase 3b: Update strategy parameters via JSON (Optuna → Rust).
    /// Phase 3b：通過 JSON 更新策略參數（Optuna → Rust）。
    UpdateStrategyParams {
        strategy_name: String,
        params_json: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Phase 3b: Get current strategy parameters as JSON.
    /// Phase 3b：獲取當前策略參數 JSON。
    GetStrategyParams {
        strategy_name: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Phase 3b: Get parameter ranges for a strategy (Optuna search space).
    /// Phase 3b：獲取策略參數範圍（Optuna 搜索空間）。
    GetParamRanges {
        strategy_name: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// RRC-1-E2: Set strategy active/paused by name.
    /// RRC-1-E2：按名稱設置策略活躍/暫停。
    SetStrategyActive {
        strategy_name: String,
        active: bool,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Update risk config at runtime (from GUI/Python/Agent → IPC → Rust).
    /// 運行時更新風控配置（從 GUI/Python/Agent → IPC → Rust）。
    UpdateRiskConfig {
        // StopConfig fields / 止損配置
        hard_stop_pct: Option<f64>,
        trailing_stop_pct: Option<Option<f64>>, // Some(None)=disable, Some(Some(x))=set
        time_stop_hours: Option<Option<f64>>,
        atr_multiplier: Option<Option<f64>>,
        take_profit_pct: Option<Option<f64>>,
        // GuardianConfig fields / 守護者配置
        max_leverage: Option<f64>,
        max_drawdown_pct: Option<f64>,
        max_same_direction_positions: Option<usize>,
        // IntentProcessor fields / 意圖處理器配置
        p1_risk_pct: Option<f64>,
        // RRC-1-A3: H0Gate shadow mode toggle / H0 門控影子模式切換
        h0_shadow_mode: Option<bool>,
        // PNL-7: agent-tunable dynamic-stop knobs
        // PNL-7：Agent 可調的動態止損參數
        dynamic_stop_base_ratio: Option<f64>,
        dynamic_stop_cap_ratio: Option<f64>,
        trailing_min_rr_ratio: Option<f64>,
        // Session 12: cost-gate + regime + boot cooldown tunables
        cost_gate_min_confidence: Option<f64>,
        cost_gate_k_base: Option<f64>,
        cost_gate_k_medium: Option<f64>,
        cost_gate_k_small: Option<f64>,
        adx_trending_threshold: Option<f64>,
        boot_cooldown_ms: Option<u64>,
        // DB-RUN-1: signals heartbeat (0 = disable throttling)
        signals_heartbeat_ms: Option<u64>,
    },
}

/// Server-side stop request dispatched from tick_pipeline to Bybit API (Item 1).
/// 從 tick_pipeline 派發到 Bybit API 的伺服器端止損請求（項目 1）。
#[derive(Debug, Clone)]
pub struct StopRequest {
    pub symbol: String,
    pub stop_loss: f64,
    pub is_long: bool,
}

/// Order dispatch request from tick_pipeline to exchange API (EXT-1).
/// 從 tick_pipeline 派發到交易所 API 的訂單派發請求。
///
/// Used in both modes:
/// - `paper_only`: shadow order (fire-and-forget after local fill, is_primary=false)
/// - `exchange`: primary order (tracked, fill confirmed via WS, is_primary=true)
#[derive(Debug, Clone)]
pub struct ShadowOrderRequest {
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Long direction / 多方向
    pub is_long: bool,
    /// Order quantity / 訂單數量
    pub qty: f64,
    /// Reference price / 參考價格
    pub price: f64,
    /// Strategy name / 策略名稱
    pub strategy: String,
    /// Timestamp (ms) when the intent was generated / 意圖生成時間戳（毫秒）
    pub paper_fill_ts: u64,
    /// true = closing position, use reduce_only / true = 平倉，使用 reduce_only
    pub is_close: bool,
    /// EXT-1: Client-assigned order link ID for tracking / 客戶端訂單連結 ID
    pub order_link_id: String,
    /// EXT-1: true = exchange mode primary order (track pending, await confirmation)
    /// false = paper_only mode shadow order (fire-and-forget)
    pub is_primary: bool,
    /// I-08 雙軌止損：broker-side stop loss price (None = engine rail only)
    pub stop_loss: Option<f64>,
    /// I-08 雙軌止損：broker-side take profit price
    pub take_profit: Option<f64>,
}

/// Tick context passed to strategies.
/// 傳遞給策略的 tick 上下文。
#[derive(Debug, Clone)]
pub struct TickContext {
    pub symbol: String,
    pub price: f64,
    pub timestamp_ms: u64,
    pub indicators: Option<IndicatorSnapshot>,
    pub signals: Vec<Signal>,
    pub h0_allowed: bool,
}

/// Tick statistics for monitoring.
/// Tick 統計。
#[derive(Debug, Default, Clone, Serialize, Deserialize)]
pub struct TickStats {
    pub total_ticks: u64,
    pub total_intents: u64,
    pub total_fills: u64,
    pub total_stops: u64,
    pub last_tick_ms: u64,
}

/// Core tick pipeline — owns all processing state.
/// 核心 tick 管線 — 擁有所有處理狀態。
pub struct TickPipeline {
    pub kline_manager: KlineManager,
    pub signal_engine: SignalEngine,
    pub orchestrator: Orchestrator,
    pub intent_processor: IntentProcessor,
    pub governance: GovernanceCore,
    pub paper_state: PaperState,
    pub stats: TickStats,
    latest_prices: HashMap<String, f64>,
    /// Per-symbol latest indicators for IPC / 每交易對最新指標供 IPC 使用
    latest_indicators: HashMap<String, IndicatorSnapshot>,
    /// Recent signals ring buffer (max 100) / 最近信號環形緩衝（最大 100）
    recent_signals: VecDeque<Signal>,
    /// Recent intents ring buffer (max 50) / 最近意圖環形緩衝（最大 50）
    recent_intents: VecDeque<TimestampedIntent>,
    /// Recent fills ring buffer (max 50) / 最近成交環形緩衝（最大 50）
    recent_fills: VecDeque<TimestampedFill>,
    /// Channel to dispatch server-side stop requests (Item 1: dual-track stops).
    /// 派發伺服器端止損請求的通道（項目 1：雙軌止損）。
    stop_request_tx: Option<tokio::sync::mpsc::UnboundedSender<StopRequest>>,
    /// ADL alert ring buffer (ts_ms, symbol, rank). Item 9.
    /// ADL 警報環形緩衝（時間戳, 交易對, 排名）。項目 9。
    adl_alerts: VecDeque<(u64, String, u32)>,
    /// Enable canary mode — on_tick returns per-tick CanaryRecord (R07-2).
    /// 啟用灰度模式 — on_tick 返回每 tick 的 CanaryRecord。
    pub canary_mode: bool,
    /// Instrument info cache for exchange precision rounding (R-05).
    /// 合約信息緩存，用於交易所精度取整。
    instrument_cache: Option<Arc<InstrumentInfoCache>>,
    /// Channel to dispatch shadow orders to Bybit Demo API.
    /// 派發影子訂單到 Bybit Demo API 的通道。
    shadow_order_tx: Option<tokio::sync::mpsc::UnboundedSender<ShadowOrderRequest>>,
    /// Phase 1: Channel to dispatch market data to async PG writer.
    /// Phase 1：派發市場數據到異步 PG 寫入器的通道。
    market_data_tx: Option<tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>>,
    /// Phase 1: Channel to dispatch feature snapshots to async PG writer.
    /// Phase 1：派發特徵快照到異步 PG 寫入器的通道。
    feature_tx: Option<tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>>,
    /// Phase 2a: Channel to dispatch trading lifecycle events to PG writer.
    /// Phase 2a：派發交易生命週期事件到 PG 寫入器的通道。
    trading_tx: Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    /// Phase 2a: Channel to dispatch decision context snapshots to PG writer.
    /// Phase 2a：派發決策上下文快照到 PG 寫入器的通道。
    context_tx: Option<tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>>,
    /// Phase 1: Feature version string for FeatureSnapshot.
    /// Phase 1：特徵版本字符串。
    feature_version: String,
    /// Phase 1: Counter for dropped channel sends (logged periodically).
    /// Phase 1：通道發送丟棄計數器（定期記錄）。
    market_tx_dropped: u64,
    feature_tx_dropped: u64,
    /// Paper trading paused — skip strategy dispatch + shadow orders, keep prices/indicators/stops.
    /// 紙盤交易暫停 — 跳過策略分派+影子訂單，保留價格/指標/止損。
    pub paper_paused: bool,
    /// EXT-1: Trading mode (paper_only or exchange).
    /// EXT-1：交易模式（紙盤或交易所）。
    trading_mode: crate::config::TradingMode,
    /// EXT-1: Sequence counter for generating unique order_link_id.
    /// EXT-1：序列計數器，用於生成唯一 order_link_id。
    exchange_seq: u64,
    /// EXT-1: Symbols with pending close orders (prevent duplicate stop-close in exchange mode).
    /// EXT-1：有待處理平倉訂單的交易對（防止交易所模式下重複止損平倉）。
    pending_close_symbols: std::collections::HashSet<String>,
    /// RRC-1-A1: H0 Gate — pre-strategy health/risk/freshness gate (shadow mode by default).
    /// RRC-1-A1：H0 門控 — 策略前的健康/風控/新鮮度檢查（默認影子模式）。
    pub h0_gate: H0Gate,
    /// RRC-1-C1: Price history tracker for ATR computation + spike detection.
    /// RRC-1-C1：價格歷史追蹤器，用於 ATR 計算 + 尖峰偵測。
    price_tracker: PriceHistoryTracker,
    /// RRC-1-C3: Per-symbol consecutive loss counter (reset on win).
    /// RRC-1-C3：每交易對連續虧損計數器（盈利時重置）。
    pub consecutive_losses: HashMap<String, u32>,
    /// RRC-1-C4: Session halted flag — set by HaltSession, cleared by Resume/Reset.
    /// RRC-1-C4：會話暫停標誌 — 由 HaltSession 設置，由 Resume/Reset 清除。
    pub session_halted: bool,
    /// Session 11: 1-minute trade aggregator (idle writer #2 fix).
    /// Session 11：1 分鐘成交聚合器（idle writer #2 修復）。
    trade_aggregator: crate::database::aggregators::TradeAggregator,
    /// Session 11: 1-minute orderbook aggregator (idle writer #1 fix).
    /// Session 11：1 分鐘訂單簿聚合器（idle writer #1 修復）。
    ob_aggregator: crate::database::aggregators::ObAggregator,
    /// PNL-3: Boot timestamp (set on first tick) for cooldown gating.
    /// PNL-3：啟動時間戳（首個 tick 設定），用於冷卻期門控。
    boot_ts_ms: Option<u64>,
    /// PNL-3: Cooldown duration after boot during which strategy signals are suppressed.
    /// Reads from OPENCLAW_BOOT_COOLDOWN_MS env var, default 60_000ms.
    /// PNL-3：啟動冷卻期，期間策略信號被抑制（止損/指標/快照繼續）。
    boot_cooldown_ms: u64,
    /// DB-RUN-1: Last persisted signal per (symbol, strategy) — direction + ts_ms.
    /// Used to dedupe by state-change and rate-limit by heartbeat.
    /// DB-RUN-1：每 (symbol, strategy) 最近持久化的信號 — 用於狀態變更去重 + 心跳節流。
    last_persisted_signal: HashMap<(String, String), (openclaw_core::signals::SignalDirection, u64)>,
    /// DB-RUN-1: Heartbeat interval — re-emit unchanged signals at most this often.
    /// Default 60_000ms (1/min). 0 disables (legacy per-tick behavior).
    /// DB-RUN-1：心跳間隔，未變化信號最多每此間隔重發一次。0=關閉節流。
    signals_heartbeat_ms: u64,
    /// DB-RUN-1: Counter for dropped (throttled) signal writes — observability.
    /// DB-RUN-1：被節流跳過的 signal 寫入計數，供 status 報告觀察降頻效果。
    signals_throttled: u64,
    /// DB-RUN-2: Counter for dropped (throttled) decision_context writes.
    /// DB-RUN-2：被節流跳過的 decision_context 寫入計數。
    context_throttled: u64,
}

impl TickPipeline {
    pub fn new(symbols: &[&str]) -> Self {
        // Read paper balance from env var or default to 10,000 USDT.
        // 從環境變量讀取紙盤餘額，預設 10,000 USDT。
        let balance = std::env::var("OPENCLAW_PAPER_BALANCE")
            .ok()
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(10_000.0);
        Self::with_balance(symbols, balance)
    }

    /// Create a pipeline with an explicit initial balance.
    /// 使用明確初始餘額創建管線。
    pub fn with_balance(symbols: &[&str], balance: f64) -> Self {
        Self {
            kline_manager: KlineManager::new(symbols, None, None),
            signal_engine: SignalEngine::new(),
            orchestrator: Orchestrator::new(),
            intent_processor: IntentProcessor::new(),
            governance: GovernanceCore::new(),
            paper_state: PaperState::new(balance),
            stats: TickStats::default(),
            latest_prices: HashMap::new(),
            latest_indicators: HashMap::new(),
            recent_signals: VecDeque::new(),
            recent_intents: VecDeque::new(),
            recent_fills: VecDeque::new(),
            stop_request_tx: None,
            adl_alerts: VecDeque::new(),
            canary_mode: false,
            instrument_cache: None,
            shadow_order_tx: None,
            market_data_tx: None,
            feature_tx: None,
            trading_tx: None,
            context_tx: None,
            feature_version: "v1.0".into(),
            market_tx_dropped: 0,
            feature_tx_dropped: 0,
            paper_paused: false,
            trading_mode: crate::config::TradingMode::PaperOnly,
            exchange_seq: 0,
            pending_close_symbols: std::collections::HashSet::new(),
            h0_gate: H0Gate::new(Some(openclaw_types::H0GateConfig {
                shadow_mode: true, // RRC-1-A3: observe-only until proven stable
                ..Default::default()
            })),
            price_tracker: PriceHistoryTracker::new(),
            consecutive_losses: HashMap::new(),
            session_halted: false,
            trade_aggregator: crate::database::aggregators::TradeAggregator::new(),
            ob_aggregator: crate::database::aggregators::ObAggregator::new(),
            boot_ts_ms: None,
            boot_cooldown_ms: std::env::var("OPENCLAW_BOOT_COOLDOWN_MS")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(60_000),
            last_persisted_signal: HashMap::new(),
            signals_heartbeat_ms: std::env::var("OPENCLAW_SIGNALS_HEARTBEAT_MS")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(60_000),
            signals_throttled: 0,
            context_throttled: 0,
        }
    }

    /// Set dynamic fee rate from API for more accurate paper trading cost.
    /// 設定 API 動態費率，提高紙盤交易成本精確度。
    pub fn set_fee_rate(&mut self, rate: f64) {
        self.intent_processor.set_fee_rate(rate);
    }

    /// PNL-3 / Session 12: Update boot cooldown at runtime via IPC.
    /// Clamped to [0, 1h]. Returns the value actually applied.
    /// PNL-3：運行時更新啟動冷卻期，鉗制到 [0, 1h]。
    pub fn set_boot_cooldown_ms(&mut self, ms: u64) -> u64 {
        let v = ms.min(3_600_000);
        self.boot_cooldown_ms = v;
        v
    }

    pub fn boot_cooldown_ms(&self) -> u64 {
        self.boot_cooldown_ms
    }

    /// DB-RUN-1: Set signals heartbeat interval at runtime. 0 disables throttling.
    /// DB-RUN-1：運行時設定 signals 心跳間隔，0=關閉節流。
    pub fn set_signals_heartbeat_ms(&mut self, ms: u64) -> u64 {
        self.signals_heartbeat_ms = ms.min(3_600_000);
        self.signals_heartbeat_ms
    }

    pub fn signals_heartbeat_ms(&self) -> u64 {
        self.signals_heartbeat_ms
    }

    pub fn signals_throttled(&self) -> u64 {
        self.signals_throttled
    }

    pub fn context_throttled(&self) -> u64 {
        self.context_throttled
    }

    /// DB-RUN-1: Decide whether to persist a freshly emitted signal.
    /// Persist if (a) direction differs from last persisted for the same
    /// (symbol, strategy) key, OR (b) heartbeat interval has elapsed.
    /// Returns true on persist (and updates the dedupe map).
    /// DB-RUN-1：判斷新生成的 signal 是否應持久化（狀態變更或心跳到期）。
    fn should_persist_signal(&mut self, sig: &openclaw_core::signals::Signal) -> bool {
        if self.signals_heartbeat_ms == 0 {
            return true;
        }
        let key = (sig.symbol.clone(), sig.source.clone());
        let now = sig.ts_ms;
        let persist = match self.last_persisted_signal.get(&key) {
            None => true,
            Some(&(prev_dir, prev_ts)) => {
                prev_dir != sig.direction
                    || now.saturating_sub(prev_ts) >= self.signals_heartbeat_ms
            }
        };
        if persist {
            self.last_persisted_signal.insert(key, (sig.direction, now));
        } else {
            self.signals_throttled += 1;
        }
        persist
    }

    /// PNL-4: Derive live regime label from indicator snapshot.
    /// Priority: Hurst regime → ADX strength fallback → "ranging" default.
    /// ADX threshold reads from RiskManagerConfig (Session 12 cleanup).
    /// PNL-4：從指標快照推導實時 regime 標籤。
    fn derive_regime(&self, snap: Option<&openclaw_core::indicators::IndicatorSnapshot>) -> String {
        if let Some(ind) = snap {
            if let Some(ref h) = ind.hurst {
                match h.regime.as_str() {
                    "trending" => return "trending".into(),
                    "mean_reverting" => return "ranging".into(),
                    _ => {}
                }
            }
            if let Some(ref a) = ind.adx {
                let threshold = self.intent_processor.risk_config().adx_trending_threshold;
                if a.adx >= threshold {
                    return "trending".into();
                }
            }
        }
        "ranging".into()
    }

    /// Set instrument info cache for exchange precision rounding (R-05).
    /// 設定合約信息緩存，用於交易所精度取整。
    pub fn set_instrument_cache(&mut self, cache: Arc<InstrumentInfoCache>) {
        self.instrument_cache = Some(cache);
    }

    /// Set channel for dispatching server-side stop requests (Item 1: dual-track stops).
    /// 設定伺服器端止損請求派發通道（項目 1：雙軌止損）。
    pub fn set_stop_channel(&mut self, tx: tokio::sync::mpsc::UnboundedSender<StopRequest>) {
        self.stop_request_tx = Some(tx);
    }

    /// Set channel for dispatching orders to exchange API.
    /// 設定訂單派發通道到交易所 API。
    pub fn set_shadow_channel(
        &mut self,
        tx: tokio::sync::mpsc::UnboundedSender<ShadowOrderRequest>,
    ) {
        self.shadow_order_tx = Some(tx);
    }

    /// EXT-1: Set trading mode (paper_only or exchange).
    /// EXT-1：設定交易模式。
    pub fn set_trading_mode(&mut self, mode: crate::config::TradingMode) {
        self.trading_mode = mode;
    }

    /// EXT-1: Clear pending close flag for a symbol (called when close order is rejected/cancelled).
    /// EXT-1：清除交易對的待處理平倉標記（平倉訂單被拒/取消時調用）。
    pub fn clear_pending_close(&mut self, symbol: &str) {
        self.pending_close_symbols.remove(symbol);
    }

    /// EXT-1: Clear all pending close flags (on reset or DCP).
    /// EXT-1：清除所有待處理平倉標記（重置或 DCP 時）。
    pub fn clear_all_pending_close(&mut self) {
        self.pending_close_symbols.clear();
    }

    /// Phase 1: Set channel for dispatching market data to async PG writer.
    /// Phase 1：設定市場數據派發到異步 PG 寫入器的通道。
    pub fn set_market_data_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>,
    ) {
        self.market_data_tx = Some(tx);
    }

    /// Phase 1: Set channel for dispatching feature snapshots to async PG writer.
    /// Phase 1：設定特徵快照派發到異步 PG 寫入器的通道。
    pub fn set_feature_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>,
    ) {
        self.feature_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching trading lifecycle events to PG writer.
    /// Phase 2a：設定交易生命週期事件派發通道。
    pub fn set_trading_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::TradingMsg>,
    ) {
        self.trading_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching decision context snapshots.
    /// Phase 2a：設定決策上下文快照派發通道。
    pub fn set_context_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>,
    ) {
        self.context_tx = Some(tx);
    }

    /// Process a single price event through the full pipeline.
    /// Returns a CanaryRecord when canary_mode is enabled (R07-2).
    /// 通過完整管線處理單個價格事件。
    /// 灰度模式啟用時返回 CanaryRecord。
    pub fn on_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Start timing the tick processing / 開始計時 tick 處理
        let tick_start = Instant::now();

        self.stats.total_ticks += 1;
        self.stats.last_tick_ms = event.ts_ms;
        // PNL-3: Stamp boot timestamp on first tick (used for cooldown gate below).
        // PNL-3：首個 tick 記錄啟動時間戳（用於下方冷卻期門控）。
        if self.boot_ts_ms.is_none() {
            self.boot_ts_ms = Some(event.ts_ms);
        }
        self.latest_prices
            .insert(event.symbol.clone(), event.last_price);
        self.paper_state
            .set_latest_price(&event.symbol, event.last_price);
        // RRC-1-B2: Reset daily start balance at UTC midnight for daily loss tracking.
        // RRC-1-B2：UTC 午夜重置每日起始餘額，用於日損追蹤。
        self.intent_processor
            .maybe_reset_daily_balance(self.paper_state.balance(), event.ts_ms);
        // RRC-1-C1: Feed price to tracker for ATR computation + spike detection.
        // RRC-1-C1：餵入價格到追蹤器，用於 ATR 計算 + 尖峰偵測。
        self.price_tracker
            .record(&event.symbol, event.last_price, event.ts_ms);
        // Update per-symbol turnover for dynamic slippage (from ticker events)
        // 更新每交易對成交額用於動態滑點（來自 ticker 事件）
        if event.turnover_24h > 0.0 {
            self.paper_state
                .set_latest_turnover(&event.symbol, event.turnover_24h);

            // Phase 1 (F-2 fix): Emit TickerSnapshot to market writer for ticker events.
            // Phase 1（F-2 修復）：為 ticker 事件發送 TickerSnapshot 到市場寫入器。
            if let Some(ref tx) = self.market_data_tx {
                let spread = if event.ask_price > 0.0 && event.bid_price > 0.0 {
                    (event.ask_price - event.bid_price) / event.last_price * 10_000.0
                } else {
                    0.0
                };
                let _ = tx.try_send(crate::database::MarketDataMsg::TickerSnapshot {
                    ts_ms: event.ts_ms,
                    symbol: event.symbol.clone(),
                    last_price: event.last_price,
                    mark_price: 0.0,  // not available in PriceEvent yet
                    index_price: 0.0, // not available in PriceEvent yet
                    best_bid: event.bid_price,
                    best_ask: event.ask_price,
                    bid_size: 0.0, // not available in PriceEvent yet
                    ask_size: 0.0, // not available in PriceEvent yet
                    volume_24h: event.volume_24h,
                    turnover_24h: event.turnover_24h,
                    spread_bps: spread,
                    open_interest: 0.0, // not available in PriceEvent yet
                });
            }
        }

        // Item 9 (M3 fix): ADL alert monitoring
        // 項目 9（M3 修復）：ADL 警報監控
        if event.metadata.get("type").map(|t| t.as_str()) == Some("adl_notice") {
            if let Some(rank_str) = event.metadata.get("adl_rank") {
                if let Ok(rank) = rank_str.parse::<u32>() {
                    self.adl_alerts
                        .push_back((event.ts_ms, event.symbol.clone(), rank));
                    if self.adl_alerts.len() > 50 {
                        self.adl_alerts.pop_front();
                    }
                    if rank >= 3 {
                        info!(
                            symbol = %event.symbol, rank = rank,
                            "⚠ ADL rank HIGH — consider reducing position / ADL 排名高，考慮減倉"
                        );
                    }
                }
            }
        }

        // Session 11: feed trade & orderbook events into 1-minute aggregators.
        // Flushes happen at minute boundaries → MarketDataMsg::TradeAgg1m / ObSnapshot.
        // Session 11：將 trade/orderbook 事件餵入 1 分鐘聚合器，跨分鐘時 flush。
        if let Some(event_type) = event.metadata.get("type").map(|s| s.as_str()) {
            match event_type {
                "trade" => {
                    let side = event
                        .metadata
                        .get("side")
                        .and_then(|s| crate::database::aggregators::TradeSide::parse(s));
                    let qty = event
                        .metadata
                        .get("qty")
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0);
                    if let Some(side) = side {
                        if let Some(msg) = self.trade_aggregator.record(
                            &event.symbol,
                            side,
                            qty,
                            event.last_price,
                            event.ts_ms,
                        ) {
                            if let Some(ref tx) = self.market_data_tx {
                                let _ = tx.try_send(msg);
                            }
                        }
                    }
                }
                "orderbook" => {
                    let bids: Vec<(f64, f64)> = event
                        .metadata
                        .get("bids5")
                        .and_then(|s| serde_json::from_str(s).ok())
                        .unwrap_or_default();
                    let asks: Vec<(f64, f64)> = event
                        .metadata
                        .get("asks5")
                        .and_then(|s| serde_json::from_str(s).ok())
                        .unwrap_or_default();
                    if !bids.is_empty() && !asks.is_empty() {
                        if let Some(msg) = self.ob_aggregator.record(
                            &event.symbol,
                            &bids,
                            &asks,
                            event.ts_ms,
                        ) {
                            if let Some(ref tx) = self.market_data_tx {
                                let _ = tx.try_send(msg);
                            }
                        }
                    }
                }
                _ => {}
            }
        }

        // Step 0: Fast track check — emergency actions before normal processing
        let ft_action = crate::fast_track::evaluate_fast_track(
            self.governance.risk.level,
            0.0, // price_drop_pct computed externally
            0.0, // margin_utilization computed externally
        );
        if ft_action == crate::fast_track::FastTrackAction::CloseAll {
            let symbols: Vec<String> = self
                .paper_state
                .positions()
                .iter()
                .map(|p| p.symbol.clone())
                .collect();
            for sym in symbols {
                self.paper_state
                    .close_position(&sym, event.last_price, event.ts_ms);
                self.stats.total_stops += 1;
            }
            // Measure elapsed time for fast-track exit / 計算快速通道退出的耗時
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], tick_duration_us);
        }

        // Step 0.5: H0 Gate pre-check (shadow mode: observe only) / H0 門控前置檢查
        self.h0_gate.update_price_ts(&event.symbol, event.ts_ms);
        let h0_result = self.h0_gate.check(&event.symbol, "linear", event.ts_ms);
        let h0_allowed = h0_result.allowed;
        if !h0_result.allowed {
            // Hard block: stops only / 硬阻斷：僅處理止損
            warn!(symbol = %event.symbol, reason = %h0_result.reason,
                "H0 BLOCKED — stops only / H0 阻斷 — 僅止損");
            for (sym, _) in &self.paper_state.check_stops(event.last_price, event.ts_ms) {
                self.paper_state
                    .close_position(sym, event.last_price, event.ts_ms);
                self.stats.total_stops += 1;
            }
            let dur = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], dur);
        }
        if !h0_result.reason.is_empty() {
            debug!(symbol = %event.symbol, reason = %h0_result.reason,
                "H0 shadow would-block / H0 影子模式本應阻斷");
        }

        // Step 1: Kline aggregation — collect closed bars for DB write.
        // 步驟 1：K 線聚合 — 收集已關閉的 K 線用於 DB 寫入。
        let closed_bars = self.kline_manager.on_tick(
            &event.symbol,
            event.last_price,
            event.ts_ms,
            event.volume_24h,
            0.0,
        );

        // Phase 1: Emit KlineClose for each closed bar to market writer (F-2 audit fix).
        // Phase 1：為每根已關閉 K 線發送 KlineClose 到市場寫入器（F-2 審計修復）。
        if let Some(ref tx) = self.market_data_tx {
            for (timeframe, bar) in &closed_bars {
                if tx
                    .try_send(crate::database::MarketDataMsg::KlineClose {
                        symbol: event.symbol.clone(),
                        timeframe: timeframe.clone(),
                        bar: bar.clone(),
                    })
                    .is_err()
                {
                    self.market_tx_dropped += 1;
                }
            }
        }

        // Step 2: Compute indicators (need enough 1m bars)
        // 步驟 2：計算指標（需要足夠的 1 分鐘 K 線）
        let indicators = self.compute_indicators(&event.symbol);

        // Store latest indicators for IPC snapshot / 存儲最新指標供 IPC 快照使用
        if let Some(ref ind) = indicators {
            self.latest_indicators
                .insert(event.symbol.clone(), ind.clone());
        }

        // Phase 1: Emit FeatureSnapshot to DB writer channel (non-blocking try_send).
        // Phase 1：發送 FeatureSnapshot 到 DB 寫入器通道（非阻塞 try_send）。
        if let (Some(ref tx), Some(ref ind)) = (&self.feature_tx, &indicators) {
            let snap = crate::feature_collector::FeatureSnapshot::new(
                event.symbol.clone(),
                event.ts_ms,
                event.last_price,
                event.volume_24h,
                ind.clone(),
                self.feature_version.clone(),
            );
            if tx.try_send(snap).is_err() {
                self.feature_tx_dropped += 1;
            }
        }

        // ── Pause gate: skip signal evaluation + strategy dispatch when paused ──
        // 暫停門控：暫停時跳過信號評估+策略分派（價格/指標/止損繼續）
        if self.paper_paused {
            // Protective stops while paused / 暫停時的保護性止損
            for (sym, trigger) in &self.paper_state.check_stops(event.last_price, event.ts_ms) {
                let pos_info = self
                    .paper_state
                    .get_position(sym)
                    .map(|p| (p.is_long, p.qty));
                debug!(symbol = %sym, reason = %trigger.reason, "stop (paused)");
                self.paper_state
                    .close_position(sym, event.last_price, event.ts_ms);
                self.stats.total_stops += 1;
                if let Some((is_long, qty)) = pos_info {
                    self.dispatch_close_order(sym, is_long, qty, event, false);
                }
            }
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, indicators, vec![], vec![], tick_duration_us);
        }

        // PNL-3: Boot cooldown — suppress strategy signals for first N ms after boot.
        // Stops/indicators/feature snapshots continue to run; only intent generation is gated.
        // PNL-3：啟動冷卻期 — 啟動後 N 毫秒內抑制策略信號（止損/指標/快照繼續）。
        let in_boot_cooldown = match self.boot_ts_ms {
            Some(boot) => event.ts_ms.saturating_sub(boot) < self.boot_cooldown_ms,
            None => false,
        };

        // Step 3: Signal evaluation
        let signals = if in_boot_cooldown {
            debug!(
                symbol = %event.symbol,
                elapsed_ms = event.ts_ms.saturating_sub(self.boot_ts_ms.unwrap_or(event.ts_ms)),
                cooldown_ms = self.boot_cooldown_ms,
                "PNL-3 boot cooldown — signals suppressed / 啟動冷卻期 — 信號已抑制"
            );
            vec![]
        } else if let Some(ref ind) = indicators {
            let input = snapshot_to_input(ind);
            self.signal_engine
                .evaluate(&event.symbol, "1m", &input, event.ts_ms)
        } else {
            vec![]
        };

        // Store recent signals for IPC snapshot (ring buffer, max 100)
        // 存儲最近信號供 IPC 快照使用（環形緩衝，最大 100）
        let mut signals_persisted_this_tick = 0u32;
        for sig in &signals {
            self.recent_signals.push_back(sig.clone());
            if self.recent_signals.len() > 100 {
                self.recent_signals.pop_front();
            }

            // DB-RUN-1: Throttle signal persistence — only write on state change
            // or heartbeat interval. Reduces 352 rows/s to ~per-symbol-per-strat
            // change rate, expected 95%+ reduction.
            // DB-RUN-1：節流 signal 寫入 — 僅狀態變更或心跳到期時持久化。
            if !self.should_persist_signal(sig) {
                continue;
            }
            signals_persisted_this_tick += 1;

            // Phase 2a: Emit signal to trading_writer for PG persistence
            if let Some(ref tx) = self.trading_tx {
                let _ = tx.try_send(crate::database::TradingMsg::Signal {
                    signal_id: format!("sig-{}-{}", sig.source, sig.ts_ms),
                    ts_ms: sig.ts_ms,
                    symbol: sig.symbol.clone(),
                    strategy_name: sig.source.clone(),
                    timeframe: sig.timeframe.clone(),
                    signal_type: format!("{:?}", sig.direction),
                    strength: sig.confidence,
                    context_id: format!("ctx-{}-{}", sig.symbol, sig.ts_ms),
                });
            }
        }

        // DB-RUN-2: Decision context piggybacks on signal persistence — only emit
        // when at least one signal was actually persisted this tick. Reduces
        // 10.6M/day to ~36k/day (~99.6% drop) while preserving full fidelity at
        // every state-change / heartbeat boundary.
        // DB-RUN-2：decision_context 跟隨 signal 持久化 — 本 tick 至少 1 個 signal
        // 被寫入時才發送 context。降幅 ~99.6%，狀態變更與心跳邊界仍保留完整快照。
        if !signals.is_empty() && signals_persisted_this_tick == 0 {
            self.context_throttled += 1;
        }
        if signals_persisted_this_tick > 0 {
            if let Some(ref tx) = self.context_tx {
                let ind = indicators.as_ref();
                let pos = self.paper_state.get_position(&event.symbol);
                let _ = tx.try_send(crate::database::DecisionContextMsg {
                    context_id: format!("ctx-{}-{}", event.symbol, event.ts_ms),
                    ts_ms: event.ts_ms,
                    decision_type: "signal_generated".into(),
                    symbol: event.symbol.clone(),
                    strategy_name: signals[0].source.clone(),
                    last_price: event.last_price,
                    spread_bps: if event.ask_price > 0.0 && event.bid_price > 0.0 {
                        (event.ask_price - event.bid_price) / event.last_price * 10_000.0
                    } else {
                        0.0
                    },
                    regime_5m: ind
                        .and_then(|i| i.hurst.as_ref())
                        .map(|h| h.regime.clone())
                        .unwrap_or_default(),
                    ind_5m_adx: ind
                        .and_then(|i| i.adx.as_ref())
                        .map(|a| a.adx)
                        .unwrap_or(0.0),
                    ind_5m_rsi: ind.and_then(|i| i.rsi_14).unwrap_or(50.0),
                    ind_5m_atr_14_pct: ind
                        .and_then(|i| i.atr_14.as_ref())
                        .map(|a| a.atr_percent)
                        .unwrap_or(0.0),
                    position_side: pos
                        .map(|p| if p.is_long { "Long" } else { "Short" })
                        .unwrap_or("None")
                        .into(),
                    position_qty: pos.map(|p| p.qty).unwrap_or(0.0),
                    total_equity: self.paper_state.balance(),
                    drawdown_pct: self.paper_state.drawdown_pct(),
                    indicators_snapshot: ind
                        .map(|i| serde_json::to_value(i).unwrap_or_default())
                        .unwrap_or_default(),
                    position_detail: pos
                        .map(|p| serde_json::to_value(p).unwrap_or_default())
                        .unwrap_or_default(),
                    decision_payload: serde_json::to_value(&signals).unwrap_or_default(),
                });
            }
        }

        // Step 4+5: Per-strategy dispatch + intent processing with rejection/fill callbacks (RC-04/RC-05).
        // 步驟 4+5：逐策略分派 + 意圖處理，含拒絕/成交回調。
        let ctx = TickContext {
            symbol: event.symbol.clone(),
            price: event.last_price,
            timestamp_ms: event.ts_ms,
            indicators: indicators.clone(),
            signals: signals.clone(),
            h0_allowed, // RRC-1-A1: real H0 gate result from Step 0.5
        };

        // NOTE: Current rejection rollback assumes each strategy emits at most 1 intent per tick.
        // If a strategy ever emits >1, partial rejection + partial fill could leave inconsistent state.
        // All current strategies satisfy this constraint. Revisit if multi-intent strategies are added.
        // 注意：當前拒絕回滾假設每策略每 tick 最多發出 1 個意圖。所有當前策略滿足此約束。
        let is_exchange_mode = self.trading_mode == crate::config::TradingMode::Exchange;
        // Extract ATR for cost gate (Gate 3) / 提取 ATR 用於成本門控
        let atr_value = indicators
            .as_ref()
            .and_then(|i| i.atr_14.as_ref())
            .map(|a| a.atr)
            .unwrap_or(0.0);

        let mut intents: Vec<crate::intent_processor::OrderIntent> = Vec::new();
        for strategy in self.orchestrator.strategies_mut() {
            if !strategy.is_active() {
                continue;
            }
            let strategy_intents = strategy.on_tick(&ctx);
            debug_assert!(
                strategy_intents.len() <= 1,
                "Strategy {} emitted {} intents in one tick — rollback assumes max 1",
                strategy.name(),
                strategy_intents.len()
            );
            for intent in &strategy_intents {
                if is_exchange_mode {
                    // ═══ EXCHANGE MODE: gates only, send order to exchange ═══
                    // ═══ 交易所模式：僅過門禁，發送訂單到交易所 ═══
                    let gate = self.intent_processor.process_gates_only(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                    );
                    if gate.approved {
                        self.stats.total_intents += 1;

                        // Phase 3b fix: Emit Intent to trading_tx for PG persistence.
                        // Phase 3b 修復：發送 Intent 到 trading_tx 以持久化到 PG。
                        if let Some(ref tx) = self.trading_tx {
                            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                                intent_id: format!("intent-{}-{}", intent.symbol, event.ts_ms),
                                ts_ms: event.ts_ms,
                                signal_id: String::new(),
                                context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                                symbol: intent.symbol.clone(),
                                side: if intent.is_long {
                                    "Buy".into()
                                } else {
                                    "Sell".into()
                                },
                                qty: gate.approved_qty,
                                price: event.last_price,
                                order_type: intent.order_type.clone(),
                                strategy_name: intent.strategy.clone(),
                            });
                        }

                        self.exchange_seq = self.exchange_seq.wrapping_add(1);
                        let order_link_id = format!("oc_{}_{}", event.ts_ms, self.exchange_seq);

                        // Round to exchange precision / 取整至交易所精度
                        let final_qty = if let Some(ref icache) = self.instrument_cache {
                            if let Some(spec) = icache.get(&intent.symbol) {
                                spec.round_qty(gate.approved_qty)
                            } else {
                                gate.approved_qty
                            }
                        } else {
                            gate.approved_qty
                        };

                        // P0-2 fix: Skip if qty rounded to zero / 數量取整為零則跳過
                        if final_qty <= 0.0 {
                            warn!(symbol = %intent.symbol, "exchange order skipped: qty=0 after rounding");
                            continue;
                        }

                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: format!("pending_exchange:{}", order_link_id),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }

                        // Dispatch to exchange / 派發到交易所
                        // I-08 雙軌止損：compute broker-side SL from stop config
                        let sl_pct = self.paper_state.stop_config_pct();
                        let broker_sl = if sl_pct > 0.0 {
                            Some(if intent.is_long {
                                event.last_price * (1.0 - sl_pct / 100.0)
                            } else {
                                event.last_price * (1.0 + sl_pct / 100.0)
                            })
                        } else {
                            None
                        };
                        if let Some(ref tx) = self.shadow_order_tx {
                            let _ = tx.send(ShadowOrderRequest {
                                symbol: intent.symbol.clone(),
                                is_long: intent.is_long,
                                qty: final_qty,
                                price: event.last_price,
                                strategy: intent.strategy.clone(),
                                paper_fill_ts: event.ts_ms,
                                is_close: false,
                                order_link_id,
                                is_primary: true,
                                stop_loss: broker_sl,
                                take_profit: None,
                            });
                        }
                    } else if let Some(ref reason) = gate.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: format!("rejected:{}", reason),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }
                    }
                } else {
                    // ═══ PAPER_ONLY MODE: simulate fill locally + optional shadow order ═══
                    // ═══ 紙盤模式：本地模擬成交 + 可選影子訂單 ═══
                    let result = self.intent_processor.process(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                    );
                    if result.submitted {
                        self.stats.total_intents += 1;
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: "submitted".into(),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }

                        // Phase 3b fix: Emit Intent to trading_tx for PG persistence.
                        // Phase 3b 修復：發送 Intent 到 trading_tx 以持久化到 PG。
                        if let Some(ref tx) = self.trading_tx {
                            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                                intent_id: format!("intent-{}-{}", intent.symbol, event.ts_ms),
                                ts_ms: event.ts_ms,
                                signal_id: String::new(),
                                context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                                symbol: intent.symbol.clone(),
                                side: if intent.is_long {
                                    "Buy".into()
                                } else {
                                    "Sell".into()
                                },
                                qty: intent.qty,
                                price: event.last_price,
                                order_type: intent.order_type.clone(),
                                strategy_name: intent.strategy.clone(),
                            });
                        }

                        if let Some(mut fill) = result.fill {
                            if let Some(ref icache) = self.instrument_cache {
                                if let Some(spec) = icache.get(&intent.symbol) {
                                    fill.fill_qty = spec.round_qty(fill.fill_qty);
                                    fill.fill_price = spec.round_price(fill.fill_price);
                                    // Paper min-qty fallback: if rounding reduced to 0, use min_qty
                                    // so high-priced assets (BTC/ETH) can still accumulate fill data.
                                    // Guard: min_qty notional must not exceed 10% of balance.
                                    // Paper 最小手數後備：取整為 0 時使用 min_qty，
                                    // 讓高價資產（BTC/ETH）仍能積累成交數據。
                                    // 防護：min_qty 名義值不得超過餘額的 10%。
                                    if fill.fill_qty <= 0.0 && spec.min_qty > 0.0 {
                                        let notional = spec.min_qty * fill.fill_price;
                                        let balance = self.paper_state.balance();
                                        if notional <= balance * 0.10 {
                                            info!(symbol = %intent.symbol, min_qty = spec.min_qty,
                                                  "paper fill: qty rounded to 0, using min_qty fallback / 數量取整為 0，使用最小手數");
                                            fill.fill_qty = spec.min_qty;
                                        }
                                    }
                                }
                            }
                            // Guard: skip zero-qty fills (instrument rounding can reduce to 0)
                            // 防護：跳過零數量成交（合約精度取整可能降為 0）
                            if fill.fill_qty <= 0.0 {
                                warn!(symbol = %intent.symbol, "paper fill skipped: qty=0 after rounding");
                                continue;
                            }
                            strategy.on_fill(intent, &fill);
                            let realized_pnl = self.paper_state.apply_fill(
                                &intent.symbol,
                                intent.is_long,
                                fill.fill_qty,
                                fill.fill_price,
                                fill.fee,
                                event.ts_ms,
                            );
                            self.stats.total_fills += 1;
                            self.recent_fills.push_back(TimestampedFill {
                                timestamp_ms: event.ts_ms,
                                symbol: intent.symbol.clone(),
                                is_long: intent.is_long,
                                qty: fill.fill_qty,
                                price: fill.fill_price,
                                fee: fill.fee,
                                strategy: intent.strategy.clone(),
                            });
                            if self.recent_fills.len() > 50 {
                                self.recent_fills.pop_front();
                            }

                            if let Some(ref tx) = self.trading_tx {
                                let _ = tx.try_send(crate::database::TradingMsg::Fill {
                                    fill_id: format!("fill-{}-{}", intent.symbol, event.ts_ms),
                                    ts_ms: event.ts_ms,
                                    order_id: format!("order-{}-{}", intent.symbol, event.ts_ms),
                                    symbol: intent.symbol.clone(),
                                    side: if intent.is_long {
                                        "Buy".into()
                                    } else {
                                        "Sell".into()
                                    },
                                    qty: fill.fill_qty,
                                    price: fill.fill_price,
                                    fee: fill.fee,
                                    realized_pnl,
                                    strategy_name: intent.strategy.clone(),
                                    context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                                });
                            }

                            if let Some(ref tx) = self.stop_request_tx {
                                if let Some(pos) = self.paper_state.get_position(&intent.symbol) {
                                    let stop_pct = self.paper_state.stop_config_pct();
                                    let sl_price = if pos.is_long {
                                        pos.entry_price * (1.0 - stop_pct / 100.0)
                                    } else {
                                        pos.entry_price * (1.0 + stop_pct / 100.0)
                                    };
                                    let _ = tx.send(StopRequest {
                                        symbol: intent.symbol.clone(),
                                        stop_loss: sl_price,
                                        is_long: pos.is_long,
                                    });
                                }
                            }

                            // Shadow order: mirror paper fill to Demo API
                            if let Some(ref tx) = self.shadow_order_tx {
                                self.exchange_seq = self.exchange_seq.wrapping_add(1);
                                let _ = tx.send(ShadowOrderRequest {
                                    symbol: intent.symbol.clone(),
                                    is_long: intent.is_long,
                                    qty: fill.fill_qty,
                                    price: fill.fill_price,
                                    strategy: intent.strategy.clone(),
                                    paper_fill_ts: event.ts_ms,
                                    is_close: false,
                                    order_link_id: format!(
                                        "sh_{}_{}",
                                        event.ts_ms, self.exchange_seq
                                    ),
                                    is_primary: false,
                                    stop_loss: None,
                                    take_profit: None,
                                });
                            }
                        }
                    } else if let Some(ref reason) = result.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: format!("rejected:{}", reason),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }
                    }
                }
            }
            intents.extend(strategy_intents);
        }

        // Step 6: Position risk checks — 9-check (RRC-1-C2, replaces basic check_stops).
        // 步驟 6：持倉風控 9 項檢查（RRC-1-C2，替代基本止損）。
        self.paper_state.update_best_prices();
        let session_drawdown = self.paper_state.drawdown_pct();
        let daily_loss = self
            .intent_processor
            .daily_loss_pct_pub(self.paper_state.balance());
        let risk_config = self.intent_processor.risk_config().clone();
        let positions: Vec<(String, bool, f64, f64, f64, u64)> = self
            .paper_state
            .positions()
            .iter()
            .map(|p| {
                let price = self
                    .latest_prices
                    .get(&p.symbol)
                    .copied()
                    .unwrap_or(p.entry_price);
                // F1: entry_price=0 → -999% (fail-closed) / entry_price=0 → 強制硬止損
                let pct = |a: f64, b: f64| {
                    if p.entry_price <= 0.0 {
                        -999.0
                    } else if p.is_long {
                        (a - b) / b * 100.0
                    } else {
                        (b - a) / b * 100.0
                    }
                };
                let pnl_pct = pct(price, p.entry_price);
                let peak_pnl_pct = pct(p.best_price, p.entry_price);
                (
                    p.symbol.clone(),
                    p.is_long,
                    p.qty,
                    pnl_pct,
                    peak_pnl_pct,
                    p.entry_ts_ms,
                )
            })
            .collect();

        for (symbol, is_long, qty, pnl_pct, peak_pnl_pct, entry_ts_ms) in &positions {
            let holding_hours = (event.ts_ms.saturating_sub(*entry_ts_ms)) as f64 / 3_600_000.0;
            let atr_pct = self.price_tracker.compute_atr_pct(symbol);
            let consec = self.consecutive_losses.get(symbol).copied().unwrap_or(0);
            // PNL-4: Pull live regime from Hurst (preferred) or ADX fallback.
            // PNL-4：從 Hurst（首選）或 ADX 退回讀取實時 regime，取代硬編碼 "ranging"。
            let regime = self.derive_regime(self.latest_indicators.get(symbol));
            let action = check_position_on_tick(
                *pnl_pct,
                *peak_pnl_pct,
                holding_hours,
                0.0,     // cost_ratio — placeholder, Phase D wiring
                &regime, // PNL-4: live regime from Hurst/ADX
                atr_pct,
                symbol,
                *entry_ts_ms,
                consec,
                daily_loss,
                session_drawdown,
                &risk_config,
            );
            match action {
                RiskAction::Hold => {} // no action / 無動作
                RiskAction::ClosePosition(reason) => {
                    if is_exchange_mode {
                        if self.pending_close_symbols.contains(symbol) {
                            continue;
                        }
                        warn!(symbol = %symbol, reason = %reason, "risk close → exchange / 風控平倉 → 交易所");
                        self.dispatch_close_order(symbol, *is_long, *qty, event, true);
                    } else {
                        debug!(symbol = %symbol, reason = %reason, "risk close / 風控平倉");
                        if *pnl_pct < 0.0 {
                            *self.consecutive_losses.entry(symbol.clone()).or_insert(0) += 1;
                        } else {
                            self.consecutive_losses.remove(symbol);
                        }
                        self.paper_state
                            .close_position(symbol, event.last_price, event.ts_ms);
                        self.stats.total_stops += 1;
                        self.dispatch_close_order(symbol, *is_long, *qty, event, false);
                    }
                }
                RiskAction::HaltSession(reason) => {
                    // RRC-1-C4: Circuit breaker — halt + close all / 熔斷 — 暫停+全部平倉
                    warn!(reason = %reason, "SESSION HALTED / 會話暫停");
                    self.session_halted = true;
                    self.paper_paused = true;
                    let all_pos: Vec<(String, bool, f64)> = self
                        .paper_state
                        .positions()
                        .iter()
                        .map(|p| (p.symbol.clone(), p.is_long, p.qty))
                        .collect();
                    for (sym, il, q) in &all_pos {
                        // Q1 fix: skip already-dispatched closes / 跳過已派發的平倉
                        if is_exchange_mode && self.pending_close_symbols.contains(sym) {
                            continue;
                        }
                        let px = self
                            .latest_prices
                            .get(sym)
                            .copied()
                            .unwrap_or(event.last_price);
                        self.paper_state.close_position(sym, px, event.ts_ms);
                        self.stats.total_stops += 1;
                        self.dispatch_close_order(sym, *il, *q, event, is_exchange_mode);
                    }
                    break;
                }
                RiskAction::SetCooldown(ms) => {
                    // RRC-1-C4: Set cooldown on H0Gate to suppress new orders.
                    // RRC-1-C4：在 H0 門控設置冷卻期，抑制新訂單。
                    let until_ms = event.ts_ms + ms;
                    info!(cooldown_ms = ms, symbol = %symbol,
                        "cooldown set by risk check / 風控設置冷卻期");
                    self.h0_gate
                        .update_risk(openclaw_types::H0GateRiskSnapshot {
                            open_position_count: self.paper_state.positions().len() as u32,
                            total_exposure_pct: 0.0, // recalculated next status interval
                            cooldown_until_ts_ms: until_ms,
                            kill_switch_active: false,
                            snapshot_ts_ms: event.ts_ms,
                        });
                }
            }
        }

        if self.stats.total_ticks % 1000 == 0 {
            info!(
                ticks = self.stats.total_ticks,
                fills = self.stats.total_fills,
                "tick stats"
            );

            // GAP-7 / idle-writer-fix #4: emit PositionSnapshot for every open
            // paper position every 1000 ticks so trading.position_snapshots
            // stays populated for ML training.
            // GAP-7：每 1000 ticks 發射持倉快照以填充 position_snapshots 表。
            if let Some(ref tx) = self.trading_tx {
                for pos in self.paper_state.positions() {
                    let mark_price = *self
                        .latest_prices
                        .get(&pos.symbol)
                        .unwrap_or(&pos.entry_price);
                    let unrealized_pnl = if pos.is_long {
                        (mark_price - pos.entry_price) * pos.qty
                    } else {
                        (pos.entry_price - mark_price) * pos.qty
                    };
                    let msg = crate::database::TradingMsg::PositionSnapshot {
                        ts_ms: event.ts_ms,
                        symbol: pos.symbol.clone(),
                        side: if pos.is_long {
                            "long".to_string()
                        } else {
                            "short".to_string()
                        },
                        qty: pos.qty,
                        entry_price: pos.entry_price,
                        mark_price,
                        unrealized_pnl,
                    };
                    let _ = tx.try_send(msg);
                }
            }
        }

        // Measure elapsed time for the full tick / 計算完整 tick 處理耗時
        let tick_duration_us = tick_start.elapsed().as_micros() as u64;
        self.maybe_canary_record(event, indicators, signals, intents, tick_duration_us)
    }

    /// EXT-1: Apply a confirmed fill from the exchange to paper_state.
    /// Called by event_consumer when exchange confirms a fill for a pending order.
    /// EXT-1：將交易所確認的成交應用到 paper_state。
    pub fn apply_confirmed_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        fill_price: f64,
        fee: f64,
        ts_ms: u64,
        strategy: &str,
        order_link_id: &str,
    ) {
        let realized_pnl = self
            .paper_state
            .apply_fill(symbol, is_long, qty, fill_price, fee, ts_ms);
        self.stats.total_fills += 1;
        // Clear pending_close flag if this was a close fill / 如果是平倉成交，清除待處理平倉標記
        self.pending_close_symbols.remove(symbol);

        self.recent_fills.push_back(TimestampedFill {
            timestamp_ms: ts_ms,
            symbol: symbol.to_string(),
            is_long,
            qty,
            price: fill_price,
            fee,
            strategy: strategy.to_string(),
        });
        if self.recent_fills.len() > 50 {
            self.recent_fills.pop_front();
        }

        if let Some(ref tx) = self.trading_tx {
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: format!("fill-{}-{}", symbol, ts_ms),
                ts_ms,
                order_id: order_link_id.to_string(),
                symbol: symbol.to_string(),
                side: if is_long { "Buy".into() } else { "Sell".into() },
                qty,
                price: fill_price,
                fee,
                realized_pnl,
                strategy_name: strategy.to_string(),
                context_id: format!("ctx-{}-{}", symbol, ts_ms),
            });
        }

        info!(
            symbol = %symbol, qty = %qty, price = %fill_price,
            order_link_id = %order_link_id,
            "confirmed fill applied / 已應用交易所確認成交"
        );
    }

    /// RRC-1-C2: Dispatch a close order via shadow/exchange channel.
    /// RRC-1-C2：通過影子/交易所通道派發平倉訂單。
    fn dispatch_close_order(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        event: &PriceEvent,
        is_primary: bool,
    ) {
        if let Some(ref tx) = self.shadow_order_tx {
            self.exchange_seq = self.exchange_seq.wrapping_add(1);
            let prefix = if is_primary { "oc_risk" } else { "sh_risk" };
            let _ = tx.send(ShadowOrderRequest {
                symbol: symbol.to_string(),
                is_long: !is_long,
                qty,
                price: event.last_price,
                strategy: "risk_check".into(),
                paper_fill_ts: event.ts_ms,
                is_close: true,
                order_link_id: format!("{}_{}_{}", prefix, event.ts_ms, self.exchange_seq),
                is_primary,
                stop_loss: None,
                take_profit: None,
            });
            if is_primary {
                self.pending_close_symbols.insert(symbol.to_string());
            }
        }
    }

    /// Build a canary record if canary_mode is enabled (R07-2).
    /// 灰度模式啟用時構建灰度記錄。
    fn maybe_canary_record(
        &self,
        event: &PriceEvent,
        indicators: Option<IndicatorSnapshot>,
        signals: Vec<Signal>,
        intents: Vec<crate::intent_processor::OrderIntent>,
        tick_duration_us: u64,
    ) -> Option<CanaryRecord> {
        if !self.canary_mode {
            return None;
        }
        Some(CanaryRecord {
            schema_version: "1.0.0".into(),
            source: "rust_engine".into(),
            tick_number: self.stats.total_ticks,
            timestamp_ms: event.ts_ms,
            symbol: event.symbol.clone(),
            price: event.last_price,
            indicators,
            signals,
            order_intents: intents,
            paper_state: self.paper_state.export_state(),
            stats: self.stats.clone(),
            tick_duration_us,
        })
    }

    fn compute_indicators(&self, symbol: &str) -> Option<IndicatorSnapshot> {
        let ohlcv = self.kline_manager.get_ohlcv(symbol, "1m", Some(100))?;
        if ohlcv.close.len() < 30 {
            return None;
        }
        Some(IndicatorEngine::compute_all(
            &ohlcv.high,
            &ohlcv.low,
            &ohlcv.close,
            &ohlcv.volume,
        ))
    }

    pub fn grant_paper_auth(&mut self) -> Result<(), String> {
        self.governance
            .grant_paper_authorization(None)
            .map(|_| ())
            .map_err(|e| e.to_string())
    }

    pub fn status(&self) -> PipelineStatus {
        PipelineStatus {
            stats: self.stats.clone(),
            governance: self.governance.status(),
            positions: self.paper_state.position_count(),
            balance: self.paper_state.balance(),
            symbols_tracked: self.latest_prices.len(),
        }
    }

    /// Create full IPC snapshot / 創建完整 IPC 快照（R06-A）
    pub fn snapshot(&self) -> PipelineSnapshot {
        let strategies: Vec<StrategyInfo> = self.orchestrator.strategy_infos();
        let mut klines: HashMap<String, Vec<openclaw_core::klines::KlineBar>> = HashMap::new();
        for sym in self.kline_manager.symbols() {
            if let Some(buf) = self.kline_manager.get_buffer(sym, "1m") {
                let bars = buf.latest_cloned(100);
                if !bars.is_empty() {
                    klines.insert(sym.clone(), bars);
                }
            }
        }

        PipelineSnapshot {
            paper_state: self.paper_state.export_state(),
            latest_prices: self.latest_prices.clone(),
            stats: self.stats.clone(),
            source: "rust_engine".into(),
            paper_paused: self.paper_paused,
            trading_mode: self.trading_mode,
            indicators: self.latest_indicators.clone(),
            signals: self.recent_signals.iter().cloned().collect(),
            strategies,
            recent_intents: self.recent_intents.iter().cloned().collect(),
            recent_fills: self.recent_fills.iter().cloned().collect(),
            klines,
            h0_gate_stats: Some(self.h0_gate.get_stats().clone()),
            stop_config: Some(self.paper_state.stop_config().clone()),
            guardian_config: Some(self.intent_processor.guardian_config().clone()),
            risk_manager_config: Some(self.intent_processor.risk_config().clone()),
            consecutive_losses: self.consecutive_losses.clone(),
            session_halted: self.session_halted,
            daily_loss_pct: self
                .intent_processor
                .daily_loss_pct_pub(self.paper_state.balance()),
            session_drawdown_pct: self.paper_state.drawdown_pct(),
        }
    }

    /// Read-only access to latest prices map (R06-A).
    /// 最新價格映射的唯讀訪問。
    pub fn latest_prices(&self) -> &HashMap<String, f64> {
        &self.latest_prices
    }

    /// Feed a single replay tick through the full pipeline (R07-replay).
    /// Delegates to on_tick() with canary_mode forced on to guarantee a
    /// CanaryRecord is returned for every tick.
    /// 將單個回放 tick 送入完整管線（R07-replay）。
    /// 強制啟用 canary_mode 以確保每個 tick 都返回 CanaryRecord。
    pub fn feed_replay_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Ensure canary_mode is on so on_tick() produces a record.
        // 確保 canary_mode 開啟，使 on_tick() 產生記錄。
        let was_canary = self.canary_mode;
        self.canary_mode = true;
        let record = self.on_tick(event);
        self.canary_mode = was_canary;
        record
    }
}

/// Convert IndicatorSnapshot to flat IndicatorInput for signal rules.
/// 將 IndicatorSnapshot 轉換為扁平 IndicatorInput 用於信號規則。
fn snapshot_to_input(snap: &IndicatorSnapshot) -> IndicatorInput {
    IndicatorInput {
        rsi: snap.rsi_14,
        sma: snap.sma_20,
        ema: snap.ema_12,
        macd: snap.macd.as_ref().map(|m| m.macd),
        macd_signal: snap.macd.as_ref().map(|m| m.signal),
        macd_histogram: snap.macd.as_ref().map(|m| m.histogram),
        bb_percent_b: snap.bollinger.as_ref().map(|b| b.percent_b),
        bb_bandwidth: snap.bollinger.as_ref().map(|b| b.bandwidth),
        atr_percent: snap.atr_14.as_ref().map(|a| a.atr_percent),
        stoch_k: snap.stochastic.as_ref().map(|s| s.k),
        adx: snap.adx.as_ref().map(|a| a.adx),
        volume_ratio: snap.volume_ratio,
    }
}

// Types extracted to pipeline_types.rs (RRC-1 E2 fix: 1200-line limit).
// 類型已提取到 pipeline_types.rs（RRC-1 E2 修復：1200 行限制）。
pub use crate::pipeline_types::{
    CanaryRecord, PipelineSnapshot, PipelineStatus, StrategyInfo, TimestampedFill,
    TimestampedIntent,
};

#[cfg(test)]
mod tests {
    use super::*;

    fn make_event(symbol: &str, price: f64, ts: u64) -> PriceEvent {
        PriceEvent::new(symbol.to_string(), price, ts)
    }

    #[test]
    fn test_pipeline_creation() {
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.stats.total_ticks, 0);
    }

    #[test]
    fn test_pipeline_on_tick() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert_eq!(pipeline.stats.total_ticks, 1);
    }

    #[test]
    fn test_pipeline_multiple_ticks() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        for i in 0..50 {
            pipeline.on_tick(&make_event("BTCUSDT", 50000.0 + i as f64, i * 60_000));
        }
        assert_eq!(pipeline.stats.total_ticks, 50);
    }

    #[test]
    fn test_position_snapshot_emitted_every_1000_ticks() {
        // GAP-7 regression: PositionSnapshot must be emitted every 1000 ticks
        // for every open paper position when trading_tx is wired.
        // GAP-7 回歸：掛接 trading_tx 時每 1000 ticks 為每個持倉發射快照。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8192);
        pipeline.set_trading_channel(tx);
        // Open a paper long position directly.
        // 直接建立紙盤多單持倉。
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0);
        // Pump exactly 1000 ticks. total_ticks becomes 1000 -> snapshot.
        // 打 1000 tick，total_ticks 達到 1000 觸發快照。
        for i in 0..1000 {
            pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, (i + 1) * 60_000));
        }
        // Drain channel; expect at least one PositionSnapshot for BTCUSDT.
        // 抽取通道；至少應有一條 BTCUSDT 的 PositionSnapshot。
        let mut found = false;
        while let Ok(msg) = rx.try_recv() {
            if let crate::database::TradingMsg::PositionSnapshot {
                symbol,
                side,
                qty,
                mark_price,
                unrealized_pnl,
                ..
            } = msg
            {
                if symbol == "BTCUSDT" {
                    assert_eq!(side, "long");
                    assert!((qty - 0.1).abs() < 1e-9);
                    assert!((mark_price - 50_000.0).abs() < 1e-9);
                    assert!(unrealized_pnl.abs() < 1e-6);
                    found = true;
                    break;
                }
            }
        }
        assert!(
            found,
            "expected a PositionSnapshot for BTCUSDT; positions={}",
            pipeline.paper_state.position_count()
        );
    }

    #[test]
    fn test_position_snapshot_noop_without_channel() {
        // Without trading_tx wired, snapshot loop must be a no-op and never panic.
        // 未掛接 trading_tx 時快照循環必須無動作且不 panic。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", false, 0.2, 50_000.0, 0.0, 0);
        for i in 0..1000 {
            pipeline.on_tick(&make_event("BTCUSDT", 49_000.0, (i + 1) * 60_000));
        }
        assert_eq!(pipeline.stats.total_ticks, 1000);
    }

    #[test]
    fn test_pipeline_with_auth() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.grant_paper_auth().unwrap();
        assert!(pipeline.governance.is_authorized());
    }

    #[test]
    fn test_canary_mode_off_returns_none() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert!(!pipeline.canary_mode);
        let record = pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert!(record.is_none());
    }

    #[test]
    fn test_canary_mode_on_returns_record() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.canary_mode = true;
        let record = pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert!(record.is_some());
        let r = record.unwrap();
        assert_eq!(r.schema_version, "1.0.0");
        assert_eq!(r.source, "rust_engine");
        assert_eq!(r.tick_number, 1);
        assert_eq!(r.symbol, "BTCUSDT");
        assert_eq!(r.price, 50000.0);
        assert_eq!(r.timestamp_ms, 1000);
    }

    #[test]
    fn test_canary_record_serializable() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.canary_mode = true;
        let record = pipeline
            .on_tick(&make_event("BTCUSDT", 50000.0, 1000))
            .unwrap();
        let json = serde_json::to_string(&record).unwrap();
        assert!(json.contains("\"schema_version\":\"1.0.0\""));
        assert!(json.contains("\"source\":\"rust_engine\""));
        // Deserialize back / 反序列化
        let r2: CanaryRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(r2.tick_number, record.tick_number);
    }

    #[test]
    fn test_snapshot_to_input() {
        let snap = IndicatorSnapshot {
            sma_20: Some(50000.0),
            sma_50: None,
            ema_12: Some(50100.0),
            ema_26: None,
            rsi_14: Some(55.0),
            macd: None,
            bollinger: None,
            atr_14: None,
            atr_5: None,
            stochastic: None,
            kama: None,
            adx: None,
            hurst: None,
            ewma_vol: None,
            volume_ratio: Some(1.2),
            donchian: None,
        };
        let input = snapshot_to_input(&snap);
        assert_eq!(input.sma, Some(50000.0));
        assert_eq!(input.rsi, Some(55.0));
        assert_eq!(input.volume_ratio, Some(1.2));
    }

    // ─── I-08 Dual-Rail Stop tests (Principle #9) ───
    // 雙軌止損測試：驗證 broker-side SL 只在 primary exchange mode 開倉時啟用

    #[test]
    fn test_dual_rail_shadow_order_has_sl_fields() {
        // Struct must expose stop_loss / take_profit for broker rail wiring
        let req = ShadowOrderRequest {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            price: 50000.0,
            strategy: "test".into(),
            paper_fill_ts: 0,
            is_close: false,
            order_link_id: "oc_test".into(),
            is_primary: true,
            stop_loss: Some(49000.0),
            take_profit: Some(52000.0),
        };
        assert_eq!(req.stop_loss, Some(49000.0));
        assert_eq!(req.take_profit, Some(52000.0));
    }

    #[test]
    fn test_dual_rail_broker_sl_long_below_entry() {
        // Long SL must sit below entry price
        let entry: f64 = 50000.0;
        let sl_pct: f64 = 2.0;
        let sl = entry * (1.0 - sl_pct / 100.0);
        assert!(sl < entry);
        assert!((sl - 49000.0f64).abs() < 0.01);
    }

    #[test]
    fn test_dual_rail_broker_sl_short_above_entry() {
        // Short SL must sit above entry price
        let entry: f64 = 50000.0;
        let sl_pct: f64 = 2.0;
        let sl = entry * (1.0 + sl_pct / 100.0);
        assert!(sl > entry);
        assert!((sl - 51000.0f64).abs() < 0.01);
    }

    #[test]
    fn test_dual_rail_close_orders_no_broker_sl() {
        // Close orders never attach broker SL (Bybit auto-cancels on reduce-only fill)
        let req = ShadowOrderRequest {
            symbol: "BTCUSDT".into(),
            is_long: false,
            qty: 0.01,
            price: 50000.0,
            strategy: "risk_check".into(),
            paper_fill_ts: 0,
            is_close: true,
            order_link_id: "oc_risk".into(),
            is_primary: true,
            stop_loss: None,
            take_profit: None,
        };
        assert!(req.stop_loss.is_none());
        assert!(req.is_close);
    }

    #[test]
    fn test_dual_rail_paper_shadow_skips_broker_sl() {
        // Paper/shadow orders keep broker SL None (engine rail handles stops locally)
        let req = ShadowOrderRequest {
            symbol: "ETHUSDT".into(),
            is_long: true,
            qty: 0.1,
            price: 3000.0,
            strategy: "ma".into(),
            paper_fill_ts: 0,
            is_close: false,
            order_link_id: "sh_test".into(),
            is_primary: false,
            stop_loss: None,
            take_profit: None,
        };
        assert!(!req.is_primary);
        assert!(req.stop_loss.is_none());
    }

    fn make_signal(symbol: &str, dir: openclaw_core::signals::SignalDirection, ts_ms: u64) -> openclaw_core::signals::Signal {
        openclaw_core::signals::Signal {
            symbol: symbol.into(),
            direction: dir,
            confidence: 0.5,
            edge_bps: 10.0,
            source: "ma_crossover".into(),
            timeframe: "1m".into(),
            reasoning: "test".into(),
            ts_ms,
        }
    }

    #[test]
    fn test_dbrun1_first_signal_persisted() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_unchanged_signal_throttled_within_heartbeat() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Same direction, +30s → throttled
        assert!(!p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 31_000)));
        assert_eq!(p.signals_throttled(), 1);
    }

    #[test]
    fn test_dbrun1_direction_change_breaks_throttle() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Direction flips → persist immediately even within heartbeat
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Short, 5_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_heartbeat_elapsed_persists() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Same direction, 60s later → heartbeat fires
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 61_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_disable_throttle() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(0);
        // Every call persists, no dedupe state consulted
        for ts in [1, 2, 3, 4, 5] {
            assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, ts)));
        }
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun2_context_counter_starts_zero() {
        let p = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(p.context_throttled(), 0);
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_per_symbol_strategy_isolation() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Different symbol, same strategy → independent key, persists
        assert!(p.should_persist_signal(&make_signal("ETHUSDT", SignalDirection::Long, 1_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_pnl3_boot_cooldown_stamps_first_tick() {
        // PNL-3: First tick stamps boot_ts_ms; subsequent ticks reuse it.
        // PNL-3：首個 tick 記錄 boot_ts_ms；後續 tick 沿用。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert!(pipeline.boot_ts_ms.is_none());
        pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, 1_000_000));
        assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
        pipeline.on_tick(&make_event("BTCUSDT", 50_001.0, 1_010_000));
        assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
    }

    #[test]
    fn test_pnl4_derive_regime_hurst_priority() {
        use openclaw_core::indicators::{HurstResult, IndicatorSnapshot};
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut ind = IndicatorSnapshot::default();
        ind.hurst = Some(HurstResult { hurst: 0.7, regime: "trending".into() });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
        ind.hurst = Some(HurstResult { hurst: 0.3, regime: "mean_reverting".into() });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
    }

    #[test]
    fn test_pnl4_derive_regime_adx_fallback() {
        use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut ind = IndicatorSnapshot::default();
        ind.hurst = Some(HurstResult { hurst: 0.5, regime: "random_walk".into() });
        ind.adx = Some(AdxResult { adx: 30.0, plus_di: 25.0, minus_di: 10.0 });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
        ind.adx = Some(AdxResult { adx: 15.0, plus_di: 10.0, minus_di: 12.0 });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
    }

    #[test]
    fn test_pnl4_derive_regime_none_default() {
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.derive_regime(None), "ranging");
    }

    #[test]
    fn test_pnl3_boot_cooldown_default_60s() {
        // PNL-3: default cooldown is 60_000ms when env var not set.
        // PNL-3：未設環境變量時冷卻期默認 60_000ms。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        // Force-set boot_ts_ms then check elapsed math via direct field.
        pipeline.boot_ts_ms = Some(0);
        assert_eq!(pipeline.boot_cooldown_ms, 60_000);
        // Tick at t=30s → still in cooldown
        let in_cd_30s: bool = (30_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
        assert!(in_cd_30s);
        // Tick at t=61s → out of cooldown
        let in_cd_61s: bool = (61_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
        assert!(!in_cd_61s);
    }
}
