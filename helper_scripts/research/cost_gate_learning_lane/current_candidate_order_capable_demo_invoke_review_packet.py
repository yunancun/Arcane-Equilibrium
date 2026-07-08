#!/usr/bin/env python3
"""Build the E3/BB review packet for an order-capable Demo invocation.

This packet is deliberately pre-execution. It verifies that the latest source
contract, runtime standing authorization, canonical bounded Demo plan, renewed
no-order active BBO window, and strict order/fill scan can be handed to E3/BB
for an exchange-facing review. It does not acquire a lease, call Bybit, submit
orders, mutate runtime state, or grant order authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

_RESEARCH_ROOT = Path(__file__).resolve().parents[1]
if str(_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_ROOT))

from cost_gate_learning_lane import bounded_probe_active_order_wiring_contract as wiring


SCHEMA_VERSION = "current_candidate_order_capable_demo_invoke_review_packet_v1"
SIGNOFF_SCHEMA_VERSION = (
    "current_candidate_order_capable_demo_invoke_review_signoff_v1"
)

READY_STATUS = "CURRENT_CANDIDATE_ORDER_CAPABLE_DEMO_INVOKE_REVIEW_PACKET_READY"
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_ORDER_CAPABLE_DEMO_INVOKE_REVIEW_PACKET_BLOCKED_BY_LOSS_CONTROL"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

E3_ROLE = "E3"
BB_ROLE = "BB"
APPROVE_DECISION = "APPROVE_ORDER_CAPABLE_DEMO_INVOKE_REVIEW_WITH_CONDITIONS"
TEMPLATE_DECISION = "REVIEW_REQUIRED_NO_APPROVAL_TEMPLATE"

DEFAULT_MAX_SOURCE_CONTRACT_AGE_SECONDS = 6 * 60 * 60
DEFAULT_MAX_AUTH_REMAINING_SECONDS = 15 * 60
DEFAULT_MAX_RENEWED_NO_ORDER_AGE_SECONDS = 3 * 60 * 60

ACTIVE_BLOCKER_ID = (
    "P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE"
)
NEXT_BLOCKER_ID = ACTIVE_BLOCKER_ID

BOUNDARY = (
    "order-capable Demo invocation E3/BB review packet only; no approval by "
    "this packet, no Decision Lease acquire/release, no Bybit call, no private "
    "or order endpoint, no order/cancel/modify, no PG query/write, no runtime/"
    "service/env/crontab/risk mutation, no Cost Gate lowering, no live/mainnet "
    "authority, no execution/fill/PnL, and no profit proof"
)

FORBIDDEN_OUTPUT_TRUE_KEYS = {
    "approval_granted_by_this_packet",
    "approval_granted",
    "order_submission_allowed_by_this_packet",
    "order_submission_allowed",
    "order_capable_action_allowed_by_this_packet",
    "order_capable_action_allowed",
    "allowed_to_submit_order",
    "allowed_by_this_packet",
    "order_submission_performed",
    "order_cancel_performed",
    "order_modify_performed",
    "bybit_call_allowed",
    "bybit_private_call_performed",
    "bybit_order_endpoint_allowed_by_this_packet",
    "decision_lease_allowed",
    "operator_auth_authorize",
    "order_or_probe_authority_granted",
    "private_endpoint_allowed",
    "private_or_order_endpoint_called",
    "order_endpoint_allowed",
    "pg_query_performed",
    "pg_write_performed",
    "db_or_pg_write",
    "runtime_mutation_performed",
    "runtime_mutation_allowed",
    "runtime_config_service_mutation",
    "service_restart_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering",
    "global_cost_gate_lowering_recommended",
    "risk_expansion",
    "live_authority_granted",
    "mainnet_authority_granted",
    "live_or_mainnet",
    "promotion_proof",
    "proof_or_promotion_claim",
    "profit_proof",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value)) and value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
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
            "approve",
            "approved",
        }
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


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approval_report_review(
    *,
    role: str,
    expected_sha256: Any,
    path: Path | None,
) -> dict[str, Any]:
    role_key = role.lower()
    expected = _str(expected_sha256)
    actual = _sha256(path)
    blockers: list[str] = []
    verdict = None
    text = ""
    if not expected:
        blockers.append(f"renewed_active_bbo_{role_key}_report_sha_missing")
    if path is None:
        blockers.append(f"renewed_active_bbo_{role_key}_report_path_missing")
    elif actual is None:
        blockers.append(f"renewed_active_bbo_{role_key}_report_missing")
    else:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("VERDICT:"):
                verdict = stripped.removeprefix("VERDICT:").strip()
                break
        if expected and actual != expected:
            blockers.append(f"renewed_active_bbo_{role_key}_report_sha_mismatch")
        if verdict != "APPROVE_WITH_CONDITIONS":
            blockers.append(
                f"renewed_active_bbo_{role_key}_report_verdict_not_approved_with_conditions"
            )
    return {
        "path": str(path) if path else None,
        "expected_sha256": expected or None,
        "actual_sha256": actual,
        "verdict": verdict,
        "approved_with_conditions": not blockers,
        "blockers": blockers,
    }


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _candidate_from_side_cell(side_cell_key: str | None) -> dict[str, Any]:
    text = _str(side_cell_key)
    parts = text.split("|")
    return {
        "side_cell_key": text or None,
        "strategy_name": parts[0] if len(parts) == 3 else None,
        "symbol": parts[1] if len(parts) == 3 else None,
        "side": parts[2] if len(parts) == 3 else None,
        "outcome_horizon_minutes": None,
    }


def _complete_candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    identity = _candidate_identity(candidate)
    side_cell = _candidate_from_side_cell(_str(identity.get("side_cell_key")))
    for key in ("strategy_name", "symbol", "side"):
        if identity.get(key) is None:
            identity[key] = side_cell.get(key)
    return identity


def _candidate_aligned(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left.get("side_cell_key") or not right.get("side_cell_key"):
        return False
    left_key = _candidate_key(left)
    right_key = _candidate_key(right)
    if None in left_key or None in right_key:
        return left.get("side_cell_key") == right.get("side_cell_key")
    return left_key == right_key


def _add_authority_check(
    checks: dict[str, list[Any]],
    key: str,
    value: Any,
) -> None:
    checks.setdefault(key, []).append(value)


def _authority_check_failed(values: list[Any], *, required: bool) -> bool:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return required
    return any(value is not False for value in present_values)


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    runtime_path: str | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    data = _dict(payload)
    return {
        "name": name,
        "snapshot_path": str(path) if path else None,
        "runtime_path": runtime_path,
        "sha256": _sha256(path),
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "generated_at_utc": data.get("generated_at_utc"),
    }


def _age_seconds(payload: dict[str, Any], now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(payload.get("generated_at_utc"))
    if parsed is None:
        return None
    return max(0.0, (now_utc - parsed).total_seconds())


def _remaining_seconds(expires_at: Any, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(expires_at)
    if parsed is None:
        return None
    return (parsed - now_utc).total_seconds()


def _false_answers() -> dict[str, Any]:
    return {
        "review_packet_ready": False,
        "approval_granted_by_this_packet": False,
        "order_capable_action_allowed_by_this_packet": False,
        "order_submission_allowed_by_this_packet": False,
        "bybit_order_endpoint_allowed_by_this_packet": False,
        "allowed_to_submit_order": False,
        "order_submission_performed": False,
        "order_cancel_performed": False,
        "order_modify_performed": False,
        "bybit_call_performed": False,
        "bybit_private_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
        "service_restart_performed": False,
        "cost_gate_lowering_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "risk_expansion": False,
        "live_authority_granted": False,
        "mainnet_authority_granted": False,
        "main_cost_gate_adjustment": "NONE",
        "promotion_proof": False,
        "profit_proof": False,
    }


def _check_output_authority(packet: dict[str, Any]) -> str | None:
    stack: list[tuple[str, Any]] = [("$", packet)]
    while stack:
        path, node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}"
                if key in FORBIDDEN_OUTPUT_TRUE_KEYS and _truthy(value):
                    return child_path
                if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                    return child_path
                stack.append((child_path, value))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                stack.append((f"{path}[{index}]", item))
    return None


def _validate_source_contract(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    data = _dict(payload)
    answers = _dict(data.get("answers"))
    candidate = _candidate_identity(_dict(data.get("candidate")))
    blockers: list[str] = []
    authority: list[str] = []
    if data.get("schema_version") != wiring.ACTIVE_ORDER_WIRING_CONTRACT_SCHEMA_VERSION:
        blockers.append("active_order_contract_schema_mismatch")
    if data.get("status") != wiring.READY_STATUS:
        blockers.append("active_order_contract_status_not_ready")
    if _dict(data.get("source_contract")).get("missing_requirements") not in ([], None):
        blockers.append("active_order_contract_missing_requirements")
    if answers.get("source_contract_ready_for_e3_bb_review") is not True:
        blockers.append("active_order_contract_not_ready_for_e3_bb_review")
    for key in (
        "active_runtime_order_authority",
        "active_runtime_probe_authority",
        "order_authority_granted",
        "probe_authority_granted",
        "order_submission_performed",
        "pg_write_performed",
        "runtime_mutation_performed",
        "live_authority_granted",
        "promotion_proof",
    ):
        if answers.get(key) is not False:
            authority.append(f"active_order_contract_{key}_not_false")
    if answers.get("main_cost_gate_adjustment") != "NONE":
        authority.append("active_order_contract_cost_gate_adjustment_not_none")
    age = _age_seconds(data, now_utc)
    if age is None:
        blockers.append("active_order_contract_generated_at_missing_or_invalid")
    elif age > max_age_seconds:
        blockers.append("active_order_contract_stale")
    return {
        "candidate": candidate,
        "age_seconds": age,
        "blockers": blockers,
        "authority_violations": authority,
    }


def _validate_standing_auth(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    min_remaining_seconds: int,
    expected_candidate: dict[str, Any],
) -> dict[str, Any]:
    data = _dict(payload)
    answers = _dict(data.get("answers"))
    risk_cap_lineage = _dict(data.get("risk_cap_lineage"))
    candidate = _candidate_identity(_dict(data.get("candidate")))
    blockers: list[str] = []
    authority: list[str] = []
    if data.get("schema_version") != "standing_demo_operator_authorization_v1":
        blockers.append("standing_demo_auth_schema_mismatch")
    if data.get("status") != "STANDING_DEMO_AUTHORIZATION_ACTIVE":
        blockers.append("standing_demo_auth_not_active")
    if data.get("demo_only") is not True:
        blockers.append("standing_demo_auth_not_demo_only")
    if not _candidate_aligned(candidate, expected_candidate):
        blockers.append("standing_demo_auth_candidate_mismatch")
    remaining = _remaining_seconds(data.get("expires_at_utc"), now_utc)
    if remaining is None:
        blockers.append("standing_demo_auth_expiry_missing_or_invalid")
    elif remaining <= min_remaining_seconds:
        blockers.append("standing_demo_auth_expired_or_too_close_to_expiry")
    for key in (
        "active_runtime_order_authority",
        "active_runtime_probe_authority",
        "order_authority_granted",
        "probe_authority_granted",
        "order_submission_performed",
        "runtime_mutation_performed",
        "live_authority_granted",
        "promotion_proof",
    ):
        if answers.get(key) is not False:
            authority.append(f"standing_auth_{key}_not_false")
    if answers.get("main_cost_gate_adjustment") != "NONE":
        authority.append("standing_auth_cost_gate_adjustment_not_none")
    return {
        "candidate": candidate,
        "expires_at_utc": data.get("expires_at_utc"),
        "remaining_seconds": remaining,
        "resolved_cap_usdt": _float(risk_cap_lineage.get("resolved_cap_usdt")),
        "risk_cap_lineage": risk_cap_lineage,
        "blockers": blockers,
        "authority_violations": authority,
    }


def _validate_soak_plan(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    expected_candidate: dict[str, Any],
) -> dict[str, Any]:
    data = _dict(payload)
    operator_auth = _dict(data.get("operator_authorization"))
    plan_candidates = _list(data.get("probe_candidates"))
    candidate = _candidate_identity(_dict(plan_candidates[0])) if plan_candidates else {}
    blockers: list[str] = []
    if data.get("schema_version") != "cost_gate_demo_learning_lane_plan_v1":
        blockers.append("soak_plan_schema_mismatch")
    if data.get("status") != "READY_FOR_DEMO_LEARNING_PROBE":
        blockers.append("soak_plan_status_not_ready")
    if data.get("main_cost_gate_adjustment") != "NONE":
        blockers.append("soak_plan_main_cost_gate_adjustment_not_none")
    if not _candidate_aligned(candidate, expected_candidate):
        blockers.append("soak_plan_candidate_mismatch")
    if operator_auth.get("status") != "BOUNDED_DEMO_PROBE_AUTHORIZED":
        blockers.append("soak_plan_operator_auth_not_authorized")
    if operator_auth.get("main_cost_gate_adjustment") != "NONE":
        blockers.append("soak_plan_operator_auth_cost_gate_adjustment_not_none")
    if operator_auth.get("side_cell_key") != expected_candidate.get("side_cell_key"):
        blockers.append("soak_plan_operator_auth_candidate_mismatch")
    remaining = _remaining_seconds(operator_auth.get("expires_at_utc"), now_utc)
    if remaining is None or remaining <= 0:
        blockers.append("soak_plan_operator_auth_expired")
    return {
        "candidate": candidate,
        "operator_authorization_status": operator_auth.get("status"),
        "operator_authorization_expires_at_utc": operator_auth.get("expires_at_utc"),
        "operator_authorization_remaining_seconds": remaining,
        "materialized_order_authority_is_input_only": True,
        "max_authorized_probe_orders": operator_auth.get("max_authorized_probe_orders"),
        "max_demo_notional_usdt_per_order": _dict(_dict(plan_candidates[0]).get("guardrails")).get(
            "max_demo_notional_usdt_per_order"
        )
        if plan_candidates
        else None,
        "blockers": blockers,
    }


def _validate_renewed_manifest(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
    expected_candidate: dict[str, Any],
    e3_approval_report_path: Path | None,
    bb_approval_report_path: Path | None,
) -> dict[str, Any]:
    data = _dict(payload)
    answers = _dict(data.get("active_answers"))
    active_window = _dict(data.get("active_window"))
    phase_a = _dict(data.get("phase_a"))
    phase_b = _dict(data.get("phase_b"))
    post = _dict(data.get("post_governance_summary") or data.get("post_governance"))
    authority_boundary = _dict(data.get("authority_boundary"))
    candidate = _candidate_from_side_cell(_str(data.get("candidate")))
    blockers: list[str] = []
    authority: list[str] = []
    active_status = data.get("active_status") or active_window.get("status")
    phase_a_count = data.get("phase_a_request_count")
    if phase_a_count is None:
        phase_a_count = phase_a.get("request_count")
    phase_b_count = data.get("phase_b_request_count")
    if phase_b_count is None:
        phase_b_count = phase_b.get("request_count")
    gate_ready = answers.get("fresh_actual_admission_bbo_and_gate_ready_during_window")
    if gate_ready is None:
        gate_ready = (
            active_window.get("actual_admission_bbo_status_during_active_window")
            == "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER"
            and active_window.get("gate_evidence_status_during_active_window")
            == "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER"
        )
    lease_released = answers.get("lease_released_before_artifact")
    if lease_released is None:
        lease_released = active_window.get("lease_released_before_artifact")
    if data.get("schema_version") != "renewed_active_bbo_execution_manifest_v1":
        blockers.append("renewed_active_bbo_manifest_schema_mismatch")
    if data.get("state_transition") != "DONE_WITH_CONCERNS":
        blockers.append("renewed_active_bbo_state_transition_not_done_with_concerns")
    if active_status != "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER":
        blockers.append("renewed_active_bbo_window_not_done_no_order")
    e3_report_review = _approval_report_review(
        role=E3_ROLE,
        expected_sha256=data.get("e3_report_sha256"),
        path=e3_approval_report_path,
    )
    bb_report_review = _approval_report_review(
        role=BB_ROLE,
        expected_sha256=data.get("bb_report_sha256"),
        path=bb_approval_report_path,
    )
    if data.get("e3_decision") is not None:
        if data.get("e3_decision") != "APPROVE_WITH_CONDITIONS":
            blockers.append("renewed_active_bbo_e3_not_approved_with_conditions")
    else:
        blockers.extend(_list(e3_report_review.get("blockers")))
    if data.get("bb_decision") is not None:
        if data.get("bb_decision") != "APPROVE_WITH_CONDITIONS":
            blockers.append("renewed_active_bbo_bb_not_approved_with_conditions")
    else:
        blockers.extend(_list(bb_report_review.get("blockers")))
    if not _candidate_aligned(candidate, expected_candidate):
        blockers.append("renewed_active_bbo_candidate_mismatch")
    if gate_ready is not True:
        blockers.append("renewed_active_bbo_gate_not_ready_during_window")
    if lease_released is not True:
        blockers.append("renewed_active_bbo_lease_not_released_before_artifact")
    if _float(post.get("lease_count")) != 0.0 or _float(post.get("lease_live_count")) != 0.0:
        blockers.append("renewed_active_bbo_post_governance_lease_not_zero")
    post_risk_level = post.get("risk_level")
    if post_risk_level not in (None, "", "NORMAL"):
        blockers.append("renewed_active_bbo_post_governance_risk_level_not_normal")
    post_position_multiplier = post.get("position_size_multiplier")
    if (
        post_position_multiplier is not None
        and _float(post_position_multiplier) != 1.0
    ):
        blockers.append(
            "renewed_active_bbo_post_governance_position_size_multiplier_not_1"
        )
    if _float(phase_a_count) != 3.0:
        blockers.append("renewed_active_bbo_phase_a_request_count_not_3")
    if _float(phase_b_count) != 3.0:
        blockers.append("renewed_active_bbo_phase_b_request_count_not_3")
    authority_checks: dict[str, list[Any]] = {}
    for key in (
        "order_submission_performed",
        "order_cancel_performed",
        "order_modify_performed",
        "bybit_private_call_performed",
        "pg_write_performed",
        "runtime_mutation_performed",
        "service_restart_performed",
        "cost_gate_lowering_performed",
        "live_authority_granted",
        "mainnet_authority_granted",
        "promotion_proof",
        "operator_auth_authorize",
    ):
        _add_authority_check(authority_checks, key, answers.get(key))
    if authority_boundary:
        compact_checks = {
            "order_submission_performed": authority_boundary.get(
                "order_or_probe_authority_granted"
            ),
            "order_cancel_performed": authority_boundary.get(
                "order_or_probe_authority_granted"
            ),
            "order_modify_performed": authority_boundary.get(
                "order_or_probe_authority_granted"
            ),
            "bybit_private_call_performed": authority_boundary.get(
                "private_or_order_endpoint_called"
            ),
            "pg_write_performed": authority_boundary.get("db_or_pg_write"),
            "runtime_mutation_performed": authority_boundary.get(
                "runtime_config_service_mutation"
            ),
            "service_restart_performed": authority_boundary.get(
                "runtime_config_service_mutation"
            ),
            "cost_gate_lowering_performed": authority_boundary.get(
                "cost_gate_lowering"
            ),
            "live_authority_granted": authority_boundary.get("live_or_mainnet"),
            "mainnet_authority_granted": authority_boundary.get("live_or_mainnet"),
            "promotion_proof": authority_boundary.get("proof_or_promotion_claim"),
            "operator_auth_authorize": authority_boundary.get(
                "operator_auth_authorize"
            ),
        }
        for key, value in compact_checks.items():
            _add_authority_check(authority_checks, key, value)
    optional_authority_keys = {"operator_auth_authorize"}
    for key, values in authority_checks.items():
        if _authority_check_failed(
            values,
            required=key not in optional_authority_keys,
        ):
            authority.append(f"renewed_active_bbo_{key}_not_false")
    cost_gate_adjustments = [
        answers.get("main_cost_gate_adjustment"),
        (
            authority_boundary.get("main_cost_gate_adjustment")
            if authority_boundary
            else None
        ),
    ]
    if authority_boundary and authority_boundary.get("cost_gate_lowering") is False:
        cost_gate_adjustments.append("NONE")
    for value in cost_gate_adjustments:
        if value not in (None, "", "NONE"):
            authority.append("renewed_active_bbo_cost_gate_adjustment_not_none")
            break
    age = _age_seconds(data, now_utc)
    if age is None:
        blockers.append("renewed_active_bbo_manifest_generated_at_missing_or_invalid")
    elif age > max_age_seconds:
        blockers.append("renewed_active_bbo_manifest_stale_for_review_packet")
    return {
        "candidate": candidate,
        "age_seconds": age,
        "active_status": active_status,
        "active_lease_id": active_window.get("lease_id"),
        "active_quote_request_count": phase_b_count,
        "post_governance_lease_count": post.get("lease_count"),
        "post_governance_lease_live_count": post.get("lease_live_count"),
        "approval_reports": {
            E3_ROLE: e3_report_review,
            BB_ROLE: bb_report_review,
        },
        "blockers": blockers,
        "authority_violations": authority,
    }


def _validate_fill_scan(
    payload: dict[str, Any] | None,
    *,
    expected_candidate: dict[str, Any],
) -> dict[str, Any]:
    data = _dict(payload)
    candidate = _candidate_from_side_cell(_str(data.get("candidate")))
    blockers: list[str] = []
    if not _candidate_aligned(candidate, expected_candidate):
        blockers.append("strict_order_fill_scan_candidate_mismatch")
    if data.get("candidate_matched_actual_order_fill_evidence_present") is not False:
        blockers.append("candidate_matched_order_fill_evidence_already_present_review_first")
    return {
        "candidate": candidate,
        "candidate_matched_actual_order_fill_evidence_present": data.get(
            "candidate_matched_actual_order_fill_evidence_present"
        ),
        "blockers": blockers,
    }


def _review_focus(role: str) -> list[str]:
    if role == E3_ROLE:
        return [
            "verify_packet_grants_no_execution_or_order_authority",
            "verify_runtime_auth_plan_and_no_order_evidence_are_fresh_enough",
            "verify_secret_token_pg_service_runtime_mutation_absent",
            "verify_future_invocation_requires fresh Decision Lease and Rust authority",
            "verify live/mainnet and Cost Gate lowering remain denied",
        ]
    return [
        "verify Bybit scope remains Demo only and bounded",
        "verify no private/order endpoint is permitted by this packet",
        "verify future invocation must rebuild BBO/instrument/order shape in-window",
        "verify post-only near-touch and max one bounded order constraints",
        "verify candidate-matched fees/slippage/reconstructability are required after any order",
    ]


def _template_for_role(
    *,
    role: str,
    generated_at_utc: str,
    candidate_side_cell_key: str | None,
    packet_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SIGNOFF_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "role": role,
        "decision": TEMPLATE_DECISION,
        "candidate_side_cell_key": candidate_side_cell_key,
        "review_packet_sha256": packet_sha256,
        "answers": _false_answers(),
        "review_notes": [
            "This inert template is not an approval.",
            "Reviewer must replace decision only after reviewing the exact packet hash.",
        ],
    }


def build_order_capable_demo_invoke_review_packet(
    *,
    active_order_contract: dict[str, Any] | None,
    standing_demo_authorization: dict[str, Any] | None,
    bounded_demo_soak_plan: dict[str, Any] | None,
    renewed_active_bbo_manifest: dict[str, Any] | None,
    strict_order_fill_scan: dict[str, Any] | None,
    now_utc: dt.datetime | None = None,
    max_source_contract_age_seconds: int = DEFAULT_MAX_SOURCE_CONTRACT_AGE_SECONDS,
    min_auth_remaining_seconds: int = DEFAULT_MAX_AUTH_REMAINING_SECONDS,
    max_renewed_no_order_age_seconds: int = DEFAULT_MAX_RENEWED_NO_ORDER_AGE_SECONDS,
    active_order_contract_path: Path | None = None,
    active_order_contract_runtime_path: str | None = None,
    standing_demo_authorization_path: Path | None = None,
    standing_demo_authorization_runtime_path: str | None = None,
    bounded_demo_soak_plan_path: Path | None = None,
    bounded_demo_soak_plan_runtime_path: str | None = None,
    renewed_active_bbo_manifest_path: Path | None = None,
    renewed_active_bbo_manifest_runtime_path: str | None = None,
    strict_order_fill_scan_path: Path | None = None,
    strict_order_fill_scan_runtime_path: str | None = None,
    e3_approval_report_path: Path | None = None,
    bb_approval_report_path: Path | None = None,
    source_head: str | None = None,
    source_origin_main: str | None = None,
    source_branch_status: str | None = None,
    runtime_head: str | None = None,
    runtime_origin_main: str | None = None,
    runtime_branch_status: str | None = None,
) -> dict[str, Any]:
    if min_auth_remaining_seconds <= 0:
        raise ValueError("min_auth_remaining_seconds must be positive")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    generated = now.isoformat()

    source_review = _validate_source_contract(
        active_order_contract,
        now_utc=now,
        max_age_seconds=max_source_contract_age_seconds,
    )
    candidate = _complete_candidate_identity(_dict(source_review.get("candidate")))
    standing_review = _validate_standing_auth(
        standing_demo_authorization,
        now_utc=now,
        min_remaining_seconds=min_auth_remaining_seconds,
        expected_candidate=candidate,
    )
    plan_review = _validate_soak_plan(
        bounded_demo_soak_plan,
        now_utc=now,
        expected_candidate=candidate,
    )
    renewed_review = _validate_renewed_manifest(
        renewed_active_bbo_manifest,
        now_utc=now,
        max_age_seconds=max_renewed_no_order_age_seconds,
        expected_candidate=candidate,
        e3_approval_report_path=e3_approval_report_path,
        bb_approval_report_path=bb_approval_report_path,
    )
    fill_review = _validate_fill_scan(
        strict_order_fill_scan,
        expected_candidate=candidate,
    )

    loss_control_blockers = sorted(
        set(
            _list(source_review.get("blockers"))
            + _list(standing_review.get("blockers"))
            + _list(plan_review.get("blockers"))
            + _list(renewed_review.get("blockers"))
            + _list(fill_review.get("blockers"))
        )
    )
    candidate_symbol = _str(candidate.get("symbol"))
    if not candidate_symbol:
        loss_control_blockers.append("candidate_symbol_missing_for_public_request_scope")
        loss_control_blockers = sorted(set(loss_control_blockers))
    authority_violations = sorted(
        set(
            _list(source_review.get("authority_violations"))
            + _list(standing_review.get("authority_violations"))
            + _list(renewed_review.get("authority_violations"))
        )
    )

    answers = _false_answers()
    answers["review_packet_ready"] = not loss_control_blockers and not authority_violations

    plan_max_notional = _float(plan_review.get("max_demo_notional_usdt_per_order"))
    standing_resolved_cap = _float(standing_review.get("resolved_cap_usdt"))
    cap_candidates = [
        value for value in (plan_max_notional, standing_resolved_cap) if value is not None
    ]
    effective_future_order_cap = min(cap_candidates) if cap_candidates else None

    status: str
    reason: str
    if authority_violations:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "input_artifact_contains_execution_authority_or_mutation_contamination"
    elif loss_control_blockers:
        status = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "order_capable_demo_invoke_review_inputs_not_safe"
    else:
        status = READY_STATUS
        reason = "order_capable_demo_invoke_review_packet_ready_for_e3_bb_no_execution"

    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "status": status,
        "reason": reason,
        "active_blocker_id": ACTIVE_BLOCKER_ID,
        "next_blocker_id": NEXT_BLOCKER_ID,
        "candidate": candidate,
        "source": {
            "head": source_head,
            "origin_main": source_origin_main,
            "branch_status": source_branch_status,
        },
        "runtime": {
            "host": "trade-core",
            "head": runtime_head,
            "origin_main": runtime_origin_main,
            "branch_status": runtime_branch_status,
        },
        "artifacts": [
            _artifact_summary(
                name="active_order_contract",
                path=active_order_contract_path,
                runtime_path=active_order_contract_runtime_path,
                payload=active_order_contract,
            ),
            _artifact_summary(
                name="standing_demo_authorization",
                path=standing_demo_authorization_path,
                runtime_path=standing_demo_authorization_runtime_path,
                payload=standing_demo_authorization,
            ),
            _artifact_summary(
                name="bounded_demo_soak_plan",
                path=bounded_demo_soak_plan_path,
                runtime_path=bounded_demo_soak_plan_runtime_path,
                payload=bounded_demo_soak_plan,
            ),
            _artifact_summary(
                name="renewed_active_bbo_manifest",
                path=renewed_active_bbo_manifest_path,
                runtime_path=renewed_active_bbo_manifest_runtime_path,
                payload=renewed_active_bbo_manifest,
            ),
            _artifact_summary(
                name="strict_order_fill_scan",
                path=strict_order_fill_scan_path,
                runtime_path=strict_order_fill_scan_runtime_path,
                payload=strict_order_fill_scan,
            ),
        ],
        "reviews": {
            "source_contract": source_review,
            "standing_demo_authorization": standing_review,
            "bounded_demo_soak_plan": plan_review,
            "renewed_no_order_active_bbo_window": renewed_review,
            "strict_order_fill_scan": fill_review,
        },
        "requested_scope": {
            "review_packet_itself": {
                "approval_granted": False,
                "order_submission_allowed": False,
                "bybit_call_allowed": False,
                "decision_lease_allowed": False,
                "runtime_mutation_allowed": False,
            },
            "future_phase_0_after_e3_bb_approval": [
                "recheck source/runtime heads and auth/plan hashes",
                "rebuild no-authority equity/envelope/governance inputs",
                "stop if standing/bounded auth expires or candidate drifts",
            ],
            "future_phase_a_public_demo_market_data": {
                "allowed_http_requests_exact": [
                    "GET /v5/market/time",
                    f"GET /v5/market/tickers?category=linear&symbol={candidate_symbol}",
                    (
                        "GET /v5/market/instruments-info?"
                        f"category=linear&symbol={candidate_symbol}"
                    ),
                ],
                "max_public_get_count_per_window": 3,
                "private_endpoint_allowed": False,
                "order_endpoint_allowed": False,
            },
            "future_phase_b_active_lease_order_shape_gate": {
                "decision_lease_scope": "TRADE_ENTRY",
                "lease_ttl_seconds_max": 5,
                "must_rebuild_bbo_instrument_order_shape_while_lease_live": True,
                "must_revalidate_guardian_rust_authority_audit_reconstructability": True,
                "released_no_order_lease_reuse_allowed": False,
            },
            "future_phase_c_conditional_single_bounded_demo_order": {
                "allowed_by_this_packet": False,
                "requires_separate_e3_bb_approval_on_this_packet_hash": True,
                "requires_all_phase_0_a_b_gates_ready": True,
                "max_orders": 1,
                "demo_only": True,
                "post_only_near_touch_limit_or_skip": True,
                "max_notional_usdt_from_plan": plan_max_notional,
                "current_standing_resolved_cap_usdt": standing_resolved_cap,
                "effective_future_order_cap_usdt": effective_future_order_cap,
                "effective_future_order_cap_source": (
                    "min(bounded_demo_soak_plan.max_demo_notional_usdt_per_order, "
                    "standing_demo_authorization.risk_cap_lineage.resolved_cap_usdt)"
                ),
                "must_record_candidate_matched_order_fill_fee_slippage_lineage": True,
            },
        },
        "requested_review_decision": {
            E3_ROLE: "Approve with conditions, reject, or block this no-execution order-capable invocation review packet.",
            BB_ROLE: "Approve with conditions, reject, or block the Demo Bybit endpoint/order-shape constraints in this no-execution packet.",
            "allowed_decisions": [
                APPROVE_DECISION,
                "REJECT",
                "BLOCKED_NEEDS_PM_REFRESH",
            ],
        },
        "requested_roles": [
            {
                "role": role,
                "required_schema_version": SIGNOFF_SCHEMA_VERSION,
                "required_decision_after_review": APPROVE_DECISION,
                "template_decision": TEMPLATE_DECISION,
                "template_is_approval": False,
                "review_focus": _review_focus(role),
                "signoff_template": _template_for_role(
                    role=role,
                    generated_at_utc=generated,
                    candidate_side_cell_key=candidate.get("side_cell_key"),
                    packet_sha256=None,
                ),
            }
            for role in (E3_ROLE, BB_ROLE)
        ],
        "loss_control_blockers": loss_control_blockers,
        "authority_boundary_violations": authority_violations,
        "max_safe_next_action": (
            "HAND_PACKET_SHA_TO_E3_AND_BB_FOR_EXPLICIT_REVIEW_NO_EXECUTION"
            if status == READY_STATUS
            else "REPAIR_OR_REFRESH_INPUTS_NO_EXECUTION"
        ),
        "answers": answers,
        "boundary": BOUNDARY,
    }

    output_violation = _check_output_authority(packet)
    if output_violation:
        packet["status"] = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        packet["reason"] = f"packet_contains_forbidden_authority_field:{output_violation}"
        packet["answers"]["review_packet_ready"] = False
        packet["authority_boundary_violations"] = sorted(
            set(packet["authority_boundary_violations"] + [output_violation])
        )
        packet["max_safe_next_action"] = "REPAIR_PACKET_SCHEMA_NO_EXECUTION"
    return packet


def render_markdown(packet: dict[str, Any]) -> str:
    answers = _dict(packet.get("answers"))
    candidate = _dict(packet.get("candidate"))
    lines = [
        "# Current Candidate Order-Capable Demo Invoke Review Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Active blocker: `{packet.get('active_blocker_id')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- Review packet ready: `{answers.get('review_packet_ready')}`",
        f"- Approval granted by this packet: `{answers.get('approval_granted_by_this_packet')}`",
        f"- Order submission allowed by this packet: `{answers.get('order_submission_allowed_by_this_packet')}`",
        f"- Max safe next action: `{packet.get('max_safe_next_action')}`",
        "",
        "## Loss-Control Blockers",
    ]
    blockers = _list(packet.get("loss_control_blockers"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Authority Boundary Violations"])
    violations = _list(packet.get("authority_boundary_violations"))
    lines.extend(f"- `{item}`" for item in violations) if violations else lines.append("- none")
    lines.extend(["", "## Requested Roles"])
    for role in _list(packet.get("requested_roles")):
        role_packet = _dict(role)
        lines.append(
            f"- `{role_packet.get('role')}`: template decision "
            f"`{role_packet.get('template_decision')}`; required decision "
            f"`{role_packet.get('required_decision_after_review')}`"
        )
    lines.extend(["", "## Boundary", "", str(packet.get("boundary", ""))])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-order-contract-json", type=Path, required=True)
    parser.add_argument("--active-order-contract-runtime-path")
    parser.add_argument("--standing-demo-authorization-json", type=Path, required=True)
    parser.add_argument("--standing-demo-authorization-runtime-path")
    parser.add_argument("--bounded-demo-soak-plan-json", type=Path, required=True)
    parser.add_argument("--bounded-demo-soak-plan-runtime-path")
    parser.add_argument("--renewed-active-bbo-manifest-json", type=Path, required=True)
    parser.add_argument("--renewed-active-bbo-manifest-runtime-path")
    parser.add_argument("--strict-order-fill-scan-json", type=Path, required=True)
    parser.add_argument("--strict-order-fill-scan-runtime-path")
    parser.add_argument("--e3-approval-report", type=Path)
    parser.add_argument("--bb-approval-report", type=Path)
    parser.add_argument("--source-head")
    parser.add_argument("--source-origin-main")
    parser.add_argument("--source-branch-status")
    parser.add_argument("--runtime-head")
    parser.add_argument("--runtime-origin-main")
    parser.add_argument("--runtime-branch-status")
    parser.add_argument("--now-utc")
    parser.add_argument(
        "--max-source-contract-age-seconds",
        type=int,
        default=DEFAULT_MAX_SOURCE_CONTRACT_AGE_SECONDS,
    )
    parser.add_argument(
        "--min-auth-remaining-seconds",
        type=int,
        default=DEFAULT_MAX_AUTH_REMAINING_SECONDS,
    )
    parser.add_argument(
        "--max-renewed-no-order-age-seconds",
        type=int,
        default=DEFAULT_MAX_RENEWED_NO_ORDER_AGE_SECONDS,
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    now = _parse_dt(args.now_utc) if args.now_utc else None
    packet = build_order_capable_demo_invoke_review_packet(
        active_order_contract=_read_json(args.active_order_contract_json),
        standing_demo_authorization=_read_json(args.standing_demo_authorization_json),
        bounded_demo_soak_plan=_read_json(args.bounded_demo_soak_plan_json),
        renewed_active_bbo_manifest=_read_json(args.renewed_active_bbo_manifest_json),
        strict_order_fill_scan=_read_json(args.strict_order_fill_scan_json),
        now_utc=now,
        max_source_contract_age_seconds=args.max_source_contract_age_seconds,
        min_auth_remaining_seconds=args.min_auth_remaining_seconds,
        max_renewed_no_order_age_seconds=args.max_renewed_no_order_age_seconds,
        active_order_contract_path=args.active_order_contract_json,
        active_order_contract_runtime_path=args.active_order_contract_runtime_path,
        standing_demo_authorization_path=args.standing_demo_authorization_json,
        standing_demo_authorization_runtime_path=args.standing_demo_authorization_runtime_path,
        bounded_demo_soak_plan_path=args.bounded_demo_soak_plan_json,
        bounded_demo_soak_plan_runtime_path=args.bounded_demo_soak_plan_runtime_path,
        renewed_active_bbo_manifest_path=args.renewed_active_bbo_manifest_json,
        renewed_active_bbo_manifest_runtime_path=args.renewed_active_bbo_manifest_runtime_path,
        strict_order_fill_scan_path=args.strict_order_fill_scan_json,
        strict_order_fill_scan_runtime_path=args.strict_order_fill_scan_runtime_path,
        e3_approval_report_path=args.e3_approval_report,
        bb_approval_report_path=args.bb_approval_report,
        source_head=args.source_head,
        source_origin_main=args.source_origin_main,
        source_branch_status=args.source_branch_status,
        runtime_head=args.runtime_head,
        runtime_origin_main=args.runtime_origin_main,
        runtime_branch_status=args.runtime_branch_status,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
