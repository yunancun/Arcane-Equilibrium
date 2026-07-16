import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = (
    ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/tests"
)
LEGACY_FIXTURE_FILE = TEST_ROOT / "stock_etf_route_fixtures.py"
FIXTURE_PACKAGE = TEST_ROOT / "stock_etf_route_fixtures"
MAX_LINES = 800


EXPECTED_MODULES = {
    "__init__.py",
    "app.py",
    "phase2_payloads.py",
    "phase3_payloads.py",
    "phase5_payloads.py",
}

EXPECTED_EXPORTS = {
    # 2026-07-03 同步 commit 929593791（expose stock ETF allowlist action buckets）：
    # phase2_payloads.py 新增三個靜態 allowlist list 常量並經 __init__ 再導出；
    # 已驗證為 source-only（下方 payload source-only 測試持續覆蓋 phase2_payloads.py）。
    "API_ALLOWLIST_DENIED_ACTIONS",
    "API_ALLOWLIST_PAPER_WRITE_ACTIONS",
    "API_ALLOWLIST_READ_ACTIONS",
    "STATIC_DIR",
    "_make_authless_client",
    "_make_client_with_ipc",
    "client_fail_closed",
    "route_module",
    "stock_etf_router",
    "_valid_account_status",
    "_valid_api_allowlist",
    "_valid_authorization_status",
    "_valid_connection_health",
    "_valid_data_foundation_status",
    "_valid_disable_cleanup_status",
    "_valid_evidence_status",
    "_valid_lane_status",
    "_valid_launch_status",
    "_valid_paper_status",
    "_valid_phase0_status",
    "_valid_policy_status",
    "_valid_reconciliation_status",
    "_valid_release_packet_status",
    "_valid_scorecard_status",
    "_valid_shadow_status",
    "_valid_universe_status",
}


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_stock_etf_route_fixtures_are_split_under_review_threshold() -> None:
    modules = {
        path.name: _loc(path)
        for path in FIXTURE_PACKAGE.glob("*.py")
    }

    assert not LEGACY_FIXTURE_FILE.exists()
    assert set(modules) == EXPECTED_MODULES
    assert all(loc <= MAX_LINES for loc in modules.values())


def test_stock_etf_route_fixture_package_preserves_import_surface() -> None:
    source = (FIXTURE_PACKAGE / "__init__.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    all_assign = next(
        node
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    )
    exports = {
        item.value
        for item in all_assign.value.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }

    assert exports == EXPECTED_EXPORTS


def test_stock_etf_route_payload_fixtures_stay_source_only() -> None:
    forbidden_import_roots = {
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "websocket",
        "websockets",
    }
    for path in (
        FIXTURE_PACKAGE / "phase2_payloads.py",
        FIXTURE_PACKAGE / "phase3_payloads.py",
        FIXTURE_PACKAGE / "phase5_payloads.py",
    ):
        source = path.read_text(encoding="utf-8")
        module = ast.parse(source)
        imports = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_import_roots)
        for forbidden in (
            "ib_insync",
            "ibapi",
            "IBApi",
            "TcpStream",
            "tokio::net",
            "write_text",
            "write_bytes",
        ):
            assert forbidden not in source
