//! Stock/ETF paper order request envelope contract.
//!
//! This source-only validator pins the request semantics that must sit between
//! lane-scoped IPC and the IBKR paper lifecycle. It does not contact IBKR,
//! create connectors, read secrets, route orders, or mutate Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, InstrumentKind,
};
use crate::stock_etf_lane_scoped_ipc::StockEtfLaneScopedIpcMethod;
use crate::stock_etf_scorecard_inputs::StockEtfOrderSide;

mod fixtures;
mod validation;

pub const STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID: &str = "stock_etf_paper_order_request_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPaperOrderType {
    Market,
    Limit,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPaperTimeInForce {
    Day,
    Gtc,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfLimitPricePolicy {
    RequiredForLimitOrder,
    AbsentForMarketOrder,
    Unchanged,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPaperOrderRequestEnvelopeV1 {
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
    pub account_fingerprint_hash: String,
    pub session_attestation_hash: String,
    pub scoped_authorization_hash: String,
    pub decision_lease_id: String,
    pub guardian_state_hash: String,
    pub risk_config_hash: String,
    pub instrument_identity_hash: String,
    pub cost_model_version_hash: String,
    pub pit_universe_contract_hash: String,
    pub source_artifact_hash: String,
    pub lifecycle_contract_hash: String,
    pub broker_capability_registry_hash: String,
    pub audit_event_id: String,
    pub symbol: String,
    pub instrument_kind: Option<InstrumentKind>,
    pub side: Option<StockEtfOrderSide>,
    pub order_type: Option<StockEtfPaperOrderType>,
    pub quantity_decimal: String,
    pub limit_price_policy: Option<StockEtfLimitPricePolicy>,
    pub limit_price_decimal: String,
    pub time_in_force: Option<StockEtfPaperTimeInForce>,
    pub order_local_id: String,
    pub idempotency_key: String,
    pub broker_order_id: String,
    pub cancel_reason: String,
    pub replacement_idempotency_key: String,
    pub replacement_quantity_decimal: String,
    pub replacement_limit_price_policy: Option<StockEtfLimitPricePolicy>,
    pub replacement_limit_price_decimal: String,
    pub replacement_time_in_force: Option<StockEtfPaperTimeInForce>,
    pub replace_reason: String,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub order_routed: bool,
    pub bybit_path_reused: bool,
    pub live_or_tiny_live_authorized: bool,
    pub margin_short_options_cfd_requested: bool,
    pub python_direct_broker_write_requested: bool,
}

impl Default for StockEtfPaperOrderRequestEnvelopeV1 {
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
            account_fingerprint_hash: String::new(),
            session_attestation_hash: String::new(),
            scoped_authorization_hash: String::new(),
            decision_lease_id: String::new(),
            guardian_state_hash: String::new(),
            risk_config_hash: String::new(),
            instrument_identity_hash: String::new(),
            cost_model_version_hash: String::new(),
            pit_universe_contract_hash: String::new(),
            source_artifact_hash: String::new(),
            lifecycle_contract_hash: String::new(),
            broker_capability_registry_hash: String::new(),
            audit_event_id: String::new(),
            symbol: String::new(),
            instrument_kind: None,
            side: None,
            order_type: None,
            quantity_decimal: String::new(),
            limit_price_policy: None,
            limit_price_decimal: String::new(),
            time_in_force: None,
            order_local_id: String::new(),
            idempotency_key: String::new(),
            broker_order_id: String::new(),
            cancel_reason: String::new(),
            replacement_idempotency_key: String::new(),
            replacement_quantity_decimal: String::new(),
            replacement_limit_price_policy: None,
            replacement_limit_price_decimal: String::new(),
            replacement_time_in_force: None,
            replace_reason: String::new(),
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            order_routed: false,
            bybit_path_reused: false,
            live_or_tiny_live_authorized: false,
            margin_short_options_cfd_requested: false,
            python_direct_broker_write_requested: false,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPaperOrderRequestVerdict {
    pub accepted: bool,
    pub blockers: Vec<StockEtfPaperOrderRequestBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPaperOrderRequestBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentNotPaper,
    LiveEnvironmentDenied,
    RequestMethodUnsupported,
    OperationMismatch,
    AuthorityScopeMismatch,
    EffectCapabilityMismatch,
    RequestIdMissing,
    AccountFingerprintHashInvalid,
    SessionAttestationHashInvalid,
    ScopedAuthorizationHashInvalid,
    DecisionLeaseMissing,
    GuardianStateHashInvalid,
    RiskConfigHashInvalid,
    InstrumentIdentityHashInvalid,
    CostModelVersionHashInvalid,
    PitUniverseContractHashInvalid,
    SourceArtifactHashInvalid,
    LifecycleContractHashInvalid,
    BrokerCapabilityRegistryHashInvalid,
    AuditEventIdMissing,
    SymbolInvalid,
    InstrumentKindDenied,
    SideMissing,
    OrderTypeMissing,
    QuantityInvalid,
    LimitPricePolicyMismatch,
    LimitPriceInvalid,
    TimeInForceMissing,
    TimeInForceIncompatible,
    LocalOrderIdMissing,
    IdempotencyKeyMissing,
    BrokerOrderIdMissing,
    CancelReasonMissing,
    ReplaceReasonMissing,
    ReplacementIdempotencyKeyMissing,
    ReplacementQuantityInvalid,
    ReplacementLimitPricePolicyMismatch,
    ReplacementLimitPriceInvalid,
    ReplacementTimeInForceMissing,
    PreviewEffectFieldPresent,
    SubmitBrokerOrderIdPresent,
    SubmitCancelOrReplaceFieldPresent,
    CancelOrderShapeFieldPresent,
    ReplaceOriginalMutableFieldPresent,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    OrderRouted,
    BybitPathReused,
    LiveOrTinyLiveAuthorized,
    MarginShortOptionsCfdRequested,
    PythonDirectBrokerWriteRequested,
}
