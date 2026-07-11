"""Canonical admitted execution-DAG ordering and producer-generation checks."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from agent_governance_registry import load_registry, native_agent_binding


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EXECUTION_NODE_FIELDS = (
    "node_id", "role", "native_agent", "requires", "node_class", "permission",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def execution_node_core(task: dict[str, Any]) -> dict[str, Any]:
    """Project one dispatch/wave task onto the identity-bearing DAG fields."""

    return {field: task.get(field) for field in EXECUTION_NODE_FIELDS}


def execution_dag_digest(tasks: list[dict[str, Any]]) -> str:
    core = {
        "schema_version": "agent_wave_execution_dag_v1",
        "nodes": [execution_node_core(task) for task in tasks],
    }
    return "sha256:" + hashlib.sha256(_canonical(core)).hexdigest()


def non_call_controller_node_ids(task_facts: dict[str, Any] | None) -> set[str]:
    """Return routed role nodes whose result is the workflow-wave controller."""

    surfaces = set((task_facts or {}).get("surfaces", []))
    excluded: set[str] = set()
    if "full_audit" in surfaces:
        excluded.add("ai_economics_review")
    if "profit_diagnosis" in surfaces:
        excluded.add("profit_control")
    return excluded


def delegated_execution_projection(
    required_nodes: Any,
    admitted_nodes: Any,
    *,
    excluded_nodes: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Compile the exact call-producing subgraph from closure dispatch nodes.

    Edges through a non-call controller are projected to that controller's
    nearest call-producing predecessors.  The returned node order is the
    dispatch order and therefore part of the canonical DAG digest.
    """

    if not isinstance(required_nodes, list) or not isinstance(admitted_nodes, list):
        return [], ["dispatch execution nodes must be arrays"]
    combined = [*required_nodes, *admitted_nodes]
    if any(not isinstance(node, dict) for node in combined):
        return [], ["dispatch execution nodes must be objects"]
    node_ids = [node.get("node_id") for node in combined]
    if any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
        return [], ["dispatch execution node ids are invalid"]
    if len(node_ids) != len(set(node_ids)):
        return [], ["dispatch execution node ids are not unique"]
    node_by_id = {str(node["node_id"]): node for node in combined}
    excluded = set(excluded_nodes or ())
    unknown_excluded = excluded - set(node_by_id)
    errors = [
        f"non-call controller node {node_id} is absent from dispatch"
        for node_id in sorted(unknown_excluded)
    ]
    for node in combined:
        node_id = str(node["node_id"])
        requires = node.get("requires")
        if (
            not isinstance(requires, list)
            or requires != sorted(set(requires))
            or any(
                not isinstance(required, str) or required not in node_by_id
                for required in (requires if isinstance(requires, list) else [])
            )
            or node_id in (requires if isinstance(requires, list) else [])
        ):
            errors.append(
                f"dispatch execution node {node_id} requires are not sorted unique dispatch predecessors"
            )

    resolving: set[str] = set()
    resolved: dict[str, set[str]] = {}

    def call_predecessors(node_id: str) -> set[str]:
        if node_id in resolved:
            return resolved[node_id]
        if node_id in resolving:
            errors.append("dispatch execution DAG contains a cycle through a non-call controller")
            return set()
        resolving.add(node_id)
        predecessors: set[str] = set()
        node = node_by_id[node_id]
        requires = node.get("requires") if isinstance(node.get("requires"), list) else []
        for required in requires:
            if required not in node_by_id:
                continue
            if required in excluded:
                predecessors.update(call_predecessors(required))
            else:
                predecessors.add(required)
        resolving.remove(node_id)
        resolved[node_id] = predecessors
        return predecessors

    projected = [
        {
            **execution_node_core(node),
            "requires": sorted(call_predecessors(str(node["node_id"]))),
        }
        for node in combined
        if node["node_id"] not in excluded
    ]
    _, topology_errors = topological_waves(projected)
    errors.extend(topology_errors)
    return projected, errors


