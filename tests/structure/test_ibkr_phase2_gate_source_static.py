from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE2_GATE = ROOT / "rust/openclaw_types/src/ibkr_phase2_gate.rs"
MAX_LINES = 800

REQUIRED_CONSTANT_TOKENS = {
    'IBKR_PHASE2_ADR: &str = "ADR-0048"',
    'IBKR_PHASE2_AMD: &str = "AMD-2026-06-29-01"',
    'IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID: &str = "phase2_ibkr_external_surface_gate_v1"',
    'IBKR_SESSION_ATTESTATION_CONTRACT_ID: &str = "ibkr_session_attestation_v1"',
    "IBKR_PAPER_GATEWAY_DEFAULT_PORT: u16 = 4002",
    "IBKR_LIVE_GATEWAY_PORT: u16 = 4001",
    "IBKR_LIVE_TWS_PORT: u16 = 7496",
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrExternalSurfaceGateStatus",
    "pub enum IbkrApiBaseline",
    "pub enum IbkrHostPolicy",
    "pub enum IbkrPortPolicy",
    "pub struct IbkrExternalSurfaceGateV1",
    "pub enum IbkrExternalSurfaceGateBlocker",
    "pub struct IbkrExternalSurfaceGateVerdict",
    "pub enum IbkrSessionAttestationStatus",
    "pub enum IbkrGatewayMode",
    "pub enum IbkrSecretSlotMode",
    "pub enum IbkrSessionDataTier",
    "pub struct IbkrSessionAttestationV1",
    "pub enum IbkrSessionAttestationBlocker",
    "pub struct IbkrSessionAttestationVerdict",
    "pub fn is_loopback_or_unix_local_host(",
}
REQUIRED_GATE_FIELDS = {
    "api_baseline",
    "host_policy",
    "port_policy",
    "live_ports_denied",
    "secret_contract_present",
    "live_secret_absent_or_empty",
    "api_allowlist_present",
    "redaction_suite_passed",
    "rate_limit_policy_present",
    "audit_event_policy_present",
    "paper_attestation_contract_present",
    "python_no_write_guard_present",
    "ibkr_call_performed",
}
REQUIRED_GATE_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "StatusNotPass",
    "AdrMismatch",
    "AmdMismatch",
    "ApiBaselineMismatch",
    "HostPolicyNotLoopbackOnly",
    "PortPolicyNotPaperGatewayOnly",
    "LivePortsNotDenied",
    "SecretContractMissing",
    "LiveSecretPresentOrUnknown",
    "ApiAllowlistMissing",
    "RedactionSuiteMissing",
    "RateLimitPolicyMissing",
    "AuditEventPolicyMissing",
    "PaperAttestationContractMissing",
    "PythonNoWriteGuardMissing",
    "IbkrCallAlreadyPerformed",
}
REQUIRED_ATTESTATION_FIELDS = {
    "account_fingerprint",
    "account_fingerprint_is_live",
    "environment",
    "host",
    "port",
    "process_identity",
    "gateway_mode",
    "secret_slot_fingerprint",
    "secret_slot_mode",
    "secret_world_readable",
    "live_secret_absent_or_empty",
    "env_var_credential_fallback_used",
    "api_server_version",
    "data_tier",
    "entitlements_fingerprint",
    "market_data_entitlement_purchase_denied",
    "gateway_started_at_ms",
    "attested_at_ms",
    "expires_at_ms",
    "raw_artifact_hash",
}
REQUIRED_ATTESTATION_BLOCKERS = {
    "StatusBlocked",
    "EnvironmentDenied",
    "HostNotLoopback",
    "LivePortDenied",
    "PortNotPaperGatewayDefault",
    "MissingAccountFingerprint",
    "AccountFingerprintInvalid",
    "LiveAccountFingerprint",
    "MissingProcessIdentity",
    "UnknownOrLiveGatewayMode",
    "MissingSecretSlotFingerprint",
    "SecretSlotFingerprintInvalid",
    "SecretSlotMissing",
    "SecretSlotWorldReadable",
    "SecretSlotModeDenied",
    "LiveSecretPresentOrUnknown",
    "EnvVarCredentialFallback",
    "MissingApiServerVersion",
    "MissingDataTier",
    "MissingDataEntitlementsFingerprint",
    "DataEntitlementsFingerprintInvalid",
    "MarketDataEntitlementPurchaseNotDenied",
    "MissingGatewayStartupTime",
    "GatewayStartupAfterAttestation",
    "MissingRawArtifactHash",
    "RawArtifactHashInvalid",
    "InvalidAttestationWindow",
    "StaleAttestation",
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
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return PHASE2_GATE.read_text(encoding="utf-8")


def _external_gate_default_block(source: str) -> str:
    return source.split("impl Default for IbkrExternalSurfaceGateV1", 1)[1].split(
        "impl IbkrExternalSurfaceGateV1",
        1,
    )[0]


def _external_gate_fixture_block(source: str) -> str:
    return source.split("impl IbkrExternalSurfaceGateV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


def _session_attestation_default_block(source: str) -> str:
    return source.split("impl Default for IbkrSessionAttestationV1", 1)[1].split(
        "impl IbkrSessionAttestationV1",
        1,
    )[0]


def _session_attestation_fixture_block(source: str) -> str:
    return source.split("impl IbkrSessionAttestationV1", 1)[1].split(
        "pub fn validate(&self, now_ms: u64)",
        1,
    )[0]


def test_ibkr_phase2_gate_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_phase2_gate_source_keeps_external_surface_gate_matrix() -> None:
    source = _source()

    for token in REQUIRED_CONSTANT_TOKENS | REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_GATE_FIELDS:
        assert field in source
    for blocker in REQUIRED_GATE_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "status: IbkrExternalSurfaceGateStatus::Blocked" in source
    assert "status: IbkrExternalSurfaceGateStatus::Pass" in source
    assert "ibkr_contact_allowed: blockers.is_empty()" in source
    assert "if self.ibkr_call_performed" in source
    assert "if self.host_policy != IbkrHostPolicy::LoopbackOnly" in source
    assert "if self.port_policy != IbkrPortPolicy::PaperGatewayPortOnly" in source


def test_ibkr_phase2_gate_source_keeps_default_blocked_and_pass_fixture_posture() -> None:
    source = _source()
    default = _external_gate_default_block(source)
    fixture = _external_gate_fixture_block(source)

    for required in (
        "contract_id: String::new()",
        "source_version: 0",
        "status: IbkrExternalSurfaceGateStatus::Blocked",
        "api_baseline: IbkrApiBaseline::IbGatewayTwsApi",
        "host_policy: IbkrHostPolicy::LoopbackOnly",
        "port_policy: IbkrPortPolicy::PaperGatewayPortOnly",
        "live_ports_denied: false",
        "secret_contract_present: false",
        "live_secret_absent_or_empty: false",
        "api_allowlist_present: false",
        "redaction_suite_passed: false",
        "rate_limit_policy_present: false",
        "audit_event_policy_present: false",
        "paper_attestation_contract_present: false",
        "python_no_write_guard_present: false",
        "ibkr_call_performed: false",
    ):
        assert required in default

    for required in (
        "contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string()",
        "source_version: 1",
        "status: IbkrExternalSurfaceGateStatus::Pass",
        "live_ports_denied: true",
        "secret_contract_present: true",
        "live_secret_absent_or_empty: true",
        "api_allowlist_present: true",
        "redaction_suite_passed: true",
        "rate_limit_policy_present: true",
        "audit_event_policy_present: true",
        "paper_attestation_contract_present: true",
        "python_no_write_guard_present: true",
        "ibkr_call_performed: false",
        "..Self::default()",
    ):
        assert required in fixture


def test_ibkr_phase2_gate_source_keeps_session_attestation_matrix() -> None:
    source = _source()

    for field in REQUIRED_ATTESTATION_FIELDS:
        assert field in source
    for blocker in REQUIRED_ATTESTATION_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert 'host: "127.0.0.1".to_string()' in source
    assert "port: IBKR_PAPER_GATEWAY_DEFAULT_PORT" in source
    assert "self.port == IBKR_LIVE_GATEWAY_PORT || self.port == IBKR_LIVE_TWS_PORT" in source
    assert "self.port != IBKR_PAPER_GATEWAY_DEFAULT_PORT" in source
    assert "if self.env_var_credential_fallback_used" in source
    assert "if now_ms >= self.expires_at_ms" in source
    assert 'matches!(normalized.as_str(), "127.0.0.1" | "::1" | "localhost")' in source
    assert 'normalized.starts_with("unix:")' in source


def test_ibkr_phase2_gate_source_keeps_session_default_and_paper_fixture_posture() -> None:
    source = _source()
    default = _session_attestation_default_block(source)
    fixture = _session_attestation_fixture_block(source)

    for required in (
        "contract_id: String::new()",
        "source_version: 0",
        "status: IbkrSessionAttestationStatus::Blocked",
        "account_fingerprint: String::new()",
        "account_fingerprint_is_live: false",
        "environment: BrokerEnvironment::ReadOnly",
        "host: String::new()",
        "port: 0",
        "process_identity: String::new()",
        "gateway_mode: IbkrGatewayMode::Unknown",
        "secret_slot_fingerprint: String::new()",
        "secret_slot_mode: IbkrSecretSlotMode::Unknown",
        "secret_world_readable: false",
        "live_secret_absent_or_empty: false",
        "env_var_credential_fallback_used: false",
        "api_server_version: String::new()",
        "data_tier: IbkrSessionDataTier::Unknown",
        "entitlements_fingerprint: String::new()",
        "market_data_entitlement_purchase_denied: false",
        "gateway_started_at_ms: 0",
        "attested_at_ms: 0",
        "expires_at_ms: 0",
        "raw_artifact_hash: String::new()",
    ):
        assert required in default

    for required in (
        "contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string()",
        "source_version: 1",
        "status: IbkrSessionAttestationStatus::PaperAttested",
        'account_fingerprint: "b".repeat(64)',
        "account_fingerprint_is_live: false",
        "environment: BrokerEnvironment::Paper",
        'host: "127.0.0.1".to_string()',
        "port: IBKR_PAPER_GATEWAY_DEFAULT_PORT",
        'process_identity: "trade-core:ibgateway-paper".to_string()',
        "gateway_mode: IbkrGatewayMode::Paper",
        'secret_slot_fingerprint: "a".repeat(64)',
        "secret_slot_mode: IbkrSecretSlotMode::Paper",
        "secret_world_readable: false",
        "live_secret_absent_or_empty: true",
        "env_var_credential_fallback_used: false",
        'api_server_version: "source_fixture_only".to_string()',
        "data_tier: IbkrSessionDataTier::Delayed",
        'entitlements_fingerprint: "c".repeat(64)',
        "market_data_entitlement_purchase_denied: true",
        "gateway_started_at_ms: 1_772_231_940_000",
        "attested_at_ms: 1_772_232_000_000",
        "expires_at_ms: 1_772_235_600_000",
        'raw_artifact_hash: "e".repeat(64)',
    ):
        assert required in fixture


def test_ibkr_phase2_gate_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PHASE2_GATE}: contains forbidden token {token!r}")

    assert violations == []
