import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READONLY_PROBE = ROOT / "rust/openclaw_types/src/stock_etf_ibkr_readonly_probe_request.rs"
MAX_LINES = 2_000

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


def _named_function_body(source: str, name: str) -> str:
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


def _assert_ordered_tokens(block: str, tokens: tuple[str, ...]) -> None:
    positions = [block.index(token) for token in tokens]
    assert positions == sorted(positions)


def _default_block(source: str) -> str:
    return source.split("impl Default for StockEtfIbkrReadonlyProbeRequestV1", 1)[1].split(
        "impl StockEtfIbkrReadonlyProbeRequestV1",
        1,
    )[0]


def _accepted_fixture_block(source: str) -> str:
    return source.split("impl StockEtfIbkrReadonlyProbeRequestV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


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
    source = _default_block(_source())

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
    source = _accepted_fixture_block(_source())

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


def test_stock_etf_readonly_probe_request_fixture_excludes_authority_cross_wire() -> None:
    source = _source()
    default_block = _default_block(source)
    fixture = _accepted_fixture_block(source)

    for required_default in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "environment: BrokerEnvironment::LiveReservedDenied",
        "api_action: NonBybitApiAction::ClientPortalWebApiUse",
        "operation: BrokerOperation::TransferOrAccountWrite",
        "authority_scope: AuthorityScope::Denied",
        "request_id: String::new()",
        "probe_id: String::new()",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "order_routed: false",
        "paper_order_submitted: false",
        "db_apply_performed: false",
        "evidence_clock_started: false",
        "bybit_path_reused: false",
        "live_or_tiny_live_authorized: false",
        "margin_short_options_cfd_requested: false",
        "account_write_requested: false",
        "market_data_entitlement_purchase_requested: false",
        "client_portal_web_api_requested: false",
        "python_direct_broker_write_requested: false",
    ):
        assert required_default in default_block

    for forbidden in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "environment: BrokerEnvironment::LiveReservedDenied",
        "environment: BrokerEnvironment::Paper",
        "api_action: NonBybitApiAction::ClientPortalWebApiUse",
        "api_action: NonBybitApiAction::PaperOrderSubmit",
        "operation: BrokerOperation::TransferOrAccountWrite",
        "operation: BrokerOperation::PaperOrderSubmit",
        "operation: BrokerOperation::LiveOrderSubmit",
        "authority_scope: AuthorityScope::Denied",
        "authority_scope: AuthorityScope::PaperRehearsal",
        "effect_capable: true",
        "request_id: String::new()",
        "probe_id: String::new()",
        "phase2_gate_artifact_hash: String::new()",
        "api_allowlist_hash: String::new()",
        "secret_slot_contract_hash: String::new()",
        "api_session_topology_hash: String::new()",
        "session_attestation_hash: String::new()",
        "redaction_policy_hash: String::new()",
        "rate_limit_policy_hash: String::new()",
        "audit_event_policy_hash: String::new()",
        "source_artifact_hash: String::new()",
        "raw_artifact_hash: String::new()",
        "redacted_summary_hash: String::new()",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
        "order_routed: true",
        "paper_order_submitted: true",
        "db_apply_performed: true",
        "evidence_clock_started: true",
        "bybit_path_reused: true",
        "live_or_tiny_live_authorized: true",
        "margin_short_options_cfd_requested: true",
        "account_write_requested: true",
        "market_data_entitlement_purchase_requested: true",
        "client_portal_web_api_requested: true",
        "python_direct_broker_write_requested: true",
    ):
        assert forbidden not in fixture


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


def test_stock_etf_readonly_probe_request_source_pins_blocker_emit_order() -> None:
    source = _source()
    validate_body = source[source.index("pub fn validate(&self)") : source.index(
        "validate_required_fields(self, &mut blockers)"
    )]
    required_fields = _named_function_body(source, "validate_required_fields")
    boundary_flags = _named_function_body(source, "validate_boundary_flags")

    _assert_ordered_tokens(
        validate_body,
        (
            "Blocker::ContractIdMismatch",
            "Blocker::SourceVersionMismatch",
            "Blocker::WrongAssetLane",
            "Blocker::WrongBroker",
            "Blocker::EnvironmentNotReadonly",
            "Blocker::ProbeActionMismatch",
            "Blocker::OperationMismatch",
            "Blocker::AuthorityScopeMismatch",
            "Blocker::EffectCapabilityPresent",
            "Blocker::ApiActionNotReadAllowed",
        ),
    )
    _assert_ordered_tokens(
        required_fields,
        (
            "Blocker::RequestIdMissing",
            "Blocker::ProbeIdMissing",
            "Blocker::ExternalSurfaceGateContractIdMismatch",
            "Blocker::Phase2GateArtifactHashInvalid",
            "Blocker::ApiAllowlistContractIdMismatch",
            "Blocker::ApiAllowlistHashInvalid",
            "Blocker::SecretSlotContractIdMismatch",
            "Blocker::SecretSlotContractHashInvalid",
            "Blocker::ApiSessionTopologyContractIdMismatch",
            "Blocker::ApiSessionTopologyHashInvalid",
            "Blocker::SessionAttestationContractIdMismatch",
            "Blocker::SessionAttestationHashInvalid",
            "Blocker::RedactionPolicyContractIdMismatch",
            "Blocker::RedactionPolicyHashInvalid",
            "Blocker::RateLimitPolicyContractIdMismatch",
            "Blocker::RateLimitPolicyHashInvalid",
            "Blocker::AuditEventPolicyContractIdMismatch",
            "Blocker::AuditEventPolicyHashInvalid",
            "Blocker::SourceArtifactHashInvalid",
            "Blocker::RawArtifactHashInvalid",
            "Blocker::RedactedSummaryHashInvalid",
        ),
    )
    _assert_ordered_tokens(
        boundary_flags,
        (
            "Blocker::IbkrContactPerformed",
            "Blocker::ConnectorRuntimeStarted",
            "Blocker::SecretContentSerialized",
            "Blocker::OrderRouted",
            "Blocker::PaperOrderSubmitted",
            "Blocker::DbApplyPerformed",
            "Blocker::EvidenceClockStarted",
            "Blocker::BybitPathReused",
            "Blocker::LiveOrTinyLiveAuthorized",
            "Blocker::MarginShortOptionsCfdRequested",
            "Blocker::AccountWriteRequested",
            "Blocker::MarketDataEntitlementPurchaseRequested",
            "Blocker::ClientPortalWebApiRequested",
            "Blocker::PythonDirectBrokerWriteRequested",
        ),
    )


def test_stock_etf_readonly_probe_request_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{READONLY_PROBE}: contains forbidden token {token!r}")

    assert violations == []
