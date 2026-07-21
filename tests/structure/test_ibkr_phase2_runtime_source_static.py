from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE2_RUNTIME = ROOT / "rust/openclaw_types/src/ibkr_phase2_runtime.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_CONSTANT_TOKENS = {
    'IBKR_SECRET_SLOT_CONTRACT_ID: &str = "ibkr_secret_slot_contract_v1"',
    'IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID: &str = "ibkr_api_session_topology_v1"',
    "IBKR_LIVE_GATEWAY_PORT",
    "IBKR_LIVE_TWS_PORT",
    "IBKR_PAPER_GATEWAY_DEFAULT_PORT",
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrSecretSlotPosture",
    "pub struct IbkrSecretSlotContractV1",
    "pub struct IbkrSecretSlotContractVerdict",
    "pub enum IbkrSecretSlotContractBlocker",
    "pub enum IbkrGatewayProcessMode",
    "pub struct IbkrApiSessionTopologyV1",
    "pub struct IbkrApiSessionTopologyVerdict",
    "pub enum IbkrApiSessionTopologyBlocker",
    "pub fn is_sha256_hex(",
}
REQUIRED_SECRET_POSTURES = {
    "Missing",
    "PresentHashed",
    "LiveAbsentOrEmpty",
    "LivePresentDenied",
    "Unknown",
}
REQUIRED_SECRET_FIELDS = {
    "contract_present",
    "readonly_slot_posture",
    "paper_slot_posture",
    "live_slot_posture",
    "secret_slot_fingerprint",
    "account_fingerprint_hash",
    "owner_only_permissions",
    "env_var_credential_fallback_denied",
    "secret_content_serialized",
    "account_id_serialized",
    "live_secret_absent_or_empty",
}
REQUIRED_SECRET_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "ContractMissing",
    "ReadonlySlotPostureInvalid",
    "PaperSlotMissingOrUnhashed",
    "LiveSlotPresentOrUnknown",
    "SecretSlotFingerprintInvalid",
    "AccountFingerprintHashInvalid",
    "OwnerOnlyPermissionsMissing",
    "EnvVarCredentialFallbackNotDenied",
    "SecretContentSerialized",
    "AccountIdSerialized",
    "LiveSecretAbsentOrEmptyNotProven",
}
REQUIRED_TOPOLOGY_FIELDS = {
    "topology_present",
    "api_baseline",
    "runtime_owner",
    "host",
    "port",
    "gateway_mode",
    "environment",
    "deterministic_client_id_present",
    "process_identity_recorded",
    "account_fingerprint_hash",
    "api_server_version_recorded",
    "data_entitlements_recorded",
    "startup_time_recorded",
    "attestation_expiry_recorded",
}
REQUIRED_TOPOLOGY_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "TopologyMissing",
    "ApiBaselineMismatch",
    "RuntimeOwnerMismatch",
    "HostNotLoopback",
    "LivePortDenied",
    "PaperPortNotUsed",
    "GatewayModeNotPaper",
    "EnvironmentNotPaper",
    "DeterministicClientIdMissing",
    "ProcessIdentityMissing",
    "AccountFingerprintHashInvalid",
    "ApiServerVersionMissing",
    "DataEntitlementsMissing",
    "StartupTimeMissing",
    "AttestationExpiryMissing",
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
    return PHASE2_RUNTIME.read_text(encoding="utf-8")


def _function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def _secret_slot_default_block(source: str) -> str:
    return source.split("impl Default for IbkrSecretSlotContractV1", 1)[1].split(
        "impl IbkrSecretSlotContractV1",
        1,
    )[0]