def topological_waves(tasks: list[dict[str, Any]]) -> tuple[list[list[str]], list[str]]:
    node_ids = [task.get("node_id") for task in tasks]
    errors: list[str] = []
    if any(not isinstance(node, str) or not node for node in node_ids):
        return [], ["execution DAG node ids are invalid"]
    if len(node_ids) != len(set(node_ids)):
        return [], ["execution DAG node ids are not unique"]
    node_set = set(node_ids)
    roles = load_registry()["roles"]
    for index, task in enumerate(tasks):
        requires = task.get("requires")
        if (
            not isinstance(requires, list)
            or requires != sorted(set(requires))
            or any(not isinstance(node, str) or node not in node_set for node in requires)
            or node_ids[index] in requires
        ):
            errors.append(
                f"execution DAG node {node_ids[index]} requires are not sorted unique admitted predecessors"
            )
        role = task.get("role")
        node_class = task.get("node_class")
        permission = task.get("permission")
        native_agent = task.get("native_agent")
        if role not in roles or node_class not in {"work", "verification"}:
            errors.append(f"execution DAG node {node_ids[index]} role/class is invalid")
        elif node_class == "verification" and permission != "read_only":
            errors.append(f"execution DAG verification node {node_ids[index]} must be read_only")
        elif node_class == "work" and (
            roles[role]["permission"] == "read_only"
            or permission != roles[role]["permission"]
        ):
            errors.append(f"execution DAG work node {node_ids[index]} permission differs from Registry")
        else:
            try:
                binding = native_agent_binding(role, node_class)
            except ValueError as exc:
                errors.append(f"execution DAG node {node_ids[index]} native binding is invalid: {exc}")
            else:
                if native_agent != binding["native_agent"]:
                    errors.append(f"execution DAG node {node_ids[index]} native_agent differs from Registry")
                if permission != binding["permission"]:
                    errors.append(f"execution DAG node {node_ids[index]} permission differs from native binding")
    for task in tasks:
        if task.get("role") == "E4" and task.get("node_class") == "work" and not any(
            candidate.get("role") == "E2"
            and candidate.get("node_class") == "verification"
            and task.get("node_id") in candidate.get("requires", [])
            for candidate in tasks
        ):
            errors.append("E4 test work requires a following E2 verification node")
    implementation_nodes = [
        task for task in tasks
        if task.get("node_id") in {
            "implementation", "implementation_backend", "implementation_frontend",
        }
        and task.get("role") in {"E1", "E1a"}
        and task.get("node_class") == "work"
    ]
    if implementation_nodes:
        implementation_ids = {
            str(implementation["node_id"]) for implementation in implementation_nodes
        }
        if implementation_ids == {
            "implementation_backend", "implementation_frontend",
        }:
            frontend = next(
                task for task in implementation_nodes
                if task.get("node_id") == "implementation_frontend"
            )
            if frontend.get("requires") != ["implementation_backend"]:
                errors.append(
                    "full-stack writers require canonical backend-to-frontend serialization"
                )
        reviews = [
            candidate for candidate in tasks
            if candidate.get("role") == "E2"
            and candidate.get("node_class") == "verification"
            and implementation_ids.issubset(set(candidate.get("requires", [])))
        ]
        if not reviews:
            errors.append("implementation requires a following E2 independent review node")
        if not reviews or not any(
            candidate.get("role") == "E4"
            and candidate.get("node_class") == "verification"
            and review.get("node_id") in candidate.get("requires", [])
            for review in reviews
            for candidate in tasks
        ):
            errors.append("implementation review requires a following E4 regression node")
    if errors:
        return [], errors
    pending = set(node_ids)
    waves: list[list[str]] = []
    while pending:
        ready = [
            node for node in node_ids
            if node in pending
            and all(required not in pending for required in tasks[node_ids.index(node)]["requires"])
        ]
        if not ready:
            return [], ["execution DAG contains a cycle"]
        waves.append(ready)
        pending.difference_update(ready)
    return waves, []


