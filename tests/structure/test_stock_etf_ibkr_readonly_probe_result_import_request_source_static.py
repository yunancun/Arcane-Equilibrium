import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULT_IMPORT_REQUEST = (
    ROOT
    / "rust/openclaw_types/src/stock_etf_ibkr_readonly_probe_result_import_request.rs"
)
MAX_LINES = 2_000

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID",
    '"stock_etf_ibkr_readonly_probe_result_import_request_v1"',
    "pub struct StockEtfIbkrReadonlyProbeResultImportRequestV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfIbkrReadonlyProbeResultImportVerdict",
    "pub struct StockEtfIbkrReadonlyProbeResultImportVerdict",
    "pub enum StockEtfIbkrReadonlyProbeResultImportBlocker",
    "fn expected_api_action(kind: StockEtfIbkrReadonlyProbeKind) -> NonBybitApiAction",
    "fn expected_operation(kind: StockEtfIbkrReadonlyProbeKind) -> BrokerOperation",
    "fn validate_required_lineage(",
    "fn validate_kind_lineage(",
    "fn validate_boundary_flags(",
    "classify_non_bybit_api_action",
    "STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "NON_BYBIT_API_ALLOWLIST_CONTRACT_ID",
    "IBKR_REDACTION_POLICY_CONTRACT_ID",
    "IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID",
    "BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID",
    "STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID",
    "STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID",
    "BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID",
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
    "result_import_request_id",
    "request_id",
    "probe_id",
    "readonly_probe_request_contract_id",
    "readonly_probe_request_hash",
    "session_attestation_contract_id",
    "session_attestation_hash",
    "api_allowlist_contract_id",
    "api_allowlist_hash",
    "redaction_policy_contract_id",
    "redaction_policy_hash",
    "audit_event_policy_contract_id",
    "audit_event_policy_hash",
    "account_cash_ledger_contract_id",
    "account_cash_ledger_hash",
    "market_data_provenance_contract_id",
    "market_data_provenance_hash",
    "instrument_identity_contract_id",
    "instrument_identity_hash",
    "broker_lifecycle_event_log_contract_id",
    "broker_lifecycle_event_log_hash",
    "health_snapshot_hash",
    "result_payload_hash",
    "raw_artifact_hash",
    "redacted_summary_hash",
    "source_artifact_hash",
    "result_as_of_ms",
    "import_requested_at_ms",
    "idempotency_key",
    "duplicate_import_detected",
    "stale_result_without_manual_review",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "result_import_performed",
    "evidence_writer_started",
    "scorecard_writer_started",
    "db_apply_performed",
    "order_routed",
    "paper_order_submitted",
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
    "EnvironmentDenied",
    "ProbeActionMismatch",
    "OperationMismatch",
    "AuthorityScopeMismatch",
    "EffectCapabilityPresent",
    "ApiActionNotReadAllowed",
    "ResultImportRequestIdMissing",
    "RequestIdMissing",
    "ProbeIdMissing",
    "ReadonlyProbeRequestContractIdMismatch",
    "ReadonlyProbeRequestHashInvalid",
    "SessionAttestationContractIdMismatch",
    "SessionAttestationHashInvalid",
    "ApiAllowlistContractIdMismatch",
    "ApiAllowlistHashInvalid",
    "RedactionPolicyContractIdMismatch",
    "RedactionPolicyHashInvalid",
    "AuditEventPolicyContractIdMismatch",
    "AuditEventPolicyHashInvalid",
    "AccountCashLedgerContractIdMismatch",
    "AccountCashLedgerHashInvalid",
    "MarketDataProvenanceContractIdMismatch",
    "MarketDataProvenanceHashInvalid",
    "InstrumentIdentityContractIdMismatch",
    "InstrumentIdentityHashInvalid",
    "BrokerLifecycleEventLogContractIdMismatch",
    "BrokerLifecycleEventLogHashInvalid",
    "HealthSnapshotHashInvalid",
    "ResultPayloadHashInvalid",
    "RawArtifactHashInvalid",
    "RedactedSummaryHashInvalid",
    "SourceArtifactHashInvalid",
    "ResultAsOfMissing",
    "ImportRequestedAtMissing",
    "ResultAsOfAfterImportRequested",
    "IdempotencyKeyMissing",
    "DuplicateImportDetected",
    "StaleResultWithoutManualReview",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "ResultImportPerformed",
    "EvidenceWriterStarted",
    "ScorecardWriterStarted",
    "DbApplyPerformed",
    "OrderRouted",
    "PaperOrderSubmitted",
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
    return RESULT_IMPORT_REQUEST.read_text(encoding="utf-8")


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
    return source.split(
        "impl Default for StockEtfIbkrReadonlyProbeResultImportRequestV1",
        1,
    )[1].split(
        "impl StockEtfIbkrReadonlyProbeResultImportRequestV1",
        1,
    )[0]


