//! ADR-0048 Stock/ETF scorecard derivation acceptance tests.
//!
//! These tests validate the derived artifact contract only. They do not contact
//! IBKR, import broker fills, generate shadow fills, start writers, write PG,
//! read secrets, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    StockEtfScorecardDerivationBlocker, StockEtfScorecardDerivationV1,
    STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID,
};

fn assert_has_blocker(
    blockers: &[StockEtfScorecardDerivationBlocker],
    blocker: StockEtfScorecardDerivationBlocker,
) {
    assert!(
        blockers.contains(&blocker),
        "missing blocker {blocker:?}; blockers: {blockers:?}"
    );
}

fn assert_lacks_blocker(
    blockers: &[StockEtfScorecardDerivationBlocker],
    blocker: StockEtfScorecardDerivationBlocker,
) {
    assert!(
        !blockers.contains(&blocker),
        "unexpected blocker {blocker:?}; blockers: {blockers:?}"
    );
}

#[test]
fn default_derivation_blocks_unsealed_unknown_artifact() {
    let verdict = StockEtfScorecardDerivationV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ContractIdMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::WrongAssetLane));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::WrongBroker));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::DerivationRunIdMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ScorecardInputBundleHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::PaperShadowReconciliationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::NotDerivedFromAtomicFactsOnly));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::BybitLiveExecutionNotProtected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::NotSealed));
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
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::DerivationRunIdMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::StrategyIdMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::UniverseVersionMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::BenchmarkVersionMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::AsOfDateMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ScorecardInputBundleHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::PaperShadowReconciliationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ScorecardVerdictHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::OutputArtifactHashInvalid));
}

#[test]
fn derivation_rejects_runtime_side_effects_and_authority() {
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
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::NotDerivedFromAtomicFactsOnly));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::IdempotentReplayNotProven));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::PaperShadowFillSeparationMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::BybitLiveExecutionNotProtected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::IbkrContactPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ShadowFillGenerated));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ReconciliationWriterStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ScorecardWriterStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::DbApplyPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::LiveOrTinyLiveAuthorized));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::NotSealed));
}

#[test]
fn derivation_rejects_atomic_replay_separation_and_writer_cross_wire_independently() {
    let mut atomic = StockEtfScorecardDerivationV1::accepted_fixture();
    atomic.derived_from_atomic_facts_only = false;
    let atomic_verdict = atomic.validate();
    assert!(!atomic_verdict.accepted);
    assert_has_blocker(
        &atomic_verdict.blockers,
        StockEtfScorecardDerivationBlocker::NotDerivedFromAtomicFactsOnly,
    );
    assert_lacks_blocker(
        &atomic_verdict.blockers,
        StockEtfScorecardDerivationBlocker::IdempotentReplayNotProven,
    );
    assert_lacks_blocker(
        &atomic_verdict.blockers,
        StockEtfScorecardDerivationBlocker::PaperShadowFillSeparationMissing,
    );
    assert_lacks_blocker(
        &atomic_verdict.blockers,
        StockEtfScorecardDerivationBlocker::BybitLiveExecutionNotProtected,
    );
    assert_lacks_blocker(
        &atomic_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ScorecardWriterStarted,
    );

    let mut replay = StockEtfScorecardDerivationV1::accepted_fixture();
    replay.idempotent_replay_proven = false;
    let replay_verdict = replay.validate();
    assert!(!replay_verdict.accepted);
    assert_has_blocker(
        &replay_verdict.blockers,
        StockEtfScorecardDerivationBlocker::IdempotentReplayNotProven,
    );
    assert_lacks_blocker(
        &replay_verdict.blockers,
        StockEtfScorecardDerivationBlocker::NotDerivedFromAtomicFactsOnly,
    );
    assert_lacks_blocker(
        &replay_verdict.blockers,
        StockEtfScorecardDerivationBlocker::PaperShadowFillSeparationMissing,
    );
    assert_lacks_blocker(
        &replay_verdict.blockers,
        StockEtfScorecardDerivationBlocker::BybitLiveExecutionNotProtected,
    );
    assert_lacks_blocker(
        &replay_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ScorecardWriterStarted,
    );

    let mut separation = StockEtfScorecardDerivationV1::accepted_fixture();
    separation.paper_and_shadow_fills_separate = false;
    let separation_verdict = separation.validate();
    assert!(!separation_verdict.accepted);
    assert_has_blocker(
        &separation_verdict.blockers,
        StockEtfScorecardDerivationBlocker::PaperShadowFillSeparationMissing,
    );
    assert_lacks_blocker(
        &separation_verdict.blockers,
        StockEtfScorecardDerivationBlocker::NotDerivedFromAtomicFactsOnly,
    );
    assert_lacks_blocker(
        &separation_verdict.blockers,
        StockEtfScorecardDerivationBlocker::IdempotentReplayNotProven,
    );
    assert_lacks_blocker(
        &separation_verdict.blockers,
        StockEtfScorecardDerivationBlocker::BybitLiveExecutionNotProtected,
    );
    assert_lacks_blocker(
        &separation_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ScorecardWriterStarted,
    );

    let mut bybit = StockEtfScorecardDerivationV1::accepted_fixture();
    bybit.bybit_live_execution_unchanged = false;
    let bybit_verdict = bybit.validate();
    assert!(!bybit_verdict.accepted);
    assert_has_blocker(
        &bybit_verdict.blockers,
        StockEtfScorecardDerivationBlocker::BybitLiveExecutionNotProtected,
    );
    assert_lacks_blocker(
        &bybit_verdict.blockers,
        StockEtfScorecardDerivationBlocker::NotDerivedFromAtomicFactsOnly,
    );
    assert_lacks_blocker(
        &bybit_verdict.blockers,
        StockEtfScorecardDerivationBlocker::IdempotentReplayNotProven,
    );
    assert_lacks_blocker(
        &bybit_verdict.blockers,
        StockEtfScorecardDerivationBlocker::PaperShadowFillSeparationMissing,
    );
    assert_lacks_blocker(
        &bybit_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ScorecardWriterStarted,
    );

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
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::IbkrContactPerformed,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ConnectorRuntimeStarted,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::BrokerFillImportPerformed,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ShadowFillGenerated,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ReconciliationWriterStarted,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::ScorecardWriterStarted,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::DbApplyPerformed,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::EvidenceClockStarted,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::SecretContentSerialized,
    );
    assert_has_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::LiveOrTinyLiveAuthorized,
    );
    assert_lacks_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::NotDerivedFromAtomicFactsOnly,
    );
    assert_lacks_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::IdempotentReplayNotProven,
    );
    assert_lacks_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::PaperShadowFillSeparationMissing,
    );
    assert_lacks_blocker(
        &writer_runtime_verdict.blockers,
        StockEtfScorecardDerivationBlocker::BybitLiveExecutionNotProtected,
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
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardDerivationBlocker::ContractIdMissing));
    assert!(!raw.contains("account_id"));
    assert!(!raw.contains("token"));
    assert!(!raw.contains("password"));
}
