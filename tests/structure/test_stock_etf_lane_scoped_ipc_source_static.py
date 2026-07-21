from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANE_SCOPED_IPC = ROOT / "rust/openclaw_types/src/stock_etf_lane_scoped_ipc.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES
REQUIRED_METHOD_VARIANTS = {
    "GetLaneStatus",
    "GetPhase0Status",
    "GetReadiness",
    "GetDataFoundationStatus",
    "GetPolicyStatus",
    "GetAuthorizationStatus",
    "GetAccountStatus",
    "GetPaperStatus",
    "GetReconciliationStatus",
    "GetScorecardStatus",
    "GetLaunchStatus",
    "GetReleasePacketStatus",
    "GetDisableCleanupStatus",
    "GetConnectionHealth",
    "PreviewPaperOrder",
    "SubmitPaperOrder",
    "CancelPaperOrder",
    "ReplacePaperOrder",
    "ImportPaperFills",
    "EvaluateShadowSignal",
    "PreviewReadonlyProbe",
}
DENIED_METHOD_VARIANTS = {
    "BybitSubmitPaperOrderDenied",
    "UnknownDenied",
}
REQUIRED_CONTRACT_TOKENS = {
    "STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID",
    "STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID",
    "IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "NON_BYBIT_API_ALLOWLIST_CONTRACT_ID",
    "IBKR_SECRET_SLOT_CONTRACT_ID",
    "IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID",
    "STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID",
    "STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID",
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
    "handle_submit_paper_order",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)


def _source() -> str:
    return LANE_SCOPED_IPC.read_text(encoding="utf-8")


def _block_between(source: str, start_token: str, end_tokens: tuple[str, ...]) -> str:
    start = source.index(start_token)
    end = len(source)
    for token in end_tokens:
        candidate = source.find(token, start + len(start_token))
        if candidate != -1:
            end = min(end, candidate)
    return source[start:end]


def _named_function_body(source: str, name: str) -> str:
    marker = f"fn {name}("
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"function body not closed: {name}")


def _assert_ordered_tokens(block: str, tokens: tuple[str, ...]) -> None:
    positions = [block.index(token) for token in tokens]
    assert positions == sorted(positions)


def _required_methods_block(source: str) -> str:
    return _block_between(source, "const REQUIRED_METHODS", ("\n\nconst STATUS_FIELDS",))


def _default_block(source: str) -> str:
    return _block_between(
        source,
        "impl Default for StockEtfLaneScopedIpcContractV1",
        ("\n}\n\nimpl StockEtfLaneScopedIpcContractV1",),
    )


def _accepted_fixture_block(source: str) -> str:
    impl = _block_between(
        source,
        "impl StockEtfLaneScopedIpcContractV1",
        ("\n#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]\npub struct StockEtfLaneScopedIpcCommandV1",),
    )
    return _block_between(
        impl,
        "pub fn accepted_fixture() -> Self",
        ("\n    pub fn validate(&self)",),
    )


def test_stock_etf_lane_scoped_ipc_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_lane_scoped_ipc_source_keeps_method_matrix() -> None:
    source = _source()
    required_methods = _required_methods_block(source)

    assert "const REQUIRED_METHODS" in source
    assert "pub enum StockEtfLaneScopedIpcMethod" in source
    assert "fn expected_method(" in source
    assert len(REQUIRED_METHOD_VARIANTS) == 21
    for variant in REQUIRED_METHOD_VARIANTS:
        assert f"StockEtfLaneScopedIpcMethod::{variant}" in required_methods
        assert f"Method::{variant}" in source
    for variant in DENIED_METHOD_VARIANTS:
        assert variant in source
        assert f"StockEtfLaneScopedIpcMethod::{variant}" not in required_methods
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source


def test_stock_etf_lane_scoped_ipc_source_keeps_default_fail_closed() -> None:
    default = _default_block(_source())

    for fail_closed in (
        "contract_id: String::new()",
        "source_version: 0",
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "rust_authority_owner: false",
        "python_forward_only: false",
        "python_direct_broker_write_denied: false",
        "bybit_ipc_reuse_denied: false",
        "existing_bybit_paper_path_denied: false",
        "live_environment_denied: false",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "commands: Vec::new()",
    ):
        assert fail_closed in default


