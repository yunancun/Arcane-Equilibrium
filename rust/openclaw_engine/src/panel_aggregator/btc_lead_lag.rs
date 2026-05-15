//! Sprint N+1 W2 BTC -> alt lead-lag panel producer namespace.
//!
//! This module keeps the public API stable while splitting the former monolith
//! into focused implementation files:
//! - producer: rolling buffers and pure lead-lag metrics
//! - ingest: BTC orderbook WS push ingestion
//! - snapshot: V088 in-memory snapshot and IPC-panel adaptor
//! - db_writer: run loop, PG fetch, V088 INSERT, and IPC slot factory

mod db_writer;
mod ingest;
mod producer;
#[cfg(test)]
mod producer_tests;
mod snapshot;

pub use db_writer::create_btc_lead_lag_panel_slot;
#[allow(unused_imports)]
pub(crate) use db_writer::insert_btc_lead_lag_snapshot;
pub use ingest::{
    compute_btc_book_imbalance, create_btc_orderbook_slot, spawn_btc_orderbook_ingest_task,
    BtcOrderbookSlot,
};
pub use producer::{compute_expected_dir, pearson_corr, psr_zero, BtcLeadLagProducer};
pub use snapshot::{snapshot_to_trait_panel, BtcLeadLagPanelSnapshot};

pub const LEAD_WINDOW_SECS_MAIN: u32 = 120;
pub const LEAD_WINDOW_SECS_SHADOW_60: u32 = 60;
pub const LEAD_WINDOW_SECS_SHADOW_300: u32 = 300;
pub const XCORR_BASELINE_SECS: u64 = 3600;
pub const XCORR_MIN_SAMPLE: usize = 30;
pub const VOLUME_Z_BASELINE_SECS: u64 = 3600;
pub const THRESHOLD_X_BPS: f64 = 10.0;
pub const THRESHOLD_Y: f64 = 0.40;
pub const REGIME_EXTREME_BPS: f64 = 200.0;
pub const ONE_HOUR_SECS: u64 = 3600;
pub const SOURCE_TIER: &str = "cross_asset_btc_lead_lag";
pub const DIAGNOSTIC_SOURCE_TIER: &str = "cross_asset_btc_lead_lag_diagnostic";
pub const ONE_MIN_SECS: u64 = 60;
pub const BTC_ORDERBOOK_SYMBOL: &str = "BTCUSDT";
pub const BTC_BOOK_IMBALANCE_TOP_N: usize = 5;
pub const OPENCLAW_ENABLE_PAPER_ENV: &str = "OPENCLAW_ENABLE_PAPER";
pub const OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC_ENV: &str =
    "OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC";

fn env_flag_enabled(name: &str) -> bool {
    matches!(std::env::var(name), Ok(value) if value.trim() == "1")
}

pub fn btc_lead_lag_diagnostic_mode_enabled() -> bool {
    env_flag_enabled(OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC_ENV)
}

pub fn btc_lead_lag_source_tier_for_mode(diagnostic_mode: bool) -> &'static str {
    if diagnostic_mode {
        DIAGNOSTIC_SOURCE_TIER
    } else {
        SOURCE_TIER
    }
}

pub fn should_spawn_btc_lead_lag_producer(has_demo: bool, has_live: bool) -> bool {
    if btc_lead_lag_diagnostic_mode_enabled() {
        return true;
    }

    match std::env::var(OPENCLAW_ENABLE_PAPER_ENV) {
        Ok(value) => value.trim() == "1",
        Err(std::env::VarError::NotPresent) => !has_demo && !has_live,
        Err(std::env::VarError::NotUnicode(_)) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Mutex, OnceLock};

    fn env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    fn clear_gate_env() {
        std::env::remove_var(OPENCLAW_ENABLE_PAPER_ENV);
        std::env::remove_var(OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC_ENV);
    }

    #[test]
    fn should_spawn_btc_lead_lag_diagnostic_overrides_paper_disabled_runtime() {
        let _guard = env_lock().lock().expect("env mutex poisoned");
        clear_gate_env();
        std::env::set_var(OPENCLAW_ENABLE_PAPER_ENV, "0");
        std::env::set_var(OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC_ENV, "1");

        assert!(should_spawn_btc_lead_lag_producer(true, false));
        assert_eq!(
            btc_lead_lag_source_tier_for_mode(btc_lead_lag_diagnostic_mode_enabled()),
            DIAGNOSTIC_SOURCE_TIER
        );

        clear_gate_env();
    }

    #[test]
    fn should_not_spawn_btc_lead_lag_when_paper_disabled_without_diagnostic() {
        let _guard = env_lock().lock().expect("env mutex poisoned");
        clear_gate_env();
        std::env::set_var(OPENCLAW_ENABLE_PAPER_ENV, "0");

        assert!(!should_spawn_btc_lead_lag_producer(true, false));

        clear_gate_env();
    }
}
