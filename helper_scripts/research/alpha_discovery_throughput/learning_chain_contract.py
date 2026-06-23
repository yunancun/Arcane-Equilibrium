"""Autonomous learning-chain contract for alpha discovery.

MODULE_NOTE:
  Purpose: collapse the existing artifact spine, discovery plan, and learning
  worklist into one machine-checkable contract for follow-on agents.
  Boundary: pure artifact/runtime summary inspection only; no DB, Bybit, order,
  probe, risk, auth, or runtime mutation authority.
"""

from __future__ import annotations

from typing import Any


AUTONOMOUS_LEARNING_CHAIN_CONTRACT_SCHEMA_VERSION = (
    "autonomous_learning_chain_contract_v1"
)

_NO_MAIN_GATE_CHANGE_VALUES = {"", "NONE", "NOT_RECOMMENDED", "NO_CHANGE"}
_AUTHORITY_BOOLEAN_SUFFIXES = (
    "global_cost_gate_lowering_recommended",
    "order_authority_granted",
    "probe_authority_granted",
    "promotion_evidence",
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
)
_AUTHORITY_ADJUSTMENT_SUFFIXES = ("main_cost_gate_adjustment",)
_DATA_EVIDENCE_KEY_FRAGMENTS = (
    "blocked_signal",
    "false_negative",
    "profit_learning",
    "current_fee",
    "sample_gated",
    "candidate_replay",
    "markout",
    "fill",
    "history",
    "outcome",
    "gross_edge",
    "net_edge",
    "edge_bps",
    "edge_capture",
    "wrongful_block",
    "gross_bps",
    "net_bps",
    "sample_count",
)
_DIAGNOSTIC_ONLY_EVIDENCE_KEY_FRAGMENTS = (
    "source_error",
    "source_path",
    "git_dirty",
    "git_behind",
    "missing_cron",
    "blocking_gate",
    "proof_gate_count_remaining",
)
_DIAGNOSTIC_ONLY_EVIDENCE_KEYS = {"min_samples"}
_NESTED_DIAGNOSTIC_ONLY_EVIDENCE_KEYS = {"cost_gate_artifact_spine_summary"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _is_true(value: Any) -> bool:
    return value is True


def _cost_gate_detail(arms: list[dict[str, Any]]) -> dict[str, Any]:
    for arm in arms:
        if arm.get("arm_id") == "cost_gate_demo_learning_lane":
            return _dict(arm.get("detail"))
    return {}


def _nested_values(
    payload: Any,
    *,
    prefix: str,
) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_nested_values(value, prefix=next_prefix))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            next_prefix = f"{prefix}[{index}]"
            out.extend(_nested_values(value, prefix=next_prefix))
    else:
        out.append((prefix, payload))
    return out


def _authority_violations(
    *,
    cost_gate_artifact_spine_summary: dict[str, Any],
    profitability_path_summary: dict[str, Any],
    learning_worklist: dict[str, Any],
) -> list[dict[str, Any]]:
    sources = {
        "cost_gate_artifact_spine_summary": cost_gate_artifact_spine_summary,
        "profitability_path_summary": profitability_path_summary,
        "learning_worklist": learning_worklist,
    }
    violations: list[dict[str, Any]] = []
    for source_name, payload in sources.items():
        for path, value in _nested_values(payload, prefix=source_name):
            leaf = path.rsplit(".", 1)[-1]
            if leaf.endswith(_AUTHORITY_BOOLEAN_SUFFIXES) and value is True:
                violations.append({
                    "field": path,
                    "value": value,
                    "reason": "runtime_authority_or_promotion_flag_true",
                })
            if leaf.endswith(_AUTHORITY_ADJUSTMENT_SUFFIXES):
                text = _str(value).upper()
                if text and text not in _NO_MAIN_GATE_CHANGE_VALUES:
                    violations.append({
                        "field": path,
                        "value": value,
                        "reason": "main_cost_gate_adjustment_not_none",
                    })
    return violations


def _raw_learning_data_present(
    *,
    detail: dict[str, Any],
    cost_gate_artifact_spine_summary: dict[str, Any],
) -> bool:
    active_state = _dict(cost_gate_artifact_spine_summary.get("active_state"))
    ledger_status = _str(detail.get("ledger_status")).upper()
    return any((
        _int(cost_gate_artifact_spine_summary.get("ready_alpha_evidence_node_count")) > 0,
        _is_true(active_state.get("blocked_outcome_review_candidate_ready")),
        _is_true(active_state.get("false_negative_candidate_packet_present")),
        _is_true(active_state.get("false_negative_queue_ready")),
        _is_true(detail.get("demo_learning_evidence_cost_gate_rejects_recorded_in_pg")),
        _int(detail.get("blocked_signal_outcome_count")) > 0,
        _int(detail.get("false_negative_candidate_packet_false_negative_count")) > 0,
        ledger_status not in {"", "MISSING", "EMPTY", "UNKNOWN"},
    ))


