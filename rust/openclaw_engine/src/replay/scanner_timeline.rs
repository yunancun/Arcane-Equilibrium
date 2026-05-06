//! Replay-safe scanner timeline reconstruction for REF-21 full-chain replay.
//!
//! This module reuses the scanner's pure scoring functions against fixture
//! OHLCV rows. It does not import live scanner runners, Bybit clients, DB
//! writers, IPC, or production singletons.

use std::collections::{HashMap, HashSet};

use crate::edge_estimates::EdgeEstimates;
use crate::market_data_client::types::TickerInfo;
use crate::replay::fixture_loader::MarketEvent;
use crate::scanner::config::ScannerConfig;
use crate::scanner::registry::SymbolRegistry;
use crate::scanner::scorer::{apply_correlation_filter, score_ticker_with_policy_and_opportunity};
use crate::scanner::strategy_policy::ScannerStrategyPolicy;
use crate::scanner::types::{ScanResult, ScoredSymbol};

const DEFAULT_LOOKBACK_MS: u64 = 24 * 60 * 60 * 1000;
const MIN_PRICE: f64 = 1e-12;

/// REF-21 replay default scanner config. Live scanner defaults to 30 minutes;
/// full-chain replay needs a 60-second timeline to approximate seven days of
/// scanner observations in one run.
pub fn replay_default_scanner_config() -> ScannerConfig {
    let mut config = ScannerConfig::default();
    config.scheduling.scan_interval_secs = 60;
    config.scheduling.warmup_delay_secs = 0;
    config
}

#[derive(Debug)]
pub enum ReplayScannerTimelineError {
    EmptyEvents,
    InvalidConfig(String),
    InvalidEvent(String),
    NoScanCycles,
}

impl std::fmt::Display for ReplayScannerTimelineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::EmptyEvents => write!(f, "scanner timeline cannot build from empty events"),
            Self::InvalidConfig(reason) => write!(f, "scanner config invalid: {reason}"),
            Self::InvalidEvent(reason) => write!(f, "market event invalid: {reason}"),
            Self::NoScanCycles => write!(f, "scanner timeline produced no scan cycles"),
        }
    }
}

impl std::error::Error for ReplayScannerTimelineError {}

#[derive(Debug, Clone)]
pub struct ReplayScannerTimeline {
    cycles: Vec<ScanResult>,
    scan_interval_ms: u64,
    lookback_ms: u64,
}

