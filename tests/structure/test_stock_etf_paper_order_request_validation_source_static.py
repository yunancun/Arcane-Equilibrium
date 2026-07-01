from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "rust/openclaw_types/src/stock_etf_paper_order_request/validation.rs"
MAX_LINES = 520

REQUIRED_HELPERS = {
    "impl StockEtfPaperOrderRequestEnvelopeV1",
    "pub fn validate(&self) -> StockEtfPaperOrderRequestVerdict",
    "fn validate_boundary_flags(",
    "fn validate_expected_surface(",
    "fn validate_preview(",
    "fn validate_submit(",
    "fn validate_cancel(",
    "fn validate_replace(",
    "fn validate_order_intent(",
    "fn validate_symbol_and_side(",
    "fn validate_preview_hashes(",
    "fn validate_effect_hashes(",
    "fn validate_limit_price(",
    "fn validate_replacement_limit_price(",
    "fn is_normalized_symbol(",
    "fn is_positive_decimal(",
    "fn effect_or_lifecycle_field_present(",
    "fn order_shape_field_present(",
    "fn original_mutable_field_present(",
    "fn cancel_or_replace_field_present(",
    "fn replace_field_present(",
}
FORBIDDEN_RUNTIME_TOKENS = (
    "std::env",
    "env::var",
    "var_os",
    "vars_os",
    "std::fs",
    "std::path::Path",
    "File::open",
    "OpenOptions",
    "read_to_string",
    "read_to_end",
    "include_str!",
    "include_bytes!",
    "std::net",
    "TcpStream",
    "UdpSocket",
    "tokio::net",
    "reqwest",
    "hyper::",
    "ureq",
    "ib_insync",
    "ibapi",
    "IBApi",
    "std::time",
    "SystemTime",
    "Instant",
    "chrono",
    "Utc::now",
    "Local::now",
    "std::thread",
    "thread::spawn",
    "tokio::spawn",
    "tokio::task",
    "tokio::time",
    "sleep(",
    "std::process",
    "process::Command",
    "Command::new",
    ".spawn(",
    "BybitRestClient",
    "BybitPrivateWs",
    "bybit_rest_client::",
    "bybit_private_ws::",
    "order_manager::",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "token =",
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return VALIDATION.read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    source = _source()
    marker = f"fn {name}("
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"function body not closed: {name}")


def _assert_tokens(source: str, tokens: tuple[str, ...]) -> None:
    for token in tokens:
        assert token in source


def test_stock_etf_paper_order_request_validation_source_stays_below_governance_cap() -> None:
    source = _source()

    assert len(source.splitlines()) <= MAX_LINES
    for token in REQUIRED_HELPERS:
        assert token in source


def test_stock_etf_paper_order_request_validation_keeps_top_level_fail_closed_dispatch() -> None:
    source = _source()
    validate_body = source[source.index("pub fn validate(&self)") : source.index(
        "fn validate_boundary_flags("
    )]

    _assert_tokens(
        validate_body,
        (
            "self.contract_id != STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID",
            "self.source_version != 1",
            "self.asset_lane != AssetLane::StockEtfCash",
            "self.broker != Broker::Ibkr",
            "self.environment == BrokerEnvironment::LiveReservedDenied",
            "self.environment != BrokerEnvironment::Paper",
            "validate_boundary_flags(self, &mut blockers)",
            "validate_expected_surface(self, &mut blockers)",
            "self.request_id.trim().is_empty()",
            "!is_sha256_hex(&self.account_fingerprint_hash)",
            "StockEtfLaneScopedIpcMethod::PreviewPaperOrder => validate_preview(self, &mut blockers)",
            "StockEtfLaneScopedIpcMethod::SubmitPaperOrder => validate_submit(self, &mut blockers)",
            "StockEtfLaneScopedIpcMethod::CancelPaperOrder => validate_cancel(self, &mut blockers)",
            "StockEtfLaneScopedIpcMethod::ReplacePaperOrder => validate_replace(self, &mut blockers)",
            "_ => blockers.push(Blocker::RequestMethodUnsupported)",
            "accepted: blockers.is_empty()",
        ),
    )


