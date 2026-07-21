from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAPER_LIFECYCLE = ROOT / "rust/openclaw_types/src/ibkr_paper_lifecycle.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_TYPE_TOKENS = {
    'IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID: &str = "ibkr_paper_order_lifecycle_v1"',
    'BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID: &str = "broker_lifecycle_event_log_v1"',
    "pub struct BrokerLifecycleEventLogV1",
    "impl Default for BrokerLifecycleEventLogV1",
    "impl BrokerLifecycleEventLogV1",
    "pub fn accepted_ack_fixture() -> Self",
    "pub fn validate(&self) -> IbkrPaperLifecycleEventVerdict",
    "pub struct IbkrPaperLifecycleEventVerdict",
    "pub enum IbkrPaperLifecycleEventBlocker",
    "pub enum IbkrPaperStaleStatePolicy",
    "pub struct IbkrPaperRestartRecoveryInputV1",
    "impl Default for IbkrPaperRestartRecoveryInputV1",
    "pub enum IbkrPaperRestartRecoveryAction",
    "pub fn classify_ibkr_paper_restart_recovery(",
    "pub const fn is_transition_allowed(",
    "pub const fn is_operation_transition_allowed(",
    "const fn stale_state_policy_matches_transition(",
    "const fn is_paper_lifecycle_operation(",
    "const fn requires_broker_order_id(",
    "const fn requires_fill_ids(",
}
REQUIRED_EVENT_FIELDS = {
    "lifecycle_contract_id",
    "event_log_contract_id",
    "source_version",
    "event_id",
    "event_sequence",
    "genesis_event",
    "event_time_ms",
    "previous_event_hash",
    "event_hash",
    "request_contract_id",
    "request_envelope_hash",
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "order_local_id",
    "idempotency_key",
    "broker_order_id",
    "execution_id",
    "commission_report_id",
    "reconciliation_run_id",
    "previous_state",
    "next_state",
    "allowed",
    "denial_reason",
    "stale_state_policy",
    "raw_artifact_hash",
    "redacted_summary_hash",
}
REQUIRED_BLOCKERS = {
    "LifecycleContractIdMismatch",
    "EventLogContractIdMismatch",
    "SourceVersionMismatch",
    "EventIdMissing",
    "EventSequenceMissing",
    "GenesisSequenceInvalid",
    "GenesisPreviousEventHashPresent",
    "PreviousEventHashInvalid",
    "EventTimeMissing",
    "EventHashInvalid",
    "RequestContractIdMismatch",
    "RequestEnvelopeHashInvalid",
    "WrongAssetLane",
    "WrongBroker",
    "PaperEnvironmentRequired",
    "LiveEnvironmentDenied",
    "OperationNotPaperLifecycle",
    "OperationTransitionMismatch",
    "LocalOrderIdMissing",
    "IdempotencyKeyMissing",
    "ReconciliationRunIdMissing",
    "BrokerOrderIdMissing",
    "ExecutionIdMissing",
    "CommissionReportIdMissing",
    "InvalidStateTransition",
    "StateUnknownRecoveryInvalid",
    "StateUnknownTerminalEvidenceMissing",
    "DenialReasonPresentOnAllowedEvent",
    "DenialReasonMissingOnDeniedEvent",
    "DeniedEventAdvancesActiveState",
    "StaleStatePolicyMissing",
    "StaleStatePolicyMismatch",
    "RawArtifactHashInvalid",
    "RedactedSummaryHashInvalid",
}
REQUIRED_STATES = {
    "LocalIntentCreated",
    "RustAuthorityAccepted",
    "BrokerSubmitRequested",
    "BrokerAcknowledged",
    "PartiallyFilled",
    "Filled",
    "CancelRequested",
    "Cancelled",
    "ReplaceRequested",
    "Replaced",
    "Rejected",
    "Inactive",
    "ManualReviewRequired",
    "StateUnknown",
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
    return PAPER_LIFECYCLE.read_text(encoding="utf-8")


def _event_default_block(source: str) -> str:
    return source.split("impl Default for BrokerLifecycleEventLogV1", 1)[1].split(
        "impl BrokerLifecycleEventLogV1",
        1,
    )[0]


def _accepted_ack_fixture_block(source: str) -> str:
    return source.split("impl BrokerLifecycleEventLogV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


def test_ibkr_paper_lifecycle_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_paper_lifecycle_source_keeps_contract_event_log_surface() -> None:
    source = _source()
    default_block = _event_default_block(source)

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_EVENT_FIELDS:
        assert field in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source
    for state in REQUIRED_STATES:
        assert f"State::{state}" in source or f"IbkrPaperOrderLifecycleState::{state}" in source

    assert "lifecycle_contract_id: String::new()" in default_block
    assert "event_log_contract_id: String::new()" in default_block
    assert "source_version: 0" in default_block
    assert "event_sequence: 0" in default_block
    assert "event_time_ms: 0" in default_block
    assert "request_contract_id: String::new()" in default_block
    assert "asset_lane: AssetLane::StockEtfCash" in default_block
    assert "broker: Broker::Ibkr" in default_block
    assert "environment: BrokerEnvironment::Paper" in default_block
    assert "operation: BrokerOperation::PaperOrderSubmit" in default_block
    assert "allowed: false" in default_block
    assert "stale_state_policy: None" in default_block
    assert "accepted: blockers.is_empty()" in source


def test_ibkr_paper_lifecycle_accepted_ack_fixture_excludes_cross_wire_defaults() -> None:
    source = _source()
    fixture = _accepted_ack_fixture_block(source)

    for required in (
        "lifecycle_contract_id: IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID.to_string()",
        "event_log_contract_id: BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID.to_string()",
        "source_version: 1",
        'event_id: "lifecycle_event_0001".to_string()',
        "event_sequence: 2",
        "genesis_event: false",
        "event_time_ms: 1_772_233_000_000",
        'request_contract_id: STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID.to_string()',
        "operation: BrokerOperation::PaperOrderSubmit",
        'order_local_id: "local_order_0001".to_string()',
        'idempotency_key: "idem_0001".to_string()',
        'broker_order_id: "paper_broker_order_0001".to_string()',
        'reconciliation_run_id: "reconcile_run_0001".to_string()',
        "previous_state: IbkrPaperOrderLifecycleState::BrokerSubmitRequested",
        "next_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged",
        "allowed: true",
        "IbkrPaperStaleStatePolicy::ReconcileByBrokerOrderIdAndIdempotencyKey",
        "raw_artifact_hash: \"a\".repeat(64)",
        "redacted_summary_hash: \"b\".repeat(64)",
        "..Self::default()",
    ):
        assert required in fixture

    for forbidden in (
        "lifecycle_contract_id: String::new()",
        "event_log_contract_id: String::new()",
        "source_version: 0",
        "event_sequence: 0",
        "genesis_event: true",
        "event_time_ms: 0",
        "previous_event_hash: String::new()",
        "event_hash: String::new()",
        "request_contract_id: String::new()",
        "request_envelope_hash: String::new()",
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "environment: BrokerEnvironment::LiveReservedDenied",
        "operation: BrokerOperation::LiveOrderSubmit",
        "operation: BrokerOperation::TransferOrAccountWrite",
        "order_local_id: String::new()",
        "idempotency_key: String::new()",
        "broker_order_id: String::new()",
        "reconciliation_run_id: String::new()",
        "allowed: false",
        "denial_reason: Some(",
        "stale_state_policy: None",
        "IbkrPaperStaleStatePolicy::PreserveTerminalWithEvidence",
        "raw_artifact_hash: String::new()",
        "redacted_summary_hash: String::new()",
    ):
        assert forbidden not in fixture


def test_ibkr_paper_lifecycle_source_keeps_append_only_lineage_validation() -> None:
    source = _source()

    assert "self.lifecycle_contract_id != IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID" in source
    assert "self.event_log_contract_id != BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID" in source
    assert "self.event_id.trim().is_empty()" in source
    assert "self.event_sequence == 0" in source
    assert "if self.genesis_event" in source
    assert "self.event_sequence != 1" in source
    assert "!self.previous_event_hash.trim().is_empty()" in source
    assert "!is_sha256_hex(&self.previous_event_hash)" in source
    assert "self.event_time_ms == 0" in source
    assert "!is_sha256_hex(&self.event_hash)" in source
    assert "self.request_contract_id != STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID" in source
    assert "!is_sha256_hex(&self.request_envelope_hash)" in source
    assert "self.environment == BrokerEnvironment::LiveReservedDenied" in source
    assert "self.environment != BrokerEnvironment::Paper" in source
    assert "!is_paper_lifecycle_operation(self.operation)" in source
    assert "!is_operation_transition_allowed(self.operation, self.previous_state, self.next_state)" in source
    assert "!is_transition_allowed(self.previous_state, self.next_state)" in source
    assert "!is_sha256_hex(&self.raw_artifact_hash)" in source
    assert "!is_sha256_hex(&self.redacted_summary_hash)" in source


def test_ibkr_paper_lifecycle_source_keeps_state_and_recovery_rules() -> None:
    source = _source()

    assert "requires_broker_order_id(self.previous_state, self.next_state)" in source
    assert "requires_fill_ids(self.next_state)" in source
    assert "self.previous_state == IbkrPaperOrderLifecycleState::StateUnknown" in source
    assert "self.next_state != IbkrPaperOrderLifecycleState::ManualReviewRequired" in source
    assert "!self.next_state.is_terminal()" in source
    assert "self.next_state.is_terminal()" in source
    assert "self.allowed && self.denial_reason.is_some()" in source
    assert "!self.allowed && self.denial_reason.is_none()" in source
    assert "DeniedEventAdvancesActiveState" in source
    assert "stale_state_policy_matches_transition(" in source
    assert "Policy::ManualReviewOnUnknown" in source
    assert "Policy::ReconcileByBrokerOrderIdAndIdempotencyKey" in source
    assert "Policy::PreserveTerminalWithEvidence" in source
    assert "input.last_local_state.is_terminal() && is_sha256_hex(&input.terminal_evidence_hash)" in source
    assert "input.broker_state_known" in source
    assert "!input.broker_order_id.trim().is_empty()" in source
    assert "!input.idempotency_key.trim().is_empty()" in source
    assert "IbkrPaperRestartRecoveryAction::PreserveTerminalState" in source
    assert "IbkrPaperRestartRecoveryAction::ReconcileByBrokerOrderIdAndIdempotencyKey" in source
    assert "IbkrPaperRestartRecoveryAction::MarkStateUnknown" in source


def test_ibkr_paper_lifecycle_source_keeps_operation_transition_matrix() -> None:
    source = _source()

    assert "Op::PaperOrderSubmit" in source
    assert "Op::PaperOrderCancel" in source
    assert "Op::PaperOrderReplace" in source
    assert "Op::PaperOrderFillImport" in source
    assert "State::LocalIntentCreated" in source
    assert "State::RustAuthorityAccepted" in source
    assert "State::BrokerSubmitRequested" in source
    assert "State::BrokerAcknowledged" in source
    assert "State::PartiallyFilled" in source
    assert "State::CancelRequested" in source
    assert "State::ReplaceRequested" in source
    assert "State::Replaced" in source
    assert "State::StateUnknown" in source
    assert "_ => false" in source
    assert "BrokerOperation::PaperOrderSubmit" in source
    assert "BrokerOperation::PaperOrderCancel" in source
    assert "BrokerOperation::PaperOrderReplace" in source
    assert "BrokerOperation::PaperOrderFillImport" in source


def test_ibkr_paper_lifecycle_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PAPER_LIFECYCLE}: contains forbidden token {token!r}")

    assert violations == []
