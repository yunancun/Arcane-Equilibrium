from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAPER_FILL_IMPORT = ROOT / "rust/openclaw_types/src/stock_etf_paper_fill_import_request.rs"
MAX_LINES = 800

REQUIRED_IMPORT_TOKENS = {
    "IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID",
    "BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID",
    "IBKR_REDACTION_POLICY_CONTRACT_ID",
    "StockEtfLaneScopedIpcMethod",
    "IbkrPaperOrderLifecycleState",
    "IbkrPaperStaleStatePolicy",
}
REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID",
    '"stock_etf_paper_fill_import_request_v1"',
    "pub struct StockEtfPaperFillImportRequestV1",
    "impl Default for StockEtfPaperFillImportRequestV1",
    "impl StockEtfPaperFillImportRequestV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfPaperFillImportVerdict",
    "pub struct StockEtfPaperFillImportVerdict",
    "pub enum StockEtfPaperFillImportBlocker",
    "fn validate_required_fields(",
    "fn validate_boundary_flags(",
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
    "session_attestation_hash",
    "lifecycle_contract_id",
    "lifecycle_contract_hash",
    "event_log_contract_id",
    "event_log_contract_hash",
    "redaction_policy_contract_id",
    "redaction_policy_hash",
    "source_artifact_hash",
    "reconciliation_run_id",
    "broker_order_id",
    "execution_id",
    "commission_report_id",
    "import_idempotency_key",
    "observed_order_state",
    "stale_state_policy",
    "raw_artifact_hash",
    "redacted_summary_hash",
    "duplicate_import_detected",
    "stale_unknown_state_without_policy",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "fill_import_performed",
    "db_apply_performed",
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
    "RequestMethodMismatch",
    "OperationMismatch",
    "AuthorityScopeMismatch",
    "EffectCapabilityPresent",
    "RequestIdMissing",
    "SessionAttestationHashInvalid",
    "LifecycleContractIdMismatch",
    "LifecycleContractHashInvalid",
    "EventLogContractIdMismatch",
    "EventLogContractHashInvalid",
    "RedactionPolicyContractIdMismatch",
    "RedactionPolicyHashInvalid",
    "SourceArtifactHashInvalid",
    "ReconciliationRunIdMissing",
    "BrokerOrderIdMissing",
    "ExecutionIdMissing",
    "CommissionReportIdMissing",
    "ImportIdempotencyKeyMissing",
    "ObservedOrderStateMissing",
    "StaleStatePolicyMissing",
    "RawArtifactHashInvalid",
    "RedactedSummaryHashInvalid",
    "DuplicateImportDetected",
    "StaleUnknownStateWithoutPolicy",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "FillImportPerformed",
    "DbApplyPerformed",
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


def _source() -> str:
    return PAPER_FILL_IMPORT.read_text(encoding="utf-8")


def _default_block(source: str) -> str:
    return source.split("impl Default for StockEtfPaperFillImportRequestV1", 1)[1].split(
        "impl StockEtfPaperFillImportRequestV1",
        1,
    )[0]


