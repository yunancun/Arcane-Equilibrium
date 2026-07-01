//! ADR-0048 Stock/ETF scorecard verdict acceptance tests.
//!
//! These tests validate the statistical verdict artifact only. They do not
//! authorize tiny-live/live, contact IBKR, import broker fills, write PG, read
//! secrets, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfScorecardVerdictBlocker,
    StockEtfScorecardVerdictLabel, StockEtfScorecardVerdictV1,
    STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID,
};

#[test]
fn default_scorecard_verdict_blocks_unsealed_unknown_artifact() {
    use StockEtfScorecardVerdictBlocker as Blocker;

    let verdict = StockEtfScorecardVerdictV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMissing,
            Blocker::SourceVersionMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::EnvironmentDenied,
            Blocker::ScorecardInputBundleHashInvalid,
            Blocker::EvidenceClockManifestHashInvalid,
            Blocker::DqManifestHashInvalid,
            Blocker::FormulaAppendixHashInvalid,
            Blocker::StatisticalPreregistrationHashInvalid,
            Blocker::BenchmarkVersionHashInvalid,
            Blocker::CostModelVersionHashInvalid,
            Blocker::StrategyHypothesisHashInvalid,
            Blocker::ReferenceDataSourcesHashInvalid,
            Blocker::PaperShadowReconciliationHashInvalid,
            Blocker::ScorecardManifestHashInvalid,
            Blocker::VerdictRationaleHashInvalid,
            Blocker::WindowThresholdMissing,
            Blocker::MinIndependentObservationMissing,
            Blocker::DivergenceThresholdMissing,
            Blocker::PsrThresholdMissing,
            Blocker::DsrThresholdMissing,
            Blocker::QcReviewHashInvalid,
            Blocker::MitReviewHashInvalid,
            Blocker::QaReviewHashInvalid,
            Blocker::QcReviewMissing,
            Blocker::MitReviewMissing,
            Blocker::QaReviewMissing,
            Blocker::ScorecardNotDerivedOnly,
            Blocker::PaperShadowFillSeparationMissing,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::NotSealed,
        ]
    );
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
    use StockEtfScorecardVerdictBlocker as Blocker;

    let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    candidate.contract_id = "stock_etf_scorecard_verdict_v1_fixture".to_string();
    candidate.scorecard_input_bundle_hash.clear();
    candidate.formula_appendix_hash = "not-a-sha".to_string();
    candidate.statistical_preregistration_hash.clear();
    candidate.paper_shadow_reconciliation_hash.clear();
    candidate.scorecard_manifest_hash.clear();
    candidate.verdict_rationale_hash.clear();

    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::ScorecardInputBundleHashInvalid,
            Blocker::FormulaAppendixHashInvalid,
            Blocker::StatisticalPreregistrationHashInvalid,
            Blocker::PaperShadowReconciliationHashInvalid,
            Blocker::ScorecardManifestHashInvalid,
            Blocker::VerdictRationaleHashInvalid,
        ]
    );
}

