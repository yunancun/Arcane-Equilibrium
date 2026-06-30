//! Stock/ETF IBKR read-only probe request contract.
//!
//! This source-only validator pins the request envelope that must precede any
//! future IBKR health, account, contract-details, or market-data read probe. It
//! does not contact IBKR, import an SDK, create connectors, inspect secrets,
//! route orders, write evidence, apply DB changes, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_non_bybit_api_allowlist::{
    classify_non_bybit_api_action, NonBybitApiAction, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
};
use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::ibkr_phase2_gate::{
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
};
use crate::ibkr_phase2_policies::{
    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID, IBKR_RATE_LIMIT_POLICY_CONTRACT_ID,
    IBKR_REDACTION_POLICY_CONTRACT_ID,
};
use crate::ibkr_phase2_runtime::{
    IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID, IBKR_SECRET_SLOT_CONTRACT_ID,
};
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation,
};

pub const STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID: &str =
    "stock_etf_ibkr_readonly_probe_request_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfIbkrReadonlyProbeKind {
    ServerTime,
    ConnectionHealth,
    AccountSummarySnapshot,
    PortfolioPositionsSnapshot,
    ContractDetails,
    MarketDataSnapshot,
    HistoricalBars,
    OpenPaperOrders,
    PaperExecutionsCommissions,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfIbkrReadonlyProbeRequestV1 {
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
    pub request_id: String,
    pub probe_id: String,
    pub external_surface_gate_contract_id: String,
    pub phase2_gate_artifact_hash: String,
    pub api_allowlist_contract_id: String,
    pub api_allowlist_hash: String,
    pub secret_slot_contract_id: String,
    pub secret_slot_contract_hash: String,
    pub api_session_topology_contract_id: String,
    pub api_session_topology_hash: String,
    pub session_attestation_contract_id: String,
    pub session_attestation_hash: String,
    pub redaction_policy_contract_id: String,
    pub redaction_policy_hash: String,
    pub rate_limit_policy_contract_id: String,
    pub rate_limit_policy_hash: String,
    pub audit_event_policy_contract_id: String,
    pub audit_event_policy_hash: String,
    pub source_artifact_hash: String,
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub order_routed: bool,
    pub paper_order_submitted: bool,
    pub db_apply_performed: bool,
    pub evidence_clock_started: bool,
    pub bybit_path_reused: bool,
    pub live_or_tiny_live_authorized: bool,
    pub margin_short_options_cfd_requested: bool,
    pub account_write_requested: bool,
    pub market_data_entitlement_purchase_requested: bool,
    pub client_portal_web_api_requested: bool,
    pub python_direct_broker_write_requested: bool,
}

