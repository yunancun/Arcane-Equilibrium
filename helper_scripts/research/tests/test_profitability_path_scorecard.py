from __future__ import annotations

import datetime as dt

from alpha_discovery_throughput.profitability_path_scorecard import (
    PROFITABILITY_PATH_SCORECARD_SCHEMA_VERSION,
    build_profitability_path_scorecard,
    render_markdown,
)


def _cost_gate_counterfactual() -> dict:
    return {
        "generated_at_utc": "2026-06-22T03:00:00+00:00",
        "friction_bps": 4.0,
        "learning_lane_scorecard": {
            "status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "profit_opportunity_ranking": {
                "status": "PROFIT_LEARNING_CANDIDATES_PRESENT",
                "candidate_count": 2,
                "top_side_cells": [
                    {
                        "side_cell_key": "ma_crossover|BTCUSDT|Buy",
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                        "learning_lane_reason": "avg_net_positive",
                        "priority_score": 44.6,
                        "priority_tier": "LOW_PRIORITY_BOUNDED_DEMO_LEARNING",
                        "avg_net_bps": 11.397,
                        "p50_gross_bps": 22.5553,
                        "net_positive_pct": 65.08,
                        "sample_count_for_gate": 39637,
                        "distinct_ts": 39637,
                        "n": 39637,
                        "rows_per_distinct_ts": 1.0,
                        "next_action": "operator_review_ranked_side_cell_for_bounded_demo_learning_lane",
                    }
                ],
            },
            "horizon_stability_scorecard": {
                "status": "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT",
                "top_side_cells": [
                    {
                        "side_cell_key": "ma_crossover|BTCUSDT|Buy",
                        "status": "CANDIDATE_MULTI_HORIZON_STABLE",
                        "candidate_horizons": [15, 60],
                        "block_confirmed_horizons": [240],
                        "observed_horizons": [15, 60, 240],
                        "best_horizon_minutes": 60,
                        "best_avg_net_bps": 11.397,
                        "best_net_positive_pct": 65.08,
                        "best_p50_gross_bps": 22.5553,
                        "best_sample_count_for_gate": 39637,
                        "reason": "side_cell_clears_learning_thresholds_on_multiple_horizons",
                    },
                    {
                        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                        "status": "MIXED_HORIZON_RESPONSE",
                        "candidate_horizons": [240],
                        "block_confirmed_horizons": [15, 60],
                        "observed_horizons": [15, 60, 240],
                        "best_horizon_minutes": 240,
                        "best_avg_net_bps": 31.8707,
                        "best_net_positive_pct": 81.94,
                        "best_p50_gross_bps": 51.4448,
                        "best_sample_count_for_gate": 13819,
                        "reason": "side_cell_candidate_on_one_horizon_but_blocked_on_another",
                    },
                ],
            },
        },
    }


