#!/usr/bin/env python3
"""Build a no-authority bounded Demo preflight for false-negative candidates.

This packet bridges the Cost Gate false-negative review path into the existing
bounded Demo probe review chain. It consumes a no-authority autonomous
parameter proposal and a false-negative operator-review artifact, then emits a
candidate-matched bounded probe design. It never submits orders, mutates plans,
lowers the Cost Gate, grants probe/order authority, writes PG, calls Bybit, or
creates promotion proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.false_negative_operator_review import (
    APPROVED_FOR_PREFLIGHT_STATUS,
    FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION,
)
from cost_gate_learning_lane.standing_demo_authorization import (
    summarize_standing_demo_authorization,
)

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT_SCHEMA_VERSION = (
    "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
)
AUTONOMOUS_PARAMETER_PROPOSAL_SCHEMA_VERSION = (
    "cost_gate_autonomous_parameter_proposal_v1"
)
READY_PROPOSAL_STATUS = "REVIEWABLE_PARAMETER_PROPOSAL_READY"
READY_PREFLIGHT_STATUS = "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
OPERATOR_REVIEW_REQUIRED_STATUS = "OPERATOR_REVIEW_REQUIRED"
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
DEFAULT_MAX_STANDING_DEMO_AUTHORIZATION_TTL_HOURS = 24
BOUNDARY = (
    "artifact-only false-negative bounded Demo probe preflight; no PG query/"
    "write, Bybit call, order, config, risk, auth, runtime mutation, global "
    "Cost Gate lowering, probe authority, order authority, or promotion proof"
)


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
    source_error: str | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload) and source_error is None
    generated_at = _generated_at(payload or {}) if present else None
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if source_error:
        status = "UNAVAILABLE"
    elif not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
        "source_error": source_error,
    }


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "enabled",
            "grant",
            "granted",
            "authorize",
            "authorized",
        }
    return False


def _authority_preserved(*payloads: dict[str, Any] | None) -> bool:
    stack: list[Any] = [payload for payload in payloads if payload is not None]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        if data.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
        for key in (
            "global_cost_gate_lowering_recommended",
            "probe_authority_granted",
            "order_authority_granted",
            "active_runtime_probe_authority",
            "active_runtime_order_authority",
            "bounded_demo_probe_authorized",
            "operator_authorization_object_emitted",
            "promotion_evidence",
            "promotion_proof",
            "runtime_mutation_performed",
            "pg_write_performed",
            "bybit_call_performed",
            "order_submission_performed",
        ):
            if _truthy_authority(data.get(key)):
                return False
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return True


def _candidate_from_proposal(packet: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(packet)
    proposal = _dict(payload.get("proposal"))
    candidate = _dict(payload.get("candidate"))
    symbols = _list(proposal.get("symbols") or candidate.get("symbols"))
    sides = _list(proposal.get("sides") or candidate.get("sides"))
    return {
        "side_cell_key": proposal.get("side_cell_key") or candidate.get("side_cell_key"),
        "strategy_name": (_list(proposal.get("strategy_names") or candidate.get("strategy_names")) or [None])[0],
        "symbol": symbols[0] if symbols else None,
        "side": sides[0] if sides else None,
        "outcome_horizon_minutes": (
            proposal.get("dominant_horizon_minutes")
            or candidate.get("dominant_horizon_minutes")
        ),
        "source_kind": "cost_gate_false_negative_after_cost",
    }


def _candidate_from_review(packet: dict[str, Any] | None) -> dict[str, Any]:
    candidate = _dict(_dict(packet).get("candidate"))
    symbols = _list(candidate.get("symbols"))
    sides = _list(candidate.get("sides"))
    strategies = _list(candidate.get("strategy_names"))
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": strategies[0] if strategies else None,
        "symbol": symbols[0] if symbols else None,
        "side": sides[0] if sides else None,
        "outcome_horizon_minutes": (
            candidate.get("dominant_horizon_minutes")
            or (_list(candidate.get("horizon_minutes")) or [None])[0]
        ),
        "source_kind": "cost_gate_false_negative_after_cost",
    }


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _proposal_ready(packet: dict[str, Any], artifact: dict[str, Any]) -> bool:
    answers = _dict(packet.get("answers"))
    proposal = _dict(packet.get("proposal"))
    return (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version") == AUTONOMOUS_PARAMETER_PROPOSAL_SCHEMA_VERSION
        and packet.get("status") == READY_PROPOSAL_STATUS
        and proposal.get("proposal_status") == "INACTIVE_REVIEW_PACKET_ONLY"
        and answers.get("reviewable_parameter_proposal_emitted") is True
        and answers.get("bounded_demo_probe_authorized") is not True
        and answers.get("probe_authority_granted") is not True
        and answers.get("order_authority_granted") is not True
        and answers.get("promotion_evidence") is not True
    )


def _review_present(packet: dict[str, Any], artifact: dict[str, Any]) -> bool:
    answers = _dict(packet.get("answers"))
    return (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version") == FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION
        and bool(packet.get("selected_side_cell_key"))
        and answers.get("global_cost_gate_lowering_recommended") is not True
        and answers.get("probe_authority_granted") is not True
        and answers.get("order_authority_granted") is not True
        and answers.get("promotion_evidence") is not True
    )


def _review_approved(packet: dict[str, Any]) -> bool:
    answers = _dict(packet.get("answers"))
    return (
        packet.get("status") == APPROVED_FOR_PREFLIGHT_STATUS
        and packet.get("operator_review_approved_for_preflight") is True
        and answers.get("operator_review_approved_for_preflight") is True
        and answers.get("review_grants_runtime_authority") is not True
        and answers.get("bounded_demo_probe_authorized") is not True
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


def _status_from_gates(gates: list[dict[str, Any]], review_is_approved: bool) -> str:
    failed = {gate["name"] for gate in gates if gate.get("passed") is not True}
    if "authority_boundary_preserved" in failed:
        return "AUTHORITY_BOUNDARY_VIOLATION"
    if "standing_demo_authorization_valid_for_preflight" in failed:
        return "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT"
    if "gui_risk_cap_lineage_valid_for_preflight" in failed:
        return "GUI_RISK_CAP_INPUT_REQUIRED_FOR_PREFLIGHT"
    if "autonomous_parameter_proposal_ready" in failed:
        return "AUTONOMOUS_PARAMETER_PROPOSAL_NOT_READY"
    if "false_negative_operator_review_present" in failed:
        return "FALSE_NEGATIVE_OPERATOR_REVIEW_REQUIRED"
    if "candidate_alignment" in failed:
        return "CANDIDATE_ALIGNMENT_MISMATCH"
    if "false_negative_operator_review_approved_for_preflight" in failed:
        return OPERATOR_REVIEW_REQUIRED_STATUS
    if review_is_approved:
        return READY_PREFLIGHT_STATUS
    return OPERATOR_REVIEW_REQUIRED_STATUS


def _bounded_demo_probe_design(
    *,
    status: str,
    candidate: dict[str, Any],
    proposal: dict[str, Any],
    standing_summary: dict[str, Any],
) -> dict[str, Any]:
    review_ready = status in {
        OPERATOR_REVIEW_REQUIRED_STATUS,
        READY_PREFLIGHT_STATUS,
    }
    thesis = _dict(_dict(proposal.get("proposal")).get("profit_thesis"))
    risk_cap = _dict(standing_summary.get("risk_cap_lineage"))
    max_probe_orders = min(
        value
        for value in [
            3,
            _int(standing_summary.get("max_authorized_probe_orders_per_candidate")),
        ]
        if value > 0
    )
    resolved_cap = _float(risk_cap.get("resolved_cap_usdt"))
    max_total_cap = (
        round(resolved_cap * max_probe_orders, 8)
        if resolved_cap is not None and max_probe_orders > 0
        else None
    )
    return {
        "schema_version": "bounded_demo_probe_design_v1",
        "status": (
            "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION"
            if status == READY_PREFLIGHT_STATUS
            else "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN"
            if review_ready
            else "NOT_READY_FOR_OPERATOR_PROBE_REVIEW"
        ),
        "candidate": candidate,
        "evidence_snapshot": {
            "source": "cost_gate_autonomous_parameter_proposal_v1",
            "proposal_id": _dict(proposal.get("proposal")).get("proposal_id"),
            "avg_gross_bps": thesis.get("avg_gross_bps"),
            "avg_net_bps": thesis.get("avg_net_bps"),
            "avg_cost_bps": thesis.get("avg_cost_bps"),
            "net_positive_pct": thesis.get("net_positive_pct"),
            "net_cost_cushion_bps": thesis.get("net_cost_cushion_bps"),
            "wrongful_block_score": thesis.get("wrongful_block_score"),
            "outcome_count": thesis.get("outcome_count"),
        },
        "edge_amplification_levers": [
            "candidate_matched_cost_gate_review_without_global_lowering",
            "post_only_near_touch_or_skip_execution_realism",
            "matched_blocked_signal_controls",
            "regime_filter_if_demo_edge_compresses_after_fees_slippage",
        ],
        "suggested_initial_probe_limits": {
            "active": False,
            "requires_separate_operator_authorization": True,
            "max_probe_intents_before_review": max_probe_orders,
            "max_filled_probe_outcomes_before_review": 3,
            "max_total_filled_probe_outcomes_before_second_review": 10,
            "max_demo_notional_usdt_per_order": resolved_cap,
            "max_total_demo_notional_usdt_before_review": max_total_cap,
            "cap_source": (
                risk_cap.get("cap_source")
                or "standing_demo_authorization.risk_cap_lineage.resolved_cap_usdt"
            ),
            "risk_source_of_truth": risk_cap.get("risk_source_of_truth"),
            "per_trade_risk_pct_fraction": risk_cap.get(
                "per_trade_risk_pct_fraction"
            ),
            "per_trade_risk_pct_display": risk_cap.get(
                "per_trade_risk_pct_display"
            ),
            "local_10_usdt_cap_is_global_risk_authority": False,
            "environment": "demo_or_live_demo_only",
            "execution_path": "existing_rust_authority_path_only",
        },
        "success_criteria": {
            "min_filled_probe_outcomes_for_first_review": 3,
            "min_filled_probe_outcomes_for_learning_review": 10,
            "min_realized_avg_net_bps": 0.0,
            "min_realized_net_positive_pct": 60.0,
            "fees_slippage_and_fill_quality_recorded": True,
            "candidate_matched_controls_required": True,
            "promotion_evidence": False,
        },
        "stop_conditions": [
            "authority_boundary_violation",
            "main_cost_gate_adjustment_requested",
            "operator_review_missing_or_expired",
            "filled_probe_outcomes_reach_review_limit",
            "realized_avg_net_bps_nonpositive_after_first_review_sample",
            "realized_net_positive_pct_below_review_floor_after_first_review_sample",
            "order_fill_or_fee_lineage_gap_detected",
            "unattributed_fill_detected_for_candidate_window",
        ],
        "required_review_artifacts": [
            "candidate_matched_probe_admission_decision_rows",
            "demo_order_intent_and_order_state_rows",
            "fill_fee_slippage_rows",
            "matched_blocked_signal_control_outcomes",
            "bounded_probe_result_review",
            "bounded_probe_execution_realism_review",
        ],
        "authority_boundary": {
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def build_false_negative_bounded_demo_probe_preflight(
    *,
    autonomous_parameter_proposal: dict[str, Any] | None,
    false_negative_operator_review: dict[str, Any] | None,
    standing_demo_authorization: dict[str, Any] | None = None,
    autonomous_parameter_proposal_path: Path | None = None,
    false_negative_operator_review_path: Path | None = None,
    standing_demo_authorization_path: Path | None = None,
    autonomous_parameter_proposal_error: str | None = None,
    false_negative_operator_review_error: str | None = None,
    standing_demo_authorization_error: str | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
    max_authorization_ttl_hours: int = DEFAULT_MAX_STANDING_DEMO_AUTHORIZATION_TTL_HOURS,
) -> dict[str, Any]:
    """Build a fail-closed no-authority false-negative preflight packet."""
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    if max_authorization_ttl_hours < 1 or max_authorization_ttl_hours > 24 * 7:
        raise ValueError("max_authorization_ttl_hours must be in [1, 168]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    proposal = _dict(autonomous_parameter_proposal)
    review = _dict(false_negative_operator_review)
    standing_payload = _dict(standing_demo_authorization)
    artifacts = {
        "autonomous_parameter_proposal": _artifact_summary(
            name="autonomous_parameter_proposal",
            path=autonomous_parameter_proposal_path,
            payload=proposal,
            source_error=autonomous_parameter_proposal_error,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "false_negative_operator_review": _artifact_summary(
            name="false_negative_operator_review",
            path=false_negative_operator_review_path,
            payload=review,
            source_error=false_negative_operator_review_error,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "standing_demo_authorization": _artifact_summary(
            name="standing_demo_authorization",
            path=standing_demo_authorization_path,
            payload=standing_payload,
            source_error=standing_demo_authorization_error,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }
    proposal_candidate = _candidate_from_proposal(proposal)
    review_candidate = _candidate_from_review(review)
    aligned = (
        bool(proposal_candidate.get("side_cell_key"))
        and _candidate_key(proposal_candidate) == _candidate_key(review_candidate)
    )
    authority_preserved = _authority_preserved(proposal, review, standing_payload)
    proposal_ready = _proposal_ready(
        proposal,
        artifacts["autonomous_parameter_proposal"],
    )
    review_present = _review_present(
        review,
        artifacts["false_negative_operator_review"],
    )
    review_approved = _review_approved(review)
    standing_input_supplied = (
        bool(standing_payload)
        or standing_demo_authorization_path is not None
        or standing_demo_authorization_error not in (None, "missing_path")
    )
    review_uses_standing = (
        review.get("operator_review_approval_source") == "standing_demo_authorization"
        or _dict(review.get("answers")).get("standing_demo_authorization_consumed") is True
    )
    standing_summary = summarize_standing_demo_authorization(
        standing_payload,
        artifacts["standing_demo_authorization"],
        now_utc=now,
        max_authorization_ttl_hours=max_authorization_ttl_hours,
        candidate=proposal_candidate if proposal_candidate.get("side_cell_key") else review_candidate,
    )
    standing_valid_for_preflight = bool(
        standing_input_supplied
        and standing_summary.get("valid_for_candidate_scoped_authorization") is True
    )
    standing_gate_needed = standing_input_supplied or review_uses_standing
    risk_cap_summary = _dict(standing_summary.get("risk_cap_lineage"))
    gui_risk_cap_valid = bool(risk_cap_summary.get("valid") is True)
    gui_risk_cap_gate_needed = review_approved
    gates = [
        _gate(
            "authority_boundary_preserved",
            authority_preserved,
            status="PRESERVED" if authority_preserved else "VIOLATED",
            reason="inputs must not grant Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof",
            next_actions=["remove_authority_granting_input_before_preflight"],
        ),
    ]
    if standing_gate_needed:
        gates.append(
            _gate(
                "standing_demo_authorization_valid_for_preflight",
                standing_valid_for_preflight,
                status=(
                    "VALID"
                    if standing_valid_for_preflight
                    else str(artifacts["standing_demo_authorization"].get("status") or "MISSING")
                ),
                reason=(
                    "standing-sourced false-negative preflight approval must "
                    "carry the same fresh Demo-only scoped loss-control envelope"
                ),
                next_actions=[
                    "supply_same_valid_standing_demo_authorization_used_for_false_negative_review"
                ],
                evidence=standing_summary,
            )
        )
    if gui_risk_cap_gate_needed:
        gates.append(
            _gate(
                "gui_risk_cap_lineage_valid_for_preflight",
                gui_risk_cap_valid,
                status="VALID" if gui_risk_cap_valid else "MISSING_OR_INVALID",
                reason=(
                    "approved bounded Demo probe preflight must source per-order "
                    "notional from GUI-backed Rust RiskConfig, not a local 10 USDT "
                    "diagnostic cap"
                ),
                next_actions=[
                    "supply_standing_demo_authorization_with_gui_risk_cap_lineage"
                ],
                evidence=risk_cap_summary,
            )
        )
    gates.extend(
        [
        _gate(
            "autonomous_parameter_proposal_ready",
            proposal_ready,
            status=str(proposal.get("status") or artifacts["autonomous_parameter_proposal"]["status"]),
            reason="proposal must be an inactive no-authority review packet",
            next_actions=["build_reviewable_autonomous_parameter_proposal"],
            evidence={
                "candidate": proposal_candidate,
                "answers": _dict(proposal.get("answers")),
            },
        ),
        _gate(
            "false_negative_operator_review_present",
            review_present,
            status=str(review.get("status") or artifacts["false_negative_operator_review"]["status"]),
            reason="false-negative review artifact must be fresh and no-authority",
            next_actions=["record_false_negative_operator_review_before_preflight"],
            evidence={
                "candidate": review_candidate,
                "answers": _dict(review.get("answers")),
            },
        ),
        _gate(
            "candidate_alignment",
            aligned,
            status="ALIGNED" if aligned else "MISMATCH",
            reason="proposal and false-negative operator review must name the same side-cell/horizon",
            next_actions=["regenerate_proposal_and_review_for_same_side_cell"],
            evidence={
                "proposal_candidate": proposal_candidate,
                "review_candidate": review_candidate,
            },
        ),
        _gate(
            "false_negative_operator_review_approved_for_preflight",
            review_approved,
            status=str(review.get("status") or "MISSING"),
            reason="operator review must approve candidate preflight without granting runtime authority",
            next_actions=["operator_review_false_negative_candidate_with_exact_preflight_confirm"],
            evidence={
                "typed_confirm_expected": review.get("typed_confirm_expected"),
                "operator_review_approved_for_preflight": review.get(
                    "operator_review_approved_for_preflight"
                ),
                "operator_review_approval_source": review.get(
                    "operator_review_approval_source"
                ),
            },
        ),
        ]
    )
    failed_gates = [gate for gate in gates if gate.get("passed") is not True]
    status = _status_from_gates(gates, review_approved)
    candidate = proposal_candidate if proposal_candidate.get("side_cell_key") else review_candidate
    design = _bounded_demo_probe_design(
        status=status,
        candidate=candidate,
        proposal=proposal,
        standing_summary=standing_summary,
    )
    if status == READY_PREFLIGHT_STATUS:
        next_actions = [
            "run_candidate_matched_touchability_preflight",
            "build_or_refresh_near_touch_or_skip_placement_review",
            "then_operator_may_authorize_bounded_demo_probe_with_exact_typed_confirm",
        ]
    elif status == OPERATOR_REVIEW_REQUIRED_STATUS:
        next_actions = [
            "operator_review_false_negative_candidate_with_exact_preflight_confirm",
            "do_not_grant_probe_or_order_authority_from_this_preflight",
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
        "schema_version": FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(gate["name"] for gate in failed_gates)
        or "false_negative_candidate_ready_for_bounded_demo_probe_authorization_review",
        "side_cell_key": candidate.get("side_cell_key"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
        "candidate": candidate,
        "bounded_demo_probe_design": design,
        "gates": gates,
        "blocking_gate_count": len(failed_gates),
        "blocking_gates": [gate["name"] for gate in failed_gates],
        "next_actions": next_actions,
        "artifacts": artifacts,
        "answers": {
            "autonomous_parameter_proposal_ready": proposal_ready,
            "false_negative_operator_review_present": review_present,
            "false_negative_operator_review_approved_for_preflight": review_approved,
            "standing_demo_authorization_present": standing_input_supplied,
            "standing_demo_authorization_required": review_uses_standing,
            "standing_demo_authorization_valid": standing_valid_for_preflight,
            "operator_review_approval_source": review.get(
                "operator_review_approval_source"
            ),
            "ready_for_operator_bounded_demo_probe_authorization": status == READY_PREFLIGHT_STATUS,
            "bounded_demo_probe_design_ready_for_operator_review": status in {
                READY_PREFLIGHT_STATUS,
                OPERATOR_REVIEW_REQUIRED_STATUS,
            },
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "runtime_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
        },
        "standing_demo_authorization": standing_summary,
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate False-Negative Bounded Demo Probe Preflight",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Side-cell: `{packet.get('side_cell_key')}`",
        f"- Symbol: `{candidate.get('symbol')}`",
        f"- Side: `{candidate.get('side')}`",
        f"- Horizon minutes: `{packet.get('outcome_horizon_minutes')}`",
        f"- Ready for bounded authorization review: `{answers.get('ready_for_operator_bounded_demo_probe_authorization')}`",
        f"- Probe authority granted: `{answers.get('probe_authority_granted')}`",
        f"- Order authority granted: `{answers.get('order_authority_granted')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Gates",
        "",
        "| gate | passed | status | reason |",
        "|---|---:|---|---|",
    ]
    for gate in _list(packet.get("gates")):
        lines.append(
            f"| {gate.get('name')} | `{gate.get('passed')}` | "
            f"`{gate.get('status')}` | {gate.get('reason')} |"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in _list(packet.get("next_actions")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, None


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--autonomous-parameter-proposal-json", type=Path, required=True)
    parser.add_argument("--false-negative-operator-review-json", type=Path, required=True)
    parser.add_argument("--standing-demo-authorization-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument(
        "--max-authorization-ttl-hours",
        type=int,
        default=DEFAULT_MAX_STANDING_DEMO_AUTHORIZATION_TTL_HOURS,
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    proposal, proposal_err = _read_json(args.autonomous_parameter_proposal_json)
    review, review_err = _read_json(args.false_negative_operator_review_json)
    standing, standing_err = _read_json(args.standing_demo_authorization_json)
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=proposal,
        false_negative_operator_review=review,
        standing_demo_authorization=standing,
        autonomous_parameter_proposal_path=args.autonomous_parameter_proposal_json,
        false_negative_operator_review_path=args.false_negative_operator_review_json,
        standing_demo_authorization_path=args.standing_demo_authorization_json,
        autonomous_parameter_proposal_error=proposal_err,
        false_negative_operator_review_error=review_err,
        standing_demo_authorization_error=standing_err,
        max_artifact_age_hours=args.max_artifact_age_hours,
        max_authorization_ttl_hours=args.max_authorization_ttl_hours,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