def test_stock_etf_paper_order_request_validation_keeps_boundary_and_surface_mapping() -> None:
    boundary = _function_body("validate_boundary_flags")
    expected_surface = _function_body("validate_expected_surface")

    _assert_tokens(
        boundary,
        (
            "if envelope.ibkr_contact_performed",
            "Blocker::IbkrContactPerformed",
            "if envelope.connector_runtime_started",
            "Blocker::ConnectorRuntimeStarted",
            "if envelope.secret_content_serialized",
            "Blocker::SecretContentSerialized",
            "if envelope.order_routed",
            "Blocker::OrderRouted",
            "if envelope.bybit_path_reused",
            "Blocker::BybitPathReused",
            "if envelope.live_or_tiny_live_authorized",
            "Blocker::LiveOrTinyLiveAuthorized",
            "if envelope.margin_short_options_cfd_requested",
            "Blocker::MarginShortOptionsCfdRequested",
            "if envelope.python_direct_broker_write_requested",
            "Blocker::PythonDirectBrokerWriteRequested",
        ),
    )
    _assert_tokens(
        expected_surface,
        (
            "StockEtfLaneScopedIpcMethod::PreviewPaperOrder => Some((",
            "BrokerOperation::PaperOrderSubmit",
            "AuthorityScope::ReadOnly",
            "false",
            "StockEtfLaneScopedIpcMethod::SubmitPaperOrder => Some((",
            "AuthorityScope::PaperRehearsal",
            "true",
            "StockEtfLaneScopedIpcMethod::CancelPaperOrder => Some((",
            "BrokerOperation::PaperOrderCancel",
            "StockEtfLaneScopedIpcMethod::ReplacePaperOrder => Some((",
            "BrokerOperation::PaperOrderReplace",
            "if envelope.operation != operation",
            "Blocker::OperationMismatch",
            "if envelope.authority_scope != authority_scope",
            "Blocker::AuthorityScopeMismatch",
            "if envelope.effect_capable != effect_capable",
            "Blocker::EffectCapabilityMismatch",
        ),
    )


def test_stock_etf_paper_order_request_validation_keeps_method_specific_field_separation() -> None:
    preview = _function_body("validate_preview")
    submit = _function_body("validate_submit")
    cancel = _function_body("validate_cancel")
    replace = _function_body("validate_replace")

    _assert_tokens(
        preview,
        (
            "validate_order_intent(envelope, blockers)",
            "validate_preview_hashes(envelope, blockers)",
            "effect_or_lifecycle_field_present(envelope)",
            "cancel_or_replace_field_present(envelope)",
            "Blocker::PreviewEffectFieldPresent",
        ),
    )
    _assert_tokens(
        submit,
        (
            "validate_order_intent(envelope, blockers)",
            "validate_effect_hashes(envelope, blockers)",
            "!is_sha256_hex(&envelope.risk_config_hash)",
            "!is_sha256_hex(&envelope.instrument_identity_hash)",
            "envelope.order_local_id.trim().is_empty()",
            "envelope.idempotency_key.trim().is_empty()",
            "!envelope.broker_order_id.trim().is_empty()",
            "Blocker::SubmitBrokerOrderIdPresent",
            "cancel_or_replace_field_present(envelope)",
            "Blocker::SubmitCancelOrReplaceFieldPresent",
        ),
    )
    _assert_tokens(
        cancel,
        (
            "validate_effect_hashes(envelope, blockers)",
            "envelope.order_local_id.trim().is_empty()",
            "envelope.idempotency_key.trim().is_empty()",
            "envelope.broker_order_id.trim().is_empty()",
            "envelope.cancel_reason.trim().is_empty()",
            "order_shape_field_present(envelope)",
            "Blocker::CancelOrderShapeFieldPresent",
            "replace_field_present(envelope)",
            "Blocker::SubmitCancelOrReplaceFieldPresent",
        ),
    )
    _assert_tokens(
        replace,
        (
            "validate_effect_hashes(envelope, blockers)",
            "envelope.order_local_id.trim().is_empty()",
            "envelope.broker_order_id.trim().is_empty()",
            "!is_sha256_hex(&envelope.instrument_identity_hash)",
            "validate_symbol_and_side(envelope, blockers)",
            "envelope.replacement_idempotency_key.trim().is_empty()",
            "!is_positive_decimal(&envelope.replacement_quantity_decimal)",
            "validate_replacement_limit_price(envelope, blockers)",
            "envelope.replacement_time_in_force.is_none()",
            "envelope.replace_reason.trim().is_empty()",
            "original_mutable_field_present(envelope)",
            "!envelope.idempotency_key.trim().is_empty()",
            "Blocker::ReplaceOriginalMutableFieldPresent",
        ),
    )