def _sealed_horizon_replay() -> dict:
    return {
        "schema_version": "horizon_specific_sealed_replay_packet_v1",
        "generated_at_utc": "2026-06-22T03:43:00+00:00",
        "status": "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW",
        "reason": "preselected_retiming_candidate_revalidated_against_sealed_replay_artifact",
        "next_action": "operator_review_sealed_replay_then_wait_for_learning_stack_outcome_accumulation",
        "selection": {
            "selected": {
                "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                "candidate_status": "RETIMING_CANDIDATE",
                "best_horizon_minutes": 240,
                "primary_horizon_minutes": 60,
            },
        },
        "source": {
            "horizon_packet": {"sha256": "horizon-sha"},
            "replay_counterfactual": {"sha256": "replay-sha"},
        },
        "replay_evaluation": {
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "failed_gate_names": [],
            "best_horizon": {
                "horizon_minutes": 240,
                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                "sample_count_for_gate": 13819,
                "avg_net_bps": 31.8707,
                "p50_gross_bps": 51.4448,
                "net_positive_pct": 81.94,
            },
            "primary_horizon": {
                "horizon_minutes": 60,
                "learning_lane_action": "BLOCK_CONFIRMED",
                "avg_net_bps": -41.8107,
            },
        },
        "answers": {
            "sealed_replay_passed": True,
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def _sealed_horizon_learning_evidence() -> dict:
    return {
        "schema_version": "sealed_horizon_learning_evidence_v1",
        "generated_at_utc": "2026-06-22T05:30:00+00:00",
        "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
        "reason": "blocked_signal_outcomes_clear_review_thresholds",
        "next_trigger": "operator_review_blocked_outcome_scorecard_before_probe_authority",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "source_kind": "horizon_specific_sealed_replay",
        "outcome_horizon_minutes": 240,
        "default_horizon_minutes": 60,
        "materialization": {
            "input_feature_row_count": 16515,
            "materialized_record_count": 16515,
            "appended_record_count": 16515,
            "decision_counts": {"ORDER_AUTHORITY_NOT_GRANTED": 16515},
            "all_order_authority_not_granted": True,
        },
        "outcomes": {
            "blocked_signal_outcome_count": 16515,
            "appended_outcome_count": 16515,
            "avg_gross_bps": 7.0511,
            "avg_net_bps": 3.0511,
            "net_positive_pct": 68.5619,
        },
        "review": {
            "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
            "review_candidate_side_cell_count": 1,
            "blocked_signal_outcome_count": 16515,
            "top_side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "top_side_cell_status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE",
            "top_side_cell_wrongful_block_score": 16000.0,
        },
        "answers": {
            "sealed_candidate_materialized": True,
            "blocked_signal_outcomes_recorded": True,
            "candidate_clears_operator_review_gate": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "artifacts": {
            "ledger": {"sha256": "ledger-sha"},
            "source_rows": {"sha256": "source-rows-sha"},
            "review": {"sha256": "review-sha"},
        },
    }


def _sealed_horizon_operator_review() -> dict:
    return {
        "schema_version": "sealed_horizon_operator_review_v1",
        "generated_at_utc": "2026-06-22T05:40:00+00:00",
        "status": "PENDING_OPERATOR_REVIEW",
        "reason": "defer",
        "decision": "defer",
        "operator_id": None,
        "review_scope": "preflight_review_only_not_probe_authorization",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "outcome_horizon_minutes": 240,
        "source_kind": "horizon_specific_sealed_replay",
        "blocked_signal_outcome_count": 16515,
        "avg_gross_bps": 7.0511,
        "avg_net_bps": 3.0511,
        "net_positive_pct": 68.5619,
        "operator_review_approved": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
        "blocking_gate_count": 0,
        "blocking_gates": [],
        "next_actions": [
            "operator_review_sealed_horizon_preflight_before_bounded_demo_probe"
        ],
        "typed_confirm_expected": (
            "approve_sealed_horizon_preflight:ma_crossover|BTCUSDT|Sell:240"
        ),
        "typed_confirm_provided": False,
        "typed_confirm_matches": False,
        "answers": {
            "operator_review_approved": False,
            "sealed_horizon_evidence_ready": True,
            "sealed_horizon_probe_preflight_aligned": True,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": "artifact-only sealed horizon operator review",
    }


def _sealed_horizon_probe_preflight(
    status: str = "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED",
) -> dict:
    blocking_gates = []
    next_actions = []
    operator_review_recorded = False
    production_lane_accumulating = False
    ready = False
    if status == "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED":
        blocking_gates = [
            "operator_sealed_horizon_review_recorded",
            "production_learning_lane_accumulating",
        ]
        next_actions = [
            "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe",
            "activate_or_repair_cost_gate_learning_lane_stack_before_runtime_probe",
        ]
    elif status == "OPERATOR_REVIEW_REQUIRED":
        blocking_gates = ["operator_sealed_horizon_review_recorded"]
        production_lane_accumulating = True
        next_actions = [
            "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
        ]
    elif status == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION":
        operator_review_recorded = True
        production_lane_accumulating = True
        ready = True
        next_actions = [
            "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
        ]
    design_status = (
        "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION"
        if ready
        else "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN"
        if production_lane_accumulating
        else "NOT_READY_FOR_OPERATOR_PROBE_REVIEW"
    )
    return {
        "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
        "generated_at_utc": "2026-06-22T06:00:00+00:00",
        "status": status,
        "reason": ";".join(blocking_gates)
        or "all_pre_authorization_gates_passed_without_authority_grant",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "outcome_horizon_minutes": 240,
        "blocking_gate_count": len(blocking_gates),
        "blocking_gates": blocking_gates,
        "next_actions": next_actions,
        "answers": {
            "sealed_horizon_evidence_ready": True,
            "decision_packet_aligned": True,
            "operator_review_recorded": operator_review_recorded,
            "production_learning_lane_accumulating": production_lane_accumulating,
            "ready_for_operator_bounded_demo_probe_authorization": ready,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "bounded_demo_probe_design": {
            "schema_version": "bounded_demo_probe_design_v1",
            "status": design_status,
            "suggested_initial_probe_limits": {
                "active": False,
                "requires_separate_operator_authorization": True,
                "max_probe_intents_before_review": 3,
                "max_demo_notional_usdt_per_order": 10,
                "max_total_demo_notional_usdt_before_review": 30,
            },
            "success_criteria": {
                "min_realized_avg_net_bps": 0.0,
                "promotion_evidence": False,
            },
        },
    }


def _bounded_probe_operator_authorization(
    status: str = "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW",
    *,
    blocking_gates: list[str] | None = None,
    ready_for_review: bool | None = None,
    authorized: bool = False,
) -> dict:
    if blocking_gates is None:
        blocking_gates = []
    if ready_for_review is None:
        ready_for_review = status == "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW"
    operator_authorization = (
        {
            "schema_version": "bounded_demo_probe_operator_authorization_v1",
            "status": "DEMO_LEARNING_PROBE_GRANTED",
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "max_authorized_probe_orders": 2,
            "order_authority_granted": True,
            "probe_authority_granted": True,
            "promotion_evidence": False,
        }
        if authorized
        else None
    )
    next_action = "operator_may_authorize_bounded_demo_probe_with_exact_typed_confirm"
    if blocking_gates:
        next_action = "refresh_bounded_probe_operator_authorization_after_source_gates_pass"
    if authorized:
        next_action = "operator_review_plan_inclusion_of_bounded_probe_operator_authorization"
    return {
        "schema_version": "bounded_demo_probe_operator_authorization_packet_v1",
        "generated_at_utc": "2026-06-22T06:20:00+00:00",
        "status": status,
        "reason": ";".join(blocking_gates) or "defer",
        "decision": "authorize" if authorized else "defer",
        "review_scope": "operator_authorization_artifact_only_not_plan_mutation",
        "candidate": {
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "source_candidate_max_probe_orders": 3,
        "requested_max_authorized_probe_orders": 2 if authorized else None,
        "expires_at_utc": "2026-06-22T18:00:00+00:00" if authorized else None,
        "operator_authorization": operator_authorization,
        "blocking_gate_count": len(blocking_gates),
        "blocking_gates": blocking_gates,
        "next_actions": [next_action],
        "typed_confirm_expected": (
            "authorize_bounded_demo_probe:ma_crossover|BTCUSDT|Sell:2:auth-fixture"
        ),
        "typed_confirm_provided": authorized,
        "typed_confirm_matches": authorized,
        "answers": {
            "ready_for_operator_authorization_review": ready_for_review,
            "bounded_demo_probe_authorized": authorized,
            "operator_authorization_object_emitted": operator_authorization is not None,
            "plan_mutation_performed": False,
            "writer_enabled": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted_in_authorization_object": authorized,
            "order_authority_granted_in_authorization_object": authorized,
        },
    }


def _bounded_probe_result_review(
    status: str = "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
    *,
    completed: int = 10,
    avg_net_bps: float = 2.5,
    net_positive_pct: float = 70.0,
    evidence_quality_status: str | None = None,
    matched_control_count: int | None = None,
    matched_control_avg_net_bps: float = 1.0,
) -> dict:
    if evidence_quality_status is None:
        if status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED":
            evidence_quality_status = "REALIZED_EDGE_FAILED"
        elif status == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED":
            evidence_quality_status = "FIRST_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
        elif status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED":
            evidence_quality_status = "LEARNING_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
        elif status == "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW":
            evidence_quality_status = "PROBE_SAMPLE_BELOW_FIRST_REVIEW_FLOOR"
        else:
            evidence_quality_status = "NO_PROBE_OUTCOMES_RECORDED"
    if matched_control_count is None:
        matched_control_count = 0 if "MISSING" in evidence_quality_status else completed
    probe_minus_control = (
        avg_net_bps - matched_control_avg_net_bps
        if matched_control_count
        else None
    )
    probe_edge_capture_ratio = (
        round(avg_net_bps / matched_control_avg_net_bps, 4)
        if matched_control_count and matched_control_avg_net_bps > 0.0
        else None
    )
    probe_execution_gap_bps = (
        round(-probe_minus_control, 4)
        if probe_minus_control is not None and probe_minus_control < 0.0
        else None
    )
    execution_realism_gap = (
        evidence_quality_status == "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
    )
    next_action = "operator_review_first_probe_results_before_any_additional_probe_budget"
    if status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED":
        next_action = (
            "operator_review_probe_learning_results_before_any_promotion_or_gate_change"
        )
    elif status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED":
        next_action = "stop_probe_and_keep_cost_gate_blocked_for_this_side_cell"
    if execution_realism_gap:
        next_action = (
            "investigate_probe_execution_realism_slippage_and_timing_before_cost_gate_review"
        )
    return {
        "schema_version": "bounded_demo_probe_result_review_v1",
        "generated_at_utc": "2026-06-22T07:00:00+00:00",
        "status": status,
        "reason": "fixture_result_review",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "candidate": {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "probe_result_summary": {
            "admitted_probe_attempt_count": completed,
            "completed_probe_outcome_count": completed,
            "positive_probe_outcome_count": int(completed * net_positive_pct / 100.0),
            "avg_realized_gross_bps": avg_net_bps + 4.0,
            "avg_realized_net_bps": avg_net_bps,
            "net_positive_pct": net_positive_pct,
            "min_realized_avg_net_bps": 0.0,
            "min_realized_net_positive_pct": 60.0,
            "first_review_outcome_floor": 3,
            "learning_review_outcome_floor": 10,
            "max_filled_probe_outcomes_before_review": 3,
        },
        "evidence_quality": {
            "schema_version": "bounded_demo_probe_evidence_quality_v1",
            "status": evidence_quality_status,
            "reason": "fixture_evidence_quality",
            "matched_control_required": completed >= 3,
            "matched_control_present": matched_control_count > 0,
            "matched_control_outcome_count": matched_control_count,
            "matched_control_avg_net_bps": matched_control_avg_net_bps
            if matched_control_count
            else None,
            "matched_control_net_positive_pct": 66.7
            if matched_control_count
            else None,
            "probe_minus_control_avg_net_bps": probe_minus_control,
            "probe_edge_capture_ratio": probe_edge_capture_ratio,
            "probe_execution_gap_bps": probe_execution_gap_bps,
            "probe_outperforms_matched_control": (
                matched_control_count > 0 and avg_net_bps > matched_control_avg_net_bps
            ),
            "execution_realism_gap": execution_realism_gap,
            "anecdote_risk": evidence_quality_status
            in {
                "CONTROL_COMPARISON_MISSING",
                "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
            },
            "promotion_evidence": False,
        },
        "answers": {
            "authority_boundary_preserved": True,
            "operator_review_required": status
            in {
                "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
                "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
                "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
            },
            "continue_probe_without_operator_review_allowed": (
                status == "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW"
            ),
            "stop_probe_recommended": (
                status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
            ),
            "learning_review_candidate": (
                status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED"
            ),
            "matched_control_comparison_present": matched_control_count > 0,
            "anecdote_risk": evidence_quality_status
            in {
                "CONTROL_COMPARISON_MISSING",
                "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
            },
            "execution_realism_gap": execution_realism_gap,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": [next_action],
        "design": {
            "status": "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION",
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        },
        "boundary": "artifact-only bounded demo-probe result review",
    }


def _bounded_probe_shadow_placement_impact(
    status: str = "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH",
    *,
    candidate_matched_order_count: int = 0,
    candidate_matched_submit_count: int = 0,
) -> dict:
    return {
        "schema_version": "bounded_demo_probe_shadow_placement_impact_v1",
        "generated_at_utc": "2026-06-22T07:04:00+00:00",
        "status": status,
        "reason": "fixture_shadow_placement_impact",
        "candidate": {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "outcome_horizon_minutes": 240,
        },
        "shadow_summary": {
            "reviewed_order_count": 6,
            "shadow_submit_count": 6,
            "shadow_skip_count": 0,
            "candidate_matched_order_count": candidate_matched_order_count,
            "candidate_matched_submit_count": candidate_matched_submit_count,
            "future_bbo_would_cross_shadow_limit_count": 4,
            "max_original_best_touch_gap_bps": 1530.6074,
            "max_shadow_initial_touch_gap_bps": 58.2092,
            "avg_shadow_initial_touch_gap_bps": 17.0489,
            "max_gap_reduction_bps": 1522.1026,
            "sample_scope": (
                "candidate_matched_runtime_sample"
                if candidate_matched_order_count
                else "current_demo_order_flow_not_candidate_matched"
            ),
        },
        "answers": {
            "shadow_placement_improves_touchability": True,
            "candidate_matched_runtime_sample_present": (
                candidate_matched_order_count > 0
            ),
            "candidate_specific_alpha_proof": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": [
            "operator_review_mechanical_touchability_before_rust_patch",
            "collect_candidate_matched_bounded_demo_probe_evidence_after_authorization",
        ],
    }


def _bounded_probe_execution_realism_review(
    *,
    status: str = "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED",
    primary_hypothesis: str = "fill_backed_execution_missing",
    next_action: str = "record_fill_backed_probe_execution_rows_or_l1_replay_before_cost_gate_review",
) -> dict:
    return {
        "schema_version": "bounded_demo_probe_execution_realism_review_v1",
        "generated_at_utc": "2026-06-22T07:05:00+00:00",
        "status": status,
        "reason": "fixture_execution_realism_review",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "candidate": {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "source_result_review": {
            "schema_version": "bounded_demo_probe_result_review_v1",
            "status": "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            "evidence_quality_status": (
                "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
            ),
            "probe_edge_capture_ratio": 0.6667,
            "probe_execution_gap_bps": 1.0,
            "probe_minus_control_avg_net_bps": -1.0,
        },
        "probe_execution_summary": {
            "count": 3,
            "avg_net_bps": 2.0,
            "avg_gross_bps": 6.0,
            "avg_cost_bps": 4.0,
            "avg_entry_delay_ms": 120000.0,
            "fill_backed_outcome_count": 0,
            "proxy_outcome_count": 3,
            "fill_backed_pct": 0.0,
        },
        "matched_control_execution_summary": {
            "count": 3,
            "avg_net_bps": 3.0,
            "avg_gross_bps": 7.0,
            "avg_cost_bps": 4.0,
            "avg_entry_delay_ms": 0.0,
            "fill_backed_outcome_count": 3,
            "proxy_outcome_count": 0,
            "fill_backed_pct": 100.0,
        },
        "gap_decomposition": {
            "net_capture_gap_bps": 1.0,
            "gross_capture_gap_bps": 1.0,
            "cost_or_slippage_gap_bps": 0.0,
            "entry_delay_gap_ms": 120000.0,
        },
        "execution_gap_hypotheses": [
            {
                "kind": primary_hypothesis,
                "severity": "HIGH",
                "next_action": next_action,
            }
        ],
        "answers": {
            "authority_boundary_preserved": True,
            "execution_realism_gap_confirmed": True,
            "fill_backed_probe_execution_available": False,
            "cost_gate_or_operator_review_allowed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": [next_action],
        "boundary": "artifact-only bounded demo-probe execution-realism review",
    }


def test_cost_gate_candidates_and_horizon_paths_do_not_grant_authority() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "DATA_FLOW_MONITOR_REQUIRED",
            "next_actions": ["run_demo_data_flow_monitor_for_1h_4h_24h"],
            "answers": {
                "silent_drop_risk": True,
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "NOT_ACCUMULATING"},
        },
        activation_preflight={"status": "NOT_ACCUMULATING"},
        now_utc=dt.datetime(2026, 6, 22, 3, tzinfo=dt.timezone.utc),
    )

    assert scorecard["schema_version"] == PROFITABILITY_PATH_SCORECARD_SCHEMA_VERSION
    assert scorecard["status"] == "PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING"
    assert scorecard["answers"]["cost_gate_crossing_candidates_present"] is True
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert scorecard["answers"]["order_authority_granted"] is False
    assert scorecard["global_boundaries"]["order_authority"] == "NOT_GRANTED"

    paths = {row["path_id"]: row for row in scorecard["top_paths"]}
    cost_path = paths["cost_gate_learning_lane:ma_crossover|BTCUSDT|Buy"]
    assert cost_path["status"] == "COST_GATE_CANDIDATE_READY_FOR_DATA_FLOW_PROOF"
    assert cost_path["required_next_gate"] == "run_demo_data_flow_monitor"
    assert cost_path["current_edge_bps"] == 11.397
    assert cost_path["sample_count"] == 39637
    assert cost_path["order_authority"] == "NOT_GRANTED"

    horizon_path = paths["horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"]
    assert horizon_path["class"] == "horizon_retiming_or_side_cell_filter"
    assert horizon_path["status"] == "HORIZON_EDGE_AMPLIFICATION_CANDIDATE"
    assert horizon_path["candidate_horizons_minutes"] == [240]
    assert horizon_path["best_horizon_minutes"] == 240


def test_sealed_horizon_replay_advances_path_to_learning_accumulation() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "ACTIVATE_OR_REPAIR_LEARNING_STACK",
            "next_actions": ["activate_or_repair_cost_gate_learning_lane_stack"],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "NOT_ACCUMULATING"},
        },
        activation_preflight={"status": "NOT_ACCUMULATING"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        now_utc=dt.datetime(2026, 6, 22, 3, tzinfo=dt.timezone.utc),
    )

    paths = {row["path_id"]: row for row in scorecard["top_paths"]}
    horizon_path = paths["horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"]
    assert horizon_path["status"] == (
        "SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION"
    )
    assert horizon_path["required_next_gate"] == (
        "learning_stack_accumulates_ledger_and_outcome_rows_for_sealed_horizon_candidate"
    )
    assert horizon_path["next_action"] == (
        "activate_or_repair_cost_gate_learning_lane_then_record_blocked_signal_outcomes"
    )
    assert horizon_path["evidence"]["sealed_replay_passed"] is True
    assert horizon_path["evidence"]["sealed_replay_best_horizon_minutes"] == 240
    assert horizon_path["evidence"]["sealed_replay_primary_action"] == "BLOCK_CONFIRMED"
    assert scorecard["artifacts"]["horizon_sealed_replay"]["present"] is True
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert horizon_path["order_authority"] == "NOT_GRANTED"
    assert horizon_path["promotion_evidence"] is False


def test_sealed_horizon_learning_evidence_advances_path_to_operator_review() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "ACTIVATE_OR_REPAIR_LEARNING_STACK",
            "next_actions": ["activate_or_repair_cost_gate_learning_lane_stack"],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "NOT_ACCUMULATING"},
        },
        activation_preflight={"status": "NOT_ACCUMULATING"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        now_utc=dt.datetime(2026, 6, 22, 6, tzinfo=dt.timezone.utc),
    )

    paths = {row["path_id"]: row for row in scorecard["top_paths"]}
    horizon_path = paths["horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"]
    assert horizon_path["status"] == (
        "SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW"
    )
    assert horizon_path["priority_rank"] == 1
    assert horizon_path["required_next_gate"] == (
        "operator_reviews_bounded_demo_probe_for_sealed_horizon_candidate"
    )
    assert horizon_path["next_action"] == (
        "operator_review_sealed_horizon_learning_evidence_before_any_bounded_demo_probe"
    )
    assert horizon_path["evidence"]["sealed_learning_operator_review_ready"] is True
    assert horizon_path["evidence"]["sealed_learning_outcome_horizon_minutes"] == 240
    assert horizon_path["evidence"]["sealed_learning_blocked_signal_outcome_count"] == (
        16515
    )
    assert horizon_path["evidence"]["sealed_learning_avg_net_bps"] == 3.0511
    assert scorecard["artifacts"]["horizon_learning_evidence"]["present"] is True
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert horizon_path["order_authority"] == "NOT_GRANTED"
    assert horizon_path["main_cost_gate_adjustment"] == "NONE"
    assert horizon_path["promotion_evidence"] is False


def test_sealed_horizon_operator_review_is_visible_without_authority() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "NOT_ACCUMULATING"},
        },
        activation_preflight={"status": "NOT_ACCUMULATING"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_operator_review=_sealed_horizon_operator_review(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            status="OPERATOR_REVIEW_REQUIRED"
        ),
        now_utc=dt.datetime(2026, 6, 22, 6, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]

    assert scorecard["answers"]["sealed_horizon_operator_review_present"] is True
    assert scorecard["answers"]["sealed_horizon_operator_review_pending"] is True
    assert scorecard["answers"]["sealed_horizon_operator_review_approved"] is False
    assert scorecard["answers"][
        "sealed_horizon_operator_review_grants_runtime_authority"
    ] is False
    assert scorecard["artifacts"]["sealed_horizon_operator_review"]["present"] is True
    assert top["evidence"]["sealed_operator_review_present"] is True
    assert top["evidence"]["sealed_operator_review_status"] == "PENDING_OPERATOR_REVIEW"
    assert top["evidence"]["sealed_operator_review_decision"] == "defer"
    assert top["evidence"]["sealed_operator_review_approved"] is False
    assert top["evidence"][
        "sealed_operator_review_review_grants_runtime_authority"
    ] is False
    assert top["evidence"]["sealed_operator_review_probe_authority_granted"] is False
    assert top["evidence"]["sealed_operator_review_order_authority_granted"] is False
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert scorecard["answers"]["order_authority_granted"] is False
    assert top["order_authority"] == "NOT_GRANTED"
    assert top["main_cost_gate_adjustment"] == "NONE"


def test_sealed_horizon_preflight_drives_profitability_closure_gates() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "NOT_ACCUMULATING"},
        },
        activation_preflight={"status": "NOT_ACCUMULATING"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(),
        now_utc=dt.datetime(2026, 6, 22, 6, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]

    assert top["path_id"] == "horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"
    assert top["status"] == (
        "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE"
    )
    assert top["required_next_gate"] == (
        "operator_review_recorded_and_production_learning_lane_accumulates"
    )
    assert top["evidence"]["sealed_probe_preflight_blocking_gate_count"] == 2
    assert top["evidence"]["sealed_probe_preflight_operator_review_recorded"] is False
    assert top["evidence"]["sealed_probe_preflight_production_lane_accumulating"] is False
    assert top["evidence"][
        "sealed_probe_preflight_bounded_demo_probe_design_status"
    ] == "NOT_READY_FOR_OPERATOR_PROBE_REVIEW"
    assert top["evidence"][
        "sealed_probe_preflight_bounded_demo_probe_max_probe_intents_before_review"
    ] == 3
    assert top["evidence"][
        "sealed_probe_preflight_bounded_demo_probe_promotion_evidence"
    ] is False

    assert closure["schema_version"] == "profitability_engineering_closure_v1"
    assert closure["status"] == (
        "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_AND_PRODUCTION_LEARNING_LANE"
    )
    assert closure["proof_gate_count_remaining"] == 2
    assert "production learning lane accumulates ledger" in closure[
        "proof_gates_remaining"
    ][1]
    assert closure["cost_gate_escape_strategy"]["global_cost_gate_lowering"] is False
    assert closure["cost_gate_escape_strategy"]["probe_authority_granted"] is False
    assert closure["cost_gate_root_blockers"][0]["source"] == (
        "sealed_horizon_probe_preflight"
    )
    assert closure["cost_gate_root_blockers"][0]["gate"] == (
        "operator_sealed_horizon_review_recorded"
    )
    next_move = closure["profitability_next_move"]
    assert next_move["move_class"] == "operator_reviews_sealed_horizon_edge_before_probe"
    assert next_move["recommended_action"] == (
        "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
    )
    assert next_move["edge_snapshot"]["candidate_key"] == "ma_crossover|BTCUSDT|Sell"
    assert next_move["edge_snapshot"]["edge_above_cost_bps"] == 27.8707
    assert next_move["runtime_mutation_required"] is False
    assert next_move["cost_gate_policy"]["global_cost_gate_lowering"] is False
    assert closure["edge_amplification_backlog"][0]["path_class"] == (
        "horizon_retiming_or_side_cell_filter"
    )
    assert scorecard["answers"]["bounded_demo_probe_preflight_present"] is True
    assert scorecard["answers"]["bounded_demo_probe_preflight_ready"] is False
    assert scorecard["artifacts"]["sealed_horizon_probe_preflight"]["present"] is True


def test_ready_preflight_keeps_authority_separate_from_profitability_closure() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        now_utc=dt.datetime(2026, 6, 22, 6, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]

    assert top["status"] == "SEALED_HORIZON_PREFLIGHT_READY_FOR_OPERATOR_AUTHORIZATION"
    assert top["evidence"]["sealed_probe_preflight_ready_for_operator_authorization"] is True
    assert closure["status"] == "OPERATOR_CAN_REVIEW_BOUNDED_DEMO_PROBE_AUTHORIZATION"
    assert closure["proof_gate_count_remaining"] == 0
    assert scorecard["answers"]["bounded_demo_probe_preflight_ready"] is True
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert scorecard["answers"]["order_authority_granted"] is False
    assert scorecard["global_boundaries"]["probe_authority"] == "NOT_GRANTED"
    assert closure["cost_gate_escape_strategy"]["order_authority_granted"] is False


def test_operator_authorization_gates_refine_profitability_closure() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_operator_authorization=_bounded_probe_operator_authorization(
            "AUTHORITY_PATH_PATCH_NOT_READY",
            blocking_gates=["authority_path_patch_readiness_ready"],
            ready_for_review=False,
        ),
        now_utc=dt.datetime(2026, 6, 22, 6, 30, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]
    strategy = closure["cost_gate_escape_strategy"]

    assert top["status"] == "BOUNDED_DEMO_PROBE_OPERATOR_AUTHORIZATION_GATES_NOT_READY"
    assert top["required_next_gate"] == (
        "complete_bounded_probe_operator_authorization_blocking_gates"
    )
    assert top["evidence"]["bounded_probe_operator_authorization_status"] == (
        "AUTHORITY_PATH_PATCH_NOT_READY"
    )
    assert top["evidence"][
        "bounded_probe_operator_authorization_blocking_gates"
    ] == ["authority_path_patch_readiness_ready"]
    assert top["evidence"][
        "bounded_probe_operator_authorization_active_runtime_order_authority"
    ] is False
    assert closure["status"] == "BOUNDED_DEMO_PROBE_OPERATOR_AUTHORIZATION_GATES_NOT_READY"
    assert closure["cost_gate_root_blockers"][0]["source"] == (
        "bounded_probe_operator_authorization"
    )
    assert closure["cost_gate_root_blockers"][0]["gate"] == (
        "authority_path_patch_readiness_ready"
    )
    assert closure["profitability_next_move"]["move_class"] == (
        "complete_cost_gate_escape_source_gate"
    )
    assert closure["profitability_next_move"]["recommended_action"] == (
        "refresh_bounded_probe_operator_authorization_after_source_gates_pass"
    )
    assert closure["profitability_next_move"]["runtime_mutation_required"] is False
    assert "Rust authority-path near-touch Adapter readiness" in closure[
        "proof_gates_remaining"
    ][0]
    assert strategy["bounded_probe_operator_authorization_status"] == (
        "AUTHORITY_PATH_PATCH_NOT_READY"
    )
    assert strategy["bounded_probe_operator_authorization_ready_for_review"] is False
    assert strategy["bounded_probe_operator_authorization_object_emitted"] is False
    assert strategy[
        "bounded_probe_operator_authorization_active_runtime_order_authority"
    ] is False
    assert scorecard["answers"][
        "bounded_demo_probe_operator_authorization_present"
    ] is True
    assert scorecard["answers"][
        "bounded_demo_probe_operator_authorization_ready_for_review"
    ] is False
    assert scorecard["artifacts"]["bounded_probe_operator_authorization"]["present"] is True


def test_ready_operator_authorization_packet_does_not_grant_runtime_authority() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_operator_authorization=_bounded_probe_operator_authorization(),
        now_utc=dt.datetime(2026, 6, 22, 6, 30, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]
    strategy = closure["cost_gate_escape_strategy"]

    assert top["status"] == (
        "BOUNDED_DEMO_PROBE_OPERATOR_AUTHORIZATION_READY_FOR_OPERATOR_REVIEW"
    )
    assert closure["status"] == (
        "OPERATOR_CAN_AUTHORIZE_BOUNDED_DEMO_PROBE_WITH_EXACT_CONFIRM"
    )
    assert closure["proof_gate_count_remaining"] == 0
    assert strategy["bounded_probe_operator_authorization_ready_for_review"] is True
    assert strategy["bounded_probe_operator_authorization_object_emitted"] is False
    assert strategy["bounded_probe_operator_authorization_active_runtime_probe_authority"] is False
    assert strategy["bounded_probe_operator_authorization_active_runtime_order_authority"] is False
    assert scorecard["answers"][
        "bounded_demo_probe_operator_authorization_ready_for_review"
    ] is True
    assert scorecard["answers"][
        "bounded_demo_probe_operator_authorization_active_runtime_order_authority"
    ] is False
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert scorecard["answers"]["order_authority_granted"] is False


def test_bounded_probe_result_failure_stops_cost_gate_escape_path() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_result_review=_bounded_probe_result_review(
            "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
            completed=3,
            avg_net_bps=-1.2,
            net_positive_pct=33.3,
        ),
        now_utc=dt.datetime(2026, 6, 22, 7, tzinfo=dt.timezone.utc),
    )

    top = {row["path_id"]: row for row in scorecard["top_paths"]}[
        "horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"
    ]
    closure = scorecard["profitability_engineering_closure"]

    assert top["status"] == "BOUNDED_DEMO_PROBE_RESULT_FAILED_STOP"
    assert top["required_next_gate"] == (
        "keep_cost_gate_blocked_after_realized_probe_edge_failed"
    )
    assert top["evidence"]["bounded_probe_result_review_status"] == (
        "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
    )
    assert top["evidence"]["bounded_probe_result_review_avg_realized_net_bps"] == -1.2
    assert top["evidence"]["bounded_probe_result_review_stop_probe_recommended"] is True
    assert closure["status"] == "COST_GATE_ESCAPE_RESULT_REVIEW_FAILED_REALIZED_EDGE"
    assert "keep Cost Gate blocked" in closure["proof_gates_remaining"][0]
    assert scorecard["answers"]["bounded_demo_probe_result_review_stop_recommended"] is True
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert scorecard["answers"]["promotion_evidence"] is False
    assert scorecard["artifacts"]["bounded_probe_result_review"]["present"] is True


