//! ADR-0048 Stock/ETF paper order request envelope acceptance tests.
//!
//! These tests validate source-only request semantics. They do not start IPC,
//! contact IBKR, inspect secrets, create connectors, route paper orders, apply
//! DB migrations, or mutate existing Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, InstrumentKind,
    StockEtfLaneScopedIpcMethod, StockEtfLimitPricePolicy, StockEtfOrderSide,
    StockEtfPaperOrderRequestBlocker, StockEtfPaperOrderRequestEnvelopeV1,
    StockEtfPaperOrderRequestVerdict, StockEtfPaperOrderType, StockEtfPaperTimeInForce,
    STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
};

#[test]
fn default_paper_order_request_envelope_blocks_all_authority() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let verdict = StockEtfPaperOrderRequestEnvelopeV1::default().validate();

    assert_verdict_blockers(
        verdict,
        &[
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::LiveEnvironmentDenied,
            Blocker::EnvironmentNotPaper,
            Blocker::RequestIdMissing,
            Blocker::AccountFingerprintHashInvalid,
            Blocker::RequestMethodUnsupported,
        ],
    );
}

#[test]
fn accepted_preview_submit_cancel_and_replace_envelopes_validate_without_side_effects() {
    let preview = StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture();
    let submit = StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture();
    let cancel = StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture();
    let replace = StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture();

    for envelope in [&preview, &submit, &cancel, &replace] {
        let verdict = envelope.validate();
        assert!(
            verdict.accepted,
            "unexpected blockers for {:?}: {:?}",
            envelope.request_method, verdict.blockers
        );
        assert_eq!(
            envelope.contract_id,
            STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID
        );
        assert_eq!(envelope.source_version, 1);
        assert_eq!(envelope.asset_lane, AssetLane::StockEtfCash);
        assert_eq!(envelope.broker, Broker::Ibkr);
        assert_eq!(envelope.environment, BrokerEnvironment::Paper);
        assert!(!envelope.ibkr_contact_performed);
        assert!(!envelope.connector_runtime_started);
        assert!(!envelope.secret_content_serialized);
        assert!(!envelope.order_routed);
        assert!(!envelope.bybit_path_reused);
        assert!(!envelope.live_or_tiny_live_authorized);
        assert!(!envelope.margin_short_options_cfd_requested);
        assert!(!envelope.python_direct_broker_write_requested);
    }

    assert_eq!(preview.authority_scope, AuthorityScope::ReadOnly);
    assert!(!preview.effect_capable);
    assert_eq!(submit.authority_scope, AuthorityScope::PaperRehearsal);
    assert!(submit.effect_capable);
    assert_eq!(cancel.operation, BrokerOperation::PaperOrderCancel);
    assert_eq!(replace.operation, BrokerOperation::PaperOrderReplace);
}

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

#[test]
fn request_method_surface_mismatches_block_operation_authority_and_effect_regressions() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let mut preview = StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture();
    preview.authority_scope = AuthorityScope::PaperRehearsal;
    preview.effect_capable = true;
    let verdict = preview.validate();
    assert_verdict_blockers(
        verdict,
        &[
            Blocker::AuthorityScopeMismatch,
            Blocker::EffectCapabilityMismatch,
        ],
    );

    let mut submit = StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture();
    submit.operation = BrokerOperation::PaperOrderCancel;
    submit.authority_scope = AuthorityScope::ReadOnly;
    submit.effect_capable = false;
    let verdict = submit.validate();
    assert_verdict_blockers(
        verdict,
        &[
            Blocker::OperationMismatch,
            Blocker::AuthorityScopeMismatch,
            Blocker::EffectCapabilityMismatch,
        ],
    );

    let mut cancel = StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture();
    cancel.operation = BrokerOperation::PaperOrderSubmit;
    cancel.authority_scope = AuthorityScope::ReadOnly;
    cancel.effect_capable = false;
    let verdict = cancel.validate();
    assert_verdict_blockers(
        verdict,
        &[
            Blocker::OperationMismatch,
            Blocker::AuthorityScopeMismatch,
            Blocker::EffectCapabilityMismatch,
        ],
    );

    let mut replace = StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture();
    replace.operation = BrokerOperation::PaperOrderSubmit;
    replace.authority_scope = AuthorityScope::ReadOnly;
    replace.effect_capable = false;
    let verdict = replace.validate();
    assert_verdict_blockers(
        verdict,
        &[
            Blocker::OperationMismatch,
            Blocker::AuthorityScopeMismatch,
            Blocker::EffectCapabilityMismatch,
        ],
    );
}

