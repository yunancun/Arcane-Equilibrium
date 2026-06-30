"""
Stock/ETF IBKR Python no-write static guard.

This test locks the ADR-0048 boundary that Python may expose display/readiness
surfaces only at the current phase. It intentionally scans only Stock/ETF/IBKR
Python surfaces and future IBKR connector paths, not the existing Bybit modules.
"""

from __future__ import annotations

import ast
from pathlib import Path


CONTROL_API_DIR = Path(__file__).resolve().parents[1]
SRV_ROOT = Path(__file__).resolve().parents[5]

FORBIDDEN_FUNCTION_NAMES = {
    "place_order",
    "submit_order",
    "submit_paper_order",
    "cancel_order",
    "cancel_all_orders",
    "cancel_paper_order",
    "replace_order",
    "replace_paper_order",
    "modify_order",
    "create_order",
}

FORBIDDEN_IPC_METHOD_STRINGS = {
    "stock_etf.submit_paper_order",
    "stock_etf.cancel_paper_order",
    "stock_etf.replace_paper_order",
    "ibkr.place_order",
    "ibkr.submit_order",
    "ibkr.cancel_order",
    "ibkr.replace_order",
}

FORBIDDEN_HTTP_ROUTE_METHODS = {"post", "put", "patch", "delete"}
FORBIDDEN_BROKER_MODULE_PREFIXES = ("ibapi", "ib_insync")
FORBIDDEN_NETWORK_MODULE_PREFIXES = (
    "aiohttp",
    "http.client",
    "httpx",
    "requests",
    "socket",
    "urllib",
    "urllib3",
    "websocket",
    "websockets",
)
FORBIDDEN_STATIC_GUI_SNIPPETS = {
    "ocPost(",
    "fetch(",
    "method: 'POST'",
    'method: "POST"',
    "method:'POST'",
    'method:"POST"',
    "method: 'PUT'",
    'method: "PUT"',
    "method: 'PATCH'",
    'method: "PATCH"',
    "method: 'DELETE'",
    'method: "DELETE"',
    "<form",
    "localStorage",
    "sessionStorage",
    "ibkr.place_order",
    "ibkr.submit_order",
    "ibkr.cancel_order",
    "ibkr.replace_order",
}


def _candidate_stock_etf_ibkr_python_files() -> list[Path]:
    app_dir = CONTROL_API_DIR / "app"
    files = {
        app_dir / "stock_etf_routes.py",
        app_dir / "asset_lane_routes.py",
        app_dir / "ibkr_paper_routes.py",
    }
    files.update(app_dir.glob("*stock_etf*.py"))
    files.update(app_dir.glob("*ibkr*.py"))

    ibkr_connector_dir = SRV_ROOT / "program_code" / "broker_connectors" / "ibkr_connector"
    if ibkr_connector_dir.exists():
        files.update(ibkr_connector_dir.rglob("*.py"))

    return sorted(path for path in files if path.exists())


def _candidate_stock_etf_static_gui_files() -> list[Path]:
    static_dir = CONTROL_API_DIR / "app" / "static"
    files = {
        static_dir / "tab-stock-etf.html",
        static_dir / "tab-stock-etf-phase0.js",
        static_dir / "tab-stock-etf-release-packet.js",
        static_dir / "tab-stock-etf-disable-cleanup.js",
        static_dir / "tab-stock-etf-reconciliation.js",
        static_dir / "tab-stock-etf.js",
    }
    return sorted(path for path in files if path.exists())


def test_stock_etf_ibkr_python_surface_has_no_direct_broker_write_api() -> None:
    files = _candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in FORBIDDEN_FUNCTION_NAMES:
                    violations.append(f"{path}: function defines forbidden broker write {node.name}()")
            elif isinstance(node, ast.Call):
                _record_forbidden_call(path, node, violations)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                _record_forbidden_import(path, node, violations)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in FORBIDDEN_IPC_METHOD_STRINGS:
                    violations.append(f"{path}: string exposes forbidden IPC method {node.value!r}")

    assert violations == []


