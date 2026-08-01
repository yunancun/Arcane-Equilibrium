"""Canonical admitted execution-DAG ordering and producer-generation checks."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from agent_governance_registry import load_registry, native_agent_binding


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EXECUTION_NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
EXECUTION_NODE_FIELDS = (
    "node_id", "role", "native_agent", "requires", "node_class", "permission",
)
CONTEXT_EXECUTION_DAG_BINDING_FIELDS = (
    "schema_version", "dag_digest", "node_count", "edge_count", "nodes",
)


class SpecializedWorkflowSplitRequired(ValueError):
    """Stable machine-readable boundary between a saved workflow and next phase."""

    error_code = "SPECIALIZED_WORKFLOW_SPLIT_REQUIRED"

    def __init__(self, surface: str, extra_node_ids: list[str]) -> None:
        self.surface = surface
        self.extra_node_ids = tuple(sorted(set(extra_node_ids)))
        super().__init__(
            f"{self.error_code}: specialized {surface} Context contains calls "
            f"outside its fixed saved-workflow DAG: {list(self.extra_node_ids)}; "
            "compile those calls into a fresh non-specialized Context bound to "
            "its selected executor"
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


def _compile_context_execution_dag_binding(
    tasks: Any,
    *,
    registry: dict[str, Any] | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Internal exact binding primitive with an explicit zero-call policy."""

    if not isinstance(tasks, list):
        raise ValueError("Context execution DAG must be an array")
    if not tasks and not allow_empty:
        raise ValueError("Context execution DAG must contain at least one node")
    if any(not isinstance(task, dict) for task in tasks):
        raise ValueError("Context execution DAG nodes must be objects")
    expected_fields = set(EXECUTION_NODE_FIELDS)
    for index, task in enumerate(tasks):
        if set(task) != expected_fields:
            raise ValueError(
                f"Context execution DAG node[{index}] fields must be exact"
            )
    nodes = [execution_node_core(task) for task in tasks]
    _, errors = topological_waves(nodes, registry=registry)
    if errors:
        raise ValueError("invalid Context execution DAG: " + "; ".join(errors))
    return {
        "schema_version": "context_execution_dag_binding_v1",
        "dag_digest": execution_dag_digest(nodes),
        "node_count": len(nodes),
        "edge_count": sum(len(node["requires"]) for node in nodes),
        "nodes": nodes,
    }


