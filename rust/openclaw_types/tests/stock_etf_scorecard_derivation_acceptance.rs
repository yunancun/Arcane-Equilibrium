//! ADR-0048 Stock/ETF scorecard derivation acceptance tests.
//!
//! These tests validate the derived artifact contract only. They do not contact
//! IBKR, import broker fills, generate shadow fills, start writers, write PG,
//! read secrets, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfScorecardDerivationBlocker,
    StockEtfScorecardDerivationV1, STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID,
};

#[test]
fn default_derivation_blocks_unsealed_unknown_artifact() {
    let verdict = StockEtfScorecardDerivationV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, default_derivation_blockers());
}

#[test]
fn accepted_derivation_validates_without_side_effects() {
    let candidate = StockEtfScorecardDerivationV1::accepted_fixture();
    let verdict = candidate.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        candidate.contract_id,
        STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID
    );
    assert!(candidate.derived_from_atomic_facts_only);
    assert!(candidate.idempotent_replay_proven);
    assert!(candidate.paper_and_shadow_fills_separate);
    assert!(candidate.bybit_live_execution_unchanged);
    assert!(!candidate.ibkr_contact_performed);
    assert!(!candidate.connector_runtime_started);
    assert!(!candidate.broker_fill_import_performed);
    assert!(!candidate.shadow_fill_generated);
    assert!(!candidate.reconciliation_writer_started);
    assert!(!candidate.scorecard_writer_started);
    assert!(!candidate.db_apply_performed);
    assert!(!candidate.evidence_clock_started);
    assert!(!candidate.secret_content_serialized);
    assert!(!candidate.live_or_tiny_live_authorized);
}

#[test]
fn derivation_requires_ids_and_lineage_hashes() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let mut candidate = StockEtfScorecardDerivationV1::accepted_fixture();
    candidate.contract_id = "stock_etf_scorecard_derivation_v1_fixture".to_string();
    candidate.derivation_run_id.clear();
    candidate.strategy_id.clear();
    candidate.universe_version.clear();
    candidate.benchmark_version.clear();
    candidate.as_of_date.clear();
    candidate.scorecard_input_bundle_hash.clear();
    candidate.paper_shadow_reconciliation_hash = "not-a-sha".to_string();
    candidate.scorecard_verdict_hash.clear();
    candidate.output_artifact_hash.clear();

    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::DerivationRunIdMissing,
            Blocker::StrategyIdMissing,
            Blocker::UniverseVersionMissing,
            Blocker::BenchmarkVersionMissing,
            Blocker::AsOfDateMissing,
            Blocker::ScorecardInputBundleHashInvalid,
            Blocker::PaperShadowReconciliationHashInvalid,
            Blocker::ScorecardVerdictHashInvalid,
            Blocker::OutputArtifactHashInvalid,
        ]
    );
}

#[test]
fn derivation_rejects_each_identity_gap_independently() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardDerivationV1), Blocker); 7] = [
        (
            |candidate| candidate.contract_id.clear(),
            Blocker::ContractIdMissing,
        ),
        (
            |candidate| {
                candidate.contract_id = "stock_etf_scorecard_derivation_v1_fixture".to_string()
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
        let mut candidate = StockEtfScorecardDerivationV1::accepted_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn derivation_rejects_each_id_gap_independently() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardDerivationV1), Blocker); 5] = [
        (
            |candidate| candidate.derivation_run_id.clear(),
            Blocker::DerivationRunIdMissing,
        ),
        (
            |candidate| candidate.strategy_id.clear(),
            Blocker::StrategyIdMissing,
        ),
        (
            |candidate| candidate.universe_version.clear(),
            Blocker::UniverseVersionMissing,
        ),
        (
            |candidate| candidate.benchmark_version.clear(),
            Blocker::BenchmarkVersionMissing,
        ),
        (
            |candidate| candidate.as_of_date.clear(),
            Blocker::AsOfDateMissing,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardDerivationV1::accepted_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn derivation_rejects_each_hash_lineage_gap_independently() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardDerivationV1), Blocker); 14] = [
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
            |candidate| candidate.paper_shadow_reconciliation_hash = "not-a-sha".to_string(),
            Blocker::PaperShadowReconciliationHashInvalid,
        ),
        (
            |candidate| candidate.formula_appendix_hash.clear(),
            Blocker::FormulaAppendixHashInvalid,
        ),
        (
            |candidate| candidate.statistical_preregistration_hash.clear(),
            Blocker::StatisticalPreregistrationHashInvalid,
        ),
        (
            |candidate| candidate.scorecard_manifest_hash.clear(),
            Blocker::ScorecardManifestHashInvalid,
        ),
        (
            |candidate| candidate.scorecard_verdict_hash.clear(),
            Blocker::ScorecardVerdictHashInvalid,
        ),
        (
            |candidate| candidate.source_commit_hash.clear(),
            Blocker::SourceCommitHashInvalid,
        ),
        (
            |candidate| candidate.derivation_code_hash.clear(),
            Blocker::DerivationCodeHashInvalid,
        ),
        (
            |candidate| candidate.output_artifact_hash.clear(),
            Blocker::OutputArtifactHashInvalid,
        ),
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
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardDerivationV1::accepted_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn derivation_rejects_runtime_side_effects_and_authority() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let mut candidate = StockEtfScorecardDerivationV1::accepted_fixture();
    candidate.derived_from_atomic_facts_only = false;
    candidate.idempotent_replay_proven = false;
    candidate.paper_and_shadow_fills_separate = false;
    candidate.bybit_live_execution_unchanged = false;
    candidate.ibkr_contact_performed = true;
    candidate.connector_runtime_started = true;
    candidate.broker_fill_import_performed = true;
    candidate.shadow_fill_generated = true;
    candidate.reconciliation_writer_started = true;
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
            Blocker::NotDerivedFromAtomicFactsOnly,
            Blocker::IdempotentReplayNotProven,
            Blocker::PaperShadowFillSeparationMissing,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::BrokerFillImportPerformed,
            Blocker::ShadowFillGenerated,
            Blocker::ReconciliationWriterStarted,
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
fn derivation_rejects_each_evidence_and_seal_gap_independently() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardDerivationV1), Blocker); 5] = [
        (
            |candidate| candidate.derived_from_atomic_facts_only = false,
            Blocker::NotDerivedFromAtomicFactsOnly,
        ),
        (
            |candidate| candidate.idempotent_replay_proven = false,
            Blocker::IdempotentReplayNotProven,
        ),
        (
            |candidate| candidate.paper_and_shadow_fills_separate = false,
            Blocker::PaperShadowFillSeparationMissing,
        ),
        (
            |candidate| candidate.bybit_live_execution_unchanged = false,
            Blocker::BybitLiveExecutionNotProtected,
        ),
        (|candidate| candidate.sealed = false, Blocker::NotSealed),
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardDerivationV1::accepted_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn derivation_rejects_each_boundary_flag_independently() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let cases: [(fn(&mut StockEtfScorecardDerivationV1), Blocker); 10] = [
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
            |candidate| candidate.shadow_fill_generated = true,
            Blocker::ShadowFillGenerated,
        ),
        (
            |candidate| candidate.reconciliation_writer_started = true,
            Blocker::ReconciliationWriterStarted,
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
    ];

    for (mutate, blocker) in cases {
        let mut candidate = StockEtfScorecardDerivationV1::accepted_fixture();
        mutate(&mut candidate);
        assert_single_blocker(candidate, blocker);
    }
}