impl ReplayScannerTimeline {
    pub fn new(
        events: &[MarketEvent],
        config: &ScannerConfig,
        estimates: &EdgeEstimates,
    ) -> Result<Self, ReplayScannerTimelineError> {
        if events.is_empty() {
            return Err(ReplayScannerTimelineError::EmptyEvents);
        }
        config
            .validate()
            .map_err(ReplayScannerTimelineError::InvalidConfig)?;
        let scan_interval_ms = config
            .scheduling
            .scan_interval_secs
            .checked_mul(1000)
            .filter(|v| *v > 0)
            .ok_or_else(|| {
                ReplayScannerTimelineError::InvalidConfig(
                    "scheduling.scan_interval_secs overflows ms or is zero".to_string(),
                )
            })?;
        let scan_interval_i64 = i64::try_from(scan_interval_ms).map_err(|_| {
            ReplayScannerTimelineError::InvalidConfig(
                "scheduling.scan_interval_secs exceeds i64 milliseconds".to_string(),
            )
        })?;
        let warmup_ms = config
            .scheduling
            .warmup_delay_secs
            .checked_mul(1000)
            .ok_or_else(|| {
                ReplayScannerTimelineError::InvalidConfig(
                    "scheduling.warmup_delay_secs overflows ms".to_string(),
                )
            })?;
        let warmup_i64 = i64::try_from(warmup_ms).map_err(|_| {
            ReplayScannerTimelineError::InvalidConfig(
                "scheduling.warmup_delay_secs exceeds i64 milliseconds".to_string(),
            )
        })?;

        let mut by_symbol: HashMap<String, Vec<MarketEvent>> = HashMap::new();
        let mut start_ts: Option<i64> = None;
        let mut end_ts: Option<i64> = None;
        for event in events {
            validate_event(event)?;
            start_ts = Some(start_ts.map_or(event.ts_ms, |ts| ts.min(event.ts_ms)));
            end_ts = Some(end_ts.map_or(event.ts_ms, |ts| ts.max(event.ts_ms)));
            by_symbol
                .entry(event.symbol.to_uppercase())
                .or_default()
                .push(event.clone());
        }
        for rows in by_symbol.values_mut() {
            rows.sort_by_key(|event| event.ts_ms);
        }

        let first_scan_ts = start_ts
            .unwrap_or_default()
            .checked_add(warmup_i64)
            .ok_or_else(|| {
                ReplayScannerTimelineError::InvalidConfig(
                    "first scan timestamp overflows i64".to_string(),
                )
            })?;
        let last_ts = end_ts.unwrap_or(first_scan_ts);
        if first_scan_ts > last_ts {
            return Err(ReplayScannerTimelineError::NoScanCycles);
        }

        let pinned = config
            .universe
            .pinned_symbols
            .iter()
            .map(|s| s.to_uppercase())
            .collect::<Vec<_>>();
        let registry = SymbolRegistry::new(pinned.clone(), pinned.clone());
        let strategy_policy = ScannerStrategyPolicy::default();
        let max_dynamic_slots = config.universe.max_symbols.saturating_sub(pinned.len());
        let open_positions = HashSet::new();
        let mut cycles = Vec::new();
        let mut scan_ts = first_scan_ts;

        while scan_ts <= last_ts {
            let tickers = build_ticker_snapshot(&by_symbol, scan_ts, DEFAULT_LOOKBACK_MS);
            let btc_change_pct = tickers
                .iter()
                .find(|ticker| ticker.symbol == "BTCUSDT")
                .map(|ticker| ticker.price_change_24h_pct * 100.0)
                .unwrap_or(0.0);
            let mut scored = Vec::new();
            let mut rejected_count = 0usize;
            for ticker in &tickers {
                if let Some(candidate) = score_ticker_with_policy_and_opportunity(
                    ticker,
                    btc_change_pct,
                    estimates,
                    &config.hard_filters,
                    &config.edge_routing,
                    &config.market_judgment,
                    &config.opportunity,
                    &strategy_policy,
                ) {
                    scored.push(candidate);
                } else {
                    rejected_count += 1;
                }
            }
            scored.sort_by(|a, b| {
                b.final_score
                    .partial_cmp(&a.final_score)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| a.symbol.cmp(&b.symbol))
            });
            let selected = apply_correlation_filter(
                scored.clone(),
                &pinned,
                max_dynamic_slots,
                &config.correlation,
            );
            let (added, removed) = registry.apply_scan_result(
                &selected,
                scan_ts.max(0) as u64,
                &config.anti_churn,
                &open_positions,
                max_dynamic_slots,
            );
            let active_symbols = registry.snapshot();
            let candidates = active_candidates(&active_symbols, &scored);
            let idx = cycles.len();
            cycles.push(ScanResult {
                scan_ts_ms: scan_ts.max(0) as u64,
                scan_id: format!("replay_scan_{idx:06}_{scan_ts}"),
                active_symbols,
                added,
                removed,
                candidates,
                opportunity_decays: Vec::new(),
                rejected_count,
                scan_duration_ms: 0,
            });

            let Some(next_ts) = scan_ts.checked_add(scan_interval_i64) else {
                break;
            };
            scan_ts = next_ts;
        }

        if cycles.is_empty() {
            return Err(ReplayScannerTimelineError::NoScanCycles);
        }
        Ok(Self {
            cycles,
            scan_interval_ms,
            lookback_ms: DEFAULT_LOOKBACK_MS,
        })
    }

    pub fn from_scan_results(
        scan_interval_ms: u64,
        cycles: Vec<ScanResult>,
    ) -> Result<Self, ReplayScannerTimelineError> {
        if scan_interval_ms == 0 {
            return Err(ReplayScannerTimelineError::InvalidConfig(
                "scan_interval_ms must be > 0".to_string(),
            ));
        }
        if cycles.is_empty() {
            return Err(ReplayScannerTimelineError::NoScanCycles);
        }
        Ok(Self {
            cycles,
            scan_interval_ms,
            lookback_ms: DEFAULT_LOOKBACK_MS,
        })
    }

    pub fn len(&self) -> usize {
        self.cycles.len()
    }

    pub fn scan_interval_ms(&self) -> u64 {
        self.scan_interval_ms
    }

    pub fn lookback_ms(&self) -> u64 {
        self.lookback_ms
    }

    pub fn latest_cycle_at(&self, ts_ms: i64) -> Option<&ScanResult> {
        let ts = ts_ms.max(0) as u64;
        match self
            .cycles
            .binary_search_by_key(&ts, |cycle| cycle.scan_ts_ms)
        {
            Ok(idx) => self.cycles.get(idx),
            Err(0) => None,
            Err(idx) => self.cycles.get(idx - 1),
        }
    }

    pub fn is_active_at(&self, symbol: &str, ts_ms: i64) -> bool {
        let symbol = symbol.to_uppercase();
        self.latest_cycle_at(ts_ms)
            .map(|cycle| cycle.active_symbols.iter().any(|s| s == &symbol))
            .unwrap_or(false)
    }
}