def test_stock_etf_lane_scoped_ipc_source_keeps_accepted_fixture_separated_and_side_effect_free() -> None:
    fixture = _accepted_fixture_block(_source())

    for required in (
        "contract_id: STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID.to_string()",
        "source_version: 1",
        "asset_lane: AssetLane::StockEtfCash",
        "broker: Broker::Ibkr",
        "rust_authority_owner: true",
        "python_forward_only: true",
        "python_direct_broker_write_denied: true",
        "bybit_ipc_reuse_denied: true",
        "existing_bybit_paper_path_denied: true",
        "live_environment_denied: true",
        "bybit_live_execution_unchanged: true",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "commands: REQUIRED_METHODS",
        ".map(StockEtfLaneScopedIpcCommandV1::fixture_for_method)",
    ):
        assert required in fixture

    for forbidden in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "rust_authority_owner: false",
        "python_forward_only: false",
        "python_direct_broker_write_denied: false",
        "bybit_ipc_reuse_denied: false",
        "existing_bybit_paper_path_denied: false",
        "live_environment_denied: false",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
        "BybitSubmitPaperOrderDenied",
        "UnknownDenied",
    ):
        assert forbidden not in fixture


def test_stock_etf_lane_scoped_ipc_source_keeps_expected_method_authority_classes() -> None:
    source = _source()

    assert "Method::GetLaneStatus => ExpectedMethod" in source
    assert "operation: Op::HealthRead" in source
    assert "authority_scope: Scope::DisplayOnly" in source
    assert "rust_owned: false" in source
    assert "Method::PreviewPaperOrder => ExpectedMethod" in source
    assert "operation: Op::PaperOrderSubmit" in source
    assert "authority_scope: Scope::ReadOnly" in source
    assert "rust_owned: true" in source
    assert "paper_effect_method(Op::PaperOrderSubmit, SUBMIT_PAPER_ORDER_FIELDS)" in source
    assert "paper_effect_method(Op::PaperOrderCancel, CANCEL_PAPER_ORDER_FIELDS)" in source
    assert "paper_effect_method(Op::PaperOrderReplace, REPLACE_PAPER_ORDER_FIELDS)" in source
    assert "operation: Op::PaperOrderFillImport" in source
    assert "operation: Op::ShadowSignalEmit" in source
    assert "Method::PreviewReadonlyProbe => ExpectedMethod" in source
    assert "authority_scope: Scope::ReadOnly" in source
    assert "required_gates: READONLY_PROBE_GATES" in source
    assert "Method::BybitSubmitPaperOrderDenied | Method::UnknownDenied" in source
    assert "authority_scope: Scope::Denied" in source


def test_stock_etf_lane_scoped_ipc_source_pins_blocker_emit_order() -> None:
    source = _source()
    validate_body = source[source.index("pub fn validate(&self)") : source.index(
        "StockEtfLaneScopedIpcVerdict::new(blockers)"
    )]
    validate_command_body = _named_function_body(source, "validate_command")

    _assert_ordered_tokens(
        validate_body,
        (
            "Blocker::ContractIdMismatch",
            "Blocker::SourceVersionMismatch",
            "Blocker::WrongAssetLane",
            "Blocker::WrongBroker",
            "Blocker::RustAuthorityOwnerMissing",
            "Blocker::PythonForwardOnlyMissing",
            "Blocker::PythonDirectBrokerWriteNotDenied",
            "Blocker::BybitIpcReuseNotDenied",
            "Blocker::ExistingBybitPaperPathNotDenied",
            "Blocker::LiveEnvironmentNotDenied",
            "Blocker::BybitLiveExecutionNotProtected",
            "Blocker::IbkrContactPerformed",
            "Blocker::ConnectorRuntimeStarted",
            "Blocker::SecretContentSerialized",
            "Blocker::CommandMethodDenied",
            "Blocker::CommandMissing",
            "Blocker::CommandDuplicated",
        ),
    )
    _assert_ordered_tokens(
        validate_command_body,
        (
            "Blocker::CommandOperationMismatch",
            "Blocker::CommandAuthorityScopeMismatch",
            "Blocker::CommandEffectCapabilityMismatch",
            "Blocker::CommandRustOwnershipMismatch",
            "Blocker::CommandRequiredGateMissing",
            "Blocker::CommandRequestFieldMissing",
            "Blocker::CommandDenialReasonMissing",
        ),
    )


def test_stock_etf_lane_scoped_ipc_source_has_no_runtime_or_bybit_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS:
        if token in source:
            violations.append(f"{LANE_SCOPED_IPC}: contains forbidden token {token!r}")

    assert violations == []