def _is_data_evidence_value(key: str, value: Any) -> bool:
    lower = key.lower()
    if lower in _DIAGNOSTIC_ONLY_EVIDENCE_KEYS:
        return False
    if any(fragment in lower for fragment in _DIAGNOSTIC_ONLY_EVIDENCE_KEY_FRAGMENTS):
        return False
    if isinstance(value, dict):
        return any(_is_data_evidence_value(str(k), v) for k, v in value.items())
    if isinstance(value, list):
        return any(_is_data_evidence_value(lower, item) for item in value)
    if not any(fragment in lower for fragment in _DATA_EVIDENCE_KEY_FRAGMENTS):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return bool(_str(value))


def _worklist_data_evidence_present(learning_worklist: dict[str, Any]) -> bool:
    for task in _list(learning_worklist.get("tasks")):
        evidence = _dict(_dict(task).get("evidence"))
        if any(
            _is_data_evidence_value(str(k), v)
            for k, v in evidence.items()
            if str(k) not in _NESTED_DIAGNOSTIC_ONLY_EVIDENCE_KEYS
        ):
            return True
    top_task = _dict(learning_worklist.get("top_task"))
    evidence = _dict(top_task.get("evidence"))
    return any(
        _is_data_evidence_value(str(k), v)
        for k, v in evidence.items()
        if str(k) not in _NESTED_DIAGNOSTIC_ONLY_EVIDENCE_KEYS
    )


def _learning_output_ready(
    *,
    learning_worklist: dict[str, Any],
) -> bool:
    top_task = _dict(learning_worklist.get("top_task"))
    return all((
        _int(learning_worklist.get("task_count")) > 0,
        bool(_str(top_task.get("task_id"))),
        bool(_str(top_task.get("learning_objective"))),
        bool(_str(top_task.get("completion_gate"))),
        isinstance(top_task.get("completion_evidence_required"), list),
    ))


def _runtime_consumer_ready(
    *,
    discovery_plan: dict[str, Any],
    learning_worklist: dict[str, Any],
    learning_summary: dict[str, Any],
) -> bool:
    plan_worklist = _dict(discovery_plan.get("learning_worklist"))
    top_task = _dict(learning_worklist.get("top_task"))
    task_id = _str(top_task.get("task_id"))
    return all((
        bool(plan_worklist),
        plan_worklist.get("schema_version") == learning_worklist.get("schema_version"),
        bool(task_id),
        learning_summary.get("top_learning_task_id") == task_id,
        bool(_str(learning_summary.get("top_learning_task_completion_gate"))),
        _int(learning_summary.get("top_learning_task_completion_evidence_required_count")) > 0,
    ))


def _value_status(learning_worklist: dict[str, Any]) -> str:
    if _int(learning_worklist.get("promotion_ready_count")) > 0:
        return "PROMOTION_REVIEW_OUTPUT"
    if _int(learning_worklist.get("operator_required_count")) > 0:
        return "OPERATOR_GATED_LEARNING_OUTPUT"
    if _int(learning_worklist.get("engineering_actionable_count")) > 0:
        return "ENGINEERING_ACTIONABLE_LEARNING_OUTPUT"
    if _int(learning_worklist.get("task_count")) > 0:
        return "WAIT_OR_SAMPLE_GATED_LEARNING_OUTPUT"
    return "NO_LEARNING_OUTPUT"