#[test]
fn effect_capable_requests_require_authorization_lifecycle_and_audit_hashes() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let mut submit = StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture();
    submit.session_attestation_hash.clear();
    submit.scoped_authorization_hash = "not-a-sha".to_string();
    submit.decision_lease_id.clear();
    submit.guardian_state_hash.clear();
    submit.lifecycle_contract_hash.clear();
    submit.broker_capability_registry_hash.clear();
    submit.audit_event_id.clear();

    let verdict = submit.validate();

    assert_verdict_blockers(
        verdict,
        &[
            Blocker::SessionAttestationHashInvalid,
            Blocker::ScopedAuthorizationHashInvalid,
            Blocker::DecisionLeaseMissing,
            Blocker::GuardianStateHashInvalid,
            Blocker::LifecycleContractHashInvalid,
            Blocker::BrokerCapabilityRegistryHashInvalid,
            Blocker::AuditEventIdMissing,
        ],
    );
}

#[test]
fn preview_request_rejects_effect_lifecycle_and_cancel_replace_pollution() {
    let mut preview_with_effect_fields =
        StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture();
    preview_with_effect_fields.session_attestation_hash = "7".repeat(64);
    preview_with_effect_fields.decision_lease_id = "decision_lease_0001".to_string();
    preview_with_effect_fields.broker_order_id = "paper_broker_order_0001".to_string();
    let verdict = preview_with_effect_fields.validate();
    assert_verdict_blockers(
        verdict,
        &[StockEtfPaperOrderRequestBlocker::PreviewEffectFieldPresent],
    );

    let mut preview_with_cancel_replace_fields =
        StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture();
    preview_with_cancel_replace_fields.cancel_reason = "cancel_not_allowed".to_string();
    preview_with_cancel_replace_fields.replacement_idempotency_key =
        "replace_not_allowed".to_string();
    let verdict = preview_with_cancel_replace_fields.validate();
    assert_verdict_blockers(
        verdict,
        &[StockEtfPaperOrderRequestBlocker::PreviewEffectFieldPresent],
    );
}

#[test]
fn submit_request_requires_stock_etf_order_intent_and_limit_price_policy() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let mut bad = StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture();
    bad.symbol = "spy".to_string();
    bad.instrument_kind = Some(InstrumentKind::CryptoPerp);
    bad.side = Some(StockEtfOrderSide::Unknown);
    bad.order_type = Some(StockEtfPaperOrderType::Limit);
    bad.quantity_decimal = "0.0".to_string();
    bad.limit_price_policy = Some(StockEtfLimitPricePolicy::AbsentForMarketOrder);
    bad.limit_price_decimal.clear();
    bad.time_in_force = None;

    let verdict = bad.validate();

    assert_verdict_blockers(
        verdict,
        &[
            Blocker::SymbolInvalid,
            Blocker::SideMissing,
            Blocker::InstrumentKindDenied,
            Blocker::QuantityInvalid,
            Blocker::LimitPricePolicyMismatch,
            Blocker::LimitPriceInvalid,
            Blocker::TimeInForceMissing,
        ],
    );
}