#[test]
fn scorecard_verdict_rejects_each_identity_gap_independently() {
    use StockEtfScorecardVerdictBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardVerdictV1), Blocker); 7] = [
        (
            |candidate| candidate.contract_id.clear(),
            Blocker::ContractIdMissing,
        ),
        (
            |candidate| {
                candidate.contract_id = "stock_etf_scorecard_verdict_v1_fixture".to_string()
            },
            Blocker::ContractIdMismatch,
        ),
        (
            |candidate| candidate.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (
            |candidate| candidate.asset_lane = AssetLane::CryptoPerp,
            Blocker::WrongAssetLane,
        ),
        (
            |candidate| candidate.broker = Broker::Bybit,
            Blocker::WrongBroker,
        ),
        (
            |candidate| candidate.environment = BrokerEnvironment::Shadow,
            Blocker::EnvironmentDenied,
        ),
        (
            |candidate| candidate.environment = BrokerEnvironment::LiveReservedDenied,
            Blocker::EnvironmentDenied,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn scorecard_verdict_rejects_each_hash_lineage_gap_independently() {
    use StockEtfScorecardVerdictBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardVerdictV1), Blocker); 12] = [
        (
            |candidate| candidate.scorecard_input_bundle_hash.clear(),
            Blocker::ScorecardInputBundleHashInvalid,
        ),
        (
            |candidate| candidate.evidence_clock_manifest_hash.clear(),
            Blocker::EvidenceClockManifestHashInvalid,
        ),
        (
            |candidate| candidate.dq_manifest_hash.clear(),
            Blocker::DqManifestHashInvalid,
        ),
        (
            |candidate| candidate.formula_appendix_hash = "not-a-sha".to_string(),
            Blocker::FormulaAppendixHashInvalid,
        ),
        (
            |candidate| candidate.statistical_preregistration_hash.clear(),
            Blocker::StatisticalPreregistrationHashInvalid,
        ),
        (
            |candidate| candidate.benchmark_version_hash.clear(),
            Blocker::BenchmarkVersionHashInvalid,
        ),
        (
            |candidate| candidate.cost_model_version_hash.clear(),
            Blocker::CostModelVersionHashInvalid,
        ),
        (
            |candidate| candidate.strategy_hypothesis_hash.clear(),
            Blocker::StrategyHypothesisHashInvalid,
        ),
        (
            |candidate| candidate.reference_data_sources_hash.clear(),
            Blocker::ReferenceDataSourcesHashInvalid,
        ),
        (
            |candidate| candidate.paper_shadow_reconciliation_hash.clear(),
            Blocker::PaperShadowReconciliationHashInvalid,
        ),
        (
            |candidate| candidate.scorecard_manifest_hash.clear(),
            Blocker::ScorecardManifestHashInvalid,
        ),
        (
            |candidate| candidate.verdict_rationale_hash.clear(),
            Blocker::VerdictRationaleHashInvalid,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn profitability_feasible_requires_thresholds_positive_lcbs_and_quality_labels() {
    use StockEtfScorecardVerdictBlocker as Blocker;

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
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::WindowThresholdNotMet,
            Blocker::IndependentObservationThresholdNotMet,
            Blocker::PaperShadowDivergenceExceeded,
            Blocker::BenchmarkAfterCostLcbNotPositive,
            Blocker::CostStressLcbNotPositive,
            Blocker::PsrThresholdNotMet,
            Blocker::DsrThresholdNotMet,
            Blocker::ConcentrationLabelRejected,
            Blocker::RegimeLabelRejected,
            Blocker::BreadthLabelRejected,
            Blocker::FreshnessLabelRejected,
            Blocker::SurvivorshipLabelRejected,
            Blocker::ExecutionRealismLabelRejected,
        ]
    );
}

#[test]
fn scorecard_verdict_rejects_each_threshold_shape_gap_independently() {
    use StockEtfScorecardVerdictBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardVerdictV1), Blocker); 6] = [
        (
            |candidate| candidate.min_window_trading_days = 0,
            Blocker::WindowThresholdMissing,
        ),
        (
            |candidate| candidate.min_independent_observation_count = 0,
            Blocker::MinIndependentObservationMissing,
        ),
        (
            |candidate| candidate.max_paper_shadow_divergence_bps = 0,
            Blocker::DivergenceThresholdMissing,
        ),
        (
            |candidate| candidate.psr_bps = 10_001,
            Blocker::ProbabilityMetricOutOfRange,
        ),
        (
            |candidate| candidate.min_psr_bps = 0,
            Blocker::PsrThresholdMissing,
        ),
        (
            |candidate| candidate.min_dsr_bps = 0,
            Blocker::DsrThresholdMissing,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn scorecard_verdict_rejects_each_profitability_and_quality_gap_independently() {
    use StockEtfScorecardVerdictBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardVerdictV1), Blocker); 13] = [
        (
            |candidate| candidate.paper_shadow_window_trading_days = 29,
            Blocker::WindowThresholdNotMet,
        ),
        (
            |candidate| candidate.independent_observation_count = 59,
            Blocker::IndependentObservationThresholdNotMet,
        ),
        (
            |candidate| candidate.paper_shadow_divergence_bps = 101,
            Blocker::PaperShadowDivergenceExceeded,
        ),
        (
            |candidate| candidate.benchmark_excess_lcb_bps = 0,
            Blocker::BenchmarkAfterCostLcbNotPositive,
        ),
        (
            |candidate| candidate.conservative_cost_stress_lcb_bps = 0,
            Blocker::CostStressLcbNotPositive,
        ),
        (
            |candidate| candidate.psr_bps = 9_499,
            Blocker::PsrThresholdNotMet,
        ),
        (
            |candidate| candidate.dsr_bps = 8_999,
            Blocker::DsrThresholdNotMet,
        ),
        (
            |candidate| candidate.concentration_label_passed = false,
            Blocker::ConcentrationLabelRejected,
        ),
        (
            |candidate| candidate.regime_label_passed = false,
            Blocker::RegimeLabelRejected,
        ),
        (
            |candidate| candidate.breadth_label_passed = false,
            Blocker::BreadthLabelRejected,
        ),
        (
            |candidate| candidate.freshness_label_passed = false,
            Blocker::FreshnessLabelRejected,
        ),
        (
            |candidate| candidate.survivorship_label_passed = false,
            Blocker::SurvivorshipLabelRejected,
        ),
        (
            |candidate| candidate.execution_realism_label_passed = false,
            Blocker::ExecutionRealismLabelRejected,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
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
    use StockEtfScorecardVerdictBlocker as Blocker;

    let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    candidate.verdict_label = StockEtfScorecardVerdictLabel::ExecutionModelInvalid;
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![Blocker::ExecutionInvalidVerdictWithoutExecutionFailure]
    );

    candidate.execution_realism_label_passed = false;
    let corrected = candidate.validate();
    assert!(corrected.accepted);
}

