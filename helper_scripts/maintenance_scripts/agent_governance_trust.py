"""Fail-closed trust semantics layered over structural closure validation.

Self-digests prove canonical integrity only.  PASS additionally requires exact
task/context/role/criterion bindings and the evidence class appropriate to the
claim.  Runtime, external, and actual-usage claims remain unavailable until a
trusted platform verifier exists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_governance_execution_dag import (
    delegated_execution_projection,
    execution_dag_digest,
    execution_node_core,
    non_call_controller_node_ids,
    topological_waves,
)
from agent_governance_workflow_receipts import (
    canonical_digest,
    validate_role_fragment_producer,
)


REPOSITORY_AUTHORITY_CLASSES = {
    "normative_policy", "implementation_contract", "active_work_state",
}
SPECIALIZED_SURFACES = {"full_audit", "profit_diagnosis", "profit"}


def _specialized_fragment_node(node_id: str, surfaces: set[str]) -> bool:
    return (
        "full_audit" in surfaces
        and (node_id == "ai_economics_review" or node_id.startswith("audit:"))
    ) or (
        "profit_diagnosis" in surfaces
        and (
            node_id == "profit_control"
            or node_id.startswith(("evidence:", "probe:"))
            or node_id == "map:PA"
        )
    )


def _specialized_nested_node(node_id: str, surfaces: set[str]) -> bool:
    return "full_audit" in surfaces and node_id.startswith(
        ("verify:", "seam:", "fix:", "review:", "regression:")
    )


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _context_source_map(context_plan: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(context_plan, dict):
        return {}
    sources = context_plan.get("sources")
    if not isinstance(sources, list):
        return {}
    return {
        item["source"]: item
        for item in sources
        if isinstance(item, dict) and isinstance(item.get("source"), str)
    }


def _context_source_value(record: dict[str, Any]) -> Any:
    encoding = record.get("content_encoding")
    content = record.get("content")
    if encoding in {"utf-8", "json"}:
        return content
    if encoding == "base64" and isinstance(content, str):
        return {"content_encoding": "base64", "content": content}
    return None


def _authority_errors(
    claims: Any,
    *,
    context_plan: dict[str, Any],
    captures: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    if not isinstance(claims, list):
        return ["authority_refs must be an array for trust binding"]
    errors: list[str] = []
    context_sources = _context_source_map(context_plan)
    task_contract = context_plan.get("task_contract", {})
    local_capture_ids = set(captures["repositories"]) | set(captures["commands"])
    platform_ids = set(captures["platform_attested"])
    runtime_ids = set(captures["runtime_attested"])
    external_policy_ids = set(captures["external_policy_attested"])
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        label = f"authority_refs[{index}]"
        authority_class = claim.get("class")
        source_ref = claim.get("source_ref")
        if authority_class in REPOSITORY_AUTHORITY_CLASSES:
            source = claim.get("source")
            expected_ref = f"context:{source}"
            record = context_sources.get(str(source))
            if source_ref != expected_ref or record is None:
                errors.append(
                    f"{label} repository authority must reference its exact pinned context source"
                )
                continue
            if claim.get("digest") != record.get("content_digest"):
                errors.append(f"{label} digest differs from exact selected context bytes")
            if claim.get("value") != _context_source_value(record):
                errors.append(
                    f"{label} value is not the deterministic identity projection of context bytes"
                )
            if claim.get("strength") != "direct":
                errors.append(f"{label} byte-backed repository authority must be direct")
            observed = _instant(claim.get("observed_at"))
            source_observed = _instant(record.get("observed_at"))
            source_expiry = _instant(record.get("expires_at"))
            if (
                observed is None or source_observed is None or source_expiry is None
                or not source_observed <= observed < source_expiry
            ):
                errors.append(f"{label} observation is outside its context capture interval")
        elif authority_class in {"runtime_observation", "external_policy"}:
            admitted_ids = (
                runtime_ids if authority_class == "runtime_observation"
                else external_policy_ids
            )
            if source_ref not in admitted_ids:
                errors.append(
                    f"{label} {authority_class} requires PLATFORM_OR_EXTERNAL_ATTESTED capture"
                )
            elif evidence_by_id.get(str(source_ref), {}).get("digest") != claim.get("digest"):
                errors.append(f"{label} digest differs from attested source capture")
            if claim.get("strength") != "direct":
                errors.append(f"{label} attested authority must be direct")
        elif authority_class == "claim_evidence":
            task_prefix = "task_contract:claim_inputs:"
            if isinstance(source_ref, str) and source_ref.startswith(task_prefix):
                key = source_ref[len(task_prefix):]
                admitted_digest = task_contract.get("claim_inputs", {}).get(key)
                if admitted_digest is None or admitted_digest != claim.get("digest"):
                    errors.append(f"{label} differs from the admitted task claim input")
                if claim.get("strength") != "derived":
                    errors.append(f"{label} task-input claim evidence must be derived")
            else:
                if source_ref not in local_capture_ids | platform_ids:
                    errors.append(f"{label} claim evidence source_ref is not a validated capture")
                elif evidence_by_id.get(str(source_ref), {}).get("digest") != claim.get("digest"):
                    errors.append(f"{label} digest differs from referenced capture")
                if claim.get("strength") == "asserted":
                    errors.append(f"{label} asserted claim evidence cannot support closure")
        else:
            errors.append(f"{label} has no trust policy for authority class")
    return errors


def _fragment_errors(
    fragments_by_node: dict[str, dict[str, Any]],
    *,
    captures: dict[str, Any],
    valid_effect_receipt_ids: set[str],
    task_contract_digest: str,
    context_artifact_digest: str,
    specialized_surfaces: set[str],
) -> list[str]:
    errors: list[str] = []
    direct_ids = (
        set(captures["repositories"])
        | set(captures["changes"])
        | set(captures["commands"])
        | set(captures["waves"])
        | valid_effect_receipt_ids
    )
    direct_ids |= set(captures["platform_attested"])
    for node_id, fragment in fragments_by_node.items():
        specialized_node = _specialized_fragment_node(
            node_id, specialized_surfaces
        )
        producer_errors = validate_role_fragment_producer(
            fragment,
            calls_by_id=captures["calls"],
            wave_records_by_digest=captures["waves"],
            expected_task_contract_digest=task_contract_digest,
            expected_context_artifact_digest=context_artifact_digest,
            allow_payload_projection=specialized_node,
            skip_result_projection=specialized_node,
        )
        errors.extend(
            f"role fragment {node_id} producer binding: {error}"
            for error in producer_errors
        )
        if fragment.get("gate_verdict") == "PASS":
            refs = set(fragment.get("evidence_refs", []))
            if not refs & direct_ids:
                errors.append(
                    f"role fragment {node_id} PASS lacks direct captured source/test/attested evidence"
                )
    return errors


def _acceptance_errors(
    packet: dict[str, Any],
    *,
    captures: dict[str, Any],
    valid_effect_receipt_ids: set[str] | None = None,
    fragments_by_node: dict[str, dict[str, Any]],
    expected_route: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    source_ids = set(captures["repositories"]) | set(captures["changes"])
    command_ids = set(captures["commands"])
    runtime_ids = set(captures["runtime_attested"]) | set(
        valid_effect_receipt_ids or ()
    )
    outcome_ids = set(captures["outcome_attested"])
    task_facts = (expected_route or {}).get("task_facts", {})
    runtime_claim = bool(task_facts.get("runtime_claim"))
    end_to_end_claim = bool(task_facts.get("end_to_end_claim"))
    for index, item in enumerate(packet.get("acceptance", [])):
        if not isinstance(item, dict) or item.get("status") != "PASS":
            continue
        refs = set(item.get("evidence_refs", []))
        if end_to_end_claim:
            if not refs & outcome_ids:
                errors.append(
                    f"acceptance[{index}] end-to-end PASS requires platform/external-attested outcome capture"
                )
        elif runtime_claim:
            if not refs & runtime_ids:
                errors.append(
                    f"acceptance[{index}] runtime PASS requires platform/external-attested runtime capture"
                )
        elif not refs & (source_ids | command_ids):
            errors.append(
                f"acceptance[{index}] source/test PASS requires repository or command capture"
            )
        supporting_fragments = [
            fragment for fragment in fragments_by_node.values()
            if fragment.get("gate_verdict") == "PASS"
            and fragment.get("classification") == "FACT"
            and fragment.get("confidence") in {"high", "med"}
            and refs.intersection(fragment.get("evidence_refs", []))
        ]
        if not supporting_fragments:
            errors.append(
                f"acceptance[{index}] has no independently call-bound FACT verifier for its exact evidence refs"
            )
    return errors


def _check_errors(
    checks: Any,
    *,
    captures: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
) -> list[str]:
    if not isinstance(checks, list):
        return ["checks must be an array for command capture binding"]
    errors: list[str] = []
    commands = captures["commands"]
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            continue
        status = check.get("status")
        if status not in {"EXECUTED", "REUSED"}:
            continue
        capture_ref = check.get("command_capture_ref")
        capture = commands.get(str(capture_ref))
        if capture is None:
            errors.append(f"checks[{index}] {status} lacks a validated command capture")
            continue
        if capture.get("result") != "PASS":
            errors.append(f"checks[{index}] command capture did not PASS")
        if capture.get("command") != check.get("command"):
            errors.append(f"checks[{index}] command differs from captured argv")
        if check.get("evidence_ref") != capture_ref:
            errors.append(f"checks[{index}] evidence_ref must be its command capture ref")
        if check.get("signature") != capture.get("record_digest"):
            errors.append(f"checks[{index}] signature must bind the command capture record")
        if status == "EXECUTED" and check.get("executed_at") != capture.get("completed_at"):
            errors.append(f"checks[{index}] executed_at differs from command capture")
        supporters = [
            fragment for fragment in fragments_by_node.values()
            if capture_ref in fragment.get("evidence_refs", [])
            and fragment.get("node_id") == capture.get("node_id")
            and fragment.get("role") == capture.get("role_id")
        ]
        if not supporters:
            errors.append(
                f"checks[{index}] command capture is not bound to its exact role/node fragment"
            )
    return errors


def _mutation_errors(
    packet: dict[str, Any], captures: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    changes = list(captures["changes"].items())
    mutation = bool(packet.get("side_effects", {}).get("repo_mutation"))
    observed_changes = [
        (evidence_id, record) for evidence_id, record in changes
        if record.get("mutation_observed") is True
    ]
    if mutation:
        if packet.get("disposition") != "CHANGED":
            errors.append("repo mutation trust binding requires CHANGED disposition")
        if not observed_changes:
            errors.append("repo mutation requires an ordered before/after repository change chain")
        for evidence_id, record in observed_changes:
            supporters = [
                fragment for fragment in packet.get("role_fragments", [])
                if isinstance(fragment, dict)
                and evidence_id in fragment.get("evidence_refs", [])
                and fragment.get("node_id") == record.get("node_id")
                and fragment.get("role") == record.get("role_id")
            ]
            if not supporters:
                errors.append(
                    f"repository change record {evidence_id} is not bound to its exact writer role/node"
                )
    elif observed_changes:
        errors.append("repository change record proves mutation while repo_mutation=false")
    return errors


def _wave_errors(
    packet: dict[str, Any],
    captures: dict[str, Any],
    expected_route: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    waves = list(captures["waves"].values())
    surfaces = set((expected_route or {}).get("task_facts", {}).get("surfaces", []))
    specialized_surfaces = surfaces & SPECIALIZED_SURFACES
    dispatch = packet.get("dispatch", {})
    required_nodes = dispatch.get("required_role_nodes", [])
    admitted_nodes = dispatch.get("admitted_role_nodes", [])
    projection, projection_errors = delegated_execution_projection(
        required_nodes,
        admitted_nodes,
        excluded_nodes=non_call_controller_node_ids(
            (expected_route or {}).get("task_facts", {})
        ),
    )
    errors.extend(
        f"closure dispatch execution projection: {error}"
        for error in projection_errors
    )
    expected_digest = execution_dag_digest(projection)
    expected_waves, topology_errors = topological_waves(projection)
    errors.extend(
        f"closure dispatch execution projection: {error}"
        for error in topology_errors
        if error not in projection_errors
    )
    if dispatch.get("dag_digest") != expected_digest:
        errors.append("closure dispatch dag_digest differs from delegated execution projection")
    if projection and len(waves) != 1:
        errors.append(
            "closure dispatch execution projection requires exactly one complete workflow wave receipt"
        )
    elif not projection and waves:
        errors.append("workflow waves exist without a delegated execution projection")

    fragments = {
        fragment.get("node_id"): fragment
        for fragment in packet.get("role_fragments", [])
        if isinstance(fragment, dict) and isinstance(fragment.get("node_id"), str)
    }
    dispatch_binding = {
        node.get("node_id"): node
        for node in [*required_nodes, *admitted_nodes]
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    if waves:
        wave = waves[0]
        wave_tasks = wave.get("admitted_tasks", [])
        wave_core = [
            execution_node_core(task)
            for task in wave_tasks
            if isinstance(task, dict)
        ] if isinstance(wave_tasks, list) else []
        if wave_core != projection:
            errors.append("workflow wave admitted tasks differ from dispatch projection")
        if wave.get("dag_digest") != expected_digest:
            errors.append("workflow wave dag_digest differs from closure dispatch")
        if wave.get("execution_waves") != expected_waves:
            errors.append("workflow wave execution_waves differ from dispatch projection")
        result_map = wave.get("result_fragment_digests", {})
        expected_result_nodes = {node["node_id"] for node in projection}
        if not isinstance(result_map, dict) or set(result_map) != expected_result_nodes:
            errors.append("workflow wave result inventory differs from dispatch projection")
            result_map = {}
        wave_task_by_node = {
            task.get("node_id"): task
            for task in wave_tasks
            if isinstance(task, dict) and isinstance(task.get("node_id"), str)
        } if isinstance(wave_tasks, list) else {}
        for task in projection:
            node_id = task["node_id"]
            binding = dispatch_binding.get(node_id, {})
            result_binding = binding.get("result_binding", "role_fragment")
            fragment = fragments.get(node_id)
            if result_binding == "nested_payload":
                if fragment is not None:
                    errors.append(
                        f"workflow nested node {node_id} unexpectedly claims a closure role fragment"
                    )
                continue
            if fragment is None:
                errors.append(
                    f"workflow admitted node {node_id} is not closure/dispatch bound"
                )
                continue
            if fragment.get("producer_record_kind") != "workflow_call_record_v1":
                errors.append(
                    f"workflow admitted node {node_id} is not produced by its recorded call"
                )
            wave_task = wave_task_by_node.get(node_id, {})
            if (
                fragment.get("role") != task.get("role")
                or fragment.get("payload_kind") != wave_task.get("payload_kind")
            ):
                errors.append(
                    f"workflow admitted node {node_id} role/payload differs from closure fragment"
                )
            if result_map.get(node_id) != canonical_digest(fragment):
                errors.append(
                    f"workflow admitted node {node_id} result digest differs from closure fragment"
                )
        for extra_wave in waves[1:]:
            for task in extra_wave.get("admitted_tasks", []):
                node_id = task.get("node_id") if isinstance(task, dict) else None
                if node_id not in expected_result_nodes:
                    errors.append(
                        f"workflow admitted node {node_id} is not closure/dispatch bound"
                    )
    wave_owned_digests = {
        fragment.get("producer_call_receipt_digest")
        for fragment in fragments.values()
        if fragment.get("producer_record_kind") == "workflow_wave_record_v1"
    }
    if specialized_surfaces and wave_owned_digests != set(captures["waves"]):
        errors.append(
            "specialized workflow waves must be owned exactly once by controller fragments"
        )
    if packet.get("gate_verdict") == "PASS":
        for wave in waves:
            if wave.get("final_null_node_count"):
                errors.append("closure PASS cannot hide final-null workflow nodes")
            if wave.get("coverage_debt"):
                errors.append("closure PASS cannot retain workflow coverage debt")
    return errors


def validate_closure_trust(
    packet: dict[str, Any],
    *,
    captures: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    context_plan: dict[str, Any],
    task_contract_digest: str,
    expected_route: dict[str, Any] | None,
    fragments_by_node: dict[str, dict[str, Any]],
    valid_effect_receipt_ids: set[str] | None = None,
) -> list[str]:
    """Apply evidence-class, authenticity-boundary, and consumption preconditions."""

    context_artifact_digest = packet.get("dispatch", {}).get(
        "context_artifact", {}
    ).get("artifact_digest")
    surfaces = set((expected_route or {}).get("task_facts", {}).get("surfaces", []))
    effect_receipt_ids = set(valid_effect_receipt_ids or ())
    errors = list(captures.get("errors", []))
    errors.extend(
        _authority_errors(
            packet.get("authority_refs"),
            context_plan=context_plan,
            captures=captures,
            evidence_by_id=evidence_by_id,
        )
    )
    errors.extend(
        _fragment_errors(
            fragments_by_node,
            captures=captures,
            valid_effect_receipt_ids=effect_receipt_ids,
            task_contract_digest=task_contract_digest,
            context_artifact_digest=str(context_artifact_digest),
            specialized_surfaces=surfaces & SPECIALIZED_SURFACES,
        )
    )
    errors.extend(
        _acceptance_errors(
            packet,
            captures=captures,
            valid_effect_receipt_ids=effect_receipt_ids,
            fragments_by_node=fragments_by_node,
            expected_route=expected_route,
        )
    )
    errors.extend(
        _check_errors(
            packet.get("checks"),
            captures=captures,
            fragments_by_node=fragments_by_node,
        )
    )
    errors.extend(_mutation_errors(packet, captures))
    errors.extend(_wave_errors(packet, captures, expected_route))
    return errors