#[test]
fn market_submit_requires_absent_limit_price_and_day_tif() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let mut valid_market = StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture();
    valid_market.order_type = Some(StockEtfPaperOrderType::Market);
    valid_market.limit_price_policy = Some(StockEtfLimitPricePolicy::AbsentForMarketOrder);
    valid_market.limit_price_decimal.clear();
    valid_market.time_in_force = Some(StockEtfPaperTimeInForce::Day);
    assert!(valid_market.validate().accepted);

    valid_market.limit_price_decimal = "450.00".to_string();
    valid_market.time_in_force = Some(StockEtfPaperTimeInForce::Gtc);
    let verdict = valid_market.validate();

    assert_verdict_blockers(
        verdict,
        &[
            Blocker::LimitPricePolicyMismatch,
            Blocker::LimitPriceInvalid,
            Blocker::TimeInForceIncompatible,
        ],
    );
}

#[test]
fn cancel_request_rejects_submit_shape_pollution() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let mut cancel = StockEtfPaperOrderRequestEnvelopeV1::accepted_cancel_fixture();
    cancel.symbol = "SPY".to_string();
    cancel.instrument_kind = Some(InstrumentKind::Etf);
    cancel.side = Some(StockEtfOrderSide::Buy);
    cancel.order_type = Some(StockEtfPaperOrderType::Limit);
    cancel.quantity_decimal = "10".to_string();
    cancel.limit_price_policy = Some(StockEtfLimitPricePolicy::RequiredForLimitOrder);
    cancel.limit_price_decimal = "450.25".to_string();
    cancel.time_in_force = Some(StockEtfPaperTimeInForce::Day);
    cancel.broker_order_id.clear();
    cancel.cancel_reason.clear();

    let verdict = cancel.validate();

    assert_verdict_blockers(
        verdict,
        &[
            Blocker::BrokerOrderIdMissing,
            Blocker::CancelReasonMissing,
            Blocker::CancelOrderShapeFieldPresent,
        ],
    );
}

#[test]
fn replace_request_requires_replacement_shape_and_rejects_original_mutable_fields() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let mut replace = StockEtfPaperOrderRequestEnvelopeV1::accepted_replace_fixture();
    replace.replacement_idempotency_key.clear();
    replace.replacement_quantity_decimal = "0".to_string();
    replace.replacement_limit_price_policy = Some(StockEtfLimitPricePolicy::AbsentForMarketOrder);
    replace.replacement_limit_price_decimal.clear();
    replace.replacement_time_in_force = None;
    replace.replace_reason.clear();
    replace.quantity_decimal = "9".to_string();
    replace.limit_price_policy = Some(StockEtfLimitPricePolicy::RequiredForLimitOrder);

    let verdict = replace.validate();

    assert_verdict_blockers(
        verdict,
        &[
            Blocker::ReplacementIdempotencyKeyMissing,
            Blocker::ReplacementQuantityInvalid,
            Blocker::ReplacementLimitPricePolicyMismatch,
            Blocker::ReplacementTimeInForceMissing,
            Blocker::ReplaceReasonMissing,
            Blocker::ReplaceOriginalMutableFieldPresent,
        ],
    );
}

#[test]
fn request_envelope_rejects_boundary_regressions() {
    use StockEtfPaperOrderRequestBlocker as Blocker;

    let envelope = StockEtfPaperOrderRequestEnvelopeV1 {
        asset_lane: AssetLane::CryptoPerp,
        broker: Broker::Bybit,
        environment: BrokerEnvironment::LiveReservedDenied,
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        order_routed: true,
        bybit_path_reused: true,
        live_or_tiny_live_authorized: true,
        margin_short_options_cfd_requested: true,
        python_direct_broker_write_requested: true,
        ..StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture()
    };
    let verdict = envelope.validate();

    assert_verdict_blockers(
        verdict,
        &[
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::LiveEnvironmentDenied,
            Blocker::EnvironmentNotPaper,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::SecretContentSerialized,
            Blocker::OrderRouted,
            Blocker::BybitPathReused,
            Blocker::LiveOrTinyLiveAuthorized,
            Blocker::MarginShortOptionsCfdRequested,
            Blocker::PythonDirectBrokerWriteRequested,
        ],
    );
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_paper_order_request.template.toml"),
    )
    .expect("read paper order request template");
    let parsed: StockEtfPaperOrderRequestEnvelopeV1 =
        toml::from_str(&raw).expect("paper order request template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.connector_runtime_started);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.order_routed);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
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
