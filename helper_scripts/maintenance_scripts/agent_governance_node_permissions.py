"""Node-scoped permission projection for routed and adaptively admitted work."""

from __future__ import annotations

from typing import Any

from agent_governance_registry import load_registry, native_agent_binding
from agent_governance_workflow_identity import requested_logical_role, requested_native_agent


def _contracts(
    route: dict[str, Any] | None, admitted: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    roles = load_registry()["roles"]
    result: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for node in (route or {}).get("nodes", []):
        role = node.get("role") if isinstance(node, dict) else None
        node_id = node.get("id") if isinstance(node, dict) else None
        if role not in roles or role == "PM" or not isinstance(node_id, str):
            continue
        try:
            binding = native_agent_binding(role, node.get("node_class"))
        except ValueError as exc:
            errors.append(f"routed node {node_id} binding is invalid: {exc}")
            continue
        expected = {"role": role, **binding}
        if any(node.get(field) != expected[field] for field in binding):
            errors.append(f"routed node {node_id} native binding differs from Registry")
        result[node_id] = expected
    for node_id, node in admitted.items():
        role, node_class = node.get("role"), node.get("node_class")
        if role in roles and node_class in {"work", "verification"}:
            try:
                binding = native_agent_binding(role, node_class)
            except ValueError as exc:
                errors.append(f"admitted node {node_id} binding is invalid: {exc}")
                continue
            expected = {"role": role, **binding}
            if any(node.get(field) != expected[field] for field in binding):
                errors.append(f"admitted node {node_id} native binding differs from Registry")
            result[node_id] = expected
    return result, errors


def validate_node_scoped_permissions(
    captures: dict[str, Any],
    route: dict[str, Any] | None,
    admitted: dict[str, dict[str, Any]],
) -> list[str]:
    contracts, errors = _contracts(route, admitted)
    for evidence_id, command in captures.get("commands", {}).items():
        contract = contracts.get(command.get("node_id"))
        if contract is None:
            errors.append(f"command capture {evidence_id} node is not dispatch-bound")
            continue
        if command.get("role_id") != contract["role"]:
            errors.append(f"command capture {evidence_id} role differs from node contract")
        if command.get("node_class") != contract["node_class"]:
            errors.append(f"command capture {evidence_id} class differs from node contract")
        policy = command.get("authorization", {}).get("policy_class")
        if contract["node_class"] == "verification" and policy == "local_test_adapter":
            errors.append(f"command capture {evidence_id} used writer permission for verification")
    for call_id, call in captures.get("calls", {}).items():
        contract = contracts.get(call.get("node_id"))
        if contract is None:
            continue
        requested = call.get("requested", {})
        actual = {
            "role": requested_logical_role(requested),
            "native_agent": requested_native_agent(requested),
            "node_class": requested.get("node_class"),
            "permission": requested.get("permission"),
        }
        for field in actual:
            if actual[field] != contract[field]:
                errors.append(
                    f"workflow call {call_id} requested {field} differs from node contract"
                )
    for evidence_id, change in captures.get("changes", {}).items():
        contract = contracts.get(change.get("node_id"))
        if contract is None or contract["node_class"] != "work":
            errors.append(f"repository change {evidence_id} is not owned by a writer work node")
        elif change.get("role_id") != contract["role"]:
            errors.append(f"repository change {evidence_id} role differs from node contract")
    return errors