def _autonomous_agent_task(
    *,
    learning_worklist: dict[str, Any],
    learning_summary: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    top_task = _dict(learning_worklist.get("top_task"))
    top_requires_operator = top_task.get("requires_operator_authorization") is True
    top_requires_runtime_mutation = top_task.get("runtime_mutation_required") is True
    if top_task and not top_requires_operator and not top_requires_runtime_mutation:
        return "AUTONOMOUS_TASK_READY", top_task

    top_engineering_id = _str(
        learning_summary.get("top_engineering_learning_task_id")
    )
    if top_engineering_id:
        for task in _list(learning_worklist.get("tasks")):
            candidate = _dict(task)
            if candidate.get("task_id") == top_engineering_id:
                return "AUTONOMOUS_ENGINEERING_TASK_READY", candidate

    if top_task and top_requires_operator:
        return "OPERATOR_REVIEW_REQUIRED", top_task
    if top_task and top_requires_runtime_mutation:
        return "OPERATOR_RUNTIME_MUTATION_REQUIRED", top_task
    if top_task:
        return "DIAGNOSTIC_TASK_READY", top_task
    return "NO_AGENT_TASK", {}


def _status(
    *,
    data_ingress_ready: bool,
    learning_engine_output_ready: bool,
    runtime_consumer_ready: bool,
    authority_boundary_preserved: bool,
    value_status: str,
) -> str:
    if not authority_boundary_preserved:
        return "AUTONOMOUS_LEARNING_CHAIN_AUTHORITY_BOUNDARY_VIOLATION"
    if not data_ingress_ready:
        return "AUTONOMOUS_LEARNING_CHAIN_DATA_INGRESS_MISSING"
    if not learning_engine_output_ready:
        return "AUTONOMOUS_LEARNING_CHAIN_ENGINE_OUTPUT_MISSING"
    if not runtime_consumer_ready:
        return "AUTONOMOUS_LEARNING_CHAIN_RUNTIME_CONSUMER_MISSING"
    if value_status in {
        "PROMOTION_REVIEW_OUTPUT",
        "OPERATOR_GATED_LEARNING_OUTPUT",
        "ENGINEERING_ACTIONABLE_LEARNING_OUTPUT",
    }:
        return "AUTONOMOUS_LEARNING_CHAIN_ACTIONABLE"
    return "AUTONOMOUS_LEARNING_CHAIN_WAITING_FOR_DATA_OR_EVENT"


def build_autonomous_learning_chain_contract(
    *,
    runtime_source: dict[str, Any],
    arms: list[dict[str, Any]],
    discovery_plan: dict[str, Any],
    learning_worklist: dict[str, Any],
    learning_summary: dict[str, Any],
    cost_gate_artifact_spine_summary: dict[str, Any],
    profitability_path_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build a single contract proving whether learning reaches runtime routing."""
    detail = _cost_gate_detail(arms)
    data_ingress_ready = _raw_learning_data_present(
        detail=detail,
        cost_gate_artifact_spine_summary=cost_gate_artifact_spine_summary,
    ) or _worklist_data_evidence_present(
        learning_worklist,
    )
    engine_output_ready = _learning_output_ready(
        learning_worklist=learning_worklist,
    )
    consumer_ready = _runtime_consumer_ready(
        discovery_plan=discovery_plan,
        learning_worklist=learning_worklist,
        learning_summary=learning_summary,
    )
    violations = _authority_violations(
        cost_gate_artifact_spine_summary=cost_gate_artifact_spine_summary,
        profitability_path_summary=profitability_path_summary,
        learning_worklist=learning_worklist,
    )
    value_status = _value_status(learning_worklist)
    agent_route_status, agent_task = _autonomous_agent_task(
        learning_worklist=learning_worklist,
        learning_summary=learning_summary,
    )
    authority_boundary_preserved = not violations

    return {
        "schema_version": AUTONOMOUS_LEARNING_CHAIN_CONTRACT_SCHEMA_VERSION,
        "policy": (
            "artifact_only_contract_no_db_no_bybit_no_order_no_probe_no_runtime_mutation"
        ),
        "status": _status(
            data_ingress_ready=data_ingress_ready,
            learning_engine_output_ready=engine_output_ready,
            runtime_consumer_ready=consumer_ready,
            authority_boundary_preserved=authority_boundary_preserved,
            value_status=value_status,
        ),
        "data_ingress_ready": data_ingress_ready,
        "learning_engine_output_ready": engine_output_ready,
        "runtime_consumer_ready": consumer_ready,
        "value_status": value_status,
        "authority_boundary_status": (
            "PRESERVED" if authority_boundary_preserved else "VIOLATION"
        ),
        "authority_violations": violations,
        "agent_route_status": agent_route_status,
        "agent_task_id": agent_task.get("task_id"),
        "agent_task_arm_id": agent_task.get("arm_id"),
        "agent_task_type": agent_task.get("task_type"),
        "agent_task_actionability": agent_task.get("actionability"),
        "agent_task_next_trigger": agent_task.get("next_trigger"),
        "agent_task_completion_gate": agent_task.get("completion_gate"),
        "agent_task_side_effect_boundary": agent_task.get("side_effect_boundary"),
        "runtime_source_activation_ready": (
            runtime_source.get("source_activation_ready") is True
        ),
        "runtime_source_activation_status": runtime_source.get(
            "source_activation_status"
        ),
        "learning_worklist_status": learning_worklist.get("status"),
        "learning_task_count": _int(learning_worklist.get("task_count")),
        "learning_operator_required_count": _int(
            learning_worklist.get("operator_required_count")
        ),
        "learning_engineering_actionable_count": _int(
            learning_worklist.get("engineering_actionable_count")
        ),
        "learning_promotion_ready_count": _int(
            learning_worklist.get("promotion_ready_count")
        ),
        "cost_gate_ready_alpha_evidence_node_count": _int(
            cost_gate_artifact_spine_summary.get("ready_alpha_evidence_node_count")
        ),
        "cost_gate_probe_result_learning_valid": (
            cost_gate_artifact_spine_summary.get("probe_result_learning_valid")
        ),
        "cost_gate_proof_gap": cost_gate_artifact_spine_summary.get("proof_gap"),
        "profitability_path_scorecard_status": profitability_path_summary.get(
            "profitability_path_scorecard_status"
        ),
        "profitability_engineering_closure_status": profitability_path_summary.get(
            "profitability_engineering_closure_status"
        ),
    }


__all__ = [
    "AUTONOMOUS_LEARNING_CHAIN_CONTRACT_SCHEMA_VERSION",
    "build_autonomous_learning_chain_contract",
]
