//! Stock/ETF IBKR read-only probe result import request contract.
//!
//! This source-only validator pins the envelope that must exist before any
//! future sanitized IBKR read-only probe result can be imported into evidence
//! inputs. It does not contact IBKR, import an SDK, start connectors, inspect
//! secrets, write evidence, apply DB changes, route orders, or change Bybit.

use serde::{Deserialize, Serialize};

use crate::ibkr_non_bybit_api_allowlist::{
    classify_non_bybit_api_action, NonBybitApiAction, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
};
use crate::ibkr_paper_lifecycle::BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID;
use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::ibkr_phase2_gate::IBKR_SESSION_ATTESTATION_CONTRACT_ID;
use crate::ibkr_phase2_policies::{
    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID, IBKR_REDACTION_POLICY_CONTRACT_ID,
};
use crate::stock_etf_ibkr_readonly_probe_request::{
    StockEtfIbkrReadonlyProbeKind, STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
};
use crate::stock_etf_instrument_identity::STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID;
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation,
};
use crate::stock_etf_phase3_evidence::STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID;
use crate::stock_etf_scorecard_inputs::BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID;

pub const STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID: &str =
    "stock_etf_ibkr_readonly_probe_result_import_request_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfIbkrReadonlyProbeResultImportRequestV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub probe_kind: StockEtfIbkrReadonlyProbeKind,
    pub api_action: NonBybitApiAction,
    pub operation: BrokerOperation,
    pub authority_scope: AuthorityScope,
    pub effect_capable: bool,
    pub result_import_request_id: String,
    pub request_id: String,
    pub probe_id: String,
    pub readonly_probe_request_contract_id: String,
    pub readonly_probe_request_hash: String,
    pub session_attestation_contract_id: String,
    pub session_attestation_hash: String,
    pub api_allowlist_contract_id: String,
    pub api_allowlist_hash: String,
    pub redaction_policy_contract_id: String,
    pub redaction_policy_hash: String,
    pub audit_event_policy_contract_id: String,
    pub audit_event_policy_hash: String,
    pub account_cash_ledger_contract_id: String,
    pub account_cash_ledger_hash: String,
    pub market_data_provenance_contract_id: String,
    pub market_data_provenance_hash: String,
    pub instrument_identity_contract_id: String,
    pub instrument_identity_hash: String,
    pub broker_lifecycle_event_log_contract_id: String,
    pub broker_lifecycle_event_log_hash: String,
    pub health_snapshot_hash: String,
    pub result_payload_hash: String,
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
    pub source_artifact_hash: String,
    pub result_as_of_ms: u64,
    pub import_requested_at_ms: u64,
    pub idempotency_key: String,
    pub duplicate_import_detected: bool,
    pub stale_result_without_manual_review: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub result_import_performed: bool,
    pub evidence_writer_started: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub order_routed: bool,
    pub paper_order_submitted: bool,
    pub bybit_path_reused: bool,
    pub live_or_tiny_live_authorized: bool,
    pub margin_short_options_cfd_requested: bool,
    pub account_write_requested: bool,
    pub market_data_entitlement_purchase_requested: bool,
    pub client_portal_web_api_requested: bool,
    pub python_direct_broker_write_requested: bool,
}

