from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IPC_TEST_ROOT = ROOT / "rust/openclaw_engine/src/ipc_server/tests"
STOCK_ETF_PARENT = IPC_TEST_ROOT / "stock_etf.rs"
STOCK_ETF_SPLIT_DIR = IPC_TEST_ROOT / "stock_etf"
MAX_LINES = 1200
EXPECTED_MODULES = {"request_contracts.rs", "status_fixtures.rs"}


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
