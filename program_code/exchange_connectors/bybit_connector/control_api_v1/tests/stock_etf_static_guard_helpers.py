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
FORBIDDEN_STATIC_GUI_BACKGROUND_SNIPPETS = {
    "BroadcastChannel(",
    "Date.now(",
    "EventSource(",
    "WebSocket(",
    "XMLHttpRequest",
    "cancelAnimationFrame(",
    "navigator.sendBeacon",
    "new SharedWorker(",
    "new Worker(",
    "performance.now(",
    "requestAnimationFrame(",
    "requestIdleCallback(",
    "setInterval(",
    "setTimeout(",
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
STOCK_ETF_STATIC_GUI_ONE_SHOT_GET_FANOUT = 16
STOCK_ETF_STATIC_GUI_TIMEOUT_MS = 5000


def candidate_stock_etf_ibkr_python_files() -> list[Path]:
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


def candidate_stock_etf_control_api_python_files() -> list[Path]:
    app_dir = CONTROL_API_DIR / "app"
    files = {
        app_dir / "stock_etf_routes.py",
        app_dir / "asset_lane_routes.py",
        app_dir / "ibkr_paper_routes.py",
    }
    files.update(app_dir.glob("*stock_etf*.py"))
    files.update(app_dir.glob("*ibkr*.py"))
    return sorted(path for path in files if path.exists())


def candidate_stock_etf_static_gui_files() -> list[Path]:
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


def stock_etf_gui_lane_template_endpoints() -> set[str]:
    template_source = (
        SRV_ROOT / "settings" / "broker" / "stock_etf_gui_lane_contract.template.toml"
    ).read_text(encoding="utf-8")
    return set(
        re.findall(r'^[a-z0-9_]+_endpoint = "([^"]+)"', template_source, re.MULTILINE)
    )


def record_forbidden_call(path: Path, node: ast.Call, violations: list[str]) -> None:
    name = call_name(node.func)
    if name in FORBIDDEN_FUNCTION_NAMES:
        violations.append(f"{path}: calls forbidden broker write {name}()")


def record_forbidden_import(path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]) -> None:
    module_names: list[str] = []
    if isinstance(node, ast.Import):
        module_names.extend(alias.name for alias in node.names)
    elif node.module:
        module_names.append(node.module)
        module_names.extend(f"{node.module}.{alias.name}" for alias in node.names)

    for module in module_names:
        if is_forbidden_module(module, FORBIDDEN_BROKER_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden direct IBKR broker module {module}")
        if is_forbidden_module(module, FORBIDDEN_NETWORK_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden network client module {module}")


def record_forbidden_dynamic_import(path: Path, node: ast.Call, violations: list[str]) -> None:
    module = literal_dynamic_import_module(node)
    if module is None:
        return
    if is_forbidden_module(module, FORBIDDEN_BROKER_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden direct IBKR broker module {module}")
    if is_forbidden_module(module, FORBIDDEN_NETWORK_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden network client module {module}")


def record_forbidden_persistence_import(
    path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]
) -> None:
    for module in imported_module_names(node):
        if is_forbidden_module(module, FORBIDDEN_PERSISTENCE_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden persistence module {module}")
        if is_forbidden_local_persistence_module(module):
            violations.append(f"{path}: imports forbidden local persistence module {module}")


def record_forbidden_persistence_dynamic_import(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    module = literal_dynamic_import_module(node)
    if module is None:
        return
    if is_forbidden_module(module, FORBIDDEN_PERSISTENCE_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden persistence module {module}")
    if is_forbidden_local_persistence_module(module):
        violations.append(f"{path}: dynamically imports forbidden local persistence module {module}")


def record_forbidden_secret_env_import(
    path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]
) -> None:
    for module in imported_module_names(node):
        if module.split(".", 1)[0] in FORBIDDEN_SECRET_ENV_IMPORT_ROOTS:
            violations.append(f"{path}: imports forbidden env/material module {module}")
        if is_forbidden_module(module, FORBIDDEN_SECRET_ENV_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden secret helper module {module}")


def record_forbidden_secret_env_call(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    call = call_name(node.func)
    if call in FORBIDDEN_SECRET_ENV_CALL_NAMES:
        violations.append(f"{path}: calls forbidden secret/env accessor {call}()")
    if call in FORBIDDEN_SECRET_FILE_READ_CALL_NAMES:
        violations.append(f"{path}: calls forbidden secret/file material reader {call}()")
    if is_os_environ_access(node.func):
        violations.append(f"{path}: accesses forbidden os.environ material")
    if is_path_home_call(node.func):
        violations.append(f"{path}: calls forbidden Path.home() material locator")


def record_forbidden_runtime_side_effect_import(
    path: Path, node: ast.Import | ast.ImportFrom, violations: list[str]
) -> None:
    for module in imported_module_names(node):
        if is_forbidden_module(module, FORBIDDEN_RUNTIME_SIDE_EFFECT_MODULE_PREFIXES):
            violations.append(f"{path}: imports forbidden runtime side-effect module {module}")


def record_forbidden_runtime_side_effect_dynamic_import(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    module = literal_dynamic_import_module(node)
    if module is None:
        return
    if is_forbidden_module(module, FORBIDDEN_RUNTIME_SIDE_EFFECT_MODULE_PREFIXES):
        violations.append(f"{path}: dynamically imports forbidden runtime side-effect module {module}")


def record_forbidden_runtime_side_effect_call(
    path: Path, node: ast.Call, violations: list[str]
) -> None:
    call = call_name(node.func)
    if call in FORBIDDEN_RUNTIME_SIDE_EFFECT_CALL_NAMES:
        violations.append(f"{path}: calls forbidden runtime side-effect function {call}()")


def record_forbidden_os_environ_access(
    path: Path, node: ast.Attribute | ast.Subscript, violations: list[str]
) -> None:
    if is_os_environ_access(node):
        violations.append(f"{path}: accesses forbidden os.environ material")


def record_forbidden_file_write_call(path: Path, node: ast.Call, violations: list[str]) -> None:
    call = call_name(node.func)
    if call in FORBIDDEN_FILE_WRITE_METHOD_NAMES:
        violations.append(f"{path}: calls forbidden file writer {call}()")
        return
    if call == "open" and open_call_uses_write_mode(node):
        violations.append(f"{path}: opens a file in write/append/create mode")
        return
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "replace"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    ):
        violations.append(f"{path}: calls forbidden file writer os.replace()")


def is_forbidden_module(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def is_forbidden_local_persistence_module(module: str) -> bool:
    return module.split(".", 1)[0] in FORBIDDEN_LOCAL_PERSISTENCE_MODULES


def literal_dynamic_import_module(node: ast.Call) -> str | None:
    call = call_name(node.func)
    if call not in {"__import__", "import_module", "importlib.import_module"}:
        return None
    if not node.args:
        return None
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
        return None
    return first_arg.value


def is_os_environ_access(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        if (
            node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            return True
        return is_os_environ_access(node.value)
    if isinstance(node, ast.Subscript):
        return is_os_environ_access(node.value)
    return False


def is_path_home_call(func: ast.expr) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "home"
        and isinstance(func.value, ast.Name)
        and func.value.id == "Path"
    )


def imported_module_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    module_names: list[str] = []
    if isinstance(node, ast.Import):
        module_names.extend(alias.name for alias in node.names)
    elif node.module:
        module_names.append(node.module)
        module_names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return module_names


def open_call_uses_write_mode(node: ast.Call) -> bool:
    mode: str | None = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        if isinstance(node.args[1].value, str):
            mode = node.args[1].value
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                mode = keyword.value.value
    return mode is not None and any(flag in mode for flag in ("w", "a", "x", "+"))


def decorated_http_method(decorator: ast.expr) -> str | None:
    if isinstance(decorator, ast.Call):
        return call_name(decorator.func)
    return call_name(decorator)


def is_empty_dict(value: ast.expr) -> bool:
    return isinstance(value, ast.Dict) and value.keys == [] and value.values == []


def stock_etf_route_method_constants(tree: ast.AST) -> dict[str, str]:
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


def is_stock_etf_get_route_decorator(decorator: ast.expr) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id == "stock_etf_router"
    )


def is_current_actor_dependency(value: ast.expr) -> bool:
    if not isinstance(value, ast.Call):
        return False
    if call_name(value.func) != "Depends" or len(value.args) != 1:
        return False
    dependency = value.args[0]
    return (
        isinstance(dependency, ast.Attribute)
        and dependency.attr == "current_actor"
        and isinstance(dependency.value, ast.Name)
        and dependency.value.id == "base"
    )


def call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
