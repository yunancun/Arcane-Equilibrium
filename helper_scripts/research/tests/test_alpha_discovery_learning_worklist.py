"""Focused tests for alpha discovery learning worklist."""

from __future__ import annotations

import datetime as dt

from alpha_discovery_throughput.discovery_loop import build_discovery_plan
from alpha_discovery_throughput.learning_worklist import build_learning_worklist


def test_learning_worklist_prioritizes_runtime_reconcile_over_mm_signal_search():
    plan = build_discovery_plan([
        {
            "arm_id": "cost_gate_demo_learning_lane",
            "gate_status": "OPERATOR_REVIEW",
            "sample_count": 0,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "learning_lane_source_activation_ready": False,
                "learning_lane_source_activation_status": "DIRTY_PATH_REVIEW_REQUIRED",
                "learning_lane_git_status": "DIRTY",
                "learning_lane_git_behind_count": 5,
                "learning_lane_git_dirty_path_count": 12,
                "demo_learning_evidence_status": (
                    "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING"
                ),
            },
        },
        {
            "arm_id": "mm_verdict_maker_edge",
            "gate_status": "CAPTURING",
            "sample_count": 42,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "walk_forward_failure_summary": {
                    "status": "NO_TRAIN_POSITIVE_CELL",
                    "candidate_count": 51,
                },
                "sample_gated_cost_wall_summary": {
                    "available": True,
                    "status": "SAMPLE_GATED_CURRENT_FEE_COST_WALL",
                    "current_fee_round_trip_bps": 4.0,
                    "best_sample_gated_net_bps": -1.8,
                    "best_sample_gated_fee_round_trip_shortfall_bps": 1.8,
                    "break_even_maker_fee_bps_per_side": 1.1,
                },
                "gross_edge_cost_decomposition": {
                    "available": True,
                    "status": "GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL",
                    "current_fee_positive_sample_gated_cell_count": 0,
                    "best_sample_gated_gross_edge_bps": 2.2,
                    "best_gross_cell_net_bps": -1.8,
                    "current_fee_round_trip_bps": 4.0,
                },
                "fee_path_feasibility": {
                    "status": "STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED",
                    "business_path_actionability": {
                        "status": "STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED",
                    },
                },
                "low_friction_signal_scorecard": {
                    "failure_summary": {
                        "sample_starved_current_fee_holdout_count": 3,
                        "sample_gated_holdout_gross_count": 5,
                        "best_sample_starved_current_fee_holdout_candidate": {
                            "name": "n1_holdout_spike",
                            "holdout_edge_before_fees_bps": 6.7,
                            "holdout_n_fill_only": 1,
                        },
                        "best_sample_gated_holdout_gross_candidate": {
                            "name": "sample_gated_below_fee",
                            "holdout_edge_before_fees_bps": 1.4,
                            "holdout_n_fill_only": 44,
                        },
                    },
                    "train_confirmed_gross_scorecard": {
                        "status": "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE",
                        "best_min_train_holdout_gross_bps": 0.8,
                        "gap_to_current_fee_round_trip_bps": 3.2,
                    },
                },
                "history_scorecard": {
                    "low_friction_near_miss_stability": {
                        "status": (
                            "LOW_FRICTION_NEAR_MISS_REPEATS_BUT_DATE_INSUFFICIENT"
                        ),
                        "reason": "repeated_key_but_distinct_dates_below_min",
                        "sample_gated_near_miss_windows": 2,
                        "repeated_key_count": 1,
                        "best_repeated_near_miss_key": {
                            "key": (
                                "low_friction_signal_scorecard_holdout_near_miss|"
                                "sample_gated_below_fee"
                            ),
                            "windows": 2,
                        },
                    },
                    "low_friction_near_miss_motif_stability": {
                        "status": (
                            "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
                        ),
                        "reason": "repeated_motif_but_distinct_dates_below_min",
                        "repeated_motif_count": 1,
                        "best_repeated_near_miss_motif": {
                            "motif_key": "low_friction_motif|spread_combo",
                            "windows": 2,
                        },
                    },
                },
            },
        },
    ], now_utc=dt.datetime(2026, 6, 22, tzinfo=dt.timezone.utc))

    worklist = plan["learning_worklist"]
    assert worklist["schema_version"] == "alpha_learning_worklist_v6"
    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert worklist["task_count"] == 2
    assert worklist["operator_required_count"] == 1
    assert worklist["runtime_mutation_required_count"] == 1

    top = worklist["top_task"]
    assert top["arm_id"] == "cost_gate_demo_learning_lane"
    assert top["task_type"] == "runtime_source_reconcile"
    assert top["requires_operator_authorization"] is True
    assert top["runtime_mutation_required"] is True
    assert top["learning_objective"] == (
        "reconcile_runtime_source_before_learning_activation_or_probe_trust"
    )
    assert top["completion_gate"] == "runtime_source_synced_clean_expected_head_match"
    assert top["completion_status"] == "PENDING_EVIDENCE"
    assert "runtime_source.source_activation_status == SYNCED_CLEAN" in (
        top["completion_evidence_required"]
    )
    assert top["evidence"]["learning_lane_git_behind_count"] == 5

    tasks = {row["arm_id"]: row for row in worklist["tasks"]}
    mm_task = tasks["mm_verdict_maker_edge"]
    assert mm_task["task_type"] == "mm_signal_search"
    assert mm_task["requires_operator_authorization"] is False
    assert mm_task["actionability"] == "engineering_actionable"
    assert mm_task["learning_objective"] == (
        "find_or_amplify_train_confirmed_low_friction_mm_signal_that_clears_"
        "current_fee"
    )
    assert mm_task["completion_gate"] == (
        "train_confirmed_sample_gated_current_fee_gross_edge_found"
    )
    assert (
        "train and holdout sample-gated gross edge clear current fee round trip"
        in mm_task["completion_evidence_required"]
    )
    assert mm_task["evidence"]["gross_edge_gap_to_current_fee_bps"] == 1.8
    assert mm_task["evidence"]["required_current_fee_gross_edge_bps"] == 4.0
    assert mm_task["evidence"]["mm_signal_search_status"] == (
        "SEARCH_REQUIRED_EDGE_UPLIFT"
    )
    assert mm_task["evidence"]["mm_signal_search_failure_mode"] == (
        "current_fee_cost_wall_train_confirmed_low_friction_gross_below_fee_"
        "lower_fee_path_scale_or_capital_gated"
    )
    assert mm_task["evidence"]["failure_mode"] == (
        "current_fee_cost_wall_train_confirmed_low_friction_gross_below_fee_"
        "lower_fee_path_scale_or_capital_gated"
    )
    assert mm_task["evidence"]["status_reason"] == (
        "missing_low_friction_holdout_gross_candidate"
    )
    assert mm_task["evidence"]["mm_signal_search_required_gross_uplift_multiple"] == (
        1.8182
    )
    assert (
        mm_task["evidence"]["mm_signal_search_sample_starved_current_fee_holdout_count"]
        == 3
    )
    assert (
        mm_task["evidence"][
            "mm_signal_search_best_sample_starved_current_fee_holdout_candidate"
        ]["name"]
        == "n1_holdout_spike"
    )
    assert mm_task["evidence"]["mm_signal_search_sample_gated_holdout_gross_count"] == 5
    assert (
        mm_task["evidence"]["mm_signal_search_best_sample_gated_holdout_gross_candidate"][
            "name"
        ]
        == "sample_gated_below_fee"
    )
    assert mm_task["evidence"][
        "mm_signal_search_history_low_friction_near_miss_stability_status"
    ] == "LOW_FRICTION_NEAR_MISS_REPEATS_BUT_DATE_INSUFFICIENT"
    assert mm_task["evidence"][
        "mm_signal_search_history_low_friction_near_miss_repeated_key_count"
    ] == 1
    assert mm_task["evidence"][
        "mm_signal_search_history_low_friction_near_miss_motif_stability_status"
    ] == "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
    assert (
        mm_task["evidence"][
            "mm_signal_search_history_low_friction_near_miss_best_repeated_motif"
        ]["motif_key"]
        == "low_friction_motif|spread_combo"
    )
    assert mm_task["evidence"]["mm_signal_search_history_guided_search_constraint"] == (
        "prioritize_repeated_low_friction_near_miss_motif_then_require_"
        "distinct_date_train_holdout_confirmation"
    )
    assert (
        mm_task["evidence"]["mm_signal_search_lower_fee_path_not_actionable_now"]
        is True
    )
    assert mm_task["evidence"]["mm_signal_search_recommended_search_constraint"] == (
        "require_train_and_holdout_sample_gated_min_gross_ge_current_fee_round_trip"
    )


