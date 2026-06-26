#!/usr/bin/env python3
"""Build a no-authority autonomous parameter proposal from learning output.

The proposal is a review packet only. It translates learned candidates into a
bounded proposal contract while preserving Cost Gate, risk, authorization,
runtime, and audit boundaries. It never writes PG, calls Bybit, submits orders,
mutates runtime state, lowers the global Cost Gate, or grants probe/order
authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any


AUTONOMOUS_PARAMETER_PROPOSAL_SCHEMA_VERSION = (
    "cost_gate_autonomous_parameter_proposal_v1"
)
LEARNING_SSOT_DECISION_SCHEMA_VERSION = "cost_gate_learning_ssot_decision_v1"
FALSE_NEGATIVE_CANDIDATE_SCHEMA_VERSION = "cost_gate_false_negative_candidate_packet_v1"
READY_FALSE_NEGATIVE_PACKET_STATUS = (
    "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
)
PROFIT_EVIDENCE_CLEARED_STATUSES = {
    "DONE",
    "DONE_WITH_CONCERNS",
    "EXPLICITLY_QUARANTINED_BY_OPERATOR",
}
BOUNDARY = (
    "artifact-only autonomous parameter proposal; review packet only; no PG "
    "query/write, Bybit call, order, config, risk, auth, runtime mutation, "
    "global Cost Gate lowering, probe authority, order authority, or promotion proof"
)
CAP_ENVELOPE_EVIDENCE_FLOOR = {
    "schema_version": "cost_gate_cap_envelope_evidence_floor_v1",
    "scope": "proposal_only_before_any_cap_or_runtime_mutation",
    "required_before_cap_envelope_review": [
        "candidate_side_cell_matches_learning_packet",
        "candidate_matched_controls_present",
        "candidate_matched_fee_slippage_and_maker_taker_labels",
        "fresh_bbo_and_instrument_metadata_for_tick_qty_min_notional",
        "cap_staircase_with_discrete_exposure_tiers",
        "portfolio_exposure_and_survival_risk_budget_math",
        "empirical_execution_realism_or_explicit_research_only_status",
        "proof_exclusion_scan_for_all_fill_backed_rows",
        "regime_breadth_freshness_survivorship_labels",
        "repeat_or_oos_path_before_any_promotion_claim",
    ],
    "minimum_execution_realism_thresholds": {
        "sample_count": ">=30 for empirical execution-realism PASS; below this remains research-only",
        "maker_fill_rate": ">=0.60 when maker or mixed order style is assumed",
        "adverse_selection_bps_p95": "<=3.50 when maker or mixed order style is assumed",
        "latency_ms_p95": "<=2000",
        "participation_rate_p95": "<=0.05",
        "capacity_notional_usdt": "> proposed tier notional",
        "order_availability_status": "PASS",
    },
    "forbidden_shortcuts": [
        "global_cost_gate_lowering",
        "implicit_cap_mutation",
        "unattributed_or_lineage_incomplete_fill_proof",
        "single_window_or_replay_only_profit_claim",
        "paper_archive_or_artifact_count_profit_claim",
        "broad_demo_api_permission_as_candidate_authority",
    ],
    "max_safe_next_action": (
        "operator_qc_review_cap_envelope_proposal_after_all_floor_evidence_is_present"
    ),
}
AUTHORITY_BEARING_TRUE_KEYS = {
    "global_cost_gate_lowering_recommended",
    "probe_authority_granted",
    "order_authority_granted",
    "active_runtime_probe_authority",
    "active_runtime_order_authority",
    "bounded_demo_probe_authorized",
    "review_grants_runtime_authority",
    "operator_authorization_object_emitted",
    "promotion_evidence",
    "promotion_proof",
    "runtime_mutation_performed",
    "pg_write_performed",
    "bybit_call_performed",
    "order_submission_performed",
}
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


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def _parse_utc(value: Any) -> dt.datetime | None:
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
    parsed = _parse_utc(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    source_error: str | None,
    now_utc: dt.datetime,
) -> dict[str, Any]:
    data = _dict(payload)
    generated_at = data.get("generated_at_utc")
    return {
        "name": name,
        "present": bool(data) and source_error is None,
        "path": str(path) if path else None,
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "generated_at_utc": generated_at,
        "age_seconds": _round(_age_seconds(generated_at, now_utc=now_utc), 3),
        "source_error": source_error,
    }


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
        for key in AUTHORITY_BEARING_TRUE_KEYS:
            if _truthy_authority(data.get(key)):
                return False
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return True


def _candidate_rows(packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(_dict(packet).get("ranked_false_negative_candidates")):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _select_candidate(
    packet: dict[str, Any] | None,
    selected_side_cell_key: str | None,
) -> tuple[dict[str, Any] | None, str]:
    rows = _candidate_rows(packet)
    selected_key = _str(selected_side_cell_key)
    if selected_key:
        for row in rows:
            if _str(row.get("side_cell_key")) == selected_key:
                return row, "explicit_side_cell_key"
        return None, "explicit_side_cell_key_not_found"
    if rows:
        return rows[0], "top_ranked_false_negative"
    return None, "no_ranked_false_negative_candidate"


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any]:
    row = _dict(candidate)
    return {
        "side_cell_key": row.get("side_cell_key"),
        "candidate_class": row.get("candidate_class"),
        "false_negative_rank": row.get("false_negative_rank"),
        "learning_diagnosis": row.get("learning_diagnosis"),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "next_action": row.get("next_action"),
        "strategy_names": row.get("strategy_names") or [],
        "symbols": row.get("symbols") or [],
        "sides": row.get("sides") or [],
        "horizon_minutes": row.get("horizon_minutes") or [],
        "dominant_horizon_minutes": row.get("dominant_horizon_minutes"),
        "outcome_count": _int(row.get("outcome_count")),
        "avg_gross_bps": _round(row.get("avg_gross_bps")),
        "avg_net_bps": _round(row.get("avg_net_bps")),
        "avg_cost_bps": _round(row.get("avg_cost_bps")),
        "net_positive_pct": _round(row.get("net_positive_pct")),
        "net_cost_cushion_bps": _round(row.get("net_cost_cushion_bps")),
        "wrongful_block_score": _round(row.get("wrongful_block_score")),
        "required_net_uplift_bps": _round(row.get("required_net_uplift_bps")),
        "operator_review_required": row.get("operator_review_required") is True,
        "global_cost_gate_lowering_recommended": _truthy_authority(
            row.get("global_cost_gate_lowering_recommended")
        ),
        "probe_authority_granted": _truthy_authority(row.get("probe_authority_granted")),
        "order_authority_granted": _truthy_authority(row.get("order_authority_granted")),
        "promotion_evidence": _truthy_authority(row.get("promotion_evidence")),
    }


def _proposal_id(candidate: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "side_cell_key": candidate.get("side_cell_key"),
            "rank": candidate.get("false_negative_rank"),
            "class": candidate.get("candidate_class"),
        },
        sort_keys=True,
        default=str,
    )
    return "cost_gate_parameter_proposal:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _proposal_from_candidate(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    row = _candidate_summary(candidate)
    if not row.get("side_cell_key"):
        return None
    return {
        "proposal_id": _proposal_id(row),
        "proposal_status": "INACTIVE_REVIEW_PACKET_ONLY",
        "proposal_kind": "cost_gate_false_negative_bounded_demo_probe_candidate",
        "learned_candidate_source": "cost_gate_false_negative_candidate_packet_v1",
        "side_cell_key": row.get("side_cell_key"),
        "strategy_names": row.get("strategy_names"),
        "symbols": row.get("symbols"),
        "sides": row.get("sides"),
        "candidate_class": row.get("candidate_class"),
        "false_negative_rank": row.get("false_negative_rank"),
        "dominant_horizon_minutes": row.get("dominant_horizon_minutes"),
        "horizon_minutes": row.get("horizon_minutes"),
        "profit_thesis": {
            "avg_gross_bps": row.get("avg_gross_bps"),
            "avg_net_bps": row.get("avg_net_bps"),
            "avg_cost_bps": row.get("avg_cost_bps"),
            "net_positive_pct": row.get("net_positive_pct"),
            "net_cost_cushion_bps": row.get("net_cost_cushion_bps"),
            "wrongful_block_score": row.get("wrongful_block_score"),
            "outcome_count": row.get("outcome_count"),
        },
        "proposed_parameter_changes": [
            {
                "parameter": "bounded_demo_probe_candidate_side_cell_key",
                "current_value": None,
                "proposed_value": row.get("side_cell_key"),
                "mutation_allowed_by_this_packet": False,
            },
            {
                "parameter": "bounded_demo_probe_review_horizon_minutes",
                "current_value": None,
                "proposed_value": (
                    row.get("dominant_horizon_minutes") or row.get("horizon_minutes")
                ),
                "mutation_allowed_by_this_packet": False,
            },
            {
                "parameter": "main_cost_gate_adjustment",
                "current_value": "UNCHANGED",
                "proposed_value": "NONE",
                "mutation_allowed_by_this_packet": False,
            },
            {
                "parameter": "bounded_demo_probe_cap_envelope",
                "current_value": "UNCHANGED",
                "proposed_value": "REQUIRES_SEPARATE_OPERATOR_QC_E3_BB_REVIEW",
                "mutation_allowed_by_this_packet": False,
            },
        ],
        "required_pre_authorization_evidence": [
            "profit_evidence_quality_overhang_resolved_or_operator_quarantined",
            "candidate_matched_touchability_evidence",
            "candidate_matched_fill_fee_slippage_lineage",
            "candidate_matched_blocked_signal_controls",
            "cap_envelope_evidence_floor_satisfied_if_cap_change_is_requested",
            "bounded_demo_probe_preflight_review_packet",
            "separate_operator_bounded_probe_authorization_object",
        ],
        "cap_envelope_evidence_floor": CAP_ENVELOPE_EVIDENCE_FLOOR,
        "forbidden_interpretations": [
            "not_a_cost_gate_lowering",
            "not_a_cap_mutation",
            "not_probe_authority",
            "not_order_authority",
            "not_runtime_config",
            "not_live_promotion",
            "not_promotion_evidence",
        ],
        "max_safe_next_action": (
            "operator_review_parameter_proposal_then_build_no_authority_preflight"
        ),
    }


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


def _status_from_gates(gates: list[dict[str, Any]]) -> str:
    failed = {gate["name"] for gate in gates if gate.get("passed") is not True}
    if "authority_boundary_preserved" in failed:
        return "AUTHORITY_BOUNDARY_VIOLATION"
    if "learning_ssot_ready" in failed:
        return "LEARNING_SSOT_DECISION_NOT_READY"
    if "profit_evidence_quality_cleared" in failed:
        return "PROFIT_EVIDENCE_QUALITY_NOT_CLEARED"
    if "learned_candidate_packet_ready" in failed:
        return "LEARNED_CANDIDATE_PACKET_NOT_READY"
    if "learned_candidate_reviewable" in failed:
        return "LEARNED_CANDIDATE_NOT_REVIEWABLE"
    return "REVIEWABLE_PARAMETER_PROPOSAL_READY"


def build_autonomous_parameter_proposal(
    *,
    learning_ssot_decision: dict[str, Any] | None,
    false_negative_candidate_packet: dict[str, Any] | None = None,
    selected_side_cell_key: str | None = None,
    profit_evidence_quality_status: str = "BLOCKED_BY_OPERATOR_ACTION",
    learning_ssot_path: Path | None = None,
    false_negative_candidate_packet_path: Path | None = None,
    learning_ssot_error: str | None = None,
    false_negative_candidate_packet_error: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a fail-closed no-authority parameter proposal contract."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    ssot = _dict(learning_ssot_decision)
    packet = _dict(false_negative_candidate_packet)
    candidate_raw, selection_method = _select_candidate(packet, selected_side_cell_key)
    candidate = _candidate_summary(candidate_raw)
    proposal = _proposal_from_candidate(candidate_raw)
    ssot_answers = _dict(ssot.get("answers"))
    ssot_decision = _dict(ssot.get("ssot_decision"))
    packet_answers = _dict(packet.get("answers"))
    packet_summary = _dict(packet.get("summary"))
    quality_status = _str(profit_evidence_quality_status).upper()

    authority_preserved = _authority_preserved(ssot, packet, candidate_raw)
    ssot_ready = (
        learning_ssot_error is None
        and ssot.get("schema_version") == LEARNING_SSOT_DECISION_SCHEMA_VERSION
        and ssot.get("current_learning_ssot") == "artifact_probe_ledger_jsonl"
        and ssot_decision.get("artifact_probe_ledger_is_current_ssot") is True
        and ssot_decision.get("pg_backed_ledger_is_current_ssot") is not True
        and ssot_decision.get("pg_backed_cutover_ready") is not True
        and ssot_answers.get("global_cost_gate_lowering_recommended") is not True
        and ssot_answers.get("probe_authority_granted") is not True
        and ssot_answers.get("order_authority_granted") is not True
        and ssot_answers.get("promotion_evidence") is not True
    )
    quality_cleared = quality_status in PROFIT_EVIDENCE_CLEARED_STATUSES
    packet_ready = (
        false_negative_candidate_packet_error is None
        and packet.get("schema_version") == FALSE_NEGATIVE_CANDIDATE_SCHEMA_VERSION
        and packet.get("status") == READY_FALSE_NEGATIVE_PACKET_STATUS
        and packet_answers.get("operator_review_ready") is True
        and packet_answers.get("global_cost_gate_lowering_recommended") is not True
        and packet_answers.get("probe_authority_granted") is not True
        and packet_answers.get("order_authority_granted") is not True
        and packet_answers.get("promotion_evidence") is not True
        and _int(packet_summary.get("false_negative_candidate_count")) > 0
    )
    candidate_reviewable = (
        bool(candidate.get("side_cell_key"))
        and candidate.get("candidate_class") == "false_negative_after_cost"
        and candidate.get("operator_review_required") is True
        and candidate.get("global_cost_gate_lowering_recommended") is not True
        and candidate.get("probe_authority_granted") is not True
        and candidate.get("order_authority_granted") is not True
        and candidate.get("promotion_evidence") is not True
    )

    artifacts = {
        "learning_ssot_decision": _artifact_summary(
            name="learning_ssot_decision",
            path=learning_ssot_path,
            payload=ssot,
            source_error=learning_ssot_error,
            now_utc=now,
        ),
        "false_negative_candidate_packet": _artifact_summary(
            name="false_negative_candidate_packet",
            path=false_negative_candidate_packet_path,
            payload=packet,
            source_error=false_negative_candidate_packet_error,
            now_utc=now,
        ),
    }
    gates = [
        _gate(
            "authority_boundary_preserved",
            authority_preserved,
            status="PRESERVED" if authority_preserved else "VIOLATED",
            reason="inputs must not grant Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof",
            next_actions=["remove_authority_bearing_input_before_parameter_proposal"],
        ),
        _gate(
            "learning_ssot_ready",
            ssot_ready,
            status=str(ssot.get("status") or artifacts["learning_ssot_decision"]["status"] or "MISSING"),
            reason="learning SSOT must be artifact ledger current, no-authority, and no-PG-cutover",
            next_actions=["refresh_cost_gate_learning_ssot_decision"],
            evidence={
                "current_learning_ssot": ssot.get("current_learning_ssot"),
                "artifact_probe_ledger_is_current_ssot": ssot_decision.get(
                    "artifact_probe_ledger_is_current_ssot"
                ),
                "pg_backed_ledger_is_current_ssot": ssot_decision.get(
                    "pg_backed_ledger_is_current_ssot"
                ),
                "pg_backed_cutover_ready": ssot_decision.get("pg_backed_cutover_ready"),
            },
        ),
        _gate(
            "profit_evidence_quality_cleared",
            quality_cleared,
            status=quality_status or "UNKNOWN",
            reason="open-order overhang and fill-lineage blockers must be resolved or explicitly quarantined before proposing a bounded candidate",
            next_actions=[
                "resolve_or_operator_quarantine_profit_evidence_quality_blocker_before_parameter_proposal"
            ],
        ),
        _gate(
            "learned_candidate_packet_ready",
            packet_ready,
            status=str(packet.get("status") or artifacts["false_negative_candidate_packet"]["status"] or "MISSING"),
            reason="learned candidate packet must be fresh enough for review and contain no-authority ranked false negatives",
            next_actions=["refresh_cost_gate_false_negative_candidate_packet"],
            evidence={
                "false_negative_candidate_count": packet_summary.get(
                    "false_negative_candidate_count"
                ),
                "operator_review_ready": packet_answers.get("operator_review_ready"),
            },
        ),
        _gate(
            "learned_candidate_reviewable",
            candidate_reviewable,
            status=str(candidate.get("status") or selection_method),
            reason="selected learned row must remain a no-authority false-negative after-cost candidate",
            next_actions=["select_reviewable_false_negative_candidate"],
            evidence={
                "selection_method": selection_method,
                "selected_side_cell_key": selected_side_cell_key,
                "candidate": candidate,
            },
        ),
    ]
    failed_gates = [gate for gate in gates if gate.get("passed") is not True]
    status = _status_from_gates(gates)
    next_actions = _dedupe(
        [
            action
            for gate in failed_gates
            for action in _list(gate.get("next_actions"))
        ]
    )
    if not next_actions and status == "REVIEWABLE_PARAMETER_PROPOSAL_READY":
        next_actions = [
            "operator_review_parameter_proposal_before_any_bounded_probe_preflight",
            "build_no_authority_candidate_matched_bounded_demo_probe_preflight",
        ]

    return {
        "schema_version": AUTONOMOUS_PARAMETER_PROPOSAL_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(gate["name"] for gate in failed_gates)
        or "learned_candidate_converted_to_reviewable_proposal_only",
        "proposal_scope": "review_packet_only_not_runtime_mutation",
        "selection_method": selection_method,
        "selected_side_cell_key": candidate.get("side_cell_key"),
        "candidate": candidate,
        "proposal": proposal if status == "REVIEWABLE_PARAMETER_PROPOSAL_READY" else None,
        "gates": gates,
        "blocking_gate_count": len(failed_gates),
        "blocking_gates": [gate["name"] for gate in failed_gates],
        "next_actions": next_actions,
        "artifacts": artifacts,
        "answers": {
            "learning_output_converted_to_reviewable_proposal": (
                status == "REVIEWABLE_PARAMETER_PROPOSAL_READY"
            ),
            "reviewable_parameter_proposal_emitted": (
                status == "REVIEWABLE_PARAMETER_PROPOSAL_READY" and proposal is not None
            ),
            "bounded_demo_probe_preflight_ready": False,
            "bounded_demo_probe_authorized": False,
            "cap_envelope_mutation_allowed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "operator_authorization_object_emitted": False,
            "promotion_evidence": False,
            "runtime_mutation_required": False,
            "runtime_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_required": False,
            "pg_write_performed": False,
            "bybit_call_required": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    proposal = _dict(packet.get("proposal"))
    candidate = _dict(packet.get("candidate"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate Autonomous Parameter Proposal",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Side-cell: `{packet.get('selected_side_cell_key')}`",
        f"- Candidate class: `{candidate.get('candidate_class')}`",
        f"- Proposal id: `{proposal.get('proposal_id')}`",
        f"- Reviewable proposal emitted: `{answers.get('reviewable_parameter_proposal_emitted')}`",
        f"- Probe authority granted: `{answers.get('probe_authority_granted')}`",
        f"- Order authority granted: `{answers.get('order_authority_granted')}`",
        f"- Cap envelope mutation allowed: `{answers.get('cap_envelope_mutation_allowed')}`",
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
    parser.add_argument("--learning-ssot-decision-json", type=Path, required=True)
    parser.add_argument("--false-negative-candidate-packet-json", type=Path, required=True)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument(
        "--profit-evidence-quality-status",
        default="BLOCKED_BY_OPERATOR_ACTION",
        help=(
            "Current P0 profit-evidence-quality status. READY proposal requires "
            "DONE, DONE_WITH_CONCERNS, or EXPLICITLY_QUARANTINED_BY_OPERATOR."
        ),
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    ssot, ssot_err = _read_json(args.learning_ssot_decision_json)
    candidate_packet, candidate_err = _read_json(args.false_negative_candidate_packet_json)
    packet = build_autonomous_parameter_proposal(
        learning_ssot_decision=ssot,
        false_negative_candidate_packet=candidate_packet,
        selected_side_cell_key=args.selected_side_cell_key,
        profit_evidence_quality_status=args.profit_evidence_quality_status,
        learning_ssot_path=args.learning_ssot_decision_json,
        false_negative_candidate_packet_path=args.false_negative_candidate_packet_json,
        learning_ssot_error=ssot_err,
        false_negative_candidate_packet_error=candidate_err,
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
