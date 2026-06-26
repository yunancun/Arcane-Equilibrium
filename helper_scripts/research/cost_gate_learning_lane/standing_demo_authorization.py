#!/usr/bin/env python3
"""Validate standing Demo authorization envelopes for review-only lanes."""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

from cost_gate_learning_lane.contract import (
    STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
    STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
)


ALLOWED_STANDING_DEMO_SCOPES = {"demo_api_only_bounded_probe"}
ALLOWED_STANDING_DEMO_ENVIRONMENTS = {"demo", "live_demo"}
TRUTHY_AUTHORITY_STRINGS = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enabled",
    "grant",
    "granted",
    "authorize",
    "authorized",
}
AUTHORITY_CONTAMINATION_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "order_authority_granted",
    "order_submission_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "runtime_mutation_performed",
    "runtime_order_authority_granted",
    "runtime_probe_authority_granted",
    "service_restart_performed",
    "writer_enabled",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value)) and value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def parse_utc_datetime(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def summarize_standing_demo_authorization(
    standing_authorization: dict[str, Any] | None,
    artifact: dict[str, Any],
    *,
    now_utc: dt.datetime,
    max_authorization_ttl_hours: int,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _dict(standing_authorization)
    answers = _dict(payload.get("answers"))
    standing_id = _str(
        payload.get("standing_authorization_id") or payload.get("authorization_id")
    )
    operator_id = _str(payload.get("operator_id"))
    environment = _str(payload.get("environment")).lower()
    scope = _str(payload.get("scope") or payload.get("authorization_scope")).lower()
    expires_at = parse_utc_datetime(payload.get("expires_at_utc"))
    max_expires_at = now_utc + dt.timedelta(hours=max_authorization_ttl_hours)
    expiry_valid = (
        expires_at is not None
        and expires_at > now_utc
        and expires_at <= max_expires_at
    )
    cap = _int(payload.get("max_authorized_probe_orders_per_candidate"))
    demo_only = payload.get("demo_only") is True
    environment_valid = environment in ALLOWED_STANDING_DEMO_ENVIRONMENTS
    scope_valid = scope in ALLOWED_STANDING_DEMO_SCOPES
    candidate_scoping_required = payload.get("candidate_scoping_required") is True
    candidate_scope = _candidate_scope(payload)
    candidate_scope_matches = _candidate_scope_matches(candidate_scope, candidate)
    live_authority_granted = (
        _truthy_authority(payload.get("live_authority_granted"))
        or _truthy_authority(answers.get("live_authority_granted"))
        or environment in {"live", "mainnet"}
    )
    runtime_authority_granted = (
        _truthy_authority(payload.get("active_runtime_probe_authority"))
        or _truthy_authority(payload.get("active_runtime_order_authority"))
        or _truthy_authority(answers.get("active_runtime_probe_authority"))
        or _truthy_authority(answers.get("active_runtime_order_authority"))
        or _truthy_authority(answers.get("runtime_probe_authority_granted"))
        or _truthy_authority(answers.get("runtime_order_authority_granted"))
    )
    cost_gate_lowering = (
        _truthy_authority(payload.get("global_cost_gate_lowering_recommended"))
        or _truthy_authority(answers.get("global_cost_gate_lowering_recommended"))
        or payload.get("main_cost_gate_adjustment") not in (None, "", "NONE")
        or answers.get("main_cost_gate_adjustment") not in (None, "", "NONE")
    )
    promotion = (
        _truthy_authority(payload.get("promotion_evidence"))
        or _truthy_authority(payload.get("promotion_proof"))
        or _truthy_authority(answers.get("promotion_evidence"))
        or _truthy_authority(answers.get("promotion_proof"))
    )
    authority_contamination = _contains_authority_contamination(payload)
    safe = not (
        live_authority_granted
        or runtime_authority_granted
        or cost_gate_lowering
        or promotion
        or authority_contamination
    )
    schema_valid = artifact.get("schema_version") == STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION
    status_active = payload.get("status") == STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS
    valid = (
        artifact.get("status") == "FRESH"
        and schema_valid
        and status_active
        and safe
        and demo_only
        and environment_valid
        and scope_valid
        and candidate_scoping_required
        and candidate_scope_matches
        and bool(standing_id)
        and bool(operator_id)
        and expiry_valid
        and cap > 0
    )
    return {
        "status": payload.get("status"),
        "standing_authorization_id": standing_id or None,
        "operator_id": operator_id or None,
        "environment": environment or None,
        "scope": scope or None,
        "demo_only": demo_only,
        "environment_valid": environment_valid,
        "scope_valid": scope_valid,
        "candidate_scoping_required": candidate_scoping_required,
        "candidate_scope": candidate_scope,
        "candidate_scope_matches": candidate_scope_matches,
        "max_authorized_probe_orders_per_candidate": cap or None,
        "expires_at_utc": expires_at.isoformat() if expires_at else None,
        "max_authorization_ttl_hours": max_authorization_ttl_hours,
        "schema_valid": schema_valid,
        "status_active": status_active,
        "expiry_valid": expiry_valid,
        "safe": safe,
        "valid_for_candidate_scoped_authorization": valid,
        "live_authority_granted": live_authority_granted,
        "runtime_authority_granted": runtime_authority_granted,
        "cost_gate_lowering_recommended": cost_gate_lowering,
        "promotion_evidence": promotion,
        "authority_contamination": authority_contamination,
    }


def _candidate_scope(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(payload.get("candidate"))
    return {
        "side_cell_key": (
            payload.get("side_cell_key")
            or payload.get("selected_side_cell_key")
            or candidate.get("side_cell_key")
        ),
        "strategy_name": payload.get("strategy_name") or candidate.get("strategy_name"),
        "symbol": payload.get("symbol") or candidate.get("symbol"),
        "side": payload.get("side") or candidate.get("side"),
        "outcome_horizon_minutes": (
            payload.get("outcome_horizon_minutes")
            or candidate.get("outcome_horizon_minutes")
            or candidate.get("dominant_horizon_minutes")
        ),
    }


def _candidate_scope_matches(
    candidate_scope: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> bool:
    expected = _dict(candidate)
    if not any(_str(value) for value in candidate_scope.values()):
        return True
    for key, value in candidate_scope.items():
        text = _str(value)
        if text and text != _str(expected.get(key)):
            return False
    return True


def _contains_authority_contamination(payload: dict[str, Any]) -> bool:
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if key in AUTHORITY_CONTAMINATION_TRUE_KEYS and _truthy_authority(value):
                return True
            if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                return True
            if key == "order_authority" and value not in (None, "", "NOT_GRANTED"):
                return True
            if isinstance(value, (dict, list)):
                stack.append(value)
    return False
