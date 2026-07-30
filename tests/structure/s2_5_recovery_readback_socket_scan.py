"""AST proof for the recovery current-readback Adapter's fixed AF_UNIX transport."""

from __future__ import annotations

import ast
from pathlib import Path


READBACK_LEAF = "agent_governance_s2_5_recovery_readback.py"
FIXED_SOCKET_PATH = (
    "/run/arcane-equilibrium/s2-5-recovery-anchor-readback.sock"
)


def readback_socket_contract_findings(
    tree: ast.AST,
    path: Path,
) -> list[str]:
    """Prove actual constructor, receiver, endpoint, and socket-object provenance."""

    if path.name != READBACK_LEAF:
        return []
    findings: list[str] = []
    parents = {
        id(child): node
        for node in ast.walk(tree)
        for child in ast.iter_child_nodes(node)
    }

    def root_name(node: ast.AST) -> str | None:
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        return node.id if isinstance(node, ast.Name) else None

    socket_imports = [
        alias
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "socket"
    ]
    if len(socket_imports) != 1 or socket_imports[0].asname is not None:
        findings.append("readback socket module must be one unaliased import")
    if any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] == "socket"
        for node in ast.walk(tree)
    ):
        findings.append("readback socket module cannot use from-import aliases")
    if any(
        root_name(node) == "socket"
        and isinstance(node.ctx, (ast.Store, ast.Del))
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript))
    ):
        findings.append("readback socket module reassignment is forbidden")

    def exact_constant_target(name: str, expected: object) -> ast.Name | None:
        assignments = [
            node
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
            )
        ]
        targets = (
            assignments[0].targets
            if len(assignments) == 1 and isinstance(assignments[0], ast.Assign)
            else [assignments[0].target]
            if len(assignments) == 1
            else []
        )
        value = assignments[0].value if len(assignments) == 1 else None
        exact = (
            len(targets) == 1
            and isinstance(targets[0], ast.Name)
            and targets[0].id == name
            and isinstance(value, ast.Constant)
            and type(value.value) is type(expected)
            and value.value == expected
        )
        if not exact:
            findings.append(f"readback {name} top-level constant is not exact")
            return None
        return targets[0]

    path_target = exact_constant_target(
        "FIXED_ATTESTOR_SOCKET_PATH",
        FIXED_SOCKET_PATH,
    )
    timeout_target = exact_constant_target("SOCKET_TIMEOUT_SECONDS", 2.0)
    response_limit_target = exact_constant_target("MAX_RESPONSE_BYTES", 65536)
    path_stores = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "FIXED_ATTESTOR_SOCKET_PATH"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if len(path_stores) != 1:
        findings.append("readback fixed attestor endpoint reassignment is forbidden")

    constructors = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "socket"
        and node.func.attr == "socket"
    ]
    constructor = constructors[0] if len(constructors) == 1 else None
    if not (
        constructor is not None
        and len(constructor.args) == 2
        and not constructor.keywords
        and all(
            isinstance(argument, ast.Attribute)
            and isinstance(argument.value, ast.Name)
            and argument.value.id == "socket"
            and argument.attr == expected
            for argument, expected in zip(
                constructor.args,
                ("AF_UNIX", "SOCK_STREAM"),
            )
        )
    ):
        findings.append(
            "readback socket constructor must be exactly AF_UNIX/SOCK_STREAM"
        )
    constructor_parent = (
        parents.get(id(constructor)) if constructor is not None else None
    )
    constructor_targets = (
        constructor_parent.targets
        if isinstance(constructor_parent, ast.Assign)
        else [constructor_parent.target]
        if isinstance(constructor_parent, ast.AnnAssign)
        else []
    )
    if not (
        len(constructor_targets) == 1
        and isinstance(constructor_targets[0], ast.Name)
        and constructor_targets[0].id == "client"
    ):
        findings.append("readback socket constructor must bind only client")

    client_stores = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "client"
        and isinstance(node.ctx, ast.Store)
    ]
    if len(client_stores) != 1:
        findings.append("readback socket client alias or reassignment is forbidden")

    transport_functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_fixed_transport_exchange"
    ]
    transport = transport_functions[0] if len(transport_functions) == 1 else None
    arguments = transport.args if transport is not None else None
    if not (
        transport is not None
        and not transport.decorator_list
        and arguments is not None
        and not arguments.posonlyargs
        and len(arguments.args) == 1
        and arguments.args[0].arg == "request_bytes"
        and isinstance(arguments.args[0].annotation, ast.Name)
        and arguments.args[0].annotation.id == "bytes"
        and arguments.vararg is None
        and not arguments.kwonlyargs
        and arguments.kwarg is None
        and not arguments.defaults
        and not arguments.kw_defaults
    ):
        findings.append(
            "readback _fixed_transport_exchange exact signature is required"
        )

    protected = {
        "socket",
        "FIXED_ATTESTOR_SOCKET_PATH",
        "SOCKET_TIMEOUT_SECONDS",
        "MAX_RESPONSE_BYTES",
        "client",
    }
    allowed_binding_ids = {
        "socket": (
            {id(socket_imports[0])}
            if len(socket_imports) == 1 and socket_imports[0].asname is None
            else set()
        ),
        "FIXED_ATTESTOR_SOCKET_PATH": (
            {id(path_target)} if path_target is not None else set()
        ),
        "SOCKET_TIMEOUT_SECONDS": (
            {id(timeout_target)} if timeout_target is not None else set()
        ),
        "MAX_RESPONSE_BYTES": (
            {id(response_limit_target)}
            if response_limit_target is not None
            else set()
        ),
        "client": (
            {id(client_stores[0])}
            if len(client_stores) == 1
            and constructor_targets == [client_stores[0]]
            else set()
        ),
    }
    bound: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.append((node.id, node))
        elif isinstance(node, ast.arg):
            bound.append((node.arg, node))
        elif isinstance(node, ast.alias):
            bound.append((node.asname or node.name.split(".")[0], node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.append((node.name, node))
        elif isinstance(node, ast.ExceptHandler) and isinstance(node.name, str):
            bound.append((node.name, node))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.extend((name, node) for name in node.names)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            bound.append((node.name, node))
        elif isinstance(node, ast.MatchMapping) and node.rest:
            bound.append((node.rest, node))
    for name, node in bound:
        if name in protected and id(node) not in allowed_binding_ids[name]:
            findings.append(f"readback {name} binding shadow is forbidden")

    allowed_shapes = {
        "settimeout": lambda call: (
            len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "SOCKET_TIMEOUT_SECONDS"
            and not call.keywords
        ),
        "connect": lambda call: (
            len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "FIXED_ATTESTOR_SOCKET_PATH"
            and not call.keywords
        ),
        "sendall": lambda call: (
            len(call.args) == 1
            and isinstance(call.args[0], ast.BinOp)
            and isinstance(call.args[0].op, ast.Add)
            and isinstance(call.args[0].left, ast.Name)
            and call.args[0].left.id == "request_bytes"
            and isinstance(call.args[0].right, ast.Constant)
            and call.args[0].right.value == b"\n"
            and not call.keywords
        ),
        "recv": lambda call: (
            len(call.args) == 1
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == 8192
            and not call.keywords
        ),
        "close": lambda call: not call.args and not call.keywords,
    }
    client_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        receiver = node.func.value
        if node.func.attr == "connect" and not (
            isinstance(receiver, ast.Name)
            and receiver.id == "client"
            and allowed_shapes["connect"](node)
        ):
            findings.append("readback connect must use the fixed attestor endpoint")
        if isinstance(receiver, ast.Name) and receiver.id == "client":
            client_calls.append(node)
            checker = allowed_shapes.get(node.func.attr)
            if checker is None or not checker(node):
                findings.append(
                    "readback socket client method/arguments are forbidden: "
                    f"{node.func.attr}"
                )
    if sum(
        node.func.attr == "connect" and allowed_shapes["connect"](node)
        for node in client_calls
    ) != 1:
        findings.append("readback requires exactly one fixed attestor endpoint connect")

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Name)
            and node.id == "client"
            and isinstance(node.ctx, ast.Load)
        ):
            continue
        parent = parents.get(id(node))
        grandparent = parents.get(id(parent)) if parent is not None else None
        if not (
            isinstance(parent, ast.Attribute)
            and parent.value is node
            and isinstance(grandparent, ast.Call)
            and grandparent.func is parent
            and grandparent in client_calls
        ):
            findings.append("readback socket client alias or escape is forbidden")
    return findings
