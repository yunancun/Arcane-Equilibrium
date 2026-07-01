from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "rust/openclaw_types/src/stock_etf_paper_order_request.rs"
VALIDATION = ROOT / "rust/openclaw_types/src/stock_etf_paper_order_request/validation.rs"
MAX_LINES = 800

REQUIRED_PARENT_TYPE_TOKENS = {
    'STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID: &str = "stock_etf_paper_order_request_v1"',
    "pub enum StockEtfPaperOrderType",
    "pub enum StockEtfPaperTimeInForce",
    "pub enum StockEtfLimitPricePolicy",
    "pub struct StockEtfPaperOrderRequestEnvelopeV1",
    "impl Default for StockEtfPaperOrderRequestEnvelopeV1",
    "pub struct StockEtfPaperOrderRequestVerdict",
    "pub enum StockEtfPaperOrderRequestBlocker",
    "mod fixtures;",
    "mod validation;",
}
REQUIRED_VALIDATION_TYPE_TOKENS = {
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
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "environment",
    "request_method",
    "operation",
    "authority_scope",
    "effect_capable",
    "request_id",
    "account_fingerprint_hash",
    "session_attestation_hash",
    "scoped_authorization_hash",
    "decision_lease_id",
    "guardian_state_hash",
    "risk_config_hash",
    "instrument_identity_hash",
    "cost_model_version_hash",
    "pit_universe_contract_hash",
    "source_artifact_hash",
    "lifecycle_contract_hash",
    "broker_capability_registry_hash",
    "audit_event_id",
    "symbol",
    "instrument_kind",
    "side",
    "order_type",
    "quantity_decimal",
    "limit_price_policy",
    "limit_price_decimal",
    "time_in_force",
    "order_local_id",
    "idempotency_key",
    "broker_order_id",
    "cancel_reason",
    "replacement_idempotency_key",
    "replacement_quantity_decimal",
    "replacement_limit_price_policy",
    "replacement_limit_price_decimal",
    "replacement_time_in_force",
    "replace_reason",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "order_routed",
    "bybit_path_reused",
    "live_or_tiny_live_authorized",
    "margin_short_options_cfd_requested",
    "python_direct_broker_write_requested",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "EnvironmentNotPaper",
    "LiveEnvironmentDenied",
    "RequestMethodUnsupported",
    "OperationMismatch",
    "AuthorityScopeMismatch",
    "EffectCapabilityMismatch",
    "RequestIdMissing",
    "AccountFingerprintHashInvalid",
    "SessionAttestationHashInvalid",
    "ScopedAuthorizationHashInvalid",
    "DecisionLeaseMissing",
    "GuardianStateHashInvalid",
    "RiskConfigHashInvalid",
    "InstrumentIdentityHashInvalid",
    "CostModelVersionHashInvalid",
    "PitUniverseContractHashInvalid",
    "SourceArtifactHashInvalid",
    "LifecycleContractHashInvalid",
    "BrokerCapabilityRegistryHashInvalid",
    "AuditEventIdMissing",
    "SymbolInvalid",
    "InstrumentKindDenied",
    "SideMissing",
    "OrderTypeMissing",
    "QuantityInvalid",
    "LimitPricePolicyMismatch",
    "LimitPriceInvalid",
    "TimeInForceMissing",
    "TimeInForceIncompatible",
    "LocalOrderIdMissing",
    "IdempotencyKeyMissing",
    "BrokerOrderIdMissing",
    "CancelReasonMissing",
    "ReplaceReasonMissing",
    "ReplacementIdempotencyKeyMissing",
    "ReplacementQuantityInvalid",
    "ReplacementLimitPricePolicyMismatch",
    "ReplacementLimitPriceInvalid",
    "ReplacementTimeInForceMissing",
    "PreviewEffectFieldPresent",
    "SubmitBrokerOrderIdPresent",
    "SubmitCancelOrReplaceFieldPresent",
    "CancelOrderShapeFieldPresent",
    "ReplaceOriginalMutableFieldPresent",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "OrderRouted",
    "BybitPathReused",
    "LiveOrTinyLiveAuthorized",
    "MarginShortOptionsCfdRequested",
    "PythonDirectBrokerWriteRequested",
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


def _parent() -> str:
    return PARENT.read_text(encoding="utf-8")


def _validation() -> str:
    return VALIDATION.read_text(encoding="utf-8")


def test_stock_etf_paper_order_request_source_stays_below_governance_cap() -> None:
    assert len(_parent().splitlines()) <= MAX_LINES
    assert len(_validation().splitlines()) <= MAX_LINES


def test_stock_etf_paper_order_request_source_keeps_envelope_contract() -> None:
    parent = _parent()
    validation = _validation()

    for token in REQUIRED_PARENT_TYPE_TOKENS:
        assert token in parent
    for token in REQUIRED_VALIDATION_TYPE_TOKENS:
        assert token in validation
    for field in REQUIRED_FIELDS:
        assert field in parent
    for blocker in REQUIRED_BLOCKERS:
        assert blocker in parent

    assert "contract_id: String::new()" in parent
    assert "source_version: 0" in parent
    assert "asset_lane: AssetLane::CryptoPerp" in parent
    assert "broker: Broker::Bybit" in parent
    assert "environment: BrokerEnvironment::LiveReservedDenied" in parent
    assert "request_method: StockEtfLaneScopedIpcMethod::UnknownDenied" in parent
    assert "operation: BrokerOperation::TransferOrAccountWrite" in parent
    assert "authority_scope: AuthorityScope::Denied" in parent
    assert "effect_capable: false" in parent
    assert "ibkr_contact_performed: false" in parent
    assert "connector_runtime_started: false" in parent
    assert "secret_content_serialized: false" in parent
    assert "order_routed: false" in parent
    assert "bybit_path_reused: false" in parent
    assert "live_or_tiny_live_authorized: false" in parent
    assert "margin_short_options_cfd_requested: false" in parent
    assert "python_direct_broker_write_requested: false" in parent
    assert "accepted: blockers.is_empty()" in validation


def test_stock_etf_paper_order_request_source_keeps_method_authority_surface() -> None:
    validation = _validation()

    assert "self.environment == BrokerEnvironment::LiveReservedDenied" in validation
    assert "self.environment != BrokerEnvironment::Paper" in validation
    assert "validate_boundary_flags(self, &mut blockers)" in validation
    assert "validate_expected_surface(self, &mut blockers)" in validation
    assert "StockEtfLaneScopedIpcMethod::PreviewPaperOrder" in validation
    assert "BrokerOperation::PaperOrderSubmit" in validation
    assert "AuthorityScope::ReadOnly" in validation
    assert "false" in validation
    assert "StockEtfLaneScopedIpcMethod::SubmitPaperOrder" in validation
    assert "AuthorityScope::PaperRehearsal" in validation
    assert "true" in validation
    assert "StockEtfLaneScopedIpcMethod::CancelPaperOrder" in validation
    assert "BrokerOperation::PaperOrderCancel" in validation
    assert "StockEtfLaneScopedIpcMethod::ReplacePaperOrder" in validation
    assert "BrokerOperation::PaperOrderReplace" in validation
    assert "if envelope.operation != operation" in validation
    assert "if envelope.authority_scope != authority_scope" in validation
    assert "if envelope.effect_capable != effect_capable" in validation
    assert "_ => blockers.push(Blocker::RequestMethodUnsupported)" in validation


def test_stock_etf_paper_order_request_source_keeps_shape_and_hash_validation() -> None:
    validation = _validation()

    assert "if self.request_id.trim().is_empty()" in validation
    assert "!is_sha256_hex(&self.account_fingerprint_hash)" in validation
    assert "validate_order_intent(envelope, blockers)" in validation
    assert "validate_preview_hashes(envelope, blockers)" in validation
    assert "validate_effect_hashes(envelope, blockers)" in validation
    assert "effect_or_lifecycle_field_present(envelope)" in validation
    assert "cancel_or_replace_field_present(envelope)" in validation
    assert "SubmitBrokerOrderIdPresent" in validation
    assert "SubmitCancelOrReplaceFieldPresent" in validation
    assert "CancelOrderShapeFieldPresent" in validation
    assert "ReplaceOriginalMutableFieldPresent" in validation
    assert "Some(InstrumentKind::Stock | InstrumentKind::Etf)" in validation
    assert "Some(StockEtfOrderSide::Buy | StockEtfOrderSide::Sell)" in validation
    assert "!is_positive_decimal(&envelope.quantity_decimal)" in validation
    assert "StockEtfPaperOrderType::Limit" in validation
    assert "StockEtfLimitPricePolicy::RequiredForLimitOrder" in validation
    assert "StockEtfPaperOrderType::Market" in validation
    assert "StockEtfLimitPricePolicy::AbsentForMarketOrder" in validation
    assert "StockEtfPaperTimeInForce::Day" in validation
    assert "StockEtfPaperTimeInForce::Gtc" in validation
    assert "if !is_sha256_hex(&envelope.session_attestation_hash)" in validation
    assert "if !is_sha256_hex(&envelope.scoped_authorization_hash)" in validation
    assert "if envelope.decision_lease_id.trim().is_empty()" in validation
    assert "if !is_sha256_hex(&envelope.guardian_state_hash)" in validation
    assert "if !is_sha256_hex(&envelope.lifecycle_contract_hash)" in validation
    assert "if !is_sha256_hex(&envelope.broker_capability_registry_hash)" in validation
    assert "if envelope.audit_event_id.trim().is_empty()" in validation


def test_stock_etf_paper_order_request_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    sources = {PARENT: _parent(), VALIDATION: _validation()}
    violations = []

    boundary_tokens = (
        "if envelope.ibkr_contact_performed",
        "if envelope.connector_runtime_started",
        "if envelope.secret_content_serialized",
        "if envelope.order_routed",
        "if envelope.bybit_path_reused",
        "if envelope.live_or_tiny_live_authorized",
        "if envelope.margin_short_options_cfd_requested",
        "if envelope.python_direct_broker_write_requested",
    )
    for token in boundary_tokens:
        assert token in sources[VALIDATION]

    for path, source in sources.items():
        for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden token {token!r}")

    assert violations == []