def test_shadow_placement_impact_updates_cost_gate_escape_closure() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_shadow_placement_impact=(
            _bounded_probe_shadow_placement_impact()
        ),
        now_utc=dt.datetime(2026, 6, 22, 7, tzinfo=dt.timezone.utc),
    )

    top = {row["path_id"]: row for row in scorecard["top_paths"]}[
        "horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"
    ]
    closure = scorecard["profitability_engineering_closure"]
    strategy = closure["cost_gate_escape_strategy"]

    assert top["status"] == (
        "BOUNDED_DEMO_PROBE_PLACEMENT_TOUCHABILITY_REPAIR_SAMPLE_MISMATCH"
    )
    assert top["required_next_gate"] == (
        "operator_reviews_mechanical_touchability_then_collect_candidate_matched_flow"
    )
    assert top["evidence"]["bounded_probe_shadow_placement_submit_count"] == 6
    assert top["evidence"][
        "bounded_probe_shadow_placement_candidate_matched_order_count"
    ] == 0
    assert top["evidence"]["bounded_probe_shadow_placement_max_gap_reduction_bps"] == (
        1522.1026
    )
    assert top["evidence"][
        "bounded_probe_shadow_placement_candidate_specific_alpha_proof"
    ] is False
    assert closure["status"] == (
        "BOUNDED_DEMO_PROBE_PLACEMENT_TOUCHABILITY_SAMPLE_MISMATCH"
    )
    assert "candidate-matched order-to-fill" in closure[
        "proof_gates_remaining"
    ][1]
    assert strategy["bounded_probe_shadow_placement_status"] == (
        "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH"
    )
    assert strategy["bounded_probe_shadow_placement_improves_touchability"] is True
    assert strategy[
        "bounded_probe_shadow_placement_candidate_specific_alpha_proof"
    ] is False
    assert scorecard["answers"][
        "bounded_demo_probe_shadow_placement_improves_touchability"
    ] is True
    assert scorecard["answers"][
        "bounded_demo_probe_shadow_placement_candidate_specific_alpha_proof"
    ] is False
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert scorecard["artifacts"]["bounded_probe_shadow_placement_impact"][
        "present"
    ] is True


