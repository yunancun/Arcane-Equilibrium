//! ADR-0048 Stock/ETF lane-scoped IPC contract.
//!
//! This source-only validator pins the Rust IPC method matrix that must remain
//! separate from existing Bybit/Paper command paths. It does not start an IPC
//! server, contact IBKR, inspect secrets, create connectors, route orders, or
//! change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_paper_lifecycle::{
    BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID, IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
};
use crate::ibkr_phase2_gate::{
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
};
use crate::ibkr_phase2_policies::IBKR_REDACTION_POLICY_CONTRACT_ID;
use crate::stock_etf_audit_events::STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID;
use crate::stock_etf_broker_capability_registry::STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID;
use crate::stock_etf_instrument_identity::STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID;
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerOperation, StockEtfDenialReason,
};
use crate::stock_etf_phase3_evidence::STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID;
use crate::stock_etf_pit_universe::STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID;
use crate::stock_etf_risk_policy::STOCK_ETF_RISK_POLICY_CONTRACT_ID;
use crate::stock_etf_scorecard_inputs::STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID;
use crate::stock_etf_strategy_hypothesis::STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID;

pub const STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID: &str = "lane_scoped_ipc_v1";
pub const STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID: &str = "stock_etf_scoped_authorization_v1";

const REQUIRED_METHODS: &[StockEtfLaneScopedIpcMethod] = &[
    StockEtfLaneScopedIpcMethod::GetLaneStatus,
    StockEtfLaneScopedIpcMethod::GetReadiness,
    StockEtfLaneScopedIpcMethod::GetDataFoundationStatus,
    StockEtfLaneScopedIpcMethod::GetPolicyStatus,
    StockEtfLaneScopedIpcMethod::GetAccountStatus,
    StockEtfLaneScopedIpcMethod::GetPaperStatus,
    StockEtfLaneScopedIpcMethod::GetReconciliationStatus,
    StockEtfLaneScopedIpcMethod::GetScorecardStatus,
    StockEtfLaneScopedIpcMethod::GetLaunchStatus,
    StockEtfLaneScopedIpcMethod::PreviewPaperOrder,
    StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
    StockEtfLaneScopedIpcMethod::CancelPaperOrder,
    StockEtfLaneScopedIpcMethod::ReplacePaperOrder,
    StockEtfLaneScopedIpcMethod::ImportPaperFills,
    StockEtfLaneScopedIpcMethod::EvaluateShadowSignal,
];

const STATUS_FIELDS: &[&str] = &["asset_lane", "broker", "request_id"];
const PREVIEW_FIELDS: &[&str] = &[
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "request_id",
    "instrument_identity_hash",
    "risk_config_hash",
    "cost_model_version_hash",
    "pit_universe_contract_hash",
    "source_artifact_hash",
];
const PAPER_EFFECT_FIELDS: &[&str] = &[
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "request_id",
    "session_attestation_hash",
    "scoped_authorization_hash",
    "decision_lease_id",
    "guardian_state_hash",
    "risk_config_hash",
    "instrument_identity_hash",
    "idempotency_key",
    "lifecycle_contract_hash",
    "broker_capability_registry_hash",
    "audit_event_id",
];
const FILL_IMPORT_FIELDS: &[&str] = &[
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "request_id",
    "session_attestation_hash",
    "lifecycle_contract_hash",
    "redaction_policy_hash",
    "source_artifact_hash",
    "reconciliation_run_id",
];
const SHADOW_FIELDS: &[&str] = &[
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "request_id",
    "evidence_clock_hash",
    "pit_universe_contract_hash",
    "strategy_hypothesis_hash",
    "cost_model_version_hash",
    "source_artifact_hash",
];

const PAPER_EFFECT_GATES: &[&str] = &[
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
    "decision_lease_valid",
    "guardian_allows",
    STOCK_ETF_RISK_POLICY_CONTRACT_ID,
    "risk_config_hash",
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
    "idempotency_key",
    STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
    STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID,
];
const FILL_IMPORT_GATES: &[&str] = &[
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    IBKR_REDACTION_POLICY_CONTRACT_ID,
];
const PREVIEW_GATES: &[&str] = &[
    STOCK_ETF_RISK_POLICY_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
];
const SHADOW_GATES: &[&str] = &[
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
    STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
    STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID,
];

const REQUIRED_DENIALS: &[StockEtfDenialReason] = &[
    StockEtfDenialReason::LaneDisabled,
    StockEtfDenialReason::BrokerDisabled,
    StockEtfDenialReason::ShadowOnly,
    StockEtfDenialReason::LiveReservedDenied,
    StockEtfDenialReason::MarketClosed,
    StockEtfDenialReason::InstrumentBlocked,
    StockEtfDenialReason::CostModelMissing,
    StockEtfDenialReason::UniverseMismatch,
    StockEtfDenialReason::CredentialUnavailable,
    StockEtfDenialReason::ConnectorUnavailable,
    StockEtfDenialReason::AuthorizationInvalid,
    StockEtfDenialReason::DecisionLeaseInvalid,
    StockEtfDenialReason::GuardianDenied,
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfLaneScopedIpcContractV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub rust_authority_owner: bool,
    pub python_forward_only: bool,
    pub python_direct_broker_write_denied: bool,
    pub bybit_ipc_reuse_denied: bool,
    pub existing_bybit_paper_path_denied: bool,
    pub live_environment_denied: bool,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub commands: Vec<StockEtfLaneScopedIpcCommandV1>,
}

