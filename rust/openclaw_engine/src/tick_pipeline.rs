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
    /// Update risk config at runtime (from GUI/Python/Agent → IPC → Rust).
    /// 運行時更新風控配置（從 GUI/Python/Agent → IPC → Rust）。
    UpdateRiskConfig {
        // StopConfig fields / 止損配置
        hard_stop_pct: Option<f64>,
        trailing_stop_pct: Option<Option<f64>>,  // Some(None)=disable, Some(Some(x))=set
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
    consecutive_losses: HashMap<String, u32>,
    /// RRC-1-C4: Session halted flag — set by HaltSession risk action, cleared by IPC Resume.
    /// RRC-1-C4：會話暫停標誌 — 由 HaltSession 風控動作設置，由 IPC Resume 清除。
    session_halted: bool,
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
        }
    }

    /// Set dynamic fee rate from API for more accurate paper trading cost.
    /// 設定 API 動態費率，提高紙盤交易成本精確度。
    pub fn set_fee_rate(&mut self, rate: f64) {
        self.intent_processor.set_fee_rate(rate);
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
    pub fn set_shadow_channel(&mut self, tx: tokio::sync::mpsc::UnboundedSender<ShadowOrderRequest>) {
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
    pub fn set_market_data_channel(&mut self, tx: tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>) {
        self.market_data_tx = Some(tx);
    }

    /// Phase 1: Set channel for dispatching feature snapshots to async PG writer.
    /// Phase 1：設定特徵快照派發到異步 PG 寫入器的通道。
    pub fn set_feature_channel(&mut self, tx: tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>) {
        self.feature_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching trading lifecycle events to PG writer.
    /// Phase 2a：設定交易生命週期事件派發通道。
    pub fn set_trading_channel(&mut self, tx: tokio::sync::mpsc::Sender<crate::database::TradingMsg>) {
        self.trading_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching decision context snapshots.
    /// Phase 2a：設定決策上下文快照派發通道。
    pub fn set_context_channel(&mut self, tx: tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>) {
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
        self.latest_prices.insert(event.symbol.clone(), event.last_price);
        self.paper_state.set_latest_price(&event.symbol, event.last_price);
        // RRC-1-B2: Reset daily start balance at UTC midnight for daily loss tracking.
        // RRC-1-B2：UTC 午夜重置每日起始餘額，用於日損追蹤。
        self.intent_processor.maybe_reset_daily_balance(
            self.paper_state.balance(), event.ts_ms,
        );
        // RRC-1-C1: Feed price to tracker for ATR computation + spike detection.
        // RRC-1-C1：餵入價格到追蹤器，用於 ATR 計算 + 尖峰偵測。
        self.price_tracker.record(&event.symbol, event.last_price, event.ts_ms);
        // Update per-symbol turnover for dynamic slippage (from ticker events)
        // 更新每交易對成交額用於動態滑點（來自 ticker 事件）
        if event.turnover_24h > 0.0 {
            self.paper_state.set_latest_turnover(&event.symbol, event.turnover_24h);

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
                    mark_price: 0.0,   // not available in PriceEvent yet
                    index_price: 0.0,  // not available in PriceEvent yet
                    best_bid: event.bid_price,
                    best_ask: event.ask_price,
                    bid_size: 0.0,     // not available in PriceEvent yet
                    ask_size: 0.0,     // not available in PriceEvent yet
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
                    self.adl_alerts.push_back((event.ts_ms, event.symbol.clone(), rank));
                    if self.adl_alerts.len() > 50 { self.adl_alerts.pop_front(); }
                    if rank >= 3 {
                        info!(
                            symbol = %event.symbol, rank = rank,
                            "⚠ ADL rank HIGH — consider reducing position / ADL 排名高，考慮減倉"
                        );
                    }
                }
            }
        }

        // Step 0: Fast track check — emergency actions before normal processing
        let ft_action = crate::fast_track::evaluate_fast_track(
            self.governance.risk.level,
            0.0, // price_drop_pct computed externally
            0.0, // margin_utilization computed externally
        );
        if ft_action == crate::fast_track::FastTrackAction::CloseAll {
            let symbols: Vec<String> = self.paper_state.positions().iter()
                .map(|p| p.symbol.clone()).collect();
            for sym in symbols {
                self.paper_state.close_position(&sym, event.last_price, event.ts_ms);
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
                self.paper_state.close_position(sym, event.last_price, event.ts_ms);
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
            &event.symbol, event.last_price, event.ts_ms,
            event.volume_24h, 0.0,
        );

        // Phase 1: Emit KlineClose for each closed bar to market writer (F-2 audit fix).
        // Phase 1：為每根已關閉 K 線發送 KlineClose 到市場寫入器（F-2 審計修復）。
        if let Some(ref tx) = self.market_data_tx {
            for (timeframe, bar) in &closed_bars {
                if tx.try_send(crate::database::MarketDataMsg::KlineClose {
                    symbol: event.symbol.clone(),
                    timeframe: timeframe.clone(),
                    bar: bar.clone(),
                }).is_err() {
                    self.market_tx_dropped += 1;
                }
            }
        }

        // Step 2: Compute indicators (need enough 1m bars)
        // 步驟 2：計算指標（需要足夠的 1 分鐘 K 線）
        let indicators = self.compute_indicators(&event.symbol);

        // Store latest indicators for IPC snapshot / 存儲最新指標供 IPC 快照使用
        if let Some(ref ind) = indicators {
            self.latest_indicators.insert(event.symbol.clone(), ind.clone());
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
                let pos_info = self.paper_state.get_position(sym).map(|p| (p.is_long, p.qty));
                debug!(symbol = %sym, reason = %trigger.reason, "stop (paused)");
                self.paper_state.close_position(sym, event.last_price, event.ts_ms);
                self.stats.total_stops += 1;
                if let Some((is_long, qty)) = pos_info {
                    self.dispatch_close_order(sym, is_long, qty, event, false);
                }
            }
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, indicators, vec![], vec![], tick_duration_us);
        }

        // Step 3: Signal evaluation
        let signals = if let Some(ref ind) = indicators {
            let input = snapshot_to_input(ind);
            self.signal_engine.evaluate(&event.symbol, "1m", &input, event.ts_ms)
        } else {
            vec![]
        };

        // Store recent signals for IPC snapshot (ring buffer, max 100)
        // 存儲最近信號供 IPC 快照使用（環形緩衝，最大 100）
        for sig in &signals {
            self.recent_signals.push_back(sig.clone());
            if self.recent_signals.len() > 100 { self.recent_signals.pop_front(); }

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

        // Phase 2a: Emit DecisionContextMsg on signal generation (one per tick with signals)
        if !signals.is_empty() {
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
                    } else { 0.0 },
                    regime_5m: ind.and_then(|i| i.hurst.as_ref()).map(|h| h.regime.clone()).unwrap_or_default(),
                    ind_5m_adx: ind.and_then(|i| i.adx.as_ref()).map(|a| a.adx).unwrap_or(0.0),
                    ind_5m_rsi: ind.and_then(|i| i.rsi_14).unwrap_or(50.0),
                    ind_5m_atr_14_pct: ind.and_then(|i| i.atr_14.as_ref()).map(|a| a.atr_percent).unwrap_or(0.0),
                    position_side: pos.map(|p| if p.is_long { "Long" } else { "Short" }).unwrap_or("None").into(),
                    position_qty: pos.map(|p| p.qty).unwrap_or(0.0),
                    total_equity: self.paper_state.balance(),
                    drawdown_pct: self.paper_state.drawdown_pct(),
                    indicators_snapshot: ind.map(|i| serde_json::to_value(i).unwrap_or_default()).unwrap_or_default(),
                    position_detail: pos.map(|p| serde_json::to_value(p).unwrap_or_default()).unwrap_or_default(),
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

        let mut intents: Vec<crate::intent_processor::OrderIntent> = Vec::new();
        for strategy in self.orchestrator.strategies_mut() {
            if !strategy.is_active() { continue; }
            let strategy_intents = strategy.on_tick(&ctx);
            debug_assert!(strategy_intents.len() <= 1,
                "Strategy {} emitted {} intents in one tick — rollback assumes max 1",
                strategy.name(), strategy_intents.len());
            for intent in &strategy_intents {
                if is_exchange_mode {
                    // ═══ EXCHANGE MODE: gates only, send order to exchange ═══
                    // ═══ 交易所模式：僅過門禁，發送訂單到交易所 ═══
                    let gate = self.intent_processor.process_gates_only(
                        intent, &self.governance, &self.paper_state,
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
                                side: if intent.is_long { "Buy".into() } else { "Sell".into() },
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
                            } else { gate.approved_qty }
                        } else { gate.approved_qty };

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
                        if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }

                        // Dispatch to exchange / 派發到交易所
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
                            });
                        }
                    } else if let Some(ref reason) = gate.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: format!("rejected:{}", reason),
                        });
                        if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    }
                } else {
                    // ═══ PAPER_ONLY MODE: simulate fill locally + optional shadow order ═══
                    // ═══ 紙盤模式：本地模擬成交 + 可選影子訂單 ═══
                    let result = self.intent_processor.process(intent, &self.governance, &self.paper_state);
                    if result.submitted {
                        self.stats.total_intents += 1;
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: "submitted".into(),
                        });
                        if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }

                        // Phase 3b fix: Emit Intent to trading_tx for PG persistence.
                        // Phase 3b 修復：發送 Intent 到 trading_tx 以持久化到 PG。
                        if let Some(ref tx) = self.trading_tx {
                            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                                intent_id: format!("intent-{}-{}", intent.symbol, event.ts_ms),
                                ts_ms: event.ts_ms,
                                signal_id: String::new(),
                                context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                                symbol: intent.symbol.clone(),
                                side: if intent.is_long { "Buy".into() } else { "Sell".into() },
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
                            self.paper_state.apply_fill(
                                &intent.symbol, intent.is_long, fill.fill_qty,
                                fill.fill_price, fill.fee, event.ts_ms,
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
                            if self.recent_fills.len() > 50 { self.recent_fills.pop_front(); }

                            if let Some(ref tx) = self.trading_tx {
                                let _ = tx.try_send(crate::database::TradingMsg::Fill {
                                    fill_id: format!("fill-{}-{}", intent.symbol, event.ts_ms),
                                    ts_ms: event.ts_ms,
                                    order_id: format!("order-{}-{}", intent.symbol, event.ts_ms),
                                    symbol: intent.symbol.clone(),
                                    side: if intent.is_long { "Buy".into() } else { "Sell".into() },
                                    qty: fill.fill_qty,
                                    price: fill.fill_price,
                                    fee: fill.fee,
                                    realized_pnl: 0.0,
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
                                    order_link_id: format!("sh_{}_{}", event.ts_ms, self.exchange_seq),
                                    is_primary: false,
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
                        if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    }
                }
            }
            intents.extend(strategy_intents);
        }

        // Step 6: Position risk checks — 9-check (RRC-1-C2, replaces basic check_stops).
        // 步驟 6：持倉風控 9 項檢查（RRC-1-C2，替代基本止損）。
        self.paper_state.update_best_prices();
        let session_drawdown = self.paper_state.drawdown_pct();
        let daily_loss = self.intent_processor.daily_loss_pct_pub(self.paper_state.balance());
        let risk_config = self.intent_processor.risk_config().clone();
        let positions: Vec<(String, bool, f64, f64, f64, u64)> = self.paper_state.positions()
            .iter()
            .map(|p| {
                let price = self.latest_prices.get(&p.symbol).copied().unwrap_or(p.entry_price);
                let pnl_pct = if p.is_long {
                    (price - p.entry_price) / p.entry_price * 100.0
                } else {
                    (p.entry_price - price) / p.entry_price * 100.0
                };
                let peak_pnl_pct = if p.is_long {
                    (p.best_price - p.entry_price) / p.entry_price * 100.0
                } else {
                    (p.entry_price - p.best_price) / p.entry_price * 100.0
                };
                (p.symbol.clone(), p.is_long, p.qty, pnl_pct, peak_pnl_pct, p.entry_ts_ms)
            })
            .collect();

        for (symbol, is_long, qty, pnl_pct, peak_pnl_pct, entry_ts_ms) in &positions {
            let holding_hours = (event.ts_ms.saturating_sub(*entry_ts_ms)) as f64 / 3_600_000.0;
            let atr_pct = self.price_tracker.compute_atr_pct(symbol);
            let consec = self.consecutive_losses.get(symbol).copied().unwrap_or(0);
            let action = check_position_on_tick(
                *pnl_pct, *peak_pnl_pct, holding_hours,
                0.0,       // cost_ratio — placeholder, Phase D wiring
                "ranging", // regime — placeholder, Phase D wiring
                atr_pct, symbol, *entry_ts_ms, consec,
                daily_loss, session_drawdown, &risk_config,
            );
            match action {
                RiskAction::Hold => {} // no action / 無動作
                RiskAction::ClosePosition(reason) => {
                    if is_exchange_mode {
                        if self.pending_close_symbols.contains(symbol) { continue; }
                        warn!(symbol = %symbol, reason = %reason, "risk close → exchange / 風控平倉 → 交易所");
                        self.dispatch_close_order(symbol, *is_long, *qty, event, true);
                    } else {
                        debug!(symbol = %symbol, reason = %reason, "risk close / 風控平倉");
                        if *pnl_pct < 0.0 {
                            *self.consecutive_losses.entry(symbol.clone()).or_insert(0) += 1;
                        } else {
                            self.consecutive_losses.remove(symbol);
                        }
                        self.paper_state.close_position(symbol, event.last_price, event.ts_ms);
                        self.stats.total_stops += 1;
                        self.dispatch_close_order(symbol, *is_long, *qty, event, false);
                    }
                }
                RiskAction::HaltSession(reason) => {
                    // RRC-1-C4: Circuit breaker — halt + close all / 熔斷 — 暫停+全部平倉
                    warn!(reason = %reason, "SESSION HALTED / 會話暫停");
                    self.session_halted = true;
                    self.paper_paused = true;
                    let all_pos: Vec<(String, bool, f64)> = self.paper_state.positions().iter()
                        .map(|p| (p.symbol.clone(), p.is_long, p.qty)).collect();
                    for (sym, il, q) in &all_pos {
                        let px = self.latest_prices.get(sym).copied().unwrap_or(event.last_price);
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
                    self.h0_gate.update_risk(openclaw_types::H0GateRiskSnapshot {
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
            info!(ticks = self.stats.total_ticks, fills = self.stats.total_fills, "tick stats");
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
        self.paper_state.apply_fill(symbol, is_long, qty, fill_price, fee, ts_ms);
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
        if self.recent_fills.len() > 50 { self.recent_fills.pop_front(); }

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
                realized_pnl: 0.0,
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
        &mut self, symbol: &str, is_long: bool, qty: f64,
        event: &PriceEvent, is_primary: bool,
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
        if ohlcv.close.len() < 30 { return None; }
        Some(IndicatorEngine::compute_all(&ohlcv.high, &ohlcv.low, &ohlcv.close, &ohlcv.volume))
    }

    pub fn grant_paper_auth(&mut self) -> Result<(), String> {
        self.governance.grant_paper_authorization(None).map(|_| ()).map_err(|e| e.to_string())
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
                if !bars.is_empty() { klines.insert(sym.clone(), bars); }
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
            daily_loss_pct: self.intent_processor.daily_loss_pct_pub(self.paper_state.balance()),
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
    PipelineStatus, CanaryRecord, StrategyInfo,
    TimestampedIntent, TimestampedFill, PipelineSnapshot,
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
        let record = pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000)).unwrap();
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
            macd: None, bollinger: None, atr_14: None, atr_5: None,
            stochastic: None, kama: None, adx: None,
            hurst: None, ewma_vol: None, volume_ratio: Some(1.2),
            donchian: None,
        };
        let input = snapshot_to_input(&snap);
        assert_eq!(input.sma, Some(50000.0));
        assert_eq!(input.rsi, Some(55.0));
        assert_eq!(input.volume_ratio, Some(1.2));
    }
}
