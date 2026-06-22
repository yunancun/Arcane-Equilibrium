#!/usr/bin/env python3
"""Build a no-authority operator review record for a sealed horizon candidate.

This artifact records whether an operator has reviewed a sealed-horizon
candidate for bounded demo-probe preflight. It never grants probe authority,
order authority, promotion proof, or a main Cost Gate adjustment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


SEALED_HORIZON_OPERATOR_REVIEW_SCHEMA_VERSION = "sealed_horizon_operator_review_v1"
APPROVED_FOR_PREFLIGHT_STATUS = "APPROVED_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT"
REJECTED_FOR_PREFLIGHT_STATUS = "REJECTED_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT"
PENDING_OPERATOR_REVIEW_STATUS = "PENDING_OPERATOR_REVIEW"
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
BOUNDARY = (
    "artifact-only sealed horizon operator review; no PG query/write, Bybit "
    "call, order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, order authority, or promotion proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
    if not value:
        return None
    text = str(value).strip()
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
    return {
        "name": name,
        "path": str(path) if path else None,
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _sealed_summary(evidence: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(evidence)
    answers = _dict(payload.get("answers"))
    outcomes = _dict(payload.get("outcomes"))
    review = _dict(payload.get("review"))
    outcome_count = (
        outcomes.get("blocked_signal_outcome_count")
        or review.get("blocked_signal_outcome_count")
        or 0
    )
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "side_cell_key": payload.get("side_cell_key") or review.get("top_side_cell_key"),
        "source_kind": payload.get("source_kind"),
        "outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
        "blocked_signal_outcome_count": outcome_count,
        "avg_gross_bps": outcomes.get("avg_gross_bps"),
        "avg_net_bps": (
            outcomes.get("avg_net_bps")
            or review.get("avg_blocked_signal_outcome_net_bps")
        ),
        "net_positive_pct": (
            outcomes.get("net_positive_pct")
            or review.get("blocked_signal_net_positive_pct")
        ),
        "top_side_cell_status": review.get("top_side_cell_status"),
        "review_ready": (
            payload.get("schema_version") == "sealed_horizon_learning_evidence_v1"
            and payload.get("status")
            == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
            and answers.get("candidate_clears_operator_review_gate") is True
            and answers.get("global_cost_gate_lowering_recommended") is not True
            and answers.get("probe_authority_granted") is not True
            and answers.get("order_authority_granted") is not True
            and _int(outcome_count) > 0
        ),
    }


def _preflight_summary(preflight: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(preflight)
    answers = _dict(payload.get("answers"))
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "side_cell_key": payload.get("side_cell_key"),
        "outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
        "sealed_horizon_evidence_ready": (
            answers.get("sealed_horizon_evidence_ready") is True
        ),
        "decision_packet_aligned": answers.get("decision_packet_aligned") is True,
        "production_learning_lane_accumulating": (
            answers.get("production_learning_lane_accumulating") is True
        ),
        "global_cost_gate_lowering_recommended": (
            answers.get("global_cost_gate_lowering_recommended") is True
        ),
        "main_cost_gate_adjustment": answers.get("main_cost_gate_adjustment"),
        "probe_authority_granted": answers.get("probe_authority_granted") is True,
        "order_authority_granted": answers.get("order_authority_granted") is True,
        "promotion_evidence": answers.get("promotion_evidence") is True,
    }


def _has_authority_violation(*payloads: dict[str, Any] | None) -> bool:
    for payload in payloads:
        data = _dict(payload)
        answers = _dict(data.get("answers"))
        for source in (data, answers):
            if source.get("order_authority_granted") is True:
                return True
            if source.get("probe_authority_granted") is True:
                return True
            if source.get("promotion_evidence") is True:
                return True
            adjustment = source.get("main_cost_gate_adjustment")
            if adjustment not in (None, "", "NONE"):
                return True
            if source.get("global_cost_gate_lowering_recommended") is True:
                return True
    return False


def expected_sealed_horizon_operator_review_typed_confirm(
    side_cell_key: Any,
    outcome_horizon_minutes: Any,
) -> str:
    """Return the exact approval phrase required for preflight approval."""
    return (
        "approve_sealed_horizon_preflight:"
        f"{str(side_cell_key or '').strip()}:{_int(outcome_horizon_minutes)}"
    )


def _normalize_decision(decision: str | None) -> str:
    text = str(decision or "defer").strip().lower().replace("_", "-")
    if text in {"approve", "approved", "approve-preflight"}:
        return "approve-preflight"
    if text in {"reject", "rejected", "decline", "declined"}:
        return "reject"
    return "defer"


def _preflight_aligned(
    *,
    preflight_artifact: dict[str, Any],
    preflight: dict[str, Any],
    sealed: dict[str, Any],
) -> bool:
    status = preflight.get("status")
    return (
        preflight_artifact["status"] == "FRESH"
        and preflight["schema_version"] == "sealed_horizon_bounded_demo_probe_preflight_v1"
        and status
        in {
            "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED",
            "OPERATOR_REVIEW_REQUIRED",
            "PRODUCTION_LEARNING_LANE_NOT_READY",
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
        }
        and preflight["sealed_horizon_evidence_ready"] is True
        and preflight["decision_packet_aligned"] is True
        and preflight["side_cell_key"] == sealed.get("side_cell_key")
        and preflight["outcome_horizon_minutes"] == sealed.get("outcome_horizon_minutes")
        and preflight["global_cost_gate_lowering_recommended"] is not True
        and preflight["main_cost_gate_adjustment"] == "NONE"
        and preflight["probe_authority_granted"] is not True
        and preflight["order_authority_granted"] is not True
        and preflight["promotion_evidence"] is not True
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
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _status_from_review(
    *,
    decision: str,
    authority_preserved: bool,
    sealed_ready: bool,
    approval_requested: bool,
    preflight_aligned: bool,
    operator_id_present: bool,
    typed_confirm_matches: bool,
) -> str:
    if not authority_preserved:
        return "AUTHORITY_BOUNDARY_VIOLATION"
    if not sealed_ready:
        return "SEALED_HORIZON_EVIDENCE_NOT_READY"
    if decision == "reject":
        return REJECTED_FOR_PREFLIGHT_STATUS
    if decision != "approve-preflight":
        return PENDING_OPERATOR_REVIEW_STATUS
    if not approval_requested:
        return PENDING_OPERATOR_REVIEW_STATUS
    if not preflight_aligned:
        return "SEALED_HORIZON_PREFLIGHT_NOT_ALIGNED"
    if not operator_id_present:
        return "OPERATOR_ID_REQUIRED"
    if not typed_confirm_matches:
        return "TYPED_CONFIRM_REQUIRED"
    return APPROVED_FOR_PREFLIGHT_STATUS


def build_sealed_horizon_operator_review(
    *,
    sealed_horizon_learning_evidence: dict[str, Any] | None,
    preflight: dict[str, Any] | None = None,
    decision: str = "defer",
    operator_id: str | None = None,
    typed_confirm: str | None = None,
    review_note: str | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
) -> dict[str, Any]:
    """Build a fail-closed operator-review record for a sealed horizon path."""
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    paths = paths or {}
    artifacts = {
        "sealed_horizon_learning_evidence": _artifact_summary(
            name="sealed_horizon_learning_evidence",
            path=paths.get("sealed_horizon_learning_evidence"),
            payload=sealed_horizon_learning_evidence,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "sealed_horizon_probe_preflight": _artifact_summary(
            name="sealed_horizon_probe_preflight",
            path=paths.get("preflight"),
            payload=preflight,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }
    sealed = _sealed_summary(sealed_horizon_learning_evidence)
    preflight_summary = _preflight_summary(preflight)
    normalized_decision = _normalize_decision(decision)
    side_cell_key = sealed.get("side_cell_key")
    horizon_minutes = sealed.get("outcome_horizon_minutes")
    expected_confirm = expected_sealed_horizon_operator_review_typed_confirm(
        side_cell_key,
        horizon_minutes,
    )
    provided_confirm = str(typed_confirm or "").strip()
    operator = str(operator_id or "").strip()
    approval_requested = normalized_decision == "approve-preflight"
    sealed_ready = (
        artifacts["sealed_horizon_learning_evidence"]["status"] == "FRESH"
        and sealed["review_ready"] is True
    )
    preflight_aligned = _preflight_aligned(
        preflight_artifact=artifacts["sealed_horizon_probe_preflight"],
        preflight=preflight_summary,
        sealed=sealed,
    )
    authority_preserved = not _has_authority_violation(
        sealed_horizon_learning_evidence,
        preflight,
    )
    typed_confirm_matches = bool(provided_confirm) and provided_confirm == expected_confirm
    status = _status_from_review(
        decision=normalized_decision,
        authority_preserved=authority_preserved,
        sealed_ready=sealed_ready,
        approval_requested=approval_requested,
        preflight_aligned=preflight_aligned,
        operator_id_present=bool(operator),
        typed_confirm_matches=typed_confirm_matches,
    )
    operator_review_approved = status == APPROVED_FOR_PREFLIGHT_STATUS

    gates = [
        _gate(
            "authority_boundary_preserved",
            authority_preserved,
            status="PRESERVED" if authority_preserved else "VIOLATED",
            reason="review inputs must not grant Cost Gate lowering, probe/order authority, or promotion proof",
            next_actions=["remove_authority_granting_input_before_review"],
        ),
        _gate(
            "sealed_horizon_learning_evidence_ready",
            sealed_ready,
            status=str(sealed.get("status") or "MISSING"),
            reason="sealed evidence must clear blocked-outcome review thresholds",
            next_actions=["build_or_refresh_sealed_horizon_learning_evidence"],
            evidence=sealed,
        ),
        _gate(
            "sealed_horizon_probe_preflight_aligned_for_approval",
            (not approval_requested) or preflight_aligned,
            status=str(preflight_summary.get("status") or "MISSING"),
            reason="approval requires a fresh preflight for the same side-cell/horizon with aligned decision evidence",
            next_actions=["run_sealed_horizon_probe_preflight_before_operator_approval"],
            evidence=preflight_summary,
        ),
        _gate(
            "operator_id_present_for_approval",
            (not approval_requested) or bool(operator),
            status="PRESENT" if operator else "MISSING",
            reason="approval requires a non-empty operator id",
            next_actions=["record_operator_id_before_approval"],
        ),
        _gate(
            "typed_confirm_matches_for_approval",
            (not approval_requested) or typed_confirm_matches,
            status="MATCH" if typed_confirm_matches else "MISSING_OR_MISMATCH",
            reason="approval requires the exact typed confirmation phrase",
            next_actions=["copy_exact_typed_confirm_from_artifact_before_approval"],
            evidence={
                "typed_confirm_expected": expected_confirm,
                "typed_confirm_provided": bool(provided_confirm),
                "typed_confirm_matches": typed_confirm_matches,
            },
        ),
    ]
    failed_gates = [gate for gate in gates if gate["passed"] is not True]
    if status == APPROVED_FOR_PREFLIGHT_STATUS:
        next_actions = [
            "feed_operator_review_artifact_to_sealed_horizon_probe_preflight",
            "wait_for_production_learning_lane_accumulation_before_any_probe_authorization",
        ]
    elif status == REJECTED_FOR_PREFLIGHT_STATUS:
        next_actions = [
            "keep_main_cost_gate_unchanged_and_continue_learning_collection",
            "do_not_request_bounded_demo_probe_authorization_for_this_review",
        ]
    elif status == PENDING_OPERATOR_REVIEW_STATUS and not failed_gates:
        next_actions = [
            "operator_review_sealed_horizon_preflight_before_bounded_demo_probe"
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
        "schema_version": SEALED_HORIZON_OPERATOR_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(gate["name"] for gate in failed_gates)
        or normalized_decision,
        "decision": normalized_decision,
        "operator_id": operator or None,
        "review_note": str(review_note).strip() if review_note else None,
        "review_scope": "preflight_review_only_not_probe_authorization",
        "side_cell_key": side_cell_key,
        "outcome_horizon_minutes": horizon_minutes,
        "source_kind": sealed.get("source_kind"),
        "blocked_signal_outcome_count": sealed.get("blocked_signal_outcome_count"),
        "avg_gross_bps": _float(sealed.get("avg_gross_bps")),
        "avg_net_bps": _float(sealed.get("avg_net_bps")),
        "net_positive_pct": _float(sealed.get("net_positive_pct")),
        "operator_review_approved": operator_review_approved,
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
            "operator_review_approved": operator_review_approved,
            "sealed_horizon_evidence_ready": sealed_ready,
            "sealed_horizon_probe_preflight_aligned": preflight_aligned,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "artifacts": artifacts,
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Sealed Horizon Operator Review",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Decision: `{packet.get('decision')}`",
        f"- Operator: `{packet.get('operator_id')}`",
        f"- Side-cell: `{packet.get('side_cell_key')}`",
        f"- Horizon minutes: `{packet.get('outcome_horizon_minutes')}`",
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


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


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
    parser.add_argument("--sealed-horizon-learning-evidence-json", type=Path, required=True)
    parser.add_argument("--preflight-json", type=Path)
    parser.add_argument(
        "--decision",
        choices=["defer", "reject", "approve-preflight"],
        default="defer",
    )
    parser.add_argument("--operator-id")
    parser.add_argument("--typed-confirm")
    parser.add_argument("--review-note")
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_sealed_horizon_operator_review(
        sealed_horizon_learning_evidence=_read_json(
            args.sealed_horizon_learning_evidence_json
        ),
        preflight=_read_json(args.preflight_json),
        decision=args.decision,
        operator_id=args.operator_id,
        typed_confirm=args.typed_confirm,
        review_note=args.review_note,
        paths={
            "sealed_horizon_learning_evidence": args.sealed_horizon_learning_evidence_json,
            "preflight": args.preflight_json,
        },
        max_artifact_age_hours=args.max_artifact_age_hours,
    )
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