def test_bounded_probe_learning_review_requires_operator_without_promotion() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_result_review=_bounded_probe_result_review(),
        now_utc=dt.datetime(2026, 6, 22, 7, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]

    assert top["status"] == (
        "BOUNDED_DEMO_PROBE_LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED"
    )
    assert top["priority_rank"] == 1
    assert top["evidence"]["bounded_probe_result_review_completed_probe_outcome_count"] == 10
    assert top["evidence"]["bounded_probe_result_review_learning_review_candidate"] is True
    assert top["evidence"]["bounded_probe_result_review_evidence_quality_status"] == (
        "LEARNING_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
    )
    assert top["evidence"]["bounded_probe_result_review_matched_control_outcome_count"] == 10
    assert closure["status"] == "BOUNDED_DEMO_PROBE_LEARNING_REVIEW_OPERATOR_REQUIRED"
    assert closure["cost_gate_escape_strategy"][
        "bounded_probe_result_review_learning_review_candidate"
    ] is True
    assert scorecard["answers"][
        "bounded_demo_probe_result_learning_review_candidate"
    ] is True
    assert scorecard["answers"]["order_authority_granted"] is False
    assert top["promotion_evidence"] is False


def test_positive_probe_result_without_control_requires_matched_control_evidence() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_result_review=_bounded_probe_result_review(
            "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            completed=3,
            avg_net_bps=2.0,
            net_positive_pct=100.0,
            evidence_quality_status="CONTROL_COMPARISON_MISSING",
            matched_control_count=0,
        ),
        now_utc=dt.datetime(2026, 6, 22, 7, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]

    assert top["status"] == "BOUNDED_DEMO_PROBE_CONTROL_COMPARISON_REQUIRED"
    assert top["required_next_gate"] == (
        "record_matched_blocked_signal_control_outcomes_before_operator_gate_review"
    )
    assert top["evidence"]["bounded_probe_result_review_anecdote_risk"] is True
    assert closure["status"] == "BOUNDED_DEMO_PROBE_CONTROL_COMPARISON_REQUIRED"
    assert "matched blocked-signal control" in closure["proof_gates_remaining"][0]


