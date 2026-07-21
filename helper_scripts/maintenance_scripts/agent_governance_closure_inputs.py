"""Non-mutating input normalization for closure validation."""

from __future__ import annotations

from typing import Any


_OBJECT_FIELDS = (
    "human_summary",
    "baseline",
    "dispatch",
    "side_effects",
    "consumption",
)
_OBJECT_LIST_FIELDS = (
    "authority_refs",
    "acceptance",
    "evidence",
    "role_fragments",
    "checks",
    "skipped_roles",
)


def normalize_closure_packet_inputs(
    packet: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Return a shallow safe view and explicit errors for malformed inputs."""

    safe_packet = dict(packet)
    errors: list[str] = []
    for field in _OBJECT_FIELDS:
        if not isinstance(packet.get(field), dict):
            safe_packet[field] = {}
            errors.append(f"closure {field} must be an object")
    for field in _OBJECT_LIST_FIELDS:
        items = packet.get(field)
        if not isinstance(items, list):
            safe_packet[field] = []
            errors.append(f"closure {field} must be a list")
            continue
        safe_items: list[dict[str, Any]] = []
        changed = False
        for index, item in enumerate(items):
            if isinstance(item, dict):
                safe_items.append(item)
                continue
            safe_items.append({})
            changed = True
            errors.append(f"{field}[{index}] must be an object")
        if changed:
            safe_packet[field] = safe_items
    if not isinstance(packet.get("unverified"), list):
        safe_packet["unverified"] = []
        errors.append("closure unverified must be a list")
    dispatch = safe_packet["dispatch"]
    if not isinstance(dispatch.get("task_facts"), dict):
        safe_packet["dispatch"] = {**dispatch, "task_facts": {}}
        errors.append("closure dispatch.task_facts must be an object")
    for field in ("acceptance", "role_fragments"):
        items = safe_packet[field]
        safe_items = items
        for index, item in enumerate(items):
            refs = item.get("evidence_refs")
            if not isinstance(refs, list):
                if safe_items is items:
                    safe_items = list(items)
                safe_items[index] = {**item, "evidence_refs": []}
                errors.append(
                    f"closure {field}[{index}].evidence_refs must be a list"
                )
                continue
            safe_refs: list[str] = []
            changed = False
            for ref_index, ref in enumerate(refs):
                if isinstance(ref, str):
                    safe_refs.append(ref)
                    continue
                changed = True
                errors.append(
                    f"closure {field}[{index}].evidence_refs[{ref_index}] "
                    "must be a string"
                )
            if changed:
                if safe_items is items:
                    safe_items = list(items)
                safe_items[index] = {**item, "evidence_refs": safe_refs}
        safe_packet[field] = safe_items
    checks = safe_packet["checks"]
    safe_checks = checks
    for index, check in enumerate(checks):
        execution_receipt = check.get("execution_receipt")
        if not isinstance(execution_receipt, dict) or isinstance(
            execution_receipt.get("facts"), dict
        ):
            continue
        if safe_checks is checks:
            safe_checks = list(checks)
        safe_checks[index] = {
            **check,
            "execution_receipt": {**execution_receipt, "facts": {}},
        }
        errors.append(
            f"closure checks[{index}].execution_receipt.facts must be an object"
        )
    safe_packet["checks"] = safe_checks
    return safe_packet, errors
