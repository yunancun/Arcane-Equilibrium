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
        "COST_GATE_CANDIDATE_READY_FOR_DATA_FLOW_PROOF": 10,
        "SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION": 11,
        "COST_GATE_CANDIDATE_EXECUTION_EVIDENCE_MISSING": 12,
        "HORIZON_EDGE_AMPLIFICATION_CANDIDATE": 20,
        "LOW_FRICTION_MM_GROSS_EDGE_BELOW_CURRENT_FEE": 40,
        "POLYMARKET_ALPHA_GROSS_BELOW_COST_OR_EXECUTION_UNMEASURED": 50,
        "FEE_OR_SCALE_PATH_NOT_SHORT_TERM_ALPHA": 70,
        "GATE_B_ACTIONABLE_WINDOW_REVIEW": 30,
        "EVENT_WAIT_NO_ACTIONABLE_WINDOW": 80,
        "WAIT_FOR_ARTIFACT": 90,
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
        sealed_passed = (
            _str(_dict(sealed).get("status"))
            == "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW"
            and _dict(_dict(sealed).get("answers")).get("sealed_replay_passed") is True
        )
        path_status = (
            "SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION"
            if sealed_passed
            else "HORIZON_EDGE_AMPLIFICATION_CANDIDATE"
        )
        required_next_gate = (
            "learning_stack_accumulates_ledger_and_outcome_rows_for_sealed_horizon_candidate"
            if sealed_passed
            else "sealed_replay_or_bounded_demo_probe_for_selected_horizon"
        )
        path_next_action = (
            "activate_or_repair_cost_gate_learning_lane_then_record_blocked_signal_outcomes"
            if sealed_passed
            else "build_horizon_specific_candidate_packet_then_operator_review"
        )
        sealed_evidence = _sealed_replay_evidence(sealed)
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
                **sealed_evidence,
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


def build_profitability_path_scorecard(
    *,
    cost_gate_counterfactual: dict[str, Any] | None = None,
    profit_learning_packet: dict[str, Any] | None = None,
    learning_plan: dict[str, Any] | None = None,
    activation_preflight: dict[str, Any] | None = None,
    horizon_sealed_replay: dict[str, Any] | None = None,
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
    }]
    if not candidates:
        status = "NO_PROFITABILITY_PATH_ARTIFACTS"
    elif readyish:
        status = "PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING"
    else:
        status = "PROFITABILITY_PATHS_REQUIRE_ALPHA_OR_COST_IMPROVEMENT"

    packet_answers = _dict(_dict(profit_learning_packet).get("answers"))
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
            "silent_drop_risk": packet_answers.get("silent_drop_risk") is True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "top_paths": candidates,
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
            "recommended_engineering_sequence": [
                "fix_or_run_demo_data_flow_monitor",
                "run_horizon_specific_replay_for_mixed_horizon_side_cells",
                "activate_or_repair_cost_gate_learning_lane_accumulation",
                "operator_review_bounded_demo_probe_for_ranked_side_cells",
                "continue_low_friction_mm_and_external_alpha_search",
            ],
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
