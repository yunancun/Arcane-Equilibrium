//! ADR-0048 Stock/ETF paper order request gap acceptance tests.
//!
//! These tests validate source-only request semantics. They do not start IPC,
//! contact IBKR, inspect secrets, create connectors, route paper orders, apply
//! DB migrations, or mutate existing Bybit behavior.

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, InstrumentKind,
    StockEtfLaneScopedIpcMethod, StockEtfLimitPricePolicy, StockEtfOrderSide,
    StockEtfPaperOrderRequestBlocker, StockEtfPaperOrderRequestEnvelopeV1,
    StockEtfPaperOrderRequestVerdict, StockEtfPaperOrderType, StockEtfPaperTimeInForce,
};

#[test]
fn paper_order_request_rejects_each_common_surface_gap_independently() {
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            contract_id: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ContractIdMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            source_version: 2,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SourceVersionMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            asset_lane: AssetLane::CfdMarginReserved,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::WrongAssetLane,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            broker: Broker::Bybit,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::WrongBroker,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            environment: BrokerEnvironment::ReadOnly,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::EnvironmentNotPaper,
    );
    assert_exact_blockers(
        StockEtfPaperOrderRequestEnvelopeV1 {
            environment: BrokerEnvironment::LiveReservedDenied,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        &[
            StockEtfPaperOrderRequestBlocker::LiveEnvironmentDenied,
            StockEtfPaperOrderRequestBlocker::EnvironmentNotPaper,
        ],
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            request_method: StockEtfLaneScopedIpcMethod::UnknownDenied,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::RequestMethodUnsupported,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            request_id: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::RequestIdMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            account_fingerprint_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::AccountFingerprintHashInvalid,
    );
}

#[test]
fn paper_order_request_rejects_each_method_authority_and_effect_gap_independently() {
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            operation: BrokerOperation::PaperOrderCancel,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::OperationMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            authority_scope: AuthorityScope::PaperRehearsal,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::AuthorityScopeMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            effect_capable: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::EffectCapabilityMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            operation: BrokerOperation::PaperOrderCancel,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::OperationMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            authority_scope: AuthorityScope::ReadOnly,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::AuthorityScopeMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            effect_capable: false,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::EffectCapabilityMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            operation: BrokerOperation::PaperOrderSubmit,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture()
        },
        StockEtfPaperOrderRequestBlocker::OperationMismatch,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            operation: BrokerOperation::PaperOrderSubmit,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::OperationMismatch,
    );
}

#[test]
fn paper_order_request_rejects_each_preview_hash_and_order_intent_gap_independently() {
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            risk_config_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::RiskConfigHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            instrument_identity_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::InstrumentIdentityHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            cost_model_version_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::CostModelVersionHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            pit_universe_contract_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::PitUniverseContractHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            source_artifact_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SourceArtifactHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            symbol: "spy".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SymbolInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            instrument_kind: Some(InstrumentKind::CryptoPerp),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::InstrumentKindDenied,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            side: Some(StockEtfOrderSide::Unknown),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SideMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            order_type: None,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::OrderTypeMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            quantity_decimal: "0".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::QuantityInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            limit_price_policy: Some(StockEtfLimitPricePolicy::AbsentForMarketOrder),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::LimitPricePolicyMismatch,
    );
    assert_exact_blockers(
        StockEtfPaperOrderRequestEnvelopeV1 {
            limit_price_decimal: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        &[
            StockEtfPaperOrderRequestBlocker::LimitPricePolicyMismatch,
            StockEtfPaperOrderRequestBlocker::LimitPriceInvalid,
        ],
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            time_in_force: None,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::TimeInForceMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            order_type: Some(StockEtfPaperOrderType::Market),
            limit_price_policy: Some(StockEtfLimitPricePolicy::AbsentForMarketOrder),
            limit_price_decimal: String::new(),
            time_in_force: Some(StockEtfPaperTimeInForce::Gtc),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture()
        },
        StockEtfPaperOrderRequestBlocker::TimeInForceIncompatible,
    );
}

