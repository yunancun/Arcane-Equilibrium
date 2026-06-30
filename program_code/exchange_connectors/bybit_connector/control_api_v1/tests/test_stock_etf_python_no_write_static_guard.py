"""
Stock/ETF IBKR Python no-write static guard.

This test locks the ADR-0048 boundary that Python may expose display/readiness
surfaces only at the current phase. It intentionally scans only Stock/ETF/IBKR
Python surfaces and future IBKR connector paths, not the existing Bybit modules.
"""

from __future__ import annotations

import ast
import re
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

ALLOWED_STOCK_ETF_STATUS_IPC_METHODS = {
    "stock_etf.get_account_status",
    "stock_etf.get_authorization_status",
    "stock_etf.get_data_foundation_status",
    "stock_etf.get_disable_cleanup_status",
    "stock_etf.get_evidence_status",
    "stock_etf.get_lane_status",
    "stock_etf.get_launch_status",
    "stock_etf.get_paper_status",
    "stock_etf.get_phase0_status",
    "stock_etf.get_policy_status",
    "stock_etf.get_readiness",
    "stock_etf.get_reconciliation_status",
    "stock_etf.get_release_packet_status",
    "stock_etf.get_scorecard_status",
    "stock_etf.get_shadow_status",
    "stock_etf.get_universe_status",
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
FORBIDDEN_PERSISTENCE_MODULE_PREFIXES = (
    "asyncpg",
    "boto3",
    "duckdb",
    "mysql",
    "pymongo",
    "psycopg",
    "psycopg2",
    "redis",
    "sqlalchemy",
    "sqlite3",
)
FORBIDDEN_LOCAL_PERSISTENCE_MODULES = {
    "agent_event_store",
    "agent_spine_client",
    "audit_persistence",
    "db_pool",
    "l2_call_ledger_writer",
    "openclaw_proposal_store",
    "state_store",
}
FORBIDDEN_SECRET_ENV_MODULE_PREFIXES = (
    "dotenv",
    "getpass",
    "keyring",
)
FORBIDDEN_RUNTIME_SIDE_EFFECT_MODULE_PREFIXES = (
    "asyncio",
    "concurrent",
    "datetime",
    "multiprocessing",
    "subprocess",
    "threading",
    "time",
)
FORBIDDEN_IBKR_CONNECTOR_RUNTIME_IMPORT_PREFIXES = (
    "broker_connectors.ibkr_connector",
    "ibkr_connector",
    "program_code.broker_connectors.ibkr_connector",
)
FORBIDDEN_SECRET_ENV_IMPORT_ROOTS = {"os"}
FORBIDDEN_SECRET_ENV_CALL_NAMES = {
    "getenv",
    "getpass",
    "load_dotenv",
}
FORBIDDEN_SECRET_FILE_READ_CALL_NAMES = {
    "expanduser",
    "open",
    "read_bytes",
    "read_text",
}
FORBIDDEN_FILE_WRITE_METHOD_NAMES = {
    "mkdir",
    "rename",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}
FORBIDDEN_RUNTIME_SIDE_EFFECT_CALL_NAMES = {
    "Thread",
    "Popen",
    "Process",
    "create_task",
    "fromtimestamp",
    "monotonic",
    "now",
    "perf_counter",
    "run",
    "sleep",
    "time",
    "to_thread",
    "utcnow",
}
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

STOCK_ETF_STATIC_GUI_FALLBACK_BUILDERS = {
    "accountFallback",
    "authorizationFallback",
    "evidenceFallback",
    "launchFallback",
    "paperFallback",
    "scorecardFallback",
    "shadowFallback",
    "universeFallback",
}

STOCK_ETF_STATIC_GUI_DATA_POLICY_RENDERERS = {
    "renderDataFoundationStatus",
    "renderPolicyStatus",
}

STOCK_ETF_STATIC_GUI_AUTH_ACCOUNT_RENDERERS = {
    "renderAccountStatus",
    "renderAuthorizationStatus",
}

STOCK_ETF_STATIC_GUI_EVIDENCE_PAPER_RENDERERS = {
    "renderEvidenceStatus",
    "renderPaperStatus",
    "renderShadowStatus",
    "renderUniverseStatus",
}

STOCK_ETF_STATIC_GUI_SCORECARD_LAUNCH_RENDERERS = {
    "renderLaunchStatus",
    "renderScorecardStatus",
}

STOCK_ETF_STATIC_GUI_READINESS_RENDERER = "renderReadiness"


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


def _candidate_stock_etf_control_api_python_files() -> list[Path]:
    app_dir = CONTROL_API_DIR / "app"
    files = {
        app_dir / "stock_etf_routes.py",
        app_dir / "asset_lane_routes.py",
        app_dir / "ibkr_paper_routes.py",
    }
    files.update(app_dir.glob("*stock_etf*.py"))
    files.update(app_dir.glob("*ibkr*.py"))
    return sorted(path for path in files if path.exists())


def _candidate_stock_etf_static_gui_files() -> list[Path]:
    static_dir = CONTROL_API_DIR / "app" / "static"
    files = {
        static_dir / "tab-stock-etf.html",
        static_dir / "tab-stock-etf-phase0.js",
        static_dir / "tab-stock-etf-release-packet.js",
        static_dir / "tab-stock-etf-disable-cleanup.js",
        static_dir / "tab-stock-etf-reconciliation.js",
        static_dir / "tab-stock-etf-readiness.js",
        static_dir / "tab-stock-etf-data-policy.js",
        static_dir / "tab-stock-etf-fallbacks.js",
        static_dir / "tab-stock-etf-auth-account.js",
        static_dir / "tab-stock-etf-evidence-paper.js",
        static_dir / "tab-stock-etf-scorecard-launch.js",
        static_dir / "tab-stock-etf.js",
    }
    return sorted(path for path in files if path.exists())


def _stock_etf_gui_lane_template_endpoints() -> set[str]:
    template_source = (
        SRV_ROOT / "settings" / "broker" / "stock_etf_gui_lane_contract.template.toml"
    ).read_text(encoding="utf-8")
    return set(
        re.findall(r'^[a-z0-9_]+_endpoint = "([^"]+)"', template_source, re.MULTILINE)
    )


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


def test_stock_etf_ibkr_python_surface_has_no_persistence_or_file_writers() -> None:
    files = _candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _record_forbidden_persistence_import(path, node, violations)
            elif isinstance(node, ast.Call):
                _record_forbidden_persistence_dynamic_import(path, node, violations)
                _record_forbidden_file_write_call(path, node, violations)

    assert violations == []


def test_stock_etf_ibkr_python_surface_has_no_secret_or_env_material_access() -> None:
    files = _candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _record_forbidden_secret_env_import(path, node, violations)
            elif isinstance(node, ast.Call):
                _record_forbidden_secret_env_call(path, node, violations)
            elif isinstance(node, (ast.Attribute, ast.Subscript)):
                _record_forbidden_os_environ_access(path, node, violations)

    assert violations == []


def test_stock_etf_ibkr_python_surface_has_no_clock_or_concurrency_side_effects() -> None:
    files = _candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _record_forbidden_runtime_side_effect_import(path, node, violations)
            elif isinstance(node, ast.Call):
                _record_forbidden_runtime_side_effect_dynamic_import(path, node, violations)
                _record_forbidden_runtime_side_effect_call(path, node, violations)

    assert violations == []


def test_stock_etf_control_api_surface_does_not_import_ibkr_connector_runtime_skeleton() -> None:
    files = _candidate_stock_etf_control_api_python_files()
    assert files, "expected Stock/ETF control-api Python surface files"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for module in _imported_module_names(node):
                    if _is_forbidden_module(
                        module, FORBIDDEN_IBKR_CONNECTOR_RUNTIME_IMPORT_PREFIXES
                    ):
                        violations.append(
                            f"{path}:{node.lineno}: imports connector runtime skeleton {module}"
                        )
            elif isinstance(node, ast.Call):
                module = _literal_dynamic_import_module(node)
                if module and _is_forbidden_module(
                    module, FORBIDDEN_IBKR_CONNECTOR_RUNTIME_IMPORT_PREFIXES
                ):
                    violations.append(
                        f"{path}:{node.lineno}: dynamically imports connector runtime skeleton {module}"
                    )

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


def test_stock_etf_routes_call_ipc_with_empty_params_only() -> None:
    path = CONTROL_API_DIR / "app" / "stock_etf_routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    ipc_calls: list[tuple[str, ast.Call]] = []
    violations: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "call":
                continue
            ipc_calls.append((function.name, node))
            params_keywords = [keyword for keyword in node.keywords if keyword.arg == "params"]
            if len(params_keywords) != 1 or not _is_empty_dict(params_keywords[0].value):
                violations.append(
                    f"{path}:{node.lineno}: Stock/ETF IPC call must use literal params={{}}"
                )
            if not node.args or not isinstance(node.args[0], ast.Name) or node.args[0].id != "method":
                violations.append(
                    f"{path}:{node.lineno}: Stock/ETF IPC call must use central method arg"
                )

    assert [function_name for function_name, _ in ipc_calls] == ["_query_stock_etf_status"]
    assert violations == []


def test_stock_etf_routes_call_only_readonly_status_ipc_methods() -> None:
    path = CONTROL_API_DIR / "app" / "stock_etf_routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    method_constants = _stock_etf_route_method_constants(tree)

    used_methods: set[str] = set()
    helper_call_count = 0
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) != "_query_stock_etf_status":
            continue
        helper_call_count += 1
        if len(node.args) != 2:
            violations.append(
                f"{path}:{node.lineno}: Stock/ETF route query helper must receive ipc and method"
            )
            continue
        if not isinstance(node.args[0], ast.Name) or node.args[0].id != "ipc":
            violations.append(
                f"{path}:{node.lineno}: Stock/ETF route query helper must receive local ipc"
            )
            continue
        if not isinstance(node.args[1], ast.Name):
            violations.append(
                f"{path}:{node.lineno}: Stock/ETF route query helper must use a named method constant"
            )
            continue
        constant_name = node.args[1].id
        method = method_constants.get(constant_name)
        if method is None:
            violations.append(
                f"{path}:{node.lineno}: Stock/ETF route query uses unknown method constant {constant_name}"
            )
            continue
        used_methods.add(method)
        if method not in ALLOWED_STOCK_ETF_STATUS_IPC_METHODS:
            violations.append(
                f"{path}:{node.lineno}: Stock/ETF route query method {method!r} is not readonly status"
            )

    assert helper_call_count == len(ALLOWED_STOCK_ETF_STATUS_IPC_METHODS)
    assert used_methods == ALLOWED_STOCK_ETF_STATUS_IPC_METHODS
    assert violations == []


