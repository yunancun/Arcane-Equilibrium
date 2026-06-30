//! Stock/ETF broker capability registry contract for ADR-0048.
//!
//! This source-only validator pins the broker operation matrix. It does not
//! contact IBKR, inspect secrets, create connectors, route orders, or change
//! Bybit live execution behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_paper_lifecycle::IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID;
use crate::ibkr_phase2_gate::{
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
};
use crate::ibkr_phase2_policies::IBKR_PAPER_ATTESTATION_CONTRACT_ID;
use crate::stock_etf_ibkr_readonly_probe_request::STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID;
use crate::stock_etf_instrument_identity::STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID;
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerOperation, StockEtfDenialReason,
};
use crate::stock_etf_lane_scoped_ipc::STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID;
use crate::stock_etf_phase3_evidence::{
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
};
use crate::stock_etf_pit_universe::STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID;
use crate::stock_etf_reference_data_sources::STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID;
use crate::stock_etf_risk_policy::STOCK_ETF_RISK_POLICY_CONTRACT_ID;
use crate::stock_etf_scorecard_inputs::{
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID, STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};
use crate::stock_etf_strategy_hypothesis::STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID;

pub const STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID: &str = "broker_capability_registry_v1";

const REQUIRED_AUDIT_FIELDS: &[&str] = &[
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "allowed",
    "denial_reason",
    "source_artifact_hash",
];

