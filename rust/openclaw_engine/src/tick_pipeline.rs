//! Tick Pipeline — on_tick 4-step orchestration (R04-1).
//! Tick 管線 — on_tick 4 步編排。
//!
//! WS event → kline aggregate → indicator compute → signal evaluate → strategy dispatch.
//! Tick actor sole-owner: no locks [V3-PA-1].

use openclaw_core::{
    governance_core::GovernanceCore,
    indicators::{IndicatorEngine, IndicatorSnapshot},
    klines::KlineManager,
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
            // Still check stops for existing positions (protective)
            // 仍然檢查現有持倉的止損（保護性）
            let triggers = self.paper_state.check_stops(event.last_price, event.ts_ms);
            for (symbol, trigger) in &triggers {
                let pos_info = self.paper_state.get_position(symbol).map(|p| (p.is_long, p.qty));
                debug!(symbol = %symbol, reason = %trigger.reason, "stop triggered (paused)");
                self.paper_state.close_position(symbol, event.last_price, event.ts_ms);
                self.stats.total_stops += 1;
                if let (Some(ref tx), Some((is_long, qty))) = (&self.shadow_order_tx, pos_info) {
                    self.exchange_seq = self.exchange_seq.wrapping_add(1);
                    let _ = tx.send(ShadowOrderRequest {
                        symbol: symbol.clone(),
                        is_long: !is_long,
                        qty,
                        price: event.last_price,
                        strategy: "stop".into(),
                        paper_fill_ts: event.ts_ms,
                        is_close: true,
                        order_link_id: format!("sh_paused_{}_{}", event.ts_ms, self.exchange_seq),
                        is_primary: false,
                    });
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
            h0_allowed: true, // simplified — full H0 gate check in intent_processor
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

        // Step 6: Check stops
        // Exchange mode: send close order to exchange; paper_only: close locally + shadow
        let triggers = self.paper_state.check_stops(event.last_price, event.ts_ms);
        for (symbol, trigger) in &triggers {
            let pos_info = self.paper_state.get_position(symbol).map(|p| (p.is_long, p.qty));
            if is_exchange_mode {
                // P0-3 fix: Skip if we already have a pending close for this symbol
                // P0-3 修復：如果此交易對已有待處理平倉訂單則跳過
                if self.pending_close_symbols.contains(symbol) {
                    continue;
                }
                // Exchange mode: send close order, don't close locally until confirmed
                warn!(symbol = %symbol, reason = %trigger.reason,
                    "stop triggered in exchange mode — sending close order");
                if let (Some(ref tx), Some((is_long, qty))) = (&self.shadow_order_tx, pos_info) {
                    self.exchange_seq = self.exchange_seq.wrapping_add(1);
                    let _ = tx.send(ShadowOrderRequest {
                        symbol: symbol.clone(),
                        is_long: !is_long,
                        qty,
                        price: event.last_price,
                        strategy: "stop".into(),
                        paper_fill_ts: event.ts_ms,
                        is_close: true,
                        order_link_id: format!("oc_stop_{}_{}", event.ts_ms, self.exchange_seq),
                        is_primary: true,
                    });
                    self.pending_close_symbols.insert(symbol.clone());
                }
            } else {
                // Paper_only mode: close locally + shadow
                debug!(symbol = %symbol, reason = %trigger.reason, "stop triggered");
                self.paper_state.close_position(symbol, event.last_price, event.ts_ms);
                self.stats.total_stops += 1;
                if let (Some(ref tx), Some((is_long, qty))) = (&self.shadow_order_tx, pos_info) {
                    self.exchange_seq = self.exchange_seq.wrapping_add(1);
                    let _ = tx.send(ShadowOrderRequest {
                        symbol: symbol.clone(),
                        is_long: !is_long,
                        qty,
                        price: event.last_price,
                        strategy: "stop".into(),
                        paper_fill_ts: event.ts_ms,
                        is_close: true,
                        order_link_id: format!("sh_{}_{}", event.ts_ms, self.exchange_seq),
                        is_primary: false,
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

    /// Create a full snapshot for IPC / persistence (R06-A).
    /// 創建完整快照供 IPC / 持久化使用。
    pub fn snapshot(&self) -> PipelineSnapshot {
        // Collect strategy info from orchestrator / 從調度器收集策略信息
        let strategies: Vec<StrategyInfo> = self.orchestrator.strategy_infos();

        // Collect latest klines per symbol (1m only, up to 100 bars)
        // 收集每交易對最新 K 線（僅 1m，最多 100 根）
        let mut klines: HashMap<String, Vec<openclaw_core::klines::KlineBar>> = HashMap::new();
        for symbol in self.kline_manager.symbols() {
            if let Some(buf) = self.kline_manager.get_buffer(symbol, "1m") {
                let bars = buf.latest_cloned(100);
                if !bars.is_empty() {
                    klines.insert(symbol.clone(), bars);
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineStatus {
    pub stats: TickStats,
    pub governance: openclaw_core::governance_core::GovernanceStatus,
    pub positions: usize,
    pub balance: f64,
    pub symbols_tracked: usize,
}

/// Per-tick canary record for Rust vs Python comparison (R07-2).
/// 每 tick 灰度記錄，用於 Rust 與 Python 比較。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanaryRecord {
    pub schema_version: String,
    pub source: String,
    pub tick_number: u64,
    pub timestamp_ms: u64,
    pub symbol: String,
    pub price: f64,
    pub indicators: Option<IndicatorSnapshot>,
    pub signals: Vec<Signal>,
    pub order_intents: Vec<crate::intent_processor::OrderIntent>,
    pub paper_state: crate::paper_state::PaperStateSnapshot,
    pub stats: TickStats,
    /// Per-tick processing latency in microseconds (for Go/No-Go P50 < 50μs check).
    /// 每 tick 處理延遲（微秒），用於 Go/No-Go P50 < 50μs 驗證。
    pub tick_duration_us: u64,
}

/// Strategy status info for IPC snapshot.
/// 策略狀態信息供 IPC 快照使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategyInfo {
    /// Strategy name / 策略名稱
    pub name: String,
    /// Whether the strategy is currently active / 策略是否當前活躍
    pub active: bool,
}

/// A timestamped order intent for IPC ring buffer.
/// 帶時間戳的交易意圖，供 IPC 環形緩衝使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimestampedIntent {
    /// Event timestamp in milliseconds / 事件時間戳（毫秒）
    pub timestamp_ms: u64,
    /// The original order intent / 原始交易意圖
    pub intent: crate::intent_processor::OrderIntent,
    /// Result: "submitted" or "rejected:<reason>" / 結果："submitted" 或 "rejected:<原因>"
    pub result: String,
}

/// A timestamped fill record for IPC ring buffer.
/// 帶時間戳的成交記錄，供 IPC 環形緩衝使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimestampedFill {
    /// Event timestamp in milliseconds / 事件時間戳（毫秒）
    pub timestamp_ms: u64,
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Long or short direction / 多空方向
    pub is_long: bool,
    /// Fill quantity / 成交數量
    pub qty: f64,
    /// Fill price / 成交價格
    pub price: f64,
    /// Fee charged / 手續費
    pub fee: f64,
    /// Strategy that generated this fill / 產生此成交的策略
    pub strategy: String,
}

/// Full pipeline snapshot for IPC consumers (R06-A).
/// 完整管線快照供 IPC 消費者使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineSnapshot {
    /// Paper trading state / 紙盤交易狀態
    pub paper_state: crate::paper_state::PaperStateSnapshot,
    /// Latest per-symbol prices / 每交易對最新價格
    pub latest_prices: HashMap<String, f64>,
    /// Tick statistics / Tick 統計
    pub stats: TickStats,
    /// Data source discriminator / 數據源標識
    pub source: String,
    /// Paper trading paused flag / 紙盤交易暫停標誌
    #[serde(default)]
    pub paper_paused: bool,
    /// EXT-1: Current trading mode / 當前交易模式
    #[serde(default)]
    pub trading_mode: crate::config::TradingMode,
    /// Per-symbol latest indicator values / 每交易對最新指標值
    pub indicators: HashMap<String, IndicatorSnapshot>,
    /// Recent signals (last 100) / 最近信號（最近 100 個）
    pub signals: Vec<Signal>,
    /// Strategy status list / 策略狀態列表
    pub strategies: Vec<StrategyInfo>,
    /// Recent order intents (last 50) / 最近交易意圖（最近 50 個）
    pub recent_intents: Vec<TimestampedIntent>,
    /// Recent fills (last 50) / 最近成交記錄（最近 50 個）
    pub recent_fills: Vec<TimestampedFill>,
    /// Per-symbol latest completed klines (up to 100 bars, 1m only).
    /// 每交易對最新已完成 K 線（最多 100 根，僅 1m）。
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub klines: HashMap<String, Vec<openclaw_core::klines::KlineBar>>,
}

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