def test_stock_etf_get_route_handlers_accept_only_response_and_authenticated_actor() -> None:
    path = CONTROL_API_DIR / "app" / "stock_etf_routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    route_count = 0
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_stock_etf_get_route_decorator(decorator) for decorator in node.decorator_list):
            continue
        route_count += 1
        arg_names = [arg.arg for arg in node.args.args]
        if not set(arg_names).issubset({"response", "actor"}):
            violations.append(
                f"{path}:{node.lineno}: {node.name}() accepts client-state args {arg_names!r}"
            )
        if node.args.vararg or node.args.kwarg or node.args.kwonlyargs:
            violations.append(
                f"{path}:{node.lineno}: {node.name}() uses variadic or keyword-only route args"
            )
        if "actor" not in arg_names:
            violations.append(f"{path}:{node.lineno}: {node.name}() lacks authenticated actor")
            continue
        actor_index = arg_names.index("actor")
        first_default_index = len(arg_names) - len(node.args.defaults)
        if actor_index < first_default_index:
            violations.append(f"{path}:{node.lineno}: {node.name}() actor lacks default Depends")
            continue
        actor_default = node.args.defaults[actor_index - first_default_index]
        if not _is_current_actor_dependency(actor_default):
            violations.append(
                f"{path}:{node.lineno}: {node.name}() actor is not Depends(base.current_actor)"
            )

    assert route_count == 17
    assert violations == []