def validate_call_dag_fields(record: Any) -> list[str]:
    if not isinstance(record, dict):
        return ["workflow call DAG binding is missing"]
    errors: list[str] = []
    if not DIGEST_RE.fullmatch(str(record.get("dag_digest", ""))):
        errors.append("workflow call dag_digest is invalid")
    requires = record.get("requires")
    if (
        not isinstance(requires, list)
        or requires != sorted(set(requires))
        or any(not isinstance(node, str) or not node for node in requires)
    ):
        errors.append("workflow call requires are not sorted unique node ids")
        requires = []
    wave = record.get("topological_wave")
    if not isinstance(wave, int) or isinstance(wave, bool) or wave < 0:
        errors.append("workflow call topological_wave is invalid")
    generation = record.get("producer_generation")
    if not isinstance(generation, dict) or set(generation) != set(requires):
        errors.append("workflow call producer_generation differs from requires")
    elif any(not DIGEST_RE.fullmatch(str(value)) for value in generation.values()):
        errors.append("workflow call producer_generation digest is invalid")
    return errors


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def validate_wave_dag_order(
    wave: Any, records: list[Any], tasks: list[dict[str, Any]]
) -> list[str]:
    """Prove manifest order/timestamps obey requires and captured producers."""

    if not isinstance(wave, dict):
        return ["workflow wave DAG binding is missing"]
    errors: list[str] = []
    expected_waves, dag_errors = topological_waves(tasks)
    errors.extend(dag_errors)
    expected_digest = execution_dag_digest(tasks)
    if wave.get("dag_digest") != expected_digest:
        errors.append("workflow wave dag_digest differs from admitted tasks")
    if wave.get("execution_waves") != expected_waves:
        errors.append("workflow wave execution_waves differ from canonical topological order")
    task_by_node = {task.get("node_id"): task for task in tasks}
    wave_by_node = {
        node: index for index, nodes in enumerate(expected_waves) for node in nodes
    }
    successful_producer: dict[str, dict[str, Any]] = {}
    previous_wave = -1
    for index, record in enumerate(records):
        errors.extend(
            f"workflow call records[{index}] {error}"
            for error in validate_call_dag_fields(record)
        )
        if not isinstance(record, dict):
            continue
        node = record.get("node_id")
        task = task_by_node.get(node)
        expected_wave = wave_by_node.get(node)
        if task is None:
            errors.append(f"workflow call records[{index}] node is not admitted")
            continue
        if record.get("dag_digest") != expected_digest:
            errors.append(f"workflow call records[{index}] dag_digest differs from wave")
        if record.get("requires") != task.get("requires"):
            errors.append(f"workflow call records[{index}] requires differ from admitted task")
        if record.get("topological_wave") != expected_wave:
            errors.append(f"workflow call records[{index}] topological wave is invalid")
        if isinstance(expected_wave, int) and expected_wave < previous_wave:
            errors.append("workflow call manifest order regresses across topological waves")
        if isinstance(expected_wave, int):
            previous_wave = max(previous_wave, expected_wave)
        generation = record.get("producer_generation")
        expected_generation = {
            required: successful_producer[required].get("record_digest")
            for required in task.get("requires", [])
            if required in successful_producer
        }
        if generation != expected_generation:
            errors.append(f"workflow call records[{index}] producer generation is incomplete or stale")
        started = _instant(record.get("started_at"))
        for required in task.get("requires", []):
            producer = successful_producer.get(required)
            ended = _instant(producer.get("ended_at")) if producer else None
            if producer is None or producer.get("returned_null") is True:
                errors.append(f"workflow call records[{index}] requires incomplete predecessor {required}")
            elif started is None or ended is None or started < ended:
                errors.append(f"workflow call records[{index}] started before predecessor {required} completed")
        if record.get("returned_null") is False:
            successful_producer[str(node)] = record
    return errors
