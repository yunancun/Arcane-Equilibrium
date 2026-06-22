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
            },
        },
    ], now_utc=dt.datetime(2026, 6, 22, tzinfo=dt.timezone.utc))

    worklist = plan["learning_worklist"]
    assert worklist["schema_version"] == "alpha_learning_worklist_v4"
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
        "find_train_confirmed_low_friction_mm_signal_that_clears_current_fee"
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
            }
        ],
    })

    task = worklist["top_task"]

    assert worklist["schema_version"] == "alpha_learning_worklist_v4"
    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert task["task_type"] == "operator_probe_review"
    assert task["learning_objective"] == (
        "operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe"
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
    assert (
        "candidate_specific_side_cell_or_candidate_key_evidence_present"
        in task["completion_evidence_required"]
    )


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
                "demo_learning_stack_heartbeats_recent": False,
                "demo_learning_stack_statuses_recent": False,
                "demo_learning_stack_latest_artifacts_present": False,
                "demo_learning_stack_cost_gate_learning_ledger_rows_present": False,
                "demo_learning_stack_blocked_signal_outcomes_present": False,
                "demo_learning_stack_blocked_outcome_review_present": False,
            }
        ],
    })

    task = worklist["top_task"]

    assert worklist["schema_version"] == "alpha_learning_worklist_v4"
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
    assert task["evidence"][
        "demo_learning_stack_cost_gate_learning_ledger_rows_present"
    ] is False