def _accepted_fixture_block(source: str) -> str:
    return source.split(
        "impl StockEtfIbkrReadonlyProbeResultImportRequestV1",
        1,
    )[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


def test_stock_etf_readonly_probe_result_import_request_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_readonly_probe_result_import_request_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_PROBE_KINDS | REQUIRED_FIELDS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_readonly_probe_result_import_request_source_keeps_fail_closed_default() -> None:
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
    assert "duplicate_import_detected: false" in source
    assert "stale_result_without_manual_review: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "secret_content_serialized: false" in source
    assert "result_import_performed: false" in source
    assert "evidence_writer_started: false" in source
    assert "scorecard_writer_started: false" in source
    assert "db_apply_performed: false" in source
    assert "order_routed: false" in source
    assert "paper_order_submitted: false" in source
    assert "bybit_path_reused: false" in source
    assert "live_or_tiny_live_authorized: false" in source
    assert "margin_short_options_cfd_requested: false" in source
    assert "account_write_requested: false" in source
    assert "market_data_entitlement_purchase_requested: false" in source
    assert "client_portal_web_api_requested: false" in source
    assert "python_direct_broker_write_requested: false" in source


def test_stock_etf_readonly_probe_result_import_request_source_keeps_accepted_fixture_boundary() -> None:
    source = _accepted_fixture_block(_source())

    assert (
        "contract_id: STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID"
        in source
    )
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::ReadOnly" in source
    assert "probe_kind: StockEtfIbkrReadonlyProbeKind::ConnectionHealth" in source
    assert "api_action: NonBybitApiAction::ConnectionHealthRead" in source
    assert "operation: BrokerOperation::HealthRead" in source
    assert "authority_scope: AuthorityScope::ReadOnly" in source
    assert "effect_capable: false" in source
    assert (
        'result_import_request_id: "readonly_probe_result_import_request_0001".to_string()'
        in source
    )
    assert 'request_id: "readonly_probe_request_0001".to_string()' in source
    assert 'probe_id: "readonly_probe_0001".to_string()' in source
    assert (
        "readonly_probe_request_contract_id: STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID"
        in source
    )
    assert "session_attestation_contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string()" in source
    assert "api_allowlist_contract_id: NON_BYBIT_API_ALLOWLIST_CONTRACT_ID.to_string()" in source
    assert "redaction_policy_contract_id: IBKR_REDACTION_POLICY_CONTRACT_ID.to_string()" in source
    assert "audit_event_policy_contract_id: IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID.to_string()" in source
    assert 'idempotency_key: "readonly_probe_result_import_idem_0001".to_string()' in source
    assert "..Self::default()" in source


def test_stock_etf_readonly_probe_result_import_fixture_excludes_authority_cross_wire() -> None:
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
        "result_import_request_id: String::new()",
        "request_id: String::new()",
        "probe_id: String::new()",
        "result_as_of_ms: 0",
        "import_requested_at_ms: 0",
        "idempotency_key: String::new()",
        "duplicate_import_detected: false",
        "stale_result_without_manual_review: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "result_import_performed: false",
        "evidence_writer_started: false",
        "scorecard_writer_started: false",
        "db_apply_performed: false",
        "order_routed: false",
        "paper_order_submitted: false",
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
        "api_action: NonBybitApiAction::ClientPortalWebApiUse",
        "api_action: NonBybitApiAction::PaperOrderSubmit",
        "operation: BrokerOperation::TransferOrAccountWrite",
        "operation: BrokerOperation::PaperOrderSubmit",
        "operation: BrokerOperation::LiveOrderSubmit",
        "authority_scope: AuthorityScope::Denied",
        "authority_scope: AuthorityScope::PaperRehearsal",
        "effect_capable: true",
        "result_import_request_id: String::new()",
        "request_id: String::new()",
        "probe_id: String::new()",
        "readonly_probe_request_hash: String::new()",
        "session_attestation_hash: String::new()",
        "api_allowlist_hash: String::new()",
        "redaction_policy_hash: String::new()",
        "audit_event_policy_hash: String::new()",
        "health_snapshot_hash: String::new()",
        "result_payload_hash: String::new()",
        "raw_artifact_hash: String::new()",
        "redacted_summary_hash: String::new()",
        "source_artifact_hash: String::new()",
        "result_as_of_ms: 0",
        "import_requested_at_ms: 0",
        "idempotency_key: String::new()",
        "duplicate_import_detected: true",
        "stale_result_without_manual_review: true",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
        "result_import_performed: true",
        "evidence_writer_started: true",
        "scorecard_writer_started: true",
        "db_apply_performed: true",
        "order_routed: true",
        "paper_order_submitted: true",
        "bybit_path_reused: true",
        "live_or_tiny_live_authorized: true",
        "margin_short_options_cfd_requested: true",
        "account_write_requested: true",
        "market_data_entitlement_purchase_requested: true",
        "client_portal_web_api_requested: true",
        "python_direct_broker_write_requested: true",
    ):
        assert forbidden not in fixture