def test_stock_etf_static_gui_endpoint_set_matches_gui_lane_contract_template() -> None:
    files = _candidate_stock_etf_static_gui_files()
    assert files, "expected Stock/ETF static GUI surface"

    combined_source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    gui_endpoints = set(
        re.findall(r"/api/v1/stock-etf(?:/[a-z0-9-]+)?", combined_source)
    )

    assert gui_endpoints == _stock_etf_gui_lane_template_endpoints()


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


def test_stock_etf_static_gui_files_stay_below_line_cap() -> None:
    files = _candidate_stock_etf_static_gui_files()
    assert files, "expected Stock/ETF static GUI surface"

    oversized = []
    for path in files:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > 2000:
            oversized.append(f"{path}:{line_count}")

    assert oversized == []


def test_stock_etf_static_gui_payload_builders_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    fallback_path = static_dir / "tab-stock-etf-fallbacks.js"
    main_source = main_path.read_text(encoding="utf-8")
    fallback_source = fallback_path.read_text(encoding="utf-8")

    missing_fallbacks = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_FALLBACK_BUILDERS)
        if f"function {name}(reason)" not in fallback_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_FALLBACK_BUILDERS)
        if f"function {name}(reason)" in main_source
    ]

    assert missing_fallbacks == []
    assert main_definitions == []
    assert len(main_source.splitlines()) <= 1400
    assert len(fallback_source.splitlines()) <= 800


