from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "settings/broker/stock_etf_ibkr_readonly_probe_request.template.toml"
MAX_LINES = 80

REQUIRED_DEFAULT_LINES = {
    'contract_id = ""',
    "source_version = 0",
    'asset_lane = "crypto_perp"',
    'broker = "bybit"',
    'environment = "live_reserved_denied"',
    'probe_kind = "connection_health"',
    'api_action = "client_portal_web_api_use"',
    'operation = "transfer_or_account_write"',
    'authority_scope = "denied"',
    "effect_capable = false",
}
REQUIRED_LINEAGE_FIELDS = {
    'request_id = ""',
    'probe_id = ""',
    'external_surface_gate_contract_id = ""',
    'phase2_gate_artifact_hash = ""',
    'api_allowlist_contract_id = ""',
    'api_allowlist_hash = ""',
    'secret_slot_contract_id = ""',
    'secret_slot_contract_hash = ""',
    'api_session_topology_contract_id = ""',
    'api_session_topology_hash = ""',
    'session_attestation_contract_id = ""',
    'session_attestation_hash = ""',
    'redaction_policy_contract_id = ""',
    'redaction_policy_hash = ""',
    'rate_limit_policy_contract_id = ""',
    'rate_limit_policy_hash = ""',
    'audit_event_policy_contract_id = ""',
    'audit_event_policy_hash = ""',
    'source_artifact_hash = ""',
    'raw_artifact_hash = ""',
    'redacted_summary_hash = ""',
}
REQUIRED_DENIAL_FLAGS = {
    "ibkr_contact_performed = false",
    "connector_runtime_started = false",
    "secret_content_serialized = false",
    "order_routed = false",
    "paper_order_submitted = false",
    "db_apply_performed = false",
    "evidence_clock_started = false",
    "bybit_path_reused = false",
    "live_or_tiny_live_authorized = false",
    "margin_short_options_cfd_requested = false",
    "account_write_requested = false",
    "market_data_entitlement_purchase_requested = false",
    "client_portal_web_api_requested = false",
    "python_direct_broker_write_requested = false",
}
FORBIDDEN_RUNTIME_TOKENS = (
    "ib_insync",
    "ibapi",
    "IBApi",
    "TcpStream",
    "UdpSocket",
    "tokio::net",
    "reqwest",
    "hyper::",
    "ureq",
    "requests",
    "urllib",
    "socket",
    "websocket",
    "std::env",
    "env::var",
    "std::fs",
    "File::open",
    "OpenOptions",
    "read_to_string",
    "include_str!",
    "BybitRestClient",
    "BybitPrivateWs",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".create_order(",
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key =",
    "api_secret =",
    "account_id =",
    "password =",
    "token =",
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_stock_etf_readonly_probe_request_template_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_readonly_probe_request_template_keeps_default_denied_shape() -> None:
    source = _source()

    for line in REQUIRED_DEFAULT_LINES:
        assert line in source

    assert " = true" not in source
    assert "stock_etf_ibkr_readonly_probe_request_v1" not in source
    assert "connection_health_read" not in source
    assert "health_read" not in source
    assert 'authority_scope = "read_only"' not in source


def test_stock_etf_readonly_probe_request_template_keeps_empty_lineage() -> None:
    source = _source()

    for line in REQUIRED_LINEAGE_FIELDS:
        assert line in source


def test_stock_etf_readonly_probe_request_template_keeps_side_effect_denials() -> None:
    source = _source()

    for line in REQUIRED_DENIAL_FLAGS:
        assert line in source


def test_stock_etf_readonly_probe_request_template_has_no_runtime_or_secret_material() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS:
        if token in source:
            violations.append(f"{TEMPLATE}: contains forbidden runtime token {token!r}")
    lower = source.lower()
    for token in FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token.lower() in lower:
            violations.append(f"{TEMPLATE}: contains forbidden secret token {token!r}")

    assert violations == []
