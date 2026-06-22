from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.decision_packet import (
    build_profit_learning_decision_packet,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 22, 12, 0, tzinfo=dt.timezone.utc)


def _data_flow(*, cost_gate: bool = True) -> dict:
    return {
        "schema_version": "demo_data_flow_monitor_v1",
        "generated_at_utc": "2026-06-22T11:55:00+00:00",
        "summary": {
            "status": "RECENT_WINDOW_EMPTY_COST_GATE_REJECT_WALL",
            "answers": {
                "short_window_empty": True,
                "broad_window_has_any_data": True,
                "broad_window_has_candidate_or_reject_data": cost_gate,
                "cost_gate_rejects_recorded": cost_gate,
                "orders_present": False,
                "fills_present": False,
                "global_cost_gate_lowering_recommended": False,
            },
            "key_counts": {
                "broad_cost_gate_rejects": 2696 if cost_gate else 0,
                "broad_orders": 0,
                "broad_fills": 0,
            },
        },
    }


def _counterfactual(*, generated_at: str = "2026-06-22T11:56:00+00:00") -> dict:
    top_cell = {
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
        "priority_score": 82.5,
        "n": 486,
        "avg_net_bps": 97.9,
        "p50_gross_bps": 49.4,
        "net_positive_pct": 86.0,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
    }
    return {
        "generated_at_utc": generated_at,
        "learning_lane_scorecard": {
            "schema_version": "cost_gate_reject_counterfactual_v2",
            "status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "action_counts": {"LEARNING_PROBE_CANDIDATE": 1},
            "profit_opportunity_ranking": {
                "schema_version": "cost_gate_profit_opportunity_ranking_v1",
                "status": "PROFIT_LEARNING_CANDIDATES_PRESENT",
                "candidate_count": 1,
                "top_side_cells": [top_cell],
            },
            "horizon_stability_scorecard": {
                "schema_version": "cost_gate_reject_horizon_stability_v1",
                "status": "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT",
            },
        },
    }


def _ready_plan() -> dict:
    return {
        "schema_version": "cost_gate_demo_learning_lane_plan_v1",
        "generated_at_utc": "2026-06-22T11:57:00+00:00",
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "OPERATOR_REVIEW",
        "selected_probe_candidate_count": 1,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
    }


def test_missing_counterfactual_routes_recorded_rejects_to_scorecard_refresh() -> None:
    packet = build_profit_learning_decision_packet(
        data_flow=_data_flow(),
        now_utc=NOW,
    )

    assert packet["status"] == "RUN_REJECT_COUNTERFACTUAL"
    assert packet["answers"]["cost_gate_rejects_recorded"] is True
    assert packet["answers"]["silent_drop_risk"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["next_actions"] == [
        "run_cost_gate_reject_counterfactual_multi_horizon_scorecard"
    ]


def test_counterfactual_candidate_without_plan_routes_to_bounded_plan() -> None:
    packet = build_profit_learning_decision_packet(
        data_flow=_data_flow(),
        counterfactual=_counterfactual(),
        now_utc=NOW,
    )

    assert packet["status"] == "BUILD_OR_REFRESH_BOUNDED_LEARNING_PLAN"
    assert packet["answers"]["counterfactual_learning_candidates_present"] is True
    assert packet["answers"]["bounded_plan_ready"] is False
    assert packet["counterfactual"]["top_side_cells"][0]["side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )


def test_ready_plan_with_source_not_ready_routes_to_stack_repair() -> None:
    packet = build_profit_learning_decision_packet(
        data_flow=_data_flow(),
        counterfactual=_counterfactual(),
        plan=_ready_plan(),
        activation_preflight={
            "schema_version": "cost_gate_demo_learning_lane_activation_preflight_v1",
            "generated_at_utc": "2026-06-22T11:58:00+00:00",
            "status": "SOURCE_NOT_READY",
            "next_actions": ["sync_runtime_source_to_current_main_before_activation"],
        },
        now_utc=NOW,
    )

    assert packet["status"] == "ACTIVATE_OR_REPAIR_LEARNING_STACK"
    assert packet["plan"]["ready"] is True
    assert packet["activation"]["status"] == "SOURCE_NOT_READY"
    assert packet["next_actions"] == ["sync_runtime_source_to_current_main_before_activation"]
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"


def test_blocked_outcome_candidate_surfaces_operator_review_without_authority() -> None:
    packet = build_profit_learning_decision_packet(
        data_flow=_data_flow(),
        counterfactual=_counterfactual(),
        plan=_ready_plan(),
        activation_preflight={
            "schema_version": "cost_gate_demo_learning_lane_activation_preflight_v1",
            "generated_at_utc": "2026-06-22T11:58:00+00:00",
            "status": "DATA_ACCUMULATING",
        },
        blocked_review={
            "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v2",
            "generated_at_utc": "2026-06-22T11:59:00+00:00",
            "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
            "review_candidate_count": 1,
        },
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == "OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES"
    assert packet["answers"]["blocked_outcome_review_candidates_present"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert "Cost Gate Profit Learning Decision Packet" in markdown
    assert "ma_crossover|ETHUSDT|Sell" in markdown


def test_stale_counterfactual_fails_closed_before_plan_review() -> None:
    packet = build_profit_learning_decision_packet(
        data_flow=_data_flow(),
        counterfactual=_counterfactual(generated_at="2026-06-20T11:56:00+00:00"),
        now_utc=NOW,
        max_artifact_age_hours=24,
    )

    assert packet["status"] == "REFRESH_REJECT_COUNTERFACTUAL"
    assert packet["artifacts"]["counterfactual"]["status"] == "STALE"
