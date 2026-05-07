//! Replay-safe TickContext input builder for REF-21 full-chain replay.
//!
//! This module reconstructs the strategy input surface from fixture data only:
//! rolling OHLCV indicators, signal-engine outputs, funding/index/OI fields
//! carried by local recorder overlays, tick size from V058 fixture metadata,
//! and rolling 24h turnover for slippage tiers. It deliberately has no DB,
//! network, IPC, exchange, live-auth, or production singleton imports.

use std::collections::{HashMap, VecDeque};

use openclaw_core::{
    indicators::{IndicatorEngine, IndicatorSnapshot, DEFAULT_EWMA_VOL_LAMBDA},
    signals::{IndicatorInput, Signal, SignalEngine},
};

use crate::replay::fixture_loader::MarketEvent;

const INDICATOR_WINDOW: usize = 100;
const MIN_INDICATOR_BARS: usize = 30;
const TURNOVER_LOOKBACK_MS: i64 = 24 * 60 * 60 * 1000;
const MIN_TURNOVER_COVERAGE_MS: i64 = TURNOVER_LOOKBACK_MS - 60_000;

#[derive(Debug, Clone)]
pub struct ReplayTickInputs {
    pub indicators: Option<IndicatorSnapshot>,
    pub signals: Vec<Signal>,
    pub h0_allowed: bool,
    pub funding_rate: Option<f64>,
    pub index_price: Option<f64>,
    pub open_interest: Option<f64>,
    pub tick_size: Option<f64>,
    pub turnover_24h: Option<f64>,
}

#[derive(Debug, Default)]
struct SymbolHistory {
    high: VecDeque<f64>,
    low: VecDeque<f64>,
    close: VecDeque<f64>,
    volume: VecDeque<f64>,
    turnover_window: VecDeque<(i64, f64)>,
    turnover_sum: f64,
}

impl SymbolHistory {
    fn push(&mut self, event: &MarketEvent) {
        push_capped(&mut self.high, event.high.max(0.0), INDICATOR_WINDOW);
        push_capped(&mut self.low, event.low.max(0.0), INDICATOR_WINDOW);
        push_capped(&mut self.close, event.close.max(0.0), INDICATOR_WINDOW);
        push_capped(&mut self.volume, event.volume.max(0.0), INDICATOR_WINDOW);

        let turnover = event
            .turnover
            .unwrap_or_else(|| event.close.max(0.0) * event.volume.max(0.0))
            .max(0.0);
        self.turnover_window.push_back((event.ts_ms, turnover));
        self.turnover_sum += turnover;
        let cutoff = event.ts_ms.saturating_sub(TURNOVER_LOOKBACK_MS);
        while let Some((ts, value)) = self.turnover_window.front().copied() {
            if ts >= cutoff {
                break;
            }
            self.turnover_window.pop_front();
            self.turnover_sum = (self.turnover_sum - value).max(0.0);
        }
    }

    fn computed_indicators(&self) -> Option<IndicatorSnapshot> {
        if self.close.len() < MIN_INDICATOR_BARS {
            return None;
        }
        let high = self.high.iter().copied().collect::<Vec<_>>();
        let low = self.low.iter().copied().collect::<Vec<_>>();
        let close = self.close.iter().copied().collect::<Vec<_>>();
        let volume = self.volume.iter().copied().collect::<Vec<_>>();
        Some(IndicatorEngine::compute_all_with_lambda(
            &high,
            &low,
            &close,
            &volume,
            DEFAULT_EWMA_VOL_LAMBDA,
        ))
    }

    fn derived_turnover_24h(&self) -> Option<f64> {
        let oldest_ts = self.turnover_window.front().map(|(ts, _)| *ts)?;
        let newest_ts = self.turnover_window.back().map(|(ts, _)| *ts)?;
        if newest_ts.saturating_sub(oldest_ts) < MIN_TURNOVER_COVERAGE_MS {
            return None;
        }
        positive_finite(self.turnover_sum)
    }
}

pub struct ReplayContextBuilder {
    histories: HashMap<String, SymbolHistory>,
    signal_engine: SignalEngine,
    timeframe: &'static str,
}

impl Default for ReplayContextBuilder {
    fn default() -> Self {
        Self::new()
    }
}