#[test]
fn paper_order_request_rejects_each_effect_lifecycle_and_submit_gap_independently() {
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            session_attestation_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SessionAttestationHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            scoped_authorization_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ScopedAuthorizationHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            decision_lease_id: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::DecisionLeaseMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            guardian_state_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::GuardianStateHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            lifecycle_contract_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::LifecycleContractHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            broker_capability_registry_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::BrokerCapabilityRegistryHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            audit_event_id: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::AuditEventIdMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            order_local_id: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::LocalOrderIdMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            idempotency_key: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::IdempotencyKeyMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            broker_order_id: "paper_broker_order_0001".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SubmitBrokerOrderIdPresent,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            cancel_reason: "cancel_not_allowed".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SubmitCancelOrReplaceFieldPresent,
    );
}

#[test]
fn paper_order_request_rejects_each_cancel_and_replace_gap_independently() {
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            broker_order_id: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture()
        },
        StockEtfPaperOrderRequestBlocker::BrokerOrderIdMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            cancel_reason: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture()
        },
        StockEtfPaperOrderRequestBlocker::CancelReasonMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            symbol: "SPY".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture()
        },
        StockEtfPaperOrderRequestBlocker::CancelOrderShapeFieldPresent,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            replacement_idempotency_key: "replace_not_allowed".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SubmitCancelOrReplaceFieldPresent,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            instrument_identity_hash: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::InstrumentIdentityHashInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            replacement_idempotency_key: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ReplacementIdempotencyKeyMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            replacement_quantity_decimal: "0".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ReplacementQuantityInvalid,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            replacement_limit_price_policy: Some(StockEtfLimitPricePolicy::AbsentForMarketOrder),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ReplacementLimitPricePolicyMismatch,
    );
    assert_exact_blockers(
        StockEtfPaperOrderRequestEnvelopeV1 {
            replacement_limit_price_decimal: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        &[
            StockEtfPaperOrderRequestBlocker::ReplacementLimitPricePolicyMismatch,
            StockEtfPaperOrderRequestBlocker::ReplacementLimitPriceInvalid,
        ],
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            replacement_time_in_force: None,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ReplacementTimeInForceMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            replace_reason: String::new(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ReplaceReasonMissing,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            idempotency_key: "idem_not_allowed_on_replace".to_string(),
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ReplaceOriginalMutableFieldPresent,
    );
}

#[test]
fn paper_order_request_rejects_each_boundary_flag_independently() {
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            ibkr_contact_performed: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::IbkrContactPerformed,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            connector_runtime_started: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::ConnectorRuntimeStarted,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            secret_content_serialized: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::SecretContentSerialized,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            order_routed: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::OrderRouted,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            bybit_path_reused: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::BybitPathReused,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            live_or_tiny_live_authorized: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::LiveOrTinyLiveAuthorized,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            margin_short_options_cfd_requested: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::MarginShortOptionsCfdRequested,
    );
    assert_single_blocker(
        StockEtfPaperOrderRequestEnvelopeV1 {
            python_direct_broker_write_requested: true,
            ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
        },
        StockEtfPaperOrderRequestBlocker::PythonDirectBrokerWriteRequested,
    );
}

fn assert_single_blocker(
    candidate: StockEtfPaperOrderRequestEnvelopeV1,
    expected: StockEtfPaperOrderRequestBlocker,
) {
    assert_exact_blockers(candidate, &[expected]);
}

fn assert_exact_blockers(
    candidate: StockEtfPaperOrderRequestEnvelopeV1,
    expected: &[StockEtfPaperOrderRequestBlocker],
) {
    let verdict = candidate.validate();

    assert_verdict_blockers(verdict, expected);
}

fn assert_verdict_blockers(
    verdict: StockEtfPaperOrderRequestVerdict,
    expected: &[StockEtfPaperOrderRequestBlocker],
) {
    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers.as_slice(), expected);
}