#[test]
fn scorecard_verdict_rejects_runtime_side_effects_and_authority() {
    use StockEtfScorecardVerdictBlocker as Blocker;

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
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ScorecardNotDerivedOnly,
            Blocker::PaperShadowFillSeparationMissing,
            Blocker::LiveFillClaimed,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::BrokerFillImportPerformed,
            Blocker::ScorecardWriterStarted,
            Blocker::DbApplyPerformed,
            Blocker::EvidenceClockStarted,
            Blocker::SecretContentSerialized,
            Blocker::LiveOrTinyLiveAuthorized,
            Blocker::NotSealed,
        ]
    );
}

#[test]
fn scorecard_verdict_rejects_each_review_authority_and_boundary_gap_independently() {
    use StockEtfScorecardVerdictBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardVerdictV1), Blocker); 21] = [
        (
            |candidate| candidate.qc_review_hash.clear(),
            Blocker::QcReviewHashInvalid,
        ),
        (
            |candidate| candidate.mit_review_hash.clear(),
            Blocker::MitReviewHashInvalid,
        ),
        (
            |candidate| candidate.qa_review_hash.clear(),
            Blocker::QaReviewHashInvalid,
        ),
        (
            |candidate| candidate.qc_review_passed = false,
            Blocker::QcReviewMissing,
        ),
        (
            |candidate| candidate.mit_review_passed = false,
            Blocker::MitReviewMissing,
        ),
        (
            |candidate| candidate.qa_review_passed = false,
            Blocker::QaReviewMissing,
        ),
        (
            |candidate| candidate.scorecard_is_derived_only = false,
            Blocker::ScorecardNotDerivedOnly,
        ),
        (
            |candidate| candidate.paper_and_shadow_fills_separate = false,
            Blocker::PaperShadowFillSeparationMissing,
        ),
        (
            |candidate| candidate.live_fill_claimed = true,
            Blocker::LiveFillClaimed,
        ),
        (
            |candidate| candidate.bybit_live_execution_unchanged = false,
            Blocker::BybitLiveExecutionNotProtected,
        ),
        (
            |candidate| candidate.ibkr_contact_performed = true,
            Blocker::IbkrContactPerformed,
        ),
        (
            |candidate| candidate.connector_runtime_started = true,
            Blocker::ConnectorRuntimeStarted,
        ),
        (
            |candidate| candidate.broker_fill_import_performed = true,
            Blocker::BrokerFillImportPerformed,
        ),
        (
            |candidate| candidate.scorecard_writer_started = true,
            Blocker::ScorecardWriterStarted,
        ),
        (
            |candidate| candidate.db_apply_performed = true,
            Blocker::DbApplyPerformed,
        ),
        (
            |candidate| candidate.evidence_clock_started = true,
            Blocker::EvidenceClockStarted,
        ),
        (
            |candidate| candidate.secret_content_serialized = true,
            Blocker::SecretContentSerialized,
        ),
        (
            |candidate| candidate.live_or_tiny_live_authorized = true,
            Blocker::LiveOrTinyLiveAuthorized,
        ),
        (|candidate| candidate.sealed = false, Blocker::NotSealed),
        (
            |candidate| {
                candidate.verdict_label = StockEtfScorecardVerdictLabel::ExecutionModelInvalid
            },
            Blocker::ExecutionInvalidVerdictWithoutExecutionFailure,
        ),
        (
            |candidate| {
                candidate.verdict_label = StockEtfScorecardVerdictLabel::EngineeringReady;
                candidate.execution_realism_label_passed = false;
            },
            Blocker::ExecutionRealismLabelRejected,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn scorecard_verdict_rejects_evidence_live_bybit_and_writer_cross_wire_independently() {
    use StockEtfScorecardVerdictBlocker as Blocker;

    let mut derived = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    derived.scorecard_is_derived_only = false;
    assert_single_blocker(derived, Blocker::ScorecardNotDerivedOnly);

    let mut separation = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    separation.paper_and_shadow_fills_separate = false;
    assert_single_blocker(separation, Blocker::PaperShadowFillSeparationMissing);

    let mut live_fill = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    live_fill.live_fill_claimed = true;
    assert_single_blocker(live_fill, Blocker::LiveFillClaimed);

    let mut bybit = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_blocker(bybit, Blocker::BybitLiveExecutionNotProtected);

    let mut writer_runtime = StockEtfScorecardVerdictV1::profitability_feasible_fixture();
    writer_runtime.ibkr_contact_performed = true;
    writer_runtime.connector_runtime_started = true;
    writer_runtime.broker_fill_import_performed = true;
    writer_runtime.scorecard_writer_started = true;
    writer_runtime.db_apply_performed = true;
    writer_runtime.evidence_clock_started = true;
    writer_runtime.secret_content_serialized = true;
    writer_runtime.live_or_tiny_live_authorized = true;
    let writer_runtime_verdict = writer_runtime.validate();
    assert!(!writer_runtime_verdict.accepted);
    assert_eq!(
        writer_runtime_verdict.blockers,
        vec![
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::BrokerFillImportPerformed,
            Blocker::ScorecardWriterStarted,
            Blocker::DbApplyPerformed,
            Blocker::EvidenceClockStarted,
            Blocker::SecretContentSerialized,
            Blocker::LiveOrTinyLiveAuthorized,
        ]
    );
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

fn assert_single_blocker(
    candidate: StockEtfScorecardVerdictV1,
    expected: StockEtfScorecardVerdictBlocker,
) {
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![expected]);
}