def test_stock_etf_ibkr_python_surface_has_no_network_client_imports() -> None:
    files = _candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _record_forbidden_import(path, node, violations)
            elif isinstance(node, ast.Call):
                _record_forbidden_dynamic_import(path, node, violations)

    assert violations == []


def test_stock_etf_ibkr_python_routes_remain_get_only_until_rust_authority_contract_changes() -> None:
    violations: list[str] = []
    for path in _candidate_stock_etf_ibkr_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    route_method = _decorated_http_method(decorator)
                    if route_method in FORBIDDEN_HTTP_ROUTE_METHODS:
                        violations.append(
                            f"{path}: {node.name}() exposes forbidden @{route_method} route"
                        )

    assert violations == []


def test_stock_etf_static_gui_surface_remains_display_only() -> None:
    files = _candidate_stock_etf_static_gui_files()
    assert files, "expected Stock/ETF static GUI surface"

    violations: list[str] = []
    forbidden_snippets = FORBIDDEN_STATIC_GUI_SNIPPETS | FORBIDDEN_IPC_METHOD_STRINGS
    sources = {path: path.read_text(encoding="utf-8") for path in files}
    combined_source = "\n".join(sources.values())
    endpoint_requirements = {
        "/api/v1/stock-etf/account-status": "account-status",
        "/api/v1/stock-etf/authorization-status": "authorization-status",
        "/api/v1/stock-etf/data-foundation-status": "data-foundation-status",
        "/api/v1/stock-etf/disable-cleanup-status": "disable-cleanup-status",
        "/api/v1/stock-etf/evidence-status": "evidence-status",
        "/api/v1/stock-etf/lane-status": "lane-status",
        "/api/v1/stock-etf/launch-status": "launch-status",
        "/api/v1/stock-etf/paper-status": "paper-status",
        "/api/v1/stock-etf/phase0-status": "phase0-status",
        "/api/v1/stock-etf/policy-status": "policy-status",
        "/api/v1/stock-etf/readiness": "readiness",
        "/api/v1/stock-etf/reconciliation-status": "reconciliation-status",
        "/api/v1/stock-etf/release-packet-status": "release-packet-status",
        "/api/v1/stock-etf/scorecard-status": "scorecard-status",
        "/api/v1/stock-etf/shadow-status": "shadow-status",
        "/api/v1/stock-etf/universe-status": "universe-status",
    }
    for endpoint, label in endpoint_requirements.items():
        if endpoint not in combined_source:
            violations.append(
                f"Stock/ETF static GUI bundle: missing read-only Stock/ETF {label} endpoint"
            )
    for path in files:
        source = sources[path]
        for snippet in sorted(forbidden_snippets):
            if snippet in source:
                violations.append(f"{path}: contains forbidden display-only snippet {snippet!r}")

    assert violations == []


def _record_forbidden_call(path: Path, node: ast.Call, violations: list[str]) -> None:
    name = _call_name(node.func)
    if name in FORBIDDEN_FUNCTION_NAMES:
        violations.append(f"{path}: calls forbidden broker write {name}()")


def _record_forbidden_import(path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]) -> None:
    module_names: list[str] = []
    if isinstance(node, ast.Import):
        module_names.extend(alias.name for alias in node.names)
    elif node.module:
        module_names.append(node.module)
        module_names.extend(f"{node.module}.{alias.name}" for alias in node.names)

    for module in module_names:
        if _is_forbidden_module(module, FORBIDDEN_BROKER_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden direct IBKR broker module {module}")
        if _is_forbidden_module(module, FORBIDDEN_NETWORK_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden network client module {module}")


def _record_forbidden_dynamic_import(path: Path, node: ast.Call, violations: list[str]) -> None:
    call_name = _call_name(node.func)
    if call_name not in {"__import__", "import_module"} or not node.args:
        return
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
        return
    module = first_arg.value
    if _is_forbidden_module(module, FORBIDDEN_BROKER_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden direct IBKR broker module {module}")
    if _is_forbidden_module(module, FORBIDDEN_NETWORK_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden network client module {module}")


def _is_forbidden_module(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _decorated_http_method(decorator: ast.expr) -> str | None:
    if isinstance(decorator, ast.Call):
        return _call_name(decorator.func)
    return _call_name(decorator)


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