fn active_candidates(active_symbols: &[String], scored: &[ScoredSymbol]) -> Vec<ScoredSymbol> {
    let active = active_symbols.iter().collect::<HashSet<_>>();
    scored
        .iter()
        .filter(|candidate| active.contains(&candidate.symbol))
        .cloned()
        .collect()
}

fn validate_event(event: &MarketEvent) -> Result<(), ReplayScannerTimelineError> {
    if event.symbol.trim().is_empty() {
        return Err(ReplayScannerTimelineError::InvalidEvent(
            "symbol must not be empty".to_string(),
        ));
    }
    for (name, value) in [
        ("open", event.open),
        ("high", event.high),
        ("low", event.low),
        ("close", event.close),
        ("volume", event.volume),
    ] {
        if !value.is_finite() {
            return Err(ReplayScannerTimelineError::InvalidEvent(format!(
                "{} {} is not finite",
                event.symbol, name
            )));
        }
    }
    if let Some(turnover) = event.turnover {
        if !turnover.is_finite() || turnover < 0.0 {
            return Err(ReplayScannerTimelineError::InvalidEvent(format!(
                "{} turnover is invalid: {:?}",
                event.symbol, event.turnover
            )));
        }
    }
    if let (Some(best_bid), Some(best_ask)) = (event.best_bid, event.best_ask) {
        if !best_bid.is_finite()
            || !best_ask.is_finite()
            || best_bid <= 0.0
            || best_ask <= 0.0
            || best_bid > best_ask
        {
            return Err(ReplayScannerTimelineError::InvalidEvent(format!(
                "{} BBO is invalid: bid={:?} ask={:?}",
                event.symbol, event.best_bid, event.best_ask
            )));
        }
    }
    if event.close <= 0.0 || event.high < event.low {
        return Err(ReplayScannerTimelineError::InvalidEvent(format!(
            "{} has invalid OHLC close={} high={} low={}",
            event.symbol, event.close, event.high, event.low
        )));
    }
    Ok(())
}

fn build_ticker_snapshot(
    by_symbol: &HashMap<String, Vec<MarketEvent>>,
    scan_ts: i64,
    lookback_ms: u64,
) -> Vec<TickerInfo> {
    let lookback_start = scan_ts.saturating_sub(lookback_ms as i64);
    let mut tickers = Vec::with_capacity(by_symbol.len());
    for (symbol, rows) in by_symbol {
        let latest_idx = upper_bound_ts(rows, scan_ts);
        if latest_idx == 0 {
            continue;
        }
        let window_start_idx = lower_bound_ts(rows, lookback_start);
        let latest = &rows[latest_idx - 1];
        let window = &rows[window_start_idx..latest_idx];
        if window.is_empty() {
            continue;
        }
        let mut high = latest.high;
        let mut low = latest.low;
        let mut volume = 0.0;
        let mut turnover = 0.0;
        for event in window {
            high = high.max(event.high);
            low = low.min(event.low);
            volume += event.volume.max(0.0);
            turnover += event
                .turnover
                .unwrap_or_else(|| event.close.max(0.0) * event.volume.max(0.0))
                .max(0.0);
        }
        let prev_price = window
            .first()
            .map(|event| event.close)
            .unwrap_or(latest.close);
        let price_change_24h_pct = if prev_price > MIN_PRICE {
            (latest.close - prev_price) / prev_price
        } else {
            0.0
        };
        let synthetic_spread_half = 0.0001_f64;
        let bid1_price = latest
            .best_bid
            .filter(|bid| bid.is_finite() && *bid > MIN_PRICE)
            .unwrap_or_else(|| (latest.close * (1.0 - synthetic_spread_half)).max(MIN_PRICE));
        let ask1_price = latest
            .best_ask
            .filter(|ask| ask.is_finite() && *ask > MIN_PRICE && *ask >= bid1_price)
            .unwrap_or_else(|| (latest.close * (1.0 + synthetic_spread_half)).max(MIN_PRICE));
        tickers.push(TickerInfo {
            symbol: symbol.clone(),
            last_price: latest.close,
            bid1_price,
            ask1_price,
            volume_24h: volume,
            turnover_24h: turnover,
            high_price_24h: high,
            low_price_24h: low,
            prev_price_24h: prev_price,
            open_interest: 0.0,
            funding_rate: 0.0,
            next_funding_time: String::new(),
            price_change_24h_pct,
        });
    }
    tickers.sort_by(|a, b| a.symbol.cmp(&b.symbol));
    tickers
}

