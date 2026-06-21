"""Learning worklist derived from alpha discovery blockers.

MODULE_NOTE:
  Module purpose: convert blocker scorecards into machine-readable learning
  tasks. It is artifact-only and never grants probe, order, or promotion
  authority.
"""

from __future__ import annotations

import hashlib
from typing import Any

LEARNING_WORKLIST_SCHEMA_VERSION = "alpha_learning_worklist_v1"

_TASK_PRIORITY = {
    "promotion_review": 0,
    "operator_probe_review": 10,
    "runtime_source_reconcile": 20,
    "cost_gate_learning_activation": 30,
    "cost_gate_outcome_review": 35,
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
    "demo_learning_evidence_status",
    "demo_learning_evidence_cost_gate_rejects_recorded_in_pg",
    "demo_learning_evidence_order_flow_evidence_status",
    "demo_learning_evidence_order_flow_evidence_starved",
    "ledger_status",
    "blocked_signal_outcome_count",
    "blocked_signal_positive_outcome_count",
    "blocked_signal_net_positive_pct",
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
    if (
        blocker_class == "source_health"
        and ("runtime_source" in next_trigger or "source_not_activation_ready" in primary)
    ):
        return "runtime_source_reconcile"
    if arm_id == "cost_gate_demo_learning_lane":
        if "blocked_signal" in primary or "blocked_outcome" in primary:
            return "cost_gate_outcome_review"
        if (
            "learning_lane" in primary
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
    if blocker_class == "rejected_no_edge":
        return "reject_or_archive"
    return "diagnose_blocker"


def _learning_objective(row: dict[str, Any], task_type: str) -> str:
    if task_type == "promotion_review":
        return "run_formal_aeg_qc_mit_review_before_any_promotion"
    if task_type == "operator_probe_review":
        return "operator_review_isolated_probe_authority_without_granting_order_authority"
    if task_type == "runtime_source_reconcile":
        return "reconcile_runtime_source_before_learning_activation_or_probe_trust"
    if task_type == "cost_gate_learning_activation":
        return "activate_bounded_cost_gate_reject_learning_before_lowering_main_gate"
    if task_type == "cost_gate_outcome_review":
        return "compare_blocked_signal_outcomes_against_market_path"
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


def _runtime_mutation_required(row: dict[str, Any], task_type: str) -> bool:
    if task_type in {"runtime_source_reconcile", "cost_gate_learning_activation"}:
        return True
    next_trigger = _str(row.get("next_trigger")).lower()
    return _contains_any(next_trigger, _RUNTIME_MUTATION_HINTS)


def _operator_authorization_required(row: dict[str, Any], task_type: str) -> bool:
    if _bool(row.get("operator_actionable")):
        return True
    if task_type in {"operator_probe_review", "runtime_source_reconcile"}:
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
