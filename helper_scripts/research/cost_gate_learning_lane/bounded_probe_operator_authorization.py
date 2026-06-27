#!/usr/bin/env python3
"""Build a bounded Demo probe operator-authorization artifact.

This artifact is the review layer between "source is ready" and any future
bounded Demo probe plan inclusion. It can emit the exact
``bounded_demo_probe_operator_authorization_v1`` object consumed by runtime
admission, but it never edits a plan, enables a writer, submits an order, lowers
the Cost Gate, or marks promotion evidence.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.bounded_probe_authority_patch_readiness import (
    PATCH_READINESS_SCHEMA_VERSION,
)
from cost_gate_learning_lane.contract import (
    AUTHORITY_PATH_PATCH_READY_STATUS,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ORDER_AUTHORITY_GRANTED,
    STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
    STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
)
from cost_gate_learning_lane.standing_demo_authorization import (
    summarize_standing_demo_authorization as _standing_demo_authorization_summary,
)


OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION = (
    "bounded_demo_probe_operator_authorization_packet_v1"
)
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
PREFLIGHT_SCHEMA_VERSION = "sealed_horizon_bounded_demo_probe_preflight_v1"
FALSE_NEGATIVE_PREFLIGHT_SCHEMA_VERSION = (
    "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
)
SUPPORTED_PREFLIGHT_SCHEMA_VERSIONS = {
    PREFLIGHT_SCHEMA_VERSION,
    FALSE_NEGATIVE_PREFLIGHT_SCHEMA_VERSION,
}
PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION = (
    "bounded_demo_probe_placement_repair_plan_v1"
)
READY_PREFLIGHT_STATUS = "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
READY_PLACEMENT_STATUS = "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
READY_REVIEW_STATUS = "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW"
FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED_STATUS = (
    "FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED"
)
FALSE_NEGATIVE_PREFLIGHT_NOT_READY_STATUS = "FALSE_NEGATIVE_PREFLIGHT_NOT_READY"
REJECTED_STATUS = "REJECTED_FOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
DEFAULT_MAX_AUTHORIZATION_TTL_HOURS = 24
BOUNDARY = (
    "artifact-only bounded Demo probe operator authorization review; no plan "
    "mutation, writer enablement, PG query/write, Bybit call, order, config, "
    "risk, runtime mutation, main Cost Gate lowering, or promotion proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def _parse_dt(value: Any) -> dt.datetime | None:
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


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _generated_at(payload: dict[str, Any]) -> Any:
    return (
        payload.get("generated_at_utc")
        or payload.get("generated")
        or payload.get("ts_utc")
    )


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = _generated_at(payload or {}) if present else None
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    sha256 = None
    if path and path.exists() and path.is_file():
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": sha256,
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _authority_preserved(*payloads: dict[str, Any] | None) -> bool:
    danger_true_keys = {
        "global_cost_gate_lowering_recommended",
        "probe_authority_granted",
        "order_authority_granted",
        "promotion_evidence",
        "promotion_proof",
        "live_authority_granted",
        "active_runtime_probe_authority",
        "active_runtime_order_authority",
        "runtime_probe_authority_granted",
        "runtime_order_authority_granted",
        "plan_mutation_performed",
        "writer_enabled",
        "order_submission_performed",
        "runtime_mutation_performed",
        "bybit_call_performed",
        "pg_write_performed",
        "service_restart_performed",
    }
    stack: list[Any] = [_dict(payload) for payload in payloads]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if key in danger_true_keys and _truthy_authority(value):
                return False
            if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                return False
            if key == "order_authority" and value not in (None, "", "NOT_GRANTED"):
                return False
            if isinstance(value, (dict, list)):
                stack.append(value)
    return True


def _candidate_summary(
    candidate: dict[str, Any],
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}
    return {
        "side_cell_key": candidate.get("side_cell_key") or fallback.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": (
            candidate.get("outcome_horizon_minutes")
            or fallback.get("outcome_horizon_minutes")
        ),
    }


def _candidate_from_preflight(preflight: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(preflight)
    design = _dict(payload.get("bounded_demo_probe_design"))
    candidate = _dict(payload.get("candidate")) or _dict(design.get("candidate"))
    return _candidate_summary(candidate, payload)


def _candidate_from_placement(placement: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(placement)
    plan = _dict(payload.get("placement_repair_plan"))
    candidate = _dict(plan.get("candidate")) or _dict(payload.get("candidate"))
    return _candidate_summary(candidate)


def _candidate_from_readiness(readiness: dict[str, Any] | None) -> dict[str, Any]:
    placement = _dict(_dict(readiness).get("placement_repair_plan"))
    return _candidate_summary(_dict(placement.get("candidate")))


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _candidate_aligned(*candidates: dict[str, Any]) -> bool:
    keys = [_candidate_key(candidate) for candidate in candidates]
    if any(not key[0] for key in keys):
        return False
    return len(set(keys)) == 1


def _preflight_summary(
    preflight: dict[str, Any] | None,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    payload = _dict(preflight)
    answers = _dict(payload.get("answers"))
    design = _dict(payload.get("bounded_demo_probe_design"))
    limits = _dict(design.get("suggested_initial_probe_limits"))
    ready = (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version") in SUPPORTED_PREFLIGHT_SCHEMA_VERSIONS
        and payload.get("status") == READY_PREFLIGHT_STATUS
        and answers.get("ready_for_operator_bounded_demo_probe_authorization") is True
        and answers.get("probe_authority_granted") is not True
        and answers.get("order_authority_granted") is not True
        and answers.get("promotion_evidence") is not True
    )
    return {
        "schema_version": artifact.get("schema_version"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "ready_for_operator_authorization": ready,
        "candidate": _candidate_from_preflight(payload),
        "max_probe_intents_before_review": _int(
            limits.get("max_probe_intents_before_review")
        ),
        "max_demo_notional_usdt_per_order": _float(
            limits.get("max_demo_notional_usdt_per_order")
        ),
        "max_total_demo_notional_usdt_before_review": _float(
            limits.get("max_total_demo_notional_usdt_before_review")
        ),
        "cap_source": limits.get("cap_source"),
        "risk_source_of_truth": limits.get("risk_source_of_truth"),
        "per_trade_risk_pct_fraction": _float(
            limits.get("per_trade_risk_pct_fraction")
        ),
        "per_trade_risk_pct_display": _float(
            limits.get("per_trade_risk_pct_display")
        ),
        "local_10_usdt_cap_is_global_risk_authority": (
            limits.get("local_10_usdt_cap_is_global_risk_authority") is True
        ),
    }


def _placement_summary(
    placement: dict[str, Any] | None,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    payload = _dict(placement)
    plan = _dict(payload.get("placement_repair_plan"))
    limits = _dict(plan.get("probe_limits"))
    ready = (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version") == PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION
        and payload.get("status") == READY_PLACEMENT_STATUS
        and plan.get("order_mode") == "post_only_near_touch_or_skip"
        and plan.get("requires_separate_operator_authorization") is True
        and plan.get("active") is False
    )
    return {
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "ready_for_operator_authorization": ready,
        "candidate": _candidate_from_placement(payload),
        "order_mode": plan.get("order_mode"),
        "max_fresh_bbo_age_ms": _int(plan.get("max_fresh_bbo_age_ms")),
        "max_initial_passive_gap_bps": _float(
            plan.get("max_initial_passive_gap_bps")
        ),
        "max_probe_intents_before_review": _int(
            limits.get("max_probe_intents_before_review")
        ),
        "max_demo_notional_usdt_per_order": _float(
            limits.get("max_demo_notional_usdt_per_order")
        ),
        "cap_source": limits.get("cap_source"),
        "risk_source_of_truth": limits.get("risk_source_of_truth"),
        "per_trade_risk_pct_fraction": _float(
            limits.get("per_trade_risk_pct_fraction")
        ),
        "per_trade_risk_pct_display": _float(
            limits.get("per_trade_risk_pct_display")
        ),
        "local_10_usdt_cap_is_global_risk_authority": (
            limits.get("local_10_usdt_cap_is_global_risk_authority") is True
        ),
    }


def _patch_readiness_summary(
    readiness: dict[str, Any] | None,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    payload = _dict(readiness)
    answers = _dict(payload.get("answers"))
    ready = (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version") == PATCH_READINESS_SCHEMA_VERSION
        and payload.get("status") == AUTHORITY_PATH_PATCH_READY_STATUS
        and answers.get("rust_near_touch_authority_adapter_present") is True
        and answers.get("rust_authority_path_wiring_present") is True
        and answers.get("probe_authority_granted") is not True
        and answers.get("order_authority_granted") is not True
        and answers.get("promotion_evidence") is not True
    )
    return {
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "ready_for_operator_authorization": ready,
        "candidate": _candidate_from_readiness(payload),
        "rust_near_touch_authority_adapter_present": (
            answers.get("rust_near_touch_authority_adapter_present") is True
        ),
        "rust_authority_path_wiring_present": (
            answers.get("rust_authority_path_wiring_present") is True
        ),
    }


def _candidate_budget(
    preflight: dict[str, Any],
    placement: dict[str, Any],
) -> int:
    candidates = [
        _int(preflight.get("max_probe_intents_before_review")),
        _int(placement.get("max_probe_intents_before_review")),
    ]
    positives = [value for value in candidates if value > 0]
    return min(positives) if positives else 0


def _nearly_equal(left: float | None, right: float | None) -> bool:
    return (
        left is not None
        and right is not None
        and abs(left - right) <= max(1e-8, abs(right) * 1e-9)
    )


def _gui_risk_notional_limit_summary(
    *,
    preflight: dict[str, Any],
    placement: dict[str, Any],
    standing: dict[str, Any],
    standing_input_supplied: bool,
) -> dict[str, Any]:
    preflight_cap = _float(preflight.get("max_demo_notional_usdt_per_order"))
    placement_cap = _float(placement.get("max_demo_notional_usdt_per_order"))
    standing_risk = _dict(standing.get("risk_cap_lineage"))
    standing_cap = _float(standing_risk.get("resolved_cap_usdt"))
    preflight_source = _str(preflight.get("risk_source_of_truth")).lower()
    preflight_local_10 = preflight.get("local_10_usdt_cap_is_global_risk_authority") is True
    placement_local_10 = placement.get("local_10_usdt_cap_is_global_risk_authority") is True
    if standing_input_supplied:
        expected_cap = standing_cap
        source_valid = standing_risk.get("valid") is True
        preflight_matches = _nearly_equal(preflight_cap, standing_cap)
        placement_matches = _nearly_equal(placement_cap, standing_cap)
    else:
        expected_cap = preflight_cap
        source_valid = (
            "gui" in preflight_source
            and "riskconfig" in preflight_source
            and preflight_local_10 is False
        )
        preflight_matches = preflight_cap is not None and preflight_cap > 0.0
        placement_matches = _nearly_equal(placement_cap, preflight_cap)
    valid = (
        source_valid
        and preflight_matches
        and placement_matches
        and preflight_cap is not None
        and preflight_cap > 0.0
        and placement_cap is not None
        and placement_cap > 0.0
        and preflight_local_10 is False
        and placement_local_10 is False
    )
    return {
        "valid": valid,
        "expected_cap_usdt": expected_cap,
        "preflight_cap_usdt": preflight_cap,
        "placement_cap_usdt": placement_cap,
        "standing_cap_usdt": standing_cap,
        "standing_input_supplied": standing_input_supplied,
        "source_valid": source_valid,
        "preflight_matches_expected_cap": preflight_matches,
        "placement_matches_expected_cap": placement_matches,
        "preflight_risk_source_of_truth": preflight.get("risk_source_of_truth"),
        "placement_risk_source_of_truth": placement.get("risk_source_of_truth"),
        "preflight_cap_source": preflight.get("cap_source"),
        "placement_cap_source": placement.get("cap_source"),
        "preflight_local_10_usdt_cap_is_global_risk_authority": preflight_local_10,
        "placement_local_10_usdt_cap_is_global_risk_authority": placement_local_10,
    }


def _normalize_decision(decision: str | None) -> str:
    text = _str(decision).lower().replace("_", "-")
    if text in {"authorize", "approve", "approved", "approve-authorization"}:
        return "authorize"
    if text in {"reject", "rejected", "decline", "declined"}:
        return "reject"
    return "defer"


def expected_bounded_demo_probe_operator_authorization_typed_confirm(
    side_cell_key: Any,
    max_authorized_probe_orders: Any,
    authorization_id: Any,
) -> str:
    """Return the exact confirmation phrase for bounded probe authorization."""
    return (
        "authorize_bounded_demo_probe:"
        f"{_str(side_cell_key)}:{_int(max_authorized_probe_orders)}:{_str(authorization_id)}"
    )


def _bounded_demo_probe_operator_authorization_typed_confirm_template(
    side_cell_key: Any,
    candidate_budget: int,
) -> str:
    max_orders = (
        f"<max_authorized_probe_orders<=%d>" % candidate_budget
        if candidate_budget > 0
        else "<max_authorized_probe_orders>"
    )
    return (
        "authorize_bounded_demo_probe:"
        f"{_str(side_cell_key)}:{max_orders}:<authorization_id>"
    )


def _gate(
    name: str,
    passed: bool,
    *,
    status: str,
    reason: str,
    next_actions: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "status": status,
        "reason": reason,
        "next_actions": next_actions or [],
        "evidence": evidence or {},
    }


def _dedupe(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _preflight_gate_metadata(preflight_summary: dict[str, Any]) -> dict[str, Any]:
    schema = preflight_summary.get("schema_version")
    if schema == FALSE_NEGATIVE_PREFLIGHT_SCHEMA_VERSION:
        return {
            "name": "false_negative_preflight_ready",
            "reason": (
                "false-negative preflight must reach "
                "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION after "
                "operator review"
            ),
            "next_actions": [
                "operator_review_false_negative_candidate_with_exact_preflight_confirm"
            ],
        }
    return {
        "name": "sealed_horizon_preflight_ready",
        "reason": (
            "sealed preflight must reach "
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        "next_actions": ["refresh_or_complete_sealed_horizon_probe_preflight"],
    }


def _status_from_gates(
    *,
    decision: str,
    authorization_requested: bool,
    failed_gates: list[dict[str, Any]],
) -> str:
    failed_by_name = {gate["name"]: gate for gate in failed_gates}
    failed = set(failed_by_name)
    if "authority_boundary_preserved" in failed:
        return "AUTHORITY_BOUNDARY_VIOLATION"
    if "standing_demo_authorization_safe" in failed:
        return "AUTHORITY_BOUNDARY_VIOLATION"
    if "standing_demo_authorization_valid_for_candidate_scope" in failed:
        return "STANDING_DEMO_AUTHORIZATION_INVALID"
    if "false_negative_preflight_ready" in failed:
        gate = failed_by_name["false_negative_preflight_ready"]
        if gate.get("status") == "OPERATOR_REVIEW_REQUIRED":
            return FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED_STATUS
        return FALSE_NEGATIVE_PREFLIGHT_NOT_READY_STATUS
    if "sealed_horizon_preflight_ready" in failed:
        return "SEALED_HORIZON_PREFLIGHT_NOT_READY"
    if "gui_risk_notional_limit_valid" in failed:
        return "GUI_RISK_CAP_INPUT_REQUIRED_FOR_AUTHORIZATION_REVIEW"
    if "placement_repair_plan_ready" in failed:
        return "PLACEMENT_REPAIR_PLAN_NOT_READY"
    if "authority_path_patch_readiness_ready" in failed:
        return "AUTHORITY_PATH_PATCH_NOT_READY"
    if "candidate_alignment" in failed:
        return "CANDIDATE_ALIGNMENT_MISMATCH"
    if decision == "reject":
        return REJECTED_STATUS
    if decision != "authorize":
        return READY_REVIEW_STATUS
    if "authorization_id_present" in failed:
        return "AUTHORIZATION_ID_REQUIRED"
    if "operator_id_present" in failed:
        return "OPERATOR_ID_REQUIRED"
    if "standing_demo_operator_matches" in failed:
        return "STANDING_DEMO_AUTHORIZATION_OPERATOR_MISMATCH"
    if "probe_budget_valid" in failed:
        return "PROBE_BUDGET_REQUIRED_OR_EXCEEDS_SOURCE_LIMIT"
    if "authorization_expiry_valid" in failed:
        return "AUTHORIZATION_EXPIRY_REQUIRED_OR_INVALID"
    if "typed_confirm_matches" in failed:
        return "TYPED_CONFIRM_REQUIRED"
    if authorization_requested:
        return BOUNDED_PROBE_AUTHORIZED_STATUS
    return READY_REVIEW_STATUS


def _authorization_object(
    *,
    authorization_id: str,
    operator_id: str,
    side_cell_key: str,
    expires_at_utc: str,
    max_authorized_probe_orders: int,
) -> dict[str, Any]:
    return {
        "schema_version": BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
        "status": BOUNDED_PROBE_AUTHORIZED_STATUS,
        "authorization_id": authorization_id,
        "operator_id": operator_id,
        "side_cell_key": side_cell_key,
        "expires_at_utc": expires_at_utc,
        "authority_path_readiness_status": AUTHORITY_PATH_PATCH_READY_STATUS,
        "main_cost_gate_adjustment": "NONE",
        "order_authority": ORDER_AUTHORITY_GRANTED,
        "max_authorized_probe_orders": max_authorized_probe_orders,
        "probe_authority_granted": True,
        "order_authority_granted": True,
        "promotion_evidence": False,
    }


def _standing_demo_candidate_authorization_id(
    *,
    standing_authorization_id: str,
    side_cell_key: str,
    max_authorized_probe_orders: int,
    expires_at_utc: str,
) -> str:
    seed = "|".join(
        [
            standing_authorization_id,
            side_cell_key,
            str(max_authorized_probe_orders),
            expires_at_utc,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"standing-demo-{digest}"


def build_bounded_demo_probe_operator_authorization(
    *,
    preflight: dict[str, Any] | None,
    placement_repair_plan: dict[str, Any] | None,
    authority_patch_readiness: dict[str, Any] | None,
    standing_demo_authorization: dict[str, Any] | None = None,
    decision: str = "defer",
    operator_id: str | None = None,
    authorization_id: str | None = None,
    max_authorized_probe_orders: int | None = None,
    expires_at_utc: str | None = None,
    typed_confirm: str | None = None,
    review_note: str | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
    max_authorization_ttl_hours: int = DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    if max_authorization_ttl_hours < 1 or max_authorization_ttl_hours > 24 * 7:
        raise ValueError("max_authorization_ttl_hours must be in [1, 168]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    max_age_seconds = max_artifact_age_hours * 3600
    artifacts = {
        "sealed_horizon_probe_preflight": _artifact_summary(
            name="sealed_horizon_probe_preflight",
            path=paths.get("preflight"),
            payload=preflight,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "placement_repair_plan": _artifact_summary(
            name="placement_repair_plan",
            path=paths.get("placement_repair_plan"),
            payload=placement_repair_plan,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "authority_patch_readiness": _artifact_summary(
            name="authority_patch_readiness",
            path=paths.get("authority_patch_readiness"),
            payload=authority_patch_readiness,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "standing_demo_authorization": _artifact_summary(
            name="standing_demo_authorization",
            path=paths.get("standing_demo_authorization"),
            payload=standing_demo_authorization,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }
    preflight_summary = _preflight_summary(
        preflight,
        artifacts["sealed_horizon_probe_preflight"],
    )
    placement_summary = _placement_summary(
        placement_repair_plan,
        artifacts["placement_repair_plan"],
    )
    readiness_summary = _patch_readiness_summary(
        authority_patch_readiness,
        artifacts["authority_patch_readiness"],
    )
    candidate = _dict(preflight_summary.get("candidate"))
    standing_summary = _standing_demo_authorization_summary(
        standing_demo_authorization,
        artifacts["standing_demo_authorization"],
        now_utc=now,
        max_authorization_ttl_hours=max_authorization_ttl_hours,
        candidate=candidate,
    )
    aligned = _candidate_aligned(
        _dict(preflight_summary.get("candidate")),
        _dict(placement_summary.get("candidate")),
        _dict(readiness_summary.get("candidate")),
    )
    side_cell_key = _str(candidate.get("side_cell_key"))
    candidate_budget = _candidate_budget(preflight_summary, placement_summary)
    requested_budget = _int(max_authorized_probe_orders)
    auth_id = _str(authorization_id)
    normalized_decision = _normalize_decision(decision)
    authorization_requested = normalized_decision == "authorize"
    provided_operator = _str(operator_id)
    standing_operator = _str(standing_summary.get("operator_id"))
    standing_id = _str(standing_summary.get("standing_authorization_id"))
    operator = provided_operator
    if authorization_requested and not operator:
        operator = standing_operator
    standing_present = artifacts["standing_demo_authorization"].get("present") is True
    standing_input_supplied = standing_present or paths.get("standing_demo_authorization") is not None
    gui_risk_notional_limit = _gui_risk_notional_limit_summary(
        preflight=preflight_summary,
        placement=placement_summary,
        standing=standing_summary,
        standing_input_supplied=standing_input_supplied,
    )
    standing_operator_matches = not (
        authorization_requested
        and standing_present
        and bool(provided_operator)
        and bool(standing_operator)
        and provided_operator != standing_operator
    )
    standing_source_valid = bool(
        authorization_requested
        and not _str(typed_confirm)
        and standing_summary.get("valid_for_candidate_scoped_authorization") is True
        and standing_operator_matches
    )
    if standing_source_valid:
        standing_cap = _int(
            standing_summary.get("max_authorized_probe_orders_per_candidate")
        )
        if requested_budget <= 0 and candidate_budget > 0 and standing_cap > 0:
            requested_budget = min(candidate_budget, standing_cap)
        if not _str(expires_at_utc):
            expires_at_utc = _str(standing_summary.get("expires_at_utc"))
        if (
            not auth_id
            and standing_id
            and side_cell_key
            and requested_budget > 0
            and _str(expires_at_utc)
        ):
            auth_id = _standing_demo_candidate_authorization_id(
                standing_authorization_id=standing_id,
                side_cell_key=side_cell_key,
                max_authorized_probe_orders=requested_budget,
                expires_at_utc=_str(expires_at_utc),
            )
    preflight_ready_for_auth = preflight_summary["ready_for_operator_authorization"] is True
    exact_confirm_fields_present = (
        preflight_ready_for_auth
        and bool(side_cell_key)
        and requested_budget > 0
        and bool(auth_id)
    )
    expected_confirm = (
        expected_bounded_demo_probe_operator_authorization_typed_confirm(
            side_cell_key,
            requested_budget,
            auth_id,
        )
        if exact_confirm_fields_present
        else None
    )
    confirm_template = _bounded_demo_probe_operator_authorization_typed_confirm_template(
        side_cell_key,
        candidate_budget,
    )
    typed_confirm_readiness = (
        "READY"
        if preflight_ready_for_auth and exact_confirm_fields_present
        else "PREFLIGHT_NOT_READY"
        if not preflight_ready_for_auth
        else "MISSING_AUTHORIZATION_FIELDS"
    )
    provided_confirm = _str(typed_confirm)
    typed_confirm_matches = bool(provided_confirm) and expected_confirm is not None and provided_confirm == expected_confirm
    standing_authorization_valid = bool(
        authorization_requested
        and not provided_confirm
        and standing_summary.get("valid_for_candidate_scoped_authorization") is True
        and standing_operator_matches
        and requested_budget > 0
        and requested_budget
        <= _int(standing_summary.get("max_authorized_probe_orders_per_candidate"))
    )
    confirmation_source = None
    if authorization_requested:
        if typed_confirm_matches:
            confirmation_source = "exact_typed_confirm"
        elif standing_authorization_valid:
            confirmation_source = "standing_demo_authorization"
    expires_at = _parse_dt(expires_at_utc)
    expiry_valid = expires_at is not None and expires_at > now
    if expiry_valid:
        max_expires_at = now + dt.timedelta(hours=max_authorization_ttl_hours)
        expiry_valid = expires_at <= max_expires_at
        standing_expires = _parse_dt(standing_summary.get("expires_at_utc"))
        if standing_authorization_valid and standing_expires is not None:
            expiry_valid = expiry_valid and expires_at <= standing_expires
    expires_text = expires_at.isoformat() if expires_at is not None else _str(expires_at_utc)
    budget_valid = (
        requested_budget > 0
        and candidate_budget > 0
        and requested_budget <= candidate_budget
        and (
            not standing_authorization_valid
            or requested_budget
            <= _int(standing_summary.get("max_authorized_probe_orders_per_candidate"))
        )
    )
    authority_preserved = _authority_preserved(
        preflight,
        placement_repair_plan,
        authority_patch_readiness,
        standing_demo_authorization,
    )
    standing_safe = (
        not standing_present or standing_summary.get("safe") is True
    )
    preflight_gate_metadata = _preflight_gate_metadata(preflight_summary)

    gates = [
        _gate(
            "authority_boundary_preserved",
            authority_preserved,
            status="PRESERVED" if authority_preserved else "VIOLATED",
            reason="inputs must not already grant Cost Gate lowering, probe/order authority, or promotion proof",
            next_actions=["remove_authority_granting_input_before_authorization_review"],
        ),
        _gate(
            preflight_gate_metadata["name"],
            preflight_summary["ready_for_operator_authorization"] is True,
            status=str(preflight_summary.get("status") or "MISSING"),
            reason=preflight_gate_metadata["reason"],
            next_actions=preflight_gate_metadata["next_actions"],
            evidence=preflight_summary,
        ),
        _gate(
            "standing_demo_authorization_safe",
            standing_safe,
            status="SAFE" if standing_safe else "UNSAFE",
            reason=(
                "standing Demo authorization input must not carry live, runtime, "
                "Cost Gate, or promotion authority"
            ),
            next_actions=[
                "remove_or_reissue_standing_demo_authorization_without_live_runtime_or_promotion_authority"
            ],
            evidence=standing_summary,
        ),
        _gate(
            "standing_demo_authorization_valid_for_candidate_scope",
            (not standing_input_supplied)
            or standing_summary.get("valid_for_candidate_scoped_authorization") is True,
            status=(
                "VALID"
                if standing_summary.get("valid_for_candidate_scoped_authorization") is True
                else "INVALID"
            ),
            reason=(
                "supplied standing Demo authorization must be valid for the "
                "candidate-scoped bounded authorization review"
            ),
            next_actions=[
                "supply_fresh_candidate_scoped_standing_demo_authorization_or_remove_invalid_envelope"
            ],
            evidence=standing_summary,
        ),
        _gate(
            "gui_risk_notional_limit_valid",
            gui_risk_notional_limit["valid"] is True,
            status="VALID" if gui_risk_notional_limit["valid"] else "MISSING_OR_INVALID",
            reason=(
                "preflight and placement per-order notional caps must match "
                "GUI-backed Rust RiskConfig cap lineage; a local 10 USDT "
                "diagnostic cap is not authorization-grade risk control"
            ),
            next_actions=[
                "refresh_preflight_and_placement_with_gui_risk_cap_lineage"
            ],
            evidence=gui_risk_notional_limit,
        ),
        _gate(
            "placement_repair_plan_ready",
            placement_summary["ready_for_operator_authorization"] is True,
            status=str(placement_summary.get("status") or "MISSING"),
            reason="placement repair plan must be fresh and near-touch-or-skip ready",
            next_actions=["refresh_bounded_probe_placement_repair_plan"],
            evidence=placement_summary,
        ),
        _gate(
            "authority_path_patch_readiness_ready",
            readiness_summary["ready_for_operator_authorization"] is True,
            status=str(readiness_summary.get("status") or "MISSING"),
            reason="source readiness must confirm near-touch Adapter and authority-path wiring",
            next_actions=["refresh_bounded_probe_authority_patch_readiness"],
            evidence=readiness_summary,
        ),
        _gate(
            "candidate_alignment",
            aligned,
            status="ALIGNED" if aligned else "MISMATCH",
            reason="preflight, placement plan, and source readiness must name the same side-cell/horizon",
            next_actions=["regenerate_artifacts_for_one_matching_side_cell"],
            evidence={
                "preflight_candidate": preflight_summary.get("candidate"),
                "placement_candidate": placement_summary.get("candidate"),
                "readiness_candidate": readiness_summary.get("candidate"),
            },
        ),
        _gate(
            "authorization_id_present",
            (not authorization_requested) or bool(auth_id),
            status="PRESENT" if auth_id else "MISSING",
            reason="authorization requires a durable authorization id",
            next_actions=["set_authorization_id_before_authorizing_probe"],
        ),
        _gate(
            "operator_id_present",
            (not authorization_requested) or bool(operator),
            status="PRESENT" if operator else "MISSING",
            reason="authorization requires a non-empty operator id",
            next_actions=["set_operator_id_before_authorizing_probe"],
        ),
        _gate(
            "standing_demo_operator_matches",
            standing_operator_matches,
            status="MATCH" if standing_operator_matches else "MISMATCH",
            reason="explicit operator id must match the standing Demo authorization operator id",
            next_actions=["use_the_standing_demo_authorization_operator_id_or_reissue_authorization"],
            evidence={
                "operator_id": operator or None,
                "explicit_operator_id": provided_operator or None,
                "standing_operator_id": standing_operator or None,
            },
        ),
        _gate(
            "probe_budget_valid",
            (not authorization_requested) or budget_valid,
            status="VALID" if budget_valid else "MISSING_OR_EXCEEDS_SOURCE_LIMIT",
            reason="authorized probe orders must be positive and no larger than the source plan budget",
            next_actions=["set_max_authorized_probe_orders_lte_source_budget"],
            evidence={
                "requested_max_authorized_probe_orders": requested_budget,
                "source_candidate_max_probe_orders": candidate_budget,
            },
        ),
        _gate(
            "authorization_expiry_valid",
            (not authorization_requested) or expiry_valid,
            status="VALID" if expiry_valid else "MISSING_OR_INVALID",
            reason="authorization expiry must be future-dated and within the allowed TTL cap",
            next_actions=["set_short_future_expires_at_utc_before_authorization"],
            evidence={
                "expires_at_utc": expires_text or None,
                "max_authorization_ttl_hours": max_authorization_ttl_hours,
            },
        ),
        _gate(
            "typed_confirm_matches",
            (not authorization_requested)
            or typed_confirm_matches
            or standing_authorization_valid,
            status=(
                "MATCH"
                if typed_confirm_matches
                else "STANDING_DEMO_AUTHORIZATION"
                if standing_authorization_valid
                else "MISSING_OR_MISMATCH"
            ),
            reason=(
                "authorization requires either the exact typed confirmation phrase "
                "or a fresh standing Demo-only authorization that still scopes the "
                "emitted object to one candidate"
            ),
            next_actions=[
                "copy_exact_typed_confirm_or_supply_valid_standing_demo_authorization"
            ],
            evidence={
                "typed_confirm_expected": expected_confirm,
                "typed_confirm_template": confirm_template,
                "typed_confirm_readiness": typed_confirm_readiness,
                "typed_confirm_provided": bool(provided_confirm),
                "typed_confirm_matches": typed_confirm_matches,
                "standing_demo_authorization_valid": standing_authorization_valid,
                "authorization_confirmation_source": confirmation_source,
            },
        ),
    ]
    failed_gates = [gate for gate in gates if gate["passed"] is not True]
    status = _status_from_gates(
        decision=normalized_decision,
        authorization_requested=authorization_requested,
        failed_gates=failed_gates,
    )
    authorized = status == BOUNDED_PROBE_AUTHORIZED_STATUS
    operator_authorization = (
        _authorization_object(
            authorization_id=auth_id,
            operator_id=operator,
            side_cell_key=side_cell_key,
            expires_at_utc=expires_text,
            max_authorized_probe_orders=requested_budget,
        )
        if authorized
        else None
    )
    if authorized:
        next_actions = [
            "operator_review_plan_inclusion_of_bounded_probe_operator_authorization",
            "keep_main_cost_gate_adjustment_none",
            "after_probe_refresh_order_to_fill_result_and_execution_realism_reviews",
        ]
    elif status == READY_REVIEW_STATUS:
        next_actions = [
            "operator_may_authorize_bounded_demo_probe_with_exact_typed_confirm",
            "do_not_edit_plan_or_enable_writer_until_authorization_artifact_is_reviewed",
        ]
    elif status == REJECTED_STATUS:
        next_actions = [
            "keep_main_cost_gate_unchanged_and_continue_learning_collection",
            "do_not_include_operator_authorization_in_any_plan_for_this_review",
        ]
    else:
        next_actions = _dedupe(
            [
                action
                for gate in failed_gates
                for action in _list(gate.get("next_actions"))
            ]
        )

    return {
        "schema_version": OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(gate["name"] for gate in failed_gates)
        or normalized_decision,
        "decision": normalized_decision,
        "review_scope": "operator_authorization_artifact_only_not_plan_mutation",
        "operator_id": operator or None,
        "authorization_id": auth_id or None,
        "review_note": _str(review_note) or None,
        "candidate": candidate,
        "source_candidate_max_probe_orders": candidate_budget,
        "requested_max_authorized_probe_orders": requested_budget or None,
        "expires_at_utc": expires_text or None,
        "operator_authorization": operator_authorization,
        "gates": gates,
        "blocking_gate_count": len(failed_gates),
        "blocking_gates": [gate["name"] for gate in failed_gates],
        "next_actions": next_actions,
        "typed_confirm_expected": expected_confirm,
        "typed_confirm_template": confirm_template,
        "typed_confirm_readiness": typed_confirm_readiness,
        "typed_confirm_provided": bool(provided_confirm),
        "typed_confirm_matches": typed_confirm_matches,
        "authorization_confirmation_source": confirmation_source,
        "answers": {
            "ready_for_operator_authorization_review": status == READY_REVIEW_STATUS,
            "bounded_demo_probe_authorized": authorized,
            "operator_authorization_object_emitted": operator_authorization is not None,
            "plan_mutation_performed": False,
            "writer_enabled": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted_in_authorization_object": authorized,
            "order_authority_granted_in_authorization_object": authorized,
            "standing_demo_authorization_present": standing_present,
            "standing_demo_authorization_valid": standing_authorization_valid,
            "authorization_confirmation_source": confirmation_source,
        },
        "artifacts": artifacts,
        "preflight": preflight_summary,
        "placement_repair_plan": placement_summary,
        "authority_patch_readiness": readiness_summary,
        "standing_demo_authorization": standing_summary,
        "boundary": BOUNDARY,
    }
