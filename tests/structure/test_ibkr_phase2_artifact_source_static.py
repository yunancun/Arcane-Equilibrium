from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE2_ARTIFACT = ROOT / "rust/openclaw_types/src/ibkr_phase2_artifact.rs"
MAX_LINES = 800

REQUIRED_IMPORT_TOKENS = {
    "IbkrExternalSurfaceGateV1",
    "IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID",
    "IBKR_PHASE2_ADR",
    "IBKR_PHASE2_AMD",
    "IbkrPhase2GatePrerequisiteFlags",
    "IbkrApiSessionTopologyV1",
    "IbkrSecretSlotContractV1",
}
REQUIRED_TYPE_TOKENS = {
    "pub struct IbkrPhase2GateArtifactV1",
    "impl Default for IbkrPhase2GateArtifactV1",
    "impl IbkrPhase2GateArtifactV1",
    "pub fn validate(&self) -> IbkrPhase2GateArtifactVerdict",
    "pub struct IbkrPhase2GateArtifactVerdict",
    "pub enum IbkrPhase2GateArtifactBlocker",
    "pub fn is_sha256_hex(",
    "fn contains_role(",
    "fn all_policy_flags_true(",
    "fn gate_flags_match_artifact(",
    "fn runtime_contracts_match_gate(",
}
REQUIRED_ARTIFACT_FIELDS = {
    "contract_id",
    "source_version",
    "artifact_id",
    "adr",
    "amd",
    "source_commit",
    "created_at_ms",
    "immutable_storage_path",
    "reviewer_roles",
    "sealed",
    "gate",
    "policy_flags",
    "secret_slot_contract",
    "api_session_topology",
    "raw_artifact_hash",
    "redacted_summary_hash",
    "supersedes_artifact_id",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "ArtifactIdMissing",
    "AdrMismatch",
    "AmdMismatch",
    "SourceCommitMissing",
    "CreatedAtMissing",
    "ImmutableStoragePathMissing",
    "ArtifactNotSealed",
    "PmReviewerMissing",
    "OperatorReviewerMissing",
    "RawArtifactHashInvalid",
    "RedactedSummaryHashInvalid",
    "ExternalSurfaceGateRejected",
    "IbkrCallAlreadyPerformed",
    "PolicyPrerequisiteFlagsRejected",
    "PolicyGateFlagMismatch",
    "SecretSlotContractRejected",
    "ApiSessionTopologyRejected",
    "RuntimeGateFlagMismatch",
}
REQUIRED_POLICY_FLAG_TOKENS = {
    "redaction_suite_passed",
    "rate_limit_policy_present",
    "audit_event_policy_present",
    "paper_attestation_contract_present",
    "python_no_write_guard_present",
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
    return PHASE2_ARTIFACT.read_text(encoding="utf-8")


def _default_block(source: str) -> str:
    return source.split("impl Default for IbkrPhase2GateArtifactV1", 1)[1].split(
        "impl IbkrPhase2GateArtifactV1",
        1,
    )[0]


def _validate_block(source: str) -> str:
    return source.split("pub fn validate(&self) -> IbkrPhase2GateArtifactVerdict", 1)[
        1
    ].split(
        "IbkrPhase2GateArtifactVerdict {",
        1,
    )[0]


def test_ibkr_phase2_artifact_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_phase2_artifact_source_keeps_artifact_contract_matrix() -> None:
    source = _source()

    for token in REQUIRED_IMPORT_TOKENS | REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_ARTIFACT_FIELDS:
        assert field in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "gate: IbkrExternalSurfaceGateV1::default()" in source
    assert "secret_slot_contract: IbkrSecretSlotContractV1::default()" in source
    assert "api_session_topology: IbkrApiSessionTopologyV1::default()" in source
    assert "ibkr_contact_allowed: blockers.is_empty()" in source


def test_ibkr_phase2_artifact_default_keeps_fail_closed_metadata_and_runtime_posture() -> None:
    default = _default_block(_source())

    for required in (
        "contract_id: String::new()",
        "source_version: 0",
        "artifact_id: String::new()",
        "source_commit: String::new()",
        "created_at_ms: 0",
        "immutable_storage_path: String::new()",
        "reviewer_roles: Vec::new()",
        "sealed: false",
        "gate: IbkrExternalSurfaceGateV1::default()",
        "redaction_suite_passed: false",
        "rate_limit_policy_present: false",
        "audit_event_policy_present: false",
        "paper_attestation_contract_present: false",
        "python_no_write_guard_present: false",
        "secret_slot_contract: IbkrSecretSlotContractV1::default()",
        "api_session_topology: IbkrApiSessionTopologyV1::default()",
        "raw_artifact_hash: String::new()",
        "redacted_summary_hash: String::new()",
        "supersedes_artifact_id: None",
    ):
        assert required in default


def test_ibkr_phase2_artifact_source_keeps_gate_policy_runtime_cross_checks() -> None:
    source = _source()

    for token in REQUIRED_POLICY_FLAG_TOKENS:
        assert token in source

    assert "if !self.gate.validate().ibkr_contact_allowed" in source
    assert "if self.gate.ibkr_call_performed" in source
    assert "if !all_policy_flags_true(self.policy_flags)" in source
    assert "if !gate_flags_match_artifact(self)" in source
    assert "let secret_verdict = self.secret_slot_contract.validate()" in source
    assert "let topology_verdict = self.api_session_topology.validate()" in source
    assert "if !runtime_contracts_match_gate(self, secret_verdict.accepted, topology_verdict.accepted)" in source
    assert 'contains_role(&self.reviewer_roles, "PM")' in source
    assert 'contains_role(&self.reviewer_roles, "Operator")' in source
    assert "artifact.gate.secret_contract_present == secret_accepted" in source
    assert "artifact.gate.live_secret_absent_or_empty" in source
    assert "topology_accepted" in source


def test_ibkr_phase2_artifact_source_keeps_exact_blocker_order() -> None:
    validate = _validate_block(_source())
    ordered_blockers = (
        "ContractIdMismatch",
        "SourceVersionMismatch",
        "ArtifactIdMissing",
        "AdrMismatch",
        "AmdMismatch",
        "SourceCommitMissing",
        "CreatedAtMissing",
        "ImmutableStoragePathMissing",
        "ArtifactNotSealed",
        "PmReviewerMissing",
        "OperatorReviewerMissing",
        "RawArtifactHashInvalid",
        "RedactedSummaryHashInvalid",
        "ExternalSurfaceGateRejected",
        "IbkrCallAlreadyPerformed",
        "PolicyPrerequisiteFlagsRejected",
        "PolicyGateFlagMismatch",
        "SecretSlotContractRejected",
        "ApiSessionTopologyRejected",
        "RuntimeGateFlagMismatch",
    )

    positions = [validate.index(f"Blocker::{blocker}") for blocker in ordered_blockers]
    assert positions == sorted(positions)
    assert validate.index("let secret_verdict = self.secret_slot_contract.validate()") < validate.index(
        "let topology_verdict = self.api_session_topology.validate()"
    )
    assert validate.index("let topology_verdict = self.api_session_topology.validate()") < validate.index(
        "runtime_contracts_match_gate(self, secret_verdict.accepted, topology_verdict.accepted)"
    )


def test_ibkr_phase2_artifact_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PHASE2_ARTIFACT}: contains forbidden token {token!r}")

    assert violations == []