impl Default for StockEtfIbkrReadonlyProbeRequestV1 {
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
            request_id: String::new(),
            probe_id: String::new(),
            external_surface_gate_contract_id: String::new(),
            phase2_gate_artifact_hash: String::new(),
            api_allowlist_contract_id: String::new(),
            api_allowlist_hash: String::new(),
            secret_slot_contract_id: String::new(),
            secret_slot_contract_hash: String::new(),
            api_session_topology_contract_id: String::new(),
            api_session_topology_hash: String::new(),
            session_attestation_contract_id: String::new(),
            session_attestation_hash: String::new(),
            redaction_policy_contract_id: String::new(),
            redaction_policy_hash: String::new(),
            rate_limit_policy_contract_id: String::new(),
            rate_limit_policy_hash: String::new(),
            audit_event_policy_contract_id: String::new(),
            audit_event_policy_hash: String::new(),
            source_artifact_hash: String::new(),
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            order_routed: false,
            paper_order_submitted: false,
            db_apply_performed: false,
            evidence_clock_started: false,
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

impl StockEtfIbkrReadonlyProbeRequestV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::ReadOnly,
            probe_kind: StockEtfIbkrReadonlyProbeKind::ConnectionHealth,
            api_action: NonBybitApiAction::ConnectionHealthRead,
            operation: BrokerOperation::HealthRead,
            authority_scope: AuthorityScope::ReadOnly,
            effect_capable: false,
            request_id: "readonly_probe_request_0001".to_string(),
            probe_id: "readonly_probe_0001".to_string(),
            external_surface_gate_contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
            phase2_gate_artifact_hash: "1".repeat(64),
            api_allowlist_contract_id: NON_BYBIT_API_ALLOWLIST_CONTRACT_ID.to_string(),
            api_allowlist_hash: "2".repeat(64),
            secret_slot_contract_id: IBKR_SECRET_SLOT_CONTRACT_ID.to_string(),
            secret_slot_contract_hash: "3".repeat(64),
            api_session_topology_contract_id: IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID.to_string(),
            api_session_topology_hash: "4".repeat(64),
            session_attestation_contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string(),
            session_attestation_hash: "5".repeat(64),
            redaction_policy_contract_id: IBKR_REDACTION_POLICY_CONTRACT_ID.to_string(),
            redaction_policy_hash: "6".repeat(64),
            rate_limit_policy_contract_id: IBKR_RATE_LIMIT_POLICY_CONTRACT_ID.to_string(),
            rate_limit_policy_hash: "7".repeat(64),
            audit_event_policy_contract_id: IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID.to_string(),
            audit_event_policy_hash: "8".repeat(64),
            source_artifact_hash: "9".repeat(64),
            raw_artifact_hash: "a".repeat(64),
            redacted_summary_hash: "b".repeat(64),
            ..Self::default()
        }
    }

    pub fn validate(&self) -> StockEtfIbkrReadonlyProbeVerdict {
        use StockEtfIbkrReadonlyProbeBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID {
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
        if self.environment != BrokerEnvironment::ReadOnly {
            blockers.push(Blocker::EnvironmentNotReadonly);
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

        validate_required_fields(self, &mut blockers);
        validate_boundary_flags(self, &mut blockers);

        StockEtfIbkrReadonlyProbeVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfIbkrReadonlyProbeVerdict {
    pub accepted: bool,
    pub blockers: Vec<StockEtfIbkrReadonlyProbeBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfIbkrReadonlyProbeBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentNotReadonly,
    ProbeActionMismatch,
    OperationMismatch,
    AuthorityScopeMismatch,
    EffectCapabilityPresent,
    ApiActionNotReadAllowed,
    RequestIdMissing,
    ProbeIdMissing,
    ExternalSurfaceGateContractIdMismatch,
    Phase2GateArtifactHashInvalid,
    ApiAllowlistContractIdMismatch,
    ApiAllowlistHashInvalid,
    SecretSlotContractIdMismatch,
    SecretSlotContractHashInvalid,
    ApiSessionTopologyContractIdMismatch,
    ApiSessionTopologyHashInvalid,
    SessionAttestationContractIdMismatch,
    SessionAttestationHashInvalid,
    RedactionPolicyContractIdMismatch,
    RedactionPolicyHashInvalid,
    RateLimitPolicyContractIdMismatch,
    RateLimitPolicyHashInvalid,
    AuditEventPolicyContractIdMismatch,
    AuditEventPolicyHashInvalid,
    SourceArtifactHashInvalid,
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    OrderRouted,
    PaperOrderSubmitted,
    DbApplyPerformed,
    EvidenceClockStarted,
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

fn validate_required_fields(
    request: &StockEtfIbkrReadonlyProbeRequestV1,
    blockers: &mut Vec<StockEtfIbkrReadonlyProbeBlocker>,
) {
    use StockEtfIbkrReadonlyProbeBlocker as Blocker;

    if request.request_id.trim().is_empty() {
        blockers.push(Blocker::RequestIdMissing);
    }
    if request.probe_id.trim().is_empty() {
        blockers.push(Blocker::ProbeIdMissing);
    }
    if request.external_surface_gate_contract_id != IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID {
        blockers.push(Blocker::ExternalSurfaceGateContractIdMismatch);
    }
    if !is_sha256_hex(&request.phase2_gate_artifact_hash) {
        blockers.push(Blocker::Phase2GateArtifactHashInvalid);
    }
    if request.api_allowlist_contract_id != NON_BYBIT_API_ALLOWLIST_CONTRACT_ID {
        blockers.push(Blocker::ApiAllowlistContractIdMismatch);
    }
    if !is_sha256_hex(&request.api_allowlist_hash) {
        blockers.push(Blocker::ApiAllowlistHashInvalid);
    }
    if request.secret_slot_contract_id != IBKR_SECRET_SLOT_CONTRACT_ID {
        blockers.push(Blocker::SecretSlotContractIdMismatch);
    }
    if !is_sha256_hex(&request.secret_slot_contract_hash) {
        blockers.push(Blocker::SecretSlotContractHashInvalid);
    }
    if request.api_session_topology_contract_id != IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID {
        blockers.push(Blocker::ApiSessionTopologyContractIdMismatch);
    }
    if !is_sha256_hex(&request.api_session_topology_hash) {
        blockers.push(Blocker::ApiSessionTopologyHashInvalid);
    }
    if request.session_attestation_contract_id != IBKR_SESSION_ATTESTATION_CONTRACT_ID {
        blockers.push(Blocker::SessionAttestationContractIdMismatch);
    }
    if !is_sha256_hex(&request.session_attestation_hash) {
        blockers.push(Blocker::SessionAttestationHashInvalid);
    }
    if request.redaction_policy_contract_id != IBKR_REDACTION_POLICY_CONTRACT_ID {
        blockers.push(Blocker::RedactionPolicyContractIdMismatch);
    }
    if !is_sha256_hex(&request.redaction_policy_hash) {
        blockers.push(Blocker::RedactionPolicyHashInvalid);
    }
    if request.rate_limit_policy_contract_id != IBKR_RATE_LIMIT_POLICY_CONTRACT_ID {
        blockers.push(Blocker::RateLimitPolicyContractIdMismatch);
    }
    if !is_sha256_hex(&request.rate_limit_policy_hash) {
        blockers.push(Blocker::RateLimitPolicyHashInvalid);
    }
    if request.audit_event_policy_contract_id != IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID {
        blockers.push(Blocker::AuditEventPolicyContractIdMismatch);
    }
    if !is_sha256_hex(&request.audit_event_policy_hash) {
        blockers.push(Blocker::AuditEventPolicyHashInvalid);
    }
    if !is_sha256_hex(&request.source_artifact_hash) {
        blockers.push(Blocker::SourceArtifactHashInvalid);
    }
    if !is_sha256_hex(&request.raw_artifact_hash) {
        blockers.push(Blocker::RawArtifactHashInvalid);
    }
    if !is_sha256_hex(&request.redacted_summary_hash) {
        blockers.push(Blocker::RedactedSummaryHashInvalid);
    }
}

fn validate_boundary_flags(
    request: &StockEtfIbkrReadonlyProbeRequestV1,
    blockers: &mut Vec<StockEtfIbkrReadonlyProbeBlocker>,
) {
    use StockEtfIbkrReadonlyProbeBlocker as Blocker;

    if request.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if request.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if request.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if request.order_routed {
        blockers.push(Blocker::OrderRouted);
    }
    if request.paper_order_submitted {
        blockers.push(Blocker::PaperOrderSubmitted);
    }
    if request.db_apply_performed {
        blockers.push(Blocker::DbApplyPerformed);
    }
    if request.evidence_clock_started {
        blockers.push(Blocker::EvidenceClockStarted);
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
