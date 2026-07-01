from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE2_POLICIES = ROOT / "rust/openclaw_types/src/ibkr_phase2_policies.rs"
MAX_LINES = 800
REQUIRED_CONTRACT_IDS = {
    "ibkr_redaction_policy_v1",
    "ibkr_rate_limit_policy_v1",
    "ibkr_audit_event_policy_v1",
    "ibkr_paper_attestation_v1",
    "ibkr_python_write_guard_policy_v1",
}
REQUIRED_TEMPLATE_TYPES = {
    "IbkrRedactionPolicyV1",
    "IbkrRateLimitPolicyV1",
    "IbkrAuditEventPolicyV1",
    "IbkrPaperAttestationPolicyV1",
    "IbkrPythonWriteGuardPolicyV1",
}
POLICY_SOURCE_TEMPLATE_COUNT = len(REQUIRED_TEMPLATE_TYPES) + 1
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
    "handle_submit_paper_order",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)


def _source() -> str:
    return PHASE2_POLICIES.read_text(encoding="utf-8")


def test_ibkr_phase2_policy_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_phase2_policy_source_keeps_named_contract_templates() -> None:
    source = _source()

    for contract_id in REQUIRED_CONTRACT_IDS:
        assert contract_id in source
    for type_name in REQUIRED_TEMPLATE_TYPES:
        assert f"impl {type_name}" in source
    assert "impl IbkrPhase2PolicyBundleV1" in source
    assert source.count("pub fn source_template() -> Self") == POLICY_SOURCE_TEMPLATE_COUNT
    assert source.count("source_version: 1") >= len(REQUIRED_TEMPLATE_TYPES)


def test_ibkr_phase2_policy_source_has_no_runtime_or_bybit_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS:
        if token in source:
            violations.append(f"{PHASE2_POLICIES}: contains forbidden token {token!r}")

    assert violations == []