def test_positive_probe_result_under_captures_control_requires_execution_review() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_result_review=_bounded_probe_result_review(
            "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            completed=3,
            avg_net_bps=2.0,
            net_positive_pct=100.0,
            evidence_quality_status=(
                "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
            ),
            matched_control_count=3,
            matched_control_avg_net_bps=3.0,
        ),
        now_utc=dt.datetime(2026, 6, 22, 7, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]
    strategy = closure["cost_gate_escape_strategy"]

    assert top["status"] == "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_REQUIRED"
    assert top["required_next_gate"] == (
        "generate_bounded_probe_execution_realism_review_before_cost_gate_or_operator_review"
    )
    assert top["next_action"] == (
        "refresh_bounded_probe_execution_realism_review"
    )
    assert top["evidence"]["bounded_probe_result_review_probe_edge_capture_ratio"] == 0.6667
    assert top["evidence"]["bounded_probe_result_review_probe_execution_gap_bps"] == 1.0
    assert top["evidence"]["bounded_probe_result_review_execution_realism_gap"] is True
    assert top["evidence"]["bounded_probe_execution_realism_review_present"] is False
    assert closure["status"] == "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_REQUIRED"
    assert "execution-realism review" in closure["proof_gates_remaining"][0]
    assert strategy["bounded_probe_result_review_execution_realism_gap"] is True
    assert strategy["bounded_probe_result_review_probe_execution_gap_bps"] == 1.0
    assert strategy["bounded_probe_execution_realism_review_status"] is None