def _accepted_fixture_block(source: str) -> str:
    return source.split("impl StockEtfPaperFillImportRequestV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


def test_stock_etf_paper_fill_import_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_paper_fill_import_source_keeps_contract_surface() -> None:
    source = _source()
    default_block = _default_block(source)

    for token in REQUIRED_IMPORT_TOKENS | REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_FIELDS:
        assert field in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "contract_id: String::new()" in default_block
    assert "source_version: 0" in default_block
    assert "asset_lane: AssetLane::CryptoPerp" in default_block
    assert "broker: Broker::Bybit" in default_block
    assert "environment: BrokerEnvironment::LiveReservedDenied" in default_block
    assert "request_method: StockEtfLaneScopedIpcMethod::UnknownDenied" in default_block
    assert "operation: BrokerOperation::TransferOrAccountWrite" in default_block
    assert "authority_scope: AuthorityScope::Denied" in default_block
    assert "effect_capable: false" in default_block
    assert "observed_order_state: None" in default_block
    assert "stale_state_policy: None" in default_block
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_paper_fill_import_source_keeps_accepted_readonly_shape() -> None:
    source = _accepted_fixture_block(_source())

    assert "contract_id: STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "request_method: StockEtfLaneScopedIpcMethod::ImportPaperFills" in source
    assert "operation: BrokerOperation::PaperOrderFillImport" in source
    assert "authority_scope: AuthorityScope::ReadOnly" in source
    assert "effect_capable: false" in source
    assert "lifecycle_contract_id: IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID.to_string()" in source
    assert "event_log_contract_id: BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID.to_string()" in source
    assert "redaction_policy_contract_id: IBKR_REDACTION_POLICY_CONTRACT_ID.to_string()" in source
    assert "observed_order_state: Some(IbkrPaperOrderLifecycleState::Filled)" in source
    assert "stale_state_policy: Some(IbkrPaperStaleStatePolicy::PreserveTerminalWithEvidence)" in source
    assert "..Self::default()" in source


def test_stock_etf_paper_fill_import_fixture_excludes_authority_lineage_and_runtime_crosswire() -> None:
    source = _source()
    default_block = _default_block(source)
    fixture = _accepted_fixture_block(source)

    for required_default in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "environment: BrokerEnvironment::LiveReservedDenied",
        "request_method: StockEtfLaneScopedIpcMethod::UnknownDenied",
        "operation: BrokerOperation::TransferOrAccountWrite",
        "authority_scope: AuthorityScope::Denied",
        "request_id: String::new()",
        "session_attestation_hash: String::new()",
        "lifecycle_contract_id: String::new()",
        "event_log_contract_id: String::new()",
        "redaction_policy_contract_id: String::new()",
        "reconciliation_run_id: String::new()",
        "broker_order_id: String::new()",
        "execution_id: String::new()",
        "commission_report_id: String::new()",
        "import_idempotency_key: String::new()",
        "observed_order_state: None",
        "stale_state_policy: None",
        "duplicate_import_detected: false",
        "stale_unknown_state_without_policy: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "fill_import_performed: false",
        "db_apply_performed: false",
        "order_routed: false",
        "bybit_path_reused: false",
        "live_or_tiny_live_authorized: false",
        "margin_short_options_cfd_requested: false",
        "python_direct_broker_write_requested: false",
    ):
        assert required_default in default_block

    for forbidden in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "environment: BrokerEnvironment::LiveReservedDenied",
        "request_method: StockEtfLaneScopedIpcMethod::UnknownDenied",
        "request_method: StockEtfLaneScopedIpcMethod::SubmitPaperOrder",
        "request_method: StockEtfLaneScopedIpcMethod::EvaluateShadowSignal",
        "operation: BrokerOperation::TransferOrAccountWrite",
        "operation: BrokerOperation::PaperOrderSubmit",
        "operation: BrokerOperation::ShadowSignalEmit",
        "authority_scope: AuthorityScope::Denied",
        "authority_scope: AuthorityScope::PaperRehearsal",
        "authority_scope: AuthorityScope::ShadowOnly",
        "effect_capable: true",
        "request_id: String::new()",
        "session_attestation_hash: String::new()",
        "lifecycle_contract_hash: String::new()",
        "event_log_contract_hash: String::new()",
        "redaction_policy_hash: String::new()",
        "source_artifact_hash: String::new()",
        "reconciliation_run_id: String::new()",
        "broker_order_id: String::new()",
        "execution_id: String::new()",
        "commission_report_id: String::new()",
        "import_idempotency_key: String::new()",
        "observed_order_state: None",
        "stale_state_policy: None",
        "raw_artifact_hash: String::new()",
        "redacted_summary_hash: String::new()",
        "duplicate_import_detected: true",
        "stale_unknown_state_without_policy: true",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
        "fill_import_performed: true",
        "db_apply_performed: true",
        "order_routed: true",
        "bybit_path_reused: true",
        "live_or_tiny_live_authorized: true",
        "margin_short_options_cfd_requested: true",
        "python_direct_broker_write_requested: true",
    ):
        assert forbidden not in fixture


