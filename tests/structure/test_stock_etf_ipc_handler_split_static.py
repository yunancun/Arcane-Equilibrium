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
