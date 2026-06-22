#!/usr/bin/env python3
"""Build a no-authority preflight for sealed horizon bounded demo probe review.

This artifact turns the current sealed-horizon proof chain into explicit gates:

1. sealed learning evidence is review-ready,
2. profit-learning decision packet is aligned with that evidence,
3. operator review has been recorded,
4. production learning lane is accumulating evidence,
5. no Cost Gate lowering, probe authority, order authority, or promotion proof
   is present in any input.

It does not query PG, call Bybit, submit orders, lower the Cost Gate, or grant
probe/order authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


SEALED_HORIZON_PROBE_PREFLIGHT_SCHEMA_VERSION = (
    "sealed_horizon_bounded_demo_probe_preflight_v1"
)
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
BOUNDARY = (
    "artifact-only sealed horizon demo-probe preflight; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, probe authority, or promotion proof"
)

ACTIVE_LEARNING_LANE_STATUSES = {
    "DATA_ACCUMULATING",
    "BLOCKED_OUTCOMES_ACCUMULATING",
    "REVIEW_CANDIDATE_OPERATOR_REVIEW",
    "PROBE_OUTCOMES_ACCUMULATING",
}
ACTIVE_STACK_HEALTH_STATUSES = {
    "EVIDENCE_STACK_ACTIVE",
    "DATA_ACCUMULATING",
    "COST_GATE_LEARNING_STACK_ACTIVE",
}
APPROVED_OPERATOR_REVIEW_STATUSES = {
    "APPROVED_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT",
    "APPROVED_FOR_BOUNDED_DEMO_PROBE_REVIEW",
}


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
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


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
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "side_cell_key": payload.get("side_cell_key") or review.get("top_side_cell_key"),
        "source_kind": payload.get("source_kind"),
        "outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
        "blocked_signal_outcome_count": (
            outcomes.get("blocked_signal_outcome_count")
            or review.get("blocked_signal_outcome_count")
            or 0
        ),
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
            and _int(
                outcomes.get("blocked_signal_outcome_count")
                or review.get("blocked_signal_outcome_count")
            )
            > 0
        ),
    }


def _decision_summary(packet: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(packet)
    answers = _dict(payload.get("answers"))
    sealed = _dict(payload.get("sealed_horizon_learning_evidence"))
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "side_cell_key": sealed.get("side_cell_key"),
        "outcome_horizon_minutes": sealed.get("outcome_horizon_minutes"),
        "sealed_review_ready": sealed.get("review_ready") is True,
        "sealed_evidence_available": (
            answers.get("sealed_horizon_learning_evidence_available") is True
        ),
        "sealed_candidates_present": (
            answers.get("sealed_horizon_learning_evidence_candidates_present") is True
        ),
        "main_cost_gate_adjustment": answers.get("main_cost_gate_adjustment"),
        "order_authority_granted": answers.get("order_authority_granted") is True,
        "promotion_evidence": answers.get("promotion_evidence") is True,
    }


def _decision_packet_aligned(
    *,
    artifact_status: str,
    decision: dict[str, Any],
    side_cell_key: Any,
    outcome_horizon_minutes: Any,
) -> bool:
    return (
        artifact_status == "FRESH"
        and decision["schema_version"] == "cost_gate_profit_learning_decision_packet_v1"
        and decision["status"] == "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE"
        and decision["sealed_evidence_available"] is True
        and decision["sealed_candidates_present"] is True
        and decision["sealed_review_ready"] is True
        and decision["side_cell_key"] == side_cell_key
        and decision["outcome_horizon_minutes"] == outcome_horizon_minutes
        and decision["main_cost_gate_adjustment"] == "NONE"
        and decision["order_authority_granted"] is not True
        and decision["promotion_evidence"] is not True
    )


def _decision_packet_candidate_paths(search_roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for root in search_roots:
        if root is None:
            continue
        candidates: list[Path]
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = []
            for pattern in (
                "profit_learning_decision_packet_latest.json",
                "profit_learning_decision_packet.json",
                "profit_learning_decision_packet*.json",
            ):
                candidates.extend(root.rglob(pattern))
        else:
            continue
        for path in candidates:
            key = str(path.resolve())
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            out.append(path)
    return sorted(out, key=lambda path: (path.stat().st_mtime, str(path)), reverse=True)


def resolve_decision_packet_for_sealed_horizon_preflight(
    *,
    sealed_horizon_learning_evidence: dict[str, Any] | None,
    explicit_decision_packet: dict[str, Any] | None = None,
    explicit_decision_packet_path: Path | None = None,
    search_roots: list[Path] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
) -> tuple[dict[str, Any] | None, Path | None]:
    """Prefer a fresh decision packet aligned to the sealed side-cell/horizon."""
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    sealed = _sealed_summary(sealed_horizon_learning_evidence)
    side_cell_key = sealed.get("side_cell_key")
    horizon_minutes = sealed.get("outcome_horizon_minutes")

    explicit_artifact = _artifact_summary(
        name="decision_packet",
        path=explicit_decision_packet_path,
        payload=explicit_decision_packet,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    explicit_summary = _decision_summary(explicit_decision_packet)
    if _decision_packet_aligned(
        artifact_status=explicit_artifact["status"],
        decision=explicit_summary,
        side_cell_key=side_cell_key,
        outcome_horizon_minutes=horizon_minutes,
    ):
        return explicit_decision_packet, explicit_decision_packet_path

    for candidate_path in _decision_packet_candidate_paths(search_roots or []):
        try:
            candidate = _read_json(candidate_path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        candidate_artifact = _artifact_summary(
            name="decision_packet",
            path=candidate_path,
            payload=candidate,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        )
        candidate_summary = _decision_summary(candidate)
        if _decision_packet_aligned(
            artifact_status=candidate_artifact["status"],
            decision=candidate_summary,
            side_cell_key=side_cell_key,
            outcome_horizon_minutes=horizon_minutes,
        ):
            return candidate, candidate_path

    return explicit_decision_packet, explicit_decision_packet_path


def _operator_review_summary(review: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(review)
    answers = _dict(payload.get("answers"))
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "side_cell_key": payload.get("side_cell_key"),
        "outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
        "operator_review_approved": (
            payload.get("status") in APPROVED_OPERATOR_REVIEW_STATUSES
            and (
                payload.get("operator_review_approved") is True
                or answers.get("operator_review_approved") is True
            )
        ),
        "main_cost_gate_adjustment": (
            payload.get("main_cost_gate_adjustment")
            or answers.get("main_cost_gate_adjustment")
        ),
        "probe_authority_granted": (
            payload.get("probe_authority_granted") is True
            or answers.get("probe_authority_granted") is True
        ),
        "order_authority_granted": (
            payload.get("order_authority_granted") is True
            or answers.get("order_authority_granted") is True
        ),
        "promotion_evidence": (
            payload.get("promotion_evidence") is True
            or answers.get("promotion_evidence") is True
        ),
    }


def _activation_summary(
    activation_preflight: dict[str, Any] | None,
    stack_health: dict[str, Any] | None,
) -> dict[str, Any]:
    activation = _dict(activation_preflight)
    stack = _dict(stack_health)
    answers = _dict(activation.get("answers"))
    ledger = _dict(activation.get("ledger"))
    activation_status = activation.get("status")
    stack_status = stack.get("status")
    accumulating = (
        answers.get("currently_accumulating_evidence") is True
        or activation_status in ACTIVE_LEARNING_LANE_STATUSES
        or stack_status in ACTIVE_STACK_HEALTH_STATUSES
    )
    return {
        "activation_status": activation_status,
        "stack_health_status": stack_status,
        "currently_accumulating_evidence": accumulating,
        "admission_decision_count": _int(ledger.get("admission_decision_count")),
        "blocked_signal_outcome_count": _int(
            ledger.get("blocked_signal_outcome_count")
        ),
        "probe_outcome_count": _int(ledger.get("probe_outcome_count")),
        "next_actions": (
            _list(activation.get("next_actions"))
            or _list(stack.get("next_actions"))
            or ([activation.get("next_action")] if activation.get("next_action") else [])
            or ([stack.get("next_action")] if stack.get("next_action") else [])
        ),
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


def _status_from_gates(gates: list[dict[str, Any]]) -> str:
    failed = {gate["name"] for gate in gates if gate.get("passed") is not True}
    if "authority_boundary_preserved" in failed:
        return "AUTHORITY_BOUNDARY_VIOLATION"
    if "sealed_horizon_learning_evidence_ready" in failed:
        return "SEALED_HORIZON_EVIDENCE_NOT_READY"
    if "profit_learning_decision_packet_aligned" in failed:
        return "PROFIT_DECISION_PACKET_NOT_ALIGNED"
    operator_failed = "operator_sealed_horizon_review_recorded" in failed
    lane_failed = "production_learning_lane_accumulating" in failed
    if operator_failed and lane_failed:
        return "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED"
    if operator_failed:
        return "OPERATOR_REVIEW_REQUIRED"
    if lane_failed:
        return "PRODUCTION_LEARNING_LANE_NOT_READY"
    return "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"


def build_sealed_horizon_bounded_demo_probe_preflight(
    *,
    sealed_horizon_learning_evidence: dict[str, Any] | None,
    decision_packet: dict[str, Any] | None = None,
    activation_preflight: dict[str, Any] | None = None,
    stack_health: dict[str, Any] | None = None,
    operator_review: dict[str, Any] | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
) -> dict[str, Any]:
    """Build a fail-closed preflight packet from existing artifacts."""
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
        "decision_packet": _artifact_summary(
            name="decision_packet",
            path=paths.get("decision_packet"),
            payload=decision_packet,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "activation_preflight": _artifact_summary(
            name="activation_preflight",
            path=paths.get("activation_preflight"),
            payload=activation_preflight,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "stack_health": _artifact_summary(
            name="stack_health",
            path=paths.get("stack_health"),
            payload=stack_health,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "operator_review": _artifact_summary(
            name="operator_review",
            path=paths.get("operator_review"),
            payload=operator_review,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }

    sealed = _sealed_summary(sealed_horizon_learning_evidence)
    decision = _decision_summary(decision_packet)
    review = _operator_review_summary(operator_review)
    activation = _activation_summary(activation_preflight, stack_health)

    side_cell_key = sealed.get("side_cell_key")
    horizon_minutes = sealed.get("outcome_horizon_minutes")
    decision_aligned = _decision_packet_aligned(
        artifact_status=artifacts["decision_packet"]["status"],
        decision=decision,
        side_cell_key=side_cell_key,
        outcome_horizon_minutes=horizon_minutes,
    )
    operator_review_aligned = (
        artifacts["operator_review"]["status"] == "FRESH"
        and review["schema_version"] == "sealed_horizon_operator_review_v1"
        and review["operator_review_approved"] is True
        and review["side_cell_key"] == side_cell_key
        and review["outcome_horizon_minutes"] == horizon_minutes
        and review["main_cost_gate_adjustment"] == "NONE"
        and review["probe_authority_granted"] is not True
        and review["order_authority_granted"] is not True
        and review["promotion_evidence"] is not True
    )
    production_accumulating = (
        artifacts["activation_preflight"]["present"]
        or artifacts["stack_health"]["present"]
    ) and activation["currently_accumulating_evidence"] is True
    authority_preserved = not _has_authority_violation(
        sealed_horizon_learning_evidence,
        decision_packet,
        activation_preflight,
        stack_health,
        operator_review,
    )

    gates = [
        _gate(
            "sealed_horizon_learning_evidence_ready",
            artifacts["sealed_horizon_learning_evidence"]["status"] == "FRESH"
            and sealed["review_ready"] is True,
            status=str(sealed.get("status") or "MISSING"),
            reason="sealed evidence must clear blocked-outcome review thresholds",
            next_actions=["build_or_refresh_sealed_horizon_learning_evidence"],
            evidence=sealed,
        ),
        _gate(
            "profit_learning_decision_packet_aligned",
            decision_aligned,
            status=str(decision.get("status") or "MISSING"),
            reason="decision packet must route the same sealed side-cell to operator review",
            next_actions=["refresh_profit_learning_decision_packet_with_sealed_evidence"],
            evidence=decision,
        ),
        _gate(
            "operator_sealed_horizon_review_recorded",
            operator_review_aligned,
            status=str(review.get("status") or "MISSING"),
            reason="operator review must approve preflight review without granting authority",
            next_actions=[
                "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
            ],
            evidence=review,
        ),
        _gate(
            "production_learning_lane_accumulating",
            production_accumulating,
            status=str(
                activation.get("activation_status")
                or activation.get("stack_health_status")
                or "MISSING"
            ),
            reason="production learning lane must accumulate ledger/outcome evidence first",
            next_actions=(
                activation["next_actions"]
                or ["activate_or_repair_cost_gate_learning_lane_stack_before_runtime_probe"]
            ),
            evidence=activation,
        ),
        _gate(
            "authority_boundary_preserved",
            authority_preserved,
            status="PRESERVED" if authority_preserved else "VIOLATED",
            reason="preflight inputs must not grant Cost Gate lowering, probe/order authority, or promotion proof",
            next_actions=["remove_authority_granting_input_before_any_review"],
            evidence={
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        ),
    ]
    status = _status_from_gates(gates)
    failed_gates = [gate for gate in gates if gate["passed"] is not True]
    next_actions = _dedupe(
        [
            action
            for gate in failed_gates
            for action in _list(gate.get("next_actions"))
        ]
    )
    if not next_actions and status == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION":
        next_actions = [
            "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
        ]

    return {
        "schema_version": SEALED_HORIZON_PROBE_PREFLIGHT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(gate["name"] for gate in failed_gates)
        or "all_pre_authorization_gates_passed_without_authority_grant",
        "side_cell_key": side_cell_key,
        "outcome_horizon_minutes": horizon_minutes,
        "gates": gates,
        "blocking_gate_count": len(failed_gates),
        "blocking_gates": [gate["name"] for gate in failed_gates],
        "next_actions": next_actions,
        "answers": {
            "sealed_horizon_evidence_ready": gates[0]["passed"],
            "decision_packet_aligned": gates[1]["passed"],
            "operator_review_recorded": gates[2]["passed"],
            "production_learning_lane_accumulating": gates[3]["passed"],
            "ready_for_operator_bounded_demo_probe_authorization": (
                status == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
            ),
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
        "# Sealed Horizon Bounded Demo Probe Preflight",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Side-cell: `{packet.get('side_cell_key')}`",
        f"- Horizon minutes: `{packet.get('outcome_horizon_minutes')}`",
        f"- Boundary: {BOUNDARY}.",
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
    parser.add_argument("--decision-packet-json", type=Path)
    parser.add_argument(
        "--decision-packet-search-root",
        action="append",
        type=Path,
        default=[],
        help=(
            "Optional file or directory to search for a fresh decision packet "
            "aligned to the sealed side-cell/horizon. If the explicit latest "
            "packet is not aligned, an aligned packet from this root is used."
        ),
    )
    parser.add_argument("--activation-preflight-json", type=Path)
    parser.add_argument("--stack-health-json", type=Path)
    parser.add_argument("--operator-review-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    sealed_horizon_learning_evidence = _read_json(
        args.sealed_horizon_learning_evidence_json
    )
    decision_packet = _read_json(args.decision_packet_json)
    decision_packet_path = args.decision_packet_json
    if args.decision_packet_search_root:
        decision_packet, decision_packet_path = (
            resolve_decision_packet_for_sealed_horizon_preflight(
                sealed_horizon_learning_evidence=sealed_horizon_learning_evidence,
                explicit_decision_packet=decision_packet,
                explicit_decision_packet_path=decision_packet_path,
                search_roots=args.decision_packet_search_root,
                max_artifact_age_hours=args.max_artifact_age_hours,
            )
        )
    payloads = {
        "sealed_horizon_learning_evidence": sealed_horizon_learning_evidence,
        "decision_packet": decision_packet,
        "activation_preflight": _read_json(args.activation_preflight_json),
        "stack_health": _read_json(args.stack_health_json),
        "operator_review": _read_json(args.operator_review_json),
    }
    paths = {
        "sealed_horizon_learning_evidence": args.sealed_horizon_learning_evidence_json,
        "decision_packet": decision_packet_path,
        "activation_preflight": args.activation_preflight_json,
        "stack_health": args.stack_health_json,
        "operator_review": args.operator_review_json,
    }
    packet = build_sealed_horizon_bounded_demo_probe_preflight(
        **payloads,
        paths=paths,
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
