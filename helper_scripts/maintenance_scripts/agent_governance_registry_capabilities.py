"""Cross-role capability and on-demand skill invariants for the Registry."""

from __future__ import annotations

from typing import Any


WEB_TOOLS = {"WebSearch", "WebFetch"}
WEB_ACQUISITION_ROLES = {"AI-E", "BB", "E3", "IB", "MIT", "QC"}
WEB_FORBIDDEN_ROLES = {
    "A3", "CC", "E1", "E1a", "E4", "E5", "FA", "OPS", "PA", "PM",
    "QA", "R4", "TW",
}


def registry_capability_errors(registry: dict[str, Any]) -> list[str]:
    """Keep broad tools scarce and high-cost skills explicitly task-triggered."""

    errors: list[str] = []
    roles = registry.get("roles", {})
    for role_id, spec in roles.items():
        tools = set(spec.get("tools", []))
        web = tools & WEB_TOOLS
        if role_id in WEB_FORBIDDEN_ROLES and web:
            errors.append(f"{role_id}: public-web tools are not admitted")
        if role_id in WEB_ACQUISITION_ROLES and web != WEB_TOOLS:
            errors.append(
                f"{role_id}: public-web acquisition requires search plus opened-URL fetch"
            )
        if role_id not in WEB_ACQUISITION_ROLES | WEB_FORBIDDEN_ROLES and web:
            errors.append(f"{role_id}: undeclared public-web acquisition capability")
    on_demand = registry.get("on_demand_skills", {})
    architecture = on_demand.get("architecture-depth-review", {})
    if architecture.get("owners") != ["PA"]:
        errors.append("architecture-depth-review must be PA-owned and on-demand")
    root = on_demand.get("16-root-principles-checklist", {})
    if set(root.get("owners", [])) != {"CC", "PA", "PM"}:
        errors.append("16-root checklist must be hard-boundary/on-demand for CC/PA/PM")
    if any(
        "16-root-principles-checklist" in spec.get("skills", [])
        for spec in roles.values()
    ):
        errors.append("16-root checklist cannot be an unconditional role skill")
    return errors
