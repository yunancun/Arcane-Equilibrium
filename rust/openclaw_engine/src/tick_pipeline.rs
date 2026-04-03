//! Tick Pipeline — on_tick 4-step orchestration (R04-1).
//! Tick 管線 — on_tick 4 步編排。
//!
//! WS event → kline aggregate → indicator compute → signal evaluate → strategy dispatch.
//! Tick actor sole-owner: no locks [V3-PA-1].

use openclaw_core::{
    governance_core::GovernanceCore,
    indicators::{IndicatorEngine, IndicatorSnapshot},
    klines::{KlineManager, OhlcvArrays},
    signals::{IndicatorInput, Signal, SignalEngine},
};
use openclaw_types::PriceEvent;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::{debug, info};

use crate::intent_processor::IntentProcessor;
use crate::orchestrator::Orchestrator;
use crate::paper_state::PaperState;

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
}

impl TickPipeline {
    pub fn new(symbols: &[&str]) -> Self {
        Self {
            kline_manager: KlineManager::new(symbols, None, None),
            signal_engine: SignalEngine::new(),
            orchestrator: Orchestrator::new(),
            intent_processor: IntentProcessor::new(),
            governance: GovernanceCore::new(),
            paper_state: PaperState::new(10_000.0),
            stats: TickStats::default(),
            latest_prices: HashMap::new(),
        }
    }

    /// Process a single price event through the full pipeline.
    /// 通過完整管線處理單個價格事件。
    pub fn on_tick(&mut self, event: &PriceEvent) {
        self.stats.total_ticks += 1;
        self.stats.last_tick_ms = event.ts_ms;
        self.latest_prices.insert(event.symbol.clone(), event.last_price);
        self.paper_state.set_latest_price(&event.symbol, event.last_price);

        // Step 1: Kline aggregation
        self.kline_manager.on_tick(
            &event.symbol, event.last_price, event.ts_ms,
            event.volume_24h, 0.0,
        );

        // Step 2: Compute indicators (need enough 1m bars)
        let indicators = self.compute_indicators(&event.symbol);

        // Step 3: Signal evaluation
        let signals = if let Some(ref ind) = indicators {
            let input = snapshot_to_input(ind);
            self.signal_engine.evaluate(&event.symbol, "1m", &input, event.ts_ms)
        } else {
            vec![]
        };

        // Step 4: Strategy dispatch
        let ctx = TickContext {
            symbol: event.symbol.clone(),
            price: event.last_price,
            timestamp_ms: event.ts_ms,
            indicators,
            signals,
            h0_allowed: true, // simplified — full H0 gate check in intent_processor
        };

        let intents = self.orchestrator.dispatch_tick(&ctx);

        // Step 5: Process intents
        if !intents.is_empty() && self.governance.is_authorized() {
            for intent in &intents {
                let result = self.intent_processor.process(intent, &self.governance, &self.paper_state);
                if result.submitted {
                    self.stats.total_intents += 1;
                    if let Some(fill) = result.fill {
                        self.paper_state.apply_fill(
                            &intent.symbol, intent.is_long, fill.fill_qty,
                            fill.fill_price, fill.fee, event.ts_ms,
                        );
                        self.stats.total_fills += 1;
                    }
                }
            }
        }

        // Step 6: Check stops
        let triggers = self.paper_state.check_stops(event.last_price, event.ts_ms);
        for (symbol, trigger) in &triggers {
            debug!(symbol = %symbol, reason = %trigger.reason, "stop triggered");
            self.paper_state.close_position(symbol, event.last_price, event.ts_ms);
            self.stats.total_stops += 1;
        }

        if self.stats.total_ticks % 1000 == 0 {
            info!(ticks = self.stats.total_ticks, fills = self.stats.total_fills, "tick stats");
        }
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
        atr_percent: snap.atr.as_ref().map(|a| a.atr_percent),
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
    fn test_snapshot_to_input() {
        let snap = IndicatorSnapshot {
            sma_20: Some(50000.0),
            ema_12: Some(50100.0),
            rsi_14: Some(55.0),
            macd: None, bollinger: None, atr: None,
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
