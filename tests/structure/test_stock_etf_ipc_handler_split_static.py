import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HANDLER_ROOT = ROOT / "rust/openclaw_engine/src/ipc_server/handlers"
STOCK_ETF_HANDLER = HANDLER_ROOT / "stock_etf.rs"
STOCK_ETF_SPLIT_DIR = HANDLER_ROOT / "stock_etf"
REQUEST_SUMMARIES = STOCK_ETF_SPLIT_DIR / "request_summaries.rs"
STATUS_SUMMARIES = STOCK_ETF_SPLIT_DIR / "status_summaries.rs"
MAX_LINES = 1200
EXPECTED_MODULES = {"request_summaries.rs", "status_summaries.rs"}
FORBIDDEN_RUNTIME_MATERIAL_TOKENS = (
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
    "read_exact",
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
)
FORBIDDEN_BYBIT_RUNTIME_TOKENS = (
    "crate::bybit_",
    "openclaw_engine::bybit_",
    "crate::bybit_rest_client",
    "crate::bybit_private_ws",
    "crate::bybit_private_ws_status_writer",
    "crate::bybit_earn_client",
    "openclaw_engine::bybit_rest_client",
    "openclaw_engine::bybit_private_ws",
    "openclaw_engine::bybit_private_ws_status_writer",
    "openclaw_engine::bybit_earn_client",
    "bybit_rest_client::",
    "bybit_private_ws::",
    "bybit_private_ws_status_writer::",
    "bybit_earn_client::",
    "BybitRestClient",
    "BybitPrivateWs",
    "BybitEnvironment",
    "BybitApiError",
    "BybitResult",
    "BybitEarn",
    "crate::order_manager",
    "openclaw_engine::order_manager",
    "order_manager::",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    "crate::order_router",
    "openclaw_engine::order_router",
    "order_router::",
    "crate::paper_state",
    "openclaw_engine::paper_state",
    "paper_state::",
    "crate::bounded_probe_active_order",
    "openclaw_engine::bounded_probe_active_order",
    "crate::platform_client",
    "openclaw_engine::platform_client",
    "platform_client::",
    "PlatformClient",
    "crate::event_consumer",
    "openclaw_engine::event_consumer",
    "event_consumer::",
    "crate::execution_listener",
    "openclaw_engine::execution_listener",
    "execution_listener::",
    "crate::database::rest_poller",
    "openclaw_engine::database::rest_poller",
    "RestPoller",
    "handle_submit_paper_order",
    ".place_order(",
    ".cancel_order(",
    ".cancel_order_by_link_id(",
    ".submit_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)
FORBIDDEN_RUNTIME_SIDE_EFFECT_TOKENS = (
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
)


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_stock_etf_ipc_handler_files_stay_below_governance_cap() -> None:
    parent = STOCK_ETF_HANDLER.read_text(encoding="utf-8")
    modules = {
        path.name: _loc(path)
        for path in STOCK_ETF_SPLIT_DIR.glob("*.rs")
    }

    assert "mod request_summaries;" in parent
    assert "mod status_summaries;" in parent
    assert set(modules) == EXPECTED_MODULES
    assert _loc(STOCK_ETF_HANDLER) <= MAX_LINES
    assert all(loc <= MAX_LINES for loc in modules.values())


def test_stock_etf_ipc_handler_files_have_no_runtime_material_readers() -> None:
    sources = {
        STOCK_ETF_HANDLER: STOCK_ETF_HANDLER.read_text(encoding="utf-8"),
        REQUEST_SUMMARIES: REQUEST_SUMMARIES.read_text(encoding="utf-8"),
        STATUS_SUMMARIES: STATUS_SUMMARIES.read_text(encoding="utf-8"),
    }

    assert sources[STOCK_ETF_HANDLER].count("StockEtfFeatureFlags::from_env()") == 1

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_RUNTIME_MATERIAL_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden runtime material token {token!r}")

    assert violations == []


def test_stock_etf_ipc_handler_files_do_not_import_or_call_bybit_runtime_paths() -> None:
    sources = {
        STOCK_ETF_HANDLER: STOCK_ETF_HANDLER.read_text(encoding="utf-8"),
        REQUEST_SUMMARIES: REQUEST_SUMMARIES.read_text(encoding="utf-8"),
        STATUS_SUMMARIES: STATUS_SUMMARIES.read_text(encoding="utf-8"),
    }

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_BYBIT_RUNTIME_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden Bybit runtime token {token!r}")

    assert violations == []


def test_stock_etf_ipc_handler_files_have_no_clock_thread_or_process_side_effects() -> None:
    sources = {
        STOCK_ETF_HANDLER: STOCK_ETF_HANDLER.read_text(encoding="utf-8"),
        REQUEST_SUMMARIES: REQUEST_SUMMARIES.read_text(encoding="utf-8"),
        STATUS_SUMMARIES: STATUS_SUMMARIES.read_text(encoding="utf-8"),
    }

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_RUNTIME_SIDE_EFFECT_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden runtime side-effect token {token!r}")

    assert violations == []


def test_stock_etf_request_summary_helpers_are_in_child_module() -> None:
    parent = STOCK_ETF_HANDLER.read_text(encoding="utf-8")
    child = REQUEST_SUMMARIES.read_text(encoding="utf-8")

    for name in (
        "operation_for_method_and_params",
        "request_from_params",
        "paper_request_envelope_summary",
        "fill_import_request_summary",
        "shadow_signal_request_summary",
        "readonly_probe_request_ipc_summary",
    ):
        assert re.search(re.escape(f"pub(super) fn {name}("), child)
        assert not re.search(rf"^{re.escape(f'fn {name}(')}", parent, re.MULTILINE)

    for method in (
        "stock_etf.preview_paper_order",
        "stock_etf.submit_paper_order",
        "stock_etf.cancel_paper_order",
        "stock_etf.replace_paper_order",
        "stock_etf.import_paper_fills",
        "stock_etf.evaluate_shadow_signal",
        "stock_etf.preview_readonly_probe",
    ):
        assert method in child

    for forbidden in (
        "ib_insync",
        "ibapi",
        "IBApi",
        "TcpStream",
        "tokio::net",
        "reqwest",
        "hyper::",
        "ureq",
    ):
        assert forbidden not in child


def test_stock_etf_status_summary_builders_are_in_child_module() -> None:
    parent = STOCK_ETF_HANDLER.read_text(encoding="utf-8")
    child = STATUS_SUMMARIES.read_text(encoding="utf-8")

    for name in (
        "account_status_summary",
        "reconciliation_status_summary",
        "scorecard_status_summary",
        "launch_status_summary",
        "disable_cleanup_status_summary",
        "release_packet_status_summary",
        "paper_status_summary",
        "shadow_status_summary",
        "universe_status_summary",
        "evidence_status_summary",
    ):
        assert re.search(re.escape(f"pub(super) fn {name}("), child)
        assert not re.search(rf"^{re.escape(f'fn {name}(')}", parent, re.MULTILINE)

    for forbidden in (
        "ib_insync",
        "ibapi",
        "IBApi",
        "TcpStream",
        "tokio::net",
        "reqwest",
        "hyper::",
        "ureq",
    ):
        assert forbidden not in child
