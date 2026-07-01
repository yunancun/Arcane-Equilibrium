from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FEATURE_FLAG_SECRET_AUTH = ROOT / "rust/openclaw_types/src/ibkr_feature_flag_secret_auth.rs"
MAX_LINES = 800

REQUIRED_IMPORT_TOKENS = {
    "IbkrPhase2GateArtifactV1",
    "IbkrSessionAttestationV1",
    "IbkrSecretSlotContractV1",
    "StockEtfFeatureFlags",
    "BrokerCapabilityRequest",
    "BrokerEnvironment",
    "BrokerOperation",
    "is_sha256_hex",
}
REQUIRED_TYPE_TOKENS = {
    'FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID: &str = "feature_flag_secret_auth_matrix_v1"',
    "pub struct StockEtfAuthorizationEnvelopeV1",
    "impl Default for StockEtfAuthorizationEnvelopeV1",
    "impl StockEtfAuthorizationEnvelopeV1",
    "pub fn paper_fixture(",
    "pub struct FeatureFlagSecretAuthMatrixV1",
    "impl Default for FeatureFlagSecretAuthMatrixV1",
    "impl FeatureFlagSecretAuthMatrixV1",
    "pub fn validate_operation(",
    "fn validate_authorization_envelope(",
    "pub struct FeatureFlagSecretAuthVerdict",
    "pub enum FeatureFlagSecretAuthBlocker",
    "pub fn evaluate_feature_flag_secret_auth_matrix(",
}
REQUIRED_MATRIX_FIELDS = {
    "contract_id",
    "source_version",
    "flags",
    "secret_slot_contract",
    "phase2_gate_artifact",
    "session_attestation",
    "authorization_envelope",
    "gui_lane_state_override_denied",
    "server_rust_matrix_authoritative",
}
REQUIRED_ENVELOPE_FIELDS = {
    "asset_lane",
    "broker",
    "environment",
    "permission_scope",
    "secret_slot_fingerprint",
    "account_fingerprint_hash",
    "risk_config_hash",
    "expires_at_ms",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "ServerRustMatrixNotAuthoritative",
    "GuiLaneStateOverrideNotDenied",
    "WrongAssetLane",
    "WrongBroker",
    "LiveEnvironmentDenied",
    "InstrumentKindDenied",
    "LiveOrAccountWriteOperationDenied",
    "LaneFlagDisabled",
    "ReadonlyFlagDisabled",
    "PaperFlagDisabled",
    "ShadowOnlyBlocksPaper",
    "SecretContractRejected",
    "LiveSecretAbsentOrEmptyNotProven",
    "Phase2ArtifactRejected",
    "SessionAttestationRejected",
    "AuthorizationEnvelopeMismatch",
    "PermissionScopeMismatch",
    "SecretSlotFingerprintInvalid",
    "AccountFingerprintHashInvalid",
    "RiskConfigHashInvalid",
    "AuthorizationEnvelopeExpired",
    "SecretSlotFingerprintMismatch",
    "AccountFingerprintMismatch",
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
    return FEATURE_FLAG_SECRET_AUTH.read_text(encoding="utf-8")


def test_ibkr_feature_flag_secret_auth_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_feature_flag_secret_auth_source_keeps_auth_matrix_contract() -> None:
    source = _source()

    for token in REQUIRED_IMPORT_TOKENS | REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_MATRIX_FIELDS | REQUIRED_ENVELOPE_FIELDS:
        assert field in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "environment: BrokerEnvironment::ReadOnly" in source
    assert "permission_scope: AuthorityScope::Denied" in source
    assert "flags: StockEtfFeatureFlags::default()" in source
    assert "secret_slot_contract: IbkrSecretSlotContractV1::default()" in source
    assert "phase2_gate_artifact: IbkrPhase2GateArtifactV1::default()" in source
    assert "session_attestation: IbkrSessionAttestationV1::default()" in source
    assert "authorization_envelope: StockEtfAuthorizationEnvelopeV1::default()" in source
    assert "gui_lane_state_override_denied: false" in source
    assert "server_rust_matrix_authoritative: false" in source
    assert "allowed: blockers.is_empty()" in source
    assert "AuthorityScope::Denied" in source


def test_ibkr_feature_flag_secret_auth_source_keeps_policy_secret_artifact_session_chain() -> None:
    source = _source()

    assert "if !self.server_rust_matrix_authoritative" in source
    assert "if !self.gui_lane_state_override_denied" in source
    assert "request.asset_lane != AssetLane::StockEtfCash" in source
    assert "request.broker != Broker::Ibkr" in source
    assert "request.environment == BrokerEnvironment::LiveReservedDenied" in source
    assert "!request.instrument_kind.allowed_for_stock_etf_cash()" in source
    assert "BrokerOperation::LiveOrderSubmit" in source
    assert "BrokerOperation::MarginOrShort" in source
    assert "BrokerOperation::OptionsOrCfd" in source
    assert "BrokerOperation::TransferOrAccountWrite" in source
    assert "if !self.flags.stock_etf_lane_enabled" in source
    assert "request.operation.is_read() && !self.flags.ibkr_readonly_enabled" in source
    assert "request.operation.is_paper_write() && !self.flags.ibkr_paper_enabled" in source
    assert "request.operation.is_paper_write() && self.flags.stock_etf_shadow_only" in source
    assert "let secret_verdict = self.secret_slot_contract.validate()" in source
    assert "if !secret_verdict.accepted" in source
    assert "if !self.secret_slot_contract.live_secret_absent_or_empty" in source
    assert "let artifact_verdict = self.phase2_gate_artifact.validate()" in source
    assert "if !artifact_verdict.ibkr_contact_allowed" in source
    assert "let session_verdict = self.session_attestation.validate(now_ms)" in source
    assert "if !session_verdict.attestation_accepted" in source
    assert "self.validate_authorization_envelope(request, now_ms, &mut blockers)" in source


def test_ibkr_feature_flag_secret_auth_source_keeps_authorization_envelope_cross_checks() -> None:
    source = _source()

    assert "envelope.asset_lane != request.asset_lane" in source
    assert "envelope.broker != request.broker" in source
    assert "envelope.environment != request.environment" in source
    assert "envelope.permission_scope != request.operation.authority_scope()" in source
    assert "!is_sha256_hex(&envelope.secret_slot_fingerprint)" in source
    assert "!is_sha256_hex(&envelope.account_fingerprint_hash)" in source
    assert "!is_sha256_hex(&envelope.risk_config_hash)" in source
    assert "envelope.expires_at_ms == 0 || now_ms >= envelope.expires_at_ms" in source
    assert (
        "envelope.secret_slot_fingerprint != self.secret_slot_contract.secret_slot_fingerprint"
        in source
    )
    assert (
        "envelope.secret_slot_fingerprint != self.session_attestation.secret_slot_fingerprint"
        in source
    )
    assert (
        "envelope.account_fingerprint_hash != self.secret_slot_contract.account_fingerprint_hash"
        in source
    )
    assert ".phase2_gate_artifact" in source
    assert ".api_session_topology" in source
    assert ".account_fingerprint_hash" in source
    assert "envelope.account_fingerprint_hash != self.session_attestation.account_fingerprint" in source


def test_ibkr_feature_flag_secret_auth_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{FEATURE_FLAG_SECRET_AUTH}: contains forbidden token {token!r}")

    assert violations == []
