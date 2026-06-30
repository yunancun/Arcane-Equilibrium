//! Stock/ETF scorecard derivation contract for ADR-0048.
//!
//! This source-only validator pins the derived scorecard artifact lineage before
//! any future writer can exist. It does not contact IBKR, import broker fills,
//! generate shadow fills, start reconciliation or scorecard writers, apply DB
//! changes, read secrets, authorize tiny-live/live, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment};

pub const STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID: &str = "stock_etf_scorecard_derivation_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardDerivationV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub derivation_run_id: String,
    pub strategy_id: String,
    pub universe_version: String,
    pub benchmark_version: String,
    pub as_of_date: String,
    pub scorecard_input_bundle_hash: String,
    pub evidence_clock_manifest_hash: String,
    pub dq_manifest_hash: String,
    pub paper_shadow_reconciliation_hash: String,
    pub formula_appendix_hash: String,
    pub statistical_preregistration_hash: String,
    pub scorecard_manifest_hash: String,
    pub scorecard_verdict_hash: String,
    pub source_commit_hash: String,
    pub derivation_code_hash: String,
    pub output_artifact_hash: String,
    pub qc_review_hash: String,
    pub mit_review_hash: String,
    pub qa_review_hash: String,
    pub derived_from_atomic_facts_only: bool,
    pub idempotent_replay_proven: bool,
    pub paper_and_shadow_fills_separate: bool,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub broker_fill_import_performed: bool,
    pub shadow_fill_generated: bool,
    pub reconciliation_writer_started: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub evidence_clock_started: bool,
    pub secret_content_serialized: bool,
    pub live_or_tiny_live_authorized: bool,
    pub sealed: bool,
}

impl Default for StockEtfScorecardDerivationV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            derivation_run_id: String::new(),
            strategy_id: String::new(),
            universe_version: String::new(),
            benchmark_version: String::new(),
            as_of_date: String::new(),
            scorecard_input_bundle_hash: String::new(),
            evidence_clock_manifest_hash: String::new(),
            dq_manifest_hash: String::new(),
            paper_shadow_reconciliation_hash: String::new(),
            formula_appendix_hash: String::new(),
            statistical_preregistration_hash: String::new(),
            scorecard_manifest_hash: String::new(),
            scorecard_verdict_hash: String::new(),
            source_commit_hash: String::new(),
            derivation_code_hash: String::new(),
            output_artifact_hash: String::new(),
            qc_review_hash: String::new(),
            mit_review_hash: String::new(),
            qa_review_hash: String::new(),
            derived_from_atomic_facts_only: false,
            idempotent_replay_proven: false,
            paper_and_shadow_fills_separate: false,
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            broker_fill_import_performed: false,
            shadow_fill_generated: false,
            reconciliation_writer_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            evidence_clock_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
            sealed: false,
        }
    }
}

