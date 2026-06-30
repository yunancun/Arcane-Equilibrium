//! ADR-0048 Stock/ETF scorecard verdict acceptance tests.
//!
//! These tests validate the statistical verdict artifact only. They do not
//! authorize tiny-live/live, contact IBKR, import broker fills, write PG, read
//! secrets, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    StockEtfScorecardVerdictBlocker, StockEtfScorecardVerdictLabel, StockEtfScorecardVerdictV1,
    STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID,
};

#[test]
fn default_scorecard_verdict_blocks_unsealed_unknown_artifact() {
    let verdict = StockEtfScorecardVerdictV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ContractIdMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::WrongAssetLane));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::WrongBroker));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::FormulaAppendixHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::StatisticalPreregistrationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ScorecardNotDerivedOnly));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::BybitLiveExecutionNotProtected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::NotSealed));
}

#[test]
fn profitability_feasible_fixture_is_source_only_and_no_authority() {
    let candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    let verdict = candidate.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(
        candidate.contract_id,
        STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID
    );
    assert_eq!(
        candidate.verdict_label,
        StockEtfScorecardVerdictLabel::ProfitabilityFeasible
    );
    assert!(candidate.scorecard_is_derived_only);
    assert!(candidate.paper_and_shadow_fills_separate);
    assert!(candidate.bybit_live_execution_unchanged);
    assert!(!candidate.live_fill_claimed);
    assert!(!candidate.ibkr_contact_performed);
    assert!(!candidate.connector_runtime_started);
    assert!(!candidate.broker_fill_import_performed);
    assert!(!candidate.scorecard_writer_started);
    assert!(!candidate.db_apply_performed);
    assert!(!candidate.evidence_clock_started);
    assert!(!candidate.secret_content_serialized);
    assert!(!candidate.live_or_tiny_live_authorized);
}

#[test]
fn scorecard_verdict_requires_formula_preregistration_and_manifest_hashes() {
    let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    candidate.contract_id = "stock_etf_scorecard_verdict_v1_fixture".to_string();
    candidate.scorecard_input_bundle_hash.clear();
    candidate.formula_appendix_hash = "not-a-sha".to_string();
    candidate.statistical_preregistration_hash.clear();
    candidate.scorecard_manifest_hash.clear();
    candidate.verdict_rationale_hash.clear();

    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ScorecardInputBundleHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::FormulaAppendixHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::StatisticalPreregistrationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ScorecardManifestHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::VerdictRationaleHashInvalid));
}

#[test]
fn profitability_feasible_requires_thresholds_positive_lcbs_and_quality_labels() {
    let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    candidate.paper_shadow_window_trading_days = 10;
    candidate.independent_observation_count = 20;
    candidate.benchmark_excess_lcb_bps = 0;
    candidate.conservative_cost_stress_lcb_bps = -1;
    candidate.paper_shadow_divergence_bps = 101;
    candidate.psr_bps = 9_499;
    candidate.dsr_bps = 8_999;
    candidate.concentration_label_passed = false;
    candidate.regime_label_passed = false;
    candidate.breadth_label_passed = false;
    candidate.freshness_label_passed = false;
    candidate.survivorship_label_passed = false;
    candidate.execution_realism_label_passed = false;

    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::WindowThresholdNotMet));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::IndependentObservationThresholdNotMet));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::BenchmarkAfterCostLcbNotPositive));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::CostStressLcbNotPositive));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::PaperShadowDivergenceExceeded));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::PsrThresholdNotMet));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::DsrThresholdNotMet));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ConcentrationLabelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::RegimeLabelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::BreadthLabelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::FreshnessLabelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::SurvivorshipLabelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ExecutionRealismLabelRejected));
}

#[test]
fn negative_verdict_can_be_sealed_without_positive_profitability() {
    let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    candidate.verdict_label = StockEtfScorecardVerdictLabel::Kill;
    candidate.gross_pnl_minor_units = -120_000;
    candidate.net_pnl_minor_units = -180_000;
    candidate.benchmark_excess_lcb_bps = -45;
    candidate.conservative_cost_stress_lcb_bps = -60;
    candidate.paper_shadow_divergence_bps = 150;
    candidate.psr_bps = 1_000;
    candidate.dsr_bps = 500;
    candidate.concentration_label_passed = false;
    candidate.regime_label_passed = false;
    candidate.breadth_label_passed = false;
    candidate.freshness_label_passed = false;
    candidate.survivorship_label_passed = false;
    candidate.execution_realism_label_passed = false;

    let verdict = candidate.validate();

    assert!(
        verdict.accepted,
        "negative verdict blockers: {:?}",
        verdict.blockers
    );
    assert!(verdict.blockers.is_empty());
}

#[test]
fn execution_model_invalid_requires_execution_model_failure_evidence() {
    let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    candidate.verdict_label = StockEtfScorecardVerdictLabel::ExecutionModelInvalid;
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert!(verdict.blockers.contains(
        &StockEtfScorecardVerdictBlocker::ExecutionInvalidVerdictWithoutExecutionFailure
    ));

    candidate.execution_realism_label_passed = false;
    let corrected = candidate.validate();
    assert!(corrected.accepted);
}

#[test]
fn scorecard_verdict_rejects_runtime_side_effects_and_authority() {
    let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    candidate.scorecard_is_derived_only = false;
    candidate.paper_and_shadow_fills_separate = false;
    candidate.live_fill_claimed = true;
    candidate.bybit_live_execution_unchanged = false;
    candidate.ibkr_contact_performed = true;
    candidate.connector_runtime_started = true;
    candidate.broker_fill_import_performed = true;
    candidate.scorecard_writer_started = true;
    candidate.db_apply_performed = true;
    candidate.evidence_clock_started = true;
    candidate.secret_content_serialized = true;
    candidate.live_or_tiny_live_authorized = true;
    candidate.sealed = false;

    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ScorecardNotDerivedOnly));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::PaperShadowFillSeparationMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::LiveFillClaimed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::BybitLiveExecutionNotProtected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::IbkrContactPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ConnectorRuntimeStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::BrokerFillImportPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::ScorecardWriterStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::DbApplyPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::EvidenceClockStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::SecretContentSerialized));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::LiveOrTinyLiveAuthorized));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardVerdictBlocker::NotSealed));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_scorecard_verdict.template.toml"),
    )
    .expect("read scorecard verdict template");
    let parsed: StockEtfScorecardVerdictV1 =
        toml::from_str(&raw).expect("scorecard verdict template parses");

    assert_eq!(
        parsed.verdict_label,
        StockEtfScorecardVerdictLabel::InsufficientEvidence
    );
    assert_eq!(parsed.source_version, 0);
    assert!(!parsed.scorecard_is_derived_only);
    assert!(!parsed.paper_and_shadow_fills_separate);
    assert!(!parsed.bybit_live_execution_unchanged);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.connector_runtime_started);
    assert!(!parsed.scorecard_writer_started);
    assert!(!parsed.db_apply_performed);
    assert!(!parsed.evidence_clock_started);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.live_or_tiny_live_authorized);
    assert!(!parsed.sealed);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
