import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BROKER_CAPABILITY_REGISTRY = (
    ROOT / "rust/openclaw_types/src/stock_etf_broker_capability_registry.rs"
)
MAX_LINES = 800

REQUIRED_IMPORT_TOKENS = {
    "IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID",
    "IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "IBKR_PAPER_ATTESTATION_CONTRACT_ID",
    "STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID",
    "STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID",
    "STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID",
    "STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID",
    "STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID",
    "STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID",
    "STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID",
    "STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID",
    "STOCK_ETF_RISK_POLICY_CONTRACT_ID",
    "BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID",
    "STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID",
    "STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID",
    "STOCK_SHADOW_FILL_MODEL_CONTRACT_ID",
    "STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID",
}
REQUIRED_TYPE_TOKENS = {
    'STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID: &str = "broker_capability_registry_v1"',
    "const REQUIRED_AUDIT_FIELDS",
    "const REQUIRED_OPERATIONS",
    "pub struct StockEtfBrokerCapabilityRegistryV1",
    "impl Default for StockEtfBrokerCapabilityRegistryV1",
    "impl StockEtfBrokerCapabilityRegistryV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfBrokerCapabilityVerdict<StockEtfBrokerCapabilityBlocker>",
    "pub struct StockEtfBrokerCapabilityEntryV1",
    "impl StockEtfBrokerCapabilityEntryV1",
    "pub fn fixture_for_operation(operation: BrokerOperation) -> Self",
    "struct ExpectedCapability",
    "fn expected_capability(operation: BrokerOperation) -> ExpectedCapability",
    "fn validate_entry(",
    "fn contains_all(",
    "pub struct StockEtfBrokerCapabilityVerdict",
    "pub enum StockEtfBrokerCapabilityBlocker",
}
REQUIRED_REGISTRY_FIELDS = {
    "registry_id",
    "source_version",
    "asset_lane",
    "broker",
    "bybit_live_execution_unchanged",
    "python_broker_write_authority_denied",
    "ibkr_live_denied",
    "cfd_margin_reserved_denied",
    "first_ibkr_contact_performed",
    "secret_content_serialized",
    "required_audit_fields",
    "operations",
}
REQUIRED_ENTRY_FIELDS = {
    "operation",
    "authority_scope",
    "required_gates",
    "typed_denial_reason",
    "rust_owned",
    "audit_event_required",
    "source_artifact_hash_required",
}
REQUIRED_AUDIT_FIELDS = {
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "allowed",
    "denial_reason",
    "source_artifact_hash",
}
REQUIRED_OPERATIONS = {
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
REQUIRED_BLOCKERS = {
    "RegistryIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "BybitLiveExecutionNotProtected",
    "PythonBrokerWriteAuthorityNotDenied",
    "IbkrLiveNotDenied",
    "CfdMarginReservedNotDenied",
    "FirstIbkrContactPerformed",
    "SecretContentSerialized",
    "RequiredAuditFieldMissing",
    "OperationMissing",
    "OperationDuplicated",
    "OperationAuthorityScopeMismatch",
    "OperationRequiredGateMissing",
    "OperationTypedDenialMismatch",
    "OperationRustOwnershipMismatch",
    "OperationAuditEventMissing",
    "OperationSourceArtifactHashMissing",
}
REQUIRED_GATE_LITERALS = {
    "stock_etf_scoped_authorization_v1",
    "decision_lease_valid",
    "guardian_allows",
    "frozen_strategy_hypothesis_hash",
    "frozen_universe_hash",
    "paper_shadow_fill_separation",
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
    return BROKER_CAPABILITY_REGISTRY.read_text(encoding="utf-8")


def _paper_fill_import_block(source: str) -> str:
    match = re.search(
        r"Op::PaperOrderFillImport => ExpectedCapability \{(?P<body>.*?)\n        \},\n"
        r"        Op::ShadowSignalEmit",
        source,
        re.DOTALL,
    )
    assert match is not None
    return match.group("body")


def test_stock_etf_broker_capability_registry_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_broker_capability_registry_source_keeps_registry_contract() -> None:
    source = _source()

    for token in REQUIRED_IMPORT_TOKENS | REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_REGISTRY_FIELDS | REQUIRED_ENTRY_FIELDS | REQUIRED_AUDIT_FIELDS:
        assert field in source
    for operation in REQUIRED_OPERATIONS:
        assert f"BrokerOperation::{operation}" in source or f"Op::{operation}" in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source
    for gate in REQUIRED_GATE_LITERALS:
        assert gate in source

    assert "registry_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "python_broker_write_authority_denied: true" in source
    assert "ibkr_live_denied: true" in source
    assert "cfd_margin_reserved_denied: true" in source
    assert "first_ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_broker_capability_registry_source_keeps_operation_authority_matrix() -> None:
    source = _source()

    assert "Op::HealthRead" in source
    assert "authority_scope: Scope::ReadOnly" in source
    assert "IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID" in source
    assert "STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID" in source
    assert "STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID" in source
    assert "IBKR_SESSION_ATTESTATION_CONTRACT_ID" in source
    assert "STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID" in source
    assert "STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID" in source
    assert "Op::PaperOrderSubmit | Op::PaperOrderCancel | Op::PaperOrderReplace" in source
    assert "authority_scope: Scope::PaperRehearsal" in source
    assert "IBKR_PAPER_ATTESTATION_CONTRACT_ID" in source
    assert "STOCK_ETF_RISK_POLICY_CONTRACT_ID" in source
    assert "IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID" in source
    assert "rust_owned: true" in source
    assert "Op::PaperOrderFillImport" in source
    assert "Op::ShadowSignalEmit" in source
    assert "authority_scope: Scope::ShadowOnly" in source
    assert "STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID" in source
    assert "STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID" in source
    assert "STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID" in source
    assert "Op::ShadowFillReconstruct" in source
    assert "STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID" in source
    assert "STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID" in source
    assert "Op::ScorecardDerive" in source
    assert "STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID" in source
    assert "BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID" in source
    assert "STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID" in source
    assert "STOCK_SHADOW_FILL_MODEL_CONTRACT_ID" in source


def test_stock_etf_broker_capability_registry_source_keeps_paper_fill_import_readonly_gate() -> None:
    body = _paper_fill_import_block(_source())

    assert "authority_scope: Scope::ReadOnly" in body
    assert "IBKR_SESSION_ATTESTATION_CONTRACT_ID" in body
    assert "IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID" in body
    assert "typed_denial_reason: None" in body
    assert "rust_owned: false" in body
    assert "Scope::PaperRehearsal" not in body
    assert "stock_etf_scoped_authorization_v1" not in body
    assert "decision_lease_valid" not in body
    assert "guardian_allows" not in body


def test_stock_etf_broker_capability_registry_source_keeps_denied_and_validation_matrix() -> None:
    source = _source()

    assert "Op::LiveOrderSubmit" in source
    assert "typed_denial_reason: Some(Deny::IbkrLiveNotAuthorized)" in source
    assert "Op::MarginOrShort" in source
    assert "typed_denial_reason: Some(Deny::StockEtfCashOnly)" in source
    assert "Op::OptionsOrCfd" in source
    assert "typed_denial_reason: Some(Deny::InstrumentKindDenied)" in source
    assert "Op::TransferOrAccountWrite" in source
    assert "typed_denial_reason: Some(Deny::AccountWriteDenied)" in source
    assert "if !self.bybit_live_execution_unchanged" in source
    assert "if !self.python_broker_write_authority_denied" in source
    assert "if !self.ibkr_live_denied" in source
    assert "if !self.cfd_margin_reserved_denied" in source
    assert "if self.first_ibkr_contact_performed" in source
    assert "if self.secret_content_serialized" in source
    assert "if !contains_all(&self.required_audit_fields, REQUIRED_AUDIT_FIELDS)" in source
    assert "for operation in REQUIRED_OPERATIONS" in source
    assert "if matches.is_empty()" in source
    assert "if matches.len() > 1" in source
    assert "if entry.authority_scope != expected.authority_scope" in source
    assert "if !contains_all(&entry.required_gates, expected.required_gates)" in source
    assert "if entry.typed_denial_reason != expected.typed_denial_reason" in source
    assert "if entry.rust_owned != expected.rust_owned" in source
    assert "if !entry.audit_event_required" in source
    assert "if !entry.source_artifact_hash_required" in source


def test_stock_etf_broker_capability_registry_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{BROKER_CAPABILITY_REGISTRY}: contains forbidden token {token!r}")

    assert violations == []