def test_stock_etf_static_gui_data_policy_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    data_policy_path = static_dir / "tab-stock-etf-data-policy.js"
    main_source = main_path.read_text(encoding="utf-8")
    data_policy_source = data_policy_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_DATA_POLICY_RENDERERS)
        if f"function {name}(data)" not in data_policy_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_DATA_POLICY_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert len(main_source.splitlines()) <= 1100
    assert len(data_policy_source.splitlines()) <= 700


def test_stock_etf_static_gui_auth_account_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    auth_account_path = static_dir / "tab-stock-etf-auth-account.js"
    main_source = main_path.read_text(encoding="utf-8")
    auth_account_source = auth_account_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_AUTH_ACCOUNT_RENDERERS)
        if f"function {name}(data)" not in auth_account_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_AUTH_ACCOUNT_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert "window.renderAuthorizationStatus" in main_source
    assert "window.renderAccountStatus" in main_source
    assert len(main_source.splitlines()) <= 900
    assert len(auth_account_source.splitlines()) <= 400


def test_stock_etf_static_gui_evidence_paper_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    evidence_paper_path = static_dir / "tab-stock-etf-evidence-paper.js"
    main_source = main_path.read_text(encoding="utf-8")
    evidence_paper_source = evidence_paper_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_EVIDENCE_PAPER_RENDERERS)
        if f"function {name}(data)" not in evidence_paper_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_EVIDENCE_PAPER_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert "window.renderEvidenceStatus" in main_source
    assert "window.renderUniverseStatus" in main_source
    assert "window.renderShadowStatus" in main_source
    assert "window.renderPaperStatus" in main_source
    assert len(main_source.splitlines()) <= 650
    assert len(evidence_paper_source.splitlines()) <= 500


def test_stock_etf_static_gui_scorecard_launch_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    scorecard_launch_path = static_dir / "tab-stock-etf-scorecard-launch.js"
    main_source = main_path.read_text(encoding="utf-8")
    scorecard_launch_source = scorecard_launch_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_SCORECARD_LAUNCH_RENDERERS)
        if f"function {name}(data)" not in scorecard_launch_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_SCORECARD_LAUNCH_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert "window.renderScorecardStatus" in main_source
    assert "window.renderLaunchStatus" in main_source
    assert len(main_source.splitlines()) <= 400
    assert len(scorecard_launch_source.splitlines()) <= 500


