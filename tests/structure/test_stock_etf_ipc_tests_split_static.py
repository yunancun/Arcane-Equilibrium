from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IPC_TEST_ROOT = ROOT / "rust/openclaw_engine/src/ipc_server/tests"
STOCK_ETF_PARENT = IPC_TEST_ROOT / "stock_etf.rs"
STOCK_ETF_SPLIT_DIR = IPC_TEST_ROOT / "stock_etf"
MAX_LINES = 1200
EXPECTED_MODULES = {"request_contracts.rs", "status_fixtures.rs"}
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


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_stock_etf_ipc_fixture_tests_are_split_under_governance_cap() -> None:
    parent = STOCK_ETF_PARENT.read_text(encoding="utf-8")
    modules = {
        path.name: _loc(path)
        for path in STOCK_ETF_SPLIT_DIR.glob("*.rs")
    }

    assert "mod request_contracts;" in parent
    assert "mod status_fixtures;" in parent
    assert set(modules) == EXPECTED_MODULES
    assert _loc(STOCK_ETF_PARENT) <= MAX_LINES
    assert all(loc <= MAX_LINES for loc in modules.values())


def test_stock_etf_ipc_fixture_tests_have_no_runtime_material_readers() -> None:
    sources = {
        STOCK_ETF_PARENT: STOCK_ETF_PARENT.read_text(encoding="utf-8"),
        STOCK_ETF_SPLIT_DIR / "request_contracts.rs": (
            STOCK_ETF_SPLIT_DIR / "request_contracts.rs"
        ).read_text(encoding="utf-8"),
        STOCK_ETF_SPLIT_DIR / "status_fixtures.rs": (
            STOCK_ETF_SPLIT_DIR / "status_fixtures.rs"
        ).read_text(encoding="utf-8"),
    }

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_RUNTIME_MATERIAL_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden runtime material token {token!r}")

    assert violations == []


def test_stock_etf_ipc_fixture_tests_do_not_import_or_call_bybit_runtime_paths() -> None:
    sources = {
        STOCK_ETF_PARENT: STOCK_ETF_PARENT.read_text(encoding="utf-8"),
        STOCK_ETF_SPLIT_DIR / "request_contracts.rs": (
            STOCK_ETF_SPLIT_DIR / "request_contracts.rs"
        ).read_text(encoding="utf-8"),
        STOCK_ETF_SPLIT_DIR / "status_fixtures.rs": (
            STOCK_ETF_SPLIT_DIR / "status_fixtures.rs"
        ).read_text(encoding="utf-8"),
    }

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_BYBIT_RUNTIME_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden Bybit runtime token {token!r}")

    assert violations == []


def test_stock_etf_request_contract_fixtures_remain_source_only_tests() -> None:
    source = (STOCK_ETF_SPLIT_DIR / "request_contracts.rs").read_text(encoding="utf-8")

    for method in (
        "stock_etf.submit_paper_order",
        "stock_etf.preview_paper_order",
        "stock_etf.cancel_paper_order",
        "stock_etf.import_paper_fills",
        "stock_etf.evaluate_shadow_signal",
        "stock_etf.preview_readonly_probe",
        "submit_paper_order",
    ):
        assert method in source

    for forbidden in (
        "ib_insync",
        "ibapi",
        "IBApi",
        "TcpStream",
        "tokio::net",
        "reqwest",
    ):
        assert forbidden not in source


def test_stock_etf_tail_status_fixtures_remain_source_only_tests() -> None:
    source = (STOCK_ETF_SPLIT_DIR / "status_fixtures.rs").read_text(encoding="utf-8")

    for method in (
        "stock_etf.get_account_status",
        "stock_etf.get_reconciliation_status",
        "stock_etf.get_scorecard_status",
        "stock_etf.get_launch_status",
        "stock_etf.get_release_packet_status",
        "stock_etf.get_disable_cleanup_status",
    ):
        assert method in source

    for forbidden in (
        "ib_insync",
        "ibapi",
        "IBApi",
        "TcpStream",
        "tokio::net",
        "reqwest",
    ):
        assert forbidden not in source
