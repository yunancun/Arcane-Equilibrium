//! ADR-0048 Stock/ETF paper order request envelope acceptance tests.
//!
//! These tests validate source-only request semantics. They do not start IPC,
//! contact IBKR, inspect secrets, create connectors, route paper orders, apply
//! DB migrations, or mutate existing Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, InstrumentKind,
    StockEtfLimitPricePolicy, StockEtfOrderSide, StockEtfPaperOrderRequestBlocker,
    StockEtfPaperOrderRequestEnvelopeV1, StockEtfPaperOrderRequestVerdict, StockEtfPaperOrderType,
    StockEtfPaperTimeInForce, STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
};

#[test]
fn default_paper_order_request_envelope_blocks_all_authority() {
    let verdict = StockEtfPaperOrderRequestEnvelopeV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::WrongAssetLane
    ));
    assert!(has(&verdict, StockEtfPaperOrderRequestBlocker::WrongBroker));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::LiveEnvironmentDenied
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::RequestMethodUnsupported
    ));
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
fn submit_request_requires_stock_etf_order_intent_and_limit_price_policy() {
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

    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::SymbolInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::InstrumentKindDenied
    ));
    assert!(has(&verdict, StockEtfPaperOrderRequestBlocker::SideMissing));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::QuantityInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::LimitPricePolicyMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::LimitPriceInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::TimeInForceMissing
    ));
}

#[test]
fn market_submit_requires_absent_limit_price_and_day_tif() {
    let mut valid_market = StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture();
    valid_market.order_type = Some(StockEtfPaperOrderType::Market);
    valid_market.limit_price_policy = Some(StockEtfLimitPricePolicy::AbsentForMarketOrder);
    valid_market.limit_price_decimal.clear();
    valid_market.time_in_force = Some(StockEtfPaperTimeInForce::Day);
    assert!(valid_market.validate().accepted);

    valid_market.limit_price_decimal = "450.00".to_string();
    valid_market.time_in_force = Some(StockEtfPaperTimeInForce::Gtc);
    let verdict = valid_market.validate();

    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::LimitPriceInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::TimeInForceIncompatible
    ));
}

#[test]
fn cancel_request_rejects_submit_shape_pollution() {
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

    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::BrokerOrderIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::CancelReasonMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::CancelOrderShapeFieldPresent
    ));
}

#[test]
fn replace_request_requires_replacement_shape_and_rejects_original_mutable_fields() {
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

    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ReplacementIdempotencyKeyMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ReplacementQuantityInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ReplacementLimitPricePolicyMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ReplacementTimeInForceMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ReplaceReasonMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ReplaceOriginalMutableFieldPresent
    ));
}

#[test]
fn request_envelope_rejects_boundary_regressions() {
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

    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::WrongAssetLane
    ));
    assert!(has(&verdict, StockEtfPaperOrderRequestBlocker::WrongBroker));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::LiveEnvironmentDenied
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::SecretContentSerialized
    ));
    assert!(has(&verdict, StockEtfPaperOrderRequestBlocker::OrderRouted));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::BybitPathReused
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::LiveOrTinyLiveAuthorized
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::MarginShortOptionsCfdRequested
    ));
    assert!(has(
        &verdict,
        StockEtfPaperOrderRequestBlocker::PythonDirectBrokerWriteRequested
    ));
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

fn has(
    verdict: &StockEtfPaperOrderRequestVerdict,
    blocker: StockEtfPaperOrderRequestBlocker,
) -> bool {
    verdict.blockers.contains(&blocker)
}