def test_stock_etf_static_gui_readiness_renderer_remains_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    readiness_path = static_dir / "tab-stock-etf-readiness.js"
    main_source = main_path.read_text(encoding="utf-8")
    readiness_source = readiness_path.read_text(encoding="utf-8")

    readiness_definition = f"function {STOCK_ETF_STATIC_GUI_READINESS_RENDERER}(data, laneStatus)"
    assert readiness_definition in readiness_source
    assert readiness_definition not in main_source
    assert "window.renderReadiness" in main_source
    assert "function toneFor(value)" not in main_source
    assert "function kvRow(label, html)" not in main_source
    assert len(main_source.splitlines()) <= 250
    assert len(readiness_source.splitlines()) <= 250


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
    module = _literal_dynamic_import_module(node)
    if module is None:
        return
    if _is_forbidden_module(module, FORBIDDEN_BROKER_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden direct IBKR broker module {module}")
    if _is_forbidden_module(module, FORBIDDEN_NETWORK_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden network client module {module}")


def _record_forbidden_persistence_import(
    path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]
) -> None:
    for module in _imported_module_names(node):
        if _is_forbidden_module(module, FORBIDDEN_PERSISTENCE_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden persistence module {module}")
        if _is_forbidden_local_persistence_module(module):
            violations.append(f"{path}: imports forbidden local persistence module {module}")


def _record_forbidden_persistence_dynamic_import(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    module = _literal_dynamic_import_module(node)
    if module is None:
        return
    if _is_forbidden_module(module, FORBIDDEN_PERSISTENCE_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden persistence module {module}")
    if _is_forbidden_local_persistence_module(module):
        violations.append(f"{path}: dynamically imports forbidden local persistence module {module}")


def _record_forbidden_secret_env_import(
    path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]
) -> None:
    for module in _imported_module_names(node):
        if module.split(".", 1)[0] in FORBIDDEN_SECRET_ENV_IMPORT_ROOTS:
            violations.append(f"{path}: imports forbidden env/material module {module}")
        if _is_forbidden_module(module, FORBIDDEN_SECRET_ENV_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden secret helper module {module}")


def _record_forbidden_secret_env_call(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    call_name = _call_name(node.func)
    if call_name in FORBIDDEN_SECRET_ENV_CALL_NAMES:
        violations.append(f"{path}: calls forbidden secret/env accessor {call_name}()")
    if call_name in FORBIDDEN_SECRET_FILE_READ_CALL_NAMES:
        violations.append(f"{path}: calls forbidden secret/file material reader {call_name}()")
    if _is_os_environ_access(node.func):
        violations.append(f"{path}: accesses forbidden os.environ material")
    if _is_path_home_call(node.func):
        violations.append(f"{path}: calls forbidden Path.home() material locator")


def _record_forbidden_runtime_side_effect_import(
    path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]
) -> None:
    for module in _imported_module_names(node):
        if _is_forbidden_module(module, FORBIDDEN_RUNTIME_SIDE_EFFECT_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden runtime side-effect module {module}")


def _record_forbidden_runtime_side_effect_dynamic_import(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    module = _literal_dynamic_import_module(node)
    if module is None:
        return
    if _is_forbidden_module(module, FORBIDDEN_RUNTIME_SIDE_EFFECT_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden runtime side-effect module {module}")


def _record_forbidden_runtime_side_effect_call(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    call_name = _call_name(node.func)
    if call_name in FORBIDDEN_RUNTIME_SIDE_EFFECT_CALL_NAMES:
        violations.append(f"{path}: calls forbidden runtime side-effect function {call_name}()")


def _record_forbidden_os_environ_access(
    path: Path, node: ast.Attribute | ast.Subscript, violations: list[str]
) -> None:
    if _is_os_environ_access(node):
        violations.append(f"{path}: accesses forbidden os.environ material")


def _record_forbidden_file_write_call(path: Path, node: ast.Call, violations: list[str]) -> None:
    call_name = _call_name(node.func)
    if call_name in FORBIDDEN_FILE_WRITE_METHOD_NAMES:
        violations.append(f"{path}: calls forbidden file writer {call_name}()")
        return
    if call_name == "open" and _open_call_uses_write_mode(node):
        violations.append(f"{path}: opens a file in write/append/create mode")
        return
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "replace"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    ):
        violations.append(f"{path}: calls forbidden file writer os.replace()")


def _is_forbidden_module(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _is_forbidden_local_persistence_module(module: str) -> bool:
    return module.split(".", 1)[0] in FORBIDDEN_LOCAL_PERSISTENCE_MODULES


def _literal_dynamic_import_module(node: ast.Call) -> str | None:
    call_name = _call_name(node.func)
    if call_name not in {"__import__", "import_module", "importlib.import_module"}:
        return None
    if not node.args:
        return None
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
        return None
    return first_arg.value


def _is_os_environ_access(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        if (
            node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            return True
        return _is_os_environ_access(node.value)
    if isinstance(node, ast.Subscript):
        return _is_os_environ_access(node.value)
    return False


def _is_path_home_call(func: ast.expr) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "home"
        and isinstance(func.value, ast.Name)
        and func.value.id == "Path"
    )


def _imported_module_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    module_names: list[str] = []
    if isinstance(node, ast.Import):
        module_names.extend(alias.name for alias in node.names)
    elif node.module:
        module_names.append(node.module)
        module_names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return module_names


def _open_call_uses_write_mode(node: ast.Call) -> bool:
    mode: str | None = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        if isinstance(node.args[1].value, str):
            mode = node.args[1].value
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                mode = keyword.value.value
    return mode is not None and any(flag in mode for flag in ("w", "a", "x", "+"))


def _decorated_http_method(decorator: ast.expr) -> str | None:
    if isinstance(decorator, ast.Call):
        return _call_name(decorator.func)
    return _call_name(decorator)


def _is_empty_dict(value: ast.expr) -> bool:
    return isinstance(value, ast.Dict) and value.keys == [] and value.values == []


def _stock_etf_route_method_constants(tree: ast.AST) -> dict[str, str]:
    method_constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if not name.endswith("_METHOD"):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            method_constants[name] = node.value.value
    return method_constants


def _is_stock_etf_get_route_decorator(decorator: ast.expr) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id == "stock_etf_router"
    )


def _is_current_actor_dependency(value: ast.expr) -> bool:
    if not isinstance(value, ast.Call):
        return False
    if _call_name(value.func) != "Depends" or len(value.args) != 1:
        return False
    dependency = value.args[0]
    return (
        isinstance(dependency, ast.Attribute)
        and dependency.attr == "current_actor"
        and isinstance(dependency.value, ast.Name)
        and dependency.value.id == "base"
    )


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
