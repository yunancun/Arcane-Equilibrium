"""Adversarial closure binding for the canonical delegated execution DAG."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_execution_dag import (  # noqa: E402
    delegated_execution_projection,
    execution_dag_digest,
    non_call_controller_node_ids,
    topological_waves,
)
from agent_governance_dispatch_validation import validate_dispatch_projection  # noqa: E402
from agent_governance_registry import load_registry  # noqa: E402
from agent_governance_routing import TASK_CONTRACT_FIELDS, route_task  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
from agent_governance_trust import _wave_errors  # noqa: E402
from agent_governance_workflow_receipts import canonical_digest  # noqa: E402


def test_narrow_query_stays_pm_only_and_finite() -> None:
    route = route_task({
        "task_shape": "query",
        "surfaces": ["governance"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "none",
        "task_prompt": "explain the current finite task policy",
    })
    assert route["roles"] == ["PM", "PM"]
    assert [node["id"] for node in route["nodes"]] == ["pm_triage", "pm_closure"]
    assert route["task_facts"]["continuation_mode"] == "finite"
    assert route["task_execution_control"]["automatic_wakeup_admitted"] is False


def test_query_cannot_bypass_hard_facts_or_opt_into_a_loop() -> None:
    base = {
        "task_shape": "query",
        "surfaces": [],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "none",
        "task_prompt": "answer a narrow read-only question",
    }
    for override in (
        {"surfaces": ["authority"]},
        {"runtime_claim": True},
        {"risk": "high"},
        {"continuation_mode": "operator_loop"},
        {"direct_interfaces": ["auth/session authority"]},
    ):
        try:
            route_task({**base, **override})
        except ValueError as error:
            assert "task_shape query requires" in str(error)
        else:
            raise AssertionError(f"unsafe query facts were admitted: {override}")


def test_operator_loop_route_requires_exact_operator_prompt_marker() -> None:
    base = {
        "task_shape": "analysis",
        "surfaces": ["governance"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "none",
        "continuation_mode": "operator_loop",
    }
    try:
        route_task({**base, "task_prompt": "answer once and stop; do not loop"})
    except ValueError as error:
        assert "leading /loop control line" in str(error)
    else:
        raise AssertionError("operator_loop without exact Operator marker was admitted")

    routed = route_task({**base, "task_prompt": "/loop\nmonitor until terminal"})
    control = routed["task_execution_control"]
    assert control["automatic_wakeup_admitted"] is True
    assert control["operator_loop_request_digest"].startswith("sha256:")
    assert control["task_contract_digest"].startswith("sha256:")
    contract = {
        field: routed["task_facts"].get(field) for field in TASK_CONTRACT_FIELDS
    }
    assert control["task_contract_digest"] == "sha256:" + hashlib.sha256(
        json.dumps(
            contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    assert (
        routed["task_facts"]["operator_loop_request_digest"]
        == control["operator_loop_request_digest"]
    )


def _implementation_fixture() -> tuple[dict, dict, dict]:
    facts = {
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "task_prompt": "implement and independently verify the change",
        "dirty_scope": ["src/feature.py"],
    }
    route = route_task(facts)
    projected, projection_errors = delegated_execution_projection(
        route["required_role_nodes"], [],
        excluded_nodes=non_call_controller_node_ids(route["task_facts"]),
    )
    assert projection_errors == []
    execution_waves, wave_errors = topological_waves(projected)
    assert wave_errors == []
    fragments = [
        {
            "node_id": task["node_id"],
            "role": task["role"],
            "payload_kind": "fixture_fragment_v1",
            "producer_record_kind": "workflow_call_record_v1",
        }
        for task in projected
    ]
    wave = {
        "record_digest": "sha256:" + "f" * 64,
        "dag_digest": execution_dag_digest(projected),
        "execution_waves": execution_waves,
        "admitted_tasks": [
            {**deepcopy(task), "payload_kind": "fixture_fragment_v1"}
            for task in projected
        ],
        "result_fragment_digests": {
            fragment["node_id"]: canonical_digest(fragment)
            for fragment in fragments
        },
        "final_null_node_count": 0,
        "coverage_debt": [],
    }
    packet = {
        "gate_verdict": "PASS",
        "dispatch": {
            "task_facts": route["task_facts"],
            "required_role_nodes": deepcopy(route["required_role_nodes"]),
            "admitted_role_nodes": [],
            "dag_digest": execution_dag_digest(projected),
        },
        "role_fragments": fragments,
    }
    captures = {"waves": {wave["record_digest"]: wave}}
    return route, packet, captures


def test_closure_wave_exactly_matches_dispatched_builder_review_regression_dag() -> None:
    route, packet, captures = _implementation_fixture()
    assert _wave_errors(packet, captures, route) == []


def test_closure_rejects_dropped_node_changed_edge_and_changed_wave() -> None:
    route, packet, captures = _implementation_fixture()

    dropped = deepcopy(captures)
    dropped_wave = next(iter(dropped["waves"].values()))
    dropped_wave["admitted_tasks"].pop()
    dropped_wave["dag_digest"] = execution_dag_digest(dropped_wave["admitted_tasks"])
    dropped_wave["execution_waves"] = [["implementation"], ["independent_review"]]
    dropped_errors = _wave_errors(packet, dropped, route)
    assert any("admitted tasks differ from dispatch projection" in error for error in dropped_errors)

    changed_edge = deepcopy(captures)
    changed_wave = next(iter(changed_edge["waves"].values()))
    review = next(
        task for task in changed_wave["admitted_tasks"]
        if task["node_id"] == "independent_review"
    )
    review["requires"] = []
    changed_wave["dag_digest"] = execution_dag_digest(changed_wave["admitted_tasks"])
    changed_wave["execution_waves"] = [
        ["implementation", "independent_review"], ["regression"],
    ]
    edge_errors = _wave_errors(packet, changed_edge, route)
    assert any("admitted tasks differ from dispatch projection" in error for error in edge_errors)
    assert any("dag_digest differs from closure dispatch" in error for error in edge_errors)

    changed_order = deepcopy(captures)
    next(iter(changed_order["waves"].values()))["execution_waves"] = [[
        "implementation", "independent_review", "regression",
    ]]
    order_errors = _wave_errors(packet, changed_order, route)
    assert any("execution_waves differ from dispatch projection" in error for error in order_errors)


def test_specialized_non_call_controller_is_projected_out_not_prefix_exempted() -> None:
    route = route_task({
        "task_shape": "audit",
        "surfaces": ["agent_workflow", "full_audit"],
        "risk": "high",
        "uncertainty": "low",
        "side_effect_class": "none",
        "task_prompt": "audit the multi-agent workflow",
    })
    admissions = [{
        "node_id": "audit:E2", "role": "E2", "native_agent": "E2",
        "node_class": "verification", "permission": "read_only",
        "requires": [], "path_scope": [],
        "reason": "full audit admitted axis",
        "result_binding": "role_fragment",
    }, {
        "node_id": "seam:critic", "role": "CC", "native_agent": "CC",
        "node_class": "verification", "permission": "read_only",
        "requires": ["audit:E2"], "path_scope": [],
        "reason": "full audit nested seam critic",
        "result_binding": "nested_payload",
    }]
    projected, errors = delegated_execution_projection(
        route["required_role_nodes"], admissions,
        excluded_nodes=non_call_controller_node_ids(route["task_facts"]),
    )
    assert errors == []
    assert "ai_economics_review" not in {
        node["node_id"] for node in projected
    }
    assert next(
        node for node in projected if node["node_id"] == "seam:critic"
    )["requires"] == ["audit:E2"]
    assert execution_dag_digest(projected) != route["dag_digest"]


def test_closure_schema_requires_admission_edges_scope_and_result_binding() -> None:
    schema = json.loads(
        (ROOT / ".codex/schemas/closure_packet_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    admission_schema = schema["properties"]["dispatch"]["properties"][
        "admitted_role_nodes"
    ]["items"]
    admission = {
        "node_id": "adaptive-review", "role": "E2", "native_agent": "E2",
        "node_class": "verification", "permission": "read_only",
        "requires": ["implementation"], "path_scope": [],
        "reason": "adversarial second thought",
        "result_binding": "role_fragment",
    }
    assert schema_subset_errors(admission, admission_schema, schema) == []
    for field in ("requires", "path_scope", "result_binding"):
        missing = deepcopy(admission)
        del missing[field]
        assert schema_subset_errors(missing, admission_schema, schema), field


def test_ordinary_workflow_cannot_hide_an_admitted_result_as_nested_payload() -> None:
    route, packet, _ = _implementation_fixture()
    admission = {
        "node_id": "hidden-review", "role": "E2", "native_agent": "E2",
        "node_class": "verification", "permission": "read_only",
        "requires": ["regression"], "path_scope": [],
        "reason": "attempt to hide an ordinary result",
        "result_binding": "nested_payload",
    }
    projected, projection_errors = delegated_execution_projection(
        route["required_role_nodes"], [admission], excluded_nodes=set(),
    )
    assert projection_errors == []
    packet["dispatch"]["admitted_role_nodes"] = [admission]
    packet["dispatch"]["dag_digest"] = execution_dag_digest(projected)
    result = validate_dispatch_projection(
        packet["dispatch"], expected_route=route,
        expected_required_nodes=route["required_role_nodes"],
        task_contract={"dirty_scope": ["src/feature.py"]},
        role_registry=load_registry()["roles"],
    )
    assert any("nested_payload is not owned" in error for error in result["errors"])
