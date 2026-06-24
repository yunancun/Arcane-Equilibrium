#!/usr/bin/env python3
"""Review bounded demo-probe outcomes against the sealed preflight design.

This artifact closes the loop after a future bounded demo probe: it consumes
the no-authority preflight design plus JSONL ledger rows and emits a
machine-checkable review verdict. It does not query PG, call Bybit, submit
orders, lower the Cost Gate, grant probe/order authority, or mutate runtime
state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    ADMIT_DECISION,
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)
from cost_gate_learning_lane.proof_exclusion import proof_exclusion_reasons
from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger


BOUNDED_PROBE_RESULT_REVIEW_SCHEMA_VERSION = "bounded_demo_probe_result_review_v1"
BOUNDARY = (
    "artifact-only bounded demo-probe result review; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
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


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _generated_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_str(row.get("generated_at_utc")), _str(row.get("attempt_id")))


def _side_cell_key_from_preflight(preflight: dict[str, Any]) -> str:
    design = _dict(preflight.get("bounded_demo_probe_design"))
    candidate = _dict(design.get("candidate"))
    return _str(candidate.get("side_cell_key") or preflight.get("side_cell_key"))


def _design_summary(preflight: dict[str, Any]) -> dict[str, Any]:
    design = _dict(preflight.get("bounded_demo_probe_design"))
    candidate = _dict(design.get("candidate"))
    limits = _dict(design.get("suggested_initial_probe_limits"))
    success = _dict(design.get("success_criteria"))
    return {
        "schema_version": design.get("schema_version"),
        "status": design.get("status"),
        "side_cell_key": candidate.get("side_cell_key") or preflight.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": (
            candidate.get("outcome_horizon_minutes")
            or preflight.get("outcome_horizon_minutes")
        ),
        "max_probe_intents_before_review": _int(
            limits.get("max_probe_intents_before_review"),
            default=3,
        ),
        "max_filled_probe_outcomes_before_review": _int(
            limits.get("max_filled_probe_outcomes_before_review"),
            default=3,
        ),
        "max_total_filled_probe_outcomes_before_second_review": _int(
            limits.get("max_total_filled_probe_outcomes_before_second_review"),
            default=10,
        ),
        "max_demo_notional_usdt_per_order": _float(
            limits.get("max_demo_notional_usdt_per_order")
        ),
        "max_total_demo_notional_usdt_before_review": _float(
            limits.get("max_total_demo_notional_usdt_before_review")
        ),
        "min_filled_probe_outcomes_for_first_review": _int(
            success.get("min_filled_probe_outcomes_for_first_review"),
            default=3,
        ),
        "min_filled_probe_outcomes_for_learning_review": _int(
            success.get("min_filled_probe_outcomes_for_learning_review"),
            default=10,
        ),
        "min_realized_avg_net_bps": _float(
            success.get("min_realized_avg_net_bps")
        )
        if success.get("min_realized_avg_net_bps") is not None
        else 0.0,
        "min_realized_net_positive_pct": _float(
            success.get("min_realized_net_positive_pct")
        )
        if success.get("min_realized_net_positive_pct") is not None
        else 60.0,
        "promotion_evidence": success.get("promotion_evidence") is True,
    }


def _authority_preserved(preflight: dict[str, Any], design: dict[str, Any]) -> bool:
    answers = _dict(preflight.get("answers"))
    design_payload = _dict(preflight.get("bounded_demo_probe_design"))
    boundary = _dict(design_payload.get("authority_boundary"))
    for source in (preflight, answers, boundary, design):
        if source.get("global_cost_gate_lowering_recommended") is True:
            return False
        if source.get("probe_authority_granted") is True:
            return False
        if source.get("order_authority_granted") is True:
            return False
        if source.get("promotion_evidence") is True:
            return False
        if source.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
    return True


def _latest_unique_by_attempt(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=_generated_sort_key):
        attempt_id = _str(row.get("attempt_id"))
        if not attempt_id:
            continue
        latest[attempt_id] = row
    return [latest[key] for key in sorted(latest)]


def _horizon_matches(row: dict[str, Any], horizon_minutes: Any) -> bool:
    expected = _int(horizon_minutes)
    observed = _int(row.get("horizon_minutes"))
    return expected <= 0 or observed <= 0 or observed == expected


def _with_proof_exclusion(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    enriched["proof_exclusion_reasons"] = proof_exclusion_reasons(row)
    return enriched


def _proof_exclusion_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": row.get("record_type"),
        "attempt_id": row.get("attempt_id"),
        "side_cell_key": row.get("side_cell_key"),
        "strategy_name": row.get("strategy_name"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "outcome_source": row.get("outcome_source"),
        "realized_net_bps": _round(row.get("realized_net_bps")),
        "proof_exclusion_reasons": _list(row.get("proof_exclusion_reasons")),
    }


def _proof_exclusion_summary(
    excluded_probe_rows: list[dict[str, Any]],
    excluded_control_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    reason_counts: dict[str, int] = {}
    for row in [*excluded_probe_rows, *excluded_control_rows]:
        for reason in _list(row.get("proof_exclusion_reasons")):
            key = _str(reason)
            if key:
                reason_counts[key] = reason_counts.get(key, 0) + 1
    return {
        "schema_version": "bounded_demo_probe_proof_exclusion_v1",
        "rule": (
            "unattributed or lineage-incomplete fill-backed rows are excluded "
            "from bounded-probe, Cost Gate, promotion, and risk-adjusted net "
            "PnL proof forever"
        ),
        "proof_excluded_probe_outcome_count": len(excluded_probe_rows),
        "proof_excluded_matched_control_outcome_count": len(excluded_control_rows),
        "reason_counts": dict(sorted(reason_counts.items())),
        "excluded_probe_outcomes": [
            _proof_exclusion_row(row) for row in excluded_probe_rows
        ],
        "excluded_matched_control_outcomes": [
            _proof_exclusion_row(row) for row in excluded_control_rows
        ],
        "promotion_evidence": False,
    }


def _matching_probe_rows(
    ledger_rows: list[dict[str, Any]],
    *,
    side_cell_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    admissions = []
    outcomes = []
    excluded_outcomes = []
    for row in ledger_rows:
        if _str(row.get("side_cell_key")) != side_cell_key:
            continue
        record_type = _str(row.get("record_type"))
        if (
            record_type == PROBE_ADMISSION_DECISION_RECORD_TYPE
            and _str(row.get("decision")) == ADMIT_DECISION
        ):
            admissions.append(row)
        elif record_type == PROBE_OUTCOME_RECORD_TYPE:
            if _float(row.get("realized_net_bps")) is not None:
                enriched = _with_proof_exclusion(row)
                if enriched["proof_exclusion_reasons"]:
                    excluded_outcomes.append(enriched)
                else:
                    outcomes.append(row)
    return (
        _latest_unique_by_attempt(admissions),
        _latest_unique_by_attempt(outcomes),
        _latest_unique_by_attempt(excluded_outcomes),
    )


def _matching_control_rows(
    ledger_rows: list[dict[str, Any]],
    *,
    side_cell_key: str,
    horizon_minutes: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls = []
    excluded_controls = []
    for row in ledger_rows:
        if _str(row.get("side_cell_key")) != side_cell_key:
            continue
        if _str(row.get("record_type")) != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
            continue
        if not _horizon_matches(row, horizon_minutes):
            continue
        if _float(row.get("realized_net_bps")) is not None:
            enriched = _with_proof_exclusion(row)
            if enriched["proof_exclusion_reasons"]:
                excluded_controls.append(enriched)
            else:
                controls.append(row)
    return _latest_unique_by_attempt(controls), _latest_unique_by_attempt(excluded_controls)


def _net_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [
        value for value in (_float(row.get("realized_net_bps")) for row in rows)
        if value is not None
    ]
    gross = [
        value for value in (_float(row.get("gross_bps")) for row in rows)
        if value is not None
    ]
    count = len(nets)
    positive_count = sum(1 for value in nets if value > 0.0)
    avg_net = sum(nets) / count if count else None
    avg_gross = sum(gross) / len(gross) if gross else None
    positive_pct = 100.0 * positive_count / count if count else None
    return {
        "count": count,
        "positive_count": positive_count,
        "avg_net_bps": avg_net,
        "avg_gross_bps": avg_gross,
        "net_positive_pct": positive_pct,
    }


def _review_status(
    *,
    authority_preserved: bool,
    design: dict[str, Any],
    outcome_count: int,
    excluded_probe_outcome_count: int,
    avg_net_bps: float | None,
    net_positive_pct: float | None,
) -> tuple[str, str, list[str]]:
    if not authority_preserved:
        return (
            "AUTHORITY_BOUNDARY_VIOLATION",
            "preflight_or_design_contains_authority_granting_fields",
            ["remove_authority_granting_input_before_any_review"],
        )
    if not design.get("side_cell_key"):
        return (
            "PREFLIGHT_DESIGN_NOT_USABLE",
            "bounded_probe_design_missing_side_cell_key",
            ["refresh_sealed_horizon_probe_preflight_with_bounded_probe_design"],
        )
    if design.get("status") not in {
        "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
        "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION",
    }:
        return (
            "PREFLIGHT_DESIGN_NOT_USABLE",
            "bounded_probe_design_not_ready_for_result_review",
            ["refresh_or_operator_review_bounded_probe_design_before_result_review"],
        )
    if outcome_count <= 0:
        if excluded_probe_outcome_count > 0:
            return (
                "PROBE_OUTCOMES_PROOF_EXCLUDED",
                "completed_probe_outcomes_failed_attribution_or_lineage_proof",
                ["repair_fill_lineage_before_counting_probe_outcomes"],
            )
        return (
            "NO_PROBE_OUTCOMES_RECORDED",
            "bounded_demo_probe_has_no_completed_outcomes",
            ["wait_for_or_record_probe_outcome_rows_before_review"],
        )

    first_review_n = max(1, _int(design.get("min_filled_probe_outcomes_for_first_review"), 3))
    learning_review_n = max(
        first_review_n,
        _int(design.get("min_filled_probe_outcomes_for_learning_review"), 10),
    )
    min_avg = _float(design.get("min_realized_avg_net_bps"))
    min_pct = _float(design.get("min_realized_net_positive_pct"))
    min_avg = min_avg if min_avg is not None else 0.0
    min_pct = min_pct if min_pct is not None else 60.0

    if outcome_count < first_review_n:
        return (
            "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW",
            "completed_probe_outcomes_below_first_review_floor",
            ["continue_recording_probe_outcomes_with_existing_authority_boundaries"],
        )

    failed = (
        (avg_net_bps is not None and avg_net_bps < min_avg)
        or (net_positive_pct is not None and net_positive_pct < min_pct)
    )
    if failed:
        return (
            "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
            "realized_probe_outcomes_do_not_clear_design_success_criteria",
            ["stop_probe_and_keep_cost_gate_blocked_for_this_side_cell"],
        )
    if outcome_count < learning_review_n:
        return (
            "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            "first_probe_review_passed_but_learning_sample_not_complete",
            ["operator_review_first_probe_results_before_any_additional_probe_budget"],
        )
    return (
        "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
        "probe_results_clear_learning_review_floor_but_do_not_grant_promotion",
        ["operator_review_probe_learning_results_before_any_promotion_or_gate_change"],
    )


def _evidence_quality(
    *,
    design: dict[str, Any],
    review_status: str,
    probe_summary: dict[str, Any],
    control_summary: dict[str, Any],
    proof_exclusion: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    first_review_n = max(1, _int(design.get("min_filled_probe_outcomes_for_first_review"), 3))
    learning_review_n = max(
        first_review_n,
        _int(design.get("min_filled_probe_outcomes_for_learning_review"), 10),
    )
    probe_count = _int(probe_summary.get("count"))
    control_count = _int(control_summary.get("count"))
    excluded_probe_count = _int(proof_exclusion.get("proof_excluded_probe_outcome_count"))
    excluded_control_count = _int(
        proof_exclusion.get("proof_excluded_matched_control_outcome_count")
    )
    probe_avg = _float(probe_summary.get("avg_net_bps"))
    control_avg = _float(control_summary.get("avg_net_bps"))
    probe_pct = _float(probe_summary.get("net_positive_pct"))
    control_pct = _float(control_summary.get("net_positive_pct"))
    avg_delta = (
        probe_avg - control_avg
        if probe_avg is not None and control_avg is not None
        else None
    )
    edge_capture_ratio = (
        probe_avg / control_avg
        if probe_avg is not None and control_avg is not None and control_avg > 0.0
        else None
    )
    execution_gap_bps = (
        -avg_delta
        if avg_delta is not None and avg_delta < 0.0
        else None
    )
    pct_delta = (
        probe_pct - control_pct
        if probe_pct is not None and control_pct is not None
        else None
    )

    if review_status == "AUTHORITY_BOUNDARY_VIOLATION":
        status = "AUTHORITY_BOUNDARY_VIOLATION"
        reason = "authority_boundary_violation_prevents_evidence_quality_review"
        next_actions = ["remove_authority_granting_input_before_any_review"]
    elif review_status == "PREFLIGHT_DESIGN_NOT_USABLE":
        status = "PREFLIGHT_DESIGN_NOT_USABLE"
        reason = "bounded_probe_design_not_usable_for_evidence_quality_review"
        next_actions = ["refresh_or_operator_review_bounded_probe_design_before_result_review"]
    elif probe_count <= 0 and excluded_probe_count > 0:
        status = "PROBE_OUTCOMES_PROOF_EXCLUDED"
        reason = "completed_probe_outcomes_failed_attribution_or_lineage_proof"
        next_actions = ["repair_fill_lineage_before_counting_probe_outcomes"]
    elif probe_count <= 0:
        status = "NO_PROBE_OUTCOMES_RECORDED"
        reason = "completed_probe_outcomes_missing"
        next_actions = ["wait_for_or_record_probe_outcome_rows_before_review"]
    elif probe_count < first_review_n:
        status = "PROBE_SAMPLE_BELOW_FIRST_REVIEW_FLOOR"
        reason = "completed_probe_outcomes_below_first_review_floor"
        next_actions = ["continue_recording_probe_outcomes_with_existing_authority_boundaries"]
    elif review_status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED":
        status = "REALIZED_EDGE_FAILED"
        reason = "probe_realized_edge_failed_absolute_success_criteria"
        next_actions = ["stop_probe_and_keep_cost_gate_blocked_for_this_side_cell"]
    elif control_count <= 0:
        status = "CONTROL_COMPARISON_MISSING"
        reason = "matched_blocked_signal_control_outcomes_missing_for_same_side_cell_horizon"
        next_actions = [
            "record_matched_blocked_signal_outcomes_for_same_side_cell_and_horizon"
        ]
    elif control_count < first_review_n:
        status = "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR"
        reason = "matched_blocked_signal_control_outcomes_below_first_review_floor"
        next_actions = [
            "continue_recording_matched_blocked_signal_control_outcomes"
        ]
    elif avg_delta is not None and avg_delta <= 0.0:
        status = "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
        reason = "probe_realized_edge_does_not_capture_matched_blocked_signal_control_edge"
        next_actions = [
            "investigate_probe_execution_realism_slippage_and_timing_before_cost_gate_review"
        ]
    elif probe_count < learning_review_n:
        status = "FIRST_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
        reason = "first_probe_review_has_matched_blocked_signal_control_comparison"
        next_actions = ["operator_review_first_probe_results_with_matched_control_before_additional_budget"]
    else:
        status = "LEARNING_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
        reason = "learning_probe_review_has_matched_blocked_signal_control_comparison"
        next_actions = ["operator_review_probe_learning_results_with_matched_control_before_any_gate_change"]

    quality = {
        "schema_version": "bounded_demo_probe_evidence_quality_v1",
        "status": status,
        "reason": reason,
        "matched_control_required": probe_count >= first_review_n,
        "matched_control_present": control_count > 0,
        "matched_control_outcome_count": control_count,
        "proof_excluded_probe_outcome_count": excluded_probe_count,
        "proof_excluded_matched_control_outcome_count": excluded_control_count,
        "proof_exclusion_present": excluded_probe_count > 0 or excluded_control_count > 0,
        "proof_exclusion_reason_counts": proof_exclusion.get("reason_counts") or {},
        "matched_control_positive_outcome_count": _int(control_summary.get("positive_count")),
        "matched_control_avg_gross_bps": _round(control_summary.get("avg_gross_bps")),
        "matched_control_avg_net_bps": _round(control_avg),
        "matched_control_net_positive_pct": _round(control_pct),
        "probe_minus_control_avg_net_bps": _round(avg_delta),
        "probe_edge_capture_ratio": _round(edge_capture_ratio),
        "probe_execution_gap_bps": _round(execution_gap_bps),
        "probe_net_positive_pct_minus_control_pct": _round(pct_delta),
        "probe_outperforms_matched_control": (
            avg_delta is not None and avg_delta > 0.0
        ),
        "execution_realism_gap": (
            status == "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
        ),
        "matched_control_horizon_minutes": design.get("outcome_horizon_minutes"),
        "first_review_outcome_floor": first_review_n,
        "learning_review_outcome_floor": learning_review_n,
        "anecdote_risk": status
        in {
            "CONTROL_COMPARISON_MISSING",
            "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
        },
        "promotion_evidence": False,
    }
    return quality, next_actions


def build_bounded_demo_probe_result_review(
    *,
    preflight: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a no-authority result review for a bounded demo probe."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    design = _design_summary(preflight)
    side_cell_key = _str(design.get("side_cell_key") or _side_cell_key_from_preflight(preflight))
    admissions, outcomes, excluded_probe_outcomes = _matching_probe_rows(
        ledger_rows,
        side_cell_key=side_cell_key,
    )
    controls, excluded_control_outcomes = _matching_control_rows(
        ledger_rows,
        side_cell_key=side_cell_key,
        horizon_minutes=design.get("outcome_horizon_minutes"),
    )
    proof_exclusion = _proof_exclusion_summary(
        excluded_probe_outcomes,
        excluded_control_outcomes,
    )
    probe_summary = _net_summary(outcomes)
    control_summary = _net_summary(controls)
    outcome_count = _int(probe_summary.get("count"))
    raw_probe_outcome_count = outcome_count + len(excluded_probe_outcomes)
    positive_count = _int(probe_summary.get("positive_count"))
    avg_net = _float(probe_summary.get("avg_net_bps"))
    avg_gross = _float(probe_summary.get("avg_gross_bps"))
    net_positive_pct = _float(probe_summary.get("net_positive_pct"))
    authority_ok = _authority_preserved(preflight, design)
    status, reason, next_actions = _review_status(
        authority_preserved=authority_ok,
        design=design,
        outcome_count=outcome_count,
        excluded_probe_outcome_count=len(excluded_probe_outcomes),
        avg_net_bps=avg_net,
        net_positive_pct=net_positive_pct,
    )
    evidence_quality, quality_actions = _evidence_quality(
        design=design,
        review_status=status,
        probe_summary=probe_summary,
        control_summary=control_summary,
        proof_exclusion=proof_exclusion,
    )
    if (
        evidence_quality.get("anecdote_risk") is True
        or evidence_quality.get("execution_realism_gap") is True
    ):
        next_actions = list(dict.fromkeys([*quality_actions, *next_actions]))
    else:
        next_actions = list(dict.fromkeys([*next_actions, *quality_actions]))
    if proof_exclusion.get("proof_excluded_probe_outcome_count") or proof_exclusion.get(
        "proof_excluded_matched_control_outcome_count"
    ):
        next_actions = list(
            dict.fromkeys(
                [
                    "repair_or_quarantine_proof_excluded_fill_lineage_before_any_cost_gate_or_promotion_review",
                    *next_actions,
                ]
            )
        )
    first_review_n = max(1, _int(design.get("min_filled_probe_outcomes_for_first_review"), 3))
    max_outcomes_before_review = max(
        first_review_n,
        _int(design.get("max_filled_probe_outcomes_before_review"), first_review_n),
    )
    operator_review_required = outcome_count >= max_outcomes_before_review or status in {
        "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
        "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
        "AUTHORITY_BOUNDARY_VIOLATION",
        "PROBE_OUTCOMES_PROOF_EXCLUDED",
    }
    proof_exclusion_present = (
        proof_exclusion.get("proof_excluded_probe_outcome_count") > 0
        or proof_exclusion.get("proof_excluded_matched_control_outcome_count") > 0
    )
    operator_review_required = operator_review_required or proof_exclusion_present

    return {
        "schema_version": BOUNDED_PROBE_RESULT_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "side_cell_key": side_cell_key,
        "candidate": {
            "strategy_name": design.get("strategy_name"),
            "symbol": design.get("symbol"),
            "side": design.get("side"),
            "outcome_horizon_minutes": design.get("outcome_horizon_minutes"),
        },
        "probe_result_summary": {
            "admitted_probe_attempt_count": len(admissions),
            "raw_completed_probe_outcome_count": raw_probe_outcome_count,
            "completed_probe_outcome_count": outcome_count,
            "proof_eligible_probe_outcome_count": outcome_count,
            "proof_excluded_probe_outcome_count": len(excluded_probe_outcomes),
            "positive_probe_outcome_count": positive_count,
            "avg_realized_gross_bps": _round(avg_gross),
            "avg_realized_net_bps": _round(avg_net),
            "net_positive_pct": _round(net_positive_pct),
            "min_realized_avg_net_bps": design.get("min_realized_avg_net_bps"),
            "min_realized_net_positive_pct": design.get(
                "min_realized_net_positive_pct"
            ),
            "first_review_outcome_floor": first_review_n,
            "learning_review_outcome_floor": design.get(
                "min_filled_probe_outcomes_for_learning_review"
            ),
            "max_filled_probe_outcomes_before_review": max_outcomes_before_review,
        },
        "proof_exclusion": proof_exclusion,
        "evidence_quality": evidence_quality,
        "answers": {
            "authority_boundary_preserved": authority_ok,
            "operator_review_required": operator_review_required,
            "continue_probe_without_operator_review_allowed": (
                authority_ok
                and not proof_exclusion_present
                and outcome_count < max_outcomes_before_review
                and status == "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW"
            ),
            "stop_probe_recommended": status
            in {
                "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
                "AUTHORITY_BOUNDARY_VIOLATION",
                "PROBE_OUTCOMES_PROOF_EXCLUDED",
            },
            "learning_review_candidate": (
                status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED"
            ),
            "matched_control_comparison_present": (
                evidence_quality.get("matched_control_present") is True
            ),
            "anecdote_risk": evidence_quality.get("anecdote_risk") is True,
            "execution_realism_gap": (
                evidence_quality.get("execution_realism_gap") is True
            ),
            "proof_exclusion_present": proof_exclusion_present,
            "proof_excluded_probe_outcome_count": len(excluded_probe_outcomes),
            "proof_excluded_matched_control_outcome_count": len(excluded_control_outcomes),
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": next_actions,
        "design": design,
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("probe_result_summary"))
    quality = _dict(packet.get("evidence_quality"))
    proof_exclusion = _dict(packet.get("proof_exclusion"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Bounded Demo Probe Result Review",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Side-cell: `{packet.get('side_cell_key')}`",
        f"- Raw completed outcomes: `{summary.get('raw_completed_probe_outcome_count')}`",
        f"- Completed outcomes: `{summary.get('completed_probe_outcome_count')}`",
        f"- Proof-excluded probe outcomes: `{proof_exclusion.get('proof_excluded_probe_outcome_count')}`",
        f"- Avg net bps: `{summary.get('avg_realized_net_bps')}`",
        f"- Net-positive pct: `{summary.get('net_positive_pct')}`",
        f"- Evidence quality: `{quality.get('status')}`",
        f"- Matched control outcomes: `{quality.get('matched_control_outcome_count')}`",
        f"- Probe minus control avg net bps: `{quality.get('probe_minus_control_avg_net_bps')}`",
        f"- Probe edge capture ratio: `{quality.get('probe_edge_capture_ratio')}`",
        f"- Probe execution gap bps: `{quality.get('probe_execution_gap_bps')}`",
        f"- Operator review required: `{answers.get('operator_review_required')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Next Actions",
        "",
    ]
    for action in _list(packet.get("next_actions")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-json", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_demo_probe_result_review(
        preflight=_read_json(args.preflight_json),
        ledger_rows=read_jsonl_ledger(args.ledger),
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