impl Default for StockEtfIbkrReadonlyProbeResultImportRequestV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            probe_kind: StockEtfIbkrReadonlyProbeKind::ConnectionHealth,
            api_action: NonBybitApiAction::ClientPortalWebApiUse,
            operation: BrokerOperation::TransferOrAccountWrite,
            authority_scope: AuthorityScope::Denied,
            effect_capable: false,
            result_import_request_id: String::new(),
            request_id: String::new(),
            probe_id: String::new(),
            readonly_probe_request_contract_id: String::new(),
            readonly_probe_request_hash: String::new(),
            session_attestation_contract_id: String::new(),
            session_attestation_hash: String::new(),
            api_allowlist_contract_id: String::new(),
            api_allowlist_hash: String::new(),
            redaction_policy_contract_id: String::new(),
            redaction_policy_hash: String::new(),
            audit_event_policy_contract_id: String::new(),
            audit_event_policy_hash: String::new(),
            account_cash_ledger_contract_id: String::new(),
            account_cash_ledger_hash: String::new(),
            market_data_provenance_contract_id: String::new(),
            market_data_provenance_hash: String::new(),
            instrument_identity_contract_id: String::new(),
            instrument_identity_hash: String::new(),
            broker_lifecycle_event_log_contract_id: String::new(),
            broker_lifecycle_event_log_hash: String::new(),
            health_snapshot_hash: String::new(),
            result_payload_hash: String::new(),
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
            source_artifact_hash: String::new(),
            result_as_of_ms: 0,
            import_requested_at_ms: 0,
            idempotency_key: String::new(),
            duplicate_import_detected: false,
            stale_result_without_manual_review: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            result_import_performed: false,
            evidence_writer_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            order_routed: false,
            paper_order_submitted: false,
            bybit_path_reused: false,
            live_or_tiny_live_authorized: false,
            margin_short_options_cfd_requested: false,
            account_write_requested: false,
            market_data_entitlement_purchase_requested: false,
            client_portal_web_api_requested: false,
            python_direct_broker_write_requested: false,
        }
    }
}