impl ReplayContextBuilder {
    pub fn new() -> Self {
        Self {
            histories: HashMap::new(),
            signal_engine: SignalEngine::new(),
            timeframe: "1m",
        }
    }

    pub fn update(&mut self, event: &MarketEvent) -> ReplayTickInputs {
        let symbol = event.symbol.to_uppercase();
        let history = self.histories.entry(symbol.clone()).or_default();
        history.push(event);

        let indicators = event
            .indicators
            .clone()
            .or_else(|| history.computed_indicators());
        let signals = if !event.signals.is_empty() {
            event.signals.clone()
        } else if let Some(ref snapshot) = indicators {
            self.signal_engine.evaluate(
                &symbol,
                self.timeframe,
                &snapshot_to_input(snapshot),
                event.ts_ms.max(0) as u64,
            )
        } else {
            Vec::new()
        };

        ReplayTickInputs {
            indicators,
            signals,
            h0_allowed: event.h0_allowed.unwrap_or(true),
            funding_rate: finite_opt(event.funding_rate),
            index_price: positive_finite_opt(event.index_price),
            open_interest: positive_finite_opt(event.open_interest),
            tick_size: positive_finite_opt(event.tick_size),
            turnover_24h: positive_finite_opt(event.turnover_24h)
                .or_else(|| history.derived_turnover_24h()),
        }
    }
}

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

fn push_capped(values: &mut VecDeque<f64>, value: f64, cap: usize) {
    values.push_back(value);
    while values.len() > cap {
        values.pop_front();
    }
}

fn positive_finite(value: f64) -> Option<f64> {
    if value.is_finite() && value > 0.0 {
        Some(value)
    } else {
        None
    }
}

fn positive_finite_opt(value: Option<f64>) -> Option<f64> {
    value.and_then(positive_finite)
}

fn finite_opt(value: Option<f64>) -> Option<f64> {
    value.filter(|v| v.is_finite())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn event(ts_ms: i64, close: f64) -> MarketEvent {
        MarketEvent {
            ts_ms,
            symbol: "BTCUSDT".to_string(),
            open: close,
            high: close + 1.0,
            low: close - 1.0,
            close,
            volume: 10.0,
            turnover: Some(close * 10.0),
            turnover_24h: None,
            best_bid: None,
            best_ask: None,
            bid_size: None,
            ask_size: None,
            bid_depth_5: None,
            ask_depth_5: None,
            spread_bps: None,
            microstructure_source: None,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            tick_size: None,
            h0_allowed: None,
            indicators: None,
            signals: Vec::new(),
        }
    }

    #[test]
    fn derives_indicators_after_warmup() {
        let mut builder = ReplayContextBuilder::new();
        let mut last = None;
        for i in 0..30 {
            last = Some(builder.update(&event(1_700_000_000_000 + i * 60_000, 100.0 + i as f64)));
        }
        let inputs = last.expect("warmup loop must produce inputs");
        assert!(inputs.indicators.is_some());
        assert!(
            inputs.turnover_24h.is_none(),
            "short windows must not masquerade as 24h turnover"
        );
    }

    #[test]
    fn derives_rolling_turnover_after_full_coverage() {
        let mut builder = ReplayContextBuilder::new();
        let mut last = None;
        for i in 0..=1440 {
            last = Some(builder.update(&event(1_700_000_000_000 + i * 60_000, 100.0 + i as f64)));
        }
        let inputs = last.expect("coverage loop must produce inputs");
        assert!(inputs.turnover_24h.unwrap() > 0.0);
    }

    #[test]
    fn fixture_fields_override_derived_inputs() {
        let mut builder = ReplayContextBuilder::new();
        let mut e = event(1_700_000_000_000, 100.0);
        e.turnover_24h = Some(5_000_000.0);
        e.funding_rate = Some(0.0002);
        e.index_price = Some(99.9);
        e.open_interest = Some(12345.0);
        e.tick_size = Some(0.1);
        e.h0_allowed = Some(false);

        let inputs = builder.update(&e);
        assert_eq!(inputs.turnover_24h, Some(5_000_000.0));
        assert_eq!(inputs.funding_rate, Some(0.0002));
        assert_eq!(inputs.index_price, Some(99.9));
        assert_eq!(inputs.open_interest, Some(12345.0));
        assert_eq!(inputs.tick_size, Some(0.1));
        assert!(!inputs.h0_allowed);
    }
}