def test_positive_probe_under_capture_with_execution_review_requires_repair() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
            "next_actions": [
                "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
            ],
            "answers": {
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "EVIDENCE_STACK_ACTIVE"},
        },
        activation_preflight={"status": "EVIDENCE_STACK_ACTIVE"},
        horizon_sealed_replay=_sealed_horizon_replay(),
        horizon_learning_evidence=_sealed_horizon_learning_evidence(),
        sealed_horizon_probe_preflight=_sealed_horizon_probe_preflight(
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ),
        bounded_probe_result_review=_bounded_probe_result_review(
            "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            completed=3,
            avg_net_bps=2.0,
            net_positive_pct=100.0,
            evidence_quality_status=(
                "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
            ),
            matched_control_count=3,
            matched_control_avg_net_bps=3.0,
        ),
        bounded_probe_execution_realism_review=(
            _bounded_probe_execution_realism_review()
        ),
        now_utc=dt.datetime(2026, 6, 22, 7, tzinfo=dt.timezone.utc),
    )

    top = scorecard["top_paths"][0]
    closure = scorecard["profitability_engineering_closure"]
    strategy = closure["cost_gate_escape_strategy"]

    assert top["status"] == "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REPAIR_REQUIRED"
    assert top["required_next_gate"] == (
        "repair_or_replay_bounded_probe_execution_realism_gap_before_cost_gate_review"
    )
    assert top["next_action"] == (
        "record_fill_backed_probe_execution_rows_or_l1_replay_before_cost_gate_review"
    )
    assert top["evidence"][
        "bounded_probe_execution_realism_review_primary_hypothesis"
    ] == "fill_backed_execution_missing"
    assert top["evidence"]["bounded_probe_execution_realism_review_net_capture_gap_bps"] == 1.0
    assert top["evidence"]["bounded_probe_execution_realism_review_probe_fill_backed_pct"] == 0.0
    assert top["evidence"][
        "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed"
    ] is False
    assert closure["status"] == "BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REPAIR_REQUIRED"
    assert "repair bounded demo probe execution-realism gap" in closure[
        "proof_gates_remaining"
    ][0]
    assert strategy["bounded_probe_execution_realism_review_status"] == (
        "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
    )
    assert strategy["bounded_probe_execution_realism_review_primary_hypothesis"] == (
        "fill_backed_execution_missing"
    )
    assert scorecard["answers"][
        "bounded_demo_probe_execution_realism_repair_required"
    ] is True
    assert scorecard["artifacts"]["bounded_probe_execution_realism_review"][
        "present"
    ] is True


