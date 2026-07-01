from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT_EVENTS = ROOT / "rust/openclaw_types/src/stock_etf_audit_events.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID",
    '"audit.asset_lane_events_v1"',
    "pub enum StockEtfAssetLaneEventKind",
    "pub struct StockEtfAssetLaneEventV1",
    "pub struct StockEtfAssetLaneEventVerdict",
    "pub enum StockEtfAssetLaneEventBlocker",
    "pub fn accepted_genesis_fixture() -> Self",
    "pub fn accepted_chained_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfAssetLaneEventVerdict<StockEtfAssetLaneEventBlocker>",
    "use crate::ibkr_phase2_artifact::is_sha256_hex",
    "IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID",
}
REQUIRED_EVENT_KINDS = {
    "Unknown",
    "GateCheck",
    "ReadinessStatus",
    "LifecycleEventRef",
    "MarketDataProvenanceRef",
    "DqManifestRef",
    "ScorecardInputRef",
    "ScorecardDerivedRef",
    "ReleasePacketRef",
    "TinyLiveEligibilityRef",
    "KillDisableCleanupRef",
}
REQUIRED_FIELDS = {
    "schema_version",
    "source_version",
    "event_id",
    "event_kind",
    "sequence_number",
    "genesis_event",
    "previous_event_hash",
    "event_time_ms",
    "producer_commit",
    "actor",
    "source",
    "asset_lane",
    "broker",
    "environment",
    "operation",
    "permission_scope",
    "account_fingerprint_hash",
    "session_fingerprint_hash",
    "decision_id",
    "order_intent_id",
    "allowed",
    "denial_reason",
    "payload_hash",
    "raw_artifact_hash",
    "redacted_summary_hash",
    "source_artifact_hash",
    "input_artifact_hashes",
    "secret_content_serialized",
    "raw_payload_inlined",
}
REQUIRED_BLOCKERS = {
    "SchemaVersionMismatch",
    "SourceVersionMismatch",
    "EventIdMissing",
    "EventKindUnknown",
    "SequenceNumberMissing",
    "GenesisSequenceInvalid",
    "GenesisPreviousHashPresent",
    "PreviousEventHashInvalid",
    "EventTimeMissing",
    "ProducerCommitMissing",
    "ActorMissing",
    "SourceMissing",
    "WrongAssetLane",
    "WrongBroker",
    "LiveEnvironmentDenied",
    "PermissionScopeMissing",
    "AccountFingerprintHashInvalid",
    "SessionFingerprintHashInvalid",
    "DecisionIdMissing",
    "OrderIntentIdMissing",
    "DenialReasonPresentOnAllowedEvent",
    "DenialReasonMissingOnDeniedEvent",
    "PayloadHashInvalid",
    "RawArtifactHashInvalid",
    "RedactedSummaryHashInvalid",
    "SourceArtifactHashInvalid",
    "InputArtifactHashesMissing",
    "InputArtifactHashInvalid",
    "SecretContentSerialized",
    "RawPayloadInlined",
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
    return AUDIT_EVENTS.read_text(encoding="utf-8")


def _validate_block(source: str) -> str:
    return source.split(
        "pub fn validate(&self) -> StockEtfAssetLaneEventVerdict<StockEtfAssetLaneEventBlocker>",
        1,
    )[1].split("StockEtfAssetLaneEventVerdict::new(blockers)", 1)[0]


def test_stock_etf_audit_events_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_audit_events_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_EVENT_KINDS | REQUIRED_FIELDS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_audit_events_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "schema_version: STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID.to_string()" in source
    assert "source_version: 0" in source
    assert "event_kind: StockEtfAssetLaneEventKind::Unknown" in source
    assert "sequence_number: 0" in source
    assert "genesis_event: false" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::ReadOnly" in source
    assert "operation: BrokerOperation::HealthRead" in source
    assert "allowed: false" in source
    assert "denial_reason: None" in source
    assert "input_artifact_hashes: Vec::new()" in source
    assert "secret_content_serialized: false" in source
    assert "raw_payload_inlined: false" in source


def test_stock_etf_audit_events_source_keeps_genesis_and_chained_fixtures() -> None:
    source = _source()

    assert "source_version: 1" in source
    assert 'event_id: "stock-etf-audit-event-0001".to_string()' in source
    assert "event_kind: StockEtfAssetLaneEventKind::GateCheck" in source
    assert "sequence_number: 1" in source
    assert "genesis_event: true" in source
    assert "previous_event_hash: String::new()" in source
    assert "source: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string()" in source
    assert 'permission_scope: "readonly_gate_check".to_string()' in source
    assert 'event_id: "stock-etf-audit-event-0002".to_string()' in source
    assert "event_kind: StockEtfAssetLaneEventKind::ScorecardInputRef" in source
    assert "sequence_number: 2" in source
    assert "genesis_event: false" in source
    assert 'source: "stock_etf_scorecard_inputs".to_string()' in source
    assert "operation: BrokerOperation::ScorecardDerive" in source
    assert 'permission_scope: "derived_scorecard_input_reference".to_string()' in source
    assert "allowed: true" in source


def test_stock_etf_audit_events_source_keeps_validation_matrix() -> None:
    source = _source()

    assert "self.schema_version != STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.event_id.trim().is_empty()" in source
    assert "self.event_kind == StockEtfAssetLaneEventKind::Unknown" in source
    assert "self.sequence_number == 0" in source
    assert "if self.genesis_event" in source
    assert "self.sequence_number != 1" in source
    assert "!self.previous_event_hash.trim().is_empty()" in source
    assert "!is_sha256_hex(&self.previous_event_hash)" in source
    assert "self.event_time_ms == 0" in source
    assert "self.producer_commit.trim().is_empty()" in source
    assert "self.actor.trim().is_empty()" in source
    assert "self.source.trim().is_empty()" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "self.environment == BrokerEnvironment::LiveReservedDenied" in source
    assert "self.permission_scope.trim().is_empty()" in source
    assert "!is_sha256_hex(&self.account_fingerprint_hash)" in source
    assert "!is_sha256_hex(&self.session_fingerprint_hash)" in source
    assert "self.decision_id.trim().is_empty()" in source
    assert "self.order_intent_id.trim().is_empty()" in source
    assert "self.allowed && self.denial_reason.is_some()" in source
    assert "!self.allowed && self.denial_reason.is_none()" in source
    assert "!is_sha256_hex(&self.payload_hash)" in source
    assert "!is_sha256_hex(&self.raw_artifact_hash)" in source
    assert "!is_sha256_hex(&self.redacted_summary_hash)" in source
    assert "!is_sha256_hex(&self.source_artifact_hash)" in source
    assert "self.input_artifact_hashes.is_empty()" in source
    assert ".any(|hash| !is_sha256_hex(hash))" in source
    assert "self.secret_content_serialized" in source
    assert "self.raw_payload_inlined" in source


def test_stock_etf_audit_events_source_keeps_exact_blocker_order() -> None:
    validate = _validate_block(_source())
    ordered_blockers = (
        "SchemaVersionMismatch",
        "SourceVersionMismatch",
        "EventIdMissing",
        "EventKindUnknown",
        "SequenceNumberMissing",
        "GenesisSequenceInvalid",
        "GenesisPreviousHashPresent",
        "PreviousEventHashInvalid",
        "EventTimeMissing",
        "ProducerCommitMissing",
        "ActorMissing",
        "SourceMissing",
        "WrongAssetLane",
        "WrongBroker",
        "LiveEnvironmentDenied",
        "PermissionScopeMissing",
        "AccountFingerprintHashInvalid",
        "SessionFingerprintHashInvalid",
        "DecisionIdMissing",
        "OrderIntentIdMissing",
        "DenialReasonPresentOnAllowedEvent",
        "DenialReasonMissingOnDeniedEvent",
        "PayloadHashInvalid",
        "RawArtifactHashInvalid",
        "RedactedSummaryHashInvalid",
        "SourceArtifactHashInvalid",
        "InputArtifactHashesMissing",
        "InputArtifactHashInvalid",
        "SecretContentSerialized",
        "RawPayloadInlined",
    )

    positions = [validate.index(f"Blocker::{blocker}") for blocker in ordered_blockers]
    assert positions == sorted(positions)


def test_stock_etf_audit_events_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{AUDIT_EVENTS}: contains forbidden token {token!r}")

    assert violations == []