const REQUIRED_OPERATIONS: &[BrokerOperation] = &[
    BrokerOperation::HealthRead,
    BrokerOperation::AccountSnapshotRead,
    BrokerOperation::MarketDataRead,
    BrokerOperation::ContractDetailsRead,
    BrokerOperation::PaperOrderSubmit,
    BrokerOperation::PaperOrderCancel,
    BrokerOperation::PaperOrderReplace,
    BrokerOperation::PaperOrderFillImport,
    BrokerOperation::ShadowSignalEmit,
    BrokerOperation::ShadowFillReconstruct,
    BrokerOperation::ScorecardDerive,
    BrokerOperation::LiveOrderSubmit,
    BrokerOperation::MarginOrShort,
    BrokerOperation::OptionsOrCfd,
    BrokerOperation::TransferOrAccountWrite,
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfBrokerCapabilityRegistryV1 {
    pub registry_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub bybit_live_execution_unchanged: bool,
    pub python_broker_write_authority_denied: bool,
    pub ibkr_live_denied: bool,
    pub cfd_margin_reserved_denied: bool,
    pub first_ibkr_contact_performed: bool,
    pub secret_content_serialized: bool,
    pub required_audit_fields: Vec<String>,
    pub operations: Vec<StockEtfBrokerCapabilityEntryV1>,
}

impl Default for StockEtfBrokerCapabilityRegistryV1 {
    fn default() -> Self {
        Self {
            registry_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            bybit_live_execution_unchanged: false,
            python_broker_write_authority_denied: false,
            ibkr_live_denied: false,
            cfd_margin_reserved_denied: false,
            first_ibkr_contact_performed: false,
            secret_content_serialized: false,
            required_audit_fields: Vec::new(),
            operations: Vec::new(),
        }
    }
}

impl StockEtfBrokerCapabilityRegistryV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            registry_id: STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            bybit_live_execution_unchanged: true,
            python_broker_write_authority_denied: true,
            ibkr_live_denied: true,
            cfd_margin_reserved_denied: true,
            first_ibkr_contact_performed: false,
            secret_content_serialized: false,
            required_audit_fields: REQUIRED_AUDIT_FIELDS
                .iter()
                .map(|field| field.to_string())
                .collect(),
            operations: REQUIRED_OPERATIONS
                .iter()
                .copied()
                .map(StockEtfBrokerCapabilityEntryV1::fixture_for_operation)
                .collect(),
        }
    }

    pub fn validate(&self) -> StockEtfBrokerCapabilityVerdict<StockEtfBrokerCapabilityBlocker> {
        use StockEtfBrokerCapabilityBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.registry_id != STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID {
            blockers.push(Blocker::RegistryIdMismatch);
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
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if !self.python_broker_write_authority_denied {
            blockers.push(Blocker::PythonBrokerWriteAuthorityNotDenied);
        }
        if !self.ibkr_live_denied {
            blockers.push(Blocker::IbkrLiveNotDenied);
        }
        if !self.cfd_margin_reserved_denied {
            blockers.push(Blocker::CfdMarginReservedNotDenied);
        }
        if self.first_ibkr_contact_performed {
            blockers.push(Blocker::FirstIbkrContactPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if !contains_all(&self.required_audit_fields, REQUIRED_AUDIT_FIELDS) {
            blockers.push(Blocker::RequiredAuditFieldMissing);
        }

        for operation in REQUIRED_OPERATIONS {
            let matches: Vec<_> = self
                .operations
                .iter()
                .filter(|entry| entry.operation == *operation)
                .collect();
            if matches.is_empty() {
                blockers.push(Blocker::OperationMissing);
                continue;
            }
            if matches.len() > 1 {
                blockers.push(Blocker::OperationDuplicated);
            }
            validate_entry(matches[0], &mut blockers);
        }

        StockEtfBrokerCapabilityVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfBrokerCapabilityEntryV1 {
    pub operation: BrokerOperation,
    pub authority_scope: AuthorityScope,
    pub required_gates: Vec<String>,
    pub typed_denial_reason: Option<StockEtfDenialReason>,
    pub rust_owned: bool,
    pub audit_event_required: bool,
    pub source_artifact_hash_required: bool,
}

impl StockEtfBrokerCapabilityEntryV1 {
    pub fn fixture_for_operation(operation: BrokerOperation) -> Self {
        let expected = expected_capability(operation);
        Self {
            operation,
            authority_scope: expected.authority_scope,
            required_gates: expected
                .required_gates
                .iter()
                .map(|gate| gate.to_string())
                .collect(),
            typed_denial_reason: expected.typed_denial_reason,
            rust_owned: expected.rust_owned,
            audit_event_required: true,
            source_artifact_hash_required: true,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ExpectedCapability {
    authority_scope: AuthorityScope,
    required_gates: &'static [&'static str],
    typed_denial_reason: Option<StockEtfDenialReason>,
    rust_owned: bool,
}

fn expected_capability(operation: BrokerOperation) -> ExpectedCapability {
    use AuthorityScope as Scope;
    use BrokerOperation as Op;
    use StockEtfDenialReason as Deny;

    match operation {
        Op::HealthRead => ExpectedCapability {
            authority_scope: Scope::ReadOnly,
            required_gates: &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::AccountSnapshotRead => ExpectedCapability {
            authority_scope: Scope::ReadOnly,
            required_gates: &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                IBKR_SESSION_ATTESTATION_CONTRACT_ID,
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::MarketDataRead => ExpectedCapability {
            authority_scope: Scope::ReadOnly,
            required_gates: &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::ContractDetailsRead => ExpectedCapability {
            authority_scope: Scope::ReadOnly,
            required_gates: &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::PaperOrderSubmit | Op::PaperOrderCancel | Op::PaperOrderReplace => ExpectedCapability {
            authority_scope: Scope::PaperRehearsal,
            required_gates: &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                IBKR_PAPER_ATTESTATION_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                "stock_etf_scoped_authorization_v1",
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                "decision_lease_valid",
                "guardian_allows",
                IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
            ],
            typed_denial_reason: None,
            rust_owned: true,
        },
        Op::PaperOrderFillImport => ExpectedCapability {
            authority_scope: Scope::ReadOnly,
            required_gates: &[
                IBKR_SESSION_ATTESTATION_CONTRACT_ID,
                IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::ShadowSignalEmit => ExpectedCapability {
            authority_scope: Scope::ShadowOnly,
            required_gates: &[
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
                STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
                STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
                "frozen_strategy_hypothesis_hash",
                "frozen_universe_hash",
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::ShadowFillReconstruct => ExpectedCapability {
            authority_scope: Scope::ShadowOnly,
            required_gates: &[
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
                STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
                STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::ScorecardDerive => ExpectedCapability {
            authority_scope: Scope::ReadOnly,
            required_gates: &[
                BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID,
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
                STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
                STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
                STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
                STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
                STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
                STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
                "paper_shadow_fill_separation",
            ],
            typed_denial_reason: None,
            rust_owned: false,
        },
        Op::LiveOrderSubmit => ExpectedCapability {
            authority_scope: Scope::Denied,
            required_gates: &[],
            typed_denial_reason: Some(Deny::IbkrLiveNotAuthorized),
            rust_owned: false,
        },
        Op::MarginOrShort => ExpectedCapability {
            authority_scope: Scope::Denied,
            required_gates: &[],
            typed_denial_reason: Some(Deny::StockEtfCashOnly),
            rust_owned: false,
        },
        Op::OptionsOrCfd => ExpectedCapability {
            authority_scope: Scope::Denied,
            required_gates: &[],
            typed_denial_reason: Some(Deny::InstrumentKindDenied),
            rust_owned: false,
        },
        Op::TransferOrAccountWrite => ExpectedCapability {
            authority_scope: Scope::Denied,
            required_gates: &[],
            typed_denial_reason: Some(Deny::AccountWriteDenied),
            rust_owned: false,
        },
    }
}

fn validate_entry(
    entry: &StockEtfBrokerCapabilityEntryV1,
    blockers: &mut Vec<StockEtfBrokerCapabilityBlocker>,
) {
    use StockEtfBrokerCapabilityBlocker as Blocker;
    let expected = expected_capability(entry.operation);

    if entry.authority_scope != expected.authority_scope {
        blockers.push(Blocker::OperationAuthorityScopeMismatch);
    }
    if !contains_all(&entry.required_gates, expected.required_gates) {
        blockers.push(Blocker::OperationRequiredGateMissing);
    }
    if entry.typed_denial_reason != expected.typed_denial_reason {
        blockers.push(Blocker::OperationTypedDenialMismatch);
    }
    if entry.rust_owned != expected.rust_owned {
        blockers.push(Blocker::OperationRustOwnershipMismatch);
    }
    if !entry.audit_event_required {
        blockers.push(Blocker::OperationAuditEventMissing);
    }
    if !entry.source_artifact_hash_required {
        blockers.push(Blocker::OperationSourceArtifactHashMissing);
    }
}

fn contains_all(actual: &[String], required: &[&str]) -> bool {
    required
        .iter()
        .all(|expected| actual.iter().any(|item| item == expected))
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfBrokerCapabilityVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfBrokerCapabilityVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfBrokerCapabilityBlocker {
    RegistryIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    BybitLiveExecutionNotProtected,
    PythonBrokerWriteAuthorityNotDenied,
    IbkrLiveNotDenied,
    CfdMarginReservedNotDenied,
    FirstIbkrContactPerformed,
    SecretContentSerialized,
    RequiredAuditFieldMissing,
    OperationMissing,
    OperationDuplicated,
    OperationAuthorityScopeMismatch,
    OperationRequiredGateMissing,
    OperationTypedDenialMismatch,
    OperationRustOwnershipMismatch,
    OperationAuditEventMissing,
    OperationSourceArtifactHashMissing,
}
