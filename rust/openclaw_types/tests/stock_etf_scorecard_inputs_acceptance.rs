//! ADR-0048 Stock/ETF scorecard input contract acceptance tests.
//!
//! These tests validate source-only input evidence shape. They do not contact
//! IBKR, import broker fills, derive scorecards, write PG, or start an evidence
//! clock.

use std::path::PathBuf;

use openclaw_types::{
    BrokerAccountPortfolioCashLedgerV1, BrokerEnvironment, StockEtfScorecardInputBlocker,
    StockEtfScorecardInputBundleV1, StockEtfStorageCapacityV1, StockShadowFillModelV1,
};

#[test]
fn default_scorecard_bundle_blocks_all_atomic_inputs() {
    let verdict = StockEtfScorecardInputBundleV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CashLedgerRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CostModelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::BenchmarkRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ShadowFillModelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::StorageCapacityRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ScorecardNotDerivedOnly));
}

#[test]
fn accepted_fixture_keeps_scorecard_derived_and_live_separate() {
    let bundle = StockEtfScorecardInputBundleV1::accepted_fixture();
    let verdict = bundle.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert!(bundle.scorecard_is_derived_only);
    assert!(bundle.paper_and_shadow_fills_separate);
    assert!(!bundle.live_fill_claimed);
}

#[test]
fn cash_ledger_rejects_live_environment_and_missing_hashes() {
    let mut ledger = BrokerAccountPortfolioCashLedgerV1::accepted_fixture();
    ledger.environment = BrokerEnvironment::LiveReservedDenied;
    ledger.account_snapshot_hash.clear();

    let verdict = ledger.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CashLedgerEnvironmentDenied));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::AccountSnapshotHashInvalid));
}

#[test]
fn shadow_fill_must_be_synthetic_and_never_linked_to_broker_or_live_fill() {
    let mut shadow = StockShadowFillModelV1::accepted_fill_fixture();
    shadow.synthetic_shadow = false;
    shadow.broker_paper_fill_linked = true;
    shadow.live_fill_linked = true;

    let verdict = shadow.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::SyntheticShadowMarkerMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ShadowFillLinkedToBrokerPaperFill));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ShadowFillLinkedToLiveFill));
}

#[test]
fn storage_capacity_requires_forward_capacity_policy_before_evidence_clock() {
    let mut storage = StockEtfStorageCapacityV1::accepted_fixture();
    storage.capacity_breach_blocks_evidence_clock = false;
    storage.capacity_plan_hash.clear();
    storage.rows_per_day_estimate = 0;

    let verdict = storage.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CapacityBreachPolicyMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CapacityPlanHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::RowsPerDayEstimateMissing));
}

#[test]
fn scorecard_bundle_rejects_live_fill_claim_and_missing_separation() {
    let mut bundle = StockEtfScorecardInputBundleV1::accepted_fixture();
    bundle.scorecard_is_derived_only = false;
    bundle.paper_and_shadow_fills_separate = false;
    bundle.live_fill_claimed = true;

    let verdict = bundle.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ScorecardNotDerivedOnly));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::PaperShadowFillSeparationMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::LiveFillClaimed));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_scorecard_inputs.template.toml"),
    )
    .expect("read scorecard input template");
    let parsed: StockEtfScorecardInputBundleV1 =
        toml::from_str(&raw).expect("scorecard input template parses");

    assert!(!parsed.scorecard_is_derived_only);
    assert!(!parsed.paper_and_shadow_fills_separate);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
