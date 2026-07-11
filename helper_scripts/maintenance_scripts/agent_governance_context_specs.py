"""Typed Registry Context-source activation and identity helpers."""

from __future__ import annotations

from typing import Any

from agent_governance_vocabulary import (
    CLAIM_FLAGS,
    KNOWN_SURFACES,
    UNCERTAINTY_LEVELS,
)


SOURCE_KINDS = {"repository_source", "repository_inventory", "evidence_artifact"}
CAPTURE_KINDS = {
    "runtime_observation", "external_policy_snapshot", "source_snapshot",
}
DERIVED_SOURCE_KINDS = {
    "current diff": "diff_snapshot",
    "direct interfaces": "interface_inventory",
    "direct callers": "caller_inventory",
    "focused acceptance tests": "test_inventory",
}


def source_name(value: str | dict[str, Any]) -> str:
    return value if isinstance(value, str) else str(value.get("source", ""))


def _condition_errors(value: Any) -> list[str]:
    if not isinstance(value, dict) or not value:
        return ["required_when must be a non-empty object"]
    allowed = {"surfaces_any", "claims_any", "uncertainty_any"}
    if not set(value) <= allowed:
        return ["required_when contains unknown condition fields"]
    errors: list[str] = []
    for field in allowed:
        items = value.get(field)
        if items is not None and (
            not isinstance(items, list) or not items
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            errors.append(f"required_when {field} must be non-empty strings")
    if set(value.get("claims_any", [])) - CLAIM_FLAGS:
        errors.append("required_when claims_any contains an unknown claim flag")
    if set(value.get("surfaces_any", [])) - KNOWN_SURFACES:
        errors.append("required_when surfaces_any contains an unknown surface")
    if set(value.get("uncertainty_any", [])) - UNCERTAINTY_LEVELS:
        errors.append("required_when uncertainty_any contains an unknown level")
    return errors


def context_source_spec_errors(value: Any) -> list[str]:
    """Validate one Registry source spec without resolving repository state."""

    if isinstance(value, str):
        return [] if value.strip() else ["Context source string must be non-empty"]
    if not isinstance(value, dict):
        return ["Context source must be a string or typed object"]
    kind = value.get("kind")
    common = {"source", "kind", "required_when"}
    allowed = {
        "repository_source": common,
        "repository_inventory": common | {"paths", "min_matches"},
        "evidence_artifact": common | {"capture_kind"},
    }.get(kind)
    if allowed is None:
        return [f"Context source kind is invalid: {kind}"]
    errors: list[str] = []
    required = {"source", "kind"}
    if kind == "repository_inventory":
        required |= {"paths", "min_matches"}
    if kind == "evidence_artifact":
        required |= {"capture_kind", "required_when"}
    if set(value) - allowed or not required <= set(value):
        errors.append(f"{kind} Context source fields are not exact")
    if not isinstance(value.get("source"), str) or not value["source"].strip():
        errors.append("typed Context source name must be non-empty")
    if "required_when" in value:
        errors.extend(_condition_errors(value["required_when"]))
    if kind == "repository_inventory":
        paths = value.get("paths")
        if (
            not isinstance(paths, list) or not paths
            or any(
                not isinstance(path, str) or not path.strip()
                or path.startswith(("/", "~")) or ".." in path.split("/")
                for path in paths
            )
        ):
            errors.append("repository_inventory paths must be safe repo-relative patterns")
        if type(value.get("min_matches")) is not int or value["min_matches"] < 0:
            errors.append("repository_inventory min_matches must be non-negative int")
    if kind == "evidence_artifact" and value.get("capture_kind") not in CAPTURE_KINDS:
        errors.append("evidence_artifact capture_kind is invalid")
    return errors


def source_is_active(spec: str | dict[str, Any], facts: dict[str, Any]) -> bool:
    if isinstance(spec, str) or "required_when" not in spec:
        return True
    condition = spec["required_when"]
    surfaces = set(facts.get("surfaces", []))
    return bool(
        surfaces.intersection(condition.get("surfaces_any", []))
        or any(facts.get(flag) is True for flag in condition.get("claims_any", []))
        or facts.get("uncertainty") in condition.get("uncertainty_any", [])
    )


def activated_source_specs(
    registry: dict[str, Any], selected_packs: list[str], facts: dict[str, Any]
) -> list[str | dict[str, Any]]:
    selected: list[str | dict[str, Any]] = []
    names: set[str] = set()
    for pack in selected_packs:
        for spec in registry["context_packs"][pack]:
            name = source_name(spec)
            if source_is_active(spec, facts) and name not in names:
                selected.append(spec)
                names.add(name)
    return selected


def trusted_derived_kinds(registry: dict[str, Any]) -> dict[str, str]:
    result = dict(DERIVED_SOURCE_KINDS)
    for specs in registry.get("context_packs", {}).values():
        for spec in specs:
            if isinstance(spec, dict) and spec.get("kind") == "repository_inventory":
                result[source_name(spec)] = "repository_inventory"
    return result
