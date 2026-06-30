import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HANDLER_ROOT = ROOT / "rust/openclaw_engine/src/ipc_server/handlers"
STOCK_ETF_HANDLER = HANDLER_ROOT / "stock_etf.rs"
STOCK_ETF_SPLIT_DIR = HANDLER_ROOT / "stock_etf"
STATUS_SUMMARIES = STOCK_ETF_SPLIT_DIR / "status_summaries.rs"
MAX_LINES = 2000


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_stock_etf_ipc_handler_files_stay_below_governance_cap() -> None:
    parent = STOCK_ETF_HANDLER.read_text(encoding="utf-8")
    modules = {
        path.name: _loc(path)
        for path in STOCK_ETF_SPLIT_DIR.glob("*.rs")
    }

    assert "mod status_summaries;" in parent
    assert "status_summaries.rs" in modules
    assert _loc(STOCK_ETF_HANDLER) <= MAX_LINES
    assert all(loc <= MAX_LINES for loc in modules.values())


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
