from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
TYPE_SOURCE_ROOT = ROOT / "rust/openclaw_types/src"
ENGINE_HANDLER_ROOT = ROOT / "rust/openclaw_engine/src/ipc_server/handlers"
TEST_SOURCE_PATTERNS = (
    "tests/structure/**/*.py",
    "rust/openclaw_types/tests/**/*.rs",
    "rust/openclaw_engine/src/ipc_server/tests/**/*.rs",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/tests/**/*.py",
)


def _stock_etf_ibkr_rust_sources() -> list[Path]:
    files = []
    files.extend(
        path
        for path in TYPE_SOURCE_ROOT.rglob("*.rs")
        if "ibkr" in path.as_posix() or "stock_etf" in path.as_posix()
    )
    files.append(ENGINE_HANDLER_ROOT / "stock_etf.rs")
    files.extend((ENGINE_HANDLER_ROOT / "stock_etf").rglob("*.rs"))
    return sorted(set(path for path in files if path.exists()))


def _test_source_text() -> str:
    chunks = []
    for pattern in TEST_SOURCE_PATTERNS:
        for path in ROOT.glob(pattern):
            if path.resolve() == THIS_FILE:
                continue
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_stock_etf_rust_source_coverage_scan_scope_is_exact() -> None:
    rels = {path.relative_to(ROOT).as_posix() for path in _stock_etf_ibkr_rust_sources()}

    assert "rust/openclaw_types/src/ibkr_phase2_gate.rs" in rels
    assert "rust/openclaw_types/src/stock_etf_paper_order_request/fixtures.rs" in rels
    assert "rust/openclaw_types/src/stock_etf_phase3_evidence/market_data.rs" in rels
    assert (
        "rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries/scorecard.rs"
        in rels
    )
    assert "rust/openclaw_engine/src/bybit_rest_client.rs" not in rels
    assert "rust/openclaw_engine/src/order_manager.rs" not in rels
    assert "rust/openclaw_engine/src/bounded_probe_active_order.rs" not in rels


def test_stock_etf_rust_source_coverage_includes_nested_child_modules() -> None:
    names = {path.name for path in _stock_etf_ibkr_rust_sources()}

    assert "validation.rs" in names
    assert "market_data.rs" in names
    assert "components.rs" in names
    assert "bundle.rs" in names
    assert "precontact.rs" in names
    assert "request_summaries.rs" in names
    assert "status_summaries.rs" in names
    assert "scorecard.rs" in names


def test_stock_etf_rust_sources_are_directly_referenced_by_tests() -> None:
    source = _test_source_text()
    uncovered = []

    for path in _stock_etf_ibkr_rust_sources():
        rel = path.relative_to(ROOT).as_posix()
        if rel not in source and path.name not in source:
            uncovered.append(rel)

    assert uncovered == []