def test_learning_worklist_keeps_promotion_review_ahead_of_replay_history():
    worklist = build_learning_worklist({
        "arms": [
            {
                "arm_id": "polymarket_leadlag_ic",
                "blocker_class": "sample_gate",
                "primary_blocker": "polymarket_candidate_replay_history_not_ready",
                "next_trigger": (
                    "collect_more_dated_polymarket_replay_history_before_promotion"
                ),
                "sample_count": 35,
                "min_samples": 30,
                "engineering_actionable": True,
                "candidate_replay_history_status": (
                    "REPLAY_HISTORY_DAYS_INSUFFICIENT"
                ),
                "candidate_replay_history_n_days": 2,
                "candidate_replay_history_min_days": 30,
            },
            {
                "arm_id": "funding_oi",
                "blocker_class": "candidate_review_ready",
                "primary_blocker": "candidate_artifacts_ready_need_aeg_chain",
                "next_trigger": "run_AEG_MIT_QC_chain_before_any_promotion",
                "promotion_ready": True,
                "engineering_actionable": True,
            },
        ],
    })

    assert worklist["status"] == "PROMOTION_REVIEW_READY"
    assert worklist["promotion_ready_count"] == 1
    assert worklist["top_task"]["arm_id"] == "funding_oi"
    assert worklist["top_task"]["task_type"] == "promotion_review"
    assert worklist["top_task"]["completion_gate"] == (
        "formal_aeg_qc_mit_review_verdict_recorded"
    )
    assert "formal_AEG_QC_MIT_review_artifact_exists" in (
        worklist["top_task"]["completion_evidence_required"]
    )

    tasks = {row["arm_id"]: row for row in worklist["tasks"]}
    poly = tasks["polymarket_leadlag_ic"]
    assert poly["task_type"] == "polymarket_replay_history"
    assert poly["actionability"] == "engineering_actionable"
    assert poly["completion_gate"] == "dated_replay_history_ready_for_aeg_recheck"
    assert (
        "candidate_replay_history_status == REPLAY_HISTORY_READY_FOR_AEG_RECHECK"
        in poly["completion_evidence_required"]
    )
    assert poly["evidence"]["candidate_replay_history_n_days"] == 2
    assert poly["evidence"]["candidate_replay_history_min_days"] == 30


