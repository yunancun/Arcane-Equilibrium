from __future__ import annotations

import ast

from stock_etf_static_guard_helpers import (
    ALLOWED_STOCK_ETF_STATUS_IPC_METHODS,
    CONTROL_API_DIR,
    FORBIDDEN_HTTP_ROUTE_METHODS,
    candidate_stock_etf_ibkr_python_files,
    call_name,
    decorated_http_method,
    is_current_actor_dependency,
    is_empty_dict,
    is_stock_etf_get_route_decorator,
    stock_etf_route_method_constants,
)


def test_stock_etf_ibkr_python_routes_remain_get_only_until_rust_authority_contract_changes() -> None:
    violations: list[str] = []
    for path in candidate_stock_etf_ibkr_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    route_method = decorated_http_method(decorator)
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
            if len(params_keywords) != 1 or not is_empty_dict(params_keywords[0].value):
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
    method_constants = stock_etf_route_method_constants(tree)

    used_methods: set[str] = set()
    helper_call_count = 0
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if call_name(node.func) != "_query_stock_etf_status":
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
        if not any(is_stock_etf_get_route_decorator(decorator) for decorator in node.decorator_list):
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
        if not is_current_actor_dependency(actor_default):
            violations.append(
                f"{path}:{node.lineno}: {node.name}() actor is not Depends(base.current_actor)"
            )

    assert route_count == 18
    assert violations == []
