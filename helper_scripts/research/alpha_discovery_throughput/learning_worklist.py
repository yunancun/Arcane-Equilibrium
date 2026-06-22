"""Learning worklist derived from alpha discovery blockers.

MODULE_NOTE:
  Module purpose: convert blocker scorecards into machine-readable learning
  tasks. It is artifact-only and never grants probe, order, or promotion
  authority.
"""

from __future__ import annotations

import hashlib
from typing import Any

LEARNING_WORKLIST_SCHEMA_VERSION = "alpha_learning_worklist_v4"

_TASK_PRIORITY = {
    "promotion_review": 0,
    "operator_probe_review": 10,
    "runtime_source_reconcile": 20,
    "cost_gate_learning_activation": 30,
    "cost_gate_outcome_review": 35,
    "bounded_probe_execution_realism": 38,
    "polymarket_execution_realism": 40,
    "polymarket_replay_history": 45,
    "polymarket_candidate_replay": 50,
    "candidate_evidence_build": 55,
    "mm_signal_search": 60,
    "fee_path_review": 65,
    "data_capture": 70,
    "sample_accumulation": 75,
    "event_wait": 80,
    "source_health": 85,
    "reject_or_archive": 90,
    "diagnose_blocker": 95,
}

_RUNTIME_MUTATION_HINTS = (
    "deploy",
    "enable_runtime",
    "install_learning_lane",
    "install_",
    "sync_runtime_source",
    "source_sync",
    "activate_cost_gate",
    "writer",
    "cron",
)