def test_stock_etf_readonly_probe_result_import_request_source_keeps_action_and_operation_mapping() -> None:
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


def test_stock_etf_readonly_probe_result_import_request_source_keeps_validation_matrix() -> None:
    source = _source()

    assert (
        "self.contract_id != STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID"
        in source
    )
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper" in source
    assert "self.api_action != expected_api_action(self.probe_kind)" in source
    assert "self.operation != expected_operation(self.probe_kind)" in source
    assert "self.authority_scope != AuthorityScope::ReadOnly" in source
    assert "self.effect_capable" in source
    assert "classify_non_bybit_api_action(self.api_action)" in source
    assert "decision.denied" in source
    assert "!decision.allowed_after_external_gate" in source
    assert "!decision.requires_external_surface_gate" in source
    assert "decision.requires_paper_order_gates" in source
    assert "validate_required_lineage(self, &mut blockers)" in source
    assert "validate_kind_lineage(self, &mut blockers)" in source
    assert "validate_boundary_flags(self, &mut blockers)" in source


def test_stock_etf_readonly_probe_result_import_request_source_keeps_lineage_checks() -> None:
    source = _source()

    assert "request.result_import_request_id.trim().is_empty()" in source
    assert "request.request_id.trim().is_empty()" in source
    assert "request.probe_id.trim().is_empty()" in source
    assert (
        "request.readonly_probe_request_contract_id\n        != STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID"
        in source
    )
    assert "!is_sha256_hex(&request.readonly_probe_request_hash)" in source
    assert "request.session_attestation_contract_id != IBKR_SESSION_ATTESTATION_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.session_attestation_hash)" in source
    assert "request.api_allowlist_contract_id != NON_BYBIT_API_ALLOWLIST_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.api_allowlist_hash)" in source
    assert "request.redaction_policy_contract_id != IBKR_REDACTION_POLICY_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.redaction_policy_hash)" in source
    assert "request.audit_event_policy_contract_id != IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.audit_event_policy_hash)" in source
    assert "!is_sha256_hex(&request.result_payload_hash)" in source
    assert "!is_sha256_hex(&request.raw_artifact_hash)" in source
    assert "!is_sha256_hex(&request.redacted_summary_hash)" in source
    assert "!is_sha256_hex(&request.source_artifact_hash)" in source
    assert "request.result_as_of_ms == 0" in source
    assert "request.import_requested_at_ms == 0" in source
    assert "request.result_as_of_ms > request.import_requested_at_ms" in source
    assert "request.idempotency_key.trim().is_empty()" in source
    assert "request.duplicate_import_detected" in source
    assert "request.stale_result_without_manual_review" in source


def test_stock_etf_readonly_probe_result_import_request_source_keeps_kind_lineage_checks() -> None:
    source = _source()

    assert "!is_sha256_hex(&request.health_snapshot_hash)" in source
    assert (
        "request.account_cash_ledger_contract_id\n                != BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID"
        in source
    )
    assert "!is_sha256_hex(&request.account_cash_ledger_hash)" in source
    assert (
        "request.instrument_identity_contract_id != STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID"
        in source
    )
    assert "!is_sha256_hex(&request.instrument_identity_hash)" in source
    assert (
        "request.market_data_provenance_contract_id\n                != STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID"
        in source
    )
    assert "!is_sha256_hex(&request.market_data_provenance_hash)" in source
    assert (
        "request.broker_lifecycle_event_log_contract_id\n                != BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID"
        in source
    )
    assert "!is_sha256_hex(&request.broker_lifecycle_event_log_hash)" in source