def test_stock_etf_paper_order_request_validation_keeps_order_shape_price_and_hash_gates() -> None:
    order_intent = _function_body("validate_order_intent")
    symbol_and_side = _function_body("validate_symbol_and_side")
    preview_hashes = _function_body("validate_preview_hashes")
    effect_hashes = _function_body("validate_effect_hashes")
    limit_price = _function_body("validate_limit_price")
    replacement_limit_price = _function_body("validate_replacement_limit_price")
    symbol = _function_body("is_normalized_symbol")
    decimal = _function_body("is_positive_decimal")

    _assert_tokens(
        order_intent,
        (
            "Some(InstrumentKind::Stock | InstrumentKind::Etf)",
            "Blocker::InstrumentKindDenied",
            "envelope.order_type.is_none()",
            "!is_positive_decimal(&envelope.quantity_decimal)",
            "validate_limit_price(envelope, blockers)",
            "Some(StockEtfPaperTimeInForce::Day)",
            "Some(StockEtfPaperTimeInForce::Gtc)",
            "envelope.order_type == Some(StockEtfPaperOrderType::Limit)",
            "Blocker::TimeInForceIncompatible",
            "Blocker::TimeInForceMissing",
        ),
    )
    _assert_tokens(
        symbol_and_side,
        (
            "!is_normalized_symbol(&envelope.symbol)",
            "Some(StockEtfOrderSide::Buy | StockEtfOrderSide::Sell)",
            "Blocker::SideMissing",
        ),
    )
    _assert_tokens(
        preview_hashes,
        (
            "risk_config_hash",
            "instrument_identity_hash",
            "cost_model_version_hash",
            "pit_universe_contract_hash",
            "source_artifact_hash",
        ),
    )
    _assert_tokens(
        effect_hashes,
        (
            "session_attestation_hash",
            "scoped_authorization_hash",
            "decision_lease_id.trim().is_empty()",
            "guardian_state_hash",
            "lifecycle_contract_hash",
            "broker_capability_registry_hash",
            "audit_event_id.trim().is_empty()",
        ),
    )
    _assert_tokens(
        limit_price,
        (
            "StockEtfPaperOrderType::Limit",
            "StockEtfLimitPricePolicy::RequiredForLimitOrder",
            "StockEtfPaperOrderType::Market",
            "StockEtfLimitPricePolicy::AbsentForMarketOrder",
            "Blocker::LimitPricePolicyMismatch",
            "Blocker::LimitPriceInvalid",
        ),
    )
    _assert_tokens(
        replacement_limit_price,
        (
            "StockEtfLimitPricePolicy::RequiredForLimitOrder",
            "StockEtfLimitPricePolicy::Unchanged",
            "Blocker::ReplacementLimitPricePolicyMismatch",
            "Blocker::ReplacementLimitPriceInvalid",
        ),
    )
    _assert_tokens(
        symbol,
        (
            "trimmed.len() <= 24",
            "trimmed == symbol",
            "b.is_ascii_uppercase() || b.is_ascii_digit() || matches!(b, b'.' | b'-')",
        ),
    )
    _assert_tokens(
        decimal,
        (
            "raw.is_empty()",
            "raw.starts_with(['+', '-'])",
            "raw.matches('.').count() > 1",
            "saw_digit && saw_nonzero",
        ),
    )


def test_stock_etf_paper_order_request_validation_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{VALIDATION}: contains forbidden token {token!r}")

    assert violations == []
