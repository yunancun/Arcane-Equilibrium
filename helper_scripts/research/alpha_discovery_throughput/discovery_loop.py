"""Read-only multi-arm discovery loop planner."""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import DISCOVERY_LOOP_SCHEMA_VERSION, RUNNER_VERSION
from .learning_worklist import build_learning_worklist

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
    "execution_realism": 6,
    "data_coverage": 7,
    "event_wait": 8,
    "robustness_wait": 9,
    "rejected_no_edge": 10,
    "source_health": 11,
    "unknown_wait": 12,
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


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _cost_gate_learning_lane_state(arm: dict[str, Any]) -> dict[str, Any]:
    detail = _dict(arm.get("detail"))
    ledger_status = str(detail.get("ledger_status") or "UNKNOWN").upper()
    loop_status = str(detail.get("learning_loop_status") or "UNKNOWN").upper()
    admission_count = _int(detail.get("admission_decision_count"))
    capture_error_count = _int(detail.get("capture_error_count"))
    blocked_outcome_count = _int(detail.get("blocked_signal_outcome_count"))
    blocked_review = _dict(detail.get("blocked_signal_outcome_review"))
    blocked_review_status = str(
        detail.get("blocked_signal_outcome_review_status")
        or blocked_review.get("status")
        or ""
    ).upper()
    historical_review = _dict(detail.get("historical_scorecard_review"))
    historical_review_status = str(
        detail.get("historical_scorecard_review_status")
        or historical_review.get("status")
        or ""
    ).upper()
    historical_candidate_count = _int(
        detail.get("historical_candidate_side_cell_count")
    )
    demo_evidence_status = str(
        detail.get("demo_learning_evidence_status") or ""
    ).upper()
    demo_evidence_next_action = detail.get("demo_learning_evidence_next_action")
    demo_cost_gate_rejects_recorded = (
        detail.get("demo_learning_evidence_cost_gate_rejects_recorded_in_pg") is True
    )
    demo_order_flow_starved = (
        detail.get("demo_learning_evidence_order_flow_evidence_starved") is True
        or str(
            detail.get("demo_learning_evidence_order_flow_evidence_status") or ""
        ).upper()
        == "COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE"
    )
    demo_learning_data_flow_stale = (
        detail.get("demo_learning_evidence_learning_data_flow_stale") is True
        or demo_evidence_status == "DEMO_LEARNING_DATA_FLOW_STALE"
        or str(
            detail.get("demo_learning_evidence_data_flow_freshness_status") or ""
        ).upper()
        == "LEARNING_DATA_FLOW_STALE"
    )
    source_activation_ready = detail.get("learning_lane_source_activation_ready")
    stack_health_status = str(
        detail.get("demo_learning_stack_healthcheck_status") or ""
    ).upper()
    stack_health_next_action = detail.get(
        "demo_learning_stack_healthcheck_next_action"
    )
    activation_packet_present = (
        detail.get("demo_learning_stack_activation_packet_present") is True
    )
    activation_packet_source_ok = (
        detail.get("demo_learning_stack_activation_packet_source_ok") is True
    )
    activation_packet_status = str(
        detail.get("demo_learning_stack_activation_packet_status") or ""
    ).upper()
    activation_packet_next_trigger = str(
        detail.get("demo_learning_stack_activation_packet_operator_next_action")
        or "refresh_demo_learning_stack_activation_packet"
    )
    dry_run_review_present = (
        detail.get("demo_learning_stack_dry_run_review_present") is True
    )
    dry_run_review_source_ok = (
        detail.get("demo_learning_stack_dry_run_review_source_ok") is True
    )
    dry_run_review_status = str(
        detail.get("demo_learning_stack_dry_run_review_status") or ""
    ).upper()
    dry_run_review_next_trigger = str(
        detail.get("demo_learning_stack_dry_run_review_operator_next_action")
        or "run_demo_learning_stack_dry_run_review"
    )
    packet_present = detail.get("profit_learning_decision_packet_present") is True
    packet_source_ok = detail.get("profit_learning_decision_packet_source_ok") is True
    packet_status = str(
        detail.get("profit_learning_decision_packet_status") or ""
    ).upper()
    packet_next_actions = _list(
        detail.get("profit_learning_decision_packet_next_actions")
    )
    packet_next_trigger = (
        str(packet_next_actions[0])
        if packet_next_actions
        else "refresh_profit_learning_decision_packet"
    )
    sealed_preflight_present = (
        detail.get("sealed_horizon_probe_preflight_present") is True
    )
    sealed_preflight_source_ok = (
        detail.get("sealed_horizon_probe_preflight_source_ok") is True
    )
    sealed_preflight_status = str(
        detail.get("sealed_horizon_probe_preflight_status") or ""
    ).upper()
    sealed_preflight_next_actions = _list(
        detail.get("sealed_horizon_probe_preflight_next_actions")
    )
    sealed_preflight_next_trigger = (
        str(sealed_preflight_next_actions[0])
        if sealed_preflight_next_actions
        else "refresh_sealed_horizon_probe_preflight"
    )
    operator_auth_present = (
        detail.get("bounded_probe_operator_authorization_present") is True
    )
    operator_auth_source_ok = (
        detail.get("bounded_probe_operator_authorization_source_ok") is True
    )
    operator_auth_status = str(
        detail.get("bounded_probe_operator_authorization_status") or ""
    ).upper()
    operator_auth_next_actions = _list(
        detail.get("bounded_probe_operator_authorization_next_actions")
    )
    operator_auth_next_trigger = (
        str(operator_auth_next_actions[0])
        if operator_auth_next_actions
        else "refresh_bounded_probe_operator_authorization"
    )
    operator_auth_active_runtime_authority = (
        detail.get("bounded_probe_operator_authorization_active_runtime_order_authority")
        is True
        or detail.get(
            "bounded_probe_operator_authorization_active_runtime_probe_authority"
        )
        is True
    )
    shadow_placement_present = (
        detail.get("bounded_probe_shadow_placement_impact_present") is True
    )
    shadow_placement_source_ok = (
        detail.get("bounded_probe_shadow_placement_impact_source_ok") is True
    )
    shadow_placement_status = str(
        detail.get("bounded_probe_shadow_placement_impact_status") or ""
    ).upper()
    shadow_placement_next_actions = _list(
        detail.get("bounded_probe_shadow_placement_impact_next_actions")
    )
    shadow_placement_next_trigger = (
        str(shadow_placement_next_actions[0])
        if shadow_placement_next_actions
        else "refresh_bounded_probe_shadow_placement_impact"
    )
    bounded_review_present = (
        detail.get("bounded_probe_result_review_present") is True
    )
    bounded_review_source_ok = (
        detail.get("bounded_probe_result_review_source_ok") is True
    )
    bounded_review_status = str(
        detail.get("bounded_probe_result_review_status") or ""
    ).upper()
    bounded_review_quality_status = str(
        detail.get("bounded_probe_result_review_evidence_quality_status") or ""
    ).upper()
    bounded_review_next_actions = _list(
        detail.get("bounded_probe_result_review_next_actions")
    )
    bounded_review_next_trigger = (
        str(bounded_review_next_actions[0])
        if bounded_review_next_actions
        else "refresh_bounded_probe_result_review"
    )
    bounded_execution_review_present = (
        detail.get("bounded_probe_execution_realism_review_present") is True
    )
    bounded_execution_review_source_ok = (
        detail.get("bounded_probe_execution_realism_review_source_ok") is True
    )
    bounded_execution_review_status = str(
        detail.get("bounded_probe_execution_realism_review_status") or ""
    ).upper()
    bounded_execution_review_next_actions = _list(
        detail.get("bounded_probe_execution_realism_review_next_actions")
    )
    bounded_execution_review_next_trigger = (
        str(bounded_execution_review_next_actions[0])
        if bounded_execution_review_next_actions
        else "refresh_bounded_probe_execution_realism_review"
    )

    if source_activation_ready is False:
        return {
            "action": BLOCK,
            "reason": "cost_gate_learning_lane_source_not_activation_ready",
            "blocker_class": "source_health",
            "primary_blocker": "cost_gate_learning_lane_source_not_activation_ready",
            "next_trigger": (
                "sync_runtime_source_to_expected_head_before_cost_gate_learning_activation"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if packet_present and not packet_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "profit_learning_decision_packet_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "profit_learning_decision_packet_not_fresh",
            "next_trigger": "refresh_profit_learning_decision_packet",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if activation_packet_present and not activation_packet_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "demo_learning_stack_activation_packet_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "demo_learning_stack_activation_packet_not_fresh",
            "next_trigger": "refresh_demo_learning_stack_activation_packet",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if dry_run_review_present and not dry_run_review_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "demo_learning_stack_dry_run_review_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "demo_learning_stack_dry_run_review_not_fresh",
            "next_trigger": "refresh_demo_learning_stack_dry_run_review",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if sealed_preflight_present and not sealed_preflight_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "sealed_horizon_probe_preflight_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "sealed_horizon_probe_preflight_not_fresh",
            "next_trigger": "refresh_sealed_horizon_probe_preflight",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if operator_auth_present and not operator_auth_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "bounded_probe_operator_authorization_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "bounded_probe_operator_authorization_not_fresh",
            "next_trigger": "refresh_bounded_probe_operator_authorization",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if shadow_placement_present and not shadow_placement_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "bounded_probe_shadow_placement_impact_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "bounded_probe_shadow_placement_impact_not_fresh",
            "next_trigger": "refresh_bounded_probe_shadow_placement_impact",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if bounded_review_present and not bounded_review_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "bounded_probe_result_review_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "bounded_probe_result_review_not_fresh",
            "next_trigger": "refresh_bounded_probe_result_review",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if bounded_execution_review_present and not bounded_execution_review_source_ok:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "bounded_probe_execution_realism_review_stale_or_unreadable",
            "blocker_class": "data_coverage",
            "primary_blocker": "bounded_probe_execution_realism_review_not_fresh",
            "next_trigger": "refresh_bounded_probe_execution_realism_review",
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if (
        shadow_placement_source_ok
        and shadow_placement_status == "AUTHORITY_BOUNDARY_VIOLATION"
    ):
        return {
            "action": BLOCK,
            "reason": "bounded_probe_shadow_placement_authority_boundary_violation",
            "blocker_class": "source_health",
            "primary_blocker": (
                "bounded_probe_shadow_placement_authority_boundary_violation"
            ),
            "next_trigger": shadow_placement_next_trigger,
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if (
        bounded_execution_review_source_ok
        and bounded_execution_review_status == "AUTHORITY_BOUNDARY_VIOLATION"
    ):
        return {
            "action": BLOCK,
            "reason": "bounded_probe_execution_realism_review_authority_boundary_violation",
            "blocker_class": "source_health",
            "primary_blocker": (
                "bounded_probe_execution_realism_review_authority_boundary_violation"
            ),
            "next_trigger": bounded_execution_review_next_trigger,
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if operator_auth_source_ok and (
        operator_auth_status == "AUTHORITY_BOUNDARY_VIOLATION"
        or operator_auth_active_runtime_authority
    ):
        return {
            "action": BLOCK,
            "reason": "bounded_probe_operator_authorization_authority_boundary_violation",
            "blocker_class": "source_health",
            "primary_blocker": (
                "bounded_probe_operator_authorization_authority_boundary_violation"
            ),
            "next_trigger": operator_auth_next_trigger,
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if bounded_review_source_ok:
        if bounded_review_status == "AUTHORITY_BOUNDARY_VIOLATION":
            return {
                "action": BLOCK,
                "reason": "bounded_probe_result_review_authority_boundary_violation",
                "blocker_class": "source_health",
                "primary_blocker": (
                    "bounded_probe_result_review_authority_boundary_violation"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if bounded_review_status == "PREFLIGHT_DESIGN_NOT_USABLE":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_result_review_preflight_design_not_usable",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "bounded_probe_result_review_preflight_design_not_usable"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if bounded_review_status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED":
            return {
                "action": BLOCK,
                "reason": "bounded_probe_result_review_realized_edge_failed",
                "blocker_class": "rejected_no_edge",
                "primary_blocker": (
                    "bounded_probe_result_review_realized_edge_failed_keep_cost_gate_blocked"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": False,
            }
        if bounded_review_status in {
            "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
        } and bounded_review_quality_status in {
            "",
            "CONTROL_COMPARISON_MISSING",
            "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
        }:
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_result_review_control_comparison_missing",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "bounded_probe_result_review_needs_matched_blocked_signal_control"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if bounded_review_status in {
            "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
        } and bounded_review_quality_status == "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP":
            if not bounded_execution_review_present:
                return {
                    "action": RUN_READ_ONLY_CAPTURE,
                    "reason": "bounded_probe_execution_realism_review_required",
                    "blocker_class": "execution_realism",
                    "primary_blocker": (
                        "bounded_probe_execution_realism_review_required"
                    ),
                    "next_trigger": "refresh_bounded_probe_execution_realism_review",
                    "operator_actionable": False,
                    "engineering_actionable": True,
                }
            if bounded_execution_review_status == (
                "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
            ):
                return {
                    "action": RUN_READ_ONLY_CAPTURE,
                    "reason": (
                        "bounded_probe_execution_realism_review_repair_required"
                    ),
                    "blocker_class": "execution_realism",
                    "primary_blocker": (
                        "bounded_probe_execution_realism_gap_diagnosed_repair_required"
                    ),
                    "next_trigger": bounded_execution_review_next_trigger,
                    "operator_actionable": False,
                    "engineering_actionable": True,
                }
            if bounded_execution_review_status in {
                "EXECUTION_REALISM_PROBE_SAMPLE_BELOW_REVIEW_FLOOR",
                "EXECUTION_REALISM_CONTROL_SAMPLE_BELOW_REVIEW_FLOOR",
            }:
                return {
                    "action": RUN_READ_ONLY_CAPTURE,
                    "reason": (
                        "bounded_probe_execution_realism_review_needs_matching_rows"
                    ),
                    "blocker_class": "sample_gate",
                    "primary_blocker": (
                        "bounded_probe_execution_realism_review_needs_matching_rows"
                    ),
                    "next_trigger": bounded_execution_review_next_trigger,
                    "operator_actionable": False,
                    "engineering_actionable": True,
                }
            if bounded_execution_review_status == "NO_EXECUTION_REALISM_GAP_TO_REVIEW":
                return {
                    "action": RUN_READ_ONLY_CAPTURE,
                    "reason": (
                        "bounded_probe_execution_realism_review_not_aligned_with_result_review"
                    ),
                    "blocker_class": "source_health",
                    "primary_blocker": (
                        "bounded_probe_execution_realism_review_not_aligned_with_result_review"
                    ),
                    "next_trigger": "refresh_bounded_probe_execution_realism_review",
                    "operator_actionable": False,
                    "engineering_actionable": True,
                }
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_result_review_execution_realism_gap",
                "blocker_class": "execution_realism",
                "primary_blocker": (
                    "bounded_probe_result_review_probe_under_captures_matched_control_edge"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if bounded_review_status == (
            "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW"
        ):
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_result_review_collect_more_outcomes",
                "blocker_class": "sample_gate",
                "primary_blocker": (
                    "bounded_probe_result_review_needs_more_probe_outcomes"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if bounded_review_status == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED":
            return {
                "action": READY_FOR_PROBE,
                "reason": "bounded_probe_first_review_passed_operator_review_required",
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "bounded_probe_first_review_passed_operator_review_required"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if bounded_review_status == (
            "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED"
        ):
            return {
                "action": READY_FOR_PROBE,
                "reason": (
                    "bounded_probe_learning_review_candidate_operator_review_required"
                ),
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "bounded_probe_learning_review_candidate_operator_review_required"
                ),
                "next_trigger": bounded_review_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }

    if operator_auth_source_ok:
        if operator_auth_status == "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW":
            return {
                "action": READY_FOR_PROBE,
                "reason": (
                    "bounded_probe_operator_authorization_ready_for_operator_review"
                ),
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "bounded_probe_operator_authorization_ready_for_operator_review"
                ),
                "next_trigger": operator_auth_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if operator_auth_status == "BOUNDED_DEMO_PROBE_AUTHORIZED":
            return {
                "action": READY_FOR_PROBE,
                "reason": (
                    "bounded_probe_operator_authorization_object_review_required"
                ),
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "bounded_probe_operator_authorization_object_review_required"
                ),
                "next_trigger": operator_auth_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if operator_auth_status in {
            "SEALED_HORIZON_PREFLIGHT_NOT_READY",
            "PLACEMENT_REPAIR_PLAN_NOT_READY",
            "AUTHORITY_PATH_PATCH_NOT_READY",
            "CANDIDATE_ALIGNMENT_MISMATCH",
            "AUTHORIZATION_ID_REQUIRED",
            "OPERATOR_ID_REQUIRED",
            "PROBE_BUDGET_REQUIRED_OR_EXCEEDS_SOURCE_LIMIT",
            "AUTHORIZATION_EXPIRY_REQUIRED_OR_INVALID",
            "TYPED_CONFIRM_REQUIRED",
        }:
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_operator_authorization_gates_not_ready",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "bounded_probe_operator_authorization_gates_not_ready"
                ),
                "next_trigger": operator_auth_next_trigger,
                "operator_actionable": operator_auth_status in {
                    "AUTHORIZATION_ID_REQUIRED",
                    "OPERATOR_ID_REQUIRED",
                    "PROBE_BUDGET_REQUIRED_OR_EXCEEDS_SOURCE_LIMIT",
                    "AUTHORIZATION_EXPIRY_REQUIRED_OR_INVALID",
                    "TYPED_CONFIRM_REQUIRED",
                },
                "engineering_actionable": operator_auth_status in {
                    "SEALED_HORIZON_PREFLIGHT_NOT_READY",
                    "PLACEMENT_REPAIR_PLAN_NOT_READY",
                    "AUTHORITY_PATH_PATCH_NOT_READY",
                    "CANDIDATE_ALIGNMENT_MISMATCH",
                },
            }

    if shadow_placement_source_ok:
        if shadow_placement_status in {
            "PLACEMENT_REPAIR_PLAN_REQUIRED",
            "ORDER_TOUCHABILITY_AUDIT_REQUIRED",
            "PLACEMENT_REPAIR_PLAN_NOT_READY",
            "ORDER_TOUCHABILITY_SAMPLE_REQUIRED",
        }:
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_shadow_placement_input_or_sample_required",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "bounded_probe_shadow_placement_input_or_sample_required"
                ),
                "next_trigger": shadow_placement_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if shadow_placement_status == "SHADOW_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_shadow_placement_would_skip_all_orders",
                "blocker_class": "execution_realism",
                "primary_blocker": (
                    "bounded_probe_shadow_placement_would_skip_all_orders"
                ),
                "next_trigger": shadow_placement_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if shadow_placement_status == (
            "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH"
        ):
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": (
                    "bounded_probe_shadow_placement_candidate_sample_missing"
                ),
                "blocker_class": "execution_realism",
                "primary_blocker": (
                    "bounded_probe_shadow_placement_candidate_sample_missing"
                ),
                "next_trigger": shadow_placement_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if shadow_placement_status in {
            "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE",
            "SHADOW_PLACEMENT_PARTIAL_SKIP_REQUIRED",
        }:
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "bounded_probe_shadow_placement_ready_for_operator_review",
                "blocker_class": "execution_realism",
                "primary_blocker": (
                    "bounded_probe_shadow_placement_ready_for_operator_review"
                ),
                "next_trigger": shadow_placement_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }

    if blocked_review_status == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT":
        return {
            "action": READY_FOR_PROBE,
            "reason": "cost_gate_blocked_outcome_review_candidate",
            "blocker_class": "probe_ready",
            "primary_blocker": (
                "cost_gate_blocked_signal_outcomes_need_demo_probe_authority_review"
            ),
            "next_trigger": (
                detail.get("blocked_signal_outcome_review_next_trigger")
                or blocked_review.get("next_trigger")
                or "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
            ),
            "operator_actionable": True,
            "engineering_actionable": True,
        }

    if dry_run_review_source_ok:
        if dry_run_review_status == "DRY_RUN_PREVIEW_FAILED_REPAIR_REQUIRED":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_dry_run_preview_failed",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_dry_run_preview_failed_repair_required"
                ),
                "next_trigger": dry_run_review_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if (
            dry_run_review_status
            == "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
        ):
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_dry_run_preview_passed",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_dry_run_preview_passed_operator_apply_review_required"
                ),
                "next_trigger": dry_run_review_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }

    if activation_packet_source_ok:
        if activation_packet_status == "SOURCE_NOT_READY":
            return {
                "action": BLOCK,
                "reason": "demo_learning_stack_activation_packet_source_not_ready",
                "blocker_class": "source_health",
                "primary_blocker": (
                    "demo_learning_stack_activation_packet_source_not_ready"
                ),
                "next_trigger": activation_packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if activation_packet_status == "READY_FOR_OPERATOR_DRY_RUN":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_activation_packet_ready_for_operator_dry_run",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_activation_packet_ready_for_operator_dry_run"
                ),
                "next_trigger": activation_packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if activation_packet_status == "STACK_INSTALLED_REPAIR_REQUIRED":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_activation_packet_repair_required",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_activation_packet_repair_required"
                ),
                "next_trigger": activation_packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if activation_packet_status == "LEARNING_REVIEW_REFRESH_REQUIRED":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_activation_packet_review_refresh_required",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_activation_packet_review_refresh_required"
                ),
                "next_trigger": activation_packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if activation_packet_status == "REVIEW_REQUIRED":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_activation_packet_review_required",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "demo_learning_stack_activation_packet_review_required"
                ),
                "next_trigger": activation_packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }

    if sealed_preflight_source_ok:
        if sealed_preflight_status == "AUTHORITY_BOUNDARY_VIOLATION":
            return {
                "action": BLOCK,
                "reason": "sealed_horizon_probe_preflight_authority_boundary_violation",
                "blocker_class": "source_health",
                "primary_blocker": (
                    "sealed_horizon_probe_preflight_authority_boundary_violation"
                ),
                "next_trigger": sealed_preflight_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if sealed_preflight_status == "SEALED_HORIZON_EVIDENCE_NOT_READY":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "sealed_horizon_probe_preflight_evidence_not_ready",
                "blocker_class": "data_coverage",
                "primary_blocker": "sealed_horizon_probe_preflight_evidence_not_ready",
                "next_trigger": sealed_preflight_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if sealed_preflight_status == "PROFIT_DECISION_PACKET_NOT_ALIGNED":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "sealed_horizon_probe_preflight_decision_packet_not_aligned",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "sealed_horizon_probe_preflight_decision_packet_not_aligned"
                ),
                "next_trigger": sealed_preflight_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if sealed_preflight_status == (
            "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED"
        ):
            return {
                "action": READY_FOR_PROBE,
                "reason": (
                    "sealed_horizon_probe_preflight_requires_operator_review_and_learning_lane"
                ),
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "sealed_horizon_probe_preflight_requires_operator_review_and_learning_lane"
                ),
                "next_trigger": sealed_preflight_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if sealed_preflight_status == "OPERATOR_REVIEW_REQUIRED":
            return {
                "action": READY_FOR_PROBE,
                "reason": "sealed_horizon_probe_preflight_requires_operator_review",
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "sealed_horizon_probe_preflight_requires_operator_review"
                ),
                "next_trigger": sealed_preflight_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if sealed_preflight_status == "PRODUCTION_LEARNING_LANE_NOT_READY":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "sealed_horizon_probe_preflight_production_lane_not_ready",
                "blocker_class": "data_coverage",
                "primary_blocker": (
                    "sealed_horizon_probe_preflight_production_lane_not_ready"
                ),
                "next_trigger": sealed_preflight_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if sealed_preflight_status == (
            "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
        ):
            return {
                "action": READY_FOR_PROBE,
                "reason": (
                    "sealed_horizon_probe_preflight_ready_for_operator_authorization"
                ),
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "sealed_horizon_probe_preflight_ready_for_operator_authorization"
                ),
                "next_trigger": sealed_preflight_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }

    if packet_source_ok:
        if packet_status == "DATA_FLOW_MONITOR_REQUIRED":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_data_flow_monitor_required",
                "blocker_class": "data_coverage",
                "primary_blocker": "profit_learning_data_flow_monitor_required",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if packet_status in {"RUN_REJECT_COUNTERFACTUAL", "REFRESH_REJECT_COUNTERFACTUAL"}:
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_reject_counterfactual_required",
                "blocker_class": "data_coverage",
                "primary_blocker": "profit_learning_reject_counterfactual_required",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if packet_status == "BUILD_OR_REFRESH_BOUNDED_LEARNING_PLAN":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_bounded_plan_required",
                "blocker_class": "data_coverage",
                "primary_blocker": "profit_learning_bounded_plan_required",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if packet_status == "RUN_LEARNING_LANE_ACTIVATION_PREFLIGHT":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_activation_preflight_required",
                "blocker_class": "source_health",
                "primary_blocker": "profit_learning_activation_preflight_required",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if packet_status == "ACTIVATE_OR_REPAIR_LEARNING_STACK":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_stack_activation_or_repair_required",
                "blocker_class": "data_coverage",
                "primary_blocker": "profit_learning_stack_activation_or_repair_required",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if packet_status == "WAIT_FOR_BLOCKED_OUTCOME_REVIEW":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_blocked_outcome_review_required",
                "blocker_class": "data_coverage",
                "primary_blocker": "profit_learning_blocked_outcome_review_required",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if packet_status == "OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES":
            return {
                "action": READY_FOR_PROBE,
                "reason": "profit_learning_demo_probe_candidates_need_operator_review",
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "profit_learning_demo_probe_candidates_need_operator_review"
                ),
                "next_trigger": packet_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if packet_status == "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE":
            return {
                "action": READY_FOR_PROBE,
                "reason": (
                    "profit_learning_sealed_horizon_demo_probe_candidate_needs_operator_review"
                ),
                "blocker_class": "probe_ready",
                "primary_blocker": (
                    "profit_learning_sealed_horizon_demo_probe_candidate_needs_operator_review"
                ),
                "next_trigger": packet_next_trigger,
                "operator_actionable": True,
                "engineering_actionable": True,
            }
        if packet_status == "CONTINUE_BLOCKED_OUTCOME_COLLECTION":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_blocked_outcomes_need_more_samples",
                "blocker_class": "sample_gate",
                "primary_blocker": "profit_learning_blocked_outcomes_need_more_samples",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if packet_status == "KEEP_COST_GATE_AND_CONTINUE_COLLECTION":
            return {
                "action": BLOCK,
                "reason": "profit_learning_counterfactual_confirms_current_block",
                "blocker_class": "rejected_no_edge",
                "primary_blocker": "profit_learning_counterfactual_confirms_current_block",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": False,
            }
        if packet_status == "NO_READY_PROFIT_LEARNING_CANDIDATE":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "profit_learning_no_ready_candidate_continue_collection",
                "blocker_class": "sample_gate",
                "primary_blocker": "profit_learning_no_ready_candidate_continue_collection",
                "next_trigger": packet_next_trigger,
                "operator_actionable": False,
                "engineering_actionable": True,
            }

    if stack_health_status == "BOUNDED_PROBE_PREFLIGHT_MISSING":
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "bounded_probe_preflight_missing_for_learning_stack",
            "blocker_class": "data_coverage",
            "primary_blocker": "bounded_probe_preflight_missing_for_learning_stack",
            "next_trigger": (
                stack_health_next_action
                or "refresh_sealed_horizon_probe_preflight_before_bounded_probe_reviews"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    if stack_health_status == "BOUNDED_PROBE_REVIEW_ARTIFACTS_MISSING":
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "bounded_probe_review_artifacts_missing_for_learning_stack",
            "blocker_class": "data_coverage",
            "primary_blocker": "bounded_probe_review_artifacts_missing_for_learning_stack",
            "next_trigger": (
                stack_health_next_action
                or "rerun_cost_gate_learning_lane_cron_after_sealed_preflight_refresh"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if ledger_status in {"MISSING", "EMPTY"}:
        if stack_health_status == "SOURCE_NOT_READY":
            return {
                "action": BLOCK,
                "reason": "demo_learning_stack_source_not_ready",
                "blocker_class": "source_health",
                "primary_blocker": "demo_learning_stack_source_not_ready",
                "next_trigger": (
                    stack_health_next_action
                    or "reconcile_runtime_source_before_stack_install_or_validation"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "NOT_INSTALLED":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_not_installed",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_not_installed",
                "next_trigger": (
                    stack_health_next_action
                    or "operator_approve_runtime_source_reconcile_then_install_demo_learning_stack_crons"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "INSTALLED_NOT_FIRING":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_installed_not_firing",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_installed_not_firing",
                "next_trigger": (
                    stack_health_next_action or "inspect_cron_logs_and_crontab_schedule"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "FIRING_NO_RECENT_STATUS":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_firing_no_recent_status",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_firing_no_recent_status",
                "next_trigger": (
                    stack_health_next_action
                    or "inspect_cron_logs_for_runtime_or_python_errors"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "ERROR":
            return {
                "action": BLOCK,
                "reason": "demo_learning_stack_error",
                "blocker_class": "source_health",
                "primary_blocker": "demo_learning_stack_error",
                "next_trigger": (
                    stack_health_next_action
                    or "inspect_cost_gate_learning_lane_status_log_and_stage_artifacts"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "FIRING_BUT_ARTIFACTS_INCOMPLETE":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_artifacts_incomplete",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_artifacts_incomplete",
                "next_trigger": (
                    stack_health_next_action
                    or "wait_one_cycle_or_inspect_latest_artifact_paths"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "RUNNING_NO_LEDGER_ROWS":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_running_no_ledger_rows",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_running_no_ledger_rows",
                "next_trigger": (
                    stack_health_next_action
                    or "confirm_materializer_input_rows_and_writer_or_pg_reject_source"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "LEDGER_ONLY_NEEDS_OUTCOME_REFRESH":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_ledger_only_needs_outcome_refresh",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_ledger_only_needs_outcome_refresh",
                "next_trigger": (
                    stack_health_next_action
                    or "wait_for_outcome_refresh_or_inspect_price_observation_windows"
                ),
                "operator_actionable": False,
                "engineering_actionable": True,
            }
        if stack_health_status == "STALE_ARTIFACT":
            return {
                "action": RUN_READ_ONLY_CAPTURE,
                "reason": "demo_learning_stack_healthcheck_stale",
                "blocker_class": "data_coverage",
                "primary_blocker": "demo_learning_stack_healthcheck_stale",
                "next_trigger": "refresh_demo_learning_stack_healthcheck_latest",
                "operator_actionable": False,
                "engineering_actionable": True,
            }

    if ledger_status in {"MISSING", "EMPTY"} and demo_learning_data_flow_stale:
        return {
            "action": BLOCK,
            "reason": "demo_learning_data_flow_stale",
            "blocker_class": "data_coverage",
            "primary_blocker": "demo_learning_data_flow_stale",
            "next_trigger": (
                demo_evidence_next_action
                or "restore_demo_data_flow_before_cost_gate_learning_activation"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if (
        ledger_status in {"MISSING", "EMPTY"}
        and demo_cost_gate_rejects_recorded
        and demo_order_flow_starved
    ):
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "fresh_cost_gate_reject_wall_no_order_flow_evidence",
            "blocker_class": "data_coverage",
            "primary_blocker": "demo_cost_gate_reject_wall_no_order_flow_evidence",
            "next_trigger": (
                detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_recommendation_next_action"
                )
                or detail.get("demo_learning_evidence_order_flow_evidence_next_action")
                or "activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if (
        ledger_status in {"MISSING", "EMPTY"}
        and demo_evidence_status == "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING"
        and demo_cost_gate_rejects_recorded
    ):
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "demo_pg_cost_gate_rejects_without_learning_ledger",
            "blocker_class": "data_coverage",
            "primary_blocker": (
                "demo_cost_gate_rejects_recorded_but_learning_lane_not_accumulating"
            ),
            "next_trigger": (
                demo_evidence_next_action
                or "enable_bounded_cost_gate_learning_lane_after_operator_review"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if (
        ledger_status in {"MISSING", "EMPTY"}
        and demo_evidence_status == "OBSERVATION_TELEMETRY_ACTIVE_NO_ACTIONABLE_LEDGER"
    ):
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "demo_observation_only_no_actionable_reject_ledger",
            "blocker_class": "data_coverage",
            "primary_blocker": (
                "demo_observation_telemetry_active_no_actionable_reject_evidence"
            ),
            "next_trigger": (
                demo_evidence_next_action
                or "wait_for_candidate_rejects_or_verify_strategy_candidate_producer"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if (
        ledger_status in {"MISSING", "EMPTY"}
        and historical_review_status == "HISTORICAL_COUNTERFACTUAL_CANDIDATES_PRESENT"
        and historical_candidate_count > 0
    ):
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "historical_cost_gate_counterfactual_candidates_need_runtime_capture",
            "blocker_class": "data_coverage",
            "primary_blocker": "historical_cost_gate_candidates_not_runtime_verified",
            "next_trigger": (
                detail.get("historical_scorecard_review_next_trigger")
                or historical_review.get("next_trigger")
                or "enable_runtime_writer_to_accumulate_reject_outcomes_for_historical_candidates"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }

    if ledger_status in {"MISSING", "EMPTY"} and loop_status == "NOT_SEEN":
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "cost_gate_learning_loop_not_seen",
            "blocker_class": "data_coverage",
            "primary_blocker": "cost_gate_learning_loop_not_running",
            "next_trigger": (
                "sync_source_install_learning_lane_cron_enable_runtime_writer_then_observe_reject_rows"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    if ledger_status in {"MISSING", "EMPTY"} and loop_status == "RUNNING_NO_LEDGER_ROWS":
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "cost_gate_learning_loop_running_no_ledger_rows",
            "blocker_class": "data_coverage",
            "primary_blocker": "cost_gate_learning_loop_running_but_no_reject_rows",
            "next_trigger": (
                "verify_runtime_ledger_writer_enabled_or_wait_for_cost_gate_rejects"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    if ledger_status in {"MISSING", "EMPTY"}:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "cost_gate_runtime_ledger_missing",
            "blocker_class": "data_coverage",
            "primary_blocker": "cost_gate_probe_candidates_ready_but_runtime_ledger_empty",
            "next_trigger": (
                "deploy_enable_runtime_ledger_writer_and_learning_lane_cron_then_observe_reject_rows"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    if ledger_status == "CAPTURE_ERRORS_PRESENT" or (
        capture_error_count > 0
        and admission_count == 0
        and blocked_outcome_count == 0
    ):
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "cost_gate_capture_errors_present",
            "blocker_class": "data_coverage",
            "primary_blocker": "cost_gate_rejects_captured_but_admission_not_evaluated",
            "next_trigger": "inspect_demo_learning_lane_plan_and_writer_config",
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    if admission_count > 0 and blocked_outcome_count == 0 and loop_status == "NOT_SEEN":
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "cost_gate_admission_rows_without_refresh_loop",
            "blocker_class": "data_coverage",
            "primary_blocker": (
                "cost_gate_rejects_recorded_but_outcome_refresh_loop_not_running"
            ),
            "next_trigger": "install_learning_lane_cron_or_run_outcome_refresh",
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    if admission_count > 0 and blocked_outcome_count == 0:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "cost_gate_blocked_signal_outcomes_missing",
            "blocker_class": "data_coverage",
            "primary_blocker": "cost_gate_rejects_recorded_need_blocked_signal_outcomes",
            "next_trigger": "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes",
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    if blocked_review_status == "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE":
        return {
            "action": BLOCK,
            "reason": "cost_gate_blocked_outcomes_confirm_current_block",
            "blocker_class": "rejected_no_edge",
            "primary_blocker": "cost_gate_blocked_signal_outcomes_confirm_current_block",
            "next_trigger": (
                detail.get("blocked_signal_outcome_review_next_trigger")
                or blocked_review.get("next_trigger")
                or "keep_cost_gate_blocked_for_reviewed_side_cells"
            ),
            "operator_actionable": False,
            "engineering_actionable": False,
        }
    if blocked_outcome_count > 0:
        return {
            "action": RUN_READ_ONLY_CAPTURE,
            "reason": "cost_gate_blocked_outcomes_below_review_gate",
            "blocker_class": "sample_gate",
            "primary_blocker": "cost_gate_blocked_signal_outcomes_accumulating",
            "next_trigger": (
                detail.get("blocked_signal_outcome_review_next_trigger")
                or blocked_review.get("next_trigger")
                or "continue_recording_and_refreshing_blocked_signal_outcomes"
            ),
            "operator_actionable": False,
            "engineering_actionable": True,
        }
    return {
        "action": RUN_READ_ONLY_CAPTURE,
        "reason": "cost_gate_learning_lane_runtime_evidence_missing",
        "blocker_class": "data_coverage",
        "primary_blocker": "cost_gate_learning_lane_runtime_evidence_missing",
        "next_trigger": "inspect_cost_gate_learning_lane_ledger_and_cron_status",
        "operator_actionable": False,
        "engineering_actionable": True,
    }


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
    elif name == "cost_gate_demo_learning_lane" and gate_status == "OPERATOR_REVIEW":
        state = _cost_gate_learning_lane_state(arm)
        action, reason = str(state["action"]), str(state["reason"])
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


def _arm_candidate_key(arm: dict[str, Any]) -> str:
    detail = _dict(arm.get("detail"))
    return str(detail.get("candidate_key") or "").strip()


def _latest_aeg_matrix_review_summary(arms: list[dict[str, Any]]) -> dict[str, Any]:
    for arm in arms:
        arm_id = str(arm.get("arm_id") or arm.get("name") or "unknown")
        if arm_id != "aeg_robustness_matrix":
            continue
        detail = _dict(arm.get("detail"))
        candidate_key = str(detail.get("candidate_key") or "").strip()
        row_count = _int(arm.get("sample_count") or detail.get("row_count"))
        counts = _dict(detail.get("final_label_counts"))
        durable = _int(
            detail.get("durable_candidate_rows")
            if detail.get("durable_candidate_rows") is not None
            else counts.get("durable-alpha candidate")
        )
        if not candidate_key or row_count <= 0:
            return {}
        status = (
            "AEG_MATRIX_DURABLE_CANDIDATE_ROWS"
            if durable > 0
            else "AEG_MATRIX_NO_DURABLE_CANDIDATE_ROWS"
        )
        return {
            "schema_version": "aeg_matrix_candidate_review_v1",
            "status": status,
            "candidate_key": candidate_key,
            "candidate_id": detail.get("candidate_id"),
            "run_id": detail.get("run_id"),
            "row_count": row_count,
            "durable_candidate_rows": durable,
            "final_label_counts": counts,
            "coverage_gate_status": detail.get("coverage_gate_status"),
            "execution_realism_mode": detail.get("execution_realism_mode"),
            "candidate_metrics_source_report_type": detail.get(
                "candidate_metrics_source_report_type"
            ),
            "candidate_metrics_selected_variant": detail.get(
                "candidate_metrics_selected_variant"
            ),
        }
    return {}


def _aeg_review_consumes_arm_candidate(
    arm: dict[str, Any],
    aeg_review: dict[str, Any],
) -> bool:
    if not aeg_review:
        return False
    candidate_key = _arm_candidate_key(arm)
    return bool(candidate_key and candidate_key == str(aeg_review.get("candidate_key") or ""))


def _aeg_candidate_exclusion_reason(arm: dict[str, Any]) -> str | None:
    detail = _dict(arm.get("detail"))
    budget_status = str(
        detail.get("candidate_replay_history_budget_status") or ""
    ).upper()
    if budget_status == "EARLY_ROTATE_RECOMMENDED":
        return "candidate_replay_history_interim_negative_edge"
    return None


def _candidate_artifact_dependency_summary(
    arms: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    aeg_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aeg_review = aeg_review or _latest_aeg_matrix_review_summary(arms)
    decisions_by_id = {str(row.get("arm_id")): row for row in decisions}
    ready: list[dict[str, Any]] = []
    already_reviewed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
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
        exclusion_reason = _aeg_candidate_exclusion_reason(arm)
        if exclusion_reason:
            detail = _dict(arm.get("detail"))
            excluded.append({
                "arm_id": arm_id,
                "action": action,
                "gate_status": gate_status,
                "sample_count": decision.get("sample_count"),
                "artifacts_ready": artifacts_ready,
                "candidate_key": _arm_candidate_key(arm) or None,
                "exclusion_reason": exclusion_reason,
                "candidate_replay_history_budget_status": detail.get(
                    "candidate_replay_history_budget_status"
                ),
                "candidate_replay_history_interim_edge_status": detail.get(
                    "candidate_replay_history_interim_edge_status"
                ),
                "candidate_replay_history_net_bps_mean": detail.get(
                    "candidate_replay_history_net_bps_mean"
                ),
                "candidate_replay_history_holdout_net_bps_mean": detail.get(
                    "candidate_replay_history_holdout_net_bps_mean"
                ),
            })
            continue
        if (
            _aeg_review_consumes_arm_candidate(arm, aeg_review)
            and aeg_review.get("status") == "AEG_MATRIX_NO_DURABLE_CANDIDATE_ROWS"
        ):
            already_reviewed.append({
                "arm_id": arm_id,
                "action": action,
                "gate_status": gate_status,
                "sample_count": decision.get("sample_count"),
                "artifacts_ready": artifacts_ready,
                "candidate_key": _arm_candidate_key(arm),
                "aeg_matrix_run_id": aeg_review.get("run_id"),
            })
            continue
        ready.append({
            "arm_id": arm_id,
            "action": action,
            "gate_status": gate_status,
            "sample_count": decision.get("sample_count"),
            "artifacts_ready": artifacts_ready,
            "candidate_key": _arm_candidate_key(arm) or None,
        })
    if ready:
        status = "CANDIDATE_ARTIFACTS_AVAILABLE_FOR_ROBUSTNESS"
        reason = "upstream_ready_or_probe_artifacts_available"
        next_trigger = "feed_candidate_artifacts_into_robustness_matrix"
        engineering_actionable = True
    elif already_reviewed:
        status = "CANDIDATE_ARTIFACTS_ALREADY_REVIEWED_NO_DURABLE_ROWS"
        reason = "latest_aeg_matrix_reviewed_candidate_without_durable_rows"
        next_trigger = (
            "build_candidate_pnl_execution_realism_and_breadth_evidence_before_rerunning_matrix"
        )
        engineering_actionable = True
    elif excluded:
        status = "CANDIDATE_ARTIFACTS_EXCLUDED_BY_INTERIM_EDGE"
        reason = "candidate_artifacts_rejected_or_rotated_before_robustness"
        next_trigger = "wait_for_new_candidate_after_reject_or_rotate"
        engineering_actionable = False
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
        "already_reviewed_candidate_artifact_count": len(already_reviewed),
        "already_reviewed_candidate_artifacts": already_reviewed[:8],
        "excluded_candidate_artifact_count": len(excluded),
        "excluded_candidate_artifacts": excluded[:8],
        "latest_aeg_matrix_review": aeg_review or None,
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


def _mm_low_friction_gross_stability_scorecard(detail: dict[str, Any]) -> dict[str, Any]:
    gross_decomp = _dict(detail.get("gross_edge_cost_decomposition"))
    sample_cost_wall = _dict(detail.get("sample_gated_cost_wall_summary"))
    low_friction = _dict(detail.get("low_friction_signal_scorecard"))
    low_friction_failure = _dict(low_friction.get("failure_summary"))
    train_confirmed = _dict(low_friction.get("train_confirmed_gross_scorecard"))
    candidate = _dict(
        gross_decomp.get("best_low_friction_signal_holdout_gross_candidate")
    )
    if not candidate:
        candidate = _dict(low_friction.get("best_holdout_gross_candidate"))

    train = _dict(candidate.get("train"))
    holdout = _dict(candidate.get("holdout"))
    sample_gate_min = _int(
        gross_decomp.get("sample_gate_min_fills")
        or low_friction.get("min_fills_for_signif"),
        default=30,
    )
    if sample_gate_min <= 0:
        sample_gate_min = 30

    def _sample_gated(cell: dict[str, Any]) -> bool:
        if not cell:
            return False
        if cell.get("sample_gated") is not None:
            return bool(cell.get("sample_gated"))
        return (
            _int(cell.get("n_fill_only") or cell.get("n")) >= sample_gate_min
            and not bool(cell.get("signif_suppressed"))
        )

    train_gross = _float(train.get("edge_before_fees_bps"))
    holdout_gross = _float(holdout.get("edge_before_fees_bps"))
    train_net = _float(train.get("net_bps"))
    holdout_net = _float(holdout.get("net_bps"))
    train_sample_gated = _sample_gated(train)
    holdout_sample_gated = _sample_gated(holdout)
    current_fee_round_trip = _float(gross_decomp.get("current_fee_round_trip_bps"))
    if current_fee_round_trip is None:
        current_fee_round_trip = _float(
            sample_cost_wall.get("current_fee_round_trip_bps")
        )
    if current_fee_round_trip is None:
        current_fee_round_trip = _float(low_friction.get("current_fee_round_trip_bps"))

    train_clears_current_fee = (
        train_sample_gated
        and current_fee_round_trip is not None
        and train_gross is not None
        and train_gross >= current_fee_round_trip
    )
    holdout_clears_current_fee = (
        holdout_sample_gated
        and current_fee_round_trip is not None
        and holdout_gross is not None
        and holdout_gross >= current_fee_round_trip
    )
    train_confirms_gross = (
        train_sample_gated
        and train_gross is not None
        and train_gross > 0.0
    )
    holdout_positive_gross = (
        holdout_sample_gated
        and holdout_gross is not None
        and holdout_gross > 0.0
    )

    if not candidate:
        status = "LOW_FRICTION_GROSS_STABILITY_UNAVAILABLE"
        reason = "missing_low_friction_holdout_gross_candidate"
        next_trigger = "search_new_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
    elif holdout_gross is None:
        status = "LOW_FRICTION_HOLDOUT_GROSS_MISSING"
        reason = "best_low_friction_candidate_missing_holdout_gross_edge"
        next_trigger = "refresh_low_friction_scorecard_before_mm_judgment"
    elif not holdout_positive_gross:
        status = "LOW_FRICTION_NO_SAMPLE_GATED_HOLDOUT_GROSS_EDGE"
        reason = "holdout_gross_not_positive_or_not_sample_gated"
        next_trigger = "search_new_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
    elif train_gross is None:
        status = "LOW_FRICTION_HOLDOUT_GROSS_TRAIN_MISSING"
        reason = "holdout_gross_positive_but_train_leg_missing"
        next_trigger = "refresh_low_friction_train_holdout_decomposition_before_strategy_judgment"
    elif not train_confirms_gross:
        status = "LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED"
        reason = (
            "holdout_gross_positive_but_train_gross_non_positive"
            if train_gross <= 0.0
            else "holdout_gross_positive_but_train_leg_not_sample_gated"
        )
        next_trigger = (
            "search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
        )
    elif train_clears_current_fee and holdout_clears_current_fee:
        status = "LOW_FRICTION_TRAIN_AND_HOLDOUT_GROSS_CLEAR_CURRENT_FEE_REVIEW"
        reason = "train_and_holdout_sample_gated_gross_clear_current_fee"
        next_trigger = "run_walk_forward_aeg_execution_realism_chain_before_any_mm_promotion"
    elif current_fee_round_trip is None:
        status = "LOW_FRICTION_TRAIN_HOLDOUT_GROSS_POSITIVE_FEE_UNKNOWN"
        reason = "train_and_holdout_gross_positive_but_current_fee_missing"
        next_trigger = "refresh_mm_current_fee_inputs_before_strategy_judgment"
    else:
        status = "LOW_FRICTION_TRAIN_HOLDOUT_GROSS_POSITIVE_BELOW_CURRENT_FEE"
        reason = "train_and_holdout_gross_positive_but_at_least_one_half_below_current_fee"
        next_trigger = (
            "search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
        )

    holdout_minus_train = (
        holdout_gross - train_gross
        if holdout_gross is not None and train_gross is not None
        else None
    )

    return {
        "schema_version": "low_friction_gross_stability_v1",
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "current_fee_round_trip_bps": _round_or_none(current_fee_round_trip),
        "sample_gate_min_fills": sample_gate_min,
        "candidate_name": candidate.get("name"),
        "candidate_condition": candidate.get("condition"),
        "candidate_feature": candidate.get("feature"),
        "train_gross_edge_bps": _round_or_none(train_gross),
        "holdout_gross_edge_bps": _round_or_none(holdout_gross),
        "train_net_bps": _round_or_none(train_net),
        "holdout_net_bps": _round_or_none(holdout_net),
        "train_n_fill_only": train.get("n_fill_only") or train.get("n"),
        "holdout_n_fill_only": holdout.get("n_fill_only") or holdout.get("n"),
        "train_sample_gated": train_sample_gated,
        "holdout_sample_gated": holdout_sample_gated,
        "train_confirms_gross": train_confirms_gross,
        "holdout_positive_gross": holdout_positive_gross,
        "train_gross_clears_current_fee": train_clears_current_fee,
        "holdout_gross_clears_current_fee": holdout_clears_current_fee,
        "holdout_minus_train_gross_bps": _round_or_none(holdout_minus_train),
        "train_confirmed_gross_status": train_confirmed.get("status"),
        "train_confirmed_positive_gross_count": train_confirmed.get(
            "train_confirmed_positive_gross_count"
        ),
        "best_train_confirmed_min_gross_bps": train_confirmed.get(
            "best_min_train_holdout_gross_bps"
        ),
        "train_confirmed_gap_to_current_fee_bps": train_confirmed.get(
            "gap_to_current_fee_round_trip_bps"
        ),
        "best_train_confirmed_gross_candidate": train_confirmed.get(
            "best_train_confirmed_gross_candidate"
        ),
        "sample_starved_current_fee_holdout_count": low_friction_failure.get(
            "sample_starved_current_fee_holdout_count"
        ),
        "best_sample_starved_current_fee_holdout_candidate": low_friction_failure.get(
            "best_sample_starved_current_fee_holdout_candidate"
        ),
        "sample_gated_holdout_gross_count": low_friction_failure.get(
            "sample_gated_holdout_gross_count"
        ),
        "best_sample_gated_holdout_gross_candidate": low_friction_failure.get(
            "best_sample_gated_holdout_gross_candidate"
        ),
        "train_confirmed_gross_count": low_friction_failure.get(
            "train_confirmed_gross_count"
        ),
    }


def _positive_multiple_or_none(
    required: float | None,
    observed: float | None,
) -> float | None:
    if required is None or observed is None or observed <= 0.0:
        return None
    return required / observed


def _mm_signal_search_directive(
    *,
    escape_status: str,
    escape_reason: str,
    next_trigger: str,
    current_fee_round_trip: float | None,
    best_gross_edge: float | None,
    gap: float | None,
    multiple: float | None,
    current_fee_positive_count: int,
    current_fee_confirmed_count: int,
    best_current_fee_source: str,
    business_status: str,
    low_friction_stability: dict[str, Any],
) -> dict[str, Any]:
    low_status = str(low_friction_stability.get("status") or "").upper()
    train_confirmed_status = str(
        low_friction_stability.get("train_confirmed_gross_status") or ""
    ).upper()
    stable_candidate = _dict(
        low_friction_stability.get("best_train_confirmed_gross_candidate")
    )
    stable_min_gross = _float(
        low_friction_stability.get("best_train_confirmed_min_gross_bps")
    )
    stable_gap = _float(
        low_friction_stability.get("train_confirmed_gap_to_current_fee_bps")
    )
    stable_multiple = _positive_multiple_or_none(
        current_fee_round_trip,
        stable_min_gross,
    )

    lower_fee_scale_gated = (
        business_status == "STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED"
    )
    if current_fee_round_trip is None or best_gross_edge is None:
        status = "SEARCH_BLOCKED_MISSING_COST_INPUTS"
        failure_mode = "missing_current_fee_or_best_sample_gated_gross_edge"
        search_focus = "refresh_mm_cost_wall_inputs"
    elif (
        current_fee_positive_count > 0
        and current_fee_confirmed_count <= 0
        and best_current_fee_source == "low_friction_signal_holdout"
    ):
        status = "SEARCH_REQUIRED_TRAIN_CONFIRMATION"
        failure_mode = "holdout_current_fee_candidate_not_train_confirmed"
        search_focus = "stabilize_holdout_current_fee_candidate_train_leg"
    elif current_fee_positive_count > 0:
        status = "SEARCH_REQUIRED_WALK_FORWARD_CONFIRMATION"
        failure_mode = "current_fee_candidate_lacks_train_holdout_walk_forward_confirmation"
        search_focus = "confirm_current_fee_candidate_in_train_holdout_walk_forward"
    elif gap is not None and gap > 0:
        status = "SEARCH_REQUIRED_EDGE_UPLIFT"
        search_focus = "amplify_train_confirmed_low_friction_candidate_shape"
        if low_status == "LOW_FRICTION_NO_SAMPLE_GATED_HOLDOUT_GROSS_EDGE":
            failure_mode = (
                "current_fee_cost_wall_low_friction_no_sample_gated_holdout_edge"
            )
        elif low_status == "LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED":
            failure_mode = (
                "current_fee_cost_wall_low_friction_holdout_not_train_confirmed"
            )
        elif (
            train_confirmed_status
            == "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE"
        ):
            failure_mode = (
                "current_fee_cost_wall_train_confirmed_low_friction_gross_below_fee"
            )
        else:
            failure_mode = "sample_gated_gross_edge_below_current_fee"
        if lower_fee_scale_gated:
            failure_mode = f"{failure_mode}_lower_fee_path_scale_or_capital_gated"
    else:
        status = "SEARCH_NOT_REQUIRED_CONFIRM_CURRENT_FEE_CELL"
        failure_mode = "gross_edge_clears_current_fee_needs_walk_forward"
        search_focus = "confirm_current_fee_cell_with_walk_forward_and_aeg_chain"

    return {
        "schema_version": "mm_signal_search_directive_v1",
        "status": status,
        "failure_mode": failure_mode,
        "status_reason": low_friction_stability.get("reason") or escape_reason,
        "escape_status": escape_status,
        "escape_reason": escape_reason,
        "success_gate": "train_confirmed_sample_gated_current_fee_gross_edge_found",
        "recommended_search_constraint": (
            "require_train_and_holdout_sample_gated_min_gross_ge_current_fee_round_trip"
        ),
        "search_focus": search_focus,
        "next_trigger": next_trigger,
        "current_fee_round_trip_bps": _round_or_none(current_fee_round_trip),
        "minimum_required_train_holdout_gross_bps": _round_or_none(
            current_fee_round_trip
        ),
        "best_sample_gated_gross_edge_bps": _round_or_none(best_gross_edge),
        "best_sample_gated_gross_gap_bps": _round_or_none(
            max(0.0, gap) if gap is not None else None
        ),
        "best_sample_gated_required_uplift_multiple": _round_or_none(
            multiple if multiple is not None and multiple > 1.0 else None
        ),
        "low_friction_gross_stability_status": low_friction_stability.get("status"),
        "low_friction_train_confirmed_gross_status": (
            low_friction_stability.get("train_confirmed_gross_status")
        ),
        "low_friction_best_train_confirmed_min_gross_bps": (
            low_friction_stability.get("best_train_confirmed_min_gross_bps")
        ),
        "low_friction_train_confirmed_gap_to_current_fee_bps": (
            low_friction_stability.get("train_confirmed_gap_to_current_fee_bps")
        ),
        "low_friction_train_confirmed_required_uplift_multiple": _round_or_none(
            stable_multiple
            if stable_multiple is not None and stable_multiple > 1.0
            else None
        ),
        "stable_candidate_shape_name": stable_candidate.get("name"),
        "stable_candidate_min_train_holdout_gross_bps": stable_candidate.get(
            "min_train_holdout_gross_bps"
        ),
        "sample_starved_current_fee_holdout_count": low_friction_stability.get(
            "sample_starved_current_fee_holdout_count"
        ),
        "best_sample_starved_current_fee_holdout_candidate": (
            low_friction_stability.get(
                "best_sample_starved_current_fee_holdout_candidate"
            )
        ),
        "sample_gated_holdout_gross_count": low_friction_stability.get(
            "sample_gated_holdout_gross_count"
        ),
        "best_sample_gated_holdout_gross_candidate": (
            low_friction_stability.get("best_sample_gated_holdout_gross_candidate")
        ),
        "unstable_holdout_candidate_name": low_friction_stability.get(
            "candidate_name"
        ),
        "unstable_holdout_candidate_condition": low_friction_stability.get(
            "candidate_condition"
        ),
        "sample_gate_min_fills": low_friction_stability.get("sample_gate_min_fills"),
        "current_fee_positive_sample_gated_cell_count": current_fee_positive_count,
        "train_confirmed_current_fee_count": current_fee_confirmed_count,
        "best_sample_gated_current_fee_source": best_current_fee_source or None,
        "fee_path_actionability_status": business_status or None,
        "lower_fee_path_not_actionable_now": lower_fee_scale_gated,
        "cost_gate_policy": "do_not_lower_global_cost_gate_for_mm_search",
        "stable_candidate_gap_to_current_fee_bps": _round_or_none(stable_gap),
    }


def _mm_signal_search_directive_row_extra(
    escape_scorecard: dict[str, Any],
) -> dict[str, Any]:
    directive = _dict(escape_scorecard.get("mm_signal_search_directive"))
    if not directive:
        return {}
    return {
        "mm_signal_search_directive": directive,
        "mm_signal_search_status": directive.get("status"),
        "mm_signal_search_failure_mode": directive.get("failure_mode"),
        "failure_mode": directive.get("failure_mode"),
        "status_reason": directive.get("status_reason"),
        "mm_signal_search_success_gate": directive.get("success_gate"),
        "mm_signal_search_recommended_search_constraint": directive.get(
            "recommended_search_constraint"
        ),
        "mm_signal_search_required_gross_uplift_multiple": directive.get(
            "best_sample_gated_required_uplift_multiple"
        ),
        "mm_signal_search_low_friction_required_gross_uplift_multiple": (
            directive.get("low_friction_train_confirmed_required_uplift_multiple")
        ),
        "mm_signal_search_candidate_shape_name": directive.get(
            "stable_candidate_shape_name"
        ),
        "mm_signal_search_sample_starved_current_fee_holdout_count": directive.get(
            "sample_starved_current_fee_holdout_count"
        ),
        "mm_signal_search_best_sample_starved_current_fee_holdout_candidate": (
            directive.get("best_sample_starved_current_fee_holdout_candidate")
        ),
        "mm_signal_search_sample_gated_holdout_gross_count": directive.get(
            "sample_gated_holdout_gross_count"
        ),
        "mm_signal_search_best_sample_gated_holdout_gross_candidate": (
            directive.get("best_sample_gated_holdout_gross_candidate")
        ),
        "mm_signal_search_lower_fee_path_not_actionable_now": directive.get(
            "lower_fee_path_not_actionable_now"
        ),
    }


def _mm_cost_wall_escape_scorecard(detail: dict[str, Any]) -> dict[str, Any]:
    gross_decomp = _dict(detail.get("gross_edge_cost_decomposition"))
    sample_cost_wall = _dict(detail.get("sample_gated_cost_wall_summary"))
    fee_path = _dict(detail.get("fee_path_feasibility"))
    business_actionability = _dict(fee_path.get("business_path_actionability"))
    low_friction = _dict(detail.get("low_friction_signal_scorecard"))
    history_extra = _mm_lower_fee_history_extra(detail)
    low_friction_stability = _mm_low_friction_gross_stability_scorecard(detail)
    train_confirmed = _dict(low_friction.get("train_confirmed_gross_scorecard"))
    low_friction_stability_status = str(
        low_friction_stability.get("status") or ""
    ).upper()
    low_friction_stability_trigger = (
        low_friction_stability.get("next_trigger")
        if low_friction_stability_status in {
            "LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED",
            "LOW_FRICTION_TRAIN_HOLDOUT_GROSS_POSITIVE_BELOW_CURRENT_FEE",
        }
        else None
    )

    best_current_fee_cell = _dict(
        gross_decomp.get("best_sample_gated_current_fee_cell")
    )
    best_gross_edge = _float(gross_decomp.get("best_sample_gated_gross_edge_bps"))
    if best_gross_edge is None:
        best_gross_edge = _float(best_current_fee_cell.get("edge_before_fees_bps"))
    best_net = _float(gross_decomp.get("best_gross_cell_net_bps"))
    if best_net is None:
        best_net = _float(best_current_fee_cell.get("net_bps"))
    current_fee_round_trip = (
        _float(gross_decomp.get("current_fee_round_trip_bps"))
        if gross_decomp.get("current_fee_round_trip_bps") is not None
        else _float(sample_cost_wall.get("current_fee_round_trip_bps"))
    )
    if (
        current_fee_round_trip is None
        and best_gross_edge is not None
        and best_net is not None
    ):
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
    current_fee_confirmed_count = _int(
        train_confirmed.get("current_fee_confirmed_count")
    )
    best_current_fee_source = str(best_current_fee_cell.get("source") or "")
    business_status = str(business_actionability.get("status") or "").upper()
    default_low_friction_trigger = (
        "search_new_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
    )

    if (
        current_fee_positive_count > 0
        and current_fee_confirmed_count <= 0
        and best_current_fee_source == "low_friction_signal_holdout"
    ):
        status = "CURRENT_FEE_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED"
        reason = "current_fee_positive_low_friction_holdout_cell_lacks_train_confirmation"
        next_trigger = (
            "search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
        )
        engineering_actionable = True
    elif current_fee_positive_count > 0:
        status = "CURRENT_FEE_SAMPLE_GATED_CELL_AVAILABLE"
        reason = "sample_gated_current_fee_positive_cell_exists"
        next_trigger = "review_current_fee_positive_mm_cell_with_walk_forward_and_aeg_chain"
        engineering_actionable = True
    elif gap is None:
        status = "INSUFFICIENT_COST_WALL_ESCAPE_INPUT"
        reason = "missing_current_fee_or_best_gross_edge"
        next_trigger = "refresh_mm_cost_wall_inputs_before_strategy_judgment"
        engineering_actionable = True
    elif (
        gap > 0
        and business_status == "STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED"
    ):
        status = "CURRENT_FEE_GROSS_EDGE_GAP_REQUIRES_NEW_LOW_FRICTION_SIGNAL"
        reason = "lower_fee_path_scale_or_capital_gated_at_current_account_state"
        next_trigger = low_friction_stability_trigger or default_low_friction_trigger
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
    signal_search_directive = _mm_signal_search_directive(
        escape_status=status,
        escape_reason=reason,
        next_trigger=next_trigger,
        current_fee_round_trip=current_fee_round_trip,
        best_gross_edge=best_gross_edge,
        gap=gap,
        multiple=multiple,
        current_fee_positive_count=current_fee_positive_count,
        current_fee_confirmed_count=current_fee_confirmed_count,
        best_current_fee_source=best_current_fee_source,
        business_status=business_status,
        low_friction_stability=low_friction_stability,
    )

    return {
        "schema_version": "mm_cost_wall_escape_v2",
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "engineering_actionable": engineering_actionable,
        "mm_signal_search_directive": signal_search_directive,
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
        "low_friction_signal_status": (
            gross_decomp.get("low_friction_signal_status") or low_friction.get("status")
        ),
        "low_friction_gross_stability_status": low_friction_stability.get("status"),
        "low_friction_gross_stability_reason": low_friction_stability.get("reason"),
        "low_friction_gross_stability_scorecard": low_friction_stability,
        "low_friction_train_confirmed_gross_status": (
            low_friction_stability.get("train_confirmed_gross_status")
        ),
        "low_friction_best_train_confirmed_min_gross_bps": (
            low_friction_stability.get("best_train_confirmed_min_gross_bps")
        ),
        "low_friction_train_confirmed_gap_to_current_fee_bps": (
            low_friction_stability.get("train_confirmed_gap_to_current_fee_bps")
        ),
        "low_friction_train_confirmed_current_fee_count": current_fee_confirmed_count,
        "best_sample_gated_current_fee_source": best_current_fee_source or None,
        "best_low_friction_signal_holdout_gross_candidate": gross_decomp.get(
            "best_low_friction_signal_holdout_gross_candidate"
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
        aeg_review = _dict(detail.get("aeg_matrix_review"))
        if aeg_review.get("status") == "AEG_MATRIX_NO_DURABLE_CANDIDATE_ROWS":
            return _finish_blocker_row(
                row,
                blocker_class="robustness_wait",
                primary_blocker="aeg_matrix_review_no_durable_candidate_rows",
                next_trigger=(
                    "build_candidate_pnl_execution_realism_and_breadth_evidence_before_promotion"
                ),
                engineering_actionable=True,
                extra={
                    "candidate_key": detail.get("candidate_key"),
                    "aeg_matrix_review_status": aeg_review.get("status"),
                    "aeg_matrix_run_id": aeg_review.get("run_id"),
                    "aeg_matrix_candidate_id": aeg_review.get("candidate_id"),
                    "aeg_matrix_row_count": aeg_review.get("row_count"),
                    "aeg_matrix_durable_candidate_rows": aeg_review.get(
                        "durable_candidate_rows"
                    ),
                    "aeg_matrix_final_label_counts": aeg_review.get(
                        "final_label_counts"
                    ),
                    "aeg_matrix_coverage_gate_status": aeg_review.get(
                        "coverage_gate_status"
                    ),
                    "aeg_matrix_execution_realism_mode": aeg_review.get(
                        "execution_realism_mode"
                    ),
                    "candidate_replay_status": detail.get("candidate_replay_status"),
                    "candidate_replay_sample_count": detail.get(
                        "candidate_replay_sample_count"
                    ),
                    "candidate_replay_round_trip_cost_bps": detail.get(
                        "candidate_replay_round_trip_cost_bps"
                    ),
                    "candidate_replay_gross_bps_mean": detail.get(
                        "candidate_replay_gross_bps_mean"
                    ),
                    "candidate_replay_net_bps_mean": detail.get(
                        "candidate_replay_net_bps_mean"
                    ),
                    "candidate_replay_holdout_net_bps_mean": detail.get(
                        "candidate_replay_holdout_net_bps_mean"
                    ),
                    "candidate_replay_cost_wall_status": detail.get(
                        "candidate_replay_cost_wall_status"
                    ),
                    "candidate_replay_execution_realism_status": detail.get(
                        "candidate_replay_execution_realism_status"
                    ),
                    "candidate_replay_history_status": detail.get(
                        "candidate_replay_history_status"
                    ),
                    "candidate_replay_history_reason": detail.get(
                        "candidate_replay_history_reason"
                    ),
                    "candidate_replay_history_report_count": detail.get(
                        "candidate_replay_history_report_count"
                    ),
                    "candidate_replay_history_matched_report_count": detail.get(
                        "candidate_replay_history_matched_report_count"
                    ),
                    "candidate_replay_history_sample_count": detail.get(
                        "candidate_replay_history_sample_count"
                    ),
                    "candidate_replay_history_n_days": detail.get(
                        "candidate_replay_history_n_days"
                    ),
                    "candidate_replay_history_min_days": detail.get(
                        "candidate_replay_history_min_days"
                    ),
                    "candidate_replay_history_min_samples": detail.get(
                        "candidate_replay_history_min_samples"
                    ),
                    "candidate_replay_history_days_remaining": detail.get(
                        "candidate_replay_history_days_remaining"
                    ),
                    "candidate_replay_history_calendar_span_days": detail.get(
                        "candidate_replay_history_calendar_span_days"
                    ),
                    "candidate_replay_history_date_gap_count": detail.get(
                        "candidate_replay_history_date_gap_count"
                    ),
                    "candidate_replay_history_earliest_ready_date": detail.get(
                        "candidate_replay_history_earliest_ready_date"
                    ),
                    "candidate_replay_history_net_bps_mean": detail.get(
                        "candidate_replay_history_net_bps_mean"
                    ),
                    "candidate_replay_history_holdout_net_bps_mean": detail.get(
                        "candidate_replay_history_holdout_net_bps_mean"
                    ),
                    "candidate_replay_history_positive_net_sample_rate": detail.get(
                        "candidate_replay_history_positive_net_sample_rate"
                    ),
                    "candidate_replay_history_interim_edge_status": detail.get(
                        "candidate_replay_history_interim_edge_status"
                    ),
                    "candidate_replay_history_budget_status": detail.get(
                        "candidate_replay_history_budget_status"
                    ),
                    "candidate_replay_history_recommended_next_action": detail.get(
                        "candidate_replay_history_recommended_next_action"
                    ),
                    "candidate_replay_history_pbo_day_count": detail.get(
                        "candidate_replay_history_pbo_day_count"
                    ),
                    "candidate_replay_history_execution_realism_status": detail.get(
                        "candidate_replay_history_execution_realism_status"
                    ),
                },
            )
        if arm_id == "polymarket_leadlag_ic":
            replay_status = str(detail.get("candidate_replay_status") or "").upper()
            history_status = str(detail.get("candidate_replay_history_status") or "").upper()
            history_present = history_status not in {"", "NO_REPLAY_HISTORY"}
            history_budget_status = str(
                detail.get("candidate_replay_history_budget_status") or ""
            ).upper()
            history_next_action = (
                detail.get("candidate_replay_history_recommended_next_action")
                or "collect_more_dated_polymarket_replay_history_before_promotion"
            )
            history_execution_status = str(
                detail.get("candidate_replay_history_execution_realism_status") or ""
            ).upper()
            replay_extra = {
                "candidate_key": detail.get("candidate_key"),
                "candidate_replay_status": detail.get("candidate_replay_status"),
                "candidate_replay_sample_count": detail.get("candidate_replay_sample_count"),
                "candidate_replay_net_bps_mean": detail.get("candidate_replay_net_bps_mean"),
                "candidate_replay_holdout_net_bps_mean": detail.get(
                    "candidate_replay_holdout_net_bps_mean"
                ),
                "candidate_replay_cost_wall_status": detail.get(
                    "candidate_replay_cost_wall_status"
                ),
                "candidate_replay_execution_realism_status": detail.get(
                    "candidate_replay_execution_realism_status"
                ),
                "candidate_replay_history_status": detail.get(
                    "candidate_replay_history_status"
                ),
                "candidate_replay_history_reason": detail.get(
                    "candidate_replay_history_reason"
                ),
                "candidate_replay_history_report_count": detail.get(
                    "candidate_replay_history_report_count"
                ),
                "candidate_replay_history_matched_report_count": detail.get(
                    "candidate_replay_history_matched_report_count"
                ),
                "candidate_replay_history_sample_count": detail.get(
                    "candidate_replay_history_sample_count"
                ),
                "candidate_replay_history_n_days": detail.get(
                    "candidate_replay_history_n_days"
                ),
                "candidate_replay_history_min_days": detail.get(
                    "candidate_replay_history_min_days"
                ),
                "candidate_replay_history_min_samples": detail.get(
                    "candidate_replay_history_min_samples"
                ),
                "candidate_replay_history_days_remaining": detail.get(
                    "candidate_replay_history_days_remaining"
                ),
                "candidate_replay_history_calendar_span_days": detail.get(
                    "candidate_replay_history_calendar_span_days"
                ),
                "candidate_replay_history_date_gap_count": detail.get(
                    "candidate_replay_history_date_gap_count"
                ),
                "candidate_replay_history_earliest_ready_date": detail.get(
                    "candidate_replay_history_earliest_ready_date"
                ),
                "candidate_replay_history_pbo_day_count": detail.get(
                    "candidate_replay_history_pbo_day_count"
                ),
                "candidate_replay_history_net_bps_mean": detail.get(
                    "candidate_replay_history_net_bps_mean"
                ),
                "candidate_replay_history_holdout_net_bps_mean": detail.get(
                    "candidate_replay_history_holdout_net_bps_mean"
                ),
                "candidate_replay_history_positive_net_sample_rate": detail.get(
                    "candidate_replay_history_positive_net_sample_rate"
                ),
                "candidate_replay_history_interim_edge_status": detail.get(
                    "candidate_replay_history_interim_edge_status"
                ),
                "candidate_replay_history_budget_status": detail.get(
                    "candidate_replay_history_budget_status"
                ),
                "candidate_replay_history_recommended_next_action": detail.get(
                    "candidate_replay_history_recommended_next_action"
                ),
                "candidate_replay_history_execution_realism_status": detail.get(
                    "candidate_replay_history_execution_realism_status"
                ),
            }
            if replay_status != "PAPER_REPLAY_BUILT" and not history_present:
                return _finish_blocker_row(
                    row,
                    blocker_class="data_coverage",
                    primary_blocker="polymarket_candidate_replay_missing",
                    next_trigger="build_polymarket_candidate_replay_before_aeg_promotion",
                    engineering_actionable=True,
                    extra=replay_extra,
                )
            if history_status in {"", "NO_REPLAY_HISTORY"}:
                return _finish_blocker_row(
                    row,
                    blocker_class="data_coverage",
                    primary_blocker="polymarket_candidate_replay_history_missing",
                    next_trigger=(
                        "collect_dated_polymarket_replay_history_before_aeg_promotion"
                    ),
                    engineering_actionable=True,
                    extra=replay_extra,
                )
            if history_budget_status == "EARLY_ROTATE_RECOMMENDED":
                return _finish_blocker_row(
                    row,
                    blocker_class="rejected_no_edge",
                    primary_blocker=(
                        "polymarket_candidate_replay_history_interim_negative_edge"
                    ),
                    next_trigger=str(history_next_action),
                    engineering_actionable=False,
                    extra=replay_extra,
                )
            if history_status != "REPLAY_HISTORY_READY_FOR_AEG_RECHECK":
                return _finish_blocker_row(
                    row,
                    blocker_class="sample_gate",
                    primary_blocker="polymarket_candidate_replay_history_not_ready",
                    next_trigger=str(history_next_action),
                    engineering_actionable=True,
                    extra=replay_extra,
                )
            if history_execution_status in {"", "UNMEASURED", "UNVERIFIED", "MISSING"}:
                return _finish_blocker_row(
                    row,
                    blocker_class="robustness_wait",
                    primary_blocker="polymarket_execution_realism_unmeasured",
                    next_trigger=(
                        "build_polymarket_execution_realism_before_promotion"
                    ),
                    engineering_actionable=True,
                    extra=replay_extra,
                )
            if history_execution_status != "PASS":
                return _finish_blocker_row(
                    row,
                    blocker_class="robustness_wait",
                    primary_blocker="polymarket_execution_realism_not_passed",
                    next_trigger=(
                        "fix_or_reject_polymarket_execution_realism_before_promotion"
                    ),
                    engineering_actionable=True,
                    extra=replay_extra,
                )
        return _finish_blocker_row(
            row,
            blocker_class="candidate_review_ready",
            primary_blocker="candidate_artifacts_ready_need_aeg_chain",
            next_trigger="run_AEG_MIT_QC_chain_before_any_promotion",
            promotion_ready=True,
            engineering_actionable=True,
        )
    if (
        arm_id == "cost_gate_demo_learning_lane"
        and row["source_ok"] is not False
        and str(decision.get("reason")) != "source_not_healthy"
    ):
        state = _cost_gate_learning_lane_state(arm)
        ledger_status = str(detail.get("ledger_status") or "UNKNOWN")
        blocked_review = _dict(detail.get("blocked_signal_outcome_review"))
        blocked_review_status = str(
            detail.get("blocked_signal_outcome_review_status")
            or blocked_review.get("status")
            or ""
        )
        return _finish_blocker_row(
            row,
            blocker_class=str(state["blocker_class"]),
            primary_blocker=str(state["primary_blocker"]),
            next_trigger=str(state["next_trigger"]),
            operator_actionable=bool(state["operator_actionable"]),
            engineering_actionable=bool(state["engineering_actionable"]),
            extra={
                "plan_status": detail.get("plan_status"),
                "main_cost_gate_adjustment": detail.get("main_cost_gate_adjustment"),
                "learning_gate_adjustment": detail.get("learning_gate_adjustment"),
                "order_authority": detail.get("order_authority"),
                "probe_candidate_count": detail.get("probe_candidate_count"),
                "selected_probe_candidate_count": detail.get(
                    "selected_probe_candidate_count"
                ),
                "probe_budget": detail.get("probe_budget"),
                "probe_candidates": detail.get("probe_candidates"),
                "do_not_probe_side_cells": detail.get("do_not_probe_side_cells"),
                "data_coverage_tasks": detail.get("data_coverage_tasks"),
                "learning_lane_source_status": detail.get("learning_lane_source_status"),
                "learning_lane_source_ready": detail.get("learning_lane_source_ready"),
                "learning_lane_source_activation_status": detail.get(
                    "learning_lane_source_activation_status"
                ),
                "learning_lane_source_activation_ready": detail.get(
                    "learning_lane_source_activation_ready"
                ),
                "learning_lane_git_status": detail.get("learning_lane_git_status"),
                "learning_lane_git_head_short": detail.get("learning_lane_git_head_short"),
                "learning_lane_git_behind_count": detail.get("learning_lane_git_behind_count"),
                "learning_lane_git_dirty_path_count": detail.get(
                    "learning_lane_git_dirty_path_count"
                ),
                "learning_lane_expected_head_status": detail.get(
                    "learning_lane_expected_head_status"
                ),
                "learning_lane_expected_head_matches": detail.get(
                    "learning_lane_expected_head_matches"
                ),
                "demo_learning_stack_healthcheck_status": detail.get(
                    "demo_learning_stack_healthcheck_status"
                ),
                "demo_learning_stack_healthcheck_raw_status": detail.get(
                    "demo_learning_stack_healthcheck_raw_status"
                ),
                "demo_learning_stack_healthcheck_reason": detail.get(
                    "demo_learning_stack_healthcheck_reason"
                ),
                "demo_learning_stack_healthcheck_next_action": detail.get(
                    "demo_learning_stack_healthcheck_next_action"
                ),
                "demo_learning_stack_healthcheck_ts_utc": detail.get(
                    "demo_learning_stack_healthcheck_ts_utc"
                ),
                "demo_learning_stack_healthcheck_age_seconds": detail.get(
                    "demo_learning_stack_healthcheck_age_seconds"
                ),
                "demo_learning_stack_healthcheck_source_ok": detail.get(
                    "demo_learning_stack_healthcheck_source_ok"
                ),
                "demo_learning_stack_healthcheck_source_path": detail.get(
                    "demo_learning_stack_healthcheck_source_path"
                ),
                "demo_learning_stack_healthcheck_source_error": detail.get(
                    "demo_learning_stack_healthcheck_source_error"
                ),
                "demo_learning_stack_activation_packet_present": detail.get(
                    "demo_learning_stack_activation_packet_present"
                ),
                "demo_learning_stack_activation_packet_status": detail.get(
                    "demo_learning_stack_activation_packet_status"
                ),
                "demo_learning_stack_activation_packet_raw_status": detail.get(
                    "demo_learning_stack_activation_packet_raw_status"
                ),
                "demo_learning_stack_activation_packet_reason": detail.get(
                    "demo_learning_stack_activation_packet_reason"
                ),
                "demo_learning_stack_activation_packet_operator_next_action": detail.get(
                    "demo_learning_stack_activation_packet_operator_next_action"
                ),
                "demo_learning_stack_activation_packet_install_review_ready": detail.get(
                    "demo_learning_stack_activation_packet_install_review_ready"
                ),
                "demo_learning_stack_activation_packet_missing_links": detail.get(
                    "demo_learning_stack_activation_packet_missing_links"
                ),
                "demo_learning_stack_activation_packet_generated_at_utc": detail.get(
                    "demo_learning_stack_activation_packet_generated_at_utc"
                ),
                "demo_learning_stack_activation_packet_age_seconds": detail.get(
                    "demo_learning_stack_activation_packet_age_seconds"
                ),
                "demo_learning_stack_activation_packet_source_ok": detail.get(
                    "demo_learning_stack_activation_packet_source_ok"
                ),
                "demo_learning_stack_activation_packet_source_path": detail.get(
                    "demo_learning_stack_activation_packet_source_path"
                ),
                "demo_learning_stack_activation_packet_source_error": detail.get(
                    "demo_learning_stack_activation_packet_source_error"
                ),
                "demo_learning_stack_activation_packet_source_ready": detail.get(
                    "demo_learning_stack_activation_packet_source_ready"
                ),
                "demo_learning_stack_activation_packet_stack_installed": detail.get(
                    "demo_learning_stack_activation_packet_stack_installed"
                ),
                "demo_learning_stack_activation_packet_missing_cron_count": detail.get(
                    "demo_learning_stack_activation_packet_missing_cron_count"
                ),
                "demo_learning_stack_activation_packet_missing_crons": detail.get(
                    "demo_learning_stack_activation_packet_missing_crons"
                ),
                "demo_learning_stack_activation_packet_sealed_horizon_probe_preflight_present": detail.get(
                    "demo_learning_stack_activation_packet_sealed_horizon_probe_preflight_present"
                ),
                "demo_learning_stack_activation_packet_bounded_probe_reviews_present": detail.get(
                    "demo_learning_stack_activation_packet_bounded_probe_reviews_present"
                ),
                "demo_learning_stack_activation_packet_cost_gate_activation_ready": detail.get(
                    "demo_learning_stack_activation_packet_cost_gate_activation_ready"
                ),
                "demo_learning_stack_activation_packet_runtime_writer_enabled": detail.get(
                    "demo_learning_stack_activation_packet_runtime_writer_enabled"
                ),
                "demo_learning_stack_activation_packet_global_cost_gate_lowering_recommended": detail.get(
                    "demo_learning_stack_activation_packet_global_cost_gate_lowering_recommended"
                ),
                "demo_learning_stack_activation_packet_order_authority_granted": detail.get(
                    "demo_learning_stack_activation_packet_order_authority_granted"
                ),
                "demo_learning_stack_activation_packet_probe_authority_granted": detail.get(
                    "demo_learning_stack_activation_packet_probe_authority_granted"
                ),
                "demo_learning_stack_activation_packet_promotion_proof": detail.get(
                    "demo_learning_stack_activation_packet_promotion_proof"
                ),
                "demo_learning_stack_activation_packet_planned_cron_count": detail.get(
                    "demo_learning_stack_activation_packet_planned_cron_count"
                ),
                "demo_learning_stack_activation_packet_healthcheck_status": detail.get(
                    "demo_learning_stack_activation_packet_healthcheck_status"
                ),
                "demo_learning_stack_activation_packet_cost_gate_activation_status": detail.get(
                    "demo_learning_stack_activation_packet_cost_gate_activation_status"
                ),
                "demo_learning_stack_activation_packet_cost_gate_escape_thesis": detail.get(
                    "demo_learning_stack_activation_packet_cost_gate_escape_thesis"
                ),
                "demo_learning_stack_activation_packet_edge_amplification_levers": detail.get(
                    "demo_learning_stack_activation_packet_edge_amplification_levers"
                ),
                "demo_learning_stack_activation_packet_next_profit_gate_after_activation": detail.get(
                    "demo_learning_stack_activation_packet_next_profit_gate_after_activation"
                ),
                "demo_learning_stack_activation_packet_dry_run_preview_shell": detail.get(
                    "demo_learning_stack_activation_packet_dry_run_preview_shell"
                ),
                "demo_learning_stack_activation_packet_operator_only_apply_shell": detail.get(
                    "demo_learning_stack_activation_packet_operator_only_apply_shell"
                ),
                "demo_learning_stack_activation_packet_operator_only_rollback_shell": detail.get(
                    "demo_learning_stack_activation_packet_operator_only_rollback_shell"
                ),
                "demo_learning_stack_activation_packet_post_install_verification_shell": detail.get(
                    "demo_learning_stack_activation_packet_post_install_verification_shell"
                ),
                "demo_learning_stack_dry_run_review_present": detail.get(
                    "demo_learning_stack_dry_run_review_present"
                ),
                "demo_learning_stack_dry_run_review_status": detail.get(
                    "demo_learning_stack_dry_run_review_status"
                ),
                "demo_learning_stack_dry_run_review_raw_status": detail.get(
                    "demo_learning_stack_dry_run_review_raw_status"
                ),
                "demo_learning_stack_dry_run_review_reason": detail.get(
                    "demo_learning_stack_dry_run_review_reason"
                ),
                "demo_learning_stack_dry_run_review_operator_next_action": detail.get(
                    "demo_learning_stack_dry_run_review_operator_next_action"
                ),
                "demo_learning_stack_dry_run_review_generated_at_utc": detail.get(
                    "demo_learning_stack_dry_run_review_generated_at_utc"
                ),
                "demo_learning_stack_dry_run_review_age_seconds": detail.get(
                    "demo_learning_stack_dry_run_review_age_seconds"
                ),
                "demo_learning_stack_dry_run_review_source_ok": detail.get(
                    "demo_learning_stack_dry_run_review_source_ok"
                ),
                "demo_learning_stack_dry_run_review_source_path": detail.get(
                    "demo_learning_stack_dry_run_review_source_path"
                ),
                "demo_learning_stack_dry_run_review_source_error": detail.get(
                    "demo_learning_stack_dry_run_review_source_error"
                ),
                "demo_learning_stack_dry_run_review_expected_head": detail.get(
                    "demo_learning_stack_dry_run_review_expected_head"
                ),
                "demo_learning_stack_dry_run_review_activation_packet_status": detail.get(
                    "demo_learning_stack_dry_run_review_activation_packet_status"
                ),
                "demo_learning_stack_dry_run_review_activation_packet_missing_cron_count": detail.get(
                    "demo_learning_stack_dry_run_review_activation_packet_missing_cron_count"
                ),
                "demo_learning_stack_dry_run_review_dry_run_preview_executed": detail.get(
                    "demo_learning_stack_dry_run_review_dry_run_preview_executed"
                ),
                "demo_learning_stack_dry_run_review_dry_run_preview_passed": detail.get(
                    "demo_learning_stack_dry_run_review_dry_run_preview_passed"
                ),
                "demo_learning_stack_dry_run_review_crontab_mutated": detail.get(
                    "demo_learning_stack_dry_run_review_crontab_mutated"
                ),
                "demo_learning_stack_dry_run_review_operator_apply_required": detail.get(
                    "demo_learning_stack_dry_run_review_operator_apply_required"
                ),
                "demo_learning_stack_dry_run_review_global_cost_gate_lowering_recommended": detail.get(
                    "demo_learning_stack_dry_run_review_global_cost_gate_lowering_recommended"
                ),
                "demo_learning_stack_dry_run_review_order_authority_granted": detail.get(
                    "demo_learning_stack_dry_run_review_order_authority_granted"
                ),
                "demo_learning_stack_dry_run_review_probe_authority_granted": detail.get(
                    "demo_learning_stack_dry_run_review_probe_authority_granted"
                ),
                "demo_learning_stack_dry_run_review_promotion_proof": detail.get(
                    "demo_learning_stack_dry_run_review_promotion_proof"
                ),
                "demo_learning_stack_dry_run_review_returncode": detail.get(
                    "demo_learning_stack_dry_run_review_returncode"
                ),
                "demo_learning_stack_dry_run_review_run_error": detail.get(
                    "demo_learning_stack_dry_run_review_run_error"
                ),
                "demo_learning_stack_dry_run_review_forced_apply_gate": detail.get(
                    "demo_learning_stack_dry_run_review_forced_apply_gate"
                ),
                "demo_learning_stack_dry_run_review_preinstall_refresh": detail.get(
                    "demo_learning_stack_dry_run_review_preinstall_refresh"
                ),
                "demo_learning_stack_dry_run_review_mutates_crontab": detail.get(
                    "demo_learning_stack_dry_run_review_mutates_crontab"
                ),
                "demo_learning_stack_dry_run_review_dry_run_preview_shell": detail.get(
                    "demo_learning_stack_dry_run_review_dry_run_preview_shell"
                ),
                "demo_learning_stack_dry_run_review_operator_only_apply_shell": detail.get(
                    "demo_learning_stack_dry_run_review_operator_only_apply_shell"
                ),
                "demo_learning_stack_dry_run_review_operator_only_rollback_shell": detail.get(
                    "demo_learning_stack_dry_run_review_operator_only_rollback_shell"
                ),
                "demo_learning_stack_source_ready": detail.get(
                    "demo_learning_stack_source_ready"
                ),
                "demo_learning_stack_stack_installed": detail.get(
                    "demo_learning_stack_stack_installed"
                ),
                "demo_learning_stack_demo_learning_evidence_cron_entry_present": detail.get(
                    "demo_learning_stack_demo_learning_evidence_cron_entry_present"
                ),
                "demo_learning_stack_sealed_horizon_probe_preflight_cron_entry_present": detail.get(
                    "demo_learning_stack_sealed_horizon_probe_preflight_cron_entry_present"
                ),
                "demo_learning_stack_cost_gate_learning_lane_cron_entry_present": detail.get(
                    "demo_learning_stack_cost_gate_learning_lane_cron_entry_present"
                ),
                "demo_learning_stack_healthcheck_cron_entry_present": detail.get(
                    "demo_learning_stack_healthcheck_cron_entry_present"
                ),
                "demo_learning_stack_heartbeats_recent": detail.get(
                    "demo_learning_stack_heartbeats_recent"
                ),
                "demo_learning_stack_demo_learning_evidence_heartbeat_recent": detail.get(
                    "demo_learning_stack_demo_learning_evidence_heartbeat_recent"
                ),
                "demo_learning_stack_sealed_horizon_probe_preflight_heartbeat_recent": detail.get(
                    "demo_learning_stack_sealed_horizon_probe_preflight_heartbeat_recent"
                ),
                "demo_learning_stack_cost_gate_learning_lane_heartbeat_recent": detail.get(
                    "demo_learning_stack_cost_gate_learning_lane_heartbeat_recent"
                ),
                "demo_learning_stack_statuses_recent": detail.get(
                    "demo_learning_stack_statuses_recent"
                ),
                "demo_learning_stack_demo_learning_evidence_status_recent": detail.get(
                    "demo_learning_stack_demo_learning_evidence_status_recent"
                ),
                "demo_learning_stack_sealed_horizon_probe_preflight_status_recent": detail.get(
                    "demo_learning_stack_sealed_horizon_probe_preflight_status_recent"
                ),
                "demo_learning_stack_cost_gate_learning_lane_status_recent": detail.get(
                    "demo_learning_stack_cost_gate_learning_lane_status_recent"
                ),
                "demo_learning_stack_latest_artifacts_present": detail.get(
                    "demo_learning_stack_latest_artifacts_present"
                ),
                "demo_learning_stack_sealed_horizon_probe_preflight_present": detail.get(
                    "demo_learning_stack_sealed_horizon_probe_preflight_present"
                ),
                "demo_learning_stack_bounded_probe_reviews_present": detail.get(
                    "demo_learning_stack_bounded_probe_reviews_present"
                ),
                "demo_learning_stack_bounded_probe_result_review_present": detail.get(
                    "demo_learning_stack_bounded_probe_result_review_present"
                ),
                "demo_learning_stack_bounded_probe_execution_realism_review_present": detail.get(
                    "demo_learning_stack_bounded_probe_execution_realism_review_present"
                ),
                "demo_learning_stack_bounded_probe_result_review_status": detail.get(
                    "demo_learning_stack_bounded_probe_result_review_status"
                ),
                "demo_learning_stack_bounded_probe_execution_realism_review_status": detail.get(
                    "demo_learning_stack_bounded_probe_execution_realism_review_status"
                ),
                "demo_learning_stack_bounded_probe_result_review_skip_reason": detail.get(
                    "demo_learning_stack_bounded_probe_result_review_skip_reason"
                ),
                "demo_learning_stack_bounded_probe_execution_realism_review_skip_reason": detail.get(
                    "demo_learning_stack_bounded_probe_execution_realism_review_skip_reason"
                ),
                "demo_learning_stack_cost_gate_learning_stage_error": detail.get(
                    "demo_learning_stack_cost_gate_learning_stage_error"
                ),
                "demo_learning_stack_cost_gate_learning_ledger_rows_present": detail.get(
                    "demo_learning_stack_cost_gate_learning_ledger_rows_present"
                ),
                "demo_learning_stack_blocked_signal_outcomes_present": detail.get(
                    "demo_learning_stack_blocked_signal_outcomes_present"
                ),
                "demo_learning_stack_blocked_outcome_review_present": detail.get(
                    "demo_learning_stack_blocked_outcome_review_present"
                ),
                "demo_learning_stack_demo_learning_evidence_classification_status": detail.get(
                    "demo_learning_stack_demo_learning_evidence_classification_status"
                ),
                "demo_learning_stack_cost_gate_learning_review_status": detail.get(
                    "demo_learning_stack_cost_gate_learning_review_status"
                ),
                "demo_learning_evidence_status": detail.get(
                    "demo_learning_evidence_status"
                ),
                "demo_learning_evidence_classification_status": detail.get(
                    "demo_learning_evidence_classification_status"
                ),
                "demo_learning_evidence_reason": detail.get(
                    "demo_learning_evidence_reason"
                ),
                "demo_learning_evidence_next_action": detail.get(
                    "demo_learning_evidence_next_action"
                ),
                "demo_learning_evidence_generated_at_utc": detail.get(
                    "demo_learning_evidence_generated_at_utc"
                ),
                "demo_learning_evidence_age_seconds": detail.get(
                    "demo_learning_evidence_age_seconds"
                ),
                "demo_learning_evidence_source_ok": detail.get(
                    "demo_learning_evidence_source_ok"
                ),
                "demo_learning_evidence_source_path": detail.get(
                    "demo_learning_evidence_source_path"
                ),
                "demo_learning_evidence_source_error": detail.get(
                    "demo_learning_evidence_source_error"
                ),
                "demo_learning_evidence_order_stall_status": detail.get(
                    "demo_learning_evidence_order_stall_status"
                ),
                "demo_learning_evidence_preflight_status": detail.get(
                    "demo_learning_evidence_preflight_status"
                ),
                "demo_learning_evidence_cost_gate_rejects_recorded_in_pg": detail.get(
                    "demo_learning_evidence_cost_gate_rejects_recorded_in_pg"
                ),
                "demo_learning_evidence_observation_only_contexts_active": detail.get(
                    "demo_learning_evidence_observation_only_contexts_active"
                ),
                "demo_learning_evidence_candidate_or_reject_data_accumulating": detail.get(
                    "demo_learning_evidence_candidate_or_reject_data_accumulating"
                ),
                "demo_learning_evidence_currently_accumulating": detail.get(
                    "demo_learning_evidence_currently_accumulating"
                ),
                "demo_learning_evidence_blocked_outcome_review_candidate_present": detail.get(
                    "demo_learning_evidence_blocked_outcome_review_candidate_present"
                ),
                "demo_learning_evidence_order_flow_silent_drop_risk": detail.get(
                    "demo_learning_evidence_order_flow_silent_drop_risk"
                ),
                "demo_learning_evidence_order_flow_evidence_status": detail.get(
                    "demo_learning_evidence_order_flow_evidence_status"
                ),
                "demo_learning_evidence_order_flow_evidence_reason": detail.get(
                    "demo_learning_evidence_order_flow_evidence_reason"
                ),
                "demo_learning_evidence_order_flow_evidence_next_action": detail.get(
                    "demo_learning_evidence_order_flow_evidence_next_action"
                ),
                "demo_learning_evidence_recent_order_flow_present": detail.get(
                    "demo_learning_evidence_recent_order_flow_present"
                ),
                "demo_learning_evidence_recent_fill_evidence_present": detail.get(
                    "demo_learning_evidence_recent_fill_evidence_present"
                ),
                "demo_learning_evidence_order_flow_evidence_starved": detail.get(
                    "demo_learning_evidence_order_flow_evidence_starved"
                ),
                "demo_learning_evidence_cost_gate_adjustment_recommendation_status": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_recommendation_status"
                ),
                "demo_learning_evidence_cost_gate_adjustment_recommendation_reason": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_recommendation_reason"
                ),
                "demo_learning_evidence_cost_gate_adjustment_recommendation_next_action": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_recommendation_next_action"
                ),
                "demo_learning_evidence_cost_gate_learning_gate_adjustment": detail.get(
                    "demo_learning_evidence_cost_gate_learning_gate_adjustment"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_preflight_blocking": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_preflight_blocking"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_activation_ready": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_activation_ready"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_activation_blockers": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_activation_blockers"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_source_activation_ready": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_source_activation_ready"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_source_activation_status": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_source_activation_status"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_required": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_required"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_enabled": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_enabled"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_status": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_status"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_required": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_required"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_enabled": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_enabled"
                ),
                "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_status": detail.get(
                    "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_status"
                ),
                "demo_learning_evidence_data_flow_freshness_status": detail.get(
                    "demo_learning_evidence_data_flow_freshness_status"
                ),
                "demo_learning_evidence_latest_learning_stage": detail.get(
                    "demo_learning_evidence_latest_learning_stage"
                ),
                "demo_learning_evidence_latest_learning_ts_utc": detail.get(
                    "demo_learning_evidence_latest_learning_ts_utc"
                ),
                "demo_learning_evidence_latest_learning_age_seconds": detail.get(
                    "demo_learning_evidence_latest_learning_age_seconds"
                ),
                "demo_learning_evidence_learning_data_flow_fresh": detail.get(
                    "demo_learning_evidence_learning_data_flow_fresh"
                ),
                "demo_learning_evidence_learning_data_flow_stale": detail.get(
                    "demo_learning_evidence_learning_data_flow_stale"
                ),
                "demo_learning_evidence_contexts": detail.get(
                    "demo_learning_evidence_contexts"
                ),
                "demo_learning_evidence_risk_verdicts": detail.get(
                    "demo_learning_evidence_risk_verdicts"
                ),
                "demo_learning_evidence_learning_ledger_rows": detail.get(
                    "demo_learning_evidence_learning_ledger_rows"
                ),
                "demo_learning_evidence_blocked_signal_outcomes": detail.get(
                    "demo_learning_evidence_blocked_signal_outcomes"
                ),
                "historical_scorecard_review_status": detail.get(
                    "historical_scorecard_review_status"
                ),
                "historical_scorecard_review_reason": detail.get(
                    "historical_scorecard_review_reason"
                ),
                "historical_scorecard_review_next_trigger": detail.get(
                    "historical_scorecard_review_next_trigger"
                ),
                "historical_scorecard_review_source_kind": detail.get(
                    "historical_scorecard_review_source_kind"
                ),
                "historical_scorecard_review_path": detail.get(
                    "historical_scorecard_review_path"
                ),
                "historical_scorecard_source_path": detail.get(
                    "historical_scorecard_source_path"
                ),
                "historical_candidate_side_cell_count": detail.get(
                    "historical_candidate_side_cell_count"
                ),
                "historical_keep_blocked_side_cell_count": detail.get(
                    "historical_keep_blocked_side_cell_count"
                ),
                "historical_data_coverage_task_count": detail.get(
                    "historical_data_coverage_task_count"
                ),
                "historical_counterfactual_is_runtime_evidence": detail.get(
                    "historical_counterfactual_is_runtime_evidence"
                ),
                "historical_scorecard_review": detail.get(
                    "historical_scorecard_review"
                ),
                "ledger_status": ledger_status,
                "ledger_path": detail.get("ledger_path"),
                "ledger_source_error": detail.get("ledger_source_error"),
                "ledger_total_rows": detail.get("ledger_total_rows"),
                "ledger_malformed_line_count": detail.get("ledger_malformed_line_count"),
                "learning_loop_status": detail.get("learning_loop_status"),
                "learning_loop_reason": detail.get("learning_loop_reason"),
                "learning_loop_max_age_seconds": detail.get(
                    "learning_loop_max_age_seconds"
                ),
                "learning_loop_heartbeat_present": detail.get(
                    "learning_loop_heartbeat_present"
                ),
                "learning_loop_heartbeat_age_seconds": detail.get(
                    "learning_loop_heartbeat_age_seconds"
                ),
                "learning_loop_status_age_seconds": detail.get(
                    "learning_loop_status_age_seconds"
                ),
                "learning_loop_last_scorecard_rc": detail.get(
                    "learning_loop_last_scorecard_rc"
                ),
                "learning_loop_refresh_scorecard_enabled": detail.get(
                    "learning_loop_refresh_scorecard_enabled"
                ),
                "learning_loop_last_scorecard_status": detail.get(
                    "learning_loop_last_scorecard_status"
                ),
                "learning_loop_last_scorecard_probe_candidate_count": detail.get(
                    "learning_loop_last_scorecard_probe_candidate_count"
                ),
                "learning_loop_last_scorecard_horizon_stability_status": detail.get(
                    "learning_loop_last_scorecard_horizon_stability_status"
                ),
                "learning_loop_last_scorecard_horizon_stability_next_trigger": (
                    detail.get(
                        "learning_loop_last_scorecard_horizon_stability_next_trigger"
                    )
                ),
                "learning_loop_last_scorecard_horizon_stability_horizons": detail.get(
                    "learning_loop_last_scorecard_horizon_stability_horizons"
                ),
                "learning_loop_last_plan_rc": detail.get(
                    "learning_loop_last_plan_rc"
                ),
                "learning_loop_refresh_plan_enabled": detail.get(
                    "learning_loop_refresh_plan_enabled"
                ),
                "learning_loop_last_plan_policy_status": detail.get(
                    "learning_loop_last_plan_policy_status"
                ),
                "learning_loop_last_plan_gate_status": detail.get(
                    "learning_loop_last_plan_gate_status"
                ),
                "learning_loop_last_plan_selected_probe_candidate_count": detail.get(
                    "learning_loop_last_plan_selected_probe_candidate_count"
                ),
                "learning_loop_last_refresh_rc": detail.get(
                    "learning_loop_last_refresh_rc"
                ),
                "learning_loop_last_review_rc": detail.get(
                    "learning_loop_last_review_rc"
                ),
                "learning_loop_last_ledger_row_count": detail.get(
                    "learning_loop_last_ledger_row_count"
                ),
                "learning_loop_last_materializer_rc": detail.get(
                    "learning_loop_last_materializer_rc"
                ),
                "learning_loop_materialize_rejects_enabled": detail.get(
                    "learning_loop_materialize_rejects_enabled"
                ),
                "learning_loop_append_materialized_rejects_enabled": detail.get(
                    "learning_loop_append_materialized_rejects_enabled"
                ),
                "learning_loop_last_materializer_status": detail.get(
                    "learning_loop_last_materializer_status"
                ),
                "learning_loop_last_materializer_input_feature_row_count": detail.get(
                    "learning_loop_last_materializer_input_feature_row_count"
                ),
                "learning_loop_last_materialized_record_count": detail.get(
                    "learning_loop_last_materialized_record_count"
                ),
                "learning_loop_last_appended_materialized_record_count": detail.get(
                    "learning_loop_last_appended_materialized_record_count"
                ),
                "learning_loop_last_materializer_decision_counts": detail.get(
                    "learning_loop_last_materializer_decision_counts"
                ),
                "learning_loop_last_review_status": detail.get(
                    "learning_loop_last_review_status"
                ),
                "learning_loop_last_review_next_trigger": detail.get(
                    "learning_loop_last_review_next_trigger"
                ),
                "learning_loop_status_log_path": detail.get(
                    "learning_loop_status_log_path"
                ),
                "learning_loop_heartbeat_path": detail.get(
                    "learning_loop_heartbeat_path"
                ),
                "learning_loop_refresh_latest_path": detail.get(
                    "learning_loop_refresh_latest_path"
                ),
                "learning_loop_materializer_latest_path": detail.get(
                    "learning_loop_materializer_latest_path"
                ),
                "learning_loop_materializer_latest_error": detail.get(
                    "learning_loop_materializer_latest_error"
                ),
                "learning_loop_review_latest_path": detail.get(
                    "learning_loop_review_latest_path"
                ),
                "admission_decision_count": detail.get("admission_decision_count"),
                "capture_error_count": detail.get("capture_error_count"),
                "captured_reject_count": detail.get("captured_reject_count"),
                "latest_capture_error": detail.get("latest_capture_error"),
                "admit_decision_count": detail.get("admit_decision_count"),
                "order_authority_not_granted_count": detail.get(
                    "order_authority_not_granted_count"
                ),
                "allowed_to_submit_order_count": detail.get("allowed_to_submit_order_count"),
                "probe_outcome_count": detail.get("probe_outcome_count"),
                "blocked_signal_outcome_count": detail.get(
                    "blocked_signal_outcome_count"
                ),
                "blocked_signal_positive_outcome_count": detail.get(
                    "blocked_signal_positive_outcome_count"
                ),
                "avg_probe_outcome_net_bps": detail.get("avg_probe_outcome_net_bps"),
                "avg_blocked_signal_outcome_net_bps": detail.get(
                    "avg_blocked_signal_outcome_net_bps"
                ),
                "blocked_signal_net_positive_pct": detail.get(
                    "blocked_signal_net_positive_pct"
                ),
                "blocked_signal_outcome_review_status": blocked_review_status or None,
                "blocked_signal_outcome_review_reason": detail.get(
                    "blocked_signal_outcome_review_reason"
                ) or blocked_review.get("reason"),
                "blocked_signal_outcome_review_next_trigger": detail.get(
                    "blocked_signal_outcome_review_next_trigger"
                ) or blocked_review.get("next_trigger"),
                "blocked_signal_outcome_review_schema_version": detail.get(
                    "blocked_signal_outcome_review_schema_version"
                ) or blocked_review.get("schema_version"),
                "blocked_signal_top_review_side_cell_key": detail.get(
                    "blocked_signal_top_review_side_cell_key"
                ) or blocked_review.get("top_side_cell_key"),
                "blocked_signal_top_review_status": detail.get(
                    "blocked_signal_top_review_status"
                ) or blocked_review.get("top_side_cell_status"),
                "blocked_signal_top_review_wrongful_block_score": detail.get(
                    "blocked_signal_top_review_wrongful_block_score"
                ) or blocked_review.get("top_side_cell_wrongful_block_score"),
                "blocked_signal_top_review_net_cost_cushion_bps": detail.get(
                    "blocked_signal_top_review_net_cost_cushion_bps"
                ) or blocked_review.get("top_side_cell_net_cost_cushion_bps"),
                "blocked_signal_top_review_candidate_side_cell_key": detail.get(
                    "blocked_signal_top_review_candidate_side_cell_key"
                ) or blocked_review.get("top_review_candidate_side_cell_key"),
                "blocked_signal_top_review_candidate_wrongful_block_score": detail.get(
                    "blocked_signal_top_review_candidate_wrongful_block_score"
                ) or blocked_review.get("top_review_candidate_wrongful_block_score"),
                "blocked_signal_top_review_candidate_net_cost_cushion_bps": detail.get(
                    "blocked_signal_top_review_candidate_net_cost_cushion_bps"
                ) or blocked_review.get("top_review_candidate_net_cost_cushion_bps"),
                "blocked_signal_outcome_review": blocked_review or None,
                "profit_learning_decision_packet_status": detail.get(
                    "profit_learning_decision_packet_status"
                ),
                "profit_learning_decision_packet_reason": detail.get(
                    "profit_learning_decision_packet_reason"
                ),
                "profit_learning_decision_packet_next_actions": detail.get(
                    "profit_learning_decision_packet_next_actions"
                ),
                "profit_learning_decision_packet_generated_at_utc": detail.get(
                    "profit_learning_decision_packet_generated_at_utc"
                ),
                "profit_learning_decision_packet_age_seconds": detail.get(
                    "profit_learning_decision_packet_age_seconds"
                ),
                "profit_learning_decision_packet_source_ok": detail.get(
                    "profit_learning_decision_packet_source_ok"
                ),
                "profit_learning_decision_packet_source_path": detail.get(
                    "profit_learning_decision_packet_source_path"
                ),
                "profit_learning_decision_packet_source_error": detail.get(
                    "profit_learning_decision_packet_source_error"
                ),
                "profit_learning_cost_gate_rejects_recorded": detail.get(
                    "profit_learning_cost_gate_rejects_recorded"
                ),
                "profit_learning_silent_drop_risk": detail.get(
                    "profit_learning_silent_drop_risk"
                ),
                "profit_learning_counterfactual_scorecard_available": detail.get(
                    "profit_learning_counterfactual_scorecard_available"
                ),
                "profit_learning_counterfactual_learning_candidates_present": detail.get(
                    "profit_learning_counterfactual_learning_candidates_present"
                ),
                "profit_learning_bounded_plan_ready": detail.get(
                    "profit_learning_bounded_plan_ready"
                ),
                "profit_learning_blocked_outcome_review_candidates_present": detail.get(
                    "profit_learning_blocked_outcome_review_candidates_present"
                ),
                "profit_learning_sealed_horizon_learning_evidence_available": (
                    detail.get(
                        "profit_learning_sealed_horizon_learning_evidence_available"
                    )
                ),
                "profit_learning_sealed_horizon_learning_evidence_candidates_present": (
                    detail.get(
                        "profit_learning_sealed_horizon_learning_evidence_candidates_present"
                    )
                ),
                "profit_learning_global_cost_gate_lowering_recommended": detail.get(
                    "profit_learning_global_cost_gate_lowering_recommended"
                ),
                "profit_learning_order_authority_granted": detail.get(
                    "profit_learning_order_authority_granted"
                ),
                "profit_learning_main_cost_gate_adjustment": detail.get(
                    "profit_learning_main_cost_gate_adjustment"
                ),
                "profit_learning_promotion_evidence": detail.get(
                    "profit_learning_promotion_evidence"
                ),
                "profit_learning_data_flow_status": detail.get(
                    "profit_learning_data_flow_status"
                ),
                "profit_learning_counterfactual_ranking_status": detail.get(
                    "profit_learning_counterfactual_ranking_status"
                ),
                "profit_learning_counterfactual_horizon_stability_status": detail.get(
                    "profit_learning_counterfactual_horizon_stability_status"
                ),
                "profit_learning_counterfactual_candidate_count": detail.get(
                    "profit_learning_counterfactual_candidate_count"
                ),
                "profit_learning_top_side_cells": detail.get(
                    "profit_learning_top_side_cells"
                ),
                "profit_learning_activation_status": detail.get(
                    "profit_learning_activation_status"
                ),
                "profit_learning_blocked_review_status": detail.get(
                    "profit_learning_blocked_review_status"
                ),
                "profit_learning_sealed_horizon_learning_evidence_status": detail.get(
                    "profit_learning_sealed_horizon_learning_evidence_status"
                ),
                "profit_learning_sealed_horizon_side_cell_key": detail.get(
                    "profit_learning_sealed_horizon_side_cell_key"
                ),
                "profit_learning_sealed_horizon_source_kind": detail.get(
                    "profit_learning_sealed_horizon_source_kind"
                ),
                "profit_learning_sealed_horizon_outcome_horizon_minutes": detail.get(
                    "profit_learning_sealed_horizon_outcome_horizon_minutes"
                ),
                "profit_learning_sealed_horizon_blocked_signal_outcome_count": (
                    detail.get(
                        "profit_learning_sealed_horizon_blocked_signal_outcome_count"
                    )
                ),
                "profit_learning_sealed_horizon_avg_gross_bps": detail.get(
                    "profit_learning_sealed_horizon_avg_gross_bps"
                ),
                "profit_learning_sealed_horizon_avg_net_bps": detail.get(
                    "profit_learning_sealed_horizon_avg_net_bps"
                ),
                "profit_learning_sealed_horizon_net_positive_pct": detail.get(
                    "profit_learning_sealed_horizon_net_positive_pct"
                ),
                "profit_learning_sealed_horizon_review_ready": detail.get(
                    "profit_learning_sealed_horizon_review_ready"
                ),
                "profit_learning_sealed_horizon_top_side_cell_status": detail.get(
                    "profit_learning_sealed_horizon_top_side_cell_status"
                ),
                "profitability_path_scorecard_status": detail.get(
                    "profitability_path_scorecard_status"
                ),
                "profitability_path_scorecard_source_ok": detail.get(
                    "profitability_path_scorecard_source_ok"
                ),
                "profitability_path_scorecard_source_path": detail.get(
                    "profitability_path_scorecard_source_path"
                ),
                "profitability_path_count": detail.get("profitability_path_count"),
                "profitability_cost_gate_crossing_candidate_count": detail.get(
                    "profitability_cost_gate_crossing_candidate_count"
                ),
                "profitability_top_path_id": detail.get("profitability_top_path_id"),
                "profitability_top_path_status": detail.get(
                    "profitability_top_path_status"
                ),
                "profitability_top_path_next_action": detail.get(
                    "profitability_top_path_next_action"
                ),
                "profitability_cost_gate_crossing_candidates_present": detail.get(
                    "profitability_cost_gate_crossing_candidates_present"
                ),
                "profitability_alpha_or_edge_amplification_paths_present": detail.get(
                    "profitability_alpha_or_edge_amplification_paths_present"
                ),
                "profitability_global_cost_gate_lowering_recommended": detail.get(
                    "profitability_global_cost_gate_lowering_recommended"
                ),
                "profitability_order_authority_granted": detail.get(
                    "profitability_order_authority_granted"
                ),
                "profitability_main_cost_gate_adjustment": detail.get(
                    "profitability_main_cost_gate_adjustment"
                ),
                "profitability_promotion_evidence": detail.get(
                    "profitability_promotion_evidence"
                ),
                "profitability_engineering_closure_status": detail.get(
                    "profitability_engineering_closure_status"
                ),
                "profitability_leading_path_id": detail.get(
                    "profitability_leading_path_id"
                ),
                "profitability_leading_path_class": detail.get(
                    "profitability_leading_path_class"
                ),
                "profitability_leading_candidate_key": detail.get(
                    "profitability_leading_candidate_key"
                ),
                "profitability_proof_gate_count_remaining": detail.get(
                    "profitability_proof_gate_count_remaining"
                ),
                "profitability_proof_gates_remaining": detail.get(
                    "profitability_proof_gates_remaining"
                ),
                "profitability_next_actions": detail.get(
                    "profitability_next_actions"
                ),
                "profitability_edge_amplification_levers": detail.get(
                    "profitability_edge_amplification_levers"
                ),
                "profitability_cost_gate_root_blockers": detail.get(
                    "profitability_cost_gate_root_blockers"
                ),
                "profitability_primary_cost_gate_root_blocker": detail.get(
                    "profitability_primary_cost_gate_root_blocker"
                ),
                "profitability_edge_amplification_backlog": detail.get(
                    "profitability_edge_amplification_backlog"
                ),
                "profitability_next_move_class": detail.get(
                    "profitability_next_move_class"
                ),
                "profitability_next_move_primary_objective": detail.get(
                    "profitability_next_move_primary_objective"
                ),
                "profitability_next_move_recommended_action": detail.get(
                    "profitability_next_move_recommended_action"
                ),
                "profitability_next_move_candidate_key": detail.get(
                    "profitability_next_move_candidate_key"
                ),
                "profitability_next_move_edge_above_cost_bps": detail.get(
                    "profitability_next_move_edge_above_cost_bps"
                ),
                "profitability_next_move_runtime_mutation_required": detail.get(
                    "profitability_next_move_runtime_mutation_required"
                ),
                "profitability_cost_gate_escape_method": detail.get(
                    "profitability_cost_gate_escape_method"
                ),
                "profitability_cost_gate_escape_global_cost_gate_lowering": detail.get(
                    "profitability_cost_gate_escape_global_cost_gate_lowering"
                ),
                "profitability_cost_gate_escape_probe_authority_granted": detail.get(
                    "profitability_cost_gate_escape_probe_authority_granted"
                ),
                "profitability_cost_gate_escape_order_authority_granted": detail.get(
                    "profitability_cost_gate_escape_order_authority_granted"
                ),
                "profitability_cost_gate_escape_promotion_evidence": detail.get(
                    "profitability_cost_gate_escape_promotion_evidence"
                ),
                "profitability_cost_gate_escape_operator_authorization_status": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_status"
                ),
                "profitability_cost_gate_escape_operator_authorization_decision": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_decision"
                ),
                "profitability_cost_gate_escape_operator_authorization_blocking_gate_count": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_blocking_gate_count"
                ),
                "profitability_cost_gate_escape_operator_authorization_blocking_gates": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_blocking_gates"
                ),
                "profitability_cost_gate_escape_operator_authorization_ready_for_review": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_ready_for_review"
                ),
                "profitability_cost_gate_escape_operator_authorization_object_emitted": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_object_emitted"
                ),
                "profitability_cost_gate_escape_operator_authorization_active_runtime_probe_authority": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_active_runtime_probe_authority"
                ),
                "profitability_cost_gate_escape_operator_authorization_active_runtime_order_authority": detail.get(
                    "profitability_cost_gate_escape_operator_authorization_active_runtime_order_authority"
                ),
                "sealed_horizon_probe_preflight_status": detail.get(
                    "sealed_horizon_probe_preflight_status"
                ),
                "sealed_horizon_probe_preflight_reason": detail.get(
                    "sealed_horizon_probe_preflight_reason"
                ),
                "sealed_horizon_probe_preflight_next_actions": detail.get(
                    "sealed_horizon_probe_preflight_next_actions"
                ),
                "sealed_horizon_probe_preflight_generated_at_utc": detail.get(
                    "sealed_horizon_probe_preflight_generated_at_utc"
                ),
                "sealed_horizon_probe_preflight_source_ok": detail.get(
                    "sealed_horizon_probe_preflight_source_ok"
                ),
                "sealed_horizon_probe_preflight_source_path": detail.get(
                    "sealed_horizon_probe_preflight_source_path"
                ),
                "sealed_horizon_probe_preflight_source_error": detail.get(
                    "sealed_horizon_probe_preflight_source_error"
                ),
                "sealed_horizon_probe_preflight_side_cell_key": detail.get(
                    "sealed_horizon_probe_preflight_side_cell_key"
                ),
                "sealed_horizon_probe_preflight_outcome_horizon_minutes": detail.get(
                    "sealed_horizon_probe_preflight_outcome_horizon_minutes"
                ),
                "sealed_horizon_probe_preflight_blocking_gate_count": detail.get(
                    "sealed_horizon_probe_preflight_blocking_gate_count"
                ),
                "sealed_horizon_probe_preflight_blocking_gates": detail.get(
                    "sealed_horizon_probe_preflight_blocking_gates"
                ),
                "sealed_horizon_probe_preflight_evidence_ready": detail.get(
                    "sealed_horizon_probe_preflight_evidence_ready"
                ),
                "sealed_horizon_probe_preflight_decision_packet_aligned": detail.get(
                    "sealed_horizon_probe_preflight_decision_packet_aligned"
                ),
                "sealed_horizon_probe_preflight_operator_review_recorded": detail.get(
                    "sealed_horizon_probe_preflight_operator_review_recorded"
                ),
                "sealed_horizon_probe_preflight_production_lane_accumulating": (
                    detail.get(
                        "sealed_horizon_probe_preflight_production_lane_accumulating"
                    )
                ),
                "sealed_horizon_probe_preflight_ready_for_operator_authorization": (
                    detail.get(
                        "sealed_horizon_probe_preflight_ready_for_operator_authorization"
                    )
                ),
                "sealed_horizon_probe_preflight_order_authority_granted": detail.get(
                    "sealed_horizon_probe_preflight_order_authority_granted"
                ),
                "sealed_horizon_probe_preflight_probe_authority_granted": detail.get(
                    "sealed_horizon_probe_preflight_probe_authority_granted"
                ),
                "sealed_horizon_probe_preflight_main_cost_gate_adjustment": detail.get(
                    "sealed_horizon_probe_preflight_main_cost_gate_adjustment"
                ),
                "sealed_horizon_probe_preflight_promotion_evidence": detail.get(
                    "sealed_horizon_probe_preflight_promotion_evidence"
                ),
                "bounded_probe_operator_authorization_present": detail.get(
                    "bounded_probe_operator_authorization_present"
                ),
                "bounded_probe_operator_authorization_status": detail.get(
                    "bounded_probe_operator_authorization_status"
                ),
                "bounded_probe_operator_authorization_reason": detail.get(
                    "bounded_probe_operator_authorization_reason"
                ),
                "bounded_probe_operator_authorization_decision": detail.get(
                    "bounded_probe_operator_authorization_decision"
                ),
                "bounded_probe_operator_authorization_next_actions": detail.get(
                    "bounded_probe_operator_authorization_next_actions"
                ),
                "bounded_probe_operator_authorization_generated_at_utc": detail.get(
                    "bounded_probe_operator_authorization_generated_at_utc"
                ),
                "bounded_probe_operator_authorization_source_ok": detail.get(
                    "bounded_probe_operator_authorization_source_ok"
                ),
                "bounded_probe_operator_authorization_source_path": detail.get(
                    "bounded_probe_operator_authorization_source_path"
                ),
                "bounded_probe_operator_authorization_source_error": detail.get(
                    "bounded_probe_operator_authorization_source_error"
                ),
                "bounded_probe_operator_authorization_side_cell_key": detail.get(
                    "bounded_probe_operator_authorization_side_cell_key"
                ),
                "bounded_probe_operator_authorization_outcome_horizon_minutes": (
                    detail.get(
                        "bounded_probe_operator_authorization_outcome_horizon_minutes"
                    )
                ),
                "bounded_probe_operator_authorization_source_candidate_max_probe_orders": (
                    detail.get(
                        "bounded_probe_operator_authorization_source_candidate_max_probe_orders"
                    )
                ),
                "bounded_probe_operator_authorization_requested_max_probe_orders": (
                    detail.get(
                        "bounded_probe_operator_authorization_requested_max_probe_orders"
                    )
                ),
                "bounded_probe_operator_authorization_blocking_gate_count": detail.get(
                    "bounded_probe_operator_authorization_blocking_gate_count"
                ),
                "bounded_probe_operator_authorization_blocking_gates": detail.get(
                    "bounded_probe_operator_authorization_blocking_gates"
                ),
                "bounded_probe_operator_authorization_typed_confirm_expected": (
                    detail.get(
                        "bounded_probe_operator_authorization_typed_confirm_expected"
                    )
                ),
                "bounded_probe_operator_authorization_ready_for_review": detail.get(
                    "bounded_probe_operator_authorization_ready_for_review"
                ),
                "bounded_probe_operator_authorization_bounded_demo_probe_authorized": (
                    detail.get(
                        "bounded_probe_operator_authorization_bounded_demo_probe_authorized"
                    )
                ),
                "bounded_probe_operator_authorization_object_emitted": detail.get(
                    "bounded_probe_operator_authorization_object_emitted"
                ),
                "bounded_probe_operator_authorization_active_runtime_order_authority": (
                    detail.get(
                        "bounded_probe_operator_authorization_active_runtime_order_authority"
                    )
                ),
                "bounded_probe_operator_authorization_active_runtime_probe_authority": (
                    detail.get(
                        "bounded_probe_operator_authorization_active_runtime_probe_authority"
                    )
                ),
                "bounded_probe_operator_authorization_global_cost_gate_lowering_recommended": (
                    detail.get(
                        "bounded_probe_operator_authorization_global_cost_gate_lowering_recommended"
                    )
                ),
                "bounded_probe_operator_authorization_main_cost_gate_adjustment": (
                    detail.get(
                        "bounded_probe_operator_authorization_main_cost_gate_adjustment"
                    )
                ),
                "bounded_probe_operator_authorization_promotion_evidence": detail.get(
                    "bounded_probe_operator_authorization_promotion_evidence"
                ),
                "bounded_probe_shadow_placement_impact_present": detail.get(
                    "bounded_probe_shadow_placement_impact_present"
                ),
                "bounded_probe_shadow_placement_impact_status": detail.get(
                    "bounded_probe_shadow_placement_impact_status"
                ),
                "bounded_probe_shadow_placement_impact_reason": detail.get(
                    "bounded_probe_shadow_placement_impact_reason"
                ),
                "bounded_probe_shadow_placement_impact_next_actions": detail.get(
                    "bounded_probe_shadow_placement_impact_next_actions"
                ),
                "bounded_probe_shadow_placement_impact_generated_at_utc": detail.get(
                    "bounded_probe_shadow_placement_impact_generated_at_utc"
                ),
                "bounded_probe_shadow_placement_impact_source_ok": detail.get(
                    "bounded_probe_shadow_placement_impact_source_ok"
                ),
                "bounded_probe_shadow_placement_impact_source_path": detail.get(
                    "bounded_probe_shadow_placement_impact_source_path"
                ),
                "bounded_probe_shadow_placement_impact_source_error": detail.get(
                    "bounded_probe_shadow_placement_impact_source_error"
                ),
                "bounded_probe_shadow_placement_side_cell_key": detail.get(
                    "bounded_probe_shadow_placement_side_cell_key"
                ),
                "bounded_probe_shadow_placement_sample_scope": detail.get(
                    "bounded_probe_shadow_placement_sample_scope"
                ),
                "bounded_probe_shadow_placement_reviewed_order_count": detail.get(
                    "bounded_probe_shadow_placement_reviewed_order_count"
                ),
                "bounded_probe_shadow_placement_submit_count": detail.get(
                    "bounded_probe_shadow_placement_submit_count"
                ),
                "bounded_probe_shadow_placement_skip_count": detail.get(
                    "bounded_probe_shadow_placement_skip_count"
                ),
                "bounded_probe_shadow_placement_candidate_matched_order_count": (
                    detail.get(
                        "bounded_probe_shadow_placement_candidate_matched_order_count"
                    )
                ),
                "bounded_probe_shadow_placement_candidate_matched_submit_count": (
                    detail.get(
                        "bounded_probe_shadow_placement_candidate_matched_submit_count"
                    )
                ),
                "bounded_probe_shadow_placement_future_bbo_cross_count": detail.get(
                    "bounded_probe_shadow_placement_future_bbo_cross_count"
                ),
                "bounded_probe_shadow_placement_max_original_best_touch_gap_bps": (
                    detail.get(
                        "bounded_probe_shadow_placement_max_original_best_touch_gap_bps"
                    )
                ),
                "bounded_probe_shadow_placement_max_initial_touch_gap_bps": (
                    detail.get(
                        "bounded_probe_shadow_placement_max_initial_touch_gap_bps"
                    )
                ),
                "bounded_probe_shadow_placement_avg_initial_touch_gap_bps": (
                    detail.get(
                        "bounded_probe_shadow_placement_avg_initial_touch_gap_bps"
                    )
                ),
                "bounded_probe_shadow_placement_max_gap_reduction_bps": detail.get(
                    "bounded_probe_shadow_placement_max_gap_reduction_bps"
                ),
                "bounded_probe_shadow_placement_improves_touchability": detail.get(
                    "bounded_probe_shadow_placement_improves_touchability"
                ),
                "bounded_probe_shadow_placement_candidate_matched_runtime_sample_present": detail.get(
                    "bounded_probe_shadow_placement_candidate_matched_runtime_sample_present"
                ),
                "bounded_probe_shadow_placement_candidate_specific_alpha_proof": (
                    detail.get(
                        "bounded_probe_shadow_placement_candidate_specific_alpha_proof"
                    )
                ),
                "bounded_probe_shadow_placement_order_authority_granted": detail.get(
                    "bounded_probe_shadow_placement_order_authority_granted"
                ),
                "bounded_probe_shadow_placement_probe_authority_granted": detail.get(
                    "bounded_probe_shadow_placement_probe_authority_granted"
                ),
                "bounded_probe_shadow_placement_main_cost_gate_adjustment": detail.get(
                    "bounded_probe_shadow_placement_main_cost_gate_adjustment"
                ),
                "bounded_probe_shadow_placement_promotion_evidence": detail.get(
                    "bounded_probe_shadow_placement_promotion_evidence"
                ),
                "bounded_probe_result_review_status": detail.get(
                    "bounded_probe_result_review_status"
                ),
                "bounded_probe_result_review_reason": detail.get(
                    "bounded_probe_result_review_reason"
                ),
                "bounded_probe_result_review_next_actions": detail.get(
                    "bounded_probe_result_review_next_actions"
                ),
                "bounded_probe_result_review_generated_at_utc": detail.get(
                    "bounded_probe_result_review_generated_at_utc"
                ),
                "bounded_probe_result_review_source_ok": detail.get(
                    "bounded_probe_result_review_source_ok"
                ),
                "bounded_probe_result_review_source_path": detail.get(
                    "bounded_probe_result_review_source_path"
                ),
                "bounded_probe_result_review_source_error": detail.get(
                    "bounded_probe_result_review_source_error"
                ),
                "bounded_probe_result_review_side_cell_key": detail.get(
                    "bounded_probe_result_review_side_cell_key"
                ),
                "bounded_probe_result_review_completed_probe_outcome_count": (
                    detail.get(
                        "bounded_probe_result_review_completed_probe_outcome_count"
                    )
                ),
                "bounded_probe_result_review_avg_realized_net_bps": detail.get(
                    "bounded_probe_result_review_avg_realized_net_bps"
                ),
                "bounded_probe_result_review_net_positive_pct": detail.get(
                    "bounded_probe_result_review_net_positive_pct"
                ),
                "bounded_probe_result_review_operator_review_required": detail.get(
                    "bounded_probe_result_review_operator_review_required"
                ),
                "bounded_probe_result_review_stop_probe_recommended": detail.get(
                    "bounded_probe_result_review_stop_probe_recommended"
                ),
                "bounded_probe_result_review_learning_review_candidate": detail.get(
                    "bounded_probe_result_review_learning_review_candidate"
                ),
                "bounded_probe_result_review_order_authority_granted": detail.get(
                    "bounded_probe_result_review_order_authority_granted"
                ),
                "bounded_probe_result_review_probe_authority_granted": detail.get(
                    "bounded_probe_result_review_probe_authority_granted"
                ),
                "bounded_probe_result_review_main_cost_gate_adjustment": detail.get(
                    "bounded_probe_result_review_main_cost_gate_adjustment"
                ),
                "bounded_probe_result_review_promotion_evidence": detail.get(
                    "bounded_probe_result_review_promotion_evidence"
                ),
                "bounded_probe_result_review_evidence_quality_status": detail.get(
                    "bounded_probe_result_review_evidence_quality_status"
                ),
                "bounded_probe_result_review_evidence_quality_reason": detail.get(
                    "bounded_probe_result_review_evidence_quality_reason"
                ),
                "bounded_probe_result_review_matched_control_required": detail.get(
                    "bounded_probe_result_review_matched_control_required"
                ),
                "bounded_probe_result_review_matched_control_present": detail.get(
                    "bounded_probe_result_review_matched_control_present"
                ),
                "bounded_probe_result_review_matched_control_outcome_count": detail.get(
                    "bounded_probe_result_review_matched_control_outcome_count"
                ),
                "bounded_probe_result_review_matched_control_avg_net_bps": detail.get(
                    "bounded_probe_result_review_matched_control_avg_net_bps"
                ),
                "bounded_probe_result_review_matched_control_net_positive_pct": detail.get(
                    "bounded_probe_result_review_matched_control_net_positive_pct"
                ),
                "bounded_probe_result_review_probe_minus_control_avg_net_bps": detail.get(
                    "bounded_probe_result_review_probe_minus_control_avg_net_bps"
                ),
                "bounded_probe_result_review_probe_edge_capture_ratio": detail.get(
                    "bounded_probe_result_review_probe_edge_capture_ratio"
                ),
                "bounded_probe_result_review_probe_execution_gap_bps": detail.get(
                    "bounded_probe_result_review_probe_execution_gap_bps"
                ),
                "bounded_probe_result_review_probe_outperforms_matched_control": detail.get(
                    "bounded_probe_result_review_probe_outperforms_matched_control"
                ),
                "bounded_probe_result_review_execution_realism_gap": detail.get(
                    "bounded_probe_result_review_execution_realism_gap"
                ),
                "bounded_probe_result_review_anecdote_risk": detail.get(
                    "bounded_probe_result_review_anecdote_risk"
                ),
                "bounded_probe_execution_realism_review_present": detail.get(
                    "bounded_probe_execution_realism_review_present"
                ),
                "bounded_probe_execution_realism_review_status": detail.get(
                    "bounded_probe_execution_realism_review_status"
                ),
                "bounded_probe_execution_realism_review_reason": detail.get(
                    "bounded_probe_execution_realism_review_reason"
                ),
                "bounded_probe_execution_realism_review_next_actions": detail.get(
                    "bounded_probe_execution_realism_review_next_actions"
                ),
                "bounded_probe_execution_realism_review_generated_at_utc": detail.get(
                    "bounded_probe_execution_realism_review_generated_at_utc"
                ),
                "bounded_probe_execution_realism_review_source_ok": detail.get(
                    "bounded_probe_execution_realism_review_source_ok"
                ),
                "bounded_probe_execution_realism_review_source_path": detail.get(
                    "bounded_probe_execution_realism_review_source_path"
                ),
                "bounded_probe_execution_realism_review_source_error": detail.get(
                    "bounded_probe_execution_realism_review_source_error"
                ),
                "bounded_probe_execution_realism_review_side_cell_key": detail.get(
                    "bounded_probe_execution_realism_review_side_cell_key"
                ),
                "bounded_probe_execution_realism_review_result_review_status": (
                    detail.get(
                        "bounded_probe_execution_realism_review_result_review_status"
                    )
                ),
                "bounded_probe_execution_realism_review_evidence_quality_status": (
                    detail.get(
                        "bounded_probe_execution_realism_review_evidence_quality_status"
                    )
                ),
                "bounded_probe_execution_realism_review_probe_edge_capture_ratio": (
                    detail.get(
                        "bounded_probe_execution_realism_review_probe_edge_capture_ratio"
                    )
                ),
                "bounded_probe_execution_realism_review_probe_execution_gap_bps": (
                    detail.get(
                        "bounded_probe_execution_realism_review_probe_execution_gap_bps"
                    )
                ),
                "bounded_probe_execution_realism_review_probe_avg_net_bps": detail.get(
                    "bounded_probe_execution_realism_review_probe_avg_net_bps"
                ),
                "bounded_probe_execution_realism_review_probe_avg_gross_bps": (
                    detail.get(
                        "bounded_probe_execution_realism_review_probe_avg_gross_bps"
                    )
                ),
                "bounded_probe_execution_realism_review_probe_avg_cost_bps": detail.get(
                    "bounded_probe_execution_realism_review_probe_avg_cost_bps"
                ),
                "bounded_probe_execution_realism_review_probe_fill_backed_pct": (
                    detail.get(
                        "bounded_probe_execution_realism_review_probe_fill_backed_pct"
                    )
                ),
                "bounded_probe_execution_realism_review_control_avg_net_bps": (
                    detail.get(
                        "bounded_probe_execution_realism_review_control_avg_net_bps"
                    )
                ),
                "bounded_probe_execution_realism_review_net_capture_gap_bps": (
                    detail.get(
                        "bounded_probe_execution_realism_review_net_capture_gap_bps"
                    )
                ),
                "bounded_probe_execution_realism_review_gross_capture_gap_bps": (
                    detail.get(
                        "bounded_probe_execution_realism_review_gross_capture_gap_bps"
                    )
                ),
                "bounded_probe_execution_realism_review_cost_or_slippage_gap_bps": (
                    detail.get(
                        "bounded_probe_execution_realism_review_cost_or_slippage_gap_bps"
                    )
                ),
                "bounded_probe_execution_realism_review_entry_delay_gap_ms": detail.get(
                    "bounded_probe_execution_realism_review_entry_delay_gap_ms"
                ),
                "bounded_probe_execution_realism_review_hypothesis_count": detail.get(
                    "bounded_probe_execution_realism_review_hypothesis_count"
                ),
                "bounded_probe_execution_realism_review_primary_hypothesis": detail.get(
                    "bounded_probe_execution_realism_review_primary_hypothesis"
                ),
                "bounded_probe_execution_realism_review_execution_gap_confirmed": (
                    detail.get(
                        "bounded_probe_execution_realism_review_execution_gap_confirmed"
                    )
                ),
                "bounded_probe_execution_realism_review_fill_backed_probe_execution_available": (
                    detail.get(
                        "bounded_probe_execution_realism_review_fill_backed_probe_execution_available"
                    )
                ),
                "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed": (
                    detail.get(
                        "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed"
                    )
                ),
                "latest_admission_decision": detail.get("latest_admission_decision"),
                "latest_record_type": detail.get("latest_record_type"),
                "latest_generated_at_utc": detail.get("latest_generated_at_utc"),
                "latest_side_cell_key": detail.get("latest_side_cell_key"),
                "boundary": detail.get("boundary"),
            },
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
        signal_search_extra = _mm_signal_search_directive_row_extra(escape_scorecard)

        if failure_status == "NO_TRAIN_POSITIVE_CELL":
            if escape_scorecard.get("status") == "CURRENT_FEE_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED":
                stability = _dict(
                    escape_scorecard.get("low_friction_gross_stability_scorecard")
                )
                return _finish_blocker_row(
                    row,
                    blocker_class="feature_family_no_edge",
                    primary_blocker="low_friction_current_fee_holdout_not_train_confirmed",
                    next_trigger=(
                        escape_scorecard.get("next_trigger")
                        or "search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
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
                        "current_fee_positive_sample_gated_cell_count": gross_decomp.get(
                            "current_fee_positive_sample_gated_cell_count"
                        ),
                        "cost_wall_escape_status": escape_scorecard.get("status"),
                        "cost_wall_escape_reason": escape_scorecard.get("reason"),
                        "cost_wall_escape_scorecard": escape_scorecard,
                        "best_sample_gated_current_fee_source": escape_scorecard.get(
                            "best_sample_gated_current_fee_source"
                        ),
                        "low_friction_gross_stability_status": (
                            escape_scorecard.get("low_friction_gross_stability_status")
                        ),
                        "low_friction_gross_stability_reason": (
                            escape_scorecard.get("low_friction_gross_stability_reason")
                        ),
                        "low_friction_train_gross_edge_bps": stability.get(
                            "train_gross_edge_bps"
                        ),
                        "low_friction_holdout_gross_edge_bps": stability.get(
                            "holdout_gross_edge_bps"
                        ),
                        "low_friction_holdout_minus_train_gross_bps": stability.get(
                            "holdout_minus_train_gross_bps"
                        ),
                        "low_friction_train_confirmed_gross_status": (
                            escape_scorecard.get(
                                "low_friction_train_confirmed_gross_status"
                            )
                        ),
                        "low_friction_train_confirmed_current_fee_count": (
                            escape_scorecard.get(
                                "low_friction_train_confirmed_current_fee_count"
                            )
                        ),
                        "low_friction_best_train_confirmed_min_gross_bps": (
                            escape_scorecard.get(
                                "low_friction_best_train_confirmed_min_gross_bps"
                            )
                        ),
                        "low_friction_train_confirmed_gap_to_current_fee_bps": (
                            escape_scorecard.get(
                                "low_friction_train_confirmed_gap_to_current_fee_bps"
                            )
                        ),
                        "best_low_friction_signal_holdout_gross_candidate": (
                            gross_decomp.get(
                                "best_low_friction_signal_holdout_gross_candidate"
                            )
                        ),
                        **signal_search_extra,
                    },
                )
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
                        "low_friction_gross_stability_status": (
                            escape_scorecard.get("low_friction_gross_stability_status")
                        ),
                        "low_friction_gross_stability_reason": (
                            escape_scorecard.get("low_friction_gross_stability_reason")
                        ),
                        "low_friction_train_gross_edge_bps": (
                            _dict(
                                escape_scorecard.get(
                                    "low_friction_gross_stability_scorecard"
                                )
                            ).get("train_gross_edge_bps")
                        ),
                        "low_friction_holdout_gross_edge_bps": (
                            _dict(
                                escape_scorecard.get(
                                    "low_friction_gross_stability_scorecard"
                                )
                            ).get("holdout_gross_edge_bps")
                        ),
                        "low_friction_holdout_minus_train_gross_bps": (
                            _dict(
                                escape_scorecard.get(
                                    "low_friction_gross_stability_scorecard"
                                )
                            ).get("holdout_minus_train_gross_bps")
                        ),
                        "low_friction_train_confirmed_gross_status": (
                            escape_scorecard.get(
                                "low_friction_train_confirmed_gross_status"
                            )
                        ),
                        "low_friction_best_train_confirmed_min_gross_bps": (
                            escape_scorecard.get(
                                "low_friction_best_train_confirmed_min_gross_bps"
                            )
                        ),
                        "low_friction_train_confirmed_gap_to_current_fee_bps": (
                            escape_scorecard.get(
                                "low_friction_train_confirmed_gap_to_current_fee_bps"
                            )
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
                        **signal_search_extra,
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
                    "gross_edge_decomposition_status": gross_status,
                    "current_fee_positive_sample_gated_cell_count": gross_decomp.get(
                        "current_fee_positive_sample_gated_cell_count"
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
                    "best_sample_gated_gross_edge_bps": (
                        escape_scorecard.get("best_sample_gated_gross_edge_bps")
                    ),
                    "best_gross_cell_net_bps": (
                        escape_scorecard.get("best_gross_cell_net_bps")
                    ),
                    "low_friction_gross_stability_status": (
                        escape_scorecard.get("low_friction_gross_stability_status")
                    ),
                    "low_friction_gross_stability_reason": (
                        escape_scorecard.get("low_friction_gross_stability_reason")
                    ),
                    "low_friction_train_confirmed_gross_status": (
                        escape_scorecard.get(
                            "low_friction_train_confirmed_gross_status"
                        )
                    ),
                    "low_friction_best_train_confirmed_min_gross_bps": (
                        escape_scorecard.get(
                            "low_friction_best_train_confirmed_min_gross_bps"
                        )
                    ),
                    "low_friction_train_confirmed_gap_to_current_fee_bps": (
                        escape_scorecard.get(
                            "low_friction_train_confirmed_gap_to_current_fee_bps"
                        )
                    ),
                    "business_path_actionability_status": business_actionability.get(
                        "status"
                    ),
                    **signal_search_extra,
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
                    **signal_search_extra,
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
        label_status_counts = _dict(detail.get("label_status_counts"))
        joined_rows = _int(detail.get("joined_rows"))
        label_feature_horizon_pairs = _int(detail.get("label_feature_horizon_pairs"))
        created_at = _parse_dt(detail.get("created_at_utc"))
        oldest_label_target = _parse_dt(detail.get("oldest_unmatured_exit_target_utc"))
        latest_price_by_symbol = _dict(detail.get("latest_price_ts_utc_by_symbol"))
        latest_price_times = [
            parsed
            for parsed in (_parse_dt(value) for value in latest_price_by_symbol.values())
            if parsed is not None
        ]
        latest_price_max = max(latest_price_times) if latest_price_times else None
        pending_label_count = sum(
            _int(label_status_counts.get(key))
            for key in (
                "entry_target_after_latest_price",
                "exit_target_after_latest_price",
            )
        )
        if (
            joined_rows == 0
            and label_feature_horizon_pairs > 0
            and pending_label_count > 0
            and detail.get("oldest_unmatured_exit_target_utc")
        ):
            if (
                created_at is not None
                and oldest_label_target is not None
                and created_at >= oldest_label_target
                and latest_price_max is not None
                and latest_price_max < oldest_label_target
            ):
                return _finish_blocker_row(
                    row,
                    blocker_class="sample_gate",
                    primary_blocker="price_data_not_caught_up_to_label_target",
                    next_trigger=(
                        "wait_for_price_data_to_cover_oldest_label_target_then_"
                        "rerun_polymarket_leadlag"
                    ),
                    extra={
                        "snapshot_rows": detail.get("snapshot_rows"),
                        "snapshot_distinct_timestamps": detail.get(
                            "snapshot_distinct_timestamps"
                        ),
                        "delta_rows": detail.get("delta_rows"),
                        "feature_points": detail.get("feature_points"),
                        "joined_rows": detail.get("joined_rows"),
                        "label_feature_horizon_pairs": detail.get(
                            "label_feature_horizon_pairs"
                        ),
                        "label_joinable_pairs": detail.get("label_joinable_pairs"),
                        "label_status_counts": label_status_counts,
                        "latest_feature_ts_utc": detail.get("latest_feature_ts_utc"),
                        "latest_price_ts_utc_by_symbol": latest_price_by_symbol,
                        "oldest_unmatured_exit_target_utc": detail.get(
                            "oldest_unmatured_exit_target_utc"
                        ),
                        "newest_unmatured_exit_target_utc": detail.get(
                            "newest_unmatured_exit_target_utc"
                        ),
                        "sample_gate_recheck_status": sample_gate_recheck.get("status"),
                        "sample_gate_recheck_scorecard": sample_gate_recheck or None,
                    },
                )
            return _finish_blocker_row(
                row,
                blocker_class="sample_gate",
                primary_blocker="label_horizon_not_matured",
                next_trigger=(
                    "rerun_polymarket_leadlag_after_label_maturity_then_alpha_discovery"
                ),
                extra={
                    "snapshot_rows": detail.get("snapshot_rows"),
                    "snapshot_distinct_timestamps": detail.get(
                        "snapshot_distinct_timestamps"
                    ),
                    "delta_rows": detail.get("delta_rows"),
                    "feature_points": detail.get("feature_points"),
                    "joined_rows": detail.get("joined_rows"),
                    "label_feature_horizon_pairs": detail.get(
                        "label_feature_horizon_pairs"
                    ),
                    "label_joinable_pairs": detail.get("label_joinable_pairs"),
                    "label_status_counts": label_status_counts,
                    "latest_feature_ts_utc": detail.get("latest_feature_ts_utc"),
                    "latest_price_ts_utc_by_symbol": latest_price_by_symbol or None,
                    "oldest_unmatured_exit_target_utc": detail.get(
                        "oldest_unmatured_exit_target_utc"
                    ),
                    "newest_unmatured_exit_target_utc": detail.get(
                        "newest_unmatured_exit_target_utc"
                    ),
                    "sample_gate_recheck_status": sample_gate_recheck.get("status"),
                    "sample_gate_recheck_scorecard": sample_gate_recheck or None,
                },
            )
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
                "excluded_candidate_artifact_count": dependency.get(
                    "excluded_candidate_artifact_count"
                ),
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
    aeg_review = _latest_aeg_matrix_review_summary(arms)
    dependency = _candidate_artifact_dependency_summary(
        arms,
        decisions,
        aeg_review=aeg_review,
    )
    normalized_arms: list[dict[str, Any]] = []
    for arm in arms:
        arm_copy = dict(arm)
        arm_id = str(arm_copy.get("arm_id") or arm_copy.get("name") or "unknown")
        if _aeg_review_consumes_arm_candidate(arm_copy, aeg_review):
            detail = dict(_dict(arm_copy.get("detail")))
            detail["aeg_matrix_review"] = aeg_review
            arm_copy["detail"] = detail
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
    learning_worklist = build_learning_worklist(blocker_scorecard)
    return {
        "schema_version": DISCOVERY_LOOP_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "policy": "read_only_recommendations_no_probe_or_trade_side_effect",
        "action_counts": counts,
        "arms": decisions,
        "profitability_blocker_scorecard": blocker_scorecard,
        "learning_worklist": learning_worklist,
    }


__all__ = [
    "BLOCK",
    "READY_FOR_AEG_CHAIN",
    "READY_FOR_PROBE",
    "RUN_READ_ONLY_CAPTURE",
    "WAIT",
    "build_discovery_plan",
    "build_learning_worklist",
    "build_profitability_blocker_scorecard",
    "classify_profitability_blocker",
    "decide_arm_action",
]