def test_stock_etf_readonly_probe_result_import_request_source_keeps_boundary_flags() -> None:
    source = _source()

    for flag in (
        "ibkr_contact_performed",
        "connector_runtime_started",
        "secret_content_serialized",
        "result_import_performed",
        "evidence_writer_started",
        "scorecard_writer_started",
        "db_apply_performed",
        "order_routed",
        "paper_order_submitted",
        "bybit_path_reused",
        "live_or_tiny_live_authorized",
        "margin_short_options_cfd_requested",
        "account_write_requested",
        "market_data_entitlement_purchase_requested",
        "client_portal_web_api_requested",
        "python_direct_broker_write_requested",
    ):
        assert f"request.{flag}" in source


def test_stock_etf_readonly_probe_result_import_request_source_pins_blocker_emit_order() -> None:
    source = _source()
    validate_body = source[source.index("pub fn validate(&self)") : source.index(
        "validate_required_lineage(self, &mut blockers)"
    )]
    required_lineage = _named_function_body(source, "validate_required_lineage")
    kind_lineage = _named_function_body(source, "validate_kind_lineage")
    boundary_flags = _named_function_body(source, "validate_boundary_flags")

    _assert_ordered_tokens(
        validate_body,
        (
            "Blocker::ContractIdMismatch",
            "Blocker::SourceVersionMismatch",
            "Blocker::WrongAssetLane",
            "Blocker::WrongBroker",
            "Blocker::EnvironmentDenied",
            "Blocker::ProbeActionMismatch",
            "Blocker::OperationMismatch",
            "Blocker::AuthorityScopeMismatch",
            "Blocker::EffectCapabilityPresent",
            "Blocker::ApiActionNotReadAllowed",
        ),
    )
    _assert_ordered_tokens(
        required_lineage,
        (
            "Blocker::ResultImportRequestIdMissing",
            "Blocker::RequestIdMissing",
            "Blocker::ProbeIdMissing",
            "Blocker::ReadonlyProbeRequestContractIdMismatch",
            "Blocker::ReadonlyProbeRequestHashInvalid",
            "Blocker::SessionAttestationContractIdMismatch",
            "Blocker::SessionAttestationHashInvalid",
            "Blocker::ApiAllowlistContractIdMismatch",
            "Blocker::ApiAllowlistHashInvalid",
            "Blocker::RedactionPolicyContractIdMismatch",
            "Blocker::RedactionPolicyHashInvalid",
            "Blocker::AuditEventPolicyContractIdMismatch",
            "Blocker::AuditEventPolicyHashInvalid",
            "Blocker::ResultPayloadHashInvalid",
            "Blocker::RawArtifactHashInvalid",
            "Blocker::RedactedSummaryHashInvalid",
            "Blocker::SourceArtifactHashInvalid",
            "Blocker::ResultAsOfMissing",
            "Blocker::ImportRequestedAtMissing",
            "Blocker::ResultAsOfAfterImportRequested",
            "Blocker::IdempotencyKeyMissing",
            "Blocker::DuplicateImportDetected",
            "Blocker::StaleResultWithoutManualReview",
        ),
    )
    _assert_ordered_tokens(
        kind_lineage,
        (
            "Blocker::HealthSnapshotHashInvalid",
            "Blocker::AccountCashLedgerContractIdMismatch",
            "Blocker::AccountCashLedgerHashInvalid",
            "Blocker::InstrumentIdentityContractIdMismatch",
            "Blocker::InstrumentIdentityHashInvalid",
            "Blocker::MarketDataProvenanceContractIdMismatch",
            "Blocker::MarketDataProvenanceHashInvalid",
            "Blocker::BrokerLifecycleEventLogContractIdMismatch",
            "Blocker::BrokerLifecycleEventLogHashInvalid",
        ),
    )
    _assert_ordered_tokens(
        boundary_flags,
        (
            "Blocker::IbkrContactPerformed",
            "Blocker::ConnectorRuntimeStarted",
            "Blocker::SecretContentSerialized",
            "Blocker::ResultImportPerformed",
            "Blocker::EvidenceWriterStarted",
            "Blocker::ScorecardWriterStarted",
            "Blocker::DbApplyPerformed",
            "Blocker::OrderRouted",
            "Blocker::PaperOrderSubmitted",
            "Blocker::BybitPathReused",
            "Blocker::LiveOrTinyLiveAuthorized",
            "Blocker::MarginShortOptionsCfdRequested",
            "Blocker::AccountWriteRequested",
            "Blocker::MarketDataEntitlementPurchaseRequested",
            "Blocker::ClientPortalWebApiRequested",
            "Blocker::PythonDirectBrokerWriteRequested",
        ),
    )


def test_stock_etf_readonly_probe_result_import_request_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{RESULT_IMPORT_REQUEST}: contains forbidden token {token!r}")

    assert violations == []
