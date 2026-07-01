from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANE_SCOPED_IPC = ROOT / "rust/openclaw_types/src/stock_etf_lane_scoped_ipc.rs"
MAX_LINES = 800
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


def test_stock_etf_lane_scoped_ipc_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_lane_scoped_ipc_source_keeps_method_matrix() -> None:
    source = _source()

    assert "const REQUIRED_METHODS" in source
    assert "pub enum StockEtfLaneScopedIpcMethod" in source
    assert "fn expected_method(" in source
    assert len(REQUIRED_METHOD_VARIANTS) == 20
    for variant in REQUIRED_METHOD_VARIANTS:
        assert f"StockEtfLaneScopedIpcMethod::{variant}" in source
        assert f"Method::{variant}" in source
    for variant in DENIED_METHOD_VARIANTS:
        assert variant in source
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source


def test_stock_etf_lane_scoped_ipc_source_has_no_runtime_or_bybit_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS:
        if token in source:
            violations.append(f"{LANE_SCOPED_IPC}: contains forbidden token {token!r}")

    assert violations == []
