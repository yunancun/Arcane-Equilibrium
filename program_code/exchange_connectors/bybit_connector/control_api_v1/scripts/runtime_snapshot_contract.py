from __future__ import annotations

"""
Runtime snapshot contract helpers.
Runtime 快照合同辅助模块。

This module centralizes the normalized JSON contract used by:
- validate_runtime_snapshot.py
- generate_runtime_snapshot.py
"""

from typing import Any

ALLOWED_CONNECTION_STATES = {"ready", "degraded", "down", "unknown"}
ALLOWED_RUNTIME_CONNECTION_STATES = {"healthy", "degraded", "down", "unknown"}
ALLOWED_COMPLETENESS_STATES = {"complete", "partial", "missing", "unknown"}
ALLOWED_SYSTEM_MODE_FACTS = {"observe_only", "shadow_only", "design_only", "demo_reserved", "live_reserved"}
ALLOWED_EXECUTION_STATE_FACTS = {"execution_disabled", "demo_blocked", "demo_enabled", "live_blocked", "unknown"}
ALLOWED_FRESHNESS_STATES = {"fresh", "stale", "unknown"}
ALLOWED_PERMISSION_FACTS = {"readonly_visible", "unavailable", "unknown"}
ALLOWED_GATE_STATES = {"passed", "failed", "blocked", "not_evaluated"}
PRODUCT_FAMILIES = {
    "spot",
    "margin",
    "perp_linear",
    "perp_inverse",
    "options",
    "other_derivatives_reserved",
}


class RuntimeSnapshotValidationError(ValueError):
    """Raised when the runtime snapshot payload violates the normalized contract."""


def validate_state(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        raise RuntimeSnapshotValidationError(f"{field_name} invalid: {value!r}")


def validate_runtime_snapshot_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise RuntimeSnapshotValidationError("top-level payload must be an object")

    required_top = [
        "runtime_snapshot_id",
        "runtime_snapshot_ts_ms",
        "rest_private_connection_state",
        "ws_private_connection_state",
        "runtime_connection_state",
        "account_fact_completeness_state",
        "source_snapshot_completeness_state",
        "global_runtime_facts",
        "product_family_facts",
    ]
    for key in required_top:
        if key not in payload:
            raise RuntimeSnapshotValidationError(f"missing top-level field: {key}")

    if not isinstance(payload["runtime_snapshot_id"], str) or not payload["runtime_snapshot_id"].strip():
        raise RuntimeSnapshotValidationError("runtime_snapshot_id must be a non-empty string")

    if not isinstance(payload["runtime_snapshot_ts_ms"], int):
        raise RuntimeSnapshotValidationError("runtime_snapshot_ts_ms must be an integer")

    validate_state(payload["rest_private_connection_state"], ALLOWED_CONNECTION_STATES, "rest_private_connection_state")
    validate_state(payload["ws_private_connection_state"], ALLOWED_CONNECTION_STATES, "ws_private_connection_state")
    validate_state(payload["runtime_connection_state"], ALLOWED_RUNTIME_CONNECTION_STATES, "runtime_connection_state")
    validate_state(payload["account_fact_completeness_state"], ALLOWED_COMPLETENESS_STATES, "account_fact_completeness_state")
    validate_state(payload["source_snapshot_completeness_state"], ALLOWED_COMPLETENESS_STATES, "source_snapshot_completeness_state")

    global_runtime_facts = payload["global_runtime_facts"]
    if not isinstance(global_runtime_facts, dict):
        raise RuntimeSnapshotValidationError("global_runtime_facts must be an object")

    for key in [
        "system_mode_fact",
        "execution_state_fact",
        "runtime_last_refresh_ts_ms",
        "runtime_data_freshness_state",
    ]:
        if key not in global_runtime_facts:
            raise RuntimeSnapshotValidationError(f"missing global_runtime_facts field: {key}")

    validate_state(global_runtime_facts["system_mode_fact"], ALLOWED_SYSTEM_MODE_FACTS, "global_runtime_facts.system_mode_fact")
    validate_state(global_runtime_facts["execution_state_fact"], ALLOWED_EXECUTION_STATE_FACTS, "global_runtime_facts.execution_state_fact")
    if not isinstance(global_runtime_facts["runtime_last_refresh_ts_ms"], int):
        raise RuntimeSnapshotValidationError("global_runtime_facts.runtime_last_refresh_ts_ms must be an integer")
    validate_state(global_runtime_facts["runtime_data_freshness_state"], ALLOWED_FRESHNESS_STATES, "global_runtime_facts.runtime_data_freshness_state")

    product_family_facts = payload["product_family_facts"]
    if not isinstance(product_family_facts, dict):
        raise RuntimeSnapshotValidationError("product_family_facts must be an object")

    for product_family, facts in product_family_facts.items():
        if product_family not in PRODUCT_FAMILIES:
            raise RuntimeSnapshotValidationError(f"unknown product family: {product_family}")
        if not isinstance(facts, dict):
            raise RuntimeSnapshotValidationError(f"product_family_facts.{product_family} must be an object")
        for key in ["exchange_permission_fact", "account_permission_fact"]:
            if key not in facts:
                raise RuntimeSnapshotValidationError(f"missing {product_family} fact field: {key}")
            validate_state(facts[key], ALLOWED_PERMISSION_FACTS, f"product_family_facts.{product_family}.{key}")

    health_telemetry = payload.get("health_telemetry")
    if health_telemetry is not None:
        if not isinstance(health_telemetry, dict):
            raise RuntimeSnapshotValidationError("health_telemetry must be an object when present")
        gates = health_telemetry.get("gates")
        if gates is not None:
            if not isinstance(gates, dict):
                raise RuntimeSnapshotValidationError("health_telemetry.gates must be an object")
            for key, value in gates.items():
                validate_state(value, ALLOWED_GATE_STATES, f"health_telemetry.gates.{key}")
