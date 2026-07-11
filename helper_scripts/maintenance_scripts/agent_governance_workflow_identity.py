"""Logical-role to actual platform selector binding for workflow receipts."""

from __future__ import annotations

from typing import Any

from agent_governance_registry import load_registry, native_agent_binding


REQUESTED_FIELDS = {
    "logical_role", "platform", "platform_requested_agent", "native_binding",
    "model", "effort", "isolation", "node_class", "permission",
}
NATIVE_BINDING_FIELDS = {"logical_role", "native_agent", "node_class", "permission"}


def requested_identity_errors(
    value: Any, *, expected_role: str | None = None,
) -> list[str]:
    if not isinstance(value, dict) or set(value) != REQUESTED_FIELDS:
        return ["workflow call requested fields do not match identity contract"]
    errors: list[str] = []
    role = value.get("logical_role")
    registry = load_registry()
    if not isinstance(role, str) or role not in registry["roles"] or role == "PM":
        errors.append("workflow call logical_role is not a registered delegated role")
    if expected_role is not None and role != expected_role:
        errors.append("workflow call logical_role differs from expected role")
    if value.get("platform") != "claude_saved_workflow":
        errors.append("workflow call platform must identify the saved-workflow runner")
    for field in ("model", "effort", "isolation"):
        item = value.get(field)
        if item is not None and (not isinstance(item, str) or not item.strip()):
            errors.append(f"workflow call requested {field} must be null or non-empty string")
    node_class, permission = value.get("node_class"), value.get("permission")
    if node_class not in {"work", "verification"}:
        errors.append("workflow call requested node_class is invalid")
    elif node_class == "verification" and permission != "read_only":
        errors.append("workflow call verification permission must be read_only")
    elif node_class == "work" and isinstance(role, str) and role in registry["roles"] and (
        registry["roles"][role]["permission"] == "read_only"
        or permission != registry["roles"][role]["permission"]
    ):
        errors.append("workflow call work permission differs from Registry")
    binding_value = value.get("native_binding")
    if not isinstance(binding_value, dict) or set(binding_value) != NATIVE_BINDING_FIELDS:
        errors.append("workflow call native_binding fields are not exact")
        return errors
    if isinstance(role, str) and role in registry["roles"] and role != "PM" and node_class in {"work", "verification"}:
        try:
            binding = native_agent_binding(role, node_class)
        except ValueError as exc:
            errors.append(f"workflow call native binding is invalid: {exc}")
        else:
            expected = {
                "logical_role": role,
                "native_agent": binding["native_agent"],
                "node_class": node_class,
                "permission": binding["permission"],
            }
            if binding_value != expected:
                errors.append("workflow call native_binding differs from Registry")
            if value.get("platform_requested_agent") != binding["native_agent"]:
                errors.append("workflow call actual platform selector differs from native binding")
            if permission != binding["permission"]:
                errors.append("workflow call permission differs from Registry native binding")
    return errors


def requested_logical_role(value: dict[str, Any]) -> Any:
    return value.get("logical_role")


def requested_native_agent(value: dict[str, Any]) -> Any:
    return value.get("platform_requested_agent")
