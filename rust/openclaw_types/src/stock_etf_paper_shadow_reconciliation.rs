//! Stock/ETF paper-shadow reconciliation contract.
//!
//! This source-only validator pins the evidence shape that reconciles IBKR
//! paper lifecycle/fill facts with synthetic stock/ETF shadow fills. It does
//! not contact IBKR, start connectors, inspect secrets, import fills, generate
//! shadow fills, write reconciliation rows, write scorecards, apply DB changes,
//! route orders, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, AuthorityScope, Broker};

pub const STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID: &str =
    "stock_etf_paper_shadow_reconciliation_v1";
pub const STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE: &str = "paper_shadow";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPaperShadowReconciliationV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub scope: String,
    pub authority_scope: AuthorityScope,
    pub effect_capable: bool,
    pub reconciliation_run_id: String,
    pub paper_order_local_id: String,
    pub broker_order_id: String,
    pub execution_id: String,
    pub commission_report_id: String,
    pub shadow_signal_id: String,
    pub lifecycle_contract_hash: String,
    pub event_log_contract_hash: String,
    pub paper_fill_import_request_hash: String,
    pub shadow_signal_request_hash: String,
    pub shadow_fill_model_hash: String,
    pub cost_model_version_hash: String,
    pub market_data_provenance_hash: String,
    pub paper_shadow_divergence_threshold_hash: String,
    pub paper_shadow_link_hash: String,
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
    pub source_artifact_hash: String,
    pub append_only_event_ready: bool,
    pub paper_fill_imported: bool,
    pub shadow_fill_synthetic: bool,
    pub divergence_bps: u32,
    pub divergence_threshold_bps: u32,
    pub unmatched_paper_fill_count: u32,
    pub unmatched_shadow_fill_count: u32,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub fill_import_performed: bool,
    pub shadow_fill_generated: bool,
    pub reconciliation_writer_started: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub order_routed: bool,
    pub bybit_path_reused: bool,
    pub live_or_tiny_live_authorized: bool,
    pub margin_short_options_cfd_requested: bool,
    pub python_direct_broker_write_requested: bool,
}

impl Default for StockEtfPaperShadowReconciliationV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            scope: String::new(),
            authority_scope: AuthorityScope::Denied,
            effect_capable: false,
            reconciliation_run_id: String::new(),
            paper_order_local_id: String::new(),
            broker_order_id: String::new(),
            execution_id: String::new(),
            commission_report_id: String::new(),
            shadow_signal_id: String::new(),
            lifecycle_contract_hash: String::new(),
            event_log_contract_hash: String::new(),
            paper_fill_import_request_hash: String::new(),
            shadow_signal_request_hash: String::new(),
            shadow_fill_model_hash: String::new(),
            cost_model_version_hash: String::new(),
            market_data_provenance_hash: String::new(),
            paper_shadow_divergence_threshold_hash: String::new(),
            paper_shadow_link_hash: String::new(),
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
            source_artifact_hash: String::new(),
            append_only_event_ready: false,
            paper_fill_imported: false,
            shadow_fill_synthetic: false,
            divergence_bps: 0,
            divergence_threshold_bps: 0,
            unmatched_paper_fill_count: 0,
            unmatched_shadow_fill_count: 0,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            fill_import_performed: false,
            shadow_fill_generated: false,
            reconciliation_writer_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            order_routed: false,
            bybit_path_reused: false,
            live_or_tiny_live_authorized: false,
            margin_short_options_cfd_requested: false,
            python_direct_broker_write_requested: false,
        }
    }
}