_EVIDENCE_KEYS = (
    "sample_count",
    "min_samples",
    "candidate_key",
    "gross_edge_gap_to_current_fee_bps",
    "required_current_fee_gross_edge_bps",
    "best_sample_gated_gross_edge_bps",
    "best_gross_cell_net_bps",
    "low_friction_gross_stability_status",
    "low_friction_train_confirmed_gross_status",
    "low_friction_best_train_confirmed_min_gross_bps",
    "low_friction_train_confirmed_gap_to_current_fee_bps",
    "business_path_actionability_status",
    "candidate_replay_status",
    "candidate_replay_sample_count",
    "candidate_replay_net_bps_mean",
    "candidate_replay_history_status",
    "candidate_replay_history_sample_count",
    "candidate_replay_history_n_days",
    "candidate_replay_history_min_days",
    "candidate_replay_history_execution_realism_status",
    "learning_lane_source_activation_status",
    "learning_lane_git_status",
    "learning_lane_git_behind_count",
    "learning_lane_git_dirty_path_count",
    "demo_learning_stack_healthcheck_status",
    "demo_learning_stack_healthcheck_reason",
    "demo_learning_stack_healthcheck_next_action",
    "demo_learning_stack_healthcheck_ts_utc",
    "demo_learning_stack_healthcheck_age_seconds",
    "demo_learning_stack_healthcheck_source_ok",
    "demo_learning_stack_source_ready",
    "demo_learning_stack_stack_installed",
    "demo_learning_stack_heartbeats_recent",
    "demo_learning_stack_statuses_recent",
    "demo_learning_stack_latest_artifacts_present",
    "demo_learning_stack_cost_gate_learning_ledger_rows_present",
    "demo_learning_stack_blocked_signal_outcomes_present",
    "demo_learning_stack_blocked_outcome_review_present",
    "demo_learning_evidence_status",
    "demo_learning_evidence_cost_gate_rejects_recorded_in_pg",
    "demo_learning_evidence_order_flow_evidence_status",
    "demo_learning_evidence_order_flow_evidence_starved",
    "ledger_status",
    "blocked_signal_outcome_review_schema_version",
    "blocked_signal_outcome_review_status",
    "blocked_signal_outcome_review_reason",
    "blocked_signal_outcome_review_next_trigger",
    "blocked_signal_outcome_count",
    "blocked_signal_positive_outcome_count",
    "blocked_signal_net_positive_pct",
    "blocked_signal_top_review_side_cell_key",
    "blocked_signal_top_review_status",
    "blocked_signal_top_review_wrongful_block_score",
    "blocked_signal_top_review_net_cost_cushion_bps",
    "blocked_signal_top_review_candidate_side_cell_key",
    "blocked_signal_top_review_candidate_wrongful_block_score",
    "blocked_signal_top_review_candidate_net_cost_cushion_bps",
    "learning_loop_last_review_top_side_cell_key",
    "learning_loop_last_review_top_wrongful_block_score",
    "learning_loop_last_review_top_net_cost_cushion_bps",
    "learning_loop_last_review_top_candidate_side_cell_key",
    "learning_loop_last_review_top_candidate_wrongful_block_score",
    "learning_loop_last_review_top_candidate_net_cost_cushion_bps",
    "profit_learning_decision_packet_status",
    "profit_learning_decision_packet_reason",
    "profit_learning_decision_packet_next_actions",
    "profit_learning_decision_packet_generated_at_utc",
    "profit_learning_decision_packet_age_seconds",
    "profit_learning_decision_packet_source_ok",
    "profit_learning_decision_packet_source_path",
    "profit_learning_decision_packet_source_error",
    "profit_learning_cost_gate_rejects_recorded",
    "profit_learning_silent_drop_risk",
    "profit_learning_counterfactual_scorecard_available",
    "profit_learning_counterfactual_learning_candidates_present",
    "profit_learning_bounded_plan_ready",
    "profit_learning_blocked_outcome_review_candidates_present",
    "profit_learning_sealed_horizon_learning_evidence_available",
    "profit_learning_sealed_horizon_learning_evidence_candidates_present",
    "profit_learning_global_cost_gate_lowering_recommended",
    "profit_learning_order_authority_granted",
    "profit_learning_main_cost_gate_adjustment",
    "profit_learning_promotion_evidence",
    "profit_learning_data_flow_status",
    "profit_learning_counterfactual_ranking_status",
    "profit_learning_counterfactual_horizon_stability_status",
    "profit_learning_counterfactual_candidate_count",
    "profit_learning_top_side_cells",
    "profit_learning_activation_status",
    "profit_learning_blocked_review_status",
    "profit_learning_sealed_horizon_learning_evidence_status",
    "profit_learning_sealed_horizon_side_cell_key",
    "profit_learning_sealed_horizon_source_kind",
    "profit_learning_sealed_horizon_outcome_horizon_minutes",
    "profit_learning_sealed_horizon_blocked_signal_outcome_count",
    "profit_learning_sealed_horizon_avg_gross_bps",
    "profit_learning_sealed_horizon_avg_net_bps",
    "profit_learning_sealed_horizon_net_positive_pct",
    "profit_learning_sealed_horizon_review_ready",
    "profit_learning_sealed_horizon_top_side_cell_status",
    "sealed_horizon_probe_preflight_status",
    "sealed_horizon_probe_preflight_reason",
    "sealed_horizon_probe_preflight_next_actions",
    "sealed_horizon_probe_preflight_generated_at_utc",
    "sealed_horizon_probe_preflight_source_ok",
    "sealed_horizon_probe_preflight_source_path",
    "sealed_horizon_probe_preflight_source_error",
    "sealed_horizon_probe_preflight_side_cell_key",
    "sealed_horizon_probe_preflight_outcome_horizon_minutes",
    "sealed_horizon_probe_preflight_blocking_gate_count",
    "sealed_horizon_probe_preflight_blocking_gates",
    "sealed_horizon_probe_preflight_evidence_ready",
    "sealed_horizon_probe_preflight_decision_packet_aligned",
    "sealed_horizon_probe_preflight_operator_review_recorded",
    "sealed_horizon_probe_preflight_production_lane_accumulating",
    "sealed_horizon_probe_preflight_ready_for_operator_authorization",
    "sealed_horizon_probe_preflight_order_authority_granted",
    "sealed_horizon_probe_preflight_probe_authority_granted",
    "sealed_horizon_probe_preflight_main_cost_gate_adjustment",
    "sealed_horizon_probe_preflight_promotion_evidence",
    "bounded_probe_result_review_status",
    "bounded_probe_result_review_reason",
    "bounded_probe_result_review_next_actions",
    "bounded_probe_result_review_generated_at_utc",
    "bounded_probe_result_review_source_ok",
    "bounded_probe_result_review_source_path",
    "bounded_probe_result_review_source_error",
    "bounded_probe_result_review_side_cell_key",
    "bounded_probe_result_review_completed_probe_outcome_count",
    "bounded_probe_result_review_avg_realized_net_bps",
    "bounded_probe_result_review_net_positive_pct",
    "bounded_probe_result_review_operator_review_required",
    "bounded_probe_result_review_stop_probe_recommended",
    "bounded_probe_result_review_learning_review_candidate",
    "bounded_probe_result_review_order_authority_granted",
    "bounded_probe_result_review_probe_authority_granted",
    "bounded_probe_result_review_main_cost_gate_adjustment",
    "bounded_probe_result_review_promotion_evidence",
    "bounded_probe_result_review_evidence_quality_status",
    "bounded_probe_result_review_evidence_quality_reason",
    "bounded_probe_result_review_matched_control_required",
    "bounded_probe_result_review_matched_control_present",
    "bounded_probe_result_review_matched_control_outcome_count",
    "bounded_probe_result_review_matched_control_avg_net_bps",
    "bounded_probe_result_review_matched_control_net_positive_pct",
    "bounded_probe_result_review_probe_minus_control_avg_net_bps",
    "bounded_probe_result_review_probe_edge_capture_ratio",
    "bounded_probe_result_review_probe_execution_gap_bps",
    "bounded_probe_result_review_probe_outperforms_matched_control",
    "bounded_probe_result_review_execution_realism_gap",
    "bounded_probe_result_review_anecdote_risk",
    "bounded_probe_execution_realism_review_present",
    "bounded_probe_execution_realism_review_status",
    "bounded_probe_execution_realism_review_reason",
    "bounded_probe_execution_realism_review_next_actions",
    "bounded_probe_execution_realism_review_generated_at_utc",
    "bounded_probe_execution_realism_review_source_ok",
    "bounded_probe_execution_realism_review_source_path",
    "bounded_probe_execution_realism_review_source_error",
    "bounded_probe_execution_realism_review_side_cell_key",
    "bounded_probe_execution_realism_review_result_review_status",
    "bounded_probe_execution_realism_review_evidence_quality_status",
    "bounded_probe_execution_realism_review_probe_edge_capture_ratio",
    "bounded_probe_execution_realism_review_probe_execution_gap_bps",
    "bounded_probe_execution_realism_review_probe_avg_net_bps",
    "bounded_probe_execution_realism_review_probe_avg_gross_bps",
    "bounded_probe_execution_realism_review_probe_avg_cost_bps",
    "bounded_probe_execution_realism_review_probe_fill_backed_pct",
    "bounded_probe_execution_realism_review_control_avg_net_bps",
    "bounded_probe_execution_realism_review_net_capture_gap_bps",
    "bounded_probe_execution_realism_review_gross_capture_gap_bps",
    "bounded_probe_execution_realism_review_cost_or_slippage_gap_bps",
    "bounded_probe_execution_realism_review_entry_delay_gap_ms",
    "bounded_probe_execution_realism_review_hypothesis_count",
    "bounded_probe_execution_realism_review_primary_hypothesis",
    "bounded_probe_execution_realism_review_execution_gap_confirmed",
    "bounded_probe_execution_realism_review_fill_backed_probe_execution_available",
    "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed",
)