def compile_context_execution_dag_binding(
    tasks: Any,
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind a caller-supplied, non-empty exact call-producing DAG."""

    return _compile_context_execution_dag_binding(
        tasks,
        registry=registry,
        allow_empty=False,
    )


def _compiler_derived_zero_call_context_execution_dag_binding(
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize the compiler's zero-delegation binding.

    This helper accepts no caller DAG and therefore cannot be used as a public
    boolean override to erase routed work.
    """

    return _compile_context_execution_dag_binding(
        [],
        registry=registry,
        allow_empty=True,
    )


def profit_diagnosis_execution_dag(
    registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compile the complete pre-call Profit Diagnosis execution DAG."""

    registry = load_registry() if registry is None else registry
    contract = registry["workflow_contracts"]["profit_diagnosis_v1"]
    evidence_axes = contract["evidence_axes"]
    probe_axes = contract["probe_axes"]
    probe_requirements = {
        "QC": ["MIT", "OPS"],
        "BB": ["MIT", "OPS"],
        "IB": ["MIT", "OPS"],
        "MIT": ["MIT", "OPS"],
        "AI-E": ["AI-E", "OPS"],
        "EXT": list(evidence_axes),
    }

    def node(
        node_id: str,
        role: str,
        requires: list[str],
    ) -> dict[str, Any]:
        binding = native_agent_binding(role, "verification", registry)
        return {
            "node_id": node_id,
            "role": role,
            "native_agent": binding["native_agent"],
            "requires": sorted(requires),
            "node_class": "verification",
            "permission": binding["permission"],
        }

    evidence = [
        node(f"evidence:{axis}", axis, [])
        for axis in evidence_axes
    ]
    probes = [
        node(
            f"probe:{axis}",
            "QC" if axis == "EXT" else axis,
            [f"evidence:{item}" for item in probe_requirements[axis]],
        )
        for axis in probe_axes
    ]
    mapped = node(
        "map:PA",
        "PA",
        [
            *[f"evidence:{axis}" for axis in evidence_axes],
            *[f"probe:{axis}" for axis in probe_axes],
        ],
    )
    tasks = [*evidence, *probes, mapped]
    _, errors = topological_waves(tasks, registry=registry)
    if errors:
        raise ValueError(
            "invalid Profit Diagnosis execution DAG: " + "; ".join(errors)
        )
    return tasks


def full_audit_execution_dag(
    registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compile the fixed pre-call Full Audit axes plus seam DAG."""

    registry = load_registry() if registry is None else registry
    axes = registry["workflow_contracts"]["full_audit_v3"]["axes"]

    def node(
        node_id: str,
        role: str,
        requires: list[str],
    ) -> dict[str, Any]:
        binding = native_agent_binding(role, "verification", registry)
        return {
            "node_id": node_id,
            "role": role,
            "native_agent": binding["native_agent"],
            "requires": sorted(requires),
            "node_class": "verification",
            "permission": binding["permission"],
        }

    audit_nodes = [node(f"audit:{axis}", axis, []) for axis in axes]
    seam = node(
        "seam:critic",
        "CC",
        [item["node_id"] for item in audit_nodes],
    )
    tasks = [*audit_nodes, seam]
    _, errors = topological_waves(tasks, registry=registry)
    if errors:
        raise ValueError("invalid Full Audit execution DAG: " + "; ".join(errors))
    return tasks


def non_call_controller_node_ids(task_facts: dict[str, Any] | None) -> set[str]:
    """Return routed role nodes whose result is the workflow-wave controller."""

    surfaces = set((task_facts or {}).get("surfaces", []))
    excluded: set[str] = set()
    if "full_audit" in surfaces:
        excluded.add("ai_economics_review")
    if "profit_diagnosis" in surfaces:
        excluded.add("profit_control")
    return excluded


def specialized_execution_surface(
    task_facts: dict[str, Any] | None,
) -> str | None:
    """Return the one saved-workflow surface that owns the call DAG."""

    surfaces = set((task_facts or {}).get("surfaces", []))
    selected = [
        surface
        for surface in ("full_audit", "profit_diagnosis")
        if surface in surfaces
    ]
    if len(selected) > 1:
        raise ValueError(
            "task facts cannot bind more than one specialized execution surface"
        )
    return selected[0] if selected else None


def _specialized_route_result_node(
    route_node: dict[str, Any],
    surface: str,
) -> str | None:
    """Map one generic route requirement to its saved-workflow owner/result."""

    node_id = route_node.get("node_id")
    role = route_node.get("role")
    if surface == "full_audit":
        if node_id == "pa_design":
            # The fixed DAG itself is the PM-owned plan; no PA model call is
            # made merely to rediscover that already-bound plan.
            return None
        if node_id == "ai_economics_review":
            # The post-wave AI-E control fragment owns the complete wave.
            return "ai_economics_review"
        if node_id == "constitutional_gate":
            return "audit:CC"
        if isinstance(role, str) and role in {
            "CC", "FA", "E2", "E3", "BB", "IB", "OPS",
            "QC", "MIT", "AI-E", "E5", "A3", "R4",
        }:
            return f"audit:{role}"
    elif surface == "profit_diagnosis":
        if node_id == "pa_design":
            return "map:PA"
        if node_id == "profit_control":
            # The deterministic AI-E controller binds the fixed wave result.
            return "profit_control"
        if role == "QC":
            # Quantitative route review is already the fixed QC probe; adding
            # the generic quant_review id would double-call the same semantics.
            return "probe:QC"
    return str(node_id) if isinstance(node_id, str) else None


def specialized_route_result_bindings(
    required_nodes: Any,
    task_facts: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Describe how routed semantics are satisfied by a specialized workflow.

    `result_node_id=None` is reserved for a deterministic controller-owned
    planning step.  Other result ids name either an actual fixed call or the
    post-wave controller fragment.  This projection is also used by closure so
    a generic route fragment is never demanded in addition to its fixed call.
    """

    try:
        surface = specialized_execution_surface(task_facts)
    except ValueError as error:
        return [], [str(error)]
    if surface is None:
        return [], []
    if not isinstance(required_nodes, list) or any(
        not isinstance(node, dict) for node in required_nodes
    ):
        return [], ["routed execution nodes must be an array of objects"]
    bindings: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for node in required_nodes:
        node_id = node.get("node_id")
        role = node.get("role")
        if not isinstance(node_id, str) or not node_id or node_id in seen:
            errors.append("routed execution node ids are invalid or duplicate")
            continue
        seen.add(node_id)
        if not isinstance(role, str) or not role:
            errors.append(f"routed execution node {node_id} role is invalid")
            continue
        result_node_id = _specialized_route_result_node(node, surface)
        bindings.append({
            "route_node_id": node_id,
            "route_role": role,
            "result_node_id": result_node_id,
            "controller_owned": result_node_id is None
            or result_node_id in {"ai_economics_review", "profit_control"},
        })

    # A fixed saved-workflow result cannot consume a predecessor that only a
    # fresh generic phase can execute. Preserve that predecessor's complete
    # downstream verification chain as explicit extras; otherwise a writer can
    # be stranded while its E2/E4 reviewers are incorrectly absorbed by fixed
    # audit nodes, turning a valid typed split into a topology error.
    binding_by_id = {
        binding["route_node_id"]: binding for binding in bindings
    }
    unmatched = {
        binding["route_node_id"]
        for binding in bindings
        if binding["result_node_id"] == binding["route_node_id"]
        and not binding["controller_owned"]
    }
    changed = True
    while changed:
        changed = False
        for node in required_nodes:
            node_id = node.get("node_id")
            requires = node.get("requires")
            if (
                not isinstance(node_id, str)
                or node_id in unmatched
                or not isinstance(requires, list)
            ):
                continue
            if any(required in unmatched for required in requires):
                binding = binding_by_id.get(node_id)
                if binding is not None:
                    binding["result_node_id"] = node_id
                    binding["controller_owned"] = False
                    unmatched.add(node_id)
                    changed = True
    return bindings, errors


def task_execution_projection(
    required_nodes: Any,
    admitted_nodes: Any,
    *,
    task_facts: dict[str, Any] | None,
    registry: dict[str, Any] | None = None,
    require_fixed_admissions: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Compile the one canonical call DAG for generic and saved workflows.

    Generic routes retain their delegated node ids.  Full Audit and Profit
    Diagnosis instead begin with their fixed workflow DAG; routed semantic
    roles are represented by fixed calls or explicit controller ownership.
    Generic routes may admit an exact superset for a separately selected host
    executor.  A specialized Context may only identify unmatched route calls
    so the caller can split them into a freshly compiled non-specialized phase;
    neither implicit nor explicit admissions may extend the fixed saved
    workflow graph.
    """

    try:
        surface = specialized_execution_surface(task_facts)
    except ValueError as error:
        return [], [str(error)]
    if surface is None:
        return delegated_execution_projection(
            required_nodes,
            admitted_nodes,
            excluded_nodes=non_call_controller_node_ids(task_facts),
            registry=registry,
        )
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

    registry = load_registry() if registry is None else registry
    fixed = (
        full_audit_execution_dag(registry)
        if surface == "full_audit"
        else profit_diagnosis_execution_dag(registry)
    )
    fixed_by_id = {node["node_id"]: node for node in fixed}
    route_bindings, errors = specialized_route_result_bindings(
        required_nodes, task_facts,
    )
    binding_by_route = {
        binding["route_node_id"]: binding["result_node_id"]
        for binding in route_bindings
    }
    controller_owned_route_ids = {
        binding["route_node_id"]
        for binding in route_bindings
        if binding["controller_owned"]
    }
    represented_route_ids = set(binding_by_route)

    admitted_by_id = {
        str(node["node_id"]): node for node in admitted_nodes
    }
    for node_id, fixed_node in fixed_by_id.items():
        admission = admitted_by_id.get(node_id)
        if require_fixed_admissions and admission is None:
            errors.append(
                f"specialized {surface} dispatch omits fixed call admission {node_id}"
            )
            continue
        if (
            admission is not None
            and execution_node_core(admission) != fixed_node
        ):
            errors.append(
                f"specialized {surface} admission substitutes fixed call node {node_id}"
            )

    def project_requires(
        node_id: str,
        requires: Any,
    ) -> list[str]:
        if not isinstance(requires, list) or requires != sorted(set(requires)):
            errors.append(
                f"dispatch execution node {node_id} requires are not sorted unique"
            )
            return []
        projected: set[str] = set()
        for required in requires:
            if not isinstance(required, str):
                errors.append(
                    f"dispatch execution node {node_id} requires are invalid"
                )
                continue
            if required in binding_by_route:
                representative = binding_by_route[required]
                if representative is not None and representative not in {
                    "ai_economics_review", "profit_control",
                }:
                    projected.add(representative)
                continue
            if required in fixed_by_id:
                projected.add(required)
                continue
            if required in node_ids:
                projected.add(required)
                continue
            errors.append(
                f"dispatch execution node {node_id} requires unknown predecessor {required}"
            )
        projected.discard(node_id)
        return sorted(projected)

    route_extras: list[dict[str, Any]] = []
    for node in required_nodes:
        node_id = str(node["node_id"])
        representative = binding_by_route.get(node_id)
        if (
            node_id not in represented_route_ids
            or (
                representative == node_id
                and node_id not in controller_owned_route_ids
            )
        ):
            route_extras.append({
                **execution_node_core(node),
                "requires": project_requires(node_id, node.get("requires")),
            })

    admitted_extras: list[dict[str, Any]] = []
    for node in admitted_nodes:
        node_id = str(node["node_id"])
        if node_id in fixed_by_id:
            continue
        admitted_extras.append({
            **execution_node_core(node),
            "requires": project_requires(node_id, node.get("requires")),
        })

    projected = [*fixed, *route_extras, *admitted_extras]
    projected_ids = {node["node_id"] for node in projected}
    for node in projected:
        missing = set(node["requires"]) - projected_ids
        if missing:
            errors.append(
                f"specialized {surface} node {node['node_id']} requires absent calls {sorted(missing)}"
            )
    _, topology_errors = topological_waves(projected, registry=registry)
    errors.extend(topology_errors)
    return projected, errors


def specialized_workflow_split_exception(
    execution_dag: Any,
    task_facts: dict[str, Any] | None,
    *,
    registry: dict[str, Any] | None = None,
) -> SpecializedWorkflowSplitRequired | None:
    """Classify only an exact fixed core plus well-formed additional calls."""

    try:
        surface = specialized_execution_surface(task_facts)
    except ValueError:
        return None
    if surface is None:
        return None
    if not isinstance(execution_dag, list) or any(
        not isinstance(node, dict) for node in execution_dag
    ):
        return None
    registry = load_registry() if registry is None else registry
    fixed = (
        full_audit_execution_dag(registry)
        if surface == "full_audit"
        else profit_diagnosis_execution_dag(registry)
    )
    fixed_ids = {node["node_id"] for node in fixed}
    if (
        len(fixed_ids) != len(fixed)
        or any(set(node) != set(EXECUTION_NODE_FIELDS) for node in execution_dag)
    ):
        return None
    node_ids = [node.get("node_id") for node in execution_dag]
    if (
        any(not isinstance(node_id, str) or not node_id for node_id in node_ids)
        or len(node_ids) != len(set(node_ids))
    ):
        return None
    fixed_projection = [
        execution_node_core(node)
        for node in execution_dag
        if node["node_id"] in fixed_ids
    ]
    if fixed_projection != fixed:
        return None
    try:
        compile_context_execution_dag_binding(execution_dag, registry=registry)
        # Import locally because routing owns the public task normalizer and
        # itself imports this module's projection primitives.
        from agent_governance_routing import route_task

        routed = route_task(task_facts or {}, registry=registry)
        expected, projection_errors = task_execution_projection(
            routed["required_role_nodes"],
            [],
            task_facts=routed["task_facts"],
            registry=registry,
        )
    except (KeyError, TypeError, ValueError):
        return None
    if projection_errors:
        return None
    expected_extras = {
        node["node_id"]: execution_node_core(node)
        for node in expected
        if node["node_id"] not in fixed_ids
    }
    supplied_extras = {
        node["node_id"]: execution_node_core(node)
        for node in execution_dag
        if node["node_id"] not in fixed_ids
    }
    if not expected_extras or supplied_extras != expected_extras:
        return None
    extra_ids = sorted(expected_extras)
    return SpecializedWorkflowSplitRequired(surface, extra_ids)


def compiler_derived_specialized_split_errors(
    execution_dag: Any,
    task_facts: dict[str, Any] | None,
    *,
    registry: dict[str, Any] | None = None,
) -> list[str]:
    """Compatibility wrapper for callers that still consume string errors."""

    error = specialized_workflow_split_exception(
        execution_dag,
        task_facts,
        registry=registry,
    )
    return [str(error)] if error is not None else []


def delegated_execution_projection(
    required_nodes: Any,
    admitted_nodes: Any,
    *,
    excluded_nodes: set[str] | None = None,
    registry: dict[str, Any] | None = None,
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
    _, topology_errors = topological_waves(projected, registry=registry)
    errors.extend(topology_errors)
    return projected, errors


def explicit_execution_dag_route_errors(
    tasks: Any,
    required_nodes: Any,
    task_facts: dict[str, Any] | None,
    *,
    registry: dict[str, Any] | None = None,
) -> list[str]:
    """Require caller DAGs to retain every canonical routed call node.

    Generic routes may admit extra nodes, but a caller cannot omit a routed node
    or reuse its node id with a different role/native/class/permission/predecessor
    core. Saved-workflow controller nodes that do not themselves make a call are
    projected out through the same canonical rule used by Context defaults.
    Specialized exact supersets are rejected separately because their saved
    executors cannot run the additional calls.
    """

    canonical, errors = task_execution_projection(
        required_nodes,
        [],
        task_facts=task_facts,
        registry=registry,
    )
    if errors:
        return [
            "cannot derive routed call-producing DAG: " + "; ".join(errors)
        ]
    if not isinstance(tasks, list):
        return ["explicit Context execution DAG must be an array"]
    supplied_by_id = {
        task.get("node_id"): task
        for task in tasks
        if isinstance(task, dict) and isinstance(task.get("node_id"), str)
    }
    route_errors: list[str] = []
    for required in canonical:
        node_id = str(required["node_id"])
        supplied = supplied_by_id.get(node_id)
        if supplied is None:
            surface = specialized_execution_surface(task_facts)
            if surface is None:
                route_errors.append(
                    f"explicit Context execution DAG omits routed call-producing node {node_id}"
                )
            else:
                route_errors.append(
                    f"explicit Context execution DAG does not authorize specialized {surface} workflow: omits fixed call node {node_id}"
                )
        elif execution_node_core(supplied) != required:
            surface = specialized_execution_surface(task_facts)
            if surface is None:
                route_errors.append(
                    f"explicit Context execution DAG substitutes routed call-producing node {node_id}"
                )
            else:
                route_errors.append(
                    f"explicit Context execution DAG does not authorize specialized {surface} workflow: substitutes fixed call node {node_id}"
                )
    surface = specialized_execution_surface(task_facts)
    if surface is not None:
        canonical_ids = {str(node["node_id"]) for node in canonical}
        unexpected_ids = sorted(
            str(task["node_id"])
            for task in tasks
            if isinstance(task, dict)
            and isinstance(task.get("node_id"), str)
            and task["node_id"] not in canonical_ids
        )
        if unexpected_ids:
            route_errors.append(
                f"explicit Context execution DAG does not authorize specialized {surface} workflow: adds unrouted call nodes {unexpected_ids}"
            )
    return route_errors


def topological_waves(
    tasks: list[dict[str, Any]],
    *,
    registry: dict[str, Any] | None = None,
) -> tuple[list[list[str]], list[str]]:
    node_ids = [task.get("node_id") for task in tasks]
    errors: list[str] = []
    if any(
        not isinstance(node, str)
        or not EXECUTION_NODE_ID_RE.fullmatch(node)
        for node in node_ids
    ):
        return [], ["execution DAG node ids are invalid"]
    if len(node_ids) != len(set(node_ids)):
        return [], ["execution DAG node ids are not unique"]
    node_set = set(node_ids)
    registry = load_registry() if registry is None else registry
    roles = registry["roles"]
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
                binding = native_agent_binding(role, node_class, registry)
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