impl StockEtfPaperShadowReconciliationV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            scope: STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE.to_string(),
            authority_scope: AuthorityScope::ReadOnly,
            effect_capable: false,
            reconciliation_run_id: "paper_shadow_reconcile_0001".to_string(),
            paper_order_local_id: "local_order_0001".to_string(),
            broker_order_id: "paper_broker_order_0001".to_string(),
            execution_id: "paper_execution_0001".to_string(),
            commission_report_id: "paper_commission_0001".to_string(),
            shadow_signal_id: "shadow_signal_0001".to_string(),
            lifecycle_contract_hash: "1".repeat(64),
            event_log_contract_hash: "2".repeat(64),
            paper_fill_import_request_hash: "3".repeat(64),
            shadow_signal_request_hash: "4".repeat(64),
            shadow_fill_model_hash: "5".repeat(64),
            cost_model_version_hash: "6".repeat(64),
            market_data_provenance_hash: "7".repeat(64),
            paper_shadow_divergence_threshold_hash: "8".repeat(64),
            paper_shadow_link_hash: "9".repeat(64),
            raw_artifact_hash: "a".repeat(64),
            redacted_summary_hash: "b".repeat(64),
            source_artifact_hash: "c".repeat(64),
            append_only_event_ready: true,
            paper_fill_imported: true,
            shadow_fill_synthetic: true,
            divergence_bps: 35,
            divergence_threshold_bps: 100,
            unmatched_paper_fill_count: 0,
            unmatched_shadow_fill_count: 0,
            ..Self::default()
        }
    }

    pub fn validate(&self) -> StockEtfPaperShadowReconciliationVerdict {
        use StockEtfPaperShadowReconciliationBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID {
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
        if self.scope != STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE {
            blockers.push(Blocker::ScopeMismatch);
        }
        if self.authority_scope != AuthorityScope::ReadOnly {
            blockers.push(Blocker::AuthorityScopeMismatch);
        }
        if self.effect_capable {
            blockers.push(Blocker::EffectCapabilityPresent);
        }

        validate_required_fields(self, &mut blockers);
        validate_reconciliation_evidence(self, &mut blockers);
        validate_boundary_flags(self, &mut blockers);

        StockEtfPaperShadowReconciliationVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPaperShadowReconciliationVerdict {
    pub accepted: bool,
    pub blockers: Vec<StockEtfPaperShadowReconciliationBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPaperShadowReconciliationBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    ScopeMismatch,
    AuthorityScopeMismatch,
    EffectCapabilityPresent,
    ReconciliationRunIdMissing,
    PaperOrderLocalIdMissing,
    BrokerOrderIdMissing,
    ExecutionIdMissing,
    CommissionReportIdMissing,
    ShadowSignalIdMissing,
    LifecycleContractHashInvalid,
    EventLogContractHashInvalid,
    PaperFillImportRequestHashInvalid,
    ShadowSignalRequestHashInvalid,
    ShadowFillModelHashInvalid,
    CostModelVersionHashInvalid,
    MarketDataProvenanceHashInvalid,
    PaperShadowDivergenceThresholdHashInvalid,
    PaperShadowLinkHashInvalid,
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
    SourceArtifactHashInvalid,
    AppendOnlyEventNotReady,
    PaperFillNotImported,
    ShadowFillNotSynthetic,
    DivergenceThresholdMissing,
    DivergenceExceedsThreshold,
    UnmatchedPaperFillPresent,
    UnmatchedShadowFillPresent,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    FillImportPerformed,
    ShadowFillGenerated,
    ReconciliationWriterStarted,
    ScorecardWriterStarted,
    DbApplyPerformed,
    OrderRouted,
    BybitPathReused,
    LiveOrTinyLiveAuthorized,
    MarginShortOptionsCfdRequested,
    PythonDirectBrokerWriteRequested,
}

fn validate_required_fields(
    reconciliation: &StockEtfPaperShadowReconciliationV1,
    blockers: &mut Vec<StockEtfPaperShadowReconciliationBlocker>,
) {
    use StockEtfPaperShadowReconciliationBlocker as Blocker;

    if reconciliation.reconciliation_run_id.trim().is_empty() {
        blockers.push(Blocker::ReconciliationRunIdMissing);
    }
    if reconciliation.paper_order_local_id.trim().is_empty() {
        blockers.push(Blocker::PaperOrderLocalIdMissing);
    }
    if reconciliation.broker_order_id.trim().is_empty() {
        blockers.push(Blocker::BrokerOrderIdMissing);
    }
    if reconciliation.execution_id.trim().is_empty() {
        blockers.push(Blocker::ExecutionIdMissing);
    }
    if reconciliation.commission_report_id.trim().is_empty() {
        blockers.push(Blocker::CommissionReportIdMissing);
    }
    if reconciliation.shadow_signal_id.trim().is_empty() {
        blockers.push(Blocker::ShadowSignalIdMissing);
    }
    if !is_sha256_hex(&reconciliation.lifecycle_contract_hash) {
        blockers.push(Blocker::LifecycleContractHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.event_log_contract_hash) {
        blockers.push(Blocker::EventLogContractHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.paper_fill_import_request_hash) {
        blockers.push(Blocker::PaperFillImportRequestHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.shadow_signal_request_hash) {
        blockers.push(Blocker::ShadowSignalRequestHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.shadow_fill_model_hash) {
        blockers.push(Blocker::ShadowFillModelHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.cost_model_version_hash) {
        blockers.push(Blocker::CostModelVersionHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.market_data_provenance_hash) {
        blockers.push(Blocker::MarketDataProvenanceHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.paper_shadow_divergence_threshold_hash) {
        blockers.push(Blocker::PaperShadowDivergenceThresholdHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.paper_shadow_link_hash) {
        blockers.push(Blocker::PaperShadowLinkHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.raw_artifact_hash) {
        blockers.push(Blocker::RawArtifactHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.redacted_summary_hash) {
        blockers.push(Blocker::RedactedSummaryHashInvalid);
    }
    if !is_sha256_hex(&reconciliation.source_artifact_hash) {
        blockers.push(Blocker::SourceArtifactHashInvalid);
    }
}

fn validate_reconciliation_evidence(
    reconciliation: &StockEtfPaperShadowReconciliationV1,
    blockers: &mut Vec<StockEtfPaperShadowReconciliationBlocker>,
) {
    use StockEtfPaperShadowReconciliationBlocker as Blocker;

    if !reconciliation.append_only_event_ready {
        blockers.push(Blocker::AppendOnlyEventNotReady);
    }
    if !reconciliation.paper_fill_imported {
        blockers.push(Blocker::PaperFillNotImported);
    }
    if !reconciliation.shadow_fill_synthetic {
        blockers.push(Blocker::ShadowFillNotSynthetic);
    }
    if reconciliation.divergence_threshold_bps == 0 {
        blockers.push(Blocker::DivergenceThresholdMissing);
    }
    if reconciliation.divergence_threshold_bps > 0
        && reconciliation.divergence_bps > reconciliation.divergence_threshold_bps
    {
        blockers.push(Blocker::DivergenceExceedsThreshold);
    }
    if reconciliation.unmatched_paper_fill_count > 0 {
        blockers.push(Blocker::UnmatchedPaperFillPresent);
    }
    if reconciliation.unmatched_shadow_fill_count > 0 {
        blockers.push(Blocker::UnmatchedShadowFillPresent);
    }
}

fn validate_boundary_flags(
    reconciliation: &StockEtfPaperShadowReconciliationV1,
    blockers: &mut Vec<StockEtfPaperShadowReconciliationBlocker>,
) {
    use StockEtfPaperShadowReconciliationBlocker as Blocker;

    if reconciliation.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if reconciliation.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if reconciliation.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if reconciliation.fill_import_performed {
        blockers.push(Blocker::FillImportPerformed);
    }
    if reconciliation.shadow_fill_generated {
        blockers.push(Blocker::ShadowFillGenerated);
    }
    if reconciliation.reconciliation_writer_started {
        blockers.push(Blocker::ReconciliationWriterStarted);
    }
    if reconciliation.scorecard_writer_started {
        blockers.push(Blocker::ScorecardWriterStarted);
    }
    if reconciliation.db_apply_performed {
        blockers.push(Blocker::DbApplyPerformed);
    }
    if reconciliation.order_routed {
        blockers.push(Blocker::OrderRouted);
    }
    if reconciliation.bybit_path_reused {
        blockers.push(Blocker::BybitPathReused);
    }
    if reconciliation.live_or_tiny_live_authorized {
        blockers.push(Blocker::LiveOrTinyLiveAuthorized);
    }
    if reconciliation.margin_short_options_cfd_requested {
        blockers.push(Blocker::MarginShortOptionsCfdRequested);
    }
    if reconciliation.python_direct_broker_write_requested {
        blockers.push(Blocker::PythonDirectBrokerWriteRequested);
    }
}