#[test]
fn derivation_rejects_atomic_replay_separation_and_writer_cross_wire_independently() {
    use StockEtfScorecardDerivationBlocker as Blocker;

    let mut atomic = StockEtfScorecardDerivationV1::accepted_fixture();
    atomic.derived_from_atomic_facts_only = false;
    assert_single_blocker(atomic, Blocker::NotDerivedFromAtomicFactsOnly);

    let mut replay = StockEtfScorecardDerivationV1::accepted_fixture();
    replay.idempotent_replay_proven = false;
    assert_single_blocker(replay, Blocker::IdempotentReplayNotProven);

    let mut separation = StockEtfScorecardDerivationV1::accepted_fixture();
    separation.paper_and_shadow_fills_separate = false;
    assert_single_blocker(separation, Blocker::PaperShadowFillSeparationMissing);

    let mut bybit = StockEtfScorecardDerivationV1::accepted_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_blocker(bybit, Blocker::BybitLiveExecutionNotProtected);

    let mut writer_runtime = StockEtfScorecardDerivationV1::accepted_fixture();
    writer_runtime.ibkr_contact_performed = true;
    writer_runtime.connector_runtime_started = true;
    writer_runtime.broker_fill_import_performed = true;
    writer_runtime.shadow_fill_generated = true;
    writer_runtime.reconciliation_writer_started = true;
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
            Blocker::ShadowFillGenerated,
            Blocker::ReconciliationWriterStarted,
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
    let template_path =
        srv_root.join("settings/broker/stock_etf_scorecard_derivation.template.toml");
    let raw = std::fs::read_to_string(&template_path).expect("read derivation template");
    let parsed: StockEtfScorecardDerivationV1 =
        toml::from_str(&raw).expect("parse derivation template");
    let verdict = parsed.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, default_derivation_blockers());
    assert!(!raw.contains("account_id"));
    assert!(!raw.contains("token"));
    assert!(!raw.contains("password"));
}

fn assert_single_blocker(
    candidate: StockEtfScorecardDerivationV1,
    expected: StockEtfScorecardDerivationBlocker,
) {
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![expected]);
}

fn default_derivation_blockers() -> Vec<StockEtfScorecardDerivationBlocker> {
    use StockEtfScorecardDerivationBlocker as Blocker;

    vec![
        Blocker::ContractIdMissing,
        Blocker::SourceVersionMismatch,
        Blocker::WrongAssetLane,
        Blocker::WrongBroker,
        Blocker::EnvironmentDenied,
        Blocker::DerivationRunIdMissing,
        Blocker::StrategyIdMissing,
        Blocker::UniverseVersionMissing,
        Blocker::BenchmarkVersionMissing,
        Blocker::AsOfDateMissing,
        Blocker::ScorecardInputBundleHashInvalid,
        Blocker::EvidenceClockManifestHashInvalid,
        Blocker::DqManifestHashInvalid,
        Blocker::PaperShadowReconciliationHashInvalid,
        Blocker::FormulaAppendixHashInvalid,
        Blocker::StatisticalPreregistrationHashInvalid,
        Blocker::ScorecardManifestHashInvalid,
        Blocker::ScorecardVerdictHashInvalid,
        Blocker::SourceCommitHashInvalid,
        Blocker::DerivationCodeHashInvalid,
        Blocker::OutputArtifactHashInvalid,
        Blocker::QcReviewHashInvalid,
        Blocker::MitReviewHashInvalid,
        Blocker::QaReviewHashInvalid,
        Blocker::NotDerivedFromAtomicFactsOnly,
        Blocker::IdempotentReplayNotProven,
        Blocker::PaperShadowFillSeparationMissing,
        Blocker::BybitLiveExecutionNotProtected,
        Blocker::NotSealed,
    ]
}
