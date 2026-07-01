from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULT_IMPORT_REQUEST = (
    ROOT
    / "rust/openclaw_types/src/stock_etf_ibkr_readonly_probe_result_import_request.rs"
)
MAX_LINES = 800

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
    source = _source()

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


def test_stock_etf_readonly_probe_result_import_request_source_keeps_action_and_operation_mapping() -> None:
    source = _source()

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


def test_stock_etf_readonly_probe_result_import_request_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{RESULT_IMPORT_REQUEST}: contains forbidden token {token!r}")

    assert violations == []