fn lower_bound_ts(rows: &[MarketEvent], ts: i64) -> usize {
    let mut left = 0usize;
    let mut right = rows.len();
    while left < right {
        let mid = left + (right - left) / 2;
        if rows[mid].ts_ms < ts {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}

fn upper_bound_ts(rows: &[MarketEvent], ts: i64) -> usize {
    let mut left = 0usize;
    let mut right = rows.len();
    while left < right {
        let mid = left + (right - left) / 2;
        if rows[mid].ts_ms <= ts {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}

#[cfg(test)]
mod tests {
    use super::*;

    fn event(symbol: &str, ts_ms: i64, close: f64, volume: f64) -> MarketEvent {
        MarketEvent {
            ts_ms,
            symbol: symbol.to_string(),
            open: close,
            high: close * 1.02,
            low: close * 0.98,
            close,
            volume,
            turnover: None,
            best_bid: None,
            best_ask: None,
            bid_size: None,
            ask_size: None,
            spread_bps: None,
            microstructure_source: None,
        }
    }

    #[test]
    fn builds_sixty_second_cycles_from_fixture_events() {
        let mut config = replay_default_scanner_config();
        config.hard_filters.min_turnover_24h_usdt = 0.0;
        config.universe.max_symbols = 3;
        config.universe.pinned_symbols = vec!["BTCUSDT".to_string()];
        config.anti_churn.min_hold_cycles = 0;
        let events = vec![
            event("BTCUSDT", 1_000, 100.0, 10.0),
            event("ETHUSDT", 1_000, 10.0, 100.0),
            event("BTCUSDT", 61_000, 102.0, 10.0),
            event("ETHUSDT", 61_000, 10.5, 100.0),
            event("BTCUSDT", 121_000, 104.0, 10.0),
            event("ETHUSDT", 121_000, 10.8, 100.0),
        ];

        let timeline = ReplayScannerTimeline::new(&events, &config, &EdgeEstimates::empty())
            .expect("timeline builds");

        assert_eq!(timeline.len(), 3);
        assert_eq!(timeline.scan_interval_ms(), 60_000);
        assert!(timeline.is_active_at("BTCUSDT", 121_000));
    }

    #[test]
    fn uses_fixture_turnover_when_present() {
        let mut high_turnover = event("SOLUSDT", 1_000, 10.0, 1.0);
        high_turnover.turnover = Some(12_000.0);
        let mut low_turnover = event("XRPUSDT", 1_000, 10.0, 1.0);
        low_turnover.turnover = Some(10.0);
        let mut by_symbol = std::collections::HashMap::new();
        by_symbol.insert("SOLUSDT".to_string(), vec![high_turnover]);
        by_symbol.insert("XRPUSDT".to_string(), vec![low_turnover]);

        let tickers = build_ticker_snapshot(&by_symbol, 1_000, DEFAULT_LOOKBACK_MS);
        let sol = tickers.iter().find(|ticker| ticker.symbol == "SOLUSDT").unwrap();
        let xrp = tickers.iter().find(|ticker| ticker.symbol == "XRPUSDT").unwrap();

        assert_eq!(sol.turnover_24h, 12_000.0);
        assert_eq!(xrp.turnover_24h, 10.0);
    }

    #[test]
    fn uses_fixture_bbo_when_present() {
        let mut event = event("BTCUSDT", 1_000, 100.0, 1.0);
        event.best_bid = Some(99.5);
        event.best_ask = Some(100.5);
        let mut by_symbol = std::collections::HashMap::new();
        by_symbol.insert("BTCUSDT".to_string(), vec![event]);

        let tickers = build_ticker_snapshot(&by_symbol, 1_000, DEFAULT_LOOKBACK_MS);
        let btc = tickers.iter().find(|ticker| ticker.symbol == "BTCUSDT").unwrap();

        assert_eq!(btc.bid1_price, 99.5);
        assert_eq!(btc.ask1_price, 100.5);
    }

    #[test]
    fn inactive_before_first_cycle_is_false() {
        let cycle = ScanResult {
            scan_ts_ms: 10_000,
            scan_id: "test".to_string(),
            active_symbols: vec!["ETHUSDT".to_string()],
            added: Vec::new(),
            removed: Vec::new(),
            candidates: Vec::new(),
            opportunity_decays: Vec::new(),
            rejected_count: 0,
            scan_duration_ms: 0,
        };
        let timeline = ReplayScannerTimeline::from_scan_results(60_000, vec![cycle]).unwrap();

        assert!(!timeline.is_active_at("ETHUSDT", 9_999));
        assert!(timeline.is_active_at("ethusdt", 10_000));
        assert!(!timeline.is_active_at("BTCUSDT", 10_000));
    }
}
