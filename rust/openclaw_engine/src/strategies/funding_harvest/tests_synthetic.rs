//! Synthetic spot ledger × strategy 整合 tests。
//! 範圍：on_fill 開 ledger / on_close_confirmed 清 ledger /
//!   on_external_close 同步清 / import_positions bootstrap 重建。

use super::synthetic_spot::SyntheticSpotState;
use super::*;
use crate::strategies::Strategy;
use openclaw_core::execution::FillResult;

fn make_intent(symbol: &str, qty: f64, strategy: &str) -> OrderIntent {
    OrderIntent {
        symbol: symbol.to_string(),
        is_long: false, // funding harvest perp SHORT
        qty,
        confidence: 0.7,
        strategy: strategy.to_string(),
        order_type: "limit".to_string(),
        limit_price: Some(50_000.0),
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: Some(crate::order_manager::TimeInForce::PostOnly),
        maker_timeout_ms: Some(45_000),
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: crate::intent_processor::IntentType::OpenLong,
        earn_payload: None,
    }
}

fn make_fill(qty: f64, price: f64) -> FillResult {
    FillResult {
        fill_price: price,
        fill_qty: qty,
        fee: 0.0,
        slippage_bps: 0.0,
        is_taker: false,
    }
}

#[test]
fn on_fill_opens_synthetic_spot_ledger() {
    let mut s = FundingHarvest::new();
    let intent = make_intent("BTCUSDT", 0.002, "funding_harvest");
    let fill = make_fill(0.002, 50_000.0);
    s.on_fill(&intent, &fill);
    let ledger = s.synthetic_spot.get("BTCUSDT").expect("ledger must exist");
    assert_eq!(ledger.state, SyntheticSpotState::Open);
    assert!((ledger.entry_notional_usd - 100.0).abs() < 1e-9);
    assert!((ledger.qty - 0.002).abs() < 1e-12);
}

#[test]
fn on_fill_ignores_other_strategy() {
    let mut s = FundingHarvest::new();
    let intent = make_intent("BTCUSDT", 0.002, "ma_crossover");
    let fill = make_fill(0.002, 50_000.0);
    s.on_fill(&intent, &fill);
    assert!(s.synthetic_spot.get("BTCUSDT").is_none());
}

#[test]
fn on_fill_rejects_zero_price() {
    let mut s = FundingHarvest::new();
    let intent = make_intent("BTCUSDT", 0.002, "funding_harvest");
    let fill = make_fill(0.002, 0.0);
    s.on_fill(&intent, &fill);
    assert!(s.synthetic_spot.get("BTCUSDT").is_none());
}

#[test]
fn on_fill_rejects_zero_qty() {
    let mut s = FundingHarvest::new();
    let intent = make_intent("BTCUSDT", 0.0, "funding_harvest");
    let fill = make_fill(0.0, 50_000.0);
    s.on_fill(&intent, &fill);
    assert!(s.synthetic_spot.get("BTCUSDT").is_none());
}

#[test]
fn on_close_confirmed_clears_ledger() {
    let mut s = FundingHarvest::new();
    let intent = make_intent("BTCUSDT", 0.002, "funding_harvest");
    let fill = make_fill(0.002, 50_000.0);
    s.on_fill(&intent, &fill);
    assert!(s.synthetic_spot.contains_key("BTCUSDT"));
    s.on_close_confirmed("BTCUSDT");
    assert!(!s.synthetic_spot.contains_key("BTCUSDT"));
    assert!(!s.entry_ms.contains_key("BTCUSDT"));
    assert!(!s.last_rebalance_check_ms.contains_key("BTCUSDT"));
}

#[test]
fn on_external_close_clears_ledger() {
    let mut s = FundingHarvest::new();
    let intent = make_intent("BTCUSDT", 0.002, "funding_harvest");
    let fill = make_fill(0.002, 50_000.0);
    s.on_fill(&intent, &fill);
    s.on_external_close("BTCUSDT");
    assert!(!s.synthetic_spot.contains_key("BTCUSDT"));
}

#[test]
fn on_close_skipped_clears_ledger() {
    let mut s = FundingHarvest::new();
    let intent = make_intent("BTCUSDT", 0.002, "funding_harvest");
    let fill = make_fill(0.002, 50_000.0);
    s.on_fill(&intent, &fill);
    s.on_close_skipped("BTCUSDT");
    assert!(!s.synthetic_spot.contains_key("BTCUSDT"));
    assert!(!s.entry_ms.contains_key("BTCUSDT"));
}

#[test]
fn import_positions_rebuilds_ledger_from_paper_state() {
    use crate::paper_state::PaperState;
    let mut paper = PaperState::new(10_000.0);
    paper.apply_fill("BTCUSDT", false, 0.002, 50_000.0, 0.0, 1_000, "funding_harvest");
    let mut s = FundingHarvest::new();
    assert!(s.synthetic_spot.is_empty());
    s.import_positions(&paper);
    let ledger = s
        .synthetic_spot
        .get("BTCUSDT")
        .expect("ledger must be rebuilt");
    assert_eq!(ledger.state, SyntheticSpotState::Open);
    assert!((ledger.entry_notional_usd - 100.0).abs() < 1e-9);
    assert_eq!(s.entry_ms.get("BTCUSDT"), Some(&1_000));
}

#[test]
fn import_positions_ignores_other_owner() {
    use crate::paper_state::PaperState;
    let mut paper = PaperState::new(10_000.0);
    paper.apply_fill("BTCUSDT", false, 0.002, 50_000.0, 0.0, 1_000, "ma_crossover");
    let mut s = FundingHarvest::new();
    s.import_positions(&paper);
    assert!(
        s.synthetic_spot.get("BTCUSDT").is_none(),
        "ma_crossover-owned position must not be imported"
    );
}
