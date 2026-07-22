from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONNECTION_HEALTH = ROOT / "rust/openclaw_types/src/ibkr_tws_connection_health.rs"
MAX_LINES = 2_000

# W4 connection-health 契約是 source-only：不得引入任何 runtime/IO/socket/時鐘/OS 符號。
FORBIDDEN_RUNTIME_TOKENS = (
    "std::env",
    "env::var",
    "std::fs",
    "std::path::Path",
    "File::open",
    "read_to_string",
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
    "std::thread",
    "tokio::spawn",
    "std::process",
    "Command::new",
)

# 契約必含的 taxonomy 符號（四束 + 負空間安全束 + 頂層狀態）。
REQUIRED_TOKENS = (
    "IBKR_CONNECTION_HEALTH_REPORT_CONTRACT_ID",
    "pub struct IbkrConnectionHealthReportV1",
    "pub enum IbkrConnectionHealthReportStatus",
    "pub enum IbkrConnectionHealthHaltReasonV1",
    "pub enum IbkrConnectionHealthEntitlementStateV1",
    "pub enum IbkrConnectionHealthBlocker",
    "pub fn inactive_fixture(",
    "pub fn validate(",
    # session 束
    "pub session_state: IbkrTwsSessionStateV1",
    "pub session_active: bool",
    "pub reconnect_attempt: u32",
    # pacing 束
    "pub main_tokens_available: u64",
    "pub ib_pacing_strikes: u32",
    # attestation 束
    "pub attestation_status: IbkrSessionAttestationStatus",
    "pub account_fingerprint_is_live: bool",
    # entitlement 束
    "pub entitlement_state: IbkrConnectionHealthEntitlementStateV1",
    # 負空間安全束
    "pub ibkr_contact_performed: bool",
    "pub gateway_socket_open: bool",
    "pub order_routed: bool",
    "pub bybit_ipc_reused: bool",
    "pub ibkr_live_enabled: bool",
    # 頂層狀態
    "pub report_status: IbkrConnectionHealthReportStatus",
)


def _source() -> str:
    return CONNECTION_HEALTH.read_text(encoding="utf-8")


def test_connection_health_contract_exists_and_below_cap() -> None:
    assert CONNECTION_HEALTH.exists()
    assert len(_source().splitlines()) <= MAX_LINES


def test_connection_health_contract_keeps_taxonomy() -> None:
    source = _source()
    for token in REQUIRED_TOKENS:
        assert token in source, f"connection-health contract missing {token!r}"


def test_connection_health_contract_negative_space_default_is_fail_closed() -> None:
    source = _source()
    # inactive/預設形態恆 blocked/false/pending/disconnected。
    assert "IbkrTwsSessionStateV1::Disconnected" in source
    assert "IbkrConnectionHealthHaltReasonV1::EnvelopeRequired" in source
    assert "IbkrSessionAttestationStatus::Blocked" in source
    assert "IbkrConnectionHealthEntitlementStateV1::Pending" in source
    assert "IbkrConnectionHealthReportStatus::ExternalVerificationPending" in source


def test_connection_health_contract_has_no_runtime_or_io_tokens() -> None:
    source = _source()
    violations = [
        f"{CONNECTION_HEALTH}: contains forbidden token {token!r}"
        for token in FORBIDDEN_RUNTIME_TOKENS
        if token in source
    ]
    assert violations == []
