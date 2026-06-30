//! Stock/ETF paper order request envelope contract.
//!
//! This source-only validator pins the request semantics that must sit between
//! lane-scoped IPC and the IBKR paper lifecycle. It does not contact IBKR,
//! create connectors, read secrets, route orders, or mutate Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_paper_lifecycle::IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID;
use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_broker_capability_registry::STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID;
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, InstrumentKind,
};
use crate::stock_etf_lane_scoped_ipc::{
    StockEtfLaneScopedIpcMethod, STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
};
use crate::stock_etf_pit_universe::STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID;
use crate::stock_etf_risk_policy::STOCK_ETF_RISK_POLICY_CONTRACT_ID;
use crate::stock_etf_scorecard_inputs::{
    StockEtfOrderSide, STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
};

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

impl StockEtfPaperOrderRequestEnvelopeV1 {
    pub fn accepted_preview_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            request_method: StockEtfLaneScopedIpcMethod::PreviewPaperOrder,
            operation: BrokerOperation::PaperOrderSubmit,
            authority_scope: AuthorityScope::ReadOnly,
            request_id: "preview_request_0001".to_string(),
            account_fingerprint_hash: "1".repeat(64),
            risk_config_hash: "2".repeat(64),
            instrument_identity_hash: "3".repeat(64),
            cost_model_version_hash: "4".repeat(64),
            pit_universe_contract_hash: "5".repeat(64),
            source_artifact_hash: "6".repeat(64),
            symbol: "SPY".to_string(),
            instrument_kind: Some(InstrumentKind::Etf),
            side: Some(StockEtfOrderSide::Buy),
            order_type: Some(StockEtfPaperOrderType::Limit),
            quantity_decimal: "10".to_string(),
            limit_price_policy: Some(StockEtfLimitPricePolicy::RequiredForLimitOrder),
            limit_price_decimal: "450.25".to_string(),
            time_in_force: Some(StockEtfPaperTimeInForce::Day),
            ..Self::default()
        }
    }

    pub fn accepted_submit_fixture() -> Self {
        Self {
            request_method: StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
            authority_scope: AuthorityScope::PaperRehearsal,
            effect_capable: true,
            request_id: "submit_request_0001".to_string(),
            session_attestation_hash: "7".repeat(64),
            scoped_authorization_hash: "8".repeat(64),
            decision_lease_id: "decision_lease_0001".to_string(),
            guardian_state_hash: "9".repeat(64),
            lifecycle_contract_hash: "a".repeat(64),
            broker_capability_registry_hash: "b".repeat(64),
            audit_event_id: "audit_event_0001".to_string(),
            cost_model_version_hash: String::new(),
            pit_universe_contract_hash: String::new(),
            source_artifact_hash: String::new(),
            order_local_id: "local_order_0001".to_string(),
            idempotency_key: "idem_0001".to_string(),
            ..Self::accepted_preview_fixture()
        }
    }

    pub fn accepted_cancel_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            request_method: StockEtfLaneScopedIpcMethod::CancelPaperOrder,
            operation: BrokerOperation::PaperOrderCancel,
            authority_scope: AuthorityScope::PaperRehearsal,
            effect_capable: true,
            request_id: "cancel_request_0001".to_string(),
            account_fingerprint_hash: "1".repeat(64),
            session_attestation_hash: "7".repeat(64),
            scoped_authorization_hash: "8".repeat(64),
            decision_lease_id: "decision_lease_0001".to_string(),
            guardian_state_hash: "9".repeat(64),
            lifecycle_contract_hash: "a".repeat(64),
            broker_capability_registry_hash: "b".repeat(64),
            audit_event_id: "audit_event_0002".to_string(),
            order_local_id: "local_order_0001".to_string(),
            idempotency_key: "cancel_idem_0001".to_string(),
            broker_order_id: "paper_broker_order_0001".to_string(),
            cancel_reason: "risk_or_operator_rehearsal".to_string(),
            ..Self::default()
        }
    }

    pub fn accepted_replace_fixture() -> Self {
        Self {
            request_method: StockEtfLaneScopedIpcMethod::ReplacePaperOrder,
            operation: BrokerOperation::PaperOrderReplace,
            request_id: "replace_request_0001".to_string(),
            audit_event_id: "audit_event_0003".to_string(),
            symbol: "SPY".to_string(),
            instrument_identity_hash: "3".repeat(64),
            side: Some(StockEtfOrderSide::Buy),
            replacement_idempotency_key: "replace_idem_0001".to_string(),
            replacement_quantity_decimal: "12".to_string(),
            replacement_limit_price_policy: Some(StockEtfLimitPricePolicy::RequiredForLimitOrder),
            replacement_limit_price_decimal: "451.10".to_string(),
            replacement_time_in_force: Some(StockEtfPaperTimeInForce::Day),
            replace_reason: "paper_rehearsal_price_or_size_update".to_string(),
            idempotency_key: String::new(),
            cancel_reason: String::new(),
            ..Self::accepted_cancel_fixture()
        }
    }

    pub fn validate(&self) -> StockEtfPaperOrderRequestVerdict {
        use StockEtfPaperOrderRequestBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID {
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
        if self.environment == BrokerEnvironment::LiveReservedDenied {
            blockers.push(Blocker::LiveEnvironmentDenied);
        }
        if self.environment != BrokerEnvironment::Paper {
            blockers.push(Blocker::EnvironmentNotPaper);
        }
        validate_boundary_flags(self, &mut blockers);
        validate_expected_surface(self, &mut blockers);

        if self.request_id.trim().is_empty() {
            blockers.push(Blocker::RequestIdMissing);
        }
        if !is_sha256_hex(&self.account_fingerprint_hash) {
            blockers.push(Blocker::AccountFingerprintHashInvalid);
        }

        match self.request_method {
            StockEtfLaneScopedIpcMethod::PreviewPaperOrder => validate_preview(self, &mut blockers),
            StockEtfLaneScopedIpcMethod::SubmitPaperOrder => validate_submit(self, &mut blockers),
            StockEtfLaneScopedIpcMethod::CancelPaperOrder => validate_cancel(self, &mut blockers),
            StockEtfLaneScopedIpcMethod::ReplacePaperOrder => validate_replace(self, &mut blockers),
            _ => blockers.push(Blocker::RequestMethodUnsupported),
        }

        StockEtfPaperOrderRequestVerdict {
            accepted: blockers.is_empty(),
            blockers,
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

fn validate_boundary_flags(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    if envelope.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if envelope.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if envelope.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if envelope.order_routed {
        blockers.push(Blocker::OrderRouted);
    }
    if envelope.bybit_path_reused {
        blockers.push(Blocker::BybitPathReused);
    }
    if envelope.live_or_tiny_live_authorized {
        blockers.push(Blocker::LiveOrTinyLiveAuthorized);
    }
    if envelope.margin_short_options_cfd_requested {
        blockers.push(Blocker::MarginShortOptionsCfdRequested);
    }
    if envelope.python_direct_broker_write_requested {
        blockers.push(Blocker::PythonDirectBrokerWriteRequested);
    }
}

fn validate_expected_surface(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let expected = match envelope.request_method {
        StockEtfLaneScopedIpcMethod::PreviewPaperOrder => Some((
            BrokerOperation::PaperOrderSubmit,
            AuthorityScope::ReadOnly,
            false,
        )),
        StockEtfLaneScopedIpcMethod::SubmitPaperOrder => Some((
            BrokerOperation::PaperOrderSubmit,
            AuthorityScope::PaperRehearsal,
            true,
        )),
        StockEtfLaneScopedIpcMethod::CancelPaperOrder => Some((
            BrokerOperation::PaperOrderCancel,
            AuthorityScope::PaperRehearsal,
            true,
        )),
        StockEtfLaneScopedIpcMethod::ReplacePaperOrder => Some((
            BrokerOperation::PaperOrderReplace,
            AuthorityScope::PaperRehearsal,
            true,
        )),
        _ => None,
    };

    let Some((operation, authority_scope, effect_capable)) = expected else {
        return;
    };
    if envelope.operation != operation {
        blockers.push(Blocker::OperationMismatch);
    }
    if envelope.authority_scope != authority_scope {
        blockers.push(Blocker::AuthorityScopeMismatch);
    }
    if envelope.effect_capable != effect_capable {
        blockers.push(Blocker::EffectCapabilityMismatch);
    }
}

fn validate_preview(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    validate_order_intent(envelope, blockers);
    validate_preview_hashes(envelope, blockers);
    if effect_or_lifecycle_field_present(envelope) || cancel_or_replace_field_present(envelope) {
        blockers.push(Blocker::PreviewEffectFieldPresent);
    }
}

fn validate_submit(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    validate_order_intent(envelope, blockers);
    validate_effect_hashes(envelope, blockers);
    if !is_sha256_hex(&envelope.risk_config_hash) {
        blockers.push(Blocker::RiskConfigHashInvalid);
    }
    if !is_sha256_hex(&envelope.instrument_identity_hash) {
        blockers.push(Blocker::InstrumentIdentityHashInvalid);
    }
    if envelope.order_local_id.trim().is_empty() {
        blockers.push(Blocker::LocalOrderIdMissing);
    }
    if envelope.idempotency_key.trim().is_empty() {
        blockers.push(Blocker::IdempotencyKeyMissing);
    }
    if !envelope.broker_order_id.trim().is_empty() {
        blockers.push(Blocker::SubmitBrokerOrderIdPresent);
    }
    if cancel_or_replace_field_present(envelope) {
        blockers.push(Blocker::SubmitCancelOrReplaceFieldPresent);
    }
}

fn validate_cancel(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    validate_effect_hashes(envelope, blockers);
    if envelope.order_local_id.trim().is_empty() {
        blockers.push(Blocker::LocalOrderIdMissing);
    }
    if envelope.idempotency_key.trim().is_empty() {
        blockers.push(Blocker::IdempotencyKeyMissing);
    }
    if envelope.broker_order_id.trim().is_empty() {
        blockers.push(Blocker::BrokerOrderIdMissing);
    }
    if envelope.cancel_reason.trim().is_empty() {
        blockers.push(Blocker::CancelReasonMissing);
    }
    if order_shape_field_present(envelope) {
        blockers.push(Blocker::CancelOrderShapeFieldPresent);
    }
    if replace_field_present(envelope) {
        blockers.push(Blocker::SubmitCancelOrReplaceFieldPresent);
    }
}

fn validate_replace(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    validate_effect_hashes(envelope, blockers);
    if envelope.order_local_id.trim().is_empty() {
        blockers.push(Blocker::LocalOrderIdMissing);
    }
    if envelope.broker_order_id.trim().is_empty() {
        blockers.push(Blocker::BrokerOrderIdMissing);
    }
    if !is_sha256_hex(&envelope.instrument_identity_hash) {
        blockers.push(Blocker::InstrumentIdentityHashInvalid);
    }
    validate_symbol_and_side(envelope, blockers);
    if envelope.replacement_idempotency_key.trim().is_empty() {
        blockers.push(Blocker::ReplacementIdempotencyKeyMissing);
    }
    if !is_positive_decimal(&envelope.replacement_quantity_decimal) {
        blockers.push(Blocker::ReplacementQuantityInvalid);
    }
    validate_replacement_limit_price(envelope, blockers);
    if envelope.replacement_time_in_force.is_none() {
        blockers.push(Blocker::ReplacementTimeInForceMissing);
    }
    if envelope.replace_reason.trim().is_empty() {
        blockers.push(Blocker::ReplaceReasonMissing);
    }
    if original_mutable_field_present(envelope) || !envelope.idempotency_key.trim().is_empty() {
        blockers.push(Blocker::ReplaceOriginalMutableFieldPresent);
    }
}

fn validate_order_intent(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    validate_symbol_and_side(envelope, blockers);
    if !matches!(
        envelope.instrument_kind,
        Some(InstrumentKind::Stock | InstrumentKind::Etf)
    ) {
        blockers.push(Blocker::InstrumentKindDenied);
    }
    if envelope.order_type.is_none() {
        blockers.push(Blocker::OrderTypeMissing);
    }
    if !is_positive_decimal(&envelope.quantity_decimal) {
        blockers.push(Blocker::QuantityInvalid);
    }
    validate_limit_price(envelope, blockers);
    match envelope.time_in_force {
        Some(StockEtfPaperTimeInForce::Day) => {}
        Some(StockEtfPaperTimeInForce::Gtc)
            if envelope.order_type == Some(StockEtfPaperOrderType::Limit) => {}
        Some(StockEtfPaperTimeInForce::Gtc) => blockers.push(Blocker::TimeInForceIncompatible),
        None => blockers.push(Blocker::TimeInForceMissing),
    }
}

fn validate_symbol_and_side(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    if !is_normalized_symbol(&envelope.symbol) {
        blockers.push(Blocker::SymbolInvalid);
    }
    if !matches!(
        envelope.side,
        Some(StockEtfOrderSide::Buy | StockEtfOrderSide::Sell)
    ) {
        blockers.push(Blocker::SideMissing);
    }
}

fn validate_preview_hashes(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    if !is_sha256_hex(&envelope.risk_config_hash) {
        blockers.push(Blocker::RiskConfigHashInvalid);
    }
    if !is_sha256_hex(&envelope.instrument_identity_hash) {
        blockers.push(Blocker::InstrumentIdentityHashInvalid);
    }
    if !is_sha256_hex(&envelope.cost_model_version_hash) {
        blockers.push(Blocker::CostModelVersionHashInvalid);
    }
    if !is_sha256_hex(&envelope.pit_universe_contract_hash) {
        blockers.push(Blocker::PitUniverseContractHashInvalid);
    }
    if !is_sha256_hex(&envelope.source_artifact_hash) {
        blockers.push(Blocker::SourceArtifactHashInvalid);
    }
}

fn validate_effect_hashes(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    if !is_sha256_hex(&envelope.session_attestation_hash) {
        blockers.push(Blocker::SessionAttestationHashInvalid);
    }
    if !is_sha256_hex(&envelope.scoped_authorization_hash) {
        blockers.push(Blocker::ScopedAuthorizationHashInvalid);
    }
    if envelope.decision_lease_id.trim().is_empty() {
        blockers.push(Blocker::DecisionLeaseMissing);
    }
    if !is_sha256_hex(&envelope.guardian_state_hash) {
        blockers.push(Blocker::GuardianStateHashInvalid);
    }
    if !is_sha256_hex(&envelope.lifecycle_contract_hash) {
        blockers.push(Blocker::LifecycleContractHashInvalid);
    }
    if !is_sha256_hex(&envelope.broker_capability_registry_hash) {
        blockers.push(Blocker::BrokerCapabilityRegistryHashInvalid);
    }
    if envelope.audit_event_id.trim().is_empty() {
        blockers.push(Blocker::AuditEventIdMissing);
    }
}

fn validate_limit_price(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    match (envelope.order_type, envelope.limit_price_policy) {
        (
            Some(StockEtfPaperOrderType::Limit),
            Some(StockEtfLimitPricePolicy::RequiredForLimitOrder),
        ) if is_positive_decimal(&envelope.limit_price_decimal) => {}
        (
            Some(StockEtfPaperOrderType::Market),
            Some(StockEtfLimitPricePolicy::AbsentForMarketOrder),
        ) if envelope.limit_price_decimal.trim().is_empty() => {}
        (Some(StockEtfPaperOrderType::Limit), Some(_))
        | (Some(StockEtfPaperOrderType::Market), Some(_)) => {
            blockers.push(Blocker::LimitPricePolicyMismatch)
        }
        (Some(StockEtfPaperOrderType::Limit), None)
        | (Some(StockEtfPaperOrderType::Market), None) => {
            blockers.push(Blocker::LimitPricePolicyMismatch)
        }
        _ => {}
    }
    if envelope.order_type == Some(StockEtfPaperOrderType::Limit)
        && !is_positive_decimal(&envelope.limit_price_decimal)
    {
        blockers.push(Blocker::LimitPriceInvalid);
    }
    if envelope.order_type == Some(StockEtfPaperOrderType::Market)
        && !envelope.limit_price_decimal.trim().is_empty()
    {
        blockers.push(Blocker::LimitPriceInvalid);
    }
}

fn validate_replacement_limit_price(
    envelope: &StockEtfPaperOrderRequestEnvelopeV1,
    blockers: &mut Vec<StockEtfPaperOrderRequestBlocker>,
) {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    match envelope.replacement_limit_price_policy {
        Some(StockEtfLimitPricePolicy::RequiredForLimitOrder)
            if is_positive_decimal(&envelope.replacement_limit_price_decimal) => {}
        Some(StockEtfLimitPricePolicy::Unchanged)
            if envelope.replacement_limit_price_decimal.trim().is_empty() => {}
        Some(_) => blockers.push(Blocker::ReplacementLimitPricePolicyMismatch),
        None => blockers.push(Blocker::ReplacementLimitPricePolicyMismatch),
    }
    if envelope.replacement_limit_price_policy
        == Some(StockEtfLimitPricePolicy::RequiredForLimitOrder)
        && !is_positive_decimal(&envelope.replacement_limit_price_decimal)
    {
        blockers.push(Blocker::ReplacementLimitPriceInvalid);
    }
    if envelope.replacement_limit_price_policy == Some(StockEtfLimitPricePolicy::Unchanged)
        && !envelope.replacement_limit_price_decimal.trim().is_empty()
    {
        blockers.push(Blocker::ReplacementLimitPriceInvalid);
    }
}

fn is_normalized_symbol(symbol: &str) -> bool {
    let trimmed = symbol.trim();
    !trimmed.is_empty()
        && trimmed.len() <= 24
        && trimmed == symbol
        && trimmed
            .bytes()
            .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || matches!(b, b'.' | b'-'))
}

fn is_positive_decimal(raw: &str) -> bool {
    let raw = raw.trim();
    if raw.is_empty() || raw.starts_with(['+', '-']) || raw.matches('.').count() > 1 {
        return false;
    }
    let mut saw_digit = false;
    let mut saw_nonzero = false;
    for b in raw.bytes() {
        match b {
            b'0' => saw_digit = true,
            b'1'..=b'9' => {
                saw_digit = true;
                saw_nonzero = true;
            }
            b'.' => {}
            _ => return false,
        }
    }
    saw_digit && saw_nonzero
}

fn effect_or_lifecycle_field_present(envelope: &StockEtfPaperOrderRequestEnvelopeV1) -> bool {
    !envelope.session_attestation_hash.is_empty()
        || !envelope.scoped_authorization_hash.is_empty()
        || !envelope.decision_lease_id.is_empty()
        || !envelope.guardian_state_hash.is_empty()
        || !envelope.lifecycle_contract_hash.is_empty()
        || !envelope.broker_capability_registry_hash.is_empty()
        || !envelope.audit_event_id.is_empty()
        || !envelope.order_local_id.is_empty()
        || !envelope.idempotency_key.is_empty()
        || !envelope.broker_order_id.is_empty()
}

fn order_shape_field_present(envelope: &StockEtfPaperOrderRequestEnvelopeV1) -> bool {
    !envelope.symbol.is_empty()
        || envelope.instrument_kind.is_some()
        || envelope.side.is_some()
        || envelope.order_type.is_some()
        || !envelope.quantity_decimal.is_empty()
        || envelope.limit_price_policy.is_some()
        || !envelope.limit_price_decimal.is_empty()
        || envelope.time_in_force.is_some()
}

fn original_mutable_field_present(envelope: &StockEtfPaperOrderRequestEnvelopeV1) -> bool {
    envelope.instrument_kind.is_some()
        || envelope.order_type.is_some()
        || !envelope.quantity_decimal.is_empty()
        || envelope.limit_price_policy.is_some()
        || !envelope.limit_price_decimal.is_empty()
        || envelope.time_in_force.is_some()
}

fn cancel_or_replace_field_present(envelope: &StockEtfPaperOrderRequestEnvelopeV1) -> bool {
    !envelope.cancel_reason.is_empty() || replace_field_present(envelope)
}

fn replace_field_present(envelope: &StockEtfPaperOrderRequestEnvelopeV1) -> bool {
    !envelope.replacement_idempotency_key.is_empty()
        || !envelope.replacement_quantity_decimal.is_empty()
        || envelope.replacement_limit_price_policy.is_some()
        || !envelope.replacement_limit_price_decimal.is_empty()
        || envelope.replacement_time_in_force.is_some()
        || !envelope.replace_reason.is_empty()
}

#[allow(dead_code)]
const _: &[&str] = &[
    STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
    STOCK_ETF_RISK_POLICY_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
];
