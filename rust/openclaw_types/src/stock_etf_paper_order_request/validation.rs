//! Stock/ETF paper order request validation helpers.

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

use super::{
    StockEtfLimitPricePolicy, StockEtfPaperOrderRequestBlocker,
    StockEtfPaperOrderRequestEnvelopeV1, StockEtfPaperOrderRequestVerdict, StockEtfPaperOrderType,
    StockEtfPaperTimeInForce, STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
};

impl StockEtfPaperOrderRequestEnvelopeV1 {
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
