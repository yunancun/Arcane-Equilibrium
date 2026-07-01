import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STOCK_ETF_LANE = ROOT / "rust/openclaw_types/src/stock_etf_lane.rs"
MAX_LINES = 800

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


def test_stock_etf_lane_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{STOCK_ETF_LANE}: contains forbidden token {token!r}")

    assert violations == []