def _str(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    return value is True


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _task_id(row: dict[str, Any], task_type: str, index: int) -> str:
    seed = "|".join((
        _str(row.get("arm_id")),
        task_type,
        _str(row.get("primary_blocker")),
        _str(row.get("next_trigger")),
        str(index),
    ))
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    arm = _str(row.get("arm_id")) or "unknown"
    return f"{arm}:{task_type}:{digest}"


def _classify_task_type(row: dict[str, Any]) -> str:
    arm_id = _str(row.get("arm_id"))
    blocker_class = _str(row.get("blocker_class"))
    primary = _str(row.get("primary_blocker")).lower()
    next_trigger = _str(row.get("next_trigger")).lower()

    if _bool(row.get("promotion_ready")):
        return "promotion_review"
    if _bool(row.get("operator_actionable")):
        return "operator_probe_review"
    if blocker_class == "rejected_no_edge":
        return "reject_or_archive"
    if (
        blocker_class == "source_health"
        and ("runtime_source" in next_trigger or "source_not_activation_ready" in primary)
    ):
        return "runtime_source_reconcile"
    if arm_id == "cost_gate_demo_learning_lane":
        if blocker_class == "execution_realism":
            return "bounded_probe_execution_realism"
        if "blocked_signal" in primary or "blocked_outcome" in primary:
            return "cost_gate_outcome_review"
        if (
            "learning_lane" in primary
            or "demo_learning_stack" in primary
            or "cost_gate_reject" in primary
            or "cost_gate" in next_trigger
        ):
            return "cost_gate_learning_activation"
    if arm_id == "mm_verdict_maker_edge":
        if blocker_class == "fee_or_scale":
            return "fee_path_review"
        if blocker_class in {"cost_wall", "feature_family_no_edge"}:
            return "mm_signal_search"
    if arm_id == "polymarket_leadlag_ic":
        if "execution_realism" in primary or "execution_realism" in next_trigger:
            return "polymarket_execution_realism"
        if "history" in primary or "history" in next_trigger:
            return "polymarket_replay_history"
        if "replay" in primary or "replay" in next_trigger:
            return "polymarket_candidate_replay"
    if blocker_class == "robustness_wait":
        return "candidate_evidence_build"
    if blocker_class == "data_coverage":
        return "data_capture"
    if blocker_class == "sample_gate":
        return "sample_accumulation"
    if blocker_class == "event_wait":
        return "event_wait"
    if blocker_class == "source_health":
        return "source_health"
    return "diagnose_blocker"


def _learning_objective(row: dict[str, Any], task_type: str) -> str:
    if task_type == "promotion_review":
        return "run_formal_aeg_qc_mit_review_before_any_promotion"
    if task_type == "operator_probe_review":
        bounded_review_status = _str(row.get("bounded_probe_result_review_status"))
        if bounded_review_status == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED":
            return "operator_review_first_bounded_probe_results_before_additional_budget"
        if bounded_review_status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED":
            return "operator_review_bounded_probe_learning_results_without_promotion"
        preflight_status = _str(row.get("sealed_horizon_probe_preflight_status"))
        if preflight_status == "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED":
            return "operator_review_sealed_horizon_preflight_and_activate_production_learning_lane"
        if preflight_status == "OPERATOR_REVIEW_REQUIRED":
            return "operator_review_sealed_horizon_probe_preflight"
        if preflight_status == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION":
            return "operator_authorize_minimal_bounded_demo_probe_after_preflight"
        if (
            _str(row.get("arm_id")) == "cost_gate_demo_learning_lane"
            and row.get("profit_learning_sealed_horizon_review_ready") is True
        ):
            return "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
        if (
            _str(row.get("arm_id")) == "cost_gate_demo_learning_lane"
            and row.get("profit_learning_top_side_cells")
        ):
            return "operator_review_profit_learning_decision_packet_before_bounded_demo_probe"
        if (
            _str(row.get("arm_id")) == "cost_gate_demo_learning_lane"
            and (
                row.get("blocked_signal_top_review_candidate_side_cell_key")
                or row.get("blocked_signal_top_review_side_cell_key")
            )
        ):
            return "operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe"
        return "operator_review_isolated_probe_authority_without_granting_order_authority"
    if task_type == "runtime_source_reconcile":
        return "reconcile_runtime_source_before_learning_activation_or_probe_trust"
    if task_type == "cost_gate_learning_activation":
        return "activate_bounded_cost_gate_reject_learning_before_lowering_main_gate"
    if task_type == "cost_gate_outcome_review":
        return "compare_blocked_signal_outcomes_against_market_path"
    if task_type == "bounded_probe_execution_realism":
        return "measure_probe_slippage_timing_and_fill_quality_against_matched_control_edge"
    if task_type == "mm_signal_search":
        return "find_train_confirmed_low_friction_mm_signal_that_clears_current_fee"
    if task_type == "fee_path_review":
        return "treat_lower_fee_path_as_business_scale_constraint_not_alpha_proof"
    if task_type == "polymarket_execution_realism":
        return "build_execution_realism_evidence_before_polymarket_promotion"
    if task_type == "polymarket_replay_history":
        return "accumulate_dated_polymarket_replay_history_with_pbo_and_breadth"
    if task_type == "polymarket_candidate_replay":
        return "convert_polymarket_ic_candidate_to_explicit_after_cost_replay"
    if task_type == "candidate_evidence_build":
        return "build_missing_candidate_pnl_breadth_execution_evidence"
    if task_type == "data_capture":
        return "fill_missing_runtime_or_replay_data_before_strategy_judgment"
    if task_type == "sample_accumulation":
        return "continue_capture_until_sample_or_date_gate_is_met"
    if task_type == "event_wait":
        return "wait_for_market_event_or_source_status_change"
    if task_type == "reject_or_archive":
        return "park_current_family_until_new_evidence_changes_the_verdict"
    return _str(row.get("next_trigger")) or "inspect_arm_detail"


def _completion_gate(task_type: str) -> str:
    if task_type == "promotion_review":
        return "formal_aeg_qc_mit_review_verdict_recorded"
    if task_type == "operator_probe_review":
        return "operator_authorization_recorded_and_probe_preflight_passes"
    if task_type == "runtime_source_reconcile":
        return "runtime_source_synced_clean_expected_head_match"
    if task_type == "cost_gate_learning_activation":
        return "learning_lane_ledger_and_blocked_outcomes_accumulating"
    if task_type == "cost_gate_outcome_review":
        return "blocked_signal_outcome_review_refreshed"
    if task_type == "bounded_probe_execution_realism":
        return "bounded_probe_execution_realism_gap_pass_or_reject_recorded"
    if task_type == "mm_signal_search":
        return "train_confirmed_sample_gated_current_fee_gross_edge_found"
    if task_type == "fee_path_review":
        return "business_fee_path_decision_recorded_not_alpha_proof"
    if task_type == "polymarket_execution_realism":
        return "polymarket_execution_realism_pass_or_reject_recorded"
    if task_type == "polymarket_replay_history":
        return "dated_replay_history_ready_for_aeg_recheck"
    if task_type == "polymarket_candidate_replay":
        return "candidate_replay_after_cost_built"
    if task_type == "candidate_evidence_build":
        return "candidate_pnl_breadth_execution_artifacts_available"
    if task_type == "data_capture":
        return "source_data_fresh_and_min_coverage_available"
    if task_type == "sample_accumulation":
        return "sample_or_date_gate_met"
    if task_type == "event_wait":
        return "fresh_event_or_source_status_change_seen"
    if task_type == "reject_or_archive":
        return "new_evidence_changes_rejected_verdict_or_archive_confirmed"
    return "blocker_reclassified_with_next_trigger"


def _completion_status(task_type: str) -> str:
    if task_type == "event_wait":
        return "WAITING_FOR_EVENT_OR_DATA"
    if task_type == "reject_or_archive":
        return "PARKED_UNTIL_NEW_EVIDENCE"
    return "PENDING_EVIDENCE"


def _completion_evidence_required(task_type: str) -> list[str]:
    if task_type == "promotion_review":
        return [
            "formal_AEG_QC_MIT_review_artifact_exists",
            "review_verdict_records_promotion_or_rejection_reason",
            "execution_realism_breadth_regime_freshness_survivorship_fields_present",
        ]
    if task_type == "operator_probe_review":
        return [
            "operator_authorization_artifact_exists",
            "isolated_probe_preflight_passes",
            "candidate_specific_side_cell_or_candidate_key_evidence_present",
            "sealed_horizon_learning_evidence_review_ready_or_blocked_review_candidate_present",
            "bounded_probe_result_review_status_recorded_when_probe_outcomes_exist",
            "order_authority_boundary_explicitly_recorded",
        ]
    if task_type == "runtime_source_reconcile":
        return [
            "runtime_source.source_activation_status == SYNCED_CLEAN",
            "runtime_source.expected_head_status == MATCH when expected_head is provided",
            "runtime_source.git_dirty_path_count == 0 and git_behind_count == 0",
            "activation_preflight_rerun_after_reconcile",
        ]
    if task_type == "cost_gate_learning_activation":
        return [
            "demo_learning_stack_healthcheck_status == EVIDENCE_STACK_ACTIVE",
            "learning_loop_status not in NOT_SEEN/MISSING",
            "ledger_total_rows or materialized_record_count increases",
            "blocked_signal_outcome_count increases after outcome refresh",
            "order_authority remains NOT_GRANTED until separate operator probe review",
        ]
    if task_type == "cost_gate_outcome_review":
        return [
            "blocked_signal_outcome_review artifact refreshed",
            "review status is DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT or NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE",
            "positive blocked outcomes include side_cell_key and net_bps evidence",
            "top blocked side-cell carries wrongful_block_score and net_cost_cushion_bps",
        ]
    if task_type == "bounded_probe_execution_realism":
        return [
            "bounded_probe_result_review_execution_realism_gap is explicit",
            "probe_edge_capture_ratio and probe_execution_gap_bps are recorded",
            "bounded_probe_execution_realism_review_status is recorded",
            "bounded_probe_execution_realism_review_primary_hypothesis is recorded",
            "net gross cost_or_slippage and entry-delay gap decomposition is recorded",
            "fill-backed execution coverage is recorded before trusting proxy rows",
            "Cost Gate review remains blocked until probe captures matched-control edge",
        ]
    if task_type == "mm_signal_search":
        return [
            "low_friction_train_confirmed_gross_status shows current_fee_confirmed candidate",
            "train and holdout sample-gated gross edge clear current fee round trip",
            "walk_forward or AEG evidence is generated before promotion review",
        ]
    if task_type == "fee_path_review":
        return [
            "fee tier or rebate decision recorded by operator/business path",
            "lower-fee scenario remains labeled as fee_or_scale not alpha proof",
        ]
    if task_type == "polymarket_execution_realism":
        return [
            "candidate_replay_history_execution_realism_status is PASS or explicit FAIL",
            "execution realism sample count and cost assumptions are recorded",
        ]
    if task_type == "polymarket_replay_history":
        return [
            "candidate_replay_history_status == REPLAY_HISTORY_READY_FOR_AEG_RECHECK",
            "candidate_replay_history_n_days >= candidate_replay_history_min_days",
            "PBO/breadth/history evidence fields are present",
        ]
    if task_type == "polymarket_candidate_replay":
        return [
            "candidate_replay_status == PAPER_REPLAY_BUILT",
            "after-cost net_bps and holdout net_bps are recorded",
            "candidate_key is preserved through AEG candidate rows",
        ]
    if task_type == "candidate_evidence_build":
        return [
            "candidate PnL evidence artifact exists",
            "breadth/regime/execution realism inputs are present",
            "AEG matrix consumes the same candidate_key",
        ]
    if task_type == "data_capture":
        return [
            "source artifact freshness gate passes",
            "required coverage/sample fields are nonzero",
            "blocker row reclassifies away from data_coverage",
        ]
    if task_type == "sample_accumulation":
        return [
            "sample_count >= min_samples or required distinct-date gate is met",
            "next discovery run reclassifies the blocker",
        ]
    if task_type == "event_wait":
        return [
            "fresh event/watch artifact changes gate status",
            "source freshness gate passes at the next discovery run",
        ]
    if task_type == "reject_or_archive":
        return [
            "new evidence changes the rejected verdict or archive/no-reopen note is recorded",
        ]
    return [
        "blocker is reclassified with a concrete next_trigger",
        "supporting source artifact is fresh and parseable",
    ]


def _runtime_mutation_required(row: dict[str, Any], task_type: str) -> bool:
    if task_type in {"runtime_source_reconcile", "cost_gate_learning_activation"}:
        return True
    next_trigger = _str(row.get("next_trigger")).lower()
    return _contains_any(next_trigger, _RUNTIME_MUTATION_HINTS)


def _operator_authorization_required(row: dict[str, Any], task_type: str) -> bool:
    if _bool(row.get("operator_actionable")):
        return True
    if task_type in {
        "operator_probe_review",
        "runtime_source_reconcile",
        "cost_gate_learning_activation",
    }:
        return True
    next_trigger = _str(row.get("next_trigger")).lower()
    return "operator_" in next_trigger or "operator-review" in next_trigger


def _actionability(row: dict[str, Any], task_type: str) -> str:
    if _operator_authorization_required(row, task_type):
        return "operator_required"
    if _bool(row.get("engineering_actionable")):
        return "engineering_actionable"
    if task_type in {"event_wait", "sample_accumulation"}:
        return "wait"
    if task_type == "reject_or_archive":
        return "parked"
    return "diagnostic"


def _compact_evidence(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _EVIDENCE_KEYS:
        value = row.get(key)
        if value is not None:
            out[key] = value
    return out


def _priority_score(row: dict[str, Any], task_type: str) -> int:
    score = _TASK_PRIORITY.get(task_type, 99)
    if _bool(row.get("promotion_ready")):
        score -= 3
    if _bool(row.get("operator_actionable")):
        score -= 2
    if _bool(row.get("engineering_actionable")):
        score -= 1
    return max(0, score)


def build_learning_worklist(
    blocker_scorecard: dict[str, Any],
    *,
    top_limit: int = 5,
) -> dict[str, Any]:
    """Build an artifact-only learning worklist from blocker rows."""
    rows = [
        row for row in blocker_scorecard.get("arms", [])
        if isinstance(row, dict)
    ]
    tasks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        task_type = _classify_task_type(row)
        requires_operator = _operator_authorization_required(row, task_type)
        runtime_mutation = _runtime_mutation_required(row, task_type)
        task = {
            "task_id": _task_id(row, task_type, index),
            "arm_id": row.get("arm_id"),
            "task_type": task_type,
            "learning_objective": _learning_objective(row, task_type),
            "completion_gate": _completion_gate(task_type),
            "completion_status": _completion_status(task_type),
            "completion_evidence_required": _completion_evidence_required(task_type),
            "blocker_class": row.get("blocker_class"),
            "primary_blocker": row.get("primary_blocker"),
            "next_trigger": row.get("next_trigger"),
            "priority_score": _priority_score(row, task_type),
            "actionability": _actionability(row, task_type),
            "requires_operator_authorization": requires_operator,
            "runtime_mutation_required": runtime_mutation,
            "promotion_ready": _bool(row.get("promotion_ready")),
            "operator_actionable": _bool(row.get("operator_actionable")),
            "engineering_actionable": _bool(row.get("engineering_actionable")),
            "side_effect_boundary": (
                "recommendation_only_no_order_authority_no_runtime_mutation"
            ),
            "evidence": _compact_evidence(row),
        }
        tasks.append(task)

    tasks.sort(key=lambda task: (
        task["priority_score"],
        _str(task.get("arm_id")),
        _str(task.get("task_type")),
    ))
    for rank, task in enumerate(tasks, start=1):
        task["rank"] = rank

    task_type_counts: dict[str, int] = {}
    actionability_counts: dict[str, int] = {}
    for task in tasks:
        task_type = _str(task.get("task_type"))
        actionability = _str(task.get("actionability"))
        task_type_counts[task_type] = task_type_counts.get(task_type, 0) + 1
        actionability_counts[actionability] = (
            actionability_counts.get(actionability, 0) + 1
        )

    promotion_ready_count = sum(1 for task in tasks if task["promotion_ready"])
    operator_required_count = sum(
        1 for task in tasks if task["requires_operator_authorization"]
    )
    runtime_mutation_required_count = sum(
        1 for task in tasks if task["runtime_mutation_required"]
    )
    engineering_actionable_count = sum(
        1 for task in tasks
        if task["actionability"] == "engineering_actionable"
    )

    if promotion_ready_count > 0:
        status = "PROMOTION_REVIEW_READY"
    elif operator_required_count > 0:
        status = "OPERATOR_GATED_LEARNING_READY"
    elif engineering_actionable_count > 0:
        status = "LEARNING_WORK_AVAILABLE"
    elif tasks:
        status = "WAITING_FOR_DATA_OR_EVENT"
    else:
        status = "NO_LEARNING_WORK"

    return {
        "schema_version": LEARNING_WORKLIST_SCHEMA_VERSION,
        "status": status,
        "task_count": len(tasks),
        "task_type_counts": task_type_counts,
        "actionability_counts": actionability_counts,
        "promotion_ready_count": promotion_ready_count,
        "operator_required_count": operator_required_count,
        "runtime_mutation_required_count": runtime_mutation_required_count,
        "engineering_actionable_count": engineering_actionable_count,
        "top_task": tasks[0] if tasks else None,
        "top_tasks": tasks[:top_limit],
        "tasks": tasks,
        "policy": "artifact_only_learning_recommendations_no_probe_or_trade_side_effect",
    }


__all__ = [
    "LEARNING_WORKLIST_SCHEMA_VERSION",
    "build_learning_worklist",
]