def test_stock_etf_paper_fill_import_source_excludes_paper_shadow_readonly_and_live_crosswire() -> None:
    source = _source()

    for forbidden_method in (
        "StockEtfLaneScopedIpcMethod::PreviewPaperOrder",
        "StockEtfLaneScopedIpcMethod::SubmitPaperOrder",
        "StockEtfLaneScopedIpcMethod::CancelPaperOrder",
        "StockEtfLaneScopedIpcMethod::ReplacePaperOrder",
        "StockEtfLaneScopedIpcMethod::EvaluateShadowSignal",
        "StockEtfLaneScopedIpcMethod::PreviewReadonlyProbe",
        "StockEtfLaneScopedIpcMethod::BybitSubmitPaperOrderDenied",
    ):
        assert forbidden_method not in source

    for forbidden_operation in (
        "BrokerOperation::PaperOrderSubmit",
        "BrokerOperation::PaperOrderCancel",
        "BrokerOperation::PaperOrderReplace",
        "BrokerOperation::ShadowSignalEmit",
        "BrokerOperation::LiveOrderSubmit",
    ):
        assert forbidden_operation not in source

    assert "AuthorityScope::PaperRehearsal" not in source
    assert "AuthorityScope::ShadowOnly" not in source
    assert "effect_capable: true" not in source


def test_stock_etf_paper_fill_import_source_keeps_lineage_and_replay_validation() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "self.environment != BrokerEnvironment::Paper" in source
    assert "self.request_method != StockEtfLaneScopedIpcMethod::ImportPaperFills" in source
    assert "self.operation != BrokerOperation::PaperOrderFillImport" in source
    assert "self.authority_scope != AuthorityScope::ReadOnly" in source
    assert "self.effect_capable" in source
    assert "request.request_id.trim().is_empty()" in source
    assert "!is_sha256_hex(&request.session_attestation_hash)" in source
    assert "request.lifecycle_contract_id != IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.lifecycle_contract_hash)" in source
    assert "request.event_log_contract_id != BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.event_log_contract_hash)" in source
    assert "request.redaction_policy_contract_id != IBKR_REDACTION_POLICY_CONTRACT_ID" in source
    assert "!is_sha256_hex(&request.redaction_policy_hash)" in source
    assert "!is_sha256_hex(&request.source_artifact_hash)" in source
    assert "request.reconciliation_run_id.trim().is_empty()" in source
    assert "request.broker_order_id.trim().is_empty()" in source
    assert "request.execution_id.trim().is_empty()" in source
    assert "request.commission_report_id.trim().is_empty()" in source
    assert "request.import_idempotency_key.trim().is_empty()" in source
    assert "request.observed_order_state.is_none()" in source
    assert "request.stale_state_policy.is_none()" in source
    assert "!is_sha256_hex(&request.raw_artifact_hash)" in source
    assert "!is_sha256_hex(&request.redacted_summary_hash)" in source
    assert "request.duplicate_import_detected" in source
    assert "request.stale_unknown_state_without_policy" in source
    assert "Some(IbkrPaperOrderLifecycleState::StateUnknown)" in source


def test_stock_etf_paper_fill_import_source_keeps_no_side_effect_boundary_flags() -> None:
    source = _source()

    assert "if request.ibkr_contact_performed" in source
    assert "if request.connector_runtime_started" in source
    assert "if request.secret_content_serialized" in source
    assert "if request.fill_import_performed" in source
    assert "if request.db_apply_performed" in source
    assert "if request.order_routed" in source
    assert "if request.bybit_path_reused" in source
    assert "if request.live_or_tiny_live_authorized" in source
    assert "if request.margin_short_options_cfd_requested" in source
    assert "if request.python_direct_broker_write_requested" in source


def test_stock_etf_paper_fill_import_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PAPER_FILL_IMPORT}: contains forbidden token {token!r}")

    assert violations == []
