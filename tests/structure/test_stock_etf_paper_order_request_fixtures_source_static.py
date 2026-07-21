from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "rust/openclaw_types/src/stock_etf_paper_order_request/fixtures.rs"
MAX_LINES = 2_000

REQUIRED_SURFACE_TOKENS = {
    "Accepted Stock/ETF paper order request fixtures",
    "impl StockEtfPaperOrderRequestEnvelopeV1",
    "pub fn accepted_preview_fixture() -> Self",
    "pub fn accepted_submit_fixture() -> Self",
    "pub fn accepted_cancel_fixture() -> Self",
    "pub fn accepted_replace_fixture() -> Self",
    "STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID",
    "StockEtfLaneScopedIpcMethod",
    "BrokerOperation",
    "AuthorityScope",
    "InstrumentKind",
    "StockEtfOrderSide",
    "StockEtfPaperOrderType",
    "StockEtfLimitPricePolicy",
    "StockEtfPaperTimeInForce",
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
    return FIXTURES.read_text(encoding="utf-8")


def test_stock_etf_paper_order_request_fixtures_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_paper_order_request_fixtures_source_keeps_fixture_surface() -> None:
    source = _source()

    for token in REQUIRED_SURFACE_TOKENS:
        assert token in source


def test_stock_etf_paper_order_request_fixtures_source_keeps_preview_shape() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "request_method: StockEtfLaneScopedIpcMethod::PreviewPaperOrder" in source
    assert "operation: BrokerOperation::PaperOrderSubmit" in source
    assert "authority_scope: AuthorityScope::ReadOnly" in source
    assert 'request_id: "preview_request_0001".to_string()' in source
    assert "account_fingerprint_hash: \"1\".repeat(64)" in source
    assert "risk_config_hash: \"2\".repeat(64)" in source
    assert "instrument_identity_hash: \"3\".repeat(64)" in source
    assert "cost_model_version_hash: \"4\".repeat(64)" in source
    assert "pit_universe_contract_hash: \"5\".repeat(64)" in source
    assert "source_artifact_hash: \"6\".repeat(64)" in source
    assert 'symbol: "SPY".to_string()' in source
    assert "instrument_kind: Some(InstrumentKind::Etf)" in source
    assert "side: Some(StockEtfOrderSide::Buy)" in source
    assert "order_type: Some(StockEtfPaperOrderType::Limit)" in source
    assert 'quantity_decimal: "10".to_string()' in source
    assert "limit_price_policy: Some(StockEtfLimitPricePolicy::RequiredForLimitOrder)" in source
    assert 'limit_price_decimal: "450.25".to_string()' in source
    assert "time_in_force: Some(StockEtfPaperTimeInForce::Day)" in source
    assert "..Self::default()" in source


def test_stock_etf_paper_order_request_fixtures_source_keeps_submit_shape() -> None:
    source = _source()

    assert "request_method: StockEtfLaneScopedIpcMethod::SubmitPaperOrder" in source
    assert "authority_scope: AuthorityScope::PaperRehearsal" in source
    assert "effect_capable: true" in source
    assert 'request_id: "submit_request_0001".to_string()' in source
    assert "session_attestation_hash: \"7\".repeat(64)" in source
    assert "scoped_authorization_hash: \"8\".repeat(64)" in source
    assert 'decision_lease_id: "decision_lease_0001".to_string()' in source
    assert "guardian_state_hash: \"9\".repeat(64)" in source
    assert "lifecycle_contract_hash: \"a\".repeat(64)" in source
    assert "broker_capability_registry_hash: \"b\".repeat(64)" in source
    assert 'audit_event_id: "audit_event_0001".to_string()' in source
    assert "cost_model_version_hash: String::new()" in source
    assert "pit_universe_contract_hash: String::new()" in source
    assert "source_artifact_hash: String::new()" in source
    assert 'order_local_id: "local_order_0001".to_string()' in source
    assert 'idempotency_key: "idem_0001".to_string()' in source
    assert "..Self::accepted_preview_fixture()" in source


def test_stock_etf_paper_order_request_fixtures_source_keeps_cancel_and_replace_shapes() -> None:
    source = _source()

    assert "request_method: StockEtfLaneScopedIpcMethod::CancelPaperOrder" in source
    assert "operation: BrokerOperation::PaperOrderCancel" in source
    assert 'request_id: "cancel_request_0001".to_string()' in source
    assert 'audit_event_id: "audit_event_0002".to_string()' in source
    assert 'broker_order_id: "paper_broker_order_0001".to_string()' in source
    assert 'cancel_reason: "risk_or_operator_rehearsal".to_string()' in source

    assert "request_method: StockEtfLaneScopedIpcMethod::ReplacePaperOrder" in source
    assert "operation: BrokerOperation::PaperOrderReplace" in source
    assert 'request_id: "replace_request_0001".to_string()' in source
    assert 'audit_event_id: "audit_event_0003".to_string()' in source
    assert 'replacement_idempotency_key: "replace_idem_0001".to_string()' in source
    assert 'replacement_quantity_decimal: "12".to_string()' in source
    assert (
        "replacement_limit_price_policy: Some(StockEtfLimitPricePolicy::RequiredForLimitOrder)"
        in source
    )
    assert 'replacement_limit_price_decimal: "451.10".to_string()' in source
    assert "replacement_time_in_force: Some(StockEtfPaperTimeInForce::Day)" in source
    assert 'replace_reason: "paper_rehearsal_price_or_size_update".to_string()' in source
    assert "idempotency_key: String::new()" in source
    assert "cancel_reason: String::new()" in source
    assert "..Self::accepted_cancel_fixture()" in source


def test_stock_etf_paper_order_request_fixtures_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{FIXTURES}: contains forbidden token {token!r}")

    assert violations == []
