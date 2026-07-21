import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STOCK_ETF_LANE = ROOT / "rust/openclaw_types/src/stock_etf_lane.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

EXPECTED_FEATURE_FLAG_KEYS = {
    "OPENCLAW_STOCK_ETF_LANE_ENABLED",
    "OPENCLAW_IBKR_READONLY_ENABLED",
    "OPENCLAW_IBKR_PAPER_ENABLED",
    "OPENCLAW_ASSET_LANE_DEFAULT",
    "OPENCLAW_STOCK_ETF_SHADOW_ONLY",
}
REQUIRED_TYPE_TOKENS = {
    "pub enum AssetLane",
    "pub enum Broker",
    "pub enum BrokerEnvironment",
    "pub enum InstrumentKind",
    "pub enum AuthorityScope",
    "pub enum BrokerOperation",
    "pub enum StockEtfDenialReason",
    "pub struct StockEtfFeatureFlags",
    "pub struct StockEtfReadiness",
    "pub struct StockEtfGateInputs",
    "pub struct BrokerCapabilityRequest",
    "pub struct BrokerCapabilityDecision",
    "pub enum IbkrPaperOrderLifecycleState",
    "pub fn evaluate_broker_operation(",
}
REQUIRED_OPERATION_VARIANTS = {
    "HealthRead",
    "AccountSnapshotRead",
    "MarketDataRead",
    "ContractDetailsRead",
    "PaperOrderSubmit",
    "PaperOrderCancel",
    "PaperOrderReplace",
    "PaperOrderFillImport",
    "ShadowSignalEmit",
    "ShadowFillReconstruct",
    "ScorecardDerive",
    "LiveOrderSubmit",
    "MarginOrShort",
    "OptionsOrCfd",
    "TransferOrAccountWrite",
}
REQUIRED_DENIAL_VARIANTS = {
    "LaneDisabled",
    "BrokerDisabled",
    "ShadowOnly",
    "LiveReservedDenied",
    "MarketClosed",
    "InstrumentBlocked",
    "CostModelMissing",
    "UniverseMismatch",
    "CredentialUnavailable",
    "ConnectorUnavailable",
    "AuthorizationInvalid",
    "DecisionLeaseInvalid",
    "GuardianDenied",
    "IbkrLiveNotAuthorized",
    "StockEtfCashOnly",
    "InstrumentKindDenied",
    "AccountWriteDenied",
    "WrongAssetLane",
    "WrongBroker",
    "WrongEnvironment",
}
REQUIRED_GATE_FIELDS = {
    "external_surface_gate_passed",
    "session_attested",
    "scoped_authorization_present",
    "decision_lease_valid",
    "guardian_allows",
    "risk_config_hash_present",
    "instrument_identity_hash_present",
    "idempotency_key_present",
    "market_open",
    "cost_model_present",
    "universe_match",
    "credential_available",
    "connector_available",
}
FORBIDDEN_RUNTIME_TOKENS = (
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
    "account_id",
    "OPENCLAW_IBKR_ACCOUNT",
    "OPENCLAW_IBKR_SECRET",
    "OPENCLAW_IBKR_TOKEN",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return STOCK_ETF_LANE.read_text(encoding="utf-8")


def _block_between(source: str, start_token: str, end_tokens: tuple[str, ...]) -> str:
    start = source.index(start_token)
    end = len(source)
    for token in end_tokens:
        candidate = source.find(token, start + len(start_token))
        if candidate != -1:
            end = min(end, candidate)
    return source[start:end]


def _default_block(source: str, type_name: str) -> str:
    return _block_between(
        source,
        f"impl Default for {type_name}",
        ("\n}\n\nimpl ", "\n}\n\n#[derive"),
    )


def _broker_operation_bool_method_body(source: str, method_name: str) -> str:
    match = re.search(
        rf"pub const fn {method_name}\(self\) -> bool \{{(?P<body>.*?)\n    \}}",
        source,
        re.DOTALL,
    )
    assert match is not None
    return match.group("body")


def test_stock_etf_lane_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_lane_source_keeps_boundary_taxonomy_matrix() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for variant in REQUIRED_OPERATION_VARIANTS:
        assert f"Self::{variant}" in source
    for variant in REQUIRED_DENIAL_VARIANTS:
        assert f"Self::{variant}" in source
    for field in REQUIRED_GATE_FIELDS:
        assert field in source

    assert 'Self::StockEtfCash => "stock_etf_cash"' in source
    assert 'Self::Ibkr => "ibkr"' in source
    assert 'Self::LiveReservedDenied => "live_reserved_denied"' in source
    assert "pub const fn allows_ibkr_live(self) -> bool {\n        false\n    }" in source
    assert "request.operation == Op::LiveOrderSubmit" in source
    assert "request.operation == Op::MarginOrShort" in source
    assert "request.operation == Op::OptionsOrCfd" in source
    assert "request.operation == Op::TransferOrAccountWrite" in source


def test_stock_etf_lane_source_keeps_operation_authority_classification() -> None:
    source = _source()
    read_body = _broker_operation_bool_method_body(source, "is_read")
    paper_write_body = _broker_operation_bool_method_body(source, "is_paper_write")
    shadow_body = _broker_operation_bool_method_body(source, "is_shadow")

    for operation in (
        "Self::HealthRead",
        "Self::AccountSnapshotRead",
        "Self::MarketDataRead",
        "Self::ContractDetailsRead",
        "Self::PaperOrderFillImport",
        "Self::ScorecardDerive",
    ):
        assert operation in read_body

    for operation in (
        "Self::PaperOrderSubmit",
        "Self::PaperOrderCancel",
        "Self::PaperOrderReplace",
    ):
        assert operation in paper_write_body
        assert operation not in read_body

    assert "Self::PaperOrderFillImport" not in paper_write_body
    assert "Self::ShadowSignalEmit" in shadow_body
    assert "Self::ShadowFillReconstruct" in shadow_body
    assert "Self::PaperOrderFillImport" not in shadow_body
    assert "pub const fn authority_scope(self) -> AuthorityScope" in source
    assert "if self.is_paper_write() {\n            AuthorityScope::PaperRehearsal" in source
    assert "} else if self.is_shadow() {\n            AuthorityScope::ShadowOnly" in source
    assert "} else if self.is_read() {\n            AuthorityScope::ReadOnly" in source
    assert "} else {\n            AuthorityScope::Denied" in source


def test_stock_etf_lane_source_keeps_feature_flag_env_allowlist_scoped() -> None:
    source = _source()
    feature_flag_keys = set(re.findall(r'"(OPENCLAW_[A-Z0-9_]+)"', source))

    assert feature_flag_keys == EXPECTED_FEATURE_FLAG_KEYS
    assert source.count("std::env::var(key).ok()") == 1
    assert source.count("std::env::var") == 1
    assert "pub fn from_env() -> Result<Self, StockEtfConfigError>" in source
    assert "pub fn from_lookup<F>(lookup: F)" in source

    for key in feature_flag_keys:
        lower = key.lower()
        assert "secret" not in lower
        assert "token" not in lower
        assert "password" not in lower
        assert "account" not in lower
        assert "key" not in lower


def test_stock_etf_lane_source_keeps_feature_flag_default_fail_closed() -> None:
    default = _default_block(_source(), "StockEtfFeatureFlags")

    for fail_closed in (
        "stock_etf_lane_enabled: false",
        "ibkr_readonly_enabled: false",
        "ibkr_paper_enabled: false",
        "asset_lane_default: AssetLane::CryptoPerp",
        "stock_etf_shadow_only: true",
    ):
        assert fail_closed in default

    for forbidden in (
        "stock_etf_lane_enabled: true",
        "ibkr_readonly_enabled: true",
        "ibkr_paper_enabled: true",
        "asset_lane_default: AssetLane::StockEtfCash",
        "stock_etf_shadow_only: false",
    ):
        assert forbidden not in default


def test_stock_etf_lane_source_keeps_gate_inputs_default_fail_closed() -> None:
    default = _default_block(_source(), "StockEtfGateInputs")

    for fail_closed in (
        "external_surface_gate_passed: false",
        "session_attested: false",
        "scoped_authorization_present: false",
        "decision_lease_valid: false",
        "guardian_allows: false",
        "risk_config_hash_present: false",
        "instrument_identity_hash_present: false",
        "idempotency_key_present: false",
        "market_open: true",
        "cost_model_present: false",
        "universe_match: false",
        "credential_available: false",
        "connector_available: false",
    ):
        assert fail_closed in default

    for forbidden in (
        "external_surface_gate_passed: true",
        "session_attested: true",
        "scoped_authorization_present: true",
        "decision_lease_valid: true",
        "guardian_allows: true",
        "risk_config_hash_present: true",
        "instrument_identity_hash_present: true",
        "idempotency_key_present: true",
        "market_open: false",
        "cost_model_present: true",
        "universe_match: true",
        "credential_available: true",
        "connector_available: true",
    ):
        assert forbidden not in default


def test_stock_etf_lane_source_keeps_evaluate_broker_operation_denial_order() -> None:
    source = _source()
    evaluator = _block_between(
        source,
        "pub fn evaluate_broker_operation(",
        ("\n#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]",),
    )

    ordered_tokens = [
        "request.asset_lane != AssetLane::StockEtfCash",
        "request.broker != Broker::Ibkr",
        "request.environment == BrokerEnvironment::LiveReservedDenied",
        "request.operation == Op::LiveOrderSubmit",
        "request.operation == Op::MarginOrShort",
        "request.operation == Op::OptionsOrCfd",
        "request.operation == Op::TransferOrAccountWrite",
        "!request.instrument_kind.allowed_for_stock_etf_cash()",
        "!flags.stock_etf_lane_enabled",
        "request.operation.is_read() && !flags.ibkr_readonly_enabled",
        "request.operation.is_paper_write() && !flags.ibkr_paper_enabled",
        "request.operation.is_paper_write() && flags.stock_etf_shadow_only",
        "request.operation.is_read() && !gates.external_surface_gate_passed",
        "request.operation.is_shadow()",
        "if request.operation.is_paper_write() {\n        if !gates.market_open",
    ]
    positions = [evaluator.index(token) for token in ordered_tokens]
    assert positions == sorted(positions)

    for denial in (
        "Deny::WrongAssetLane",
        "Deny::WrongBroker",
        "Deny::LiveReservedDenied",
        "Deny::IbkrLiveNotAuthorized",
        "Deny::StockEtfCashOnly",
        "Deny::InstrumentKindDenied",
        "Deny::AccountWriteDenied",
        "Deny::LaneDisabled",
        "Deny::BrokerDisabled",
        "Deny::ShadowOnly",
        "Deny::AuthorizationInvalid",
        "Deny::CostModelMissing",
        "Deny::UniverseMismatch",
        "Deny::MarketClosed",
        "Deny::CredentialUnavailable",
        "Deny::ConnectorUnavailable",
        "Deny::DecisionLeaseInvalid",
        "Deny::GuardianDenied",
    ):
        assert denial in evaluator


def test_stock_etf_lane_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{STOCK_ETF_LANE}: contains forbidden token {token!r}")

    assert violations == []