def test_learning_worklist_carries_ranked_cost_gate_blocked_review_evidence():
    worklist = build_learning_worklist({
        "arms": [
            {
                "arm_id": "cost_gate_demo_learning_lane",
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "cost_gate_blocked_signal_outcomes_need_demo_probe_authority_review"
                ),
                "next_trigger": (
                    "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
                ),
                "operator_actionable": True,
                "engineering_actionable": True,
                "ledger_status": "BLOCKED_SIGNAL_OUTCOMES_PRESENT",
                "blocked_signal_outcome_review_schema_version": (
                    "cost_gate_demo_learning_lane_blocked_outcome_review_v2"
                ),
                "blocked_signal_outcome_review_status": (
                    "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
                ),
                "blocked_signal_outcome_count": 3,
                "blocked_signal_positive_outcome_count": 2,
                "blocked_signal_net_positive_pct": 66.666667,
                "blocked_signal_top_review_candidate_side_cell_key": (
                    "ma_crossover|ETHUSDT|Sell"
                ),
                "blocked_signal_top_review_candidate_wrongful_block_score": 3.444444,
                "blocked_signal_top_review_candidate_net_cost_cushion_bps": 5.166667,
                "blocked_signal_top_review_side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "blocked_signal_top_review_wrongful_block_score": 3.444444,
                "blocked_signal_top_review_net_cost_cushion_bps": 5.166667,
                "learning_loop_last_scorecard_horizon_stability_status": (
                    "SINGLE_HORIZON_ONLY"
                ),
                "learning_loop_last_scorecard_horizon_stability_horizons": [
                    60,
                ],
                "profit_learning_counterfactual_horizon_stability_status": (
                    "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
                ),
                "profit_learning_top_side_cells": [
                    {
                        "candidate_key": "ma_crossover|ETHUSDT|Sell",
                        "horizon_status": "CANDIDATE_MULTI_HORIZON_STABLE",
                        "candidate_horizons_minutes": [15, 30, 60, 120, 240],
                        "best_horizon_minutes": 120,
                    }
                ],
                "sealed_horizon_probe_preflight_status": "OPERATOR_REVIEW_REQUIRED",
            }
        ],
    })

    task = worklist["top_task"]

    assert worklist["schema_version"] == "alpha_learning_worklist_v6"
    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert task["task_type"] == "operator_probe_review"
    assert task["learning_objective"] == (
        "operator_review_multi_horizon_blocked_signal_side_cell_before_bounded_demo_probe"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is False
    assert task["evidence"]["blocked_signal_outcome_review_schema_version"] == (
        "cost_gate_demo_learning_lane_blocked_outcome_review_v2"
    )
    assert task["evidence"]["blocked_signal_top_review_candidate_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert task["evidence"]["blocked_signal_top_review_candidate_wrongful_block_score"] == (
        3.444444
    )
    assert task["evidence"]["blocked_signal_top_review_candidate_net_cost_cushion_bps"] == (
        5.166667
    )
    assert task["evidence"][
        "learning_loop_last_scorecard_horizon_stability_status"
    ] == "SINGLE_HORIZON_ONLY"
    assert task["evidence"][
        "profit_learning_counterfactual_horizon_stability_status"
    ] == "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
    assert task["evidence"]["profit_learning_top_side_cells"][0][
        "candidate_horizons_minutes"
    ] == [15, 30, 60, 120, 240]
    assert (
        "candidate_specific_side_cell_or_candidate_key_evidence_present"
        in task["completion_evidence_required"]
    )
    assert (
        "horizon_stability_status_and_candidate_horizons_recorded_when_available"
        in task["completion_evidence_required"]
    )


def test_learning_worklist_uses_sealed_horizon_review_objective():
    worklist = build_learning_worklist({
        "arms": [
            {
                "arm_id": "cost_gate_demo_learning_lane",
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "profit_learning_sealed_horizon_demo_probe_candidate_needs_operator_review"
                ),
                "next_trigger": (
                    "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
                ),
                "operator_actionable": True,
                "engineering_actionable": True,
                "profit_learning_decision_packet_status": (
                    "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE"
                ),
                "profit_learning_sealed_horizon_learning_evidence_candidates_present": True,
                "profit_learning_sealed_horizon_learning_evidence_status": (
                    "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
                ),
                "profit_learning_sealed_horizon_side_cell_key": (
                    "ma_crossover|BTCUSDT|Sell"
                ),
                "profit_learning_sealed_horizon_source_kind": (
                    "horizon_specific_sealed_replay"
                ),
                "profit_learning_sealed_horizon_outcome_horizon_minutes": 240,
                "profit_learning_sealed_horizon_blocked_signal_outcome_count": 16515,
                "profit_learning_sealed_horizon_avg_net_bps": 3.0511,
                "profit_learning_sealed_horizon_net_positive_pct": 68.5619,
                "profit_learning_sealed_horizon_review_ready": True,
                "profit_learning_order_authority_granted": False,
                "profit_learning_main_cost_gate_adjustment": "NONE",
            }
        ],
    })

    task = worklist["top_task"]

    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert task["task_type"] == "operator_probe_review"
    assert task["learning_objective"] == (
        "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is False
    assert "sealed_horizon_learning_evidence_review_ready_or_blocked_review_candidate_present" in (
        task["completion_evidence_required"]
    )
    assert task["evidence"]["profit_learning_sealed_horizon_side_cell_key"] == (
        "ma_crossover|BTCUSDT|Sell"
    )
    assert task["evidence"]["profit_learning_sealed_horizon_outcome_horizon_minutes"] == 240
    assert task["evidence"]["profit_learning_sealed_horizon_avg_net_bps"] == 3.0511
    assert task["evidence"]["profit_learning_order_authority_granted"] is False
    assert task["evidence"]["profit_learning_main_cost_gate_adjustment"] == "NONE"


def test_learning_worklist_carries_demo_learning_stack_health_evidence():
    worklist = build_learning_worklist({
        "arms": [
            {
                "arm_id": "cost_gate_demo_learning_lane",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_not_installed",
                "next_trigger": "install_stack_after_operator_source_reconcile",
                "engineering_actionable": True,
                "ledger_status": "MISSING",
                "demo_learning_stack_healthcheck_status": "NOT_INSTALLED",
                "demo_learning_stack_healthcheck_reason": (
                    "one_or_both_demo_learning_stack_crons_missing"
                ),
                "demo_learning_stack_healthcheck_next_action": (
                    "install_stack_after_operator_source_reconcile"
                ),
                "demo_learning_stack_healthcheck_ts_utc": "2026-06-21T18:04:00Z",
                "demo_learning_stack_healthcheck_source_ok": True,
                "demo_learning_stack_source_ready": True,
                "demo_learning_stack_stack_installed": False,
                "demo_learning_stack_demo_learning_evidence_cron_entry_present": False,
                "demo_learning_stack_sealed_horizon_probe_preflight_cron_entry_present": False,
                "demo_learning_stack_cost_gate_learning_lane_cron_entry_present": False,
                "demo_learning_stack_healthcheck_cron_entry_present": False,
                "demo_learning_stack_heartbeats_recent": False,
                "demo_learning_stack_demo_learning_evidence_heartbeat_recent": False,
                "demo_learning_stack_sealed_horizon_probe_preflight_heartbeat_recent": False,
                "demo_learning_stack_cost_gate_learning_lane_heartbeat_recent": False,
                "demo_learning_stack_statuses_recent": False,
                "demo_learning_stack_demo_learning_evidence_status_recent": False,
                "demo_learning_stack_sealed_horizon_probe_preflight_status_recent": False,
                "demo_learning_stack_cost_gate_learning_lane_status_recent": False,
                "demo_learning_stack_latest_artifacts_present": False,
                "demo_learning_stack_cost_gate_learning_ledger_rows_present": False,
                "demo_learning_stack_blocked_signal_outcomes_present": False,
                "demo_learning_stack_blocked_outcome_review_present": False,
            }
        ],
    })

    task = worklist["top_task"]

    assert worklist["schema_version"] == "alpha_learning_worklist_v6"
    assert task["task_type"] == "cost_gate_learning_activation"
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is True
    assert task["actionability"] == "operator_required"
    assert task["completion_gate"] == (
        "learning_lane_ledger_and_blocked_outcomes_accumulating"
    )
    assert (
        "demo_learning_stack_healthcheck_status == EVIDENCE_STACK_ACTIVE"
        in task["completion_evidence_required"]
    )
    assert task["evidence"]["demo_learning_stack_healthcheck_status"] == (
        "NOT_INSTALLED"
    )
    assert task["evidence"]["demo_learning_stack_stack_installed"] is False
    assert (
        task["evidence"][
            "demo_learning_stack_sealed_horizon_probe_preflight_cron_entry_present"
        ]
        is False
    )
    assert task["evidence"][
        "demo_learning_stack_cost_gate_learning_ledger_rows_present"
    ] is False


def test_learning_worklist_carries_demo_learning_stack_activation_packet_evidence():
    worklist = build_learning_worklist({
        "arms": [
            {
                "arm_id": "cost_gate_demo_learning_lane",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_activation_packet_ready_for_operator_dry_run"
                ),
                "next_trigger": (
                    "run_dry_run_preview_then_apply_only_if_installer_preflight_passes"
                ),
                "engineering_actionable": True,
                "demo_learning_stack_activation_packet_present": True,
                "demo_learning_stack_activation_packet_status": (
                    "READY_FOR_OPERATOR_DRY_RUN"
                ),
                "demo_learning_stack_activation_packet_reason": (
                    "source_ready_but_one_or_more_stack_crons_missing"
                ),
                "demo_learning_stack_activation_packet_operator_next_action": (
                    "run_dry_run_preview_then_apply_only_if_installer_preflight_passes"
                ),
                "demo_learning_stack_activation_packet_install_review_ready": True,
                "demo_learning_stack_activation_packet_missing_cron_count": 4,
                "demo_learning_stack_activation_packet_missing_crons": [
                    "demo_learning_evidence",
                    "sealed_horizon_probe_preflight",
                    "cost_gate_learning_lane",
                    "demo_learning_stack_healthcheck",
                ],
                "demo_learning_stack_activation_packet_global_cost_gate_lowering_recommended": False,
                "demo_learning_stack_activation_packet_order_authority_granted": False,
                "demo_learning_stack_activation_packet_probe_authority_granted": False,
                "demo_learning_stack_activation_packet_dry_run_preview_shell": (
                    "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 install_stack"
                ),
                "demo_learning_stack_activation_packet_edge_amplification_levers": [
                    "side_cell_filtering",
                    "horizon_retiming",
                    "low_friction_execution_filtering",
                ],
            }
        ],
    })

    task = worklist["top_task"]

    assert worklist["schema_version"] == "alpha_learning_worklist_v6"
    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert task["task_type"] == "cost_gate_learning_activation"
    assert task["learning_objective"] == (
        "review_demo_learning_stack_activation_packet_and_run_dry_run_"
        "before_any_cron_install"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is True
    assert task["actionability"] == "operator_required"
    assert "dry-run preview is captured before any operator apply" in (
        task["completion_evidence_required"]
    )
    assert task["evidence"]["demo_learning_stack_activation_packet_status"] == (
        "READY_FOR_OPERATOR_DRY_RUN"
    )
    assert task["evidence"][
        "demo_learning_stack_activation_packet_missing_cron_count"
    ] == 4
    assert task["evidence"][
        "demo_learning_stack_activation_packet_global_cost_gate_lowering_recommended"
    ] is False
    assert task["evidence"][
        "demo_learning_stack_activation_packet_order_authority_granted"
    ] is False
    assert task["evidence"][
        "demo_learning_stack_activation_packet_probe_authority_granted"
    ] is False


def test_learning_worklist_carries_demo_learning_stack_dry_run_review_evidence():
    worklist = build_learning_worklist({
        "arms": [
            {
                "arm_id": "cost_gate_demo_learning_lane",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_dry_run_preview_passed_operator_apply_review_required"
                ),
                "next_trigger": (
                    "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
                ),
                "operator_actionable": True,
                "engineering_actionable": True,
                "demo_learning_stack_dry_run_review_present": True,
                "demo_learning_stack_dry_run_review_status": (
                    "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
                ),
                "demo_learning_stack_dry_run_review_reason": (
                    "installer_dry_run_preview_passed_without_crontab_mutation"
                ),
                "demo_learning_stack_dry_run_review_operator_next_action": (
                    "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
                ),
                "demo_learning_stack_dry_run_review_expected_head": "abc1234",
                "demo_learning_stack_dry_run_review_activation_packet_status": (
                    "READY_FOR_OPERATOR_DRY_RUN"
                ),
                "demo_learning_stack_dry_run_review_dry_run_preview_executed": True,
                "demo_learning_stack_dry_run_review_dry_run_preview_passed": True,
                "demo_learning_stack_dry_run_review_crontab_mutated": False,
                "demo_learning_stack_dry_run_review_operator_apply_required": True,
                "demo_learning_stack_dry_run_review_global_cost_gate_lowering_recommended": False,
                "demo_learning_stack_dry_run_review_order_authority_granted": False,
                "demo_learning_stack_dry_run_review_probe_authority_granted": False,
                "demo_learning_stack_dry_run_review_forced_apply_gate": "0",
                "demo_learning_stack_dry_run_review_preinstall_refresh": "0",
                "demo_learning_stack_dry_run_review_mutates_crontab": False,
                "demo_learning_stack_dry_run_review_dry_run_preview_shell": (
                    "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 install_stack"
                ),
                "demo_learning_stack_dry_run_review_operator_only_apply_shell": (
                    "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack"
                ),
            }
        ],
    })

    task = worklist["top_task"]

    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert task["task_type"] == "cost_gate_learning_activation"
    assert task["learning_objective"] == (
        "operator_review_learning_stack_dry_run_preview_before_cron_apply"
    )
    assert task["next_trigger"] == (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is True
    assert task["actionability"] == "operator_required"
    assert task["evidence"]["demo_learning_stack_dry_run_review_status"] == (
        "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
    )
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_dry_run_preview_passed"
    ] is True
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_operator_apply_required"
    ] is True
    assert task["evidence"]["demo_learning_stack_dry_run_review_forced_apply_gate"] == "0"
    assert task["evidence"]["demo_learning_stack_dry_run_review_mutates_crontab"] is False
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_global_cost_gate_lowering_recommended"
    ] is False
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_order_authority_granted"
    ] is False
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_probe_authority_granted"
    ] is False


