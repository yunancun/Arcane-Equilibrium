#!/usr/bin/env python3
"""Build a ranked profitability path scorecard from existing artifacts.

This module answers the operator question "how can this system become
profitable?" without granting order authority. It reads existing Cost Gate,
MM, Polymarket, and Gate-B artifacts and emits a single ranked set of paths
with the next proof gate for each one.

No PG query/write, Bybit call, order placement, config/risk/auth mutation,
runtime mutation, Cost Gate lowering, or probe authority is performed here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


PROFITABILITY_PATH_SCORECARD_SCHEMA_VERSION = "alpha_profitability_path_scorecard_v1"
BOUNDARY = (
    "artifact-only profitability path scorecard; no PG query/write, Bybit call, "
    "order, config, risk, auth, runtime mutation, main Cost Gate lowering, "
    "probe authority, or promotion authority"
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
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    out = _float(value)
    if out is None:
        return None
    return round(out, ndigits)


def _generated_at(payload: dict[str, Any]) -> Any:
    return (
        payload.get("generated_at_utc")
        or payload.get("created_at_utc")
        or payload.get("generated_at")
        or payload.get("generated")
        or payload.get("ts_utc")
    )


def _artifact_summary(
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    return {
        "name": name,
        "path": str(path) if path else None,
        "present": present,
        "schema_version": _dict(payload).get("schema_version") if present else None,
        "generated_at_utc": _generated_at(_dict(payload)) if present else None,
    }


def _score_priority(path: dict[str, Any]) -> tuple[int, float]:
    """Sort by status class first, then evidence strength."""
    status_rank = {
        "SEALED_HORIZON_PREFLIGHT_READY_FOR_OPERATOR_AUTHORIZATION": 6,
        "BOUNDED_DEMO_PROBE_LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED": 5,
        "BOUNDED_DEMO_PROBE_FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED": 6,
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REPAIR_REQUIRED": 6,
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_REQUIRED": 6,
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_GAP": 6,
        "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_READY_FOR_OPERATOR_REVIEW": 6,
        "BOUNDED_DEMO_PROBE_PLACEMENT_TOUCHABILITY_REPAIR_SAMPLE_MISMATCH": 6,
        "BOUNDED_DEMO_PROBE_PLACEMENT_PARTIAL_SKIP_REVIEW_REQUIRED": 7,
        "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS": 8,
        "BOUNDED_DEMO_PROBE_PLACEMENT_SAMPLE_REQUIRED": 8,
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_SAMPLE_REQUIRED": 7,
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_NOT_ALIGNED": 8,
        "BOUNDED_DEMO_PROBE_CONTROL_COMPARISON_REQUIRED": 7,
        "BOUNDED_DEMO_PROBE_COLLECT_MORE_OUTCOMES": 7,
        "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW": 7,
        "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE": 8,
        "SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW": 9,
        "SEALED_HORIZON_PREFLIGHT_PRODUCTION_LANE_NOT_READY": 9,
        "COST_GATE_CANDIDATE_READY_FOR_DATA_FLOW_PROOF": 10,
        "SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION": 11,
        "COST_GATE_CANDIDATE_EXECUTION_EVIDENCE_MISSING": 12,
        "HORIZON_EDGE_AMPLIFICATION_CANDIDATE": 20,
        "SEALED_HORIZON_PREFLIGHT_NOT_ALIGNED": 25,
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_AUTHORITY_BOUNDARY_VIOLATION": 25,
        "LOW_FRICTION_MM_GROSS_EDGE_BELOW_CURRENT_FEE": 40,
        "POLYMARKET_ALPHA_GROSS_BELOW_COST_OR_EXECUTION_UNMEASURED": 50,
        "BOUNDED_DEMO_PROBE_RESULT_FAILED_STOP": 85,
        "FEE_OR_SCALE_PATH_NOT_SHORT_TERM_ALPHA": 70,
        "GATE_B_ACTIONABLE_WINDOW_REVIEW": 30,
        "EVENT_WAIT_NO_ACTIONABLE_WINDOW": 80,
        "WAIT_FOR_ARTIFACT": 90,
        "SEALED_HORIZON_PREFLIGHT_AUTHORITY_BOUNDARY_VIOLATION": 96,
    }.get(_str(path.get("status")), 95)
    edge = _float(path.get("current_edge_bps")) or -9999.0
    sample = _int(path.get("sample_count"))
    return (status_rank, -(edge + min(sample, 100_000) / 100_000.0))


def _profit_packet_next_actions(packet: dict[str, Any] | None) -> list[str]:
    return [str(item) for item in _list(_dict(packet).get("next_actions"))]


def _profit_packet_status(packet: dict[str, Any] | None) -> str:
    return _str(_dict(packet).get("status"))


def _activation_status(
    profit_packet: dict[str, Any] | None,
    activation_preflight: dict[str, Any] | None,
) -> str:
    packet_activation = _dict(_dict(profit_packet).get("activation"))
    return _str(packet_activation.get("status") or _dict(activation_preflight).get("status"))


def _cost_gate_required_next_gate(
    *,
    profit_packet: dict[str, Any] | None,
    activation_preflight: dict[str, Any] | None,
) -> tuple[str, str]:
    packet_status = _profit_packet_status(profit_packet)
    activation = _activation_status(profit_packet, activation_preflight)
    actions = _profit_packet_next_actions(profit_packet)
    if packet_status == "DATA_FLOW_MONITOR_REQUIRED":
        return ("run_demo_data_flow_monitor", actions[0] if actions else "run_demo_data_flow_monitor_for_1h_4h_24h")
    if activation in {"NOT_ACCUMULATING", "NOT_INSTALLED", "INSTALLED_NOT_FIRING"}:
        return (
            "learning_stack_accumulates_ledger_and_outcome_rows",
            actions[0] if actions else "activate_or_repair_cost_gate_learning_lane_stack",
        )
    if packet_status == "OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES":
        return (
            "operator_review_before_bounded_demo_probe",
            actions[0] if actions else "operator_review_blocked_outcome_scorecard_before_probe_authority",
        )
    return (
        "demo_execution_realism_and_bounded_probe_preflight",
        actions[0] if actions else "prove_candidate_with_demo_execution_realism_before_any_gate_change",
    )


def _cost_gate_scorecard(counterfactual: dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_dict(counterfactual).get("learning_lane_scorecard"))


def _profit_ranking(counterfactual: dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_cost_gate_scorecard(counterfactual).get("profit_opportunity_ranking"))


def _horizon_scorecard(counterfactual: dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_cost_gate_scorecard(counterfactual).get("horizon_stability_scorecard"))


def _horizon_cells_by_key(counterfactual: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _list(_horizon_scorecard(counterfactual).get("top_side_cells")):
        if isinstance(row, dict) and row.get("side_cell_key"):
            out[str(row["side_cell_key"])] = row
    return out


def _sealed_replay_side_cell_key(sealed_replay: dict[str, Any] | None) -> str:
    return _str(
        _dict(
            _dict(_dict(sealed_replay).get("selection")).get("selected")
        ).get("side_cell_key")
        or _dict(_dict(sealed_replay).get("replay_evaluation")).get("side_cell_key")
    )


def _sealed_replay_by_key(
    horizon_sealed_replay: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    key = _sealed_replay_side_cell_key(horizon_sealed_replay)
    if not key:
        return {}
    return {key: _dict(horizon_sealed_replay)}


def _sealed_replay_evidence(sealed: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(sealed)
    if not payload:
        return {}
    replay = _dict(_dict(payload.get("replay_evaluation")).get("best_horizon"))
    primary = _dict(_dict(payload.get("replay_evaluation")).get("primary_horizon"))
    source = _dict(payload.get("source"))
    return {
        "sealed_replay_schema_version": payload.get("schema_version"),
        "sealed_replay_status": payload.get("status"),
        "sealed_replay_reason": payload.get("reason"),
        "sealed_replay_next_action": payload.get("next_action"),
        "sealed_replay_generated_at_utc": payload.get("generated_at_utc"),
        "sealed_replay_failed_gate_names": _dict(
            payload.get("replay_evaluation")
        ).get("failed_gate_names"),
        "sealed_replay_best_horizon_minutes": replay.get("horizon_minutes"),
        "sealed_replay_best_avg_net_bps": replay.get("avg_net_bps"),
        "sealed_replay_best_p50_gross_bps": replay.get("p50_gross_bps"),
        "sealed_replay_best_net_positive_pct": replay.get("net_positive_pct"),
        "sealed_replay_best_sample_count_for_gate": replay.get("sample_count_for_gate"),
        "sealed_replay_primary_horizon_minutes": primary.get("horizon_minutes"),
        "sealed_replay_primary_action": primary.get("learning_lane_action"),
        "sealed_replay_primary_avg_net_bps": primary.get("avg_net_bps"),
        "sealed_replay_horizon_packet_sha256": _dict(
            source.get("horizon_packet")
        ).get("sha256"),
        "sealed_replay_counterfactual_sha256": _dict(
            source.get("replay_counterfactual")
        ).get("sha256"),
    }


def _sealed_learning_evidence_side_cell_key(evidence: dict[str, Any] | None) -> str:
    return _str(
        _dict(evidence).get("side_cell_key")
        or _dict(_dict(evidence).get("review")).get("top_side_cell_key")
    )


def _sealed_learning_evidence_by_key(
    horizon_learning_evidence: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    key = _sealed_learning_evidence_side_cell_key(horizon_learning_evidence)
    if not key:
        return {}
    return {key: _dict(horizon_learning_evidence)}


def _sealed_probe_preflight_by_key(
    sealed_horizon_probe_preflight: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    key = _str(_dict(sealed_horizon_probe_preflight).get("side_cell_key"))
    if not key:
        return {}
    return {key: _dict(sealed_horizon_probe_preflight)}


def _bounded_probe_result_review_by_key(
    bounded_probe_result_review: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    payload = _dict(bounded_probe_result_review)
    key = _str(
        payload.get("side_cell_key") or _dict(payload.get("design")).get("side_cell_key")
    )
    if not key:
        return {}
    return {key: payload}


def _bounded_probe_execution_realism_review_by_key(
    bounded_probe_execution_realism_review: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    payload = _dict(bounded_probe_execution_realism_review)
    key = _str(
        payload.get("side_cell_key")
        or _dict(payload.get("candidate")).get("side_cell_key")
        or _dict(payload.get("source_result_review")).get("side_cell_key")
    )
    if not key:
        return {}
    return {key: payload}


def _bounded_probe_shadow_placement_impact_by_key(
    bounded_probe_shadow_placement_impact: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    payload = _dict(bounded_probe_shadow_placement_impact)
    key = _str(_dict(payload.get("candidate")).get("side_cell_key"))
    if not key:
        return {}
    return {key: payload}


def _sealed_learning_review_ready(evidence: dict[str, Any] | None) -> bool:
    payload = _dict(evidence)
    answers = _dict(payload.get("answers"))
    return (
        payload.get("schema_version") == "sealed_horizon_learning_evidence_v1"
        and payload.get("status") == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
        and answers.get("candidate_clears_operator_review_gate") is True
        and answers.get("order_authority_granted") is not True
        and answers.get("probe_authority_granted") is not True
        and answers.get("global_cost_gate_lowering_recommended") is not True
    )


def _sealed_learning_evidence_fields(evidence: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(evidence)
    if not payload:
        return {}
    materialization = _dict(payload.get("materialization"))
    outcomes = _dict(payload.get("outcomes"))
    review = _dict(payload.get("review"))
    artifacts = _dict(payload.get("artifacts"))
    return {
        "sealed_learning_schema_version": payload.get("schema_version"),
        "sealed_learning_status": payload.get("status"),
        "sealed_learning_reason": payload.get("reason"),
        "sealed_learning_generated_at_utc": payload.get("generated_at_utc"),
        "sealed_learning_side_cell_key": payload.get("side_cell_key"),
        "sealed_learning_source_kind": payload.get("source_kind"),
        "sealed_learning_outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
        "sealed_learning_input_feature_row_count": materialization.get(
            "input_feature_row_count"
        ),
        "sealed_learning_materialized_record_count": materialization.get(
            "materialized_record_count"
        ),
        "sealed_learning_all_order_authority_not_granted": materialization.get(
            "all_order_authority_not_granted"
        ),
        "sealed_learning_blocked_signal_outcome_count": outcomes.get(
            "blocked_signal_outcome_count"
        ),
        "sealed_learning_avg_gross_bps": outcomes.get("avg_gross_bps"),
        "sealed_learning_avg_net_bps": outcomes.get("avg_net_bps"),
        "sealed_learning_net_positive_pct": outcomes.get("net_positive_pct"),
        "sealed_learning_review_candidate_side_cell_count": review.get(
            "review_candidate_side_cell_count"
        ),
        "sealed_learning_top_side_cell_status": review.get("top_side_cell_status"),
        "sealed_learning_wrongful_block_score": review.get(
            "top_side_cell_wrongful_block_score"
        ),
        "sealed_learning_ledger_sha256": _dict(artifacts.get("ledger")).get("sha256"),
        "sealed_learning_source_rows_sha256": _dict(
            artifacts.get("source_rows")
        ).get("sha256"),
        "sealed_learning_review_sha256": _dict(artifacts.get("review")).get("sha256"),
    }


def _bounded_probe_result_review_fields(
    review: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(review)
    if not payload:
        return {
            "bounded_probe_result_review_present": False,
            "bounded_probe_result_review_status": None,
            "bounded_probe_result_review_completed_probe_outcome_count": 0,
            "bounded_probe_result_review_operator_review_required": False,
            "bounded_probe_result_review_stop_probe_recommended": False,
            "bounded_probe_result_review_learning_review_candidate": False,
            "bounded_probe_result_review_evidence_quality_status": None,
            "bounded_probe_result_review_matched_control_outcome_count": 0,
            "bounded_probe_result_review_probe_edge_capture_ratio": None,
            "bounded_probe_result_review_probe_execution_gap_bps": None,
            "bounded_probe_result_review_execution_realism_gap": False,
            "bounded_probe_result_review_anecdote_risk": False,
        }
    summary = _dict(payload.get("probe_result_summary"))
    quality = _dict(payload.get("evidence_quality"))
    answers = _dict(payload.get("answers"))
    design = _dict(payload.get("design"))
    return {
        "bounded_probe_result_review_present": True,
        "bounded_probe_result_review_schema_version": payload.get("schema_version"),
        "bounded_probe_result_review_status": payload.get("status"),
        "bounded_probe_result_review_reason": payload.get("reason"),
        "bounded_probe_result_review_generated_at_utc": payload.get(
            "generated_at_utc"
        ),
        "bounded_probe_result_review_side_cell_key": payload.get("side_cell_key"),
        "bounded_probe_result_review_next_actions": _list(
            payload.get("next_actions")
        ),
        "bounded_probe_result_review_admitted_probe_attempt_count": summary.get(
            "admitted_probe_attempt_count"
        ),
        "bounded_probe_result_review_completed_probe_outcome_count": summary.get(
            "completed_probe_outcome_count"
        ),
        "bounded_probe_result_review_positive_probe_outcome_count": summary.get(
            "positive_probe_outcome_count"
        ),
        "bounded_probe_result_review_avg_realized_gross_bps": summary.get(
            "avg_realized_gross_bps"
        ),
        "bounded_probe_result_review_avg_realized_net_bps": summary.get(
            "avg_realized_net_bps"
        ),
        "bounded_probe_result_review_net_positive_pct": summary.get(
            "net_positive_pct"
        ),
        "bounded_probe_result_review_min_realized_avg_net_bps": summary.get(
            "min_realized_avg_net_bps"
        ),
        "bounded_probe_result_review_min_realized_net_positive_pct": summary.get(
            "min_realized_net_positive_pct"
        ),
        "bounded_probe_result_review_first_review_outcome_floor": summary.get(
            "first_review_outcome_floor"
        ),
        "bounded_probe_result_review_learning_review_outcome_floor": summary.get(
            "learning_review_outcome_floor"
        ),
        "bounded_probe_result_review_max_filled_probe_outcomes_before_review": (
            summary.get("max_filled_probe_outcomes_before_review")
        ),
        "bounded_probe_result_review_authority_boundary_preserved": answers.get(
            "authority_boundary_preserved"
        ),
        "bounded_probe_result_review_operator_review_required": (
            answers.get("operator_review_required") is True
        ),
        "bounded_probe_result_review_continue_probe_without_operator_review_allowed": (
            answers.get("continue_probe_without_operator_review_allowed") is True
        ),
        "bounded_probe_result_review_stop_probe_recommended": (
            answers.get("stop_probe_recommended") is True
        ),
        "bounded_probe_result_review_learning_review_candidate": (
            answers.get("learning_review_candidate") is True
        ),
        "bounded_probe_result_review_probe_authority_granted": (
            answers.get("probe_authority_granted") is True
        ),
        "bounded_probe_result_review_order_authority_granted": (
            answers.get("order_authority_granted") is True
        ),
        "bounded_probe_result_review_main_cost_gate_adjustment": answers.get(
            "main_cost_gate_adjustment"
        ),
        "bounded_probe_result_review_promotion_evidence": (
            answers.get("promotion_evidence") is True
        ),
        "bounded_probe_result_review_design_status": design.get("status"),
        "bounded_probe_result_review_evidence_quality_status": quality.get("status"),
        "bounded_probe_result_review_evidence_quality_reason": quality.get("reason"),
        "bounded_probe_result_review_matched_control_required": (
            quality.get("matched_control_required") is True
        ),
        "bounded_probe_result_review_matched_control_present": (
            quality.get("matched_control_present") is True
        ),
        "bounded_probe_result_review_matched_control_outcome_count": quality.get(
            "matched_control_outcome_count"
        ),
        "bounded_probe_result_review_matched_control_avg_net_bps": quality.get(
            "matched_control_avg_net_bps"
        ),
        "bounded_probe_result_review_matched_control_net_positive_pct": quality.get(
            "matched_control_net_positive_pct"
        ),
        "bounded_probe_result_review_probe_minus_control_avg_net_bps": (
            quality.get("probe_minus_control_avg_net_bps")
        ),
        "bounded_probe_result_review_probe_edge_capture_ratio": (
            quality.get("probe_edge_capture_ratio")
        ),
        "bounded_probe_result_review_probe_execution_gap_bps": (
            quality.get("probe_execution_gap_bps")
        ),
        "bounded_probe_result_review_probe_outperforms_matched_control": (
            quality.get("probe_outperforms_matched_control") is True
        ),
        "bounded_probe_result_review_execution_realism_gap": (
            quality.get("execution_realism_gap") is True
        ),
        "bounded_probe_result_review_anecdote_risk": (
            quality.get("anecdote_risk") is True
        ),
    }


def _bounded_probe_execution_realism_review_fields(
    review: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(review)
    if not payload:
        return {
            "bounded_probe_execution_realism_review_present": False,
            "bounded_probe_execution_realism_review_status": None,
            "bounded_probe_execution_realism_review_primary_hypothesis": None,
            "bounded_probe_execution_realism_review_net_capture_gap_bps": None,
            "bounded_probe_execution_realism_review_probe_fill_backed_pct": None,
            "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed": False,
        }
    source = _dict(payload.get("source_result_review"))
    probe = _dict(payload.get("probe_execution_summary"))
    control = _dict(payload.get("matched_control_execution_summary"))
    gap = _dict(payload.get("gap_decomposition"))
    answers = _dict(payload.get("answers"))
    hypotheses = _list(payload.get("execution_gap_hypotheses"))
    first_hypothesis = (
        hypotheses[0] if hypotheses and isinstance(hypotheses[0], dict) else {}
    )
    return {
        "bounded_probe_execution_realism_review_present": True,
        "bounded_probe_execution_realism_review_schema_version": payload.get(
            "schema_version"
        ),
        "bounded_probe_execution_realism_review_status": payload.get("status"),
        "bounded_probe_execution_realism_review_reason": payload.get("reason"),
        "bounded_probe_execution_realism_review_generated_at_utc": payload.get(
            "generated_at_utc"
        ),
        "bounded_probe_execution_realism_review_side_cell_key": payload.get(
            "side_cell_key"
        ),
        "bounded_probe_execution_realism_review_next_actions": _list(
            payload.get("next_actions")
        ),
        "bounded_probe_execution_realism_review_result_review_status": (
            source.get("status")
        ),
        "bounded_probe_execution_realism_review_evidence_quality_status": (
            source.get("evidence_quality_status")
        ),
        "bounded_probe_execution_realism_review_probe_edge_capture_ratio": (
            source.get("probe_edge_capture_ratio")
        ),
        "bounded_probe_execution_realism_review_probe_execution_gap_bps": (
            source.get("probe_execution_gap_bps")
        ),
        "bounded_probe_execution_realism_review_probe_avg_net_bps": probe.get(
            "avg_net_bps"
        ),
        "bounded_probe_execution_realism_review_probe_avg_gross_bps": probe.get(
            "avg_gross_bps"
        ),
        "bounded_probe_execution_realism_review_probe_avg_cost_bps": probe.get(
            "avg_cost_bps"
        ),
        "bounded_probe_execution_realism_review_probe_fill_backed_pct": probe.get(
            "fill_backed_pct"
        ),
        "bounded_probe_execution_realism_review_control_avg_net_bps": control.get(
            "avg_net_bps"
        ),
        "bounded_probe_execution_realism_review_net_capture_gap_bps": gap.get(
            "net_capture_gap_bps"
        ),
        "bounded_probe_execution_realism_review_gross_capture_gap_bps": gap.get(
            "gross_capture_gap_bps"
        ),
        "bounded_probe_execution_realism_review_cost_or_slippage_gap_bps": gap.get(
            "cost_or_slippage_gap_bps"
        ),
        "bounded_probe_execution_realism_review_entry_delay_gap_ms": gap.get(
            "entry_delay_gap_ms"
        ),
        "bounded_probe_execution_realism_review_hypothesis_count": len(hypotheses),
        "bounded_probe_execution_realism_review_primary_hypothesis": (
            first_hypothesis.get("kind")
        ),
        "bounded_probe_execution_realism_review_execution_gap_confirmed": (
            answers.get("execution_realism_gap_confirmed") is True
        ),
        "bounded_probe_execution_realism_review_fill_backed_probe_execution_available": (
            answers.get("fill_backed_probe_execution_available") is True
        ),
        "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed": (
            answers.get("cost_gate_or_operator_review_allowed") is True
        ),
    }


def _bounded_probe_shadow_placement_impact_fields(
    impact: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(impact)
    if not payload:
        return {
            "bounded_probe_shadow_placement_impact_present": False,
            "bounded_probe_shadow_placement_impact_status": None,
            "bounded_probe_shadow_placement_sample_scope": None,
            "bounded_probe_shadow_placement_submit_count": 0,
            "bounded_probe_shadow_placement_candidate_matched_order_count": 0,
            "bounded_probe_shadow_placement_improves_touchability": False,
            "bounded_probe_shadow_placement_candidate_specific_alpha_proof": False,
        }
    candidate = _dict(payload.get("candidate"))
    summary = _dict(payload.get("shadow_summary"))
    answers = _dict(payload.get("answers"))
    return {
        "bounded_probe_shadow_placement_impact_present": True,
        "bounded_probe_shadow_placement_impact_schema_version": payload.get(
            "schema_version"
        ),
        "bounded_probe_shadow_placement_impact_status": payload.get("status"),
        "bounded_probe_shadow_placement_impact_reason": payload.get("reason"),
        "bounded_probe_shadow_placement_impact_generated_at_utc": payload.get(
            "generated_at_utc"
        ),
        "bounded_probe_shadow_placement_impact_next_actions": _list(
            payload.get("next_actions")
        ),
        "bounded_probe_shadow_placement_side_cell_key": candidate.get(
            "side_cell_key"
        ),
        "bounded_probe_shadow_placement_outcome_horizon_minutes": candidate.get(
            "outcome_horizon_minutes"
        ),
        "bounded_probe_shadow_placement_sample_scope": summary.get("sample_scope"),
        "bounded_probe_shadow_placement_reviewed_order_count": summary.get(
            "reviewed_order_count"
        ),
        "bounded_probe_shadow_placement_submit_count": summary.get(
            "shadow_submit_count"
        ),
        "bounded_probe_shadow_placement_skip_count": summary.get(
            "shadow_skip_count"
        ),
        "bounded_probe_shadow_placement_candidate_matched_order_count": (
            summary.get("candidate_matched_order_count")
        ),
        "bounded_probe_shadow_placement_candidate_matched_submit_count": (
            summary.get("candidate_matched_submit_count")
        ),
        "bounded_probe_shadow_placement_future_bbo_cross_count": summary.get(
            "future_bbo_would_cross_shadow_limit_count"
        ),
        "bounded_probe_shadow_placement_max_original_best_touch_gap_bps": (
            summary.get("max_original_best_touch_gap_bps")
        ),
        "bounded_probe_shadow_placement_max_initial_touch_gap_bps": (
            summary.get("max_shadow_initial_touch_gap_bps")
        ),
        "bounded_probe_shadow_placement_avg_initial_touch_gap_bps": (
            summary.get("avg_shadow_initial_touch_gap_bps")
        ),
        "bounded_probe_shadow_placement_max_gap_reduction_bps": summary.get(
            "max_gap_reduction_bps"
        ),
        "bounded_probe_shadow_placement_improves_touchability": (
            answers.get("shadow_placement_improves_touchability") is True
        ),
        "bounded_probe_shadow_placement_candidate_matched_runtime_sample_present": (
            answers.get("candidate_matched_runtime_sample_present") is True
        ),
        "bounded_probe_shadow_placement_candidate_specific_alpha_proof": (
            answers.get("candidate_specific_alpha_proof") is True
        ),
        "bounded_probe_shadow_placement_order_authority_granted": (
            answers.get("order_authority_granted") is True
        ),
        "bounded_probe_shadow_placement_probe_authority_granted": (
            answers.get("probe_authority_granted") is True
        ),
        "bounded_probe_shadow_placement_main_cost_gate_adjustment": answers.get(
            "main_cost_gate_adjustment"
        ),
        "bounded_probe_shadow_placement_promotion_evidence": (
            answers.get("promotion_evidence") is True
        ),
    }


def _first_text(items: Any, fallback: str) -> str:
    for item in _list(items):
        text = _str(item)
        if text:
            return text
    return fallback


def _sealed_probe_preflight_fields(
    preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(preflight)
    if not payload:
        return {
            "sealed_probe_preflight_present": False,
            "sealed_probe_preflight_status": None,
            "sealed_probe_preflight_blocking_gates": [],
            "sealed_probe_preflight_blocking_gate_count": 0,
            "sealed_probe_preflight_ready_for_operator_authorization": False,
            "sealed_probe_preflight_bounded_demo_probe_design_status": None,
        }
    answers = _dict(payload.get("answers"))
    design = _dict(payload.get("bounded_demo_probe_design"))
    limits = _dict(design.get("suggested_initial_probe_limits"))
    success = _dict(design.get("success_criteria"))
    return {
        "sealed_probe_preflight_present": True,
        "sealed_probe_preflight_schema_version": payload.get("schema_version"),
        "sealed_probe_preflight_status": payload.get("status"),
        "sealed_probe_preflight_reason": payload.get("reason"),
        "sealed_probe_preflight_generated_at_utc": payload.get("generated_at_utc"),
        "sealed_probe_preflight_next_actions": _list(payload.get("next_actions")),
        "sealed_probe_preflight_blocking_gates": _list(payload.get("blocking_gates")),
        "sealed_probe_preflight_blocking_gate_count": _int(
            payload.get("blocking_gate_count")
        ),
        "sealed_probe_preflight_evidence_ready": answers.get(
            "sealed_horizon_evidence_ready"
        ),
        "sealed_probe_preflight_decision_packet_aligned": answers.get(
            "decision_packet_aligned"
        ),
        "sealed_probe_preflight_operator_review_recorded": answers.get(
            "operator_review_recorded"
        ),
        "sealed_probe_preflight_production_lane_accumulating": answers.get(
            "production_learning_lane_accumulating"
        ),
        "sealed_probe_preflight_ready_for_operator_authorization": answers.get(
            "ready_for_operator_bounded_demo_probe_authorization"
        )
        is True,
        "sealed_probe_preflight_probe_authority_granted": (
            answers.get("probe_authority_granted") is True
        ),
        "sealed_probe_preflight_order_authority_granted": (
            answers.get("order_authority_granted") is True
        ),
        "sealed_probe_preflight_main_cost_gate_adjustment": (
            answers.get("main_cost_gate_adjustment")
        ),
        "sealed_probe_preflight_promotion_evidence": (
            answers.get("promotion_evidence") is True
        ),
        "sealed_probe_preflight_bounded_demo_probe_design_status": (
            design.get("status")
        ),
        "sealed_probe_preflight_bounded_demo_probe_max_probe_intents_before_review": (
            limits.get("max_probe_intents_before_review")
        ),
        "sealed_probe_preflight_bounded_demo_probe_max_demo_notional_usdt_per_order": (
            limits.get("max_demo_notional_usdt_per_order")
        ),
        "sealed_probe_preflight_bounded_demo_probe_max_total_demo_notional_usdt_before_review": (
            limits.get("max_total_demo_notional_usdt_before_review")
        ),
        "sealed_probe_preflight_bounded_demo_probe_min_realized_avg_net_bps": (
            success.get("min_realized_avg_net_bps")
        ),
        "sealed_probe_preflight_bounded_demo_probe_promotion_evidence": (
            success.get("promotion_evidence") is True
        ),
    }


def _sealed_preflight_path_state(
    preflight: dict[str, Any] | None,
) -> tuple[str, str, str]:
    payload = _dict(preflight)
    status = _str(payload.get("status"))
    next_actions = payload.get("next_actions")
    if status == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION":
        return (
            "SEALED_HORIZON_PREFLIGHT_READY_FOR_OPERATOR_AUTHORIZATION",
            "separate_operator_authorization_for_minimal_rust_authority_bounded_demo_probe",
            _first_text(
                next_actions,
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately",
            ),
        )
    if status == "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED":
        return (
            "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE",
            "operator_review_recorded_and_production_learning_lane_accumulates",
            _first_text(
                next_actions,
                "operator_review_sealed_horizon_preflight_and_activate_production_learning_lane",
            ),
        )
    if status == "OPERATOR_REVIEW_REQUIRED":
        return (
            "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW",
            "operator_review_recorded_without_granting_order_or_probe_authority",
            _first_text(next_actions, "operator_review_sealed_horizon_probe_preflight"),
        )
    if status == "PRODUCTION_LEARNING_LANE_NOT_READY":
        return (
            "SEALED_HORIZON_PREFLIGHT_PRODUCTION_LANE_NOT_READY",
            "production_learning_lane_accumulates_ledger_and_outcome_rows",
            _first_text(next_actions, "activate_or_repair_cost_gate_learning_lane_stack_before_runtime_probe"),
        )
    if status == "AUTHORITY_BOUNDARY_VIOLATION":
        return (
            "SEALED_HORIZON_PREFLIGHT_AUTHORITY_BOUNDARY_VIOLATION",
            "remove_authority_granting_input_before_any_review",
            _first_text(next_actions, "remove_authority_granting_input_before_any_review"),
        )
    return (
        "SEALED_HORIZON_PREFLIGHT_NOT_ALIGNED",
        "refresh_preflight_until_sealed_evidence_decision_packet_and_runtime_lane_align",
        _first_text(next_actions, "refresh_sealed_horizon_probe_preflight"),
    )


def _bounded_probe_result_path_state(
    review: dict[str, Any] | None,
    execution_realism_review: dict[str, Any] | None = None,
) -> tuple[str, str, str] | None:
    payload = _dict(review)
    status = _str(payload.get("status"))
    quality = _dict(payload.get("evidence_quality"))
    quality_status = _str(quality.get("status"))
    next_actions = payload.get("next_actions")
    execution_payload = _dict(execution_realism_review)
    execution_status = _str(execution_payload.get("status"))
    execution_next_actions = _list(execution_payload.get("next_actions"))
    quality_next_action = "record_matched_blocked_signal_outcomes_for_same_side_cell_and_horizon"
    completed = _int(_dict(payload.get("probe_result_summary")).get(
        "completed_probe_outcome_count"
    ))
    if status == "AUTHORITY_BOUNDARY_VIOLATION":
        return (
            "SEALED_HORIZON_PREFLIGHT_AUTHORITY_BOUNDARY_VIOLATION",
            "remove_authority_granting_probe_result_input_before_any_review",
            _first_text(next_actions, "remove_authority_granting_input_before_any_review"),
        )
    if status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED":
        return (
            "BOUNDED_DEMO_PROBE_RESULT_FAILED_STOP",
            "keep_cost_gate_blocked_after_realized_probe_edge_failed",
            _first_text(next_actions, "stop_probe_and_keep_cost_gate_blocked_for_this_side_cell"),
        )
    if status in {
        "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
    } and quality_status in {
        "",
        "CONTROL_COMPARISON_MISSING",
        "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
    }:
        return (
            "BOUNDED_DEMO_PROBE_CONTROL_COMPARISON_REQUIRED",
            "record_matched_blocked_signal_control_outcomes_before_operator_gate_review",
            _first_text(next_actions, quality_next_action),
        )
    if status in {
        "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
    } and quality_status == "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP":
        if not execution_payload:
            return (
                "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_REQUIRED",
                "generate_bounded_probe_execution_realism_review_before_cost_gate_or_operator_review",
                "refresh_bounded_probe_execution_realism_review",
            )
        if execution_status == "AUTHORITY_BOUNDARY_VIOLATION":
            return (
                "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_AUTHORITY_BOUNDARY_VIOLATION",
                "remove_authority_granting_execution_review_input_before_any_review",
                _first_text(
                    execution_next_actions,
                    "remove_authority_granting_input_before_any_review",
                ),
            )
        if execution_status == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED":
            return (
                "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REPAIR_REQUIRED",
                "repair_or_replay_bounded_probe_execution_realism_gap_before_cost_gate_review",
                _first_text(
                    execution_next_actions,
                    "record_fill_backed_probe_execution_rows_or_l1_replay_before_cost_gate_review",
                ),
            )
        if execution_status in {
            "EXECUTION_REALISM_PROBE_SAMPLE_BELOW_REVIEW_FLOOR",
            "EXECUTION_REALISM_CONTROL_SAMPLE_BELOW_REVIEW_FLOOR",
        }:
            return (
                "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_SAMPLE_REQUIRED",
                "record_probe_and_matched_control_rows_before_execution_realism_review",
                _first_text(
                    execution_next_actions,
                    "continue_recording_probe_and_matched_control_outcomes_before_execution_realism_review",
                ),
            )
        if execution_status == "NO_EXECUTION_REALISM_GAP_TO_REVIEW":
            return (
                "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_NOT_ALIGNED",
                "refresh_execution_realism_review_until_it_matches_result_review",
                _first_text(
                    execution_next_actions,
                    "refresh_bounded_probe_execution_realism_review",
                ),
            )
        return (
            "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_GAP",
            "investigate_probe_execution_realism_before_cost_gate_or_operator_review",
            _first_text(
                next_actions,
                "investigate_probe_execution_realism_slippage_and_timing_before_cost_gate_review",
            ),
        )
    if status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED":
        return (
            "BOUNDED_DEMO_PROBE_LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
            "operator_review_probe_learning_results_before_any_promotion_or_gate_change",
            _first_text(next_actions, "operator_review_probe_learning_results_before_any_promotion_or_gate_change"),
        )
    if status == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED":
        return (
            "BOUNDED_DEMO_PROBE_FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            "operator_review_first_probe_results_before_any_additional_probe_budget",
            _first_text(next_actions, "operator_review_first_probe_results_before_any_additional_probe_budget"),
        )
    if status == "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW":
        return (
            "BOUNDED_DEMO_PROBE_COLLECT_MORE_OUTCOMES",
            "record_completed_probe_outcomes_until_first_review_floor",
            _first_text(next_actions, "continue_recording_probe_outcomes_with_existing_authority_boundaries"),
        )
    if completed > 0 and status == "PREFLIGHT_DESIGN_NOT_USABLE":
        return (
            "SEALED_HORIZON_PREFLIGHT_NOT_ALIGNED",
            "refresh_or_operator_review_bounded_probe_design_before_result_review",
            _first_text(next_actions, "refresh_or_operator_review_bounded_probe_design_before_result_review"),
        )
    return None


def _bounded_probe_shadow_placement_path_state(
    impact: dict[str, Any] | None,
) -> tuple[str, str, str] | None:
    payload = _dict(impact)
    status = _str(payload.get("status"))
    next_actions = payload.get("next_actions")
    if not status:
        return None
    if status == "AUTHORITY_BOUNDARY_VIOLATION":
        return (
            "BOUNDED_DEMO_PROBE_PLACEMENT_AUTHORITY_BOUNDARY_VIOLATION",
            "remove_authority_granting_shadow_placement_input_before_any_review",
            _first_text(next_actions, "remove_authority_granting_input_before_review"),
        )
    if status in {
        "PLACEMENT_REPAIR_PLAN_REQUIRED",
        "ORDER_TOUCHABILITY_AUDIT_REQUIRED",
        "PLACEMENT_REPAIR_PLAN_NOT_READY",
        "ORDER_TOUCHABILITY_SAMPLE_REQUIRED",
    }:
        return (
            "BOUNDED_DEMO_PROBE_PLACEMENT_SAMPLE_REQUIRED",
            "fresh_placement_repair_plan_and_order_touchability_sample_required",
            _first_text(next_actions, "refresh_bounded_probe_shadow_placement_impact"),
        )
    if status == "SHADOW_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS":
        return (
            "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS",
            "inspect_bbo_spread_or_passive_gap_before_rust_patch",
            _first_text(
                next_actions,
                "inspect_bbo_spread_or_max_initial_gap_before_rust_patch",
            ),
        )
    if status == "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH":
        return (
            "BOUNDED_DEMO_PROBE_PLACEMENT_TOUCHABILITY_REPAIR_SAMPLE_MISMATCH",
            "operator_reviews_mechanical_touchability_then_collect_candidate_matched_flow",
            _first_text(
                next_actions,
                "operator_review_mechanical_touchability_before_rust_patch",
            ),
        )
    if status == "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE":
        return (
            "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_READY_FOR_OPERATOR_REVIEW",
            "operator_reviews_existing_rust_authority_path_near_touch_patch",
            _first_text(
                next_actions,
                "operator_review_existing_rust_authority_path_patch",
            ),
        )
    if status == "SHADOW_PLACEMENT_PARTIAL_SKIP_REQUIRED":
        return (
            "BOUNDED_DEMO_PROBE_PLACEMENT_PARTIAL_SKIP_REVIEW_REQUIRED",
            "review_shadow_skips_before_rust_authority_path_patch",
            _first_text(next_actions, "review_shadow_skips_before_rust_patch"),
        )
    return None


def _base_path(
    *,
    path_id: str,
    path_class: str,
    status: str,
    why: str,
    current_edge_bps: Any,
    cost_threshold_bps: Any,
    sample_count: Any,
    required_next_gate: str,
    next_action: str,
    horizon_status: str | None = None,
    candidate_key: str | None = None,
    candidate_horizons: list[Any] | None = None,
    best_horizon_minutes: Any = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "path_id": path_id,
        "class": path_class,
        "status": status,
        "candidate_key": candidate_key,
        "why_it_can_cross_cost_gate": why,
        "current_edge_bps": _round(current_edge_bps),
        "cost_threshold_bps": _round(cost_threshold_bps),
        "net_cushion_bps": _round(current_edge_bps),
        "sample_count": _int(sample_count),
        "horizon_status": horizon_status,
        "candidate_horizons_minutes": candidate_horizons or [],
        "best_horizon_minutes": _int(best_horizon_minutes) if best_horizon_minutes else None,
        "required_next_gate": required_next_gate,
        "next_action": next_action,
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "authority_boundary": (
            "operator review required; no order/probe authority and no main Cost Gate lowering"
        ),
        "evidence": evidence or {},
    }


def _cost_gate_candidate_paths(
    *,
    counterfactual: dict[str, Any] | None,
    profit_packet: dict[str, Any] | None,
    activation_preflight: dict[str, Any] | None,
    horizon_sealed_replay: dict[str, Any] | None,
    horizon_learning_evidence: dict[str, Any] | None,
    sealed_horizon_probe_preflight: dict[str, Any] | None,
    bounded_probe_shadow_placement_impact: dict[str, Any] | None,
    bounded_probe_result_review: dict[str, Any] | None,
    bounded_probe_execution_realism_review: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not counterfactual:
        return []
    friction_bps = _float(counterfactual.get("friction_bps")) or 4.0
    required_gate, next_action = _cost_gate_required_next_gate(
        profit_packet=profit_packet,
        activation_preflight=activation_preflight,
    )
    packet_status = _profit_packet_status(profit_packet)
    if packet_status == "DATA_FLOW_MONITOR_REQUIRED":
        status = "COST_GATE_CANDIDATE_READY_FOR_DATA_FLOW_PROOF"
    else:
        status = "COST_GATE_CANDIDATE_EXECUTION_EVIDENCE_MISSING"
    horizon_by_key = _horizon_cells_by_key(counterfactual)
    sealed_by_key = _sealed_replay_by_key(horizon_sealed_replay)
    learning_evidence_by_key = _sealed_learning_evidence_by_key(
        horizon_learning_evidence
    )
    sealed_probe_preflight_by_key = _sealed_probe_preflight_by_key(
        sealed_horizon_probe_preflight
    )
    bounded_probe_shadow_placement_impact_by_key = (
        _bounded_probe_shadow_placement_impact_by_key(
            bounded_probe_shadow_placement_impact
        )
    )
    bounded_probe_result_review_by_key = _bounded_probe_result_review_by_key(
        bounded_probe_result_review
    )
    bounded_probe_execution_realism_review_by_key = (
        _bounded_probe_execution_realism_review_by_key(
            bounded_probe_execution_realism_review
        )
    )
    paths: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _list(_profit_ranking(counterfactual).get("top_side_cells")):
        if not isinstance(row, dict):
            continue
        if row.get("learning_lane_action") != "LEARNING_PROBE_CANDIDATE":
            continue
        key = _str(row.get("side_cell_key"))
        if not key:
            continue
        horizon = horizon_by_key.get(key, {})
        seen.add(key)
        paths.append(_base_path(
            path_id=f"cost_gate_learning_lane:{key}",
            path_class="bounded_demo_learning_probe",
            status=status,
            candidate_key=key,
            why=(
                "Rejected signal side-cell has positive after-friction kline markout; "
                "it may cross the Cost Gate only after data-flow, ledger/outcome, and "
                "demo execution-realism proof."
            ),
            current_edge_bps=row.get("avg_net_bps"),
            cost_threshold_bps=friction_bps,
            sample_count=(
                row.get("sample_count_for_gate")
                or row.get("distinct_ts")
                or row.get("n")
            ),
            horizon_status=_str(horizon.get("status")) or None,
            candidate_horizons=_list(horizon.get("candidate_horizons")),
            best_horizon_minutes=horizon.get("best_horizon_minutes"),
            required_next_gate=required_gate,
            next_action=row.get("next_action") or next_action,
            evidence={
                "priority_score": row.get("priority_score"),
                "priority_tier": row.get("priority_tier"),
                "net_positive_pct": row.get("net_positive_pct"),
                "p50_gross_bps": row.get("p50_gross_bps"),
                "raw_rows": row.get("n"),
                "distinct_ts": row.get("distinct_ts"),
                "rows_per_distinct_ts": row.get("rows_per_distinct_ts"),
                "learning_lane_reason": row.get("learning_lane_reason"),
                "profit_packet_status": packet_status,
                "activation_status": _activation_status(profit_packet, activation_preflight),
            },
        ))

    for key, horizon in horizon_by_key.items():
        candidate_horizons = _list(horizon.get("candidate_horizons"))
        if not candidate_horizons:
            continue
        if key in seen and horizon.get("status") != "MIXED_HORIZON_RESPONSE":
            continue
        if horizon.get("status") not in {"MIXED_HORIZON_RESPONSE", "CANDIDATE_MULTI_HORIZON_STABLE"}:
            continue
        sealed = sealed_by_key.get(key)
        learning_evidence = learning_evidence_by_key.get(key)
        sealed_probe_preflight = sealed_probe_preflight_by_key.get(key)
        bounded_probe_shadow_placement_impact = (
            bounded_probe_shadow_placement_impact_by_key.get(key)
        )
        bounded_probe_result_review = bounded_probe_result_review_by_key.get(key)
        bounded_probe_execution_realism_review = (
            bounded_probe_execution_realism_review_by_key.get(key)
        )
        sealed_passed = (
            _str(_dict(sealed).get("status"))
            == "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW"
            and _dict(_dict(sealed).get("answers")).get("sealed_replay_passed") is True
        )
        learning_ready = _sealed_learning_review_ready(learning_evidence)
        result_path_state = _bounded_probe_result_path_state(
            bounded_probe_result_review,
            execution_realism_review=bounded_probe_execution_realism_review,
        )
        shadow_placement_path_state = _bounded_probe_shadow_placement_path_state(
            bounded_probe_shadow_placement_impact
        )
        if result_path_state:
            path_status, required_next_gate, path_next_action = result_path_state
        elif shadow_placement_path_state:
            path_status, required_next_gate, path_next_action = (
                shadow_placement_path_state
            )
        elif learning_ready and sealed_probe_preflight:
            path_status, required_next_gate, path_next_action = (
                _sealed_preflight_path_state(sealed_probe_preflight)
            )
        elif learning_ready:
            path_status = "SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW"
            required_next_gate = (
                "operator_reviews_bounded_demo_probe_for_sealed_horizon_candidate"
            )
            path_next_action = (
                "operator_review_sealed_horizon_learning_evidence_before_any_bounded_demo_probe"
            )
        elif sealed_passed:
            path_status = "SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION"
            required_next_gate = (
                "learning_stack_accumulates_ledger_and_outcome_rows_for_sealed_horizon_candidate"
            )
            path_next_action = (
                "activate_or_repair_cost_gate_learning_lane_then_record_blocked_signal_outcomes"
            )
        else:
            path_status = "HORIZON_EDGE_AMPLIFICATION_CANDIDATE"
            required_next_gate = "sealed_replay_or_bounded_demo_probe_for_selected_horizon"
            path_next_action = "build_horizon_specific_candidate_packet_then_operator_review"
        sealed_evidence = _sealed_replay_evidence(sealed)
        learning_fields = _sealed_learning_evidence_fields(learning_evidence)
        sealed_preflight_fields = _sealed_probe_preflight_fields(sealed_probe_preflight)
        shadow_placement_fields = _bounded_probe_shadow_placement_impact_fields(
            bounded_probe_shadow_placement_impact
        )
        bounded_probe_result_fields = _bounded_probe_result_review_fields(
            bounded_probe_result_review
        )
        bounded_probe_execution_realism_fields = (
            _bounded_probe_execution_realism_review_fields(
                bounded_probe_execution_realism_review
            )
        )
        paths.append(_base_path(
            path_id=f"horizon_edge_amplification:{key}",
            path_class="horizon_retiming_or_side_cell_filter",
            status=path_status,
            candidate_key=key,
            why=(
                "The same side-cell changes sign across holding horizons; retiming, "
                "regime filtering, or side-cell specialization can amplify edge instead "
                "of globally lowering the Cost Gate. A sealed replay pass moves this "
                "path from replay-selection proof to learning/outcome accumulation."
            ),
            current_edge_bps=horizon.get("best_avg_net_bps"),
            cost_threshold_bps=friction_bps,
            sample_count=(
                horizon.get("best_sample_count_for_gate")
                or horizon.get("best_distinct_ts")
            ),
            horizon_status=_str(horizon.get("status")) or None,
            candidate_horizons=candidate_horizons,
            best_horizon_minutes=horizon.get("best_horizon_minutes"),
            required_next_gate=required_next_gate,
            next_action=path_next_action,
            evidence={
                "block_confirmed_horizons": horizon.get("block_confirmed_horizons"),
                "observed_horizons": horizon.get("observed_horizons"),
                "best_net_positive_pct": horizon.get("best_net_positive_pct"),
                "best_p50_gross_bps": horizon.get("best_p50_gross_bps"),
                "reason": horizon.get("reason"),
                "horizon_rows": horizon.get("horizon_rows"),
                "sealed_replay_present": bool(sealed),
                "sealed_replay_passed": sealed_passed,
                "sealed_learning_evidence_present": bool(learning_evidence),
                "sealed_learning_operator_review_ready": learning_ready,
                **sealed_evidence,
                **learning_fields,
                **sealed_preflight_fields,
                **shadow_placement_fields,
                **bounded_probe_result_fields,
                **bounded_probe_execution_realism_fields,
            },
        ))
    return paths


def _mm_signal_path(
    fillsim: dict[str, Any] | None,
    fillsim_history: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not fillsim:
        return []
    low_friction = _dict(fillsim.get("low_friction_signal_scorecard"))
    train_confirmed = _dict(low_friction.get("train_confirmed_gross_scorecard"))
    best = _dict(
        train_confirmed.get("best_train_confirmed_gross_candidate")
        or low_friction.get("best_train_confirmed_gross_candidate")
    )
    current_fee = (
        train_confirmed.get("current_fee_round_trip_bps")
        or low_friction.get("current_fee_round_trip_bps")
        or _dict(fillsim.get("maker_fee_sensitivity_scorecard")).get("current_fee_round_trip_bps")
        or 4.0
    )
    current_edge = (
        best.get("min_train_holdout_gross_bps")
        or best.get("holdout_edge_before_fees_bps")
        or best.get("edge_before_fees_bps")
    )
    if not best:
        return [_base_path(
            path_id="mm_low_friction_signal_search",
            path_class="low_friction_mm_alpha_search",
            status="WAIT_FOR_ARTIFACT",
            why=(
                "MM can cross the cost wall only with a train-confirmed low-friction "
                "gross edge; the current artifact has no usable candidate summary."
            ),
            current_edge_bps=None,
            cost_threshold_bps=current_fee,
            sample_count=0,
            required_next_gate="low_friction_train_confirmed_gross_scorecard_present",
            next_action="refresh_fill_sim_and_mm_verdict_artifacts",
        )]
    history = _dict(fillsim_history)
    return [_base_path(
        path_id="mm_low_friction_signal_search",
        path_class="low_friction_mm_alpha_search",
        status="LOW_FRICTION_MM_GROSS_EDGE_BELOW_CURRENT_FEE",
        candidate_key=_str(best.get("name") or best.get("condition")),
        why=(
            "This path becomes profitable by increasing gross edge in low-friction "
            "maker conditions until train and holdout both clear the current round-trip fee."
        ),
        current_edge_bps=current_edge,
        cost_threshold_bps=current_fee,
        sample_count=min(
            _int(best.get("train_n_fill_only") or best.get("n_fill_only")),
            _int(best.get("holdout_n_fill_only") or best.get("n_fill_only")),
        ),
        required_next_gate="train_confirmed_gross_edge_ge_current_fee_round_trip_and_history_stability",
        next_action="search_regime_or_microstructure_filters_that_raise_train_confirmed_gross_edge",
        evidence={
            "scorecard_status": train_confirmed.get("status") or low_friction.get("status"),
            "gap_to_current_fee_round_trip_bps": _round(
                best.get("gap_to_current_fee_round_trip_bps")
            ),
            "train_edge_before_fees_bps": best.get("train_edge_before_fees_bps"),
            "holdout_edge_before_fees_bps": best.get("holdout_edge_before_fees_bps"),
            "history_status": history.get("status"),
            "history_reason": history.get("reason"),
            "history_valid_windows": history.get("valid_windows"),
            "history_distinct_window_dates": history.get("distinct_window_dates"),
        },
    )]


def _fee_or_scale_path(
    fillsim: dict[str, Any] | None,
    fillsim_history: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    history = _dict(fillsim_history)
    stability = _dict(history.get("lower_fee_break_even_stability"))
    maker_fee = _dict(fillsim or {}).get("maker_fee_sensitivity_scorecard")
    sensitivity = _dict(maker_fee)
    best = _dict(
        stability.get("best_repeated_lower_fee_break_even_key")
        or stability.get("best_lower_fee_break_even_window")
        or history.get("best_sample_gated_break_even_window")
        or sensitivity.get("best_sample_gated_break_even_cell")
    )
    cell = _dict(best.get("best_cell") or best.get("cell") or best)
    if not history and not sensitivity:
        return []
    return [_base_path(
        path_id="fee_rebate_scale_path",
        path_class="fee_or_scale",
        status="FEE_OR_SCALE_PATH_NOT_SHORT_TERM_ALPHA",
        candidate_key=_str(best.get("key") or cell.get("key") or cell.get("name")),
        why=(
            "Lower fee/rebate can turn some low-gross cells positive, but this is a "
            "capital, volume, or Bybit business-development path; it is not alpha proof."
        ),
        current_edge_bps=cell.get("edge_before_fees_bps"),
        cost_threshold_bps=(
            2.0 * (_float(stability.get("current_maker_fee_bps_per_side")) or 2.0)
        ),
        sample_count=cell.get("n_fill_only") or best.get("windows"),
        required_next_gate="capital_or_fee_tier_commitment_plus_repeated_distinct_date_edge",
        next_action="keep_as_business_path_while_engineering_searches_stronger_alpha",
        evidence={
            "lower_fee_break_even_stability_status": stability.get("status"),
            "lower_fee_break_even_reason": stability.get("reason"),
            "history_status": history.get("status"),
            "distinct_window_dates": stability.get("distinct_window_dates")
            or history.get("distinct_window_dates"),
            "break_even_maker_fee_bps_per_side": (
                cell.get("break_even_maker_fee_bps_per_side")
                or best.get("break_even_maker_fee_bps_per_side")
            ),
            "fee_reduction_to_breakeven_bps_per_side": cell.get(
                "fee_reduction_to_breakeven_bps_per_side"
            ),
        },
    )]


def _polymarket_path(polymarket: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not polymarket:
        return []
    verdict = _dict(polymarket.get("verdict"))
    replay = _dict(polymarket.get("candidate_replay_scorecard"))
    selected = _dict(replay.get("selected_summary"))
    return [_base_path(
        path_id="polymarket_leadlag_alpha_path",
        path_class="external_event_leadlag_alpha",
        status="POLYMARKET_ALPHA_GROSS_BELOW_COST_OR_EXECUTION_UNMEASURED",
        candidate_key=_str(
            replay.get("selected_candidate_key")
            or selected.get("candidate_key")
            or verdict.get("best_candidate_key")
        ),
        why=(
            "Polymarket lead-lag can become an alpha source only if IC candidates "
            "survive explicit replay, cost, dated history, PBO, and execution realism."
        ),
        current_edge_bps=selected.get("gross_bps_mean") or selected.get("net_bps_mean"),
        cost_threshold_bps=replay.get("round_trip_cost_bps") or selected.get("round_trip_cost_bps") or 4.0,
        sample_count=selected.get("sample_count") or _dict(polymarket.get("counts")).get("max_overlap_adjusted_ic_points"),
        horizon_status=verdict.get("status"),
        candidate_horizons=[selected.get("horizon_minutes")] if selected.get("horizon_minutes") else [],
        best_horizon_minutes=selected.get("horizon_minutes"),
        required_next_gate="dated_replay_history_pbo_breadth_and_execution_realism",
        next_action="accumulate_more_dated_replay_samples_and_build_execution_realism",
        evidence={
            "verdict_status": verdict.get("status"),
            "candidate_replay_status": replay.get("status"),
            "candidate_count": verdict.get("candidate_count") or replay.get("candidate_count"),
            "net_bps_mean": selected.get("net_bps_mean"),
            "holdout_net_bps_mean": selected.get("holdout_net_bps_mean"),
            "execution_realism_status": selected.get("execution_realism_status"),
            "n_days": selected.get("n_days"),
            "k_trials": selected.get("k_trials"),
        },
    )]


def _gate_b_path(gate_b_watch: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not gate_b_watch:
        return []
    counts = _dict(gate_b_watch.get("candidate_counts"))
    actionable = _int(counts.get("alertable")) + _int(counts.get("start_now")) + _int(counts.get("schedule"))
    status = "EVENT_WAIT_NO_ACTIONABLE_WINDOW" if actionable == 0 else "GATE_B_ACTIONABLE_WINDOW_REVIEW"
    return [_base_path(
        path_id="gate_b_listing_fade_event_path",
        path_class="event_driven_listing_fade",
        status=status,
        why=(
            "Listing-fade can be profitable only when a fresh Gate-B event window appears; "
            "watch-only stale windows are not alpha evidence."
        ),
        current_edge_bps=None,
        cost_threshold_bps=4.0,
        sample_count=actionable,
        required_next_gate="fresh_actionable_gate_b_window_then_isolated_24h_capture",
        next_action="wait_for_gate_b_watch_actionable_start_now_or_schedule",
        evidence={
            "watch_status": gate_b_watch.get("status") or gate_b_watch.get("artifact_status"),
            "candidate_counts": counts,
            "alerts_sent": gate_b_watch.get("alerts_sent"),
            "source_health": gate_b_watch.get("source_health"),
        },
    )]


def _proof_gate_labels(blocking_gates: list[Any]) -> list[str]:
    labels = {
        "operator_sealed_horizon_review_recorded": (
            "operator records sealed-horizon review without granting order/probe authority"
        ),
        "production_learning_lane_accumulating": (
            "production learning lane accumulates ledger and blocked-outcome rows"
        ),
        "sealed_horizon_learning_evidence_ready": (
            "sealed horizon blocked-outcome evidence is fresh and review-ready"
        ),
        "profit_learning_decision_packet_aligned": (
            "profit-learning packet routes the same side-cell and horizon"
        ),
        "authority_boundary_preserved": (
            "inputs preserve no Cost Gate lowering, no order authority, no promotion proof"
        ),
    }
    out: list[str] = []
    for gate in blocking_gates:
        key = _str(gate)
        if not key:
            continue
        out.append(labels.get(key, key))
    return out


def _path_class_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in candidates:
        cls = _str(row.get("class")) or "unknown"
        counts[cls] = counts.get(cls, 0) + 1
    return counts


def _lever_status(candidates: list[dict[str, Any]], path_class: str) -> dict[str, Any]:
    rows = [row for row in candidates if row.get("class") == path_class]
    if not rows:
        return {"path_class": path_class, "status": "NO_CURRENT_ARTIFACT", "path_count": 0}
    top = rows[0]
    return {
        "path_class": path_class,
        "status": top.get("status"),
        "path_count": len(rows),
        "top_path_id": top.get("path_id"),
        "top_candidate_key": top.get("candidate_key"),
        "top_edge_bps": top.get("current_edge_bps"),
        "top_sample_count": top.get("sample_count"),
        "required_next_gate": top.get("required_next_gate"),
        "next_action": top.get("next_action"),
    }


def _profitability_engineering_closure(
    *,
    candidates: list[dict[str, Any]],
    sealed_horizon_probe_preflight: dict[str, Any] | None,
    bounded_probe_shadow_placement_impact: dict[str, Any] | None,
    bounded_probe_result_review: dict[str, Any] | None,
    bounded_probe_execution_realism_review: dict[str, Any] | None,
) -> dict[str, Any]:
    top = candidates[0] if candidates else {}
    preflight = _dict(sealed_horizon_probe_preflight)
    preflight_status = _str(preflight.get("status"))
    preflight_answers = _dict(preflight.get("answers"))
    blocking_gates = _list(preflight.get("blocking_gates"))
    shadow_placement = _dict(bounded_probe_shadow_placement_impact)
    shadow_status = _str(shadow_placement.get("status"))
    shadow_summary = _dict(shadow_placement.get("shadow_summary"))
    shadow_answers = _dict(shadow_placement.get("answers"))
    shadow_next_actions = _list(shadow_placement.get("next_actions"))
    result_review = _dict(bounded_probe_result_review)
    result_status = _str(result_review.get("status"))
    result_summary = _dict(result_review.get("probe_result_summary"))
    result_answers = _dict(result_review.get("answers"))
    result_quality = _dict(result_review.get("evidence_quality"))
    result_quality_status = _str(result_quality.get("status"))
    result_next_actions = _list(result_review.get("next_actions"))
    completed_probe_outcomes = _int(
        result_summary.get("completed_probe_outcome_count")
    )
    execution_review = _dict(bounded_probe_execution_realism_review)
    execution_status = _str(execution_review.get("status"))
    execution_next_actions = _list(execution_review.get("next_actions"))
    execution_probe = _dict(execution_review.get("probe_execution_summary"))
    execution_gap = _dict(execution_review.get("gap_decomposition"))
    execution_answers = _dict(execution_review.get("answers"))
    execution_hypotheses = _list(execution_review.get("execution_gap_hypotheses"))
    execution_primary_hypothesis = (
        execution_hypotheses[0]
        if execution_hypotheses and isinstance(execution_hypotheses[0], dict)
        else {}
    )
    result_under_capture = (
        result_status
        in {
            "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
            "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        }
        and result_quality_status == "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
    )

    if not candidates:
        status = "NO_PROFITABILITY_PATH_TO_CLOSE"
    elif result_status == "AUTHORITY_BOUNDARY_VIOLATION":
        status = "AUTHORITY_BOUNDARY_VIOLATION_REPAIR_FIRST"
    elif result_status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED":
        status = "COST_GATE_ESCAPE_RESULT_REVIEW_FAILED_REALIZED_EDGE"
    elif result_status in {
        "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
        "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
    } and result_quality_status in {
        "",
        "CONTROL_COMPARISON_MISSING",
        "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
    }:
        status = "BOUNDED_DEMO_PROBE_CONTROL_COMPARISON_REQUIRED"
    elif result_under_capture and not execution_review:
        status = "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_REQUIRED"
    elif (
        result_under_capture
        and execution_status == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
    ):
        status = "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REPAIR_REQUIRED"
    elif result_under_capture and execution_status in {
        "EXECUTION_REALISM_PROBE_SAMPLE_BELOW_REVIEW_FLOOR",
        "EXECUTION_REALISM_CONTROL_SAMPLE_BELOW_REVIEW_FLOOR",
    }:
        status = "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_SAMPLE_REQUIRED"
    elif result_under_capture and execution_status == "NO_EXECUTION_REALISM_GAP_TO_REVIEW":
        status = "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_NOT_ALIGNED"
    elif result_under_capture:
        status = "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_GAP"
    elif result_status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED":
        status = "BOUNDED_DEMO_PROBE_LEARNING_REVIEW_OPERATOR_REQUIRED"
    elif result_status == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED":
        status = "BOUNDED_DEMO_PROBE_FIRST_REVIEW_OPERATOR_REQUIRED"
    elif result_status == "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW":
        status = "BOUNDED_DEMO_PROBE_ACCUMULATING_OUTCOMES_BEFORE_REVIEW"
    elif shadow_status == "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH":
        status = "BOUNDED_DEMO_PROBE_PLACEMENT_TOUCHABILITY_SAMPLE_MISMATCH"
    elif shadow_status == "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE":
        status = "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_OPERATOR_REVIEW_REQUIRED"
    elif shadow_status == "SHADOW_PLACEMENT_PARTIAL_SKIP_REQUIRED":
        status = "BOUNDED_DEMO_PROBE_PLACEMENT_PARTIAL_SKIP_REVIEW_REQUIRED"
    elif shadow_status == "SHADOW_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS":
        status = "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS"
    elif preflight_status == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION":
        status = "OPERATOR_CAN_REVIEW_BOUNDED_DEMO_PROBE_AUTHORIZATION"
    elif preflight_status == "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED":
        status = "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_AND_PRODUCTION_LEARNING_LANE"
    elif preflight_status == "OPERATOR_REVIEW_REQUIRED":
        status = "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW"
    elif preflight_status == "PRODUCTION_LEARNING_LANE_NOT_READY":
        status = "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_PRODUCTION_LEARNING_LANE"
    elif preflight_status == "AUTHORITY_BOUNDARY_VIOLATION":
        status = "AUTHORITY_BOUNDARY_VIOLATION_REPAIR_FIRST"
    elif top:
        status = "PROFITABILITY_PATHS_REQUIRE_NEXT_PROOF_GATE"
    else:
        status = "NO_PROFITABILITY_PATH_TO_CLOSE"

    preflight_next_actions = _list(preflight.get("next_actions"))
    remaining = _proof_gate_labels(blocking_gates)
    if result_status == "AUTHORITY_BOUNDARY_VIOLATION":
        remaining = ["remove authority-granting result-review input before continuing"]
    elif result_status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED":
        remaining = ["realized bounded demo probe edge failed; keep Cost Gate blocked"]
    elif result_status in {
        "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
        "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
    } and result_quality_status in {
        "",
        "CONTROL_COMPARISON_MISSING",
        "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
    }:
        remaining = [
            "record matched blocked-signal control outcomes before treating positive probe results as Cost Gate evidence"
        ]
    elif result_under_capture and not execution_review:
        remaining = [
            "generate bounded demo probe execution-realism review before Cost Gate or operator review"
        ]
    elif (
        result_under_capture
        and execution_status == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
    ):
        remaining = [
            "repair bounded demo probe execution-realism gap or record fill-backed/L1 evidence before Cost Gate review"
        ]
    elif result_under_capture and execution_status in {
        "EXECUTION_REALISM_PROBE_SAMPLE_BELOW_REVIEW_FLOOR",
        "EXECUTION_REALISM_CONTROL_SAMPLE_BELOW_REVIEW_FLOOR",
    }:
        remaining = [
            "record enough probe and matched-control rows for execution-realism review"
        ]
    elif result_under_capture and execution_status == "NO_EXECUTION_REALISM_GAP_TO_REVIEW":
        remaining = [
            "refresh execution-realism review until it aligns with bounded result review"
        ]
    elif result_under_capture:
        remaining = [
            "investigate bounded demo probe execution realism gap before treating matched-control edge as capturable"
        ]
    elif result_status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED":
        remaining = ["operator reviews bounded probe learning results before any gate or promotion change"]
    elif result_status == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED":
        remaining = ["operator reviews first bounded probe results before additional probe budget"]
    elif result_status == "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW":
        remaining = ["complete first-review bounded probe outcome floor"]
    elif shadow_status == "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH":
        remaining = [
            "operator reviews mechanical near-touch improvement before any Rust authority-path patch",
            "collect candidate-matched order-to-fill and fill-fee-slippage lineage after separate authorization",
        ]
    elif shadow_status == "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE":
        remaining = [
            "operator reviews existing Rust authority-path near-touch patch before bounded Demo probe",
            "record candidate-matched fill-backed execution evidence before any Cost Gate change",
        ]
    elif shadow_status == "SHADOW_PLACEMENT_PARTIAL_SKIP_REQUIRED":
        remaining = ["review shadow skipped orders before any Rust authority-path patch"]
    elif shadow_status == "SHADOW_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS":
        remaining = ["repair spread or max-passive-gap assumptions before Rust patch"]
    if not remaining and top and status == "PROFITABILITY_PATHS_REQUIRE_NEXT_PROOF_GATE":
        remaining = [_str(top.get("required_next_gate"))]
    next_actions = [
        action for action in [
            *[str(item) for item in execution_next_actions],
            (
                "refresh_bounded_probe_execution_realism_review"
                if result_under_capture and not execution_review
                else ""
            ),
            *[str(item) for item in result_next_actions],
            *[str(item) for item in shadow_next_actions],
            *[str(item) for item in preflight_next_actions],
            _str(top.get("next_action")),
            "continue_low_friction_mm_and_external_alpha_search",
        ]
        if action
    ]

    return {
        "schema_version": "profitability_engineering_closure_v1",
        "status": status,
        "profit_thesis": (
            "Do not lower the global Cost Gate. Cross it with side-cell and horizon "
            "specialization, bounded demo learning, execution-realism proof, and "
            "parallel alpha search for stronger low-friction or event-driven signals."
        ),
        "leading_path_id": top.get("path_id"),
        "leading_path_status": top.get("status"),
        "leading_path_class": top.get("class"),
        "leading_candidate_key": top.get("candidate_key"),
        "proof_gates_remaining": remaining,
        "proof_gate_count_remaining": len(remaining),
        "next_actions": list(dict.fromkeys(next_actions)),
        "cost_gate_escape_strategy": {
            "method": "bounded_side_cell_horizon_probe_after_preflight",
            "global_cost_gate_lowering": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "sealed_horizon_probe_preflight_status": preflight_status or None,
            "sealed_horizon_probe_preflight_ready": (
                preflight_answers.get(
                    "ready_for_operator_bounded_demo_probe_authorization"
                )
                is True
            ),
            "sealed_horizon_probe_preflight_blocking_gates": blocking_gates,
            "bounded_probe_result_review_status": result_status or None,
            "bounded_probe_result_review_completed_probe_outcomes": (
                completed_probe_outcomes
            ),
            "bounded_probe_result_review_operator_review_required": (
                result_answers.get("operator_review_required") is True
            ),
            "bounded_probe_result_review_stop_recommended": (
                result_answers.get("stop_probe_recommended") is True
            ),
            "bounded_probe_result_review_learning_review_candidate": (
                result_answers.get("learning_review_candidate") is True
            ),
            "bounded_probe_result_review_evidence_quality_status": (
                result_quality_status or None
            ),
            "bounded_probe_result_review_matched_control_outcomes": (
                result_quality.get("matched_control_outcome_count")
            ),
            "bounded_probe_result_review_probe_minus_control_avg_net_bps": (
                result_quality.get("probe_minus_control_avg_net_bps")
            ),
            "bounded_probe_result_review_probe_edge_capture_ratio": (
                result_quality.get("probe_edge_capture_ratio")
            ),
            "bounded_probe_result_review_probe_execution_gap_bps": (
                result_quality.get("probe_execution_gap_bps")
            ),
            "bounded_probe_result_review_execution_realism_gap": (
                result_quality.get("execution_realism_gap") is True
            ),
            "bounded_probe_result_review_anecdote_risk": (
                result_quality.get("anecdote_risk") is True
            ),
            "bounded_probe_shadow_placement_status": shadow_status or None,
            "bounded_probe_shadow_placement_sample_scope": shadow_summary.get(
                "sample_scope"
            ),
            "bounded_probe_shadow_placement_submit_count": shadow_summary.get(
                "shadow_submit_count"
            ),
            "bounded_probe_shadow_placement_candidate_matched_order_count": (
                shadow_summary.get("candidate_matched_order_count")
            ),
            "bounded_probe_shadow_placement_max_initial_touch_gap_bps": (
                shadow_summary.get("max_shadow_initial_touch_gap_bps")
            ),
            "bounded_probe_shadow_placement_max_gap_reduction_bps": (
                shadow_summary.get("max_gap_reduction_bps")
            ),
            "bounded_probe_shadow_placement_improves_touchability": (
                shadow_answers.get("shadow_placement_improves_touchability") is True
            ),
            "bounded_probe_shadow_placement_candidate_specific_alpha_proof": (
                shadow_answers.get("candidate_specific_alpha_proof") is True
            ),
            "bounded_probe_execution_realism_review_status": (
                execution_status or None
            ),
            "bounded_probe_execution_realism_review_primary_hypothesis": (
                execution_primary_hypothesis.get("kind")
            ),
            "bounded_probe_execution_realism_review_net_capture_gap_bps": (
                execution_gap.get("net_capture_gap_bps")
            ),
            "bounded_probe_execution_realism_review_gross_capture_gap_bps": (
                execution_gap.get("gross_capture_gap_bps")
            ),
            "bounded_probe_execution_realism_review_cost_or_slippage_gap_bps": (
                execution_gap.get("cost_or_slippage_gap_bps")
            ),
            "bounded_probe_execution_realism_review_entry_delay_gap_ms": (
                execution_gap.get("entry_delay_gap_ms")
            ),
            "bounded_probe_execution_realism_review_probe_fill_backed_pct": (
                execution_probe.get("fill_backed_pct")
            ),
            "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed": (
                execution_answers.get("cost_gate_or_operator_review_allowed") is True
            ),
        },
        "edge_amplification_levers": [
            _lever_status(candidates, "horizon_retiming_or_side_cell_filter"),
            _lever_status(candidates, "bounded_demo_learning_probe"),
            _lever_status(candidates, "low_friction_mm_alpha_search"),
            _lever_status(candidates, "external_event_leadlag_alpha"),
            _lever_status(candidates, "event_driven_listing_fade"),
            _lever_status(candidates, "fee_or_scale"),
        ],
        "autonomous_learning_requirements": [
            "demo/live_demo rejects are recorded and not silently dropped",
            "production learning lane writes admission ledger rows",
            "outcome refresh records blocked-signal markouts at the intended horizon",
            "operator review separates evidence approval from order/probe authority",
            "Rust authority remains the only path for any future bounded demo probe",
        ],
        "path_class_counts": _path_class_counts(candidates),
        "boundary": BOUNDARY,
    }


def build_profitability_path_scorecard(
    *,
    cost_gate_counterfactual: dict[str, Any] | None = None,
    profit_learning_packet: dict[str, Any] | None = None,
    learning_plan: dict[str, Any] | None = None,
    activation_preflight: dict[str, Any] | None = None,
    horizon_sealed_replay: dict[str, Any] | None = None,
    horizon_learning_evidence: dict[str, Any] | None = None,
    sealed_horizon_probe_preflight: dict[str, Any] | None = None,
    bounded_probe_shadow_placement_impact: dict[str, Any] | None = None,
    bounded_probe_result_review: dict[str, Any] | None = None,
    bounded_probe_execution_realism_review: dict[str, Any] | None = None,
    fillsim: dict[str, Any] | None = None,
    fillsim_history: dict[str, Any] | None = None,
    polymarket_leadlag: dict[str, Any] | None = None,
    gate_b_watch: dict[str, Any] | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    input_paths = paths or {}
    candidates: list[dict[str, Any]] = []
    candidates.extend(_cost_gate_candidate_paths(
        counterfactual=cost_gate_counterfactual,
        profit_packet=profit_learning_packet,
        activation_preflight=activation_preflight,
        horizon_sealed_replay=horizon_sealed_replay,
        horizon_learning_evidence=horizon_learning_evidence,
        sealed_horizon_probe_preflight=sealed_horizon_probe_preflight,
        bounded_probe_shadow_placement_impact=bounded_probe_shadow_placement_impact,
        bounded_probe_result_review=bounded_probe_result_review,
        bounded_probe_execution_realism_review=bounded_probe_execution_realism_review,
    ))
    candidates.extend(_mm_signal_path(fillsim, fillsim_history))
    candidates.extend(_fee_or_scale_path(fillsim, fillsim_history))
    candidates.extend(_polymarket_path(polymarket_leadlag))
    candidates.extend(_gate_b_path(gate_b_watch))
    candidates.sort(key=_score_priority)
    for idx, row in enumerate(candidates, start=1):
        row["priority_rank"] = idx

    cost_gate_paths = [p for p in candidates if p["class"] in {
        "bounded_demo_learning_probe",
        "horizon_retiming_or_side_cell_filter",
    }]
    readyish = [p for p in candidates if _str(p.get("status")) in {
        "COST_GATE_CANDIDATE_READY_FOR_DATA_FLOW_PROOF",
        "COST_GATE_CANDIDATE_EXECUTION_EVIDENCE_MISSING",
        "HORIZON_EDGE_AMPLIFICATION_CANDIDATE",
        "SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION",
        "SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW",
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_REQUIRED",
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REPAIR_REQUIRED",
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_SAMPLE_REQUIRED",
        "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_GAP",
        "BOUNDED_DEMO_PROBE_CONTROL_COMPARISON_REQUIRED",
        "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_READY_FOR_OPERATOR_REVIEW",
        "BOUNDED_DEMO_PROBE_PLACEMENT_TOUCHABILITY_REPAIR_SAMPLE_MISMATCH",
        "BOUNDED_DEMO_PROBE_PLACEMENT_PARTIAL_SKIP_REVIEW_REQUIRED",
        "BOUNDED_DEMO_PROBE_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS",
        "BOUNDED_DEMO_PROBE_PLACEMENT_SAMPLE_REQUIRED",
    }]
    if not candidates:
        status = "NO_PROFITABILITY_PATH_ARTIFACTS"
    elif readyish:
        status = "PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING"
    else:
        status = "PROFITABILITY_PATHS_REQUIRE_ALPHA_OR_COST_IMPROVEMENT"

    packet_answers = _dict(_dict(profit_learning_packet).get("answers"))
    closure = _profitability_engineering_closure(
        candidates=candidates,
        sealed_horizon_probe_preflight=sealed_horizon_probe_preflight,
        bounded_probe_result_review=bounded_probe_result_review,
        bounded_probe_execution_realism_review=(
            bounded_probe_execution_realism_review
        ),
        bounded_probe_shadow_placement_impact=bounded_probe_shadow_placement_impact,
    )
    return {
        "schema_version": PROFITABILITY_PATH_SCORECARD_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "summary": {
            "path_count": len(candidates),
            "cost_gate_crossing_candidate_count": len(cost_gate_paths),
            "top_path_id": candidates[0]["path_id"] if candidates else None,
            "top_path_status": candidates[0]["status"] if candidates else None,
            "top_path_next_action": candidates[0]["next_action"] if candidates else None,
        },
        "answers": {
            "profitability_proven": False,
            "cost_gate_crossing_candidates_present": bool(cost_gate_paths),
            "alpha_or_edge_amplification_paths_present": any(
                p["class"] in {
                    "bounded_demo_learning_probe",
                    "horizon_retiming_or_side_cell_filter",
                    "low_friction_mm_alpha_search",
                    "external_event_leadlag_alpha",
                    "event_driven_listing_fade",
                }
                for p in candidates
            ),
            "autonomous_learning_loop_accumulating": (
                _activation_status(profit_learning_packet, activation_preflight)
                == "EVIDENCE_STACK_ACTIVE"
            ),
            "bounded_demo_probe_preflight_present": bool(
                _dict(sealed_horizon_probe_preflight)
            ),
            "bounded_demo_probe_preflight_ready": (
                _dict(_dict(sealed_horizon_probe_preflight).get("answers")).get(
                    "ready_for_operator_bounded_demo_probe_authorization"
                )
                is True
            ),
            "bounded_demo_probe_result_review_present": bool(
                _dict(bounded_probe_result_review)
            ),
            "bounded_demo_probe_shadow_placement_impact_present": bool(
                _dict(bounded_probe_shadow_placement_impact)
            ),
            "bounded_demo_probe_shadow_placement_improves_touchability": (
                _dict(
                    _dict(bounded_probe_shadow_placement_impact).get("answers")
                ).get("shadow_placement_improves_touchability")
                is True
            ),
            "bounded_demo_probe_shadow_placement_candidate_specific_alpha_proof": (
                _dict(
                    _dict(bounded_probe_shadow_placement_impact).get("answers")
                ).get("candidate_specific_alpha_proof")
                is True
            ),
            "bounded_demo_probe_result_review_operator_review_required": (
                _dict(_dict(bounded_probe_result_review).get("answers")).get(
                    "operator_review_required"
                )
                is True
            ),
            "bounded_demo_probe_result_review_stop_recommended": (
                _dict(_dict(bounded_probe_result_review).get("answers")).get(
                    "stop_probe_recommended"
                )
                is True
            ),
            "bounded_demo_probe_result_learning_review_candidate": (
                _dict(_dict(bounded_probe_result_review).get("answers")).get(
                    "learning_review_candidate"
                )
                is True
            ),
            "bounded_demo_probe_execution_realism_review_present": bool(
                _dict(bounded_probe_execution_realism_review)
            ),
            "bounded_demo_probe_execution_realism_repair_required": (
                _str(_dict(bounded_probe_execution_realism_review).get("status"))
                == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
            ),
            "silent_drop_risk": packet_answers.get("silent_drop_risk") is True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "top_paths": candidates,
        "profitability_engineering_closure": closure,
        "artifacts": {
            "cost_gate_counterfactual": _artifact_summary(
                "cost_gate_counterfactual",
                input_paths.get("cost_gate_counterfactual"),
                cost_gate_counterfactual,
            ),
            "profit_learning_packet": _artifact_summary(
                "profit_learning_packet",
                input_paths.get("profit_learning_packet"),
                profit_learning_packet,
            ),
            "learning_plan": _artifact_summary(
                "learning_plan",
                input_paths.get("learning_plan"),
                learning_plan,
            ),
            "activation_preflight": _artifact_summary(
                "activation_preflight",
                input_paths.get("activation_preflight"),
                activation_preflight,
            ),
            "horizon_sealed_replay": _artifact_summary(
                "horizon_sealed_replay",
                input_paths.get("horizon_sealed_replay"),
                horizon_sealed_replay,
            ),
            "horizon_learning_evidence": _artifact_summary(
                "horizon_learning_evidence",
                input_paths.get("horizon_learning_evidence"),
                horizon_learning_evidence,
            ),
            "sealed_horizon_probe_preflight": _artifact_summary(
                "sealed_horizon_probe_preflight",
                input_paths.get("sealed_horizon_probe_preflight"),
                sealed_horizon_probe_preflight,
            ),
            "bounded_probe_result_review": _artifact_summary(
                "bounded_probe_result_review",
                input_paths.get("bounded_probe_result_review"),
                bounded_probe_result_review,
            ),
            "bounded_probe_shadow_placement_impact": _artifact_summary(
                "bounded_probe_shadow_placement_impact",
                input_paths.get("bounded_probe_shadow_placement_impact"),
                bounded_probe_shadow_placement_impact,
            ),
            "bounded_probe_execution_realism_review": _artifact_summary(
                "bounded_probe_execution_realism_review",
                input_paths.get("bounded_probe_execution_realism_review"),
                bounded_probe_execution_realism_review,
            ),
            "fillsim": _artifact_summary("fillsim", input_paths.get("fillsim"), fillsim),
            "fillsim_history": _artifact_summary(
                "fillsim_history",
                input_paths.get("fillsim_history"),
                fillsim_history,
            ),
            "polymarket_leadlag": _artifact_summary(
                "polymarket_leadlag",
                input_paths.get("polymarket_leadlag"),
                polymarket_leadlag,
            ),
            "gate_b_watch": _artifact_summary(
                "gate_b_watch",
                input_paths.get("gate_b_watch"),
                gate_b_watch,
            ),
        },
        "global_boundaries": {
            "order_authority": "NOT_GRANTED",
            "probe_authority": "NOT_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "runtime_mutation": "NONE",
            "promotion_evidence": False,
            "boundary": BOUNDARY,
        },
        "operator_read": {
            "do_not_lower_global_cost_gate": True,
            "recommended_engineering_sequence": closure["next_actions"],
        },
    }


def render_markdown(scorecard: dict[str, Any]) -> str:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", "\\|")

    lines = [
        "# Profitability Path Scorecard",
        "",
        f"- Generated: `{scorecard.get('generated_at_utc')}`",
        f"- Status: `{scorecard.get('status')}`",
        "- Boundary: artifact-only; no order authority, no probe authority, no Cost Gate lowering.",
        "",
        "## Answers",
        "",
        "| answer | value |",
        "|---|---|",
    ]
    for key, value in _dict(scorecard.get("answers")).items():
        lines.append(f"| {key} | `{value}` |")

    lines.extend([
        "",
        "## Ranked Paths",
        "",
        "| rank | path | class | status | edge_bps | cost_bps | sample_n | next gate |",
        "|---:|---|---|---|---:|---:|---:|---|",
    ])
    for row in _list(scorecard.get("top_paths")):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('priority_rank')} | {md_cell(row.get('path_id'))} | "
            f"{md_cell(row.get('class'))} | {md_cell(row.get('status'))} | "
            f"{row.get('current_edge_bps')} | "
            f"{row.get('cost_threshold_bps')} | {row.get('sample_count')} | "
            f"{md_cell(row.get('required_next_gate'))} |"
        )

    closure = _dict(scorecard.get("profitability_engineering_closure"))
    if closure:
        lines.extend([
            "",
            "## Engineering Closure",
            "",
            f"- Status: `{closure.get('status')}`",
            f"- Leading path: `{closure.get('leading_path_id')}`",
            f"- Remaining proof gates: `{closure.get('proof_gate_count_remaining')}`",
            "",
        ])
        for gate in _list(closure.get("proof_gates_remaining")):
            lines.append(f"- `{gate}`")

    lines.extend(["", "## Next Actions", ""])
    for action in _list(_dict(scorecard.get("operator_read")).get("recommended_engineering_sequence")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
    parser.add_argument("--cost-gate-counterfactual-json", type=Path)
    parser.add_argument("--profit-learning-packet-json", type=Path)
    parser.add_argument("--learning-plan-json", type=Path)
    parser.add_argument("--activation-preflight-json", type=Path)
    parser.add_argument("--horizon-sealed-replay-json", type=Path)
    parser.add_argument("--horizon-learning-evidence-json", type=Path)
    parser.add_argument("--sealed-horizon-probe-preflight-json", type=Path)
    parser.add_argument("--bounded-probe-shadow-placement-impact-json", type=Path)
    parser.add_argument("--bounded-probe-result-review-json", type=Path)
    parser.add_argument("--bounded-probe-execution-realism-review-json", type=Path)
    parser.add_argument("--fillsim-json", type=Path)
    parser.add_argument("--fillsim-history-json", type=Path)
    parser.add_argument("--polymarket-leadlag-json", type=Path)
    parser.add_argument("--gate-b-watch-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    paths = {
        "cost_gate_counterfactual": args.cost_gate_counterfactual_json,
        "profit_learning_packet": args.profit_learning_packet_json,
        "learning_plan": args.learning_plan_json,
        "activation_preflight": args.activation_preflight_json,
        "horizon_sealed_replay": args.horizon_sealed_replay_json,
        "horizon_learning_evidence": args.horizon_learning_evidence_json,
        "sealed_horizon_probe_preflight": args.sealed_horizon_probe_preflight_json,
        "bounded_probe_shadow_placement_impact": (
            args.bounded_probe_shadow_placement_impact_json
        ),
        "bounded_probe_result_review": args.bounded_probe_result_review_json,
        "bounded_probe_execution_realism_review": (
            args.bounded_probe_execution_realism_review_json
        ),
        "fillsim": args.fillsim_json,
        "fillsim_history": args.fillsim_history_json,
        "polymarket_leadlag": args.polymarket_leadlag_json,
        "gate_b_watch": args.gate_b_watch_json,
    }
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_read_json(args.cost_gate_counterfactual_json),
        profit_learning_packet=_read_json(args.profit_learning_packet_json),
        learning_plan=_read_json(args.learning_plan_json),
        activation_preflight=_read_json(args.activation_preflight_json),
        horizon_sealed_replay=_read_json(args.horizon_sealed_replay_json),
        horizon_learning_evidence=_read_json(args.horizon_learning_evidence_json),
        sealed_horizon_probe_preflight=_read_json(
            args.sealed_horizon_probe_preflight_json
        ),
        bounded_probe_shadow_placement_impact=_read_json(
            args.bounded_probe_shadow_placement_impact_json
        ),
        bounded_probe_result_review=_read_json(args.bounded_probe_result_review_json),
        bounded_probe_execution_realism_review=_read_json(
            args.bounded_probe_execution_realism_review_json
        ),
        fillsim=_read_json(args.fillsim_json),
        fillsim_history=_read_json(args.fillsim_history_json),
        polymarket_leadlag=_read_json(args.polymarket_leadlag_json),
        gate_b_watch=_read_json(args.gate_b_watch_json),
        paths=paths,
    )
    if args.output:
        _write_text(args.output, render_markdown(scorecard))
    if args.json_output:
        _write_json(args.json_output, scorecard)
    if args.print_json:
        print(json.dumps(scorecard, ensure_ascii=False, sort_keys=True, default=str))
    if not (args.output or args.json_output or args.print_json):
        print(render_markdown(scorecard), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