impl StockEtfScorecardDerivationV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            derivation_run_id: "scorecard-derive-2026-06-30-001".to_string(),
            strategy_id: "stock_etf_cash_shadow_signal_v1".to_string(),
            universe_version: "pit-us-etf-v1".to_string(),
            benchmark_version: "SPY_total_return_matched_control_v1".to_string(),
            as_of_date: "2026-06-30".to_string(),
            scorecard_input_bundle_hash: "1".repeat(64),
            evidence_clock_manifest_hash: "2".repeat(64),
            dq_manifest_hash: "3".repeat(64),
            paper_shadow_reconciliation_hash: "4".repeat(64),
            formula_appendix_hash: "5".repeat(64),
            statistical_preregistration_hash: "6".repeat(64),
            scorecard_manifest_hash: "7".repeat(64),
            scorecard_verdict_hash: "8".repeat(64),
            source_commit_hash: "9".repeat(64),
            derivation_code_hash: "a".repeat(64),
            output_artifact_hash: "b".repeat(64),
            qc_review_hash: "c".repeat(64),
            mit_review_hash: "d".repeat(64),
            qa_review_hash: "e".repeat(64),
            derived_from_atomic_facts_only: true,
            idempotent_replay_proven: true,
            paper_and_shadow_fills_separate: true,
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            broker_fill_import_performed: false,
            shadow_fill_generated: false,
            reconciliation_writer_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            evidence_clock_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
            sealed: true,
        }
    }

    pub fn validate(&self) -> StockEtfScorecardDerivationVerdict {
        use StockEtfScorecardDerivationBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id.trim().is_empty() {
            blockers.push(Blocker::ContractIdMissing);
        } else if self.contract_id != STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if self.environment != BrokerEnvironment::Paper {
            blockers.push(Blocker::EnvironmentDenied);
        }
        validate_ids(self, &mut blockers);
        validate_hashes(self, &mut blockers);
        validate_authority(self, &mut blockers);

        StockEtfScorecardDerivationVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardDerivationVerdict {
    pub accepted: bool,
    pub blockers: Vec<StockEtfScorecardDerivationBlocker>,
}

impl StockEtfScorecardDerivationVerdict {
    fn new(blockers: Vec<StockEtfScorecardDerivationBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfScorecardDerivationBlocker {
    ContractIdMissing,
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentDenied,
    DerivationRunIdMissing,
    StrategyIdMissing,
    UniverseVersionMissing,
    BenchmarkVersionMissing,
    AsOfDateMissing,
    ScorecardInputBundleHashInvalid,
    EvidenceClockManifestHashInvalid,
    DqManifestHashInvalid,
    PaperShadowReconciliationHashInvalid,
    FormulaAppendixHashInvalid,
    StatisticalPreregistrationHashInvalid,
    ScorecardManifestHashInvalid,
    ScorecardVerdictHashInvalid,
    SourceCommitHashInvalid,
    DerivationCodeHashInvalid,
    OutputArtifactHashInvalid,
    QcReviewHashInvalid,
    MitReviewHashInvalid,
    QaReviewHashInvalid,
    NotDerivedFromAtomicFactsOnly,
    IdempotentReplayNotProven,
    PaperShadowFillSeparationMissing,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    BrokerFillImportPerformed,
    ShadowFillGenerated,
    ReconciliationWriterStarted,
    ScorecardWriterStarted,
    DbApplyPerformed,
    EvidenceClockStarted,
    SecretContentSerialized,
    LiveOrTinyLiveAuthorized,
    NotSealed,
}

fn validate_ids(
    candidate: &StockEtfScorecardDerivationV1,
    blockers: &mut Vec<StockEtfScorecardDerivationBlocker>,
) {
    use StockEtfScorecardDerivationBlocker as Blocker;
    if candidate.derivation_run_id.trim().is_empty() {
        blockers.push(Blocker::DerivationRunIdMissing);
    }
    if candidate.strategy_id.trim().is_empty() {
        blockers.push(Blocker::StrategyIdMissing);
    }
    if candidate.universe_version.trim().is_empty() {
        blockers.push(Blocker::UniverseVersionMissing);
    }
    if candidate.benchmark_version.trim().is_empty() {
        blockers.push(Blocker::BenchmarkVersionMissing);
    }
    if candidate.as_of_date.trim().is_empty() {
        blockers.push(Blocker::AsOfDateMissing);
    }
}

fn validate_hashes(
    candidate: &StockEtfScorecardDerivationV1,
    blockers: &mut Vec<StockEtfScorecardDerivationBlocker>,
) {
    use StockEtfScorecardDerivationBlocker as Blocker;
    if !is_sha256_hex(&candidate.scorecard_input_bundle_hash) {
        blockers.push(Blocker::ScorecardInputBundleHashInvalid);
    }
    if !is_sha256_hex(&candidate.evidence_clock_manifest_hash) {
        blockers.push(Blocker::EvidenceClockManifestHashInvalid);
    }
    if !is_sha256_hex(&candidate.dq_manifest_hash) {
        blockers.push(Blocker::DqManifestHashInvalid);
    }
    if !is_sha256_hex(&candidate.paper_shadow_reconciliation_hash) {
        blockers.push(Blocker::PaperShadowReconciliationHashInvalid);
    }
    if !is_sha256_hex(&candidate.formula_appendix_hash) {
        blockers.push(Blocker::FormulaAppendixHashInvalid);
    }
    if !is_sha256_hex(&candidate.statistical_preregistration_hash) {
        blockers.push(Blocker::StatisticalPreregistrationHashInvalid);
    }
    if !is_sha256_hex(&candidate.scorecard_manifest_hash) {
        blockers.push(Blocker::ScorecardManifestHashInvalid);
    }
    if !is_sha256_hex(&candidate.scorecard_verdict_hash) {
        blockers.push(Blocker::ScorecardVerdictHashInvalid);
    }
    if !is_sha256_hex(&candidate.source_commit_hash) {
        blockers.push(Blocker::SourceCommitHashInvalid);
    }
    if !is_sha256_hex(&candidate.derivation_code_hash) {
        blockers.push(Blocker::DerivationCodeHashInvalid);
    }
    if !is_sha256_hex(&candidate.output_artifact_hash) {
        blockers.push(Blocker::OutputArtifactHashInvalid);
    }
    if !is_sha256_hex(&candidate.qc_review_hash) {
        blockers.push(Blocker::QcReviewHashInvalid);
    }
    if !is_sha256_hex(&candidate.mit_review_hash) {
        blockers.push(Blocker::MitReviewHashInvalid);
    }
    if !is_sha256_hex(&candidate.qa_review_hash) {
        blockers.push(Blocker::QaReviewHashInvalid);
    }
}

fn validate_authority(
    candidate: &StockEtfScorecardDerivationV1,
    blockers: &mut Vec<StockEtfScorecardDerivationBlocker>,
) {
    use StockEtfScorecardDerivationBlocker as Blocker;
    if !candidate.derived_from_atomic_facts_only {
        blockers.push(Blocker::NotDerivedFromAtomicFactsOnly);
    }
    if !candidate.idempotent_replay_proven {
        blockers.push(Blocker::IdempotentReplayNotProven);
    }
    if !candidate.paper_and_shadow_fills_separate {
        blockers.push(Blocker::PaperShadowFillSeparationMissing);
    }
    if !candidate.bybit_live_execution_unchanged {
        blockers.push(Blocker::BybitLiveExecutionNotProtected);
    }
    if candidate.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if candidate.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if candidate.broker_fill_import_performed {
        blockers.push(Blocker::BrokerFillImportPerformed);
    }
    if candidate.shadow_fill_generated {
        blockers.push(Blocker::ShadowFillGenerated);
    }
    if candidate.reconciliation_writer_started {
        blockers.push(Blocker::ReconciliationWriterStarted);
    }
    if candidate.scorecard_writer_started {
        blockers.push(Blocker::ScorecardWriterStarted);
    }
    if candidate.db_apply_performed {
        blockers.push(Blocker::DbApplyPerformed);
    }
    if candidate.evidence_clock_started {
        blockers.push(Blocker::EvidenceClockStarted);
    }
    if candidate.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if candidate.live_or_tiny_live_authorized {
        blockers.push(Blocker::LiveOrTinyLiveAuthorized);
    }
    if !candidate.sealed {
        blockers.push(Blocker::NotSealed);
    }
}
