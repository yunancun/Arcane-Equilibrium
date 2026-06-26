#!/usr/bin/env python3
"""Build a no-authority operator review for ranked Cost Gate false negatives.

This artifact records whether a ranked false-negative candidate may proceed to
bounded Demo probe preflight review. It never grants probe authority, order
authority, promotion proof, or a main Cost Gate adjustment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.false_negative_candidate_packet import SCHEMA_VERSION
from cost_gate_learning_lane.standing_demo_authorization import (
    summarize_standing_demo_authorization,
)


FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION = (
    "cost_gate_false_negative_operator_review_v1"
)
APPROVED_FOR_PREFLIGHT_STATUS = (
    "APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT"
)
REJECTED_FOR_PREFLIGHT_STATUS = (
    "REJECTED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT"
)
PENDING_OPERATOR_REVIEW_STATUS = "PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW"
READY_PACKET_STATUS = "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
DEFAULT_MAX_STANDING_DEMO_AUTHORIZATION_TTL_HOURS = 24
BOUNDARY = (
    "artifact-only Cost Gate false-negative operator review; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, main Cost Gate "
    "lowering, probe authority, order authority, or promotion proof"
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
    return payload.get("generated_at_utc") or payload.get("generated") or payload.get("ts_utc")


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


def _authority_preserved(payload: dict[str, Any] | None) -> bool:
    data = _dict(payload)
    stack = [data, _dict(data.get("answers"))]
    for source in stack:
        if source.get("global_cost_gate_lowering_recommended") is True:
            return False
        if source.get("probe_authority_granted") is True:
            return False
        if source.get("order_authority_granted") is True:
            return False
        if source.get("promotion_evidence") is True:
            return False
        if source.get("promotion_proof") is True:
            return False
        if source.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
    return True


def _candidate_rows(packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(_dict(packet).get("ranked_false_negative_candidates")):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any]:
    row = _dict(candidate)
    return {
        "side_cell_key": row.get("side_cell_key"),
        "false_negative_rank": row.get("false_negative_rank"),
        "strategy_names": row.get("strategy_names") or [],
        "symbols": row.get("symbols") or [],
        "sides": row.get("sides") or [],
        "horizon_minutes": row.get("horizon_minutes") or [],
        "dominant_horizon_minutes": row.get("dominant_horizon_minutes"),
        "outcome_count": _int(row.get("outcome_count")),
        "avg_gross_bps": _float(row.get("avg_gross_bps")),
        "avg_net_bps": _float(row.get("avg_net_bps")),
        "avg_cost_bps": _float(row.get("avg_cost_bps")),
        "net_positive_pct": _float(row.get("net_positive_pct")),
        "net_cost_cushion_bps": _float(row.get("net_cost_cushion_bps")),
        "wrongful_block_score": _float(row.get("wrongful_block_score")),
        "candidate_class": row.get("candidate_class"),
        "learning_diagnosis": row.get("learning_diagnosis"),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "next_action": row.get("next_action"),
        "operator_review_required": row.get("operator_review_required") is True,
        "global_cost_gate_lowering_recommended": (
            row.get("global_cost_gate_lowering_recommended") is True
        ),
        "probe_authority_granted": row.get("probe_authority_granted") is True,
        "order_authority_granted": row.get("order_authority_granted") is True,
        "promotion_evidence": row.get("promotion_evidence") is True,
    }


def _select_candidate(
    packet: dict[str, Any] | None,
    selected_side_cell_key: str | None,
) -> tuple[dict[str, Any] | None, str]:
    rows = _candidate_rows(packet)
    selected = _str(selected_side_cell_key)
    if selected:
        for row in rows:
            if _str(row.get("side_cell_key")) == selected:
                return row, "explicit_side_cell_key"
        return None, "explicit_side_cell_key_not_found"
    if rows:
        return rows[0], "top_ranked_false_negative"
    return None, "no_ranked_false_negative_candidate"


def expected_false_negative_operator_review_typed_confirm(
    side_cell_key: Any,
    false_negative_rank: Any,
) -> str:
    """Return the exact phrase required to approve candidate preflight review."""
    return (
        "approve_cost_gate_false_negative_preflight:"
        f"{_str(side_cell_key)}:{_int(false_negative_rank)}"
    )


def _normalize_decision(decision: str | None) -> str:
    text = _str(decision or "defer").lower().replace("_", "-")
    if text in {"approve", "approved", "approve-preflight"}:
        return "approve-preflight"
    if text in {"reject", "rejected", "decline", "declined"}:
        return "reject"
    return "defer"


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


def _status_from_gates(
    *,
    decision: str,
    approval_requested: bool,
    failed_gates: list[dict[str, Any]],
) -> str:
    failed = {gate["name"] for gate in failed_gates}
    if "authority_boundary_preserved" in failed:
        return "AUTHORITY_BOUNDARY_VIOLATION"
    if "standing_demo_authorization_valid_for_preflight_review" in failed:
        return "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT_REVIEW"
    if "false_negative_candidate_packet_ready" in failed:
        return "FALSE_NEGATIVE_CANDIDATE_PACKET_NOT_READY"
    if "candidate_selected" in failed:
        return "FALSE_NEGATIVE_CANDIDATE_SELECTION_REQUIRED"
    if "candidate_reviewable" in failed:
        return "FALSE_NEGATIVE_CANDIDATE_NOT_REVIEWABLE"
    if decision == "reject":
        return REJECTED_FOR_PREFLIGHT_STATUS
    if decision != "approve-preflight":
        return PENDING_OPERATOR_REVIEW_STATUS
    if "operator_id_present" in failed:
        return "OPERATOR_ID_REQUIRED"
    if "typed_confirm_matches" in failed:
        return "TYPED_CONFIRM_REQUIRED"
    if approval_requested:
        return APPROVED_FOR_PREFLIGHT_STATUS
    return PENDING_OPERATOR_REVIEW_STATUS


def _existing_review_is_preservable(
    existing_review: dict[str, Any] | None,
    *,
    candidate: dict[str, Any],
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> tuple[bool, str]:
    review = _dict(existing_review)
    if not review:
        return False, "existing_review_missing"
    if review.get("schema_version") != FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION:
        return False, "existing_review_schema_mismatch"
    if review.get("status") != APPROVED_FOR_PREFLIGHT_STATUS:
        return False, "existing_review_not_approved_for_preflight"
    if review.get("decision") != "approve-preflight":
        return False, "existing_review_decision_not_approve_preflight"
    if _authority_preserved(review) is not True:
        return False, "existing_review_authority_boundary_violation"
    age = _age_seconds(_generated_at(review), now_utc=now_utc)
    if age is None:
        return False, "existing_review_unknown_age"
    if age > max_age_seconds:
        return False, "existing_review_stale"
    answers = _dict(review.get("answers"))
    if answers.get("operator_review_approved_for_preflight") is not True:
        return False, "existing_review_answer_not_approved"
    if answers.get("bounded_demo_probe_preflight_approved") is not True:
        return False, "existing_review_preflight_answer_not_approved"
    if answers.get("review_grants_runtime_authority") is not False:
        return False, "existing_review_runtime_authority_not_false"
    if answers.get("bounded_demo_probe_authorized") is not False:
        return False, "existing_review_probe_authorized_not_false"
    if _str(review.get("selected_side_cell_key")) != _str(candidate.get("side_cell_key")):
        return False, "existing_review_side_cell_mismatch"
    if _int(review.get("selected_false_negative_rank")) != _int(
        candidate.get("false_negative_rank")
    ):
        return False, "existing_review_rank_mismatch"
    return True, "existing_approval_preserved_for_default_defer_refresh"


def _preserve_existing_review(
    existing_review: dict[str, Any],
    *,
    now_utc: dt.datetime,
    review_note: str | None,
) -> dict[str, Any]:
    preserved = dict(existing_review)
    answers = dict(_dict(preserved.get("answers")))
    answers.update(
        {
            "operator_review_approved_for_preflight": True,
            "bounded_demo_probe_preflight_approved": True,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        }
    )
    preserved.update(
        {
            "defer_refresh_preserved_existing_approval": True,
            "defer_refresh_generated_at_utc": now_utc.isoformat(),
            "defer_refresh_decision": "defer",
            "defer_refresh_reason": (
                "existing_approve_preflight_review_is_fresh_aligned_and_no_authority"
            ),
            "answers": answers,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        }
    )
    note = _str(review_note)
    if note:
        preserved["defer_refresh_note"] = note
    return preserved


def build_false_negative_operator_review(
    *,
    false_negative_candidate_packet: dict[str, Any] | None,
    existing_operator_review: dict[str, Any] | None = None,
    standing_demo_authorization: dict[str, Any] | None = None,
    source_path: Path | None = None,
    standing_demo_authorization_path: Path | None = None,
    source_error: str | None = None,
    standing_demo_authorization_error: str | None = None,
    selected_side_cell_key: str | None = None,
    decision: str = "defer",
    operator_id: str | None = None,
    typed_confirm: str | None = None,
    review_note: str | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
    max_authorization_ttl_hours: int = DEFAULT_MAX_STANDING_DEMO_AUTHORIZATION_TTL_HOURS,
) -> dict[str, Any]:
    """Build a fail-closed operator-review record for a false-negative path."""
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    if max_authorization_ttl_hours < 1 or max_authorization_ttl_hours > 24 * 7:
        raise ValueError("max_authorization_ttl_hours must be in [1, 168]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    packet = _dict(false_negative_candidate_packet)
    standing_payload = _dict(standing_demo_authorization)
    max_age_seconds = max_artifact_age_hours * 3600
    artifact = _artifact_summary(
        name="false_negative_candidate_packet",
        path=source_path,
        payload=packet,
        source_error=source_error,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    standing_artifact = _artifact_summary(
        name="standing_demo_authorization",
        path=standing_demo_authorization_path,
        payload=standing_payload,
        source_error=standing_demo_authorization_error,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    selected, selection_method = _select_candidate(packet, selected_side_cell_key)
    candidate = _candidate_summary(selected)
    answers = _dict(packet.get("answers"))
    summary = _dict(packet.get("summary"))
    normalized_decision = _normalize_decision(decision)
    operator = _str(operator_id)
    provided_confirm = _str(typed_confirm)
    expected_confirm = expected_false_negative_operator_review_typed_confirm(
        candidate.get("side_cell_key"),
        candidate.get("false_negative_rank"),
    )
    typed_confirm_matches = bool(provided_confirm) and provided_confirm == expected_confirm
    approval_requested = normalized_decision == "approve-preflight"
    standing_input_supplied = (
        bool(standing_payload)
        or standing_demo_authorization_path is not None
        or standing_demo_authorization_error not in (None, "missing_path")
    )
    standing_summary = summarize_standing_demo_authorization(
        standing_payload,
        standing_artifact,
        now_utc=now,
        max_authorization_ttl_hours=max_authorization_ttl_hours,
        candidate={
            "side_cell_key": candidate.get("side_cell_key"),
            "strategy_name": (_list(candidate.get("strategy_names")) or [None])[0],
            "symbol": (_list(candidate.get("symbols")) or [None])[0],
            "side": (_list(candidate.get("sides")) or [None])[0],
            "outcome_horizon_minutes": candidate.get("dominant_horizon_minutes")
            or (_list(candidate.get("horizon_minutes")) or [None])[0],
        },
    )
    standing_approval_valid = bool(
        standing_input_supplied
        and normalized_decision == "defer"
        and not provided_confirm
        and standing_summary.get("valid_for_candidate_scoped_authorization") is True
    )
    if standing_approval_valid and not operator:
        operator = _str(standing_summary.get("operator_id"))
    approval_source = (
        "exact_typed_confirm"
        if approval_requested and typed_confirm_matches
        else "standing_demo_authorization"
        if standing_approval_valid
        else None
    )
    authority_preserved = _authority_preserved(packet)
    packet_ready = (
        artifact["status"] == "FRESH"
        and artifact["schema_version"] == SCHEMA_VERSION
        and packet.get("status") == READY_PACKET_STATUS
        and answers.get("operator_review_ready") is True
        and answers.get("global_cost_gate_lowering_recommended") is not True
        and answers.get("probe_authority_granted") is not True
        and answers.get("order_authority_granted") is not True
        and answers.get("promotion_evidence") is not True
        and _int(summary.get("false_negative_candidate_count")) > 0
    )
    candidate_selected = bool(candidate.get("side_cell_key"))
    candidate_reviewable = (
        candidate_selected
        and candidate.get("candidate_class") == "false_negative_after_cost"
        and candidate.get("operator_review_required") is True
        and candidate.get("global_cost_gate_lowering_recommended") is not True
        and candidate.get("probe_authority_granted") is not True
        and candidate.get("order_authority_granted") is not True
        and candidate.get("promotion_evidence") is not True
    )

    if (
        normalized_decision == "defer"
        and authority_preserved
        and packet_ready
        and artifact["status"] == "FRESH"
        and artifact["schema_version"] == SCHEMA_VERSION
        and candidate_reviewable
        and (not standing_input_supplied or standing_approval_valid)
    ):
        preserve_existing, _preserve_reason = _existing_review_is_preservable(
            existing_operator_review,
            candidate=candidate,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        )
        if preserve_existing:
            return _preserve_existing_review(
                _dict(existing_operator_review),
                now_utc=now,
                review_note=review_note,
            )

    gates = [
        _gate(
            "authority_boundary_preserved",
            authority_preserved,
            status="PRESERVED" if authority_preserved else "VIOLATED",
            reason="review input must not grant Cost Gate lowering, probe/order authority, or promotion proof",
            next_actions=["remove_authority_granting_input_before_review"],
        ),
    ]
    if standing_input_supplied:
        gates.append(
            _gate(
                "standing_demo_authorization_valid_for_preflight_review",
                standing_approval_valid,
                status=(
                    "VALID"
                    if standing_approval_valid
                    else str(standing_artifact.get("status") or "MISSING")
                ),
                reason=(
                    "standing Demo envelope must be fresh, Demo-only, scoped for "
                    "bounded probe review, candidate-scoped, unexpired, and "
                    "free of runtime/order/Cost Gate/promotion authority"
                ),
                next_actions=[
                    "supply_fresh_valid_standing_demo_authorization_or_remove_invalid_envelope"
                ],
                evidence=standing_summary,
            )
        )
    gates.extend(
        [
            _gate(
                "false_negative_candidate_packet_ready",
                packet_ready,
                status=str(packet.get("status") or artifact["status"]),
                reason="candidate packet must be fresh, schema-valid, and ready for operator review",
                next_actions=["refresh_cost_gate_false_negative_candidate_packet"],
                evidence={
                    "artifact": artifact,
                    "summary": summary,
                    "answers": {
                        "operator_review_ready": answers.get("operator_review_ready"),
                        "global_cost_gate_lowering_recommended": answers.get(
                            "global_cost_gate_lowering_recommended"
                        ),
                        "probe_authority_granted": answers.get("probe_authority_granted"),
                        "order_authority_granted": answers.get("order_authority_granted"),
                        "promotion_evidence": answers.get("promotion_evidence"),
                    },
                },
            ),
            _gate(
                "candidate_selected",
                candidate_selected,
                status="SELECTED" if candidate_selected else selection_method,
                reason="review must name a ranked false-negative side-cell candidate",
                next_actions=["select_ranked_false_negative_side_cell_for_review"],
                evidence={
                    "selection_method": selection_method,
                    "selected_side_cell_key": selected_side_cell_key,
                },
            ),
            _gate(
                "candidate_reviewable",
                candidate_reviewable,
                status=str(candidate.get("status") or "MISSING"),
                reason="selected candidate must remain a no-authority false-negative after-cost review row",
                next_actions=["rebuild_packet_or_select_reviewable_false_negative_candidate"],
                evidence=candidate,
            ),
        ]
    )
    gates.extend(
        [
        _gate(
            "operator_id_present",
            (not approval_requested and not standing_approval_valid) or bool(operator),
            status="PRESENT" if operator else "MISSING",
            reason="approval requires a non-empty operator id",
            next_actions=["record_operator_id_before_approval"],
        ),
        _gate(
            "typed_confirm_matches",
            (not approval_requested) or typed_confirm_matches,
            status=(
                "MATCH"
                if typed_confirm_matches
                else "STANDING_DEMO_AUTHORIZATION"
                if standing_approval_valid
                else "MISSING_OR_MISMATCH"
            ),
            reason=(
                "typed-confirm approval requires the exact phrase; standing Demo "
                "envelope approval is recorded in its separate fail-closed gate"
            ),
            next_actions=["copy_exact_typed_confirm_from_artifact_before_approval"],
            evidence={
                "typed_confirm_expected": expected_confirm,
                "typed_confirm_provided": bool(provided_confirm),
                "typed_confirm_matches": typed_confirm_matches,
                "standing_demo_authorization_valid": standing_approval_valid,
            },
        ),
        ]
    )
    failed_gates = [gate for gate in gates if gate["passed"] is not True]
    effective_decision = (
        "approve-preflight" if standing_approval_valid else normalized_decision
    )
    status = _status_from_gates(
        decision=effective_decision,
        approval_requested=approval_requested or standing_approval_valid,
        failed_gates=failed_gates,
    )
    approved_for_preflight = status == APPROVED_FOR_PREFLIGHT_STATUS
    recorded_decision = (
        "approve-preflight" if approved_for_preflight else normalized_decision
    )

    if approved_for_preflight:
        next_actions = [
            "build_candidate_matched_bounded_demo_probe_preflight_for_approved_false_negative",
            "preserve_global_cost_gate_no_lowering",
            "require_touchability_fill_fee_slippage_lineage_before_probe_authorization",
        ]
    elif status == REJECTED_FOR_PREFLIGHT_STATUS:
        next_actions = [
            "keep_main_cost_gate_unchanged_for_rejected_false_negative_candidate",
            "continue_blocked_signal_learning_collection",
        ]
    elif status == PENDING_OPERATOR_REVIEW_STATUS and not failed_gates:
        next_actions = [
            "operator_review_ranked_false_negative_candidate_before_bounded_demo_probe_preflight"
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
        "schema_version": FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(gate["name"] for gate in failed_gates)
        or recorded_decision,
        "decision": recorded_decision,
        "operator_id": operator or None,
        "review_note": _str(review_note) or None,
        "review_scope": "preflight_review_only_not_probe_authorization",
        "operator_review_approval_source": approval_source,
        "selection_method": selection_method,
        "selected_side_cell_key": candidate.get("side_cell_key"),
        "selected_false_negative_rank": candidate.get("false_negative_rank"),
        "candidate": candidate,
        "operator_review_approved_for_preflight": approved_for_preflight,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
        "gates": gates,
        "blocking_gate_count": len(failed_gates),
        "blocking_gates": [gate["name"] for gate in failed_gates],
        "next_actions": next_actions,
        "typed_confirm_expected": expected_confirm,
        "typed_confirm_provided": bool(provided_confirm),
        "typed_confirm_matches": typed_confirm_matches,
        "answers": {
            "operator_review_approved_for_preflight": approved_for_preflight,
            "bounded_demo_probe_preflight_approved": approved_for_preflight,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "standing_demo_authorization_present": standing_input_supplied,
            "standing_demo_authorization_valid": standing_approval_valid,
            "standing_demo_authorization_consumed": (
                approval_source == "standing_demo_authorization"
            ),
            "operator_review_approval_source": approval_source,
        },
        "artifacts": {
            "false_negative_candidate_packet": artifact,
            "standing_demo_authorization": standing_artifact,
        },
        "standing_demo_authorization": standing_summary,
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    lines = [
        "# Cost Gate False-Negative Operator Review",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Decision: `{packet.get('decision')}`",
        f"- Operator: `{packet.get('operator_id')}`",
        f"- Side-cell: `{packet.get('selected_side_cell_key')}`",
        f"- False-negative rank: `{packet.get('selected_false_negative_rank')}`",
        f"- Avg net bps: `{candidate.get('avg_net_bps')}`",
        f"- Net cost cushion bps: `{candidate.get('net_cost_cushion_bps')}`",
        f"- Wrongful block score: `{candidate.get('wrongful_block_score')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Approval Phrase",
        "",
        f"`{packet.get('typed_confirm_expected')}`",
        "",
        "## Gates",
        "",
        "| gate | passed | status | reason |",
        "|---|---:|---|---|",
    ]
    for gate in packet.get("gates") or []:
        lines.append(
            f"| {gate.get('name')} | `{gate.get('passed')}` | "
            f"`{gate.get('status')}` | {gate.get('reason')} |"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in packet.get("next_actions") or []:
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
    parser.add_argument("--false-negative-candidate-packet-json", type=Path, required=True)
    parser.add_argument("--existing-operator-review-json", type=Path)
    parser.add_argument("--standing-demo-authorization-json", type=Path)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument(
        "--decision",
        choices=["defer", "reject", "approve-preflight"],
        default="defer",
    )
    parser.add_argument("--operator-id")
    parser.add_argument("--typed-confirm")
    parser.add_argument("--review-note")
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument(
        "--max-authorization-ttl-hours",
        type=int,
        default=DEFAULT_MAX_STANDING_DEMO_AUTHORIZATION_TTL_HOURS,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet, err = _read_json(args.false_negative_candidate_packet_json)
    existing_review, _existing_err = _read_json(args.existing_operator_review_json)
    standing, standing_err = _read_json(args.standing_demo_authorization_json)
    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        existing_operator_review=existing_review,
        standing_demo_authorization=standing,
        source_path=args.false_negative_candidate_packet_json,
        standing_demo_authorization_path=args.standing_demo_authorization_json,
        source_error=err,
        standing_demo_authorization_error=standing_err,
        selected_side_cell_key=args.selected_side_cell_key,
        decision=args.decision,
        operator_id=args.operator_id,
        typed_confirm=args.typed_confirm,
        review_note=args.review_note,
        max_artifact_age_hours=args.max_artifact_age_hours,
        max_authorization_ttl_hours=args.max_authorization_ttl_hours,
    )
    markdown = render_markdown(review)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, review)
    if args.print_json:
        print(json.dumps(review, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
