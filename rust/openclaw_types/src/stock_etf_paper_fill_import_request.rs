//! Stock/ETF paper fill import request contract.
//!
//! This source-only validator pins the fill-import request shape that must sit
//! between lane-scoped IPC and broker lifecycle reconstruction. It does not
//! contact IBKR, create connectors, read secrets, import fills, mutate the DB,
//! route orders, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_paper_lifecycle::{
    IbkrPaperStaleStatePolicy, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
};
use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::ibkr_phase2_policies::IBKR_REDACTION_POLICY_CONTRACT_ID;
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation,
    IbkrPaperOrderLifecycleState,
};
use crate::stock_etf_lane_scoped_ipc::StockEtfLaneScopedIpcMethod;

pub const STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID: &str =
    "stock_etf_paper_fill_import_request_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPaperFillImportRequestV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub request_method: StockEtfLaneScopedIpcMethod,
    pub operation: BrokerOperation,
    pub authority_scope: AuthorityScope,
    pub effect_capable: bool,
    pub request_id: String,
    pub session_attestation_hash: String,
    pub lifecycle_contract_id: String,
    pub lifecycle_contract_hash: String,
    pub event_log_contract_id: String,
    pub event_log_contract_hash: String,
    pub redaction_policy_contract_id: String,
    pub redaction_policy_hash: String,
    pub source_artifact_hash: String,
    pub reconciliation_run_id: String,
    pub broker_order_id: String,
    pub execution_id: String,
    pub commission_report_id: String,
    pub import_idempotency_key: String,
    pub observed_order_state: Option<IbkrPaperOrderLifecycleState>,
    pub stale_state_policy: Option<IbkrPaperStaleStatePolicy>,
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
    pub duplicate_import_detected: bool,
    pub stale_unknown_state_without_policy: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub fill_import_performed: bool,
    pub db_apply_performed: bool,
    pub order_routed: bool,
    pub bybit_path_reused: bool,
    pub live_or_tiny_live_authorized: bool,
    pub margin_short_options_cfd_requested: bool,
    pub python_direct_broker_write_requested: bool,
}

impl Default for StockEtfPaperFillImportRequestV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            request_method: StockEtfLaneScopedIpcMethod::UnknownDenied,
            operation: BrokerOperation::TransferOrAccountWrite,
            authority_scope: AuthorityScope::Denied,
            effect_capable: false,
            request_id: String::new(),
            session_attestation_hash: String::new(),
            lifecycle_contract_id: String::new(),
            lifecycle_contract_hash: String::new(),
            event_log_contract_id: String::new(),
            event_log_contract_hash: String::new(),
            redaction_policy_contract_id: String::new(),
            redaction_policy_hash: String::new(),
            source_artifact_hash: String::new(),
            reconciliation_run_id: String::new(),
            broker_order_id: String::new(),
            execution_id: String::new(),
            commission_report_id: String::new(),
            import_idempotency_key: String::new(),
            observed_order_state: None,
            stale_state_policy: None,
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
            duplicate_import_detected: false,
            stale_unknown_state_without_policy: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            fill_import_performed: false,
            db_apply_performed: false,
            order_routed: false,
            bybit_path_reused: false,
            live_or_tiny_live_authorized: false,
            margin_short_options_cfd_requested: false,
            python_direct_broker_write_requested: false,
        }
    }
}