impl Default for StockEtfLaneScopedIpcContractV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            rust_authority_owner: false,
            python_forward_only: false,
            python_direct_broker_write_denied: false,
            bybit_ipc_reuse_denied: false,
            existing_bybit_paper_path_denied: false,
            live_environment_denied: false,
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            commands: Vec::new(),
        }
    }
}

impl StockEtfLaneScopedIpcContractV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            rust_authority_owner: true,
            python_forward_only: true,
            python_direct_broker_write_denied: true,
            bybit_ipc_reuse_denied: true,
            existing_bybit_paper_path_denied: true,
            live_environment_denied: true,
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            commands: REQUIRED_METHODS
                .iter()
                .copied()
                .map(StockEtfLaneScopedIpcCommandV1::fixture_for_method)
                .collect(),
        }
    }

    pub fn validate(&self) -> StockEtfLaneScopedIpcVerdict<StockEtfLaneScopedIpcBlocker> {
        use StockEtfLaneScopedIpcBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID {
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
        if !self.rust_authority_owner {
            blockers.push(Blocker::RustAuthorityOwnerMissing);
        }
        if !self.python_forward_only {
            blockers.push(Blocker::PythonForwardOnlyMissing);
        }
        if !self.python_direct_broker_write_denied {
            blockers.push(Blocker::PythonDirectBrokerWriteNotDenied);
        }
        if !self.bybit_ipc_reuse_denied {
            blockers.push(Blocker::BybitIpcReuseNotDenied);
        }
        if !self.existing_bybit_paper_path_denied {
            blockers.push(Blocker::ExistingBybitPaperPathNotDenied);
        }
        if !self.live_environment_denied {
            blockers.push(Blocker::LiveEnvironmentNotDenied);
        }
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.connector_runtime_started {
            blockers.push(Blocker::ConnectorRuntimeStarted);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }

        for command in &self.commands {
            if matches!(
                command.method,
                StockEtfLaneScopedIpcMethod::BybitSubmitPaperOrderDenied
                    | StockEtfLaneScopedIpcMethod::UnknownDenied
            ) {
                blockers.push(Blocker::CommandMethodDenied);
            }
        }

        for method in REQUIRED_METHODS {
            let matches: Vec<_> = self
                .commands
                .iter()
                .filter(|command| command.method == *method)
                .collect();
            if matches.is_empty() {
                blockers.push(Blocker::CommandMissing);
                continue;
            }
            if matches.len() > 1 {
                blockers.push(Blocker::CommandDuplicated);
            }
            validate_command(matches[0], &mut blockers);
        }

        StockEtfLaneScopedIpcVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfLaneScopedIpcCommandV1 {
    pub method: StockEtfLaneScopedIpcMethod,
    pub operation: BrokerOperation,
    pub authority_scope: AuthorityScope,
    pub effect_capable: bool,
    pub rust_owned: bool,
    pub required_gates: Vec<String>,
    pub required_request_fields: Vec<String>,
    pub typed_denial_reasons: Vec<StockEtfDenialReason>,
}

impl StockEtfLaneScopedIpcCommandV1 {
    pub fn fixture_for_method(method: StockEtfLaneScopedIpcMethod) -> Self {
        let expected = expected_method(method);
        Self {
            method,
            operation: expected.operation,
            authority_scope: expected.authority_scope,
            effect_capable: expected.effect_capable,
            rust_owned: expected.rust_owned,
            required_gates: expected
                .required_gates
                .iter()
                .map(|gate| gate.to_string())
                .collect(),
            required_request_fields: expected
                .required_request_fields
                .iter()
                .map(|field| field.to_string())
                .collect(),
            typed_denial_reasons: REQUIRED_DENIALS.to_vec(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfLaneScopedIpcMethod {
    GetLaneStatus,
    GetReadiness,
    GetDataFoundationStatus,
    GetPolicyStatus,
    GetAccountStatus,
    GetPaperStatus,
    GetReconciliationStatus,
    GetScorecardStatus,
    GetLaunchStatus,
    PreviewPaperOrder,
    SubmitPaperOrder,
    CancelPaperOrder,
    ReplacePaperOrder,
    ImportPaperFills,
    EvaluateShadowSignal,
    BybitSubmitPaperOrderDenied,
    UnknownDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ExpectedMethod {
    operation: BrokerOperation,
    authority_scope: AuthorityScope,
    effect_capable: bool,
    rust_owned: bool,
    required_gates: &'static [&'static str],
    required_request_fields: &'static [&'static str],
}

fn expected_method(method: StockEtfLaneScopedIpcMethod) -> ExpectedMethod {
    use AuthorityScope as Scope;
    use BrokerOperation as Op;
    use StockEtfLaneScopedIpcMethod as Method;

    match method {
        Method::GetLaneStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetReadiness => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetDataFoundationStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetPolicyStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetAccountStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetPaperStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetReconciliationStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetScorecardStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::GetLaunchStatus => ExpectedMethod {
            operation: Op::HealthRead,
            authority_scope: Scope::DisplayOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: STATUS_FIELDS,
        },
        Method::PreviewPaperOrder => ExpectedMethod {
            operation: Op::PaperOrderSubmit,
            authority_scope: Scope::ReadOnly,
            effect_capable: false,
            rust_owned: true,
            required_gates: PREVIEW_GATES,
            required_request_fields: PREVIEW_FIELDS,
        },
        Method::SubmitPaperOrder => paper_effect_method(Op::PaperOrderSubmit),
        Method::CancelPaperOrder => paper_effect_method(Op::PaperOrderCancel),
        Method::ReplacePaperOrder => paper_effect_method(Op::PaperOrderReplace),
        Method::ImportPaperFills => ExpectedMethod {
            operation: Op::PaperOrderFillImport,
            authority_scope: Scope::ReadOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: FILL_IMPORT_GATES,
            required_request_fields: FILL_IMPORT_FIELDS,
        },
        Method::EvaluateShadowSignal => ExpectedMethod {
            operation: Op::ShadowSignalEmit,
            authority_scope: Scope::ShadowOnly,
            effect_capable: false,
            rust_owned: false,
            required_gates: SHADOW_GATES,
            required_request_fields: SHADOW_FIELDS,
        },
        Method::BybitSubmitPaperOrderDenied | Method::UnknownDenied => ExpectedMethod {
            operation: Op::TransferOrAccountWrite,
            authority_scope: Scope::Denied,
            effect_capable: false,
            rust_owned: false,
            required_gates: &[],
            required_request_fields: &[],
        },
    }
}

const fn paper_effect_method(operation: BrokerOperation) -> ExpectedMethod {
    ExpectedMethod {
        operation,
        authority_scope: AuthorityScope::PaperRehearsal,
        effect_capable: true,
        rust_owned: true,
        required_gates: PAPER_EFFECT_GATES,
        required_request_fields: PAPER_EFFECT_FIELDS,
    }
}

fn validate_command(
    command: &StockEtfLaneScopedIpcCommandV1,
    blockers: &mut Vec<StockEtfLaneScopedIpcBlocker>,
) {
    use StockEtfLaneScopedIpcBlocker as Blocker;
    let expected = expected_method(command.method);

    if command.operation != expected.operation {
        blockers.push(Blocker::CommandOperationMismatch);
    }
    if command.authority_scope != expected.authority_scope {
        blockers.push(Blocker::CommandAuthorityScopeMismatch);
    }
    if command.effect_capable != expected.effect_capable {
        blockers.push(Blocker::CommandEffectCapabilityMismatch);
    }
    if command.rust_owned != expected.rust_owned {
        blockers.push(Blocker::CommandRustOwnershipMismatch);
    }
    if !contains_all_strings(&command.required_gates, expected.required_gates) {
        blockers.push(Blocker::CommandRequiredGateMissing);
    }
    if !contains_all_strings(
        &command.required_request_fields,
        expected.required_request_fields,
    ) {
        blockers.push(Blocker::CommandRequestFieldMissing);
    }
    if !contains_all_denials(&command.typed_denial_reasons, REQUIRED_DENIALS) {
        blockers.push(Blocker::CommandDenialReasonMissing);
    }
}

fn contains_all_strings(actual: &[String], required: &[&str]) -> bool {
    required
        .iter()
        .all(|expected| actual.iter().any(|item| item == expected))
}

fn contains_all_denials(
    actual: &[StockEtfDenialReason],
    required: &[StockEtfDenialReason],
) -> bool {
    required
        .iter()
        .all(|expected| actual.iter().any(|item| item == expected))
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfLaneScopedIpcVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfLaneScopedIpcVerdict<B> {
    pub fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfLaneScopedIpcBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    RustAuthorityOwnerMissing,
    PythonForwardOnlyMissing,
    PythonDirectBrokerWriteNotDenied,
    BybitIpcReuseNotDenied,
    ExistingBybitPaperPathNotDenied,
    LiveEnvironmentNotDenied,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    CommandMissing,
    CommandDuplicated,
    CommandMethodDenied,
    CommandOperationMismatch,
    CommandAuthorityScopeMismatch,
    CommandEffectCapabilityMismatch,
    CommandRustOwnershipMismatch,
    CommandRequiredGateMissing,
    CommandRequestFieldMissing,
    CommandDenialReasonMissing,
}