def _secret_slot_template_block(source: str) -> str:
    return source.split("impl IbkrSecretSlotContractV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


def _topology_default_block(source: str) -> str:
    return source.split("impl Default for IbkrApiSessionTopologyV1", 1)[1].split(
        "impl IbkrApiSessionTopologyV1",
        1,
    )[0]


def _topology_template_block(source: str) -> str:
    return source.split("impl IbkrApiSessionTopologyV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


def test_ibkr_phase2_runtime_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_phase2_runtime_source_keeps_secret_slot_contract_matrix() -> None:
    source = _source()

    for token in REQUIRED_CONSTANT_TOKENS | REQUIRED_TYPE_TOKENS:
        assert token in source
    for posture in REQUIRED_SECRET_POSTURES:
        assert f"IbkrSecretSlotPosture::{posture}" in source or posture in source
    for field in REQUIRED_SECRET_FIELDS:
        assert field in source
    for blocker in REQUIRED_SECRET_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "paper_slot_posture: IbkrSecretSlotPosture::PresentHashed" in source
    assert "live_slot_posture: IbkrSecretSlotPosture::LiveAbsentOrEmpty" in source
    assert "secret_content_serialized: false" in source
    assert "account_id_serialized: false" in source
    assert "if self.secret_content_serialized" in source
    assert "if self.account_id_serialized" in source


def test_ibkr_phase2_runtime_source_keeps_api_session_topology_matrix() -> None:
    source = _source()

    for field in REQUIRED_TOPOLOGY_FIELDS:
        assert field in source
    for blocker in REQUIRED_TOPOLOGY_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert 'api_baseline: "ib_gateway_tws_api".to_string()' in source
    assert 'runtime_owner: "trade-core".to_string()' in source
    assert 'host: "127.0.0.1".to_string()' in source
    assert "port: IBKR_PAPER_GATEWAY_DEFAULT_PORT" in source
    assert "gateway_mode: IbkrGatewayProcessMode::PaperGateway" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "self.port == IBKR_LIVE_GATEWAY_PORT || self.port == IBKR_LIVE_TWS_PORT" in source
    assert "self.port != IBKR_PAPER_GATEWAY_DEFAULT_PORT" in source
    assert "!is_loopback_or_unix_local_host(&self.host)" in source


def test_ibkr_phase2_runtime_source_keeps_default_and_source_template_posture() -> None:
    source = _source()
    secret_default = _secret_slot_default_block(source)
    secret_template = _secret_slot_template_block(source)
    topology_default = _topology_default_block(source)
    topology_template = _topology_template_block(source)

    for required in (
        "contract_id: String::new()",
        "source_version: 0",
        "contract_present: false",
        "readonly_slot_posture: IbkrSecretSlotPosture::Unknown",
        "paper_slot_posture: IbkrSecretSlotPosture::Unknown",
        "live_slot_posture: IbkrSecretSlotPosture::Unknown",
        "secret_slot_fingerprint: String::new()",
        "account_fingerprint_hash: String::new()",
        "owner_only_permissions: false",
        "env_var_credential_fallback_denied: false",
        "secret_content_serialized: false",
        "account_id_serialized: false",
        "live_secret_absent_or_empty: false",
    ):
        assert required in secret_default

    for required in (
        "contract_id: IBKR_SECRET_SLOT_CONTRACT_ID.to_string()",
        "source_version: 1",
        "contract_present: true",
        "readonly_slot_posture: IbkrSecretSlotPosture::PresentHashed",
        "paper_slot_posture: IbkrSecretSlotPosture::PresentHashed",
        "live_slot_posture: IbkrSecretSlotPosture::LiveAbsentOrEmpty",
        'secret_slot_fingerprint: "a".repeat(64)',
        'account_fingerprint_hash: "b".repeat(64)',
        "owner_only_permissions: true",
        "env_var_credential_fallback_denied: true",
        "secret_content_serialized: false",
        "account_id_serialized: false",
        "live_secret_absent_or_empty: true",
    ):
        assert required in secret_template

    for required in (
        "contract_id: String::new()",
        "source_version: 0",
        "topology_present: false",
        "api_baseline: String::new()",
        "runtime_owner: String::new()",
        "host: String::new()",
        "port: 0",
        "gateway_mode: IbkrGatewayProcessMode::Unknown",
        "environment: BrokerEnvironment::ReadOnly",
        "deterministic_client_id_present: false",
        "process_identity_recorded: false",
        "account_fingerprint_hash: String::new()",
        "api_server_version_recorded: false",
        "data_entitlements_recorded: false",
        "startup_time_recorded: false",
        "attestation_expiry_recorded: false",
    ):
        assert required in topology_default

    for required in (
        "contract_id: IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID.to_string()",
        "source_version: 1",
        "topology_present: true",
        'api_baseline: "ib_gateway_tws_api".to_string()',
        'runtime_owner: "trade-core".to_string()',
        'host: "127.0.0.1".to_string()',
        "port: IBKR_PAPER_GATEWAY_DEFAULT_PORT",
        "gateway_mode: IbkrGatewayProcessMode::PaperGateway",
        "environment: BrokerEnvironment::Paper",
        "deterministic_client_id_present: true",
        "process_identity_recorded: true",
        'account_fingerprint_hash: "c".repeat(64)',
        "api_server_version_recorded: true",
        "data_entitlements_recorded: true",
        "startup_time_recorded: true",
        "attestation_expiry_recorded: true",
    ):
        assert required in topology_template


def test_ibkr_phase2_runtime_source_keeps_fail_closed_verdicts_and_live_port_dual_denial() -> None:
    source = _source()

    assert "accepted: blockers.is_empty()" in source
    assert "if self.contract_id != IBKR_SECRET_SLOT_CONTRACT_ID" in source
    assert "if self.contract_id != IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID" in source
    assert "if self.port == IBKR_LIVE_GATEWAY_PORT || self.port == IBKR_LIVE_TWS_PORT" in source
    assert "blockers.push(Blocker::LivePortDenied)" in source
    assert "if self.port != IBKR_PAPER_GATEWAY_DEFAULT_PORT" in source
    assert "blockers.push(Blocker::PaperPortNotUsed)" in source
    assert "if !self.live_secret_absent_or_empty" in source
    assert "blockers.push(Blocker::LiveSecretAbsentOrEmptyNotProven)" in source


def test_ibkr_phase2_runtime_source_keeps_exact_blocker_order() -> None:
    source = _source()
    secret_slot = _function_block(
        source,
        "pub fn validate(&self) -> IbkrSecretSlotContractVerdict {",
        "IbkrSecretSlotContractVerdict {",
    )
    topology = _function_block(
        source,
        "pub fn validate(&self) -> IbkrApiSessionTopologyVerdict {",
        "IbkrApiSessionTopologyVerdict {",
    )

    for block, ordered_blockers in (
        (
            secret_slot,
            (
                "ContractIdMismatch",
                "SourceVersionMismatch",
                "ContractMissing",
                "ReadonlySlotPostureInvalid",
                "PaperSlotMissingOrUnhashed",
                "LiveSlotPresentOrUnknown",
                "SecretSlotFingerprintInvalid",
                "AccountFingerprintHashInvalid",
                "OwnerOnlyPermissionsMissing",
                "EnvVarCredentialFallbackNotDenied",
                "SecretContentSerialized",
                "AccountIdSerialized",
                "LiveSecretAbsentOrEmptyNotProven",
            ),
        ),
        (
            topology,
            (
                "ContractIdMismatch",
                "SourceVersionMismatch",
                "TopologyMissing",
                "ApiBaselineMismatch",
                "RuntimeOwnerMismatch",
                "HostNotLoopback",
                "LivePortDenied",
                "PaperPortNotUsed",
                "GatewayModeNotPaper",
                "EnvironmentNotPaper",
                "DeterministicClientIdMissing",
                "ProcessIdentityMissing",
                "AccountFingerprintHashInvalid",
                "ApiServerVersionMissing",
                "DataEntitlementsMissing",
                "StartupTimeMissing",
                "AttestationExpiryMissing",
            ),
        ),
    ):
        positions = [block.index(f"Blocker::{blocker}") for blocker in ordered_blockers]
        assert positions == sorted(positions)


def test_ibkr_phase2_runtime_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PHASE2_RUNTIME}: contains forbidden token {token!r}")

    assert violations == []
