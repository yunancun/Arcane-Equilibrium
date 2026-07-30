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

    path_assignments = [
        node
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name)
            and target.id == "FIXED_ATTESTOR_SOCKET_PATH"
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
        )
    ]
    path_value = path_assignments[0].value if len(path_assignments) == 1 else None
    if not (
        isinstance(path_value, ast.Constant)
        and path_value.value == FIXED_SOCKET_PATH
    ):
        findings.append("readback fixed attestor endpoint constant is not exact")
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
