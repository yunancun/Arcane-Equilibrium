"""Deterministic routed-axis and nested-call projection for Full Audit."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_governance_registry import native_agent_binding


def nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def adaptive_axes(
    expected_route: dict[str, Any] | None,
    run_sequence: int,
    axes_contract: list[str],
) -> list[str]:
    """Project route roles plus Full Audit backstops without duplicate routing."""

    selected = {"CC", "FA"}
    selected.update(
        item.get("role")
        for item in (expected_route or {}).get("required_role_nodes", [])
        if item.get("role") in axes_contract
    )
    unselected = [axis for axis in axes_contract if axis not in selected]
    if unselected:
        selected.add(unselected[run_sequence % len(unselected)])
    return [axis for axis in axes_contract if axis in selected]


def nested_admission_inventory(
    admitted_axes: list[str], fragments_by_node: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Derive every typed nested call from admitted axis payloads."""

    inventory: list[dict[str, Any]] = []
    audit_nodes = sorted(f"audit:{axis}" for axis in admitted_axes)
    role_by_view = {"source": "E2", "impact": "PA", "third": "E3"}
    for axis in admitted_axes:
        parent = f"audit:{axis}"
        payload = fragments_by_node.get(parent, {}).get("payload", {})
        outcomes = payload.get("verification_outcomes", [])
        for record in outcomes if isinstance(outcomes, list) else []:
            outcome = record.get("outcome", {}) if isinstance(record, dict) else {}
            claim_id, votes = outcome.get("claim_id"), outcome.get("verifier_votes", [])
            if not isinstance(claim_id, str) or not isinstance(votes, list):
                continue
            vote_nodes = {
                vote.get("view"): f"verify:{claim_id}:{vote.get('view')}"
                for vote in votes if isinstance(vote, dict)
                and vote.get("view") in role_by_view
            }
            for vote in votes:
                view = vote.get("view") if isinstance(vote, dict) else None
                if view not in role_by_view:
                    continue
                role = role_by_view[view]
                requires = [parent]
                if view == "third":
                    requires.extend(
                        vote_nodes[item] for item in ("source", "impact")
                        if item in vote_nodes
                    )
                inventory.append({
                    "node_id": vote_nodes[view], "role": role,
                    **native_agent_binding(role, "verification"),
                    "node_class": "verification",
                    "requires": sorted(set(requires)), "path_scope": [],
                    "reason": "full audit typed finding verification",
                    "result_binding": "nested_payload",
                })
    inventory.append({
        "node_id": "seam:critic", "role": "CC",
        **native_agent_binding("CC", "verification"),
        "node_class": "verification", "requires": audit_nodes,
        "path_scope": [], "reason": "full audit cross-axis seam critic",
        "result_binding": "nested_payload",
    })
    return inventory
