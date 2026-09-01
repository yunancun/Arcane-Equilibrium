"""Closure dispatch admission, delegated DAG, and writer-scope validation."""

from __future__ import annotations

from typing import Any

from agent_governance_execution_dag import (
    execution_dag_digest,
    task_execution_projection,
)
from agent_governance_repository_changes import writer_scope_contracts


def validate_dispatch_projection(
    dispatch: dict[str, Any],
    *,
    expected_route: dict[str, Any] | None,
    expected_required_nodes: list[dict[str, Any]],
    task_contract: dict[str, Any],
    role_registry: dict[str, Any],
) -> dict[str, Any]:
    """Validate final PM admissions and compile their exact call-producing DAG."""

    errors: list[str] = []
    admitted_nodes = dispatch.get("admitted_role_nodes", [])
    if not isinstance(admitted_nodes, list):
        errors.append("dispatch admitted_role_nodes must be an array")
        admitted_nodes = []
    admitted_by_node: dict[str, dict[str, Any]] = {}
    surfaces = set((expected_route or {}).get("task_facts", {}).get("surfaces", []))
    route_node_ids = {
        node["id"] for node in (expected_route or {}).get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }
    for index, node in enumerate(admitted_nodes):
        if not isinstance(node, dict):
            errors.append(f"dispatch admitted_role_nodes[{index}] must be an object")
            continue
        node_id, role = node.get("node_id"), node.get("role")
        node_class = node.get("node_class")
        if not node_id or node_id in admitted_by_node or node_id in route_node_ids:
            errors.append(
                f"dispatch admitted_role_nodes[{index}] node_id missing, duplicate, or collides with routed DAG"
            )
            continue
        admitted_by_node[node_id] = node
        if role not in role_registry or role == "PM":
            errors.append(f"dispatch admitted_role_nodes[{index}] has invalid delegated role")
        if node_class not in {"work", "verification"}:
            errors.append(f"dispatch admitted_role_nodes[{index}] has invalid node_class")
        if (
            node_class == "work" and role in role_registry
            and role_registry[role]["permission"] == "read_only"
        ):
            errors.append(
                f"dispatch admitted_role_nodes[{index}] binds read-only role to work node"
            )
        if node.get("result_binding") not in {"role_fragment", "nested_payload"}:
            errors.append(f"dispatch admitted_role_nodes[{index}] has invalid result_binding")
        elif node.get("result_binding") == "nested_payload" and "full_audit" not in surfaces:
            errors.append(
                f"dispatch admitted_role_nodes[{index}] nested_payload is not owned by a specialized workflow contract"
            )

    dispatch_node_ids = {
        node.get("node_id")
        for node in [*expected_required_nodes, *admitted_nodes]
        if isinstance(node, dict)
    }
    for index, node in enumerate(admitted_nodes):
        if not isinstance(node, dict):
            continue
        requires = node.get("requires")
        if (
            not isinstance(requires, list)
            or requires != sorted(set(requires))
            or any(required not in dispatch_node_ids for required in requires)
            or node.get("node_id") in requires
        ):
            errors.append(
                f"dispatch admitted_role_nodes[{index}] requires are not sorted unique dispatch predecessors"
            )

    projection, projection_errors = task_execution_projection(
        expected_required_nodes,
        admitted_nodes,
        task_facts=(expected_route or {}).get("task_facts", {}),
        require_fixed_admissions=True,
    )
    errors.extend(
        f"dispatch delegated execution projection invalid: {error}"
        for error in projection_errors
    )
    if dispatch.get("dag_digest") != execution_dag_digest(projection):
        errors.append("dispatch dag_digest does not match delegated execution projection")

    claim_payloads = task_contract.get("claim_payloads", {})
    if not isinstance(claim_payloads, dict):
        errors.append("task contract claim_payloads must be an object")
        claim_payloads = {}
    scope_contract = claim_payloads.get("repository_writer_scope_contract")
    adaptive_writer_node_ids = {
        node.get("node_id") for node in admitted_nodes
        if isinstance(node, dict) and node.get("node_class") == "work"
    }
    writer_scopes, writer_errors = writer_scope_contracts(
        [*expected_required_nodes, *admitted_nodes],
        expected_dirty_scope=sorted(task_contract.get("dirty_scope", [])),
        scope_contract=scope_contract,
        adaptive_writer_node_ids=adaptive_writer_node_ids,
    )
    errors.extend(writer_errors)
    roles_by_node = {
        node.get("node_id"): node.get("role")
        for node in [*expected_required_nodes, *admitted_nodes]
        if isinstance(node, dict) and isinstance(node.get("role"), str)
    }
    writer_roles = {
        node_id: roles_by_node[node_id]
        for node_id in writer_scopes if node_id in roles_by_node
    }
    return {
        "admitted_nodes": admitted_nodes,
        "admitted_by_node": admitted_by_node,
        "projection": projection,
        "writer_scopes": writer_scopes,
        "writer_roles": writer_roles,
        "errors": errors,
    }