impl StockEtfIbkrReadonlyProbeResultImportRequestV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID
                .to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::ReadOnly,
            probe_kind: StockEtfIbkrReadonlyProbeKind::ConnectionHealth,
            api_action: NonBybitApiAction::ConnectionHealthRead,
            operation: BrokerOperation::HealthRead,
            authority_scope: AuthorityScope::ReadOnly,
            effect_capable: false,
            result_import_request_id: "readonly_probe_result_import_request_0001".to_string(),
            request_id: "readonly_probe_request_0001".to_string(),
            probe_id: "readonly_probe_0001".to_string(),
            readonly_probe_request_contract_id: STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID
                .to_string(),
            readonly_probe_request_hash: "1".repeat(64),
            session_attestation_contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string(),
            session_attestation_hash: "2".repeat(64),
            api_allowlist_contract_id: NON_BYBIT_API_ALLOWLIST_CONTRACT_ID.to_string(),
            api_allowlist_hash: "3".repeat(64),
            redaction_policy_contract_id: IBKR_REDACTION_POLICY_CONTRACT_ID.to_string(),
            redaction_policy_hash: "4".repeat(64),
            audit_event_policy_contract_id: IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID.to_string(),
            audit_event_policy_hash: "5".repeat(64),
            health_snapshot_hash: "6".repeat(64),
            result_payload_hash: "7".repeat(64),
            raw_artifact_hash: "8".repeat(64),
            redacted_summary_hash: "9".repeat(64),
            source_artifact_hash: "a".repeat(64),
            result_as_of_ms: 1_772_233_000_000,
            import_requested_at_ms: 1_772_233_001_000,
            idempotency_key: "readonly_probe_result_import_idem_0001".to_string(),
            ..Self::default()
        }
    }

    pub fn validate(&self) -> StockEtfIbkrReadonlyProbeResultImportVerdict {
        use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID {
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
        if !matches!(
            self.environment,
            BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper
        ) {
            blockers.push(Blocker::EnvironmentDenied);
        }
        if self.api_action != expected_api_action(self.probe_kind) {
            blockers.push(Blocker::ProbeActionMismatch);
        }
        if self.operation != expected_operation(self.probe_kind) {
            blockers.push(Blocker::OperationMismatch);
        }
        if self.authority_scope != AuthorityScope::ReadOnly {
            blockers.push(Blocker::AuthorityScopeMismatch);
        }
        if self.effect_capable {
            blockers.push(Blocker::EffectCapabilityPresent);
        }

        let decision = classify_non_bybit_api_action(self.api_action);
        if decision.denied
            || !decision.allowed_after_external_gate
            || !decision.requires_external_surface_gate
            || decision.requires_paper_order_gates
        {
            blockers.push(Blocker::ApiActionNotReadAllowed);
        }

        validate_required_lineage(self, &mut blockers);
        validate_kind_lineage(self, &mut blockers);
        validate_boundary_flags(self, &mut blockers);

        StockEtfIbkrReadonlyProbeResultImportVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfIbkrReadonlyProbeResultImportVerdict {
    pub accepted: bool,
    pub blockers: Vec<StockEtfIbkrReadonlyProbeResultImportBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfIbkrReadonlyProbeResultImportBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentDenied,
    ProbeActionMismatch,
    OperationMismatch,
    AuthorityScopeMismatch,
    EffectCapabilityPresent,
    ApiActionNotReadAllowed,
    ResultImportRequestIdMissing,
    RequestIdMissing,
    ProbeIdMissing,
    ReadonlyProbeRequestContractIdMismatch,
    ReadonlyProbeRequestHashInvalid,
    SessionAttestationContractIdMismatch,
    SessionAttestationHashInvalid,
    ApiAllowlistContractIdMismatch,
    ApiAllowlistHashInvalid,
    RedactionPolicyContractIdMismatch,
    RedactionPolicyHashInvalid,
    AuditEventPolicyContractIdMismatch,
    AuditEventPolicyHashInvalid,
    AccountCashLedgerContractIdMismatch,
    AccountCashLedgerHashInvalid,
    MarketDataProvenanceContractIdMismatch,
    MarketDataProvenanceHashInvalid,
    InstrumentIdentityContractIdMismatch,
    InstrumentIdentityHashInvalid,
    BrokerLifecycleEventLogContractIdMismatch,
    BrokerLifecycleEventLogHashInvalid,
    HealthSnapshotHashInvalid,
    ResultPayloadHashInvalid,
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
    SourceArtifactHashInvalid,
    ResultAsOfMissing,
    ImportRequestedAtMissing,
    ResultAsOfAfterImportRequested,
    IdempotencyKeyMissing,
    DuplicateImportDetected,
    StaleResultWithoutManualReview,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    ResultImportPerformed,
    EvidenceWriterStarted,
    ScorecardWriterStarted,
    DbApplyPerformed,
    OrderRouted,
    PaperOrderSubmitted,
    BybitPathReused,
    LiveOrTinyLiveAuthorized,
    MarginShortOptionsCfdRequested,
    AccountWriteRequested,
    MarketDataEntitlementPurchaseRequested,
    ClientPortalWebApiRequested,
    PythonDirectBrokerWriteRequested,
}

fn expected_api_action(kind: StockEtfIbkrReadonlyProbeKind) -> NonBybitApiAction {
    match kind {
        StockEtfIbkrReadonlyProbeKind::ServerTime => NonBybitApiAction::ServerTimeRead,
        StockEtfIbkrReadonlyProbeKind::ConnectionHealth => NonBybitApiAction::ConnectionHealthRead,
        StockEtfIbkrReadonlyProbeKind::AccountSummarySnapshot => {
            NonBybitApiAction::AccountSummarySnapshotRead
        }
        StockEtfIbkrReadonlyProbeKind::PortfolioPositionsSnapshot => {
            NonBybitApiAction::PortfolioPositionsSnapshotRead
        }
        StockEtfIbkrReadonlyProbeKind::ContractDetails => NonBybitApiAction::ContractDetailsRead,
        StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot => {
            NonBybitApiAction::MarketDataSnapshotRead
        }
        StockEtfIbkrReadonlyProbeKind::HistoricalBars => NonBybitApiAction::HistoricalBarsRead,
        StockEtfIbkrReadonlyProbeKind::OpenPaperOrders => NonBybitApiAction::OpenPaperOrdersRead,
        StockEtfIbkrReadonlyProbeKind::PaperExecutionsCommissions => {
            NonBybitApiAction::PaperExecutionsCommissionsRead
        }
    }
}

fn expected_operation(kind: StockEtfIbkrReadonlyProbeKind) -> BrokerOperation {
    match kind {
        StockEtfIbkrReadonlyProbeKind::ServerTime
        | StockEtfIbkrReadonlyProbeKind::ConnectionHealth => BrokerOperation::HealthRead,
        StockEtfIbkrReadonlyProbeKind::AccountSummarySnapshot
        | StockEtfIbkrReadonlyProbeKind::PortfolioPositionsSnapshot
        | StockEtfIbkrReadonlyProbeKind::OpenPaperOrders
        | StockEtfIbkrReadonlyProbeKind::PaperExecutionsCommissions => {
            BrokerOperation::AccountSnapshotRead
        }
        StockEtfIbkrReadonlyProbeKind::ContractDetails => BrokerOperation::ContractDetailsRead,
        StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot
        | StockEtfIbkrReadonlyProbeKind::HistoricalBars => BrokerOperation::MarketDataRead,
    }
}

fn validate_required_lineage(
    request: &StockEtfIbkrReadonlyProbeResultImportRequestV1,
    blockers: &mut Vec<StockEtfIbkrReadonlyProbeResultImportBlocker>,
) {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    if request.result_import_request_id.trim().is_empty() {
        blockers.push(Blocker::ResultImportRequestIdMissing);
    }
    if request.request_id.trim().is_empty() {
        blockers.push(Blocker::RequestIdMissing);
    }
    if request.probe_id.trim().is_empty() {
        blockers.push(Blocker::ProbeIdMissing);
    }
    if request.readonly_probe_request_contract_id
        != STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID
    {
        blockers.push(Blocker::ReadonlyProbeRequestContractIdMismatch);
    }
    if !is_sha256_hex(&request.readonly_probe_request_hash) {
        blockers.push(Blocker::ReadonlyProbeRequestHashInvalid);
    }
    if request.session_attestation_contract_id != IBKR_SESSION_ATTESTATION_CONTRACT_ID {
        blockers.push(Blocker::SessionAttestationContractIdMismatch);
    }
    if !is_sha256_hex(&request.session_attestation_hash) {
        blockers.push(Blocker::SessionAttestationHashInvalid);
    }
    if request.api_allowlist_contract_id != NON_BYBIT_API_ALLOWLIST_CONTRACT_ID {
        blockers.push(Blocker::ApiAllowlistContractIdMismatch);
    }
    if !is_sha256_hex(&request.api_allowlist_hash) {
        blockers.push(Blocker::ApiAllowlistHashInvalid);
    }
    if request.redaction_policy_contract_id != IBKR_REDACTION_POLICY_CONTRACT_ID {
        blockers.push(Blocker::RedactionPolicyContractIdMismatch);
    }
    if !is_sha256_hex(&request.redaction_policy_hash) {
        blockers.push(Blocker::RedactionPolicyHashInvalid);
    }
    if request.audit_event_policy_contract_id != IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID {
        blockers.push(Blocker::AuditEventPolicyContractIdMismatch);
    }
    if !is_sha256_hex(&request.audit_event_policy_hash) {
        blockers.push(Blocker::AuditEventPolicyHashInvalid);
    }
    if !is_sha256_hex(&request.result_payload_hash) {
        blockers.push(Blocker::ResultPayloadHashInvalid);
    }
    if !is_sha256_hex(&request.raw_artifact_hash) {
        blockers.push(Blocker::RawArtifactHashInvalid);
    }
    if !is_sha256_hex(&request.redacted_summary_hash) {
        blockers.push(Blocker::RedactedSummaryHashInvalid);
    }
    if !is_sha256_hex(&request.source_artifact_hash) {
        blockers.push(Blocker::SourceArtifactHashInvalid);
    }
    if request.result_as_of_ms == 0 {
        blockers.push(Blocker::ResultAsOfMissing);
    }
    if request.import_requested_at_ms == 0 {
        blockers.push(Blocker::ImportRequestedAtMissing);
    }
    if request.result_as_of_ms > request.import_requested_at_ms {
        blockers.push(Blocker::ResultAsOfAfterImportRequested);
    }
    if request.idempotency_key.trim().is_empty() {
        blockers.push(Blocker::IdempotencyKeyMissing);
    }
    if request.duplicate_import_detected {
        blockers.push(Blocker::DuplicateImportDetected);
    }
    if request.stale_result_without_manual_review {
        blockers.push(Blocker::StaleResultWithoutManualReview);
    }
}

fn validate_kind_lineage(
    request: &StockEtfIbkrReadonlyProbeResultImportRequestV1,
    blockers: &mut Vec<StockEtfIbkrReadonlyProbeResultImportBlocker>,
) {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    match request.probe_kind {
        StockEtfIbkrReadonlyProbeKind::ServerTime
        | StockEtfIbkrReadonlyProbeKind::ConnectionHealth => {
            if !is_sha256_hex(&request.health_snapshot_hash) {
                blockers.push(Blocker::HealthSnapshotHashInvalid);
            }
        }
        StockEtfIbkrReadonlyProbeKind::AccountSummarySnapshot
        | StockEtfIbkrReadonlyProbeKind::PortfolioPositionsSnapshot => {
            if request.account_cash_ledger_contract_id
                != BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID
            {
                blockers.push(Blocker::AccountCashLedgerContractIdMismatch);
            }
            if !is_sha256_hex(&request.account_cash_ledger_hash) {
                blockers.push(Blocker::AccountCashLedgerHashInvalid);
            }
        }
        StockEtfIbkrReadonlyProbeKind::ContractDetails => {
            if request.instrument_identity_contract_id != STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID
            {
                blockers.push(Blocker::InstrumentIdentityContractIdMismatch);
            }
            if !is_sha256_hex(&request.instrument_identity_hash) {
                blockers.push(Blocker::InstrumentIdentityHashInvalid);
            }
        }
        StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot
        | StockEtfIbkrReadonlyProbeKind::HistoricalBars => {
            if request.market_data_provenance_contract_id
                != STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID
            {
                blockers.push(Blocker::MarketDataProvenanceContractIdMismatch);
            }
            if !is_sha256_hex(&request.market_data_provenance_hash) {
                blockers.push(Blocker::MarketDataProvenanceHashInvalid);
            }
        }
        StockEtfIbkrReadonlyProbeKind::OpenPaperOrders
        | StockEtfIbkrReadonlyProbeKind::PaperExecutionsCommissions => {
            if request.broker_lifecycle_event_log_contract_id
                != BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID
            {
                blockers.push(Blocker::BrokerLifecycleEventLogContractIdMismatch);
            }
            if !is_sha256_hex(&request.broker_lifecycle_event_log_hash) {
                blockers.push(Blocker::BrokerLifecycleEventLogHashInvalid);
            }
        }
    }
}

fn validate_boundary_flags(
    request: &StockEtfIbkrReadonlyProbeResultImportRequestV1,
    blockers: &mut Vec<StockEtfIbkrReadonlyProbeResultImportBlocker>,
) {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    if request.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if request.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if request.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if request.result_import_performed {
        blockers.push(Blocker::ResultImportPerformed);
    }
    if request.evidence_writer_started {
        blockers.push(Blocker::EvidenceWriterStarted);
    }
    if request.scorecard_writer_started {
        blockers.push(Blocker::ScorecardWriterStarted);
    }
    if request.db_apply_performed {
        blockers.push(Blocker::DbApplyPerformed);
    }
    if request.order_routed {
        blockers.push(Blocker::OrderRouted);
    }
    if request.paper_order_submitted {
        blockers.push(Blocker::PaperOrderSubmitted);
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
    if request.account_write_requested {
        blockers.push(Blocker::AccountWriteRequested);
    }
    if request.market_data_entitlement_purchase_requested {
        blockers.push(Blocker::MarketDataEntitlementPurchaseRequested);
    }
    if request.client_portal_web_api_requested {
        blockers.push(Blocker::ClientPortalWebApiRequested);
    }
    if request.python_direct_broker_write_requested {
        blockers.push(Blocker::PythonDirectBrokerWriteRequested);
    }
}
