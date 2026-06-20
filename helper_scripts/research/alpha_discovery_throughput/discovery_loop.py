"""Read-only multi-arm discovery loop planner."""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import DISCOVERY_LOOP_SCHEMA_VERSION, RUNNER_VERSION

READY_FOR_AEG_CHAIN = "READY_FOR_AEG_CHAIN"
READY_FOR_PROBE = "READY_FOR_PROBE"
RUN_READ_ONLY_CAPTURE = "RUN_READ_ONLY_CAPTURE"
WAIT = "WAIT"
BLOCK = "BLOCK"

_PRIORITY = {
    READY_FOR_AEG_CHAIN: 0,
    READY_FOR_PROBE: 1,
    RUN_READ_ONLY_CAPTURE: 2,
    WAIT: 3,
    BLOCK: 4,
}

_BLOCKER_PRIORITY = {
    "candidate_review_ready": 0,
    "probe_ready": 1,
    "feature_family_no_edge": 2,
    "cost_wall": 3,
    "fee_or_scale": 4,
    "sample_gate": 5,
    "data_coverage": 6,
    "event_wait": 7,
    "robustness_wait": 8,
    "rejected_no_edge": 9,
    "source_health": 10,
    "unknown_wait": 11,
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def decide_arm_action(arm: dict[str, Any], *, min_samples: int = 30) -> dict[str, Any]:
    """單 discovery arm 的 deterministic action。"""
    name = str(arm.get("arm_id") or arm.get("name") or "unknown")
    gate_status = str(arm.get("gate_status") or arm.get("status") or "").upper()
    sample_count = _int(arm.get("sample_count"))
    artifacts_ready = bool(arm.get("artifacts_ready"))
    source_ok = arm.get("source_ok", True) is not False
    reason = "default_wait"
    action = WAIT

    if not source_ok or gate_status in {"SOURCE_FAILURE", "ERROR", "FAILED"}:
        action, reason = BLOCK, "source_not_healthy"
    elif gate_status in {"KILL", "KILLED", "REJECTED", "NO_EDGE_SURVIVES", "NO_EDGE"}:
        action, reason = BLOCK, f"gate_status:{gate_status.lower()}"
    elif gate_status in {"WATCH_ONLY", "NO_CANDIDATE", "WAIT"}:
        action, reason = WAIT, f"gate_status:{gate_status.lower()}"
    elif artifacts_ready and sample_count >= min_samples:
        action, reason = READY_FOR_AEG_CHAIN, "artifacts_ready_and_sample_gate_met"
    elif gate_status in {"ACTIONABLE_START_NOW", "ACTIONABLE_SCHEDULE", "OPERATOR_REVIEW"}:
        action, reason = READY_FOR_PROBE, f"gate_status:{gate_status.lower()}"
    elif sample_count < min_samples:
        action, reason = RUN_READ_ONLY_CAPTURE, "sample_count_below_gate"

    return {
        "arm_id": name,
        "action": action,
        "reason": reason,
        "sample_count": sample_count,
        "min_samples": min_samples,
        "artifacts_ready": artifacts_ready,
        "gate_status": gate_status or "UNSPECIFIED",
        "rank": _PRIORITY[action],
    }


def _base_blocker_row(arm: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "arm_id": decision.get("arm_id"),
        "action": decision.get("action"),
        "reason": decision.get("reason"),
        "gate_status": decision.get("gate_status"),
        "sample_count": decision.get("sample_count"),
        "min_samples": decision.get("min_samples"),
        "artifacts_ready": decision.get("artifacts_ready"),
        "source_ok": arm.get("source_ok", True) is not False,
        "source_error": arm.get("source_error"),
        "promotion_ready": False,
        "operator_actionable": False,
        "engineering_actionable": False,
        "secondary_blockers": [],
    }


def _finish_blocker_row(
    row: dict[str, Any],
    *,
    blocker_class: str,
    primary_blocker: str,
    next_trigger: str,
    promotion_ready: bool = False,
    operator_actionable: bool = False,
    engineering_actionable: bool = False,
    secondary_blockers: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row.update({
        "blocker_class": blocker_class,
        "primary_blocker": primary_blocker,
        "next_trigger": next_trigger,
        "promotion_ready": promotion_ready,
        "operator_actionable": operator_actionable,
        "engineering_actionable": engineering_actionable,
        "blocker_rank": _BLOCKER_PRIORITY.get(blocker_class, 99),
    })
    if secondary_blockers:
        row["secondary_blockers"] = secondary_blockers
    if extra:
        row.update(extra)
    return row


def _candidate_artifact_dependency_summary(
    arms: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    decisions_by_id = {str(row.get("arm_id")): row for row in decisions}
    ready: list[dict[str, Any]] = []
    for arm in arms:
        arm_id = str(arm.get("arm_id") or arm.get("name") or "unknown")
        if arm_id == "aeg_robustness_matrix":
            continue
        decision = decisions_by_id.get(arm_id, {})
        action = str(decision.get("action") or "")
        gate_status = str(arm.get("gate_status") or arm.get("status") or "")
        artifacts_ready = bool(arm.get("artifacts_ready"))
        if action not in {READY_FOR_AEG_CHAIN, READY_FOR_PROBE} and not artifacts_ready:
            continue
        ready.append({
            "arm_id": arm_id,
            "action": action,
            "gate_status": gate_status,
            "sample_count": decision.get("sample_count"),
            "artifacts_ready": artifacts_ready,
        })
    if ready:
        status = "CANDIDATE_ARTIFACTS_AVAILABLE_FOR_ROBUSTNESS"
        reason = "upstream_ready_or_probe_artifacts_available"
        next_trigger = "feed_candidate_artifacts_into_robustness_matrix"
        engineering_actionable = True
    else:
        status = "NO_CANDIDATE_ARTIFACTS_AVAILABLE_FOR_ROBUSTNESS"
        reason = "no_upstream_ready_or_probe_artifacts"
        next_trigger = "wait_for_candidate_or_probe_artifact_before_robustness_matrix"
        engineering_actionable = False
    return {
        "schema_version": "aeg_candidate_artifact_dependency_v1",
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "engineering_actionable": engineering_actionable,
        "candidate_artifact_count": len(ready),
        "candidate_artifacts": ready[:8],
    }


def _mm_lower_fee_history_extra(detail: dict[str, Any]) -> dict[str, Any]:
    history = _dict(detail.get("history_scorecard"))
    stability = _dict(history.get("lower_fee_break_even_stability"))
    return {
        "history_scorecard_status": history.get("status"),
        "history_scorecard_reason": history.get("reason"),
        "lower_fee_break_even_stability_status": stability.get("status"),
        "lower_fee_break_even_stability_reason": stability.get("reason"),
        "lower_fee_break_even_windows": (
            stability.get("lower_fee_break_even_windows")
            if "lower_fee_break_even_windows" in stability
            else history.get("lower_fee_break_even_windows")
        ),
        "lower_fee_break_even_distinct_window_dates": (
            stability.get("distinct_window_dates")
            or history.get("lower_fee_break_even_distinct_window_dates")
        ),
        "repeated_lower_fee_break_even_key_count": stability.get(
            "repeated_key_count"
        ),
        "best_lower_fee_break_even_window": (
            stability.get("best_lower_fee_break_even_window")
            or history.get("best_lower_fee_break_even_window")
        ),
        "best_repeated_lower_fee_break_even_key": stability.get(
            "best_repeated_lower_fee_break_even_key"
        ),
    }


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _mm_cost_wall_escape_scorecard(detail: dict[str, Any]) -> dict[str, Any]:
    gross_decomp = _dict(detail.get("gross_edge_cost_decomposition"))
    sample_cost_wall = _dict(detail.get("sample_gated_cost_wall_summary"))
    fee_path = _dict(detail.get("fee_path_feasibility"))
    business_actionability = _dict(fee_path.get("business_path_actionability"))
    history_extra = _mm_lower_fee_history_extra(detail)

    best_gross_edge = _float(gross_decomp.get("best_sample_gated_gross_edge_bps"))
    best_net = _float(gross_decomp.get("best_gross_cell_net_bps"))
    current_fee_round_trip = (
        _float(gross_decomp.get("current_fee_round_trip_bps"))
        if gross_decomp.get("current_fee_round_trip_bps") is not None
        else _float(sample_cost_wall.get("current_fee_round_trip_bps"))
    )
    if current_fee_round_trip is None and best_gross_edge is not None and best_net is not None:
        current_fee_round_trip = best_gross_edge - best_net
    gap = (
        current_fee_round_trip - best_gross_edge
        if current_fee_round_trip is not None and best_gross_edge is not None
        else None
    )
    multiple = (
        current_fee_round_trip / best_gross_edge
        if current_fee_round_trip is not None and best_gross_edge not in {None, 0.0}
        else None
    )
    current_fee_positive_count = _int(
        gross_decomp.get("current_fee_positive_sample_gated_cell_count")
    )
    business_status = str(business_actionability.get("status") or "").upper()

    if current_fee_positive_count > 0:
        status = "CURRENT_FEE_SAMPLE_GATED_CELL_AVAILABLE"
        reason = "sample_gated_current_fee_positive_cell_exists"
        next_trigger = "review_current_fee_positive_mm_cell_with_walk_forward_and_aeg_chain"
        engineering_actionable = True
    elif gap is None:
        status = "INSUFFICIENT_COST_WALL_ESCAPE_INPUT"
        reason = "missing_current_fee_or_best_gross_edge"
        next_trigger = "refresh_mm_cost_wall_inputs_before_strategy_judgment"
        engineering_actionable = True
    elif gap > 0 and business_status == "STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED":
        status = "CURRENT_FEE_GROSS_EDGE_GAP_REQUIRES_NEW_LOW_FRICTION_SIGNAL"
        reason = "lower_fee_path_scale_or_capital_gated_at_current_account_state"
        next_trigger = (
            "search_new_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
        )
        engineering_actionable = True
    elif gap > 0:
        status = "CURRENT_FEE_GROSS_EDGE_GAP_OR_LOWER_FEE_REQUIRED"
        reason = "best_sample_gated_gross_edge_below_current_fee_round_trip"
        next_trigger = "validate_lower_fee_access_or_new_low_friction_mm_signal"
        engineering_actionable = True
    else:
        status = "GROSS_EDGE_CLEARS_CURRENT_FEE_NEEDS_WALK_FORWARD_CONFIRMATION"
        reason = "gross_edge_clears_current_fee_but_current_fee_positive_count_absent"
        next_trigger = "run_walk_forward_confirmation_before_any_mm_promotion"
        engineering_actionable = True

    return {
        "schema_version": "mm_cost_wall_escape_v1",
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "engineering_actionable": engineering_actionable,
        "required_current_fee_gross_edge_bps": _round_or_none(current_fee_round_trip),
        "best_sample_gated_gross_edge_bps": _round_or_none(best_gross_edge),
        "gross_edge_gap_to_current_fee_bps": _round_or_none(
            max(0.0, gap) if gap is not None else None
        ),
        "gross_edge_multiple_to_clear_current_fee": _round_or_none(
            multiple if multiple is not None and multiple > 0 else None
        ),
        "best_gross_cell_net_bps": _round_or_none(best_net),
        "fee_reduction_needed_bps_per_side": gross_decomp.get(
            "fee_reduction_needed_bps_per_side"
        ) or sample_cost_wall.get("fee_reduction_needed_bps_per_side"),
        "business_path_actionability_status": business_actionability.get("status"),
        "business_path_operator_action_required": (
            business_actionability.get("operator_action_required")
        ),
        "lower_fee_break_even_stability_status": history_extra.get(
            "lower_fee_break_even_stability_status"
        ),
        "lower_fee_break_even_windows": history_extra.get(
            "lower_fee_break_even_windows"
        ),
        "top_sample_gated_gross_cells": gross_decomp.get(
            "top_sample_gated_gross_cells"
        ),
        "best_sample_gated_gross_cell": gross_decomp.get(
            "best_sample_gated_gross_cell"
        ),
    }


def _mm_secondary_blockers(detail: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    gross_decomp = _dict(detail.get("gross_edge_cost_decomposition"))
    gross_status = str(gross_decomp.get("status") or "").upper()
    if gross_status == "GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL":
        blockers.append({
            "blocker_class": "cost_wall",
            "blocker": "gross_edge_exists_but_current_fee_exceeds_break_even",
            "best_sample_gated_gross_edge_bps": gross_decomp.get(
                "best_sample_gated_gross_edge_bps"
            ),
            "best_gross_cell_net_bps": gross_decomp.get("best_gross_cell_net_bps"),
            "break_even_maker_fee_bps_per_side": gross_decomp.get(
                "break_even_maker_fee_bps_per_side"
            ),
            "fee_reduction_needed_bps_per_side": gross_decomp.get(
                "fee_reduction_needed_bps_per_side"
            ),
            "best_sample_gated_gross_cell": gross_decomp.get(
                "best_sample_gated_gross_cell"
            ),
            "best_walk_forward_holdout_gross_candidate": gross_decomp.get(
                "best_walk_forward_holdout_gross_candidate"
            ),
        })

    sample_cost_wall = _dict(detail.get("sample_gated_cost_wall_summary"))
    sample_shortfall = _float(
        sample_cost_wall.get("best_sample_gated_fee_round_trip_shortfall_bps")
    )
    if sample_shortfall is not None and sample_shortfall > 0:
        blockers.append({
            "blocker_class": "cost_wall",
            "blocker": "current_maker_fee_exceeds_sample_gated_fill_sim_break_even",
            "best_sample_gated_net_bps": sample_cost_wall.get(
                "best_sample_gated_net_bps"
            ),
            "best_sample_gated_fee_round_trip_shortfall_bps": sample_shortfall,
            "break_even_maker_fee_bps_per_side": sample_cost_wall.get(
                "break_even_maker_fee_bps_per_side"
            ),
            "fee_reduction_needed_bps_per_side": sample_cost_wall.get(
                "fee_reduction_needed_bps_per_side"
            ),
        })

    cost_wall = _dict(detail.get("cost_wall_summary"))
    if cost_wall:
        shortfall = _float(cost_wall.get("best_fee_round_trip_shortfall_bps"))
        if shortfall is not None and shortfall > 0:
            blockers.append({
                "blocker_class": "cost_wall",
                "blocker": "live_markout_current_maker_fee_exceeds_best_break_even",
                "best_symbol_by_net_edge": cost_wall.get("best_symbol_by_net_edge"),
                "best_fee_round_trip_shortfall_bps": shortfall,
                "best_n_maker_fills": cost_wall.get("best_n_maker_fills"),
            })

    history_extra = _mm_lower_fee_history_extra(detail)
    history_status = str(
        history_extra.get("lower_fee_break_even_stability_status") or ""
    ).upper()
    if history_status in {
        "LOWER_FEE_BREAK_EVEN_ROTATES_OR_DATE_INSUFFICIENT",
        "LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT",
    }:
        blockers.append({
            "blocker_class": "fee_or_scale",
            "blocker": "lower_fee_break_even_not_stable_across_distinct_windows",
            "lower_fee_break_even_stability_status": history_extra.get(
                "lower_fee_break_even_stability_status"
            ),
            "lower_fee_break_even_stability_reason": history_extra.get(
                "lower_fee_break_even_stability_reason"
            ),
            "lower_fee_break_even_windows": history_extra.get(
                "lower_fee_break_even_windows"
            ),
            "lower_fee_break_even_distinct_window_dates": history_extra.get(
                "lower_fee_break_even_distinct_window_dates"
            ),
            "repeated_lower_fee_break_even_key_count": history_extra.get(
                "repeated_lower_fee_break_even_key_count"
            ),
            "best_lower_fee_break_even_window": history_extra.get(
                "best_lower_fee_break_even_window"
            ),
        })

    fee_path = _dict(detail.get("fee_path_feasibility"))
    business_actionability = _dict(fee_path.get("business_path_actionability"))
    fee_status = str(fee_path.get("status") or "").upper()
    if fee_status == "STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED":
        blockers.append({
            "blocker_class": "fee_or_scale",
            "blocker": "lower_standard_vip_fee_may_clear_but_scale_or_capital_gated",
            "business_path_actionability_status": business_actionability.get("status"),
            "operator_action_required": business_actionability.get(
                "operator_action_required"
            ),
            "break_even_maker_fee_bps_per_side": fee_path.get(
                "break_even_maker_fee_bps_per_side"
            ),
            "fee_reduction_needed_bps_per_side": fee_path.get(
                "fee_reduction_needed_bps_per_side"
            ),
            "first_standard_vip_tier_clearing_break_even": fee_path.get(
                "first_standard_vip_tier_clearing_break_even"
            ),
            "business_path_actionability": business_actionability or None,
        })
    elif fee_status == "NO_STANDARD_VIP_TIER_CLEARS_BREAK_EVEN":
        blockers.append({
            "blocker_class": "fee_or_scale",
            "blocker": "no_standard_vip_fee_tier_clears_break_even",
            "break_even_maker_fee_bps_per_side": fee_path.get(
                "break_even_maker_fee_bps_per_side"
            ),
        })
    return blockers


def classify_profitability_blocker(
    arm: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Classify why an arm is not yet usable as profit evidence."""
    arm_id = str(decision.get("arm_id") or arm.get("arm_id") or "")
    action = str(decision.get("action") or "")
    gate_status = str(decision.get("gate_status") or "").upper()
    detail = _dict(arm.get("detail"))
    row = _base_blocker_row(arm, decision)

    if action == READY_FOR_AEG_CHAIN:
        return _finish_blocker_row(
            row,
            blocker_class="candidate_review_ready",
            primary_blocker="candidate_artifacts_ready_need_aeg_chain",
            next_trigger="run_AEG_MIT_QC_chain_before_any_promotion",
            promotion_ready=True,
            engineering_actionable=True,
        )
    if action == READY_FOR_PROBE:
        return _finish_blocker_row(
            row,
            blocker_class="probe_ready",
            primary_blocker="operator_probe_preflight_ready",
            next_trigger="operator_review_then_isolated_probe_if_authorized",
            operator_actionable=True,
        )
    if row["source_ok"] is False or str(decision.get("reason")) == "source_not_healthy":
        return _finish_blocker_row(
            row,
            blocker_class="source_health",
            primary_blocker=f"source_not_healthy:{arm.get('source_error') or 'unknown'}",
            next_trigger="restore_or_refresh_source_artifact_before_strategy_judgment",
            engineering_actionable=True,
        )

    if arm_id == "mm_verdict_maker_edge":
        failure = _dict(detail.get("walk_forward_failure_summary"))
        failure_status = str(failure.get("status") or "").upper()
        secondary = _mm_secondary_blockers(detail)
        fee_path = _dict(detail.get("fee_path_feasibility"))
        business_actionability = _dict(fee_path.get("business_path_actionability"))
        fee_status = str(fee_path.get("status") or "").upper()
        cost_wall = _dict(detail.get("cost_wall_summary"))
        sample_cost_wall = _dict(detail.get("sample_gated_cost_wall_summary"))
        gross_decomp = _dict(detail.get("gross_edge_cost_decomposition"))
        gross_status = str(gross_decomp.get("status") or "").upper()
        sample_cost_shortfall = _float(
            sample_cost_wall.get("best_sample_gated_fee_round_trip_shortfall_bps")
        )
        cost_shortfall = _float(cost_wall.get("best_fee_round_trip_shortfall_bps"))
        escape_scorecard = _mm_cost_wall_escape_scorecard(detail)

        if failure_status == "NO_TRAIN_POSITIVE_CELL":
            if gross_status == "GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL":
                return _finish_blocker_row(
                    row,
                    blocker_class="cost_wall",
                    primary_blocker=(
                        "gross_edge_below_current_fee_no_current_fee_walk_forward_positive"
                    ),
                    next_trigger=(
                        escape_scorecard.get("next_trigger")
                        or "validate_lower_fee_or_new_low_friction_signal_path_before_expanding_current_family"
                    ),
                    engineering_actionable=bool(
                        escape_scorecard.get("engineering_actionable", True)
                    ),
                    secondary_blockers=secondary,
                    extra={
                        "walk_forward_failure_status": failure_status,
                        "candidate_count": failure.get("candidate_count"),
                        "best_train_candidate": failure.get("best_train_candidate"),
                        "best_holdout_candidate": failure.get("best_holdout_candidate"),
                        "gross_edge_decomposition_status": gross_status,
                        "gross_positive_sample_gated_cell_count": gross_decomp.get(
                            "gross_positive_sample_gated_cell_count"
                        ),
                        "current_fee_positive_sample_gated_cell_count": gross_decomp.get(
                            "current_fee_positive_sample_gated_cell_count"
                        ),
                        "best_sample_gated_gross_edge_bps": gross_decomp.get(
                            "best_sample_gated_gross_edge_bps"
                        ),
                        "best_gross_cell_net_bps": gross_decomp.get(
                            "best_gross_cell_net_bps"
                        ),
                        "break_even_maker_fee_bps_per_side": gross_decomp.get(
                            "break_even_maker_fee_bps_per_side"
                        ),
                        "fee_reduction_needed_bps_per_side": gross_decomp.get(
                            "fee_reduction_needed_bps_per_side"
                        ),
                        "cost_wall_escape_status": escape_scorecard.get("status"),
                        "cost_wall_escape_reason": escape_scorecard.get("reason"),
                        "cost_wall_escape_scorecard": escape_scorecard,
                        "required_current_fee_gross_edge_bps": (
                            escape_scorecard.get("required_current_fee_gross_edge_bps")
                        ),
                        "gross_edge_gap_to_current_fee_bps": (
                            escape_scorecard.get("gross_edge_gap_to_current_fee_bps")
                        ),
                        "gross_edge_multiple_to_clear_current_fee": (
                            escape_scorecard.get("gross_edge_multiple_to_clear_current_fee")
                        ),
                        "business_path_actionability_status": business_actionability.get(
                            "status"
                        ),
                        "business_path_operator_action_required": (
                            business_actionability.get("operator_action_required")
                        ),
                        "business_path_actionability": (
                            business_actionability or None
                        ),
                        **_mm_lower_fee_history_extra(detail),
                        "best_sample_gated_gross_cell": gross_decomp.get(
                            "best_sample_gated_gross_cell"
                        ),
                        "best_walk_forward_holdout_gross_candidate": gross_decomp.get(
                            "best_walk_forward_holdout_gross_candidate"
                        ),
                    },
                )
            return _finish_blocker_row(
                row,
                blocker_class="feature_family_no_edge",
                primary_blocker="no_train_positive_walk_forward_feature_cell",
                next_trigger="stop_expanding_current_mm_filter_family_seek_new_signal_or_fee_path",
                engineering_actionable=True,
                secondary_blockers=secondary,
                extra={
                    "walk_forward_failure_status": failure_status,
                    "candidate_count": failure.get("candidate_count"),
                    "best_train_candidate": failure.get("best_train_candidate"),
                    "best_holdout_candidate": failure.get("best_holdout_candidate"),
                },
            )
        if failure_status == "TRAIN_POSITIVE_HOLDOUT_DECAY":
            return _finish_blocker_row(
                row,
                blocker_class="feature_family_no_edge",
                primary_blocker="train_positive_decays_in_holdout",
                next_trigger="reject_or_rework_filter_family_before_more_runtime_capture",
                engineering_actionable=True,
                secondary_blockers=secondary,
                extra={
                    "walk_forward_failure_status": failure_status,
                    "best_train_candidate": failure.get("best_train_candidate"),
                    "best_holdout_candidate": failure.get("best_holdout_candidate"),
                },
            )
        if sample_cost_shortfall is not None and sample_cost_shortfall > 0:
            return _finish_blocker_row(
                row,
                blocker_class="cost_wall",
                primary_blocker="current_fee_round_trip_exceeds_sample_gated_fill_sim_break_even",
                next_trigger="find_sample_gated_current_fee_cell_or_new_low_friction_mm_signal",
                engineering_actionable=True,
                secondary_blockers=secondary,
                extra={
                    "best_sample_gated_net_bps": sample_cost_wall.get(
                        "best_sample_gated_net_bps"
                    ),
                    "best_sample_gated_fee_round_trip_shortfall_bps": (
                        sample_cost_shortfall
                    ),
                    "break_even_maker_fee_bps_per_side": sample_cost_wall.get(
                        "break_even_maker_fee_bps_per_side"
                    ),
                    "fee_reduction_needed_bps_per_side": sample_cost_wall.get(
                        "fee_reduction_needed_bps_per_side"
                    ),
                    "sample_gated_cell_count": sample_cost_wall.get(
                        "sample_gated_cell_count"
                    ),
                    "business_path_actionability_status": business_actionability.get(
                        "status"
                    ),
                    "business_path_operator_action_required": (
                        business_actionability.get("operator_action_required")
                    ),
                },
            )
        if cost_shortfall is not None and cost_shortfall > 0:
            return _finish_blocker_row(
                row,
                blocker_class="cost_wall",
                primary_blocker="live_markout_current_fee_round_trip_exceeds_best_break_even",
                next_trigger="collect_more_maker_fills_or_use_sample_gated_fill_sim_cost_wall",
                engineering_actionable=True,
                secondary_blockers=secondary,
                extra={
                    "best_symbol_by_net_edge": cost_wall.get("best_symbol_by_net_edge"),
                    "best_fee_round_trip_shortfall_bps": cost_shortfall,
                    "best_n_maker_fills": cost_wall.get("best_n_maker_fills"),
                },
            )
        if fee_status in {
            "STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED",
            "NO_STANDARD_VIP_TIER_CLEARS_BREAK_EVEN",
        }:
            return _finish_blocker_row(
                row,
                blocker_class="fee_or_scale",
                primary_blocker=f"fee_path:{fee_status.lower()}",
                next_trigger="business_fee_path_review_not_strategy_promotion",
                secondary_blockers=secondary,
                extra={
                    "break_even_maker_fee_bps_per_side": fee_path.get(
                        "break_even_maker_fee_bps_per_side"
                    ),
                    "fee_reduction_needed_bps_per_side": fee_path.get(
                        "fee_reduction_needed_bps_per_side"
                    ),
                    "business_path_actionability_status": business_actionability.get(
                        "status"
                    ),
                    "business_path_operator_action_required": (
                        business_actionability.get("operator_action_required")
                    ),
                    "business_path_actionability": business_actionability or None,
                },
            )

    if arm_id == "polymarket_leadlag_ic" and _int(decision.get("sample_count")) < _int(
        decision.get("min_samples")
    ):
        pre_gate_persistence = _dict(detail.get("pre_gate_watchlist_persistence_scorecard"))
        sample_gate_recheck = _dict(detail.get("sample_gate_recheck_scorecard"))
        top_persistent_cells = _list(pre_gate_persistence.get("top_cells"))
        return _finish_blocker_row(
            row,
            blocker_class="sample_gate",
            primary_blocker="overlap_adjusted_ic_sample_below_gate",
            next_trigger=(
                sample_gate_recheck.get("next_trigger")
                or "wait_until_sample_gate_eta_then_recompute_hac_bh_filters"
            ),
            extra={
                "min_samples_remaining_to_gate": detail.get("min_samples_remaining_to_gate"),
                "sample_gate_eta_utc": detail.get("sample_gate_eta_utc"),
                "sample_gate_recheck_status": sample_gate_recheck.get("status"),
                "sample_gate_recheck_scorecard": sample_gate_recheck or None,
                "pre_gate_watchlist_persistence_status": detail.get(
                    "pre_gate_watchlist_persistence_status"
                ) or pre_gate_persistence.get("status"),
                "pre_gate_watchlist_recurring_cell_count": detail.get(
                    "pre_gate_watchlist_recurring_cell_count"
                ) or pre_gate_persistence.get("recurring_cell_count"),
                "pre_gate_watchlist_persistent_cell_count": detail.get(
                    "pre_gate_watchlist_persistent_cell_count"
                ) or pre_gate_persistence.get("persistent_cell_count"),
                "pre_gate_watchlist_floor_qualified_recurring_cell_count": detail.get(
                    "pre_gate_watchlist_floor_qualified_recurring_cell_count"
                ) or pre_gate_persistence.get("floor_qualified_recurring_cell_count"),
                "pre_gate_watchlist_floor_qualified_persistent_cell_count": detail.get(
                    "pre_gate_watchlist_floor_qualified_persistent_cell_count"
                ) or pre_gate_persistence.get("floor_qualified_persistent_cell_count"),
                "best_persistent_pre_gate_cell": (
                    top_persistent_cells[0]
                    if top_persistent_cells and isinstance(top_persistent_cells[0], dict)
                    else None
                ),
                "price_feedback_partial_collapse_count": detail.get(
                    "price_feedback_partial_collapse_count"
                ),
                "pre_gate_hac_watchlist_count": detail.get("pre_gate_hac_watchlist_count"),
            },
        )

    if arm_id == "flash_dip_l1_short_exit_replay":
        fail_reasons = [str(item) for item in _list(detail.get("fail_reasons"))]
        relation = str(detail.get("dominant_missing_event_window_l1_relation") or "")
        coverage_action = _dict(detail.get("coverage_action_scorecard"))
        coverage_action_status = str(
            detail.get("coverage_action_status")
            or coverage_action.get("status")
            or ""
        )
        coverage_engineering_actionable = coverage_action.get("engineering_actionable")
        if isinstance(coverage_engineering_actionable, bool):
            engineering_actionable = coverage_engineering_actionable
        else:
            engineering_actionable = True
        next_trigger = (
            coverage_action.get("next_trigger")
            or "capture_candidate_windows_with_l1_overlap_then_replay_short_exit"
        )
        if any("l1" in reason.lower() for reason in fail_reasons) or relation:
            return _finish_blocker_row(
                row,
                blocker_class="data_coverage",
                primary_blocker=relation or (fail_reasons[0] if fail_reasons else "l1_replay_coverage_gap"),
                next_trigger=next_trigger,
                engineering_actionable=engineering_actionable,
                extra={
                    "candidate_events": detail.get("candidate_events"),
                    "events_missing_l1_in_event_window": detail.get(
                        "events_missing_l1_in_event_window"
                    ),
                    "dominant_missing_event_window_l1_relation": relation or None,
                    "coverage_action_status": coverage_action_status or None,
                    "coverage_action_reason": (
                        detail.get("coverage_action_reason")
                        or coverage_action.get("reason")
                    ),
                    "coverage_action_scorecard": coverage_action or None,
                },
            )

    if arm_id == "flash_dip_execution_realism":
        verdict = str(detail.get("verdict_status") or "").upper()
        short_exit_status = str(detail.get("short_exit_status") or "").upper()
        fail_reasons = [str(item) for item in _list(detail.get("fail_reasons"))]
        if verdict == "EXECUTION_REALISM_BLOCKED" and short_exit_status == "SHORT_EXIT_RESEARCH_SIGNAL":
            dependent_l1 = _dict(detail.get("dependent_l1_short_exit_replay"))
            dependent_l1_actionable = dependent_l1.get("engineering_actionable")
            if isinstance(dependent_l1_actionable, bool):
                engineering_actionable = dependent_l1_actionable
            else:
                engineering_actionable = True
            next_trigger = (
                dependent_l1.get("coverage_action_next_trigger")
                or "run_l1_short_exit_replay_with_candidate_window_coverage_before_any_retune"
            )
            return _finish_blocker_row(
                row,
                blocker_class="data_coverage",
                primary_blocker="daily_exit_execution_realism_blocked_short_exit_needs_l1_replay",
                next_trigger=next_trigger,
                engineering_actionable=engineering_actionable,
                extra={
                    "candidate_label": detail.get("candidate_label"),
                    "k_pct": detail.get("k_pct"),
                    "gate_buffer_bps": detail.get("gate_buffer_bps"),
                    "gate_filled": detail.get("gate_filled"),
                    "gate_distinct_days": detail.get("gate_distinct_days"),
                    "gate_annret": detail.get("gate_annret"),
                    "short_exit_status": short_exit_status,
                    "best_short_exit_horizon": detail.get("best_short_exit_horizon"),
                    "best_short_exit_annret": detail.get("best_short_exit_annret"),
                    "best_short_exit_n_filled": detail.get("best_short_exit_n_filled"),
                    "best_short_exit_days": detail.get("best_short_exit_days"),
                    "dependent_l1_coverage_action_status": dependent_l1.get(
                        "coverage_action_status"
                    ),
                    "dependent_l1_coverage_action_reason": dependent_l1.get(
                        "coverage_action_reason"
                    ),
                    "dependent_l1_engineering_actionable": dependent_l1.get(
                        "engineering_actionable"
                    ),
                    "dependent_l1_dominant_missing_event_window_l1_relation": dependent_l1.get(
                        "dominant_missing_event_window_l1_relation"
                    ),
                    "dependent_l1_short_exit_replay": dependent_l1 or None,
                },
            )
        if verdict == "EXECUTION_REALISM_BLOCKED":
            return _finish_blocker_row(
                row,
                blocker_class="rejected_no_edge",
                primary_blocker="execution_realism_blocked_without_short_exit_research_signal",
                next_trigger="do_not_retune_flash_dip_shallow_k_without_new_execution_evidence",
                extra={
                    "candidate_label": detail.get("candidate_label"),
                    "fail_reasons": fail_reasons,
                    "gate_annret": detail.get("gate_annret"),
                    "gate_maxdd": detail.get("gate_maxdd"),
                },
            )
        if verdict == "EXECUTION_REALISM_INSUFFICIENT_SAMPLE":
            return _finish_blocker_row(
                row,
                blocker_class="sample_gate",
                primary_blocker="execution_realism_sample_below_gate",
                next_trigger="continue_read_only_execution_realism_capture_until_min_samples",
                extra={
                    "candidate_label": detail.get("candidate_label"),
                    "fail_reasons": fail_reasons,
                    "gate_filled": detail.get("gate_filled"),
                    "gate_distinct_days": detail.get("gate_distinct_days"),
                },
            )

    if arm_id == "flash_dip_buy_demo":
        touchability = _dict(detail.get("touchability"))
        if gate_status == "CAPTURING_NO_TOUCH":
            action_scorecard = _dict(touchability.get("action_scorecard"))
            action_status = str(action_scorecard.get("status") or "")
            next_trigger = (
                "run_shallow_k_execution_realism_then_l1_replay_before_any_retune"
                if action_status == "SHALLOW_REPRICE_RESEARCH_BAND_PRESENT"
                else "wait_for_touchable_dip_or_use_l1_replay_to_reprice_k_ladder"
            )
            return _finish_blocker_row(
                row,
                blocker_class="event_wait",
                primary_blocker="configured_flash_dip_limit_not_touchable",
                next_trigger=next_trigger,
                extra={
                    "true_order_count": touchability.get("true_order_count"),
                    "touched_count": touchability.get("touched_count"),
                    "deepest_candidate_k_with_touch_pct": touchability.get(
                        "deepest_candidate_k_with_touch_pct"
                    ),
                    "touchability_action_status": action_scorecard.get("status"),
                    "research_candidate_k_pct": action_scorecard.get(
                        "research_candidate_k_pct"
                    ),
                    "research_candidate_touched_count": action_scorecard.get(
                        "research_candidate_touched_count"
                    ),
                    "research_candidate_touch_rate_pct": action_scorecard.get(
                        "research_candidate_touch_rate_pct"
                    ),
                    "touchable_lower_k_count": action_scorecard.get(
                        "touchable_lower_k_count"
                    ),
                },
            )

    if gate_status in {"NO_EDGE_SURVIVES", "NO_EDGE", "REJECTED", "KILL", "KILLED"}:
        return _finish_blocker_row(
            row,
            blocker_class="rejected_no_edge",
            primary_blocker=f"gate_status:{gate_status.lower()}",
            next_trigger="do_not_promote_current_family_without_new_evidence",
        )

    if arm_id == "gate_b_listing_fade":
        return _finish_blocker_row(
            row,
            blocker_class="event_wait",
            primary_blocker=f"gate_b_status:{gate_status.lower()}",
            next_trigger="wait_for_fresh_gate_b_actionable_alert",
        )

    if arm_id == "aeg_robustness_matrix":
        dependency = _dict(detail.get("candidate_artifact_dependency"))
        return _finish_blocker_row(
            row,
            blocker_class="robustness_wait",
            primary_blocker="no_durable_aeg_candidate_rows",
            next_trigger=(
                dependency.get("next_trigger")
                or "feed_candidate_artifacts_into_robustness_matrix"
            ),
            engineering_actionable=(
                dependency.get("engineering_actionable")
                if isinstance(dependency.get("engineering_actionable"), bool)
                else True
            ),
            extra={
                "candidate_artifact_dependency_status": dependency.get("status"),
                "candidate_artifact_dependency_reason": dependency.get("reason"),
                "candidate_artifact_count": dependency.get("candidate_artifact_count"),
                "candidate_artifact_dependency": dependency or None,
            },
        )

    if action == RUN_READ_ONLY_CAPTURE and _int(decision.get("sample_count")) < _int(
        decision.get("min_samples")
    ):
        return _finish_blocker_row(
            row,
            blocker_class="sample_gate",
            primary_blocker="sample_count_below_gate",
            next_trigger="continue_read_only_capture_until_min_samples",
        )

    if action == WAIT:
        return _finish_blocker_row(
            row,
            blocker_class="event_wait",
            primary_blocker=f"gate_status:{gate_status.lower()}",
            next_trigger="wait_for_source_status_change",
        )

    return _finish_blocker_row(
        row,
        blocker_class="unknown_wait",
        primary_blocker="unclassified_profitability_blocker",
        next_trigger="inspect_arm_detail",
        engineering_actionable=True,
    )


def build_profitability_blocker_scorecard(
    arms: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    min_samples: int = 30,
) -> dict[str, Any]:
    """Summarize cross-arm reasons we still have no promotable profit edge."""
    dependency = _candidate_artifact_dependency_summary(arms, decisions)
    normalized_arms: list[dict[str, Any]] = []
    for arm in arms:
        arm_copy = dict(arm)
        arm_id = str(arm_copy.get("arm_id") or arm_copy.get("name") or "unknown")
        if arm_id == "aeg_robustness_matrix":
            detail = dict(_dict(arm_copy.get("detail")))
            detail["candidate_artifact_dependency"] = dependency
            arm_copy["detail"] = detail
        normalized_arms.append(arm_copy)
    arms_by_id = {
        str(arm.get("arm_id") or arm.get("name") or "unknown"): arm
        for arm in normalized_arms
    }
    rows = [
        classify_profitability_blocker(arms_by_id.get(str(decision.get("arm_id")), {}), decision)
        for decision in decisions
    ]
    rows.sort(key=lambda row: (
        row.get("blocker_rank", 99),
        _PRIORITY.get(str(row.get("action")), 99),
        str(row.get("arm_id")),
    ))
    counts: dict[str, int] = {}
    for row in rows:
        blocker_class = str(row.get("blocker_class") or "unknown_wait")
        counts[blocker_class] = counts.get(blocker_class, 0) + 1

    promotion_ready_count = sum(1 for row in rows if row.get("promotion_ready") is True)
    operator_actionable_count = sum(1 for row in rows if row.get("operator_actionable") is True)
    engineering_actionable_count = sum(1 for row in rows if row.get("engineering_actionable") is True)
    if promotion_ready_count > 0:
        status = "ACTIONABLE_ALPHA_REVIEW_READY"
    elif operator_actionable_count > 0:
        status = "ACTIONABLE_PROBE_READY"
    elif any(
        counts.get(name, 0)
        for name in (
            "feature_family_no_edge",
            "cost_wall",
            "fee_or_scale",
            "data_coverage",
            "rejected_no_edge",
            "source_health",
        )
    ):
        status = "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    else:
        status = "NO_ACTIONABLE_ALPHA_WAIT_OR_SAMPLE_GATED"

    return {
        "schema_version": "alpha_profitability_blocker_scorecard_v1",
        "status": status,
        "min_samples": min_samples,
        "blocker_counts": counts,
        "promotion_ready_count": promotion_ready_count,
        "operator_actionable_count": operator_actionable_count,
        "engineering_actionable_count": engineering_actionable_count,
        "top_blockers": rows[:3],
        "arms": rows,
    }


def build_discovery_plan(
    arms: list[dict[str, Any]],
    *,
    min_samples: int = 30,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """多臂 read-only discovery action plan。"""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    decisions = [decide_arm_action(arm, min_samples=min_samples) for arm in arms]
    decisions.sort(key=lambda row: (row["rank"], row["arm_id"]))
    counts: dict[str, int] = {}
    for row in decisions:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    blocker_scorecard = build_profitability_blocker_scorecard(
        arms,
        decisions,
        min_samples=min_samples,
    )
    return {
        "schema_version": DISCOVERY_LOOP_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "policy": "read_only_recommendations_no_probe_or_trade_side_effect",
        "action_counts": counts,
        "arms": decisions,
        "profitability_blocker_scorecard": blocker_scorecard,
    }


__all__ = [
    "BLOCK",
    "READY_FOR_AEG_CHAIN",
    "READY_FOR_PROBE",
    "RUN_READ_ONLY_CAPTURE",
    "WAIT",
    "build_discovery_plan",
    "build_profitability_blocker_scorecard",
    "classify_profitability_blocker",
    "decide_arm_action",
]
