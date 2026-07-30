"""Logical-role to actual platform selector binding for workflow receipts."""

from __future__ import annotations

from typing import Any

from agent_governance_execution_policy import (
    requested_history_errors,
    surface_allows_mandatory_role,
    surface_profile_binding,
)
from agent_governance_registry import load_registry, native_agent_binding


REQUESTED_FIELDS = {
    "logical_role", "platform", "platform_requested_agent", "native_binding",
    "surface_profile_id", "surface_profile_digest", "history",
    "model", "effort", "isolation", "node_class", "permission",
}
NATIVE_BINDING_FIELDS = {"logical_role", "native_agent", "node_class", "permission"}


def requested_identity_errors(
    value: Any,
    *,
    expected_role: str | None = None,
    admitted_history_exception_digests: set[str] | None = None,
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
    profile_id = value.get("surface_profile_id")
    try:
        surface = surface_profile_binding(str(profile_id), registry)
    except ValueError as exc:
        errors.append(f"workflow call execution surface is invalid: {exc}")
        surface = None
    if surface is not None:
        profile = surface["profile"]
        if value.get("surface_profile_digest") != surface["digest"]:
            errors.append("workflow call execution surface digest differs from Registry")
        if value.get("platform") != profile["platform"]:
            errors.append("workflow call platform differs from execution surface")
        if (
            isinstance(role, str)
            and role in registry["roles"]
            and role != "PM"
            and not surface_allows_mandatory_role(profile, role)
        ):
            errors.append(
                "workflow call execution surface is not eligible for mandatory roles"
            )
    errors.extend(
        requested_history_errors(
            value.get("history"),
            admitted_exception_digests=(
                admitted_history_exception_digests
                if admitted_history_exception_digests is not None
                else set()
            ),
        )
    )
    for field in ("model", "effort", "isolation"):
        item = value.get(field)
        if item is not None and (not isinstance(item, str) or not item.strip()):
            errors.append(f"workflow call requested {field} must be null or non-empty string")
    if (
        surface is not None
        and surface["profile"]["platform"] == "codex_native_collaboration"
        and isinstance(role, str)
        and role in registry["roles"]
    ):
        model_route = registry["model_routing"]["roles"][role]
        if value.get("model") != model_route["model"]:
            errors.append("Codex workflow model differs from Registry model route")
        if value.get("effort") != model_route["model_reasoning_effort"]:
            errors.append("Codex workflow effort differs from Registry model route")
    if (
        surface is not None
        and surface["profile"]["platform"] == "claude_saved_workflow"
        and isinstance(role, str)
        and role in registry["roles"]
    ):
        model_policy = registry["saved_workflow_model_policy"]
        if value.get("model") != model_policy["model"]:
            errors.append(
                "saved workflow model differs from Registry model policy"
            )
        if value.get("effort") != model_policy["role_efforts"][role]:
            errors.append(
                "saved workflow effort differs from Registry role policy"
            )
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