impl StockEtfPaperFillImportRequestV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            request_method: StockEtfLaneScopedIpcMethod::ImportPaperFills,
            operation: BrokerOperation::PaperOrderFillImport,
            authority_scope: AuthorityScope::ReadOnly,
            effect_capable: false,
            request_id: "fill_import_request_0001".to_string(),
            session_attestation_hash: "1".repeat(64),
            lifecycle_contract_id: IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID.to_string(),
            lifecycle_contract_hash: "2".repeat(64),
            event_log_contract_id: BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID.to_string(),
            event_log_contract_hash: "3".repeat(64),
            redaction_policy_contract_id: IBKR_REDACTION_POLICY_CONTRACT_ID.to_string(),
            redaction_policy_hash: "4".repeat(64),
            source_artifact_hash: "5".repeat(64),
            reconciliation_run_id: "reconcile_run_0001".to_string(),
            broker_order_id: "paper_broker_order_0001".to_string(),
            execution_id: "paper_execution_0001".to_string(),
            commission_report_id: "paper_commission_0001".to_string(),
            import_idempotency_key: "fill_import_idem_0001".to_string(),
            observed_order_state: Some(IbkrPaperOrderLifecycleState::Filled),
            stale_state_policy: Some(IbkrPaperStaleStatePolicy::PreserveTerminalWithEvidence),
            raw_artifact_hash: "6".repeat(64),
            redacted_summary_hash: "7".repeat(64),
            ..Self::default()
        }
    }

    pub fn validate(&self) -> StockEtfPaperFillImportVerdict {
        use StockEtfPaperFillImportBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID {
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
            blockers.push(Blocker::EnvironmentNotPaper);
        }
        if self.request_method != StockEtfLaneScopedIpcMethod::ImportPaperFills {
            blockers.push(Blocker::RequestMethodMismatch);
        }
        if self.operation != BrokerOperation::PaperOrderFillImport {
            blockers.push(Blocker::OperationMismatch);
        }
        if self.authority_scope != AuthorityScope::ReadOnly {
            blockers.push(Blocker::AuthorityScopeMismatch);
        }
        if self.effect_capable {
            blockers.push(Blocker::EffectCapabilityPresent);
        }

        validate_required_fields(self, &mut blockers);
        validate_boundary_flags(self, &mut blockers);

        StockEtfPaperFillImportVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPaperFillImportVerdict {
    pub accepted: bool,
    pub blockers: Vec<StockEtfPaperFillImportBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPaperFillImportBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentNotPaper,
    RequestMethodMismatch,
    OperationMismatch,
    AuthorityScopeMismatch,
    EffectCapabilityPresent,
    RequestIdMissing,
    SessionAttestationHashInvalid,
    LifecycleContractIdMismatch,
    LifecycleContractHashInvalid,
    EventLogContractIdMismatch,
    EventLogContractHashInvalid,
    RedactionPolicyContractIdMismatch,
    RedactionPolicyHashInvalid,
    SourceArtifactHashInvalid,
    ReconciliationRunIdMissing,
    BrokerOrderIdMissing,
    ExecutionIdMissing,
    CommissionReportIdMissing,
    ImportIdempotencyKeyMissing,
    ObservedOrderStateMissing,
    StaleStatePolicyMissing,
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
    DuplicateImportDetected,
    StaleUnknownStateWithoutPolicy,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    FillImportPerformed,
    DbApplyPerformed,
    OrderRouted,
    BybitPathReused,
    LiveOrTinyLiveAuthorized,
    MarginShortOptionsCfdRequested,
    PythonDirectBrokerWriteRequested,
}

fn validate_required_fields(
    request: &StockEtfPaperFillImportRequestV1,
    blockers: &mut Vec<StockEtfPaperFillImportBlocker>,
) {
    use StockEtfPaperFillImportBlocker as Blocker;

    if request.request_id.trim().is_empty() {
        blockers.push(Blocker::RequestIdMissing);
    }
    if !is_sha256_hex(&request.session_attestation_hash) {
        blockers.push(Blocker::SessionAttestationHashInvalid);
    }
    if request.lifecycle_contract_id != IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID {
        blockers.push(Blocker::LifecycleContractIdMismatch);
    }
    if !is_sha256_hex(&request.lifecycle_contract_hash) {
        blockers.push(Blocker::LifecycleContractHashInvalid);
    }
    if request.event_log_contract_id != BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID {
        blockers.push(Blocker::EventLogContractIdMismatch);
    }
    if !is_sha256_hex(&request.event_log_contract_hash) {
        blockers.push(Blocker::EventLogContractHashInvalid);
    }
    if request.redaction_policy_contract_id != IBKR_REDACTION_POLICY_CONTRACT_ID {
        blockers.push(Blocker::RedactionPolicyContractIdMismatch);
    }
    if !is_sha256_hex(&request.redaction_policy_hash) {
        blockers.push(Blocker::RedactionPolicyHashInvalid);
    }
    if !is_sha256_hex(&request.source_artifact_hash) {
        blockers.push(Blocker::SourceArtifactHashInvalid);
    }
    if request.reconciliation_run_id.trim().is_empty() {
        blockers.push(Blocker::ReconciliationRunIdMissing);
    }
    if request.broker_order_id.trim().is_empty() {
        blockers.push(Blocker::BrokerOrderIdMissing);
    }
    if request.execution_id.trim().is_empty() {
        blockers.push(Blocker::ExecutionIdMissing);
    }
    if request.commission_report_id.trim().is_empty() {
        blockers.push(Blocker::CommissionReportIdMissing);
    }
    if request.import_idempotency_key.trim().is_empty() {
        blockers.push(Blocker::ImportIdempotencyKeyMissing);
    }
    if request.observed_order_state.is_none() {
        blockers.push(Blocker::ObservedOrderStateMissing);
    }
    if request.stale_state_policy.is_none() {
        blockers.push(Blocker::StaleStatePolicyMissing);
    }
    if !is_sha256_hex(&request.raw_artifact_hash) {
        blockers.push(Blocker::RawArtifactHashInvalid);
    }
    if !is_sha256_hex(&request.redacted_summary_hash) {
        blockers.push(Blocker::RedactedSummaryHashInvalid);
    }
    if request.duplicate_import_detected {
        blockers.push(Blocker::DuplicateImportDetected);
    }
    if request.stale_unknown_state_without_policy
        || matches!(
            request.observed_order_state,
            Some(IbkrPaperOrderLifecycleState::StateUnknown)
        ) && request.stale_state_policy.is_none()
    {
        blockers.push(Blocker::StaleUnknownStateWithoutPolicy);
    }
}

fn validate_boundary_flags(
    request: &StockEtfPaperFillImportRequestV1,
    blockers: &mut Vec<StockEtfPaperFillImportBlocker>,
) {
    use StockEtfPaperFillImportBlocker as Blocker;

    if request.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if request.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if request.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if request.fill_import_performed {
        blockers.push(Blocker::FillImportPerformed);
    }
    if request.db_apply_performed {
        blockers.push(Blocker::DbApplyPerformed);
    }
    if request.order_routed {
        blockers.push(Blocker::OrderRouted);
    }
    if request.bybit_path_reused {
        blockers.push(Blocker::BybitPathReused);
    }
    if request.live_or_tiny_live_authorized {
        blockers.push(Blocker::LiveOrTinyLiveAuthorized);
    }
    if request.margin_short_options_cfd_requested {
        blockers.push(Blocker::MarginShortOptionsCfdRequested);
    }
    if request.python_direct_broker_write_requested {
        blockers.push(Blocker::PythonDirectBrokerWriteRequested);
    }
}