def test_learning_worklist_promotes_profitability_runtime_mutation_next_move():
    worklist = build_learning_worklist({
        "arms": [
            {
                "arm_id": "aeg_robustness_matrix",
                "blocker_class": "robustness_wait",
                "primary_blocker": "aeg_matrix_review_no_durable_candidate_rows",
                "engineering_actionable": True,
                "sample_count": 0,
                "min_samples": 30,
            },
            {
                "arm_id": "cost_gate_demo_learning_lane",
                "blocker_class": "data_coverage",
                "primary_blocker": "profitability_execution_evidence_missing",
                "next_trigger": "continue_data_capture",
                "engineering_actionable": True,
                "profitability_engineering_closure_status": (
                    "DEMO_LEARNING_STACK_ACTIVATION_REQUIRED"
                ),
                "profitability_next_move_class": (
                    "activate_sustainable_demo_learning_stack"
                ),
                "profitability_next_move_recommended_action": (
                    "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
                ),
                "profitability_next_move_runtime_mutation_required": True,
                "profitability_primary_cost_gate_root_blocker": {
                    "gate": "demo_learning_stack_operator_apply_required",
                    "runtime_mutation_required": True,
                },
                "demo_learning_stack_dry_run_review_status": (
                    "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
                ),
                "demo_learning_stack_dry_run_review_operator_apply_required": True,
                "demo_learning_stack_dry_run_review_crontab_mutated": False,
            },
        ],
    })

    top = worklist["top_task"]

    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert worklist["runtime_mutation_required_count"] == 1
    assert top["arm_id"] == "cost_gate_demo_learning_lane"
    assert top["task_type"] == "cost_gate_learning_activation"
    assert top["learning_objective"] == (
        "operator_review_learning_stack_dry_run_preview_before_cron_apply"
    )
    assert top["primary_blocker"] == "demo_learning_stack_operator_apply_required"
    assert top["next_trigger"] == (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    assert top["requires_operator_authorization"] is True
    assert top["runtime_mutation_required"] is True
    assert top["actionability"] == "operator_required"
    assert top["side_effect_boundary"] == (
        "recommendation_only_operator_runtime_mutation_required_"
        "no_order_or_probe_authority"
    )
    assert top["evidence"]["profitability_next_move_runtime_mutation_required"] is True
    assert top["evidence"]["profitability_primary_cost_gate_root_blocker"][
        "gate"
    ] == "demo_learning_stack_operator_apply_required"