def test_mm_fee_polymarket_and_gate_b_paths_are_separated() -> None:
    scorecard = build_profitability_path_scorecard(
        fillsim={
            "generated_at": "2026-06-22T03:00:00+00:00",
            "low_friction_signal_scorecard": {
                "status": "LOW_FRICTION_SIGNAL_TRAIN_ONLY_CURRENT_FEE",
                "current_fee_round_trip_bps": 4.0,
                "train_confirmed_gross_scorecard": {
                    "status": "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE",
                    "current_fee_round_trip_bps": 4.0,
                    "best_train_confirmed_gross_candidate": {
                        "name": "quoted_half_spread_bps_train_p90",
                        "train_edge_before_fees_bps": 4.416,
                        "holdout_edge_before_fees_bps": 2.269,
                        "min_train_holdout_gross_bps": 2.269,
                        "gap_to_current_fee_round_trip_bps": 1.731,
                        "train_n_fill_only": 69,
                        "holdout_n_fill_only": 74,
                    },
                },
            },
            "maker_fee_sensitivity_scorecard": {
                "status": "LOWER_FEE_SAMPLE_GATED_POSITIVE",
                "current_fee_round_trip_bps": 4.0,
                "best_sample_gated_break_even_cell": {
                    "key": "edge_scorecard|ADAUSDT",
                    "edge_before_fees_bps": 1.632,
                    "n_fill_only": 1521,
                    "break_even_maker_fee_bps_per_side": 0.816,
                },
            },
        },
        fillsim_history={
            "status": "HISTORY_INSUFFICIENT_WINDOWS",
            "reason": "below_min_windows_or_dates",
            "valid_windows": 4,
            "distinct_window_dates": ["2026-06-20", "2026-06-21"],
            "lower_fee_break_even_stability": {
                "status": "LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT",
                "reason": "repeated_key_but_distinct_dates_below_min",
                "current_maker_fee_bps_per_side": 2.0,
                "best_repeated_lower_fee_break_even_key": {
                    "key": "edge_scorecard|ADAUSDT",
                    "windows": 3,
                    "best_cell": {
                        "key": "edge_scorecard|ADAUSDT",
                        "edge_before_fees_bps": 2.048,
                        "n_fill_only": 850,
                        "break_even_maker_fee_bps_per_side": 1.024,
                        "fee_reduction_to_breakeven_bps_per_side": 0.976,
                    },
                },
            },
        },
        polymarket_leadlag={
            "schema_version": "polymarket.leadlag_report.v0.15",
            "verdict": {"status": "IC_CANDIDATE_REVIEW_REQUIRED", "candidate_count": 3},
            "candidate_replay_scorecard": {
                "status": "PAPER_REPLAY_BUILT",
                "round_trip_cost_bps": 4.0,
                "selected_candidate_key": "polymarket_leadlag_ic|event_reg|BTCUSDT|15m",
                "candidate_count": 3,
                "selected_summary": {
                    "candidate_key": "polymarket_leadlag_ic|event_reg|BTCUSDT|15m",
                    "gross_bps_mean": 1.4647,
                    "net_bps_mean": -2.5353,
                    "holdout_net_bps_mean": -1.0761,
                    "sample_count": 116,
                    "n_days": 3,
                    "horizon_minutes": 15,
                    "execution_realism_status": "UNMEASURED",
                },
            },
        },
        gate_b_watch={
            "schema_version": 1,
            "status": "WATCH_ONLY",
            "candidate_counts": {
                "total": 21,
                "watch_only": 1,
                "alertable": 0,
                "start_now": 0,
                "schedule": 0,
            },
        },
        now_utc=dt.datetime(2026, 6, 22, 3, tzinfo=dt.timezone.utc),
    )

    by_class = {row["class"]: row for row in scorecard["top_paths"]}
    assert by_class["low_friction_mm_alpha_search"]["status"] == (
        "LOW_FRICTION_MM_GROSS_EDGE_BELOW_CURRENT_FEE"
    )
    assert by_class["low_friction_mm_alpha_search"]["current_edge_bps"] == 2.269
    assert by_class["fee_or_scale"]["status"] == "FEE_OR_SCALE_PATH_NOT_SHORT_TERM_ALPHA"
    assert by_class["external_event_leadlag_alpha"]["status"] == (
        "POLYMARKET_ALPHA_GROSS_BELOW_COST_OR_EXECUTION_UNMEASURED"
    )
    assert by_class["event_driven_listing_fade"]["status"] == "EVENT_WAIT_NO_ACTIONABLE_WINDOW"
    assert scorecard["answers"]["profitability_proven"] is False
    assert scorecard["answers"]["alpha_or_edge_amplification_paths_present"] is True

    markdown = render_markdown(scorecard)
    assert "Profitability Path Scorecard" in markdown
    assert "mm_low_friction_signal_search" in markdown
    assert "Profitability Next Move" in markdown
    assert "Edge Amplification Backlog" in markdown
