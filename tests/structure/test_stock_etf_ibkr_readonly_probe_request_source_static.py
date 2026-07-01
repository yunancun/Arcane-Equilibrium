import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READONLY_PROBE = ROOT / "rust/openclaw_types/src/stock_etf_ibkr_readonly_probe_request.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID",
    '"stock_etf_ibkr_readonly_probe_request_v1"',
    "pub enum StockEtfIbkrReadonlyProbeKind",
    "pub struct StockEtfIbkrReadonlyProbeRequestV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfIbkrReadonlyProbeVerdict",
    "pub struct StockEtfIbkrReadonlyProbeVerdict",
    "pub enum StockEtfIbkrReadonlyProbeBlocker",
    "fn expected_api_action(kind: StockEtfIbkrReadonlyProbeKind) -> NonBybitApiAction",
    "fn expected_operation(kind: StockEtfIbkrReadonlyProbeKind) -> BrokerOperation",
    "fn validate_required_fields(",
    "fn validate_boundary_flags(",
    "classify_non_bybit_api_action",
    "NON_BYBIT_API_ALLOWLIST_CONTRACT_ID",
    "IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID",
    "IBKR_RATE_LIMIT_POLICY_CONTRACT_ID",
    "IBKR_REDACTION_POLICY_CONTRACT_ID",
    "IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID",
    "IBKR_SECRET_SLOT_CONTRACT_ID",
}
REQUIRED_PROBE_KINDS = {
    "ServerTime",
    "ConnectionHealth",
    "AccountSummarySnapshot",
    "PortfolioPositionsSnapshot",
    "ContractDetails",
    "MarketDataSnapshot",
    "HistoricalBars",
    "OpenPaperOrders",
    "PaperExecutionsCommissions",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "environment",
    "probe_kind",
    "api_action",
    "operation",
    "authority_scope",
    "effect_capable",
    "request_id",
    "probe_id",
    "external_surface_gate_contract_id",
    "phase2_gate_artifact_hash",
    "api_allowlist_contract_id",
    "api_allowlist_hash",
    "secret_slot_contract_id",
    "secret_slot_contract_hash",
    "api_session_topology_contract_id",
    "api_session_topology_hash",
    "session_attestation_contract_id",
    "session_attestation_hash",
    "redaction_policy_contract_id",
    "redaction_policy_hash",
    "rate_limit_policy_contract_id",
    "rate_limit_policy_hash",
    "audit_event_policy_contract_id",
    "audit_event_policy_hash",
    "source_artifact_hash",
    "raw_artifact_hash",
    "redacted_summary_hash",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "order_routed",
    "paper_order_submitted",
    "db_apply_performed",
    "evidence_clock_started",
    "bybit_path_reused",
    "live_or_tiny_live_authorized",
    "margin_short_options_cfd_requested",
    "account_write_requested",
    "market_data_entitlement_purchase_requested",
    "client_portal_web_api_requested",
    "python_direct_broker_write_requested",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "EnvironmentNotReadonly",
    "ProbeActionMismatch",
    "OperationMismatch",
    "AuthorityScopeMismatch",
    "EffectCapabilityPresent",
    "ApiActionNotReadAllowed",
    "RequestIdMissing",
    "ProbeIdMissing",
    "ExternalSurfaceGateContractIdMismatch",
    "Phase2GateArtifactHashInvalid",
    "ApiAllowlistContractIdMismatch",
    "ApiAllowlistHashInvalid",
    "SecretSlotContractIdMismatch",
    "SecretSlotContractHashInvalid",
    "ApiSessionTopologyContractIdMismatch",
    "ApiSessionTopologyHashInvalid",
    "SessionAttestationContractIdMismatch",
    "SessionAttestationHashInvalid",
    "RedactionPolicyContractIdMismatch",
    "RedactionPolicyHashInvalid",
    "RateLimitPolicyContractIdMismatch",
    "RateLimitPolicyHashInvalid",
    "AuditEventPolicyContractIdMismatch",
    "AuditEventPolicyHashInvalid",
    "SourceArtifactHashInvalid",
    "RawArtifactHashInvalid",
    "RedactedSummaryHashInvalid",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "OrderRouted",
    "PaperOrderSubmitted",
    "DbApplyPerformed",
    "EvidenceClockStarted",
    "BybitPathReused",
    "LiveOrTinyLiveAuthorized",
    "MarginShortOptionsCfdRequested",
    "AccountWriteRequested",
    "MarketDataEntitlementPurchaseRequested",
    "ClientPortalWebApiRequested",
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


def _source() -> str:
    return READONLY_PROBE.read_text(encoding="utf-8")


def _function_body(source: str, function_name: str, return_type: str) -> str:
    match = re.search(
        rf"fn {function_name}\(kind: StockEtfIbkrReadonlyProbeKind\) -> {return_type} \{{(?P<body>.*?)\n\}}",
        source,
        re.DOTALL,
    )
    assert match is not None
    return match.group("body")


def test_stock_etf_readonly_probe_request_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_readonly_probe_request_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_PROBE_KINDS | REQUIRED_FIELDS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_readonly_probe_request_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "environment: BrokerEnvironment::LiveReservedDenied" in source
    assert "probe_kind: StockEtfIbkrReadonlyProbeKind::ConnectionHealth" in source
    assert "api_action: NonBybitApiAction::ClientPortalWebApiUse" in source
    assert "operation: BrokerOperation::TransferOrAccountWrite" in source
    assert "authority_scope: AuthorityScope::Denied" in source
    assert "effect_capable: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "secret_content_serialized: false" in source
    assert "order_routed: false" in source
    assert "paper_order_submitted: false" in source
    assert "db_apply_performed: false" in source
    assert "evidence_clock_started: false" in source
    assert "bybit_path_reused: false" in source
    assert "live_or_tiny_live_authorized: false" in source
    assert "margin_short_options_cfd_requested: false" in source
    assert "account_write_requested: false" in source
    assert "market_data_entitlement_purchase_requested: false" in source
    assert "client_portal_web_api_requested: false" in source
    assert "python_direct_broker_write_requested: false" in source


def test_stock_etf_readonly_probe_request_source_keeps_accepted_fixture_boundary() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::ReadOnly" in source
    assert "probe_kind: StockEtfIbkrReadonlyProbeKind::ConnectionHealth" in source
    assert "api_action: NonBybitApiAction::ConnectionHealthRead" in source
    assert "operation: BrokerOperation::HealthRead" in source
    assert "authority_scope: AuthorityScope::ReadOnly" in source
    assert "effect_capable: false" in source
    assert 'request_id: "readonly_probe_request_0001".to_string()' in source
    assert 'probe_id: "readonly_probe_0001".to_string()' in source
    assert "external_surface_gate_contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string()" in source
    assert "api_allowlist_contract_id: NON_BYBIT_API_ALLOWLIST_CONTRACT_ID.to_string()" in source
    assert "secret_slot_contract_id: IBKR_SECRET_SLOT_CONTRACT_ID.to_string()" in source
    assert "api_session_topology_contract_id: IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID.to_string()" in source
    assert "session_attestation_contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string()" in source
    assert "redaction_policy_contract_id: IBKR_REDACTION_POLICY_CONTRACT_ID.to_string()" in source
    assert "rate_limit_policy_contract_id: IBKR_RATE_LIMIT_POLICY_CONTRACT_ID.to_string()" in source
    assert "audit_event_policy_contract_id: IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID.to_string()" in source
    assert "..Self::default()" in source


def test_stock_etf_readonly_probe_request_source_keeps_action_and_operation_mapping() -> None:
    source = _source()
    api_body = _function_body(source, "expected_api_action", "NonBybitApiAction")
    operation_body = _function_body(source, "expected_operation", "BrokerOperation")

    for kind, action in (
        ("ServerTime", "ServerTimeRead"),
        ("ConnectionHealth", "ConnectionHealthRead"),
        ("AccountSummarySnapshot", "AccountSummarySnapshotRead"),
        ("PortfolioPositionsSnapshot", "PortfolioPositionsSnapshotRead"),
        ("ContractDetails", "ContractDetailsRead"),
        ("MarketDataSnapshot", "MarketDataSnapshotRead"),
        ("HistoricalBars", "HistoricalBarsRead"),
        ("OpenPaperOrders", "OpenPaperOrdersRead"),
        ("PaperExecutionsCommissions", "PaperExecutionsCommissionsRead"),
    ):
        assert f"StockEtfIbkrReadonlyProbeKind::{kind}" in source
        assert f"NonBybitApiAction::{action}" in source

    assert "BrokerOperation::HealthRead" in source
    assert "BrokerOperation::AccountSnapshotRead" in source
    assert "BrokerOperation::ContractDetailsRead" in source
    assert "BrokerOperation::MarketDataRead" in source
    assert "NonBybitApiAction::PaperOrderSubmit" not in api_body
    assert "NonBybitApiAction::PaperOrderCancel" not in api_body
    assert "NonBybitApiAction::PaperOrderReplace" not in api_body
    assert "BrokerOperation::PaperOrderSubmit" not in operation_body
    assert "BrokerOperation::PaperOrderCancel" not in operation_body
    assert "BrokerOperation::PaperOrderReplace" not in operation_body
    assert "BrokerOperation::LiveOrderSubmit" not in operation_body
    assert (
        "StockEtfIbkrReadonlyProbeKind::OpenPaperOrders\n        | StockEtfIbkrReadonlyProbeKind::PaperExecutionsCommissions"
        in operation_body
    )
    assert "=> {\n            BrokerOperation::AccountSnapshotRead" in operation_body


def test_stock_etf_readonly_probe_request_source_keeps_validation_matrix() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "self.environment != BrokerEnvironment::ReadOnly" in source
    assert "self.api_action != expected_api_action(self.probe_kind)" in source
    assert "self.operation != expected_operation(self.probe_kind)" in source
    assert "self.authority_scope != AuthorityScope::ReadOnly" in source
    assert "self.effect_capable" in source
    assert "classify_non_bybit_api_action(self.api_action)" in source
    assert "decision.denied" in source
    assert "!decision.allowed_after_external_gate" in source
    assert "!decision.requires_external_surface_gate" in source
    assert "decision.requires_paper_order_gates" in source
    assert "validate_required_fields(self, &mut blockers)" in source
    assert "validate_boundary_flags(self, &mut blockers)" in source


def test_stock_etf_readonly_probe_request_source_keeps_required_field_and_boundary_checks() -> None:
    source = _source()

    assert "request.request_id.trim().is_empty()" in source
    assert "request.probe_id.trim().is_empty()" in source
    assert "request.external_surface_gate_contract_id != IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.phase2_gate_artifact_hash)" in source
    assert "request.api_allowlist_contract_id != NON_BYBIT_API_ALLOWLIST_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.api_allowlist_hash)" in source
    assert "request.secret_slot_contract_id != IBKR_SECRET_SLOT_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.secret_slot_contract_hash)" in source
    assert "request.api_session_topology_contract_id != IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.api_session_topology_hash)" in source
    assert "request.session_attestation_contract_id != IBKR_SESSION_ATTESTATION_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.session_attestation_hash)" in source
    assert "request.redaction_policy_contract_id != IBKR_REDACTION_POLICY_CONTRACT_ID" in source
    assert "request.rate_limit_policy_contract_id != IBKR_RATE_LIMIT_POLICY_CONTRACT_ID" in source
    assert "request.audit_event_policy_contract_id != IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.source_artifact_hash)" in source
    assert "!is_sha256_hex(&request.raw_artifact_hash)" in source
    assert "!is_sha256_hex(&request.redacted_summary_hash)" in source
    for flag in (
        "ibkr_contact_performed",
        "connector_runtime_started",
        "secret_content_serialized",
        "order_routed",
        "paper_order_submitted",
        "db_apply_performed",
        "evidence_clock_started",
        "bybit_path_reused",
        "live_or_tiny_live_authorized",
        "margin_short_options_cfd_requested",
        "account_write_requested",
        "market_data_entitlement_purchase_requested",
        "client_portal_web_api_requested",
        "python_direct_broker_write_requested",
    ):
        assert f"request.{flag}" in source


def test_stock_etf_readonly_probe_request_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{READONLY_PROBE}: contains forbidden token {token!r}")

    assert violations == []
