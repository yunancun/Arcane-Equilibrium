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


def _impl_block(source: str, type_name: str) -> str:
    return source.split(f"impl {type_name}", 1)[1].split("pub fn validate(&self)", 1)[0]


def _default_block(source: str, type_name: str) -> str:
    return source.split(f"impl Default for {type_name}", 1)[1].split(
        f"impl {type_name}",
        1,
    )[0]


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


def test_ibkr_phase2_policy_source_templates_keep_fail_closed_authority_posture() -> None:
    source = _source()

    redaction_template = _impl_block(source, "IbkrRedactionPolicyV1")
    for required in (
        "policy_present: true",
        "raw_payload_hash_required: true",
        "redacted_summary_hash_required: true",
        "account_id_in_logs_allowed: false",
        "secret_in_logs_allowed: false",
        "local_path_in_logs_allowed: false",
        "cookie_in_logs_allowed: false",
        "token_in_logs_allowed: false",
        "raw_payload_in_logs_allowed: false",
        "stack_trace_in_reports_allowed: false",
    ):
        assert required in redaction_template
    for forbidden in (
        "account_id_in_logs_allowed: true",
        "secret_in_logs_allowed: true",
        "local_path_in_logs_allowed: true",
        "cookie_in_logs_allowed: true",
        "token_in_logs_allowed: true",
        "raw_payload_in_logs_allowed: true",
        "stack_trace_in_reports_allowed: true",
    ):
        assert forbidden not in redaction_template

    rate_limit_template = _impl_block(source, "IbkrRateLimitPolicyV1")
    for required in (
        "policy_present: true",
        "scope: IbkrRateLimitScope::GlobalAndPerAction",
        "min_request_spacing_ms: 100",
        "max_in_flight_requests: 4",
        "per_action_buckets_present: true",
        "pacing_violation_circuit_breaker_present: true",
        "read_snapshot_budget_present: true",
        "market_data_subscription_budget_present: true",
        "paper_order_write_budget_present: true",
    ):
        assert required in rate_limit_template
    assert "scope: IbkrRateLimitScope::Unknown" not in rate_limit_template

    audit_template = _impl_block(source, "IbkrAuditEventPolicyV1")
    for required in (
        "append_only_required: true",
        "asset_lane_required: true",
        "broker_required: true",
        "environment_required: true",
        "operation_required: true",
        "allowed_required: true",
        "denial_reason_required: true",
        "source_artifact_hash_required: true",
        "raw_artifact_hash_required: true",
        "redacted_summary_hash_required: true",
        "account_fingerprint_hash_only: true",
        "raw_payload_storage_allowed: false",
    ):
        assert required in audit_template
    assert "raw_payload_storage_allowed: true" not in audit_template

    paper_template = _impl_block(source, "IbkrPaperAttestationPolicyV1")
    for required in (
        "external_surface_gate_required: true",
        "session_attestation_required: true",
        "rust_lane_scoped_ipc_required: true",
        "scoped_authorization_required: true",
        "decision_lease_required: true",
        "guardian_required: true",
        "risk_config_hash_required: true",
        "instrument_identity_hash_required: true",
        "idempotency_key_required: true",
        "lifecycle_event_log_required: true",
        "reconciliation_required_before_terminal: true",
        "paper_environment_only: true",
        "live_account_fingerprint_denied: true",
        "margin_short_options_cfd_denied: true",
        "max_paper_notional_required: true",
    ):
        assert required in paper_template

    python_template = _impl_block(source, "IbkrPythonWriteGuardPolicyV1")
    for required in (
        "python_broker_write_authority_denied: true",
        "python_can_read_display_import: true",
        "python_can_call_rust_lane_ipc: true",
        "python_ibkr_order_methods_denied: true",
        "python_live_secret_access_denied: true",
        "gui_cannot_override_authority: true",
        "bybit_paths_unmodified: true",
    ):
        assert required in python_template

    for type_name in REQUIRED_TEMPLATE_TYPES:
        default = _default_block(source, type_name)
        assert "source_version: 0" in default
        assert "policy_present: false" in default


def test_ibkr_phase2_policy_source_has_no_runtime_or_bybit_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS:
        if token in source:
            violations.append(f"{PHASE2_POLICIES}: contains forbidden token {token!r}")

    assert violations == []
