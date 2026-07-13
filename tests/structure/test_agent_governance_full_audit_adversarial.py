from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "helper_scripts" / "maintenance_scripts" / "agent_governance.py"
SUPPORT_PATH = ROOT / "tests/structure/test_development_agent_governance.py"
ADMITTED_CAP_FIELDS = (
    "max_context_tokens_per_call", "max_prompt_utf8_bytes_per_call",
    "max_workflow_planned_input_tokens", "max_unique_nodes",
    "max_call_attempts", "retry_budget",
)
NODE_STDIN_ARGS = "JSON.parse(fs.readFileSync(0, 'utf8'))"


def _load_governance():
    spec = importlib.util.spec_from_file_location("agent_governance", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _host_execution_verifier(packet: dict):
    spec = importlib.util.spec_from_file_location("full_audit_attestation_support", SUPPORT_PATH)
    assert spec is not None and spec.loader is not None
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    return support._test_execution_attestation_verifier(packet)


def _digest(value) -> str:
    rendered = _canonical(value)
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _admitted_caps(authority: dict) -> dict:
    return {field: authority[field] for field in ADMITTED_CAP_FIELDS}


def _role_fragment(
    registry: dict,
    node_id: str,
    role: str,
    payload: dict,
    task_contract_digest: str,
) -> dict:
    return {
        "schema_version": "role_fragment_v1",
        "id": f"fragment:{node_id}",
        "node_id": node_id,
        "role": role,
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "classification": "FACT",
        "confidence": "high",
        "summary": f"{node_id} completed",
        "task_contract_digest": task_contract_digest,
        "evidence_refs": ["ev-source-1", "ev-repo-authority"],
        "concerns": [],
        "next_action": {"owner": "PM", "action": "integrate immutable fragment"},
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform telemetry unavailable",
        },
        "payload_kind": registry["roles"][role]["payload_kind"],
        "payload": payload,
    }


def _refresh_full_lineage(governance: object, packet: dict, contract: dict) -> None:
    context = packet["dispatch"]["context_artifact"]
    task = packet["dispatch"]["task_facts"]
    task_digest = context["task_contract_digest"]
    context_digest = context["artifact_digest"]
    dirty_scope = task["dirty_scope"]
    focus = task.get("focus", "")
    workflow_digest = _digest({"workflow": "full-audit-fixture", "context": context_digest})
    observed = packet["adjudicated_at"]
    calls = []
    results = {}
    controller = _controller(packet, contract)
    registry = governance.load_registry()
    call_tasks: dict[str, dict] = {}
    nested_admissions: list[dict] = []

    def admit_nested(node: str, role: str, requires: list[str], reason: str) -> None:
        nested_admissions.append({
            "node_id": node, "role": role,
            **governance.native_agent_binding(role, "verification"),
            "node_class": "verification", "requires": sorted(set(requires)),
            "path_scope": [], "reason": reason,
            "result_binding": "nested_payload",
        })

    audit_nodes = sorted(
        fragment["node_id"]
        for fragment in packet["role_fragments"]
        if fragment["node_id"].startswith("audit:")
    )
    for fragment in packet["role_fragments"]:
        if fragment is controller:
            continue
        node = fragment["node_id"]
        if node.startswith("audit:"):
            for outcome_record in fragment["payload"]["verification_outcomes"]:
                outcome = outcome_record["outcome"]
                claim_id = outcome["claim_id"]
                vote_nodes = {
                    vote["view"]: f"verify:{claim_id}:{vote['view']}"
                    for vote in outcome["verifier_votes"]
                }
                for vote in outcome["verifier_votes"]:
                    view = vote["view"]
                    requires = [node]
                    if view == "third":
                        requires.extend(
                            vote_nodes[item]
                            for item in ("source", "impact")
                            if item in vote_nodes
                        )
                    admit_nested(
                        vote_nodes[view],
                        {"source": "E2", "impact": "PA", "third": "E3"}[view],
                        requires,
                        "full audit typed finding verification",
                    )
    admit_nested(
        "seam:critic", "CC", audit_nodes,
        "full audit cross-axis seam critic",
    )
    axis_admissions = [
        item for item in packet["dispatch"]["admitted_role_nodes"]
        if item.get("result_binding") == "role_fragment"
    ]
    packet["dispatch"]["admitted_role_nodes"] = [
        *axis_admissions, *nested_admissions,
    ]
    dag_nodes, projection_errors = governance.delegated_execution_projection(
        packet["dispatch"]["required_role_nodes"],
        packet["dispatch"]["admitted_role_nodes"],
        excluded_nodes=governance.non_call_controller_node_ids(task),
    )
    assert projection_errors == [], projection_errors
    call_tasks = {item["node_id"]: item for item in dag_nodes}
    dag_digest = governance.execution_dag_digest(dag_nodes)
    packet["dispatch"]["dag_digest"] = dag_digest
    execution_waves, topology_errors = governance.topological_waves(dag_nodes)
    assert topology_errors == [], topology_errors
    wave_by_node = {
        node: index for index, nodes in enumerate(execution_waves) for node in nodes
    }
    built_by_node: dict[str, dict] = {}

    def add_call(node: str, role: str, payload_kind: str, result: object) -> dict:
        task = call_tasks[node]
        producer_generation = {
            required: built_by_node[required]["record_digest"]
            for required in task["requires"]
        }
        call = governance.build_controller_workflow_call_record(
            workflow_contract_digest=workflow_digest,
            logical_call_id=f"full-audit-fixture:{node}:attempt:1",
            node_id=node, payload_kind=payload_kind, attempt=1,
            retry_parent_call_id=None, phase="Wave", label=f"fixture:{node}",
            requested={
                "logical_role": role,
                "platform": "claude_saved_workflow",
                "platform_requested_agent": task["native_agent"],
                "native_binding": {
                    "logical_role": role,
                    "native_agent": task["native_agent"],
                    "node_class": task["node_class"],
                    "permission": task["permission"],
                },
                "model": None, "effort": None, "isolation": None,
                "node_class": task["node_class"], "permission": task["permission"],
            },
            prompt_digest=_digest({"prompt": node}), context_artifact_digest=context_digest,
            task_contract_digest=task_digest, dirty_scope_digest=_digest(dirty_scope),
            focus_digest=_digest(focus), compiler_input_tokens_lower_bound=0,
            admitted_input_tokens_lower_bound=0,
            response_schema_digest=_digest({"response": node}),
            started_at=observed, ended_at=observed, returned_null=False,
            parsed_result_digest=_digest(result),
            dag_digest=dag_digest, requires=task["requires"],
            topological_wave=wave_by_node[node],
            producer_generation=producer_generation,
        )
        calls.append(call)
        built_by_node[node] = call
        results[node] = call["parsed_result_digest"]
        return call

    for fragment in packet["role_fragments"]:
        fragment["task_contract_digest"] = task_digest
        if fragment is controller:
            continue
        node = fragment["node_id"]
        if node.startswith("audit:"):
            raw = {
                key: value
                for key, value in fragment["payload"]["audit"].items()
                if key != "axis"
            }
            call = add_call(node, fragment["role"], fragment["payload_kind"], raw)
            fragment.update({
                "context_artifact_digest": context_digest,
                "producer_record_kind": "workflow_call_record_v1",
                "producer_call_ref": call["logical_call_id"],
                "producer_call_receipt_digest": call["record_digest"],
            })
            for record in fragment["payload"]["verification_outcomes"]:
                outcome = record["outcome"]
                ordered_votes = sorted(
                    outcome["verifier_votes"],
                    key=lambda vote: {"source": 0, "impact": 1, "third": 2}[vote["view"]],
                )
                for vote in ordered_votes:
                    view = vote["view"]
                    projection = {key: vote[key] for key in ("refuted", "confidence", "reason", "evidence")}
                    if view == "third":
                        projection["reachable"] = vote["reachable"]
                    role = {"source": "E2", "impact": "PA", "third": "E3"}[view]
                    call = add_call(
                        f"verify:{outcome['claim_id']}:{view}", role,
                        governance.load_registry()["roles"][role]["payload_kind"], projection,
                    )
                    vote.update({
                        "producer_record_kind": "workflow_call_record_v1",
                        "producer_call_ref": call["logical_call_id"],
                        "producer_call_receipt_digest": call["record_digest"],
                    })
                record["outcome_digest"] = _digest(outcome)
        else:
            raw = {
                key: fragment[key] for key in (
                    "work_status", "gate_verdict", "classification", "confidence",
                    "summary", "evidence_refs", "concerns", "next_action", "payload",
                )
            }
            call = add_call(node, fragment["role"], fragment["payload_kind"], raw)
            fragment.update({
                "context_artifact_digest": context_digest,
                "producer_record_kind": "workflow_call_record_v1",
                "producer_call_ref": call["logical_call_id"],
                "producer_call_receipt_digest": call["record_digest"],
            })
        results[node] = _digest(fragment)
    control = controller["payload"]
    seam_call = add_call(
        "seam:critic", "CC", governance.load_registry()["roles"]["CC"]["payload_kind"],
        control["seam_result"],
    )
    control.update({
        "workflow_contract_digest": workflow_digest,
        "seam_call_ref": seam_call["logical_call_id"],
        "seam_call_receipt_digest": seam_call["record_digest"],
        "axis_fragment_digests": {
            item["node_id"]: _digest(item)
            for item in packet["role_fragments"] if item["node_id"].startswith("audit:")
        },
    })
    results["seam:critic"] = seam_call["parsed_result_digest"]
    calls.sort(key=lambda item: (item["topological_wave"], item["logical_call_id"]))
    manifest = governance.build_workflow_call_manifest(calls, workflow_contract_digest=workflow_digest)
    call_by_node = {call["node_id"]: call for call in calls}
    admitted_tasks = [{
        "node_id": task["node_id"], "role": task["role"],
        "native_agent": task["native_agent"],
        "requires": task["requires"],
        "node_class": task["node_class"], "permission": task["permission"],
        "payload_kind": call_by_node[task["node_id"]]["payload_kind"],
        "task_contract_digest": task_digest,
        "context_artifact_digest": context_digest,
        "description_digest": _digest(task["node_id"]),
        "base_prompt_digest": call_by_node[task["node_id"]]["prompt_digest"],
        "requested": call_by_node[task["node_id"]]["requested"],
        "dirty_scope": dirty_scope, "dirty_scope_digest": _digest(dirty_scope),
        "focus": focus, "focus_digest": _digest(focus),
        "compiler_estimated_input_tokens": 0, "admitted_input_tokens_lower_bound": 0,
    } for task in dag_nodes]
    authority = json.loads(context["budget_authority_canonical"])
    budget_authority = {
        "authority_digest": context["budget_authority_digest"],
        "authority_canonical": context["budget_authority_canonical"],
        "admitted_caps": _admitted_caps(authority),
    }
    wave = governance.build_workflow_wave_record(
        manifest=manifest,
        admitted_tasks=admitted_tasks,
        budget_authority=budget_authority,
        result_fragment_digests={
            call["node_id"]: results[call["node_id"]] for call in calls
        },
        accounting_boundary={
            "usage_measurement_status": "unavailable",
            "controller_overhead_status": "unavailable",
            "excluded_from_token_lower_bounds": [
                "semantic fixture has no platform telemetry or compiler estimate"
            ],
        },
    )
    control.update({
        "call_manifest_digest": manifest["manifest_digest"],
        "workflow_wave_record_digest": wave["record_digest"],
    })
    controller.update({
        "context_artifact_digest": context_digest,
        "producer_record_kind": "workflow_wave_record_v1",
        "producer_call_ref": wave["record_digest"],
        "producer_call_receipt_digest": wave["record_digest"],
    })
    packet["evidence"] = [
        item for item in packet["evidence"]
        if item["id"] not in {"ev-full-call-manifest", "ev-full-wave"}
    ] + [
        {"id": "ev-full-call-manifest", "scope": "data", "kind": "workflow_call_manifest_v1", "digest": manifest["manifest_digest"], "artifact": manifest},
        {"id": "ev-full-wave", "scope": "data", "kind": "workflow_wave_record_v1", "digest": wave["record_digest"], "artifact": wave},
    ]
    packet["consumption"] = {
        "measurement_status": "partial", "measurement_source": "orchestrator_receipt",
        "unavailable_reason": "actual platform usage unavailable in semantic fixture",
        "wave_record_refs": ["ev-full-wave"],
        "missing_metrics": ["input_tokens", "output_tokens", "cache_read_tokens", "tool_calls", "wall_time_ms", "accepted_findings", "rework_count"],
        "planned_tokens": 0, "retry_count": 0, "fan_out": len(calls),
        "quality_reserve_used": False,
    }


def _clean_packet() -> tuple[object, dict, dict]:
    governance = _load_governance()
    registry = governance.load_registry()
    contract = registry["workflow_contracts"]["full_audit_v3"]
    axes = contract["axes"]
    criterion = "full audit closed mandatory coverage"
    scope = sorted([
        ".claude/workflows/openclaw-full-audit.js",
        "CLAUDE.md",
        "helper_scripts/maintenance_scripts/agent_governance_full_audit.py",
    ])
    source_baseline = governance.capture_repository_baseline()
    task_facts = {
        "task_shape": "audit",
        "surfaces": ["agent_workflow", "full_audit"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "objective": "audit",
        "scope": scope,
        "acceptance_criteria": [criterion],
        "hard_stops": ["no runtime or broker effect"],
        "baseline": source_baseline,
        "direct_interfaces": ["full_audit_v3", "closure_packet_v1"],
        "previous_failure": "typed verifier semantics were not closure-bound",
    }
    route = governance.route_task(task_facts)
    context_plan = governance.compile_context("PM", route["task_facts"])
    assert context_plan["budget"]["pass_allowed"] is True
    context_artifact = governance.materialize_context_artifact(context_plan)
    adjudicated = datetime.now(timezone.utc) + timedelta(seconds=2)
    observed = adjudicated - timedelta(seconds=1)
    baseline = {
        **source_baseline,
        "runtime_head": None,
        "runtime_observed_at": None,
    }
    axis_bindings = [
        {
            "node_id": f"audit:{axis}", "role": axis,
            **governance.native_agent_binding(axis, "verification"),
            "node_class": "verification", "reason": "full audit admitted axis",
        }
        for axis in axes
    ]
    admissions = [
        {
            **binding, "requires": [], "path_scope": [],
            "result_binding": "role_fragment",
        }
        for binding in axis_bindings
    ]
    source_receipt = governance.build_source_review_receipt(
        producer_role="E2",
        command="review full-audit semantic fixture",
        baseline=baseline,
        criteria=[criterion],
        observed_at=_z(observed),
        exit_code=0,
        stdout=b"full-audit semantic fixture verified",
        stderr=b"",
    )
    repository_capture = governance.capture_repository(scope)
    policy_source = next(item for item in context_plan["sources"] if item["source"] == "AGENTS.md")
    authority = governance.build_authority_claim(
        authority_class="normative_policy",
        subject="full_audit_closure_policy",
        value=policy_source["content"],
        source=policy_source["source"],
        source_ref=f"context:{policy_source['source']}",
        source_digest=policy_source["content_digest"],
        observed_at=_z(observed),
        scope="repo",
        strength="direct",
        expiry=None,
    )
    packet = {
        "schema_version": "closure_packet_v1",
        "task_id": "full-audit-semantic",
        "human_summary": {
            "objective": "audit",
            "scope": scope,
            "outcome": "audit complete",
        },
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "disposition": "NO_CHANGE_NEEDED",
        "confidence": "high",
        "adjudicated_at": _z(adjudicated),
        "baseline": baseline,
        "dispatch": {
            "task_facts": route["task_facts"],
            "context_artifact": context_artifact,
            "dag_digest": route["dag_digest"],
            "required_role_nodes": route["required_role_nodes"],
            "admitted_role_nodes": admissions,
        },
        "authority_refs": [authority],
        "acceptance": [
            {
                "criterion": criterion,
                "status": "PASS",
                    "evidence_refs": ["ev-source-1", "ev-repo-authority"],
            }
        ],
        "evidence": [
            {
                "id": "ev-source-1",
                "scope": "source",
                "kind": "source_review_receipt_v1",
                "digest": source_receipt["receipt_digest"],
                "observed_at": _z(observed),
                "artifact": source_receipt,
            },
            {
                "id": "ev-repo-authority",
                "scope": "source",
                "kind": "repository_capture_v1",
                "digest": repository_capture["record_digest"],
                "observed_at": repository_capture["observed_at"],
                "artifact": repository_capture,
            },
        ],
        "role_fragments": [],
        "checks": [],
        "side_effects": {
            "repo_mutation": False,
            "runtime_contact": False,
            "private_external_contact": False,
            "broker_effect": False,
        },
        "unverified": [],
        "skipped_roles": [
            item
            for item in route["skipped"]
            if item["role"] not in set(axes)
        ],
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform telemetry unavailable",
        },
        "next_action": {"owner": "PM", "action": "close"},
    }
    controller_payload = {
            "schema_version": "full_audit_control_v1",
        "baseline": deepcopy(baseline),
        "scheduler": "adaptive_shadow",
        "selection_surfaces": ["agent_workflow", "full_audit"],
        "run_sequence": 0,
        "adaptive_recall_approved": False,
        "adaptive_recall_authority_digest": None,
        "expected_axes": axes,
        "admitted_axes": axes,
        "deferred_axes": [],
        "axis_bindings": deepcopy(axis_bindings),
        "axis_fragment_digests": {},
        "coverage_debt": [],
        "coverage_holes": [],
        "assumption_count": 0,
        "disputed_count": 0,
        "decision_changing_findings": 0,
        "seam_present": True,
        "seam_result": {"reprobes": []},
        "seam_result_digest": _digest({"reprobes": []}),
        "pass_eligible": True,
        "unverified_projection": [],
    }
    for requirement in route["required_role_nodes"]:
        payload = (
            deepcopy(controller_payload)
            if requirement["node_id"] == contract["controller_node_id"]
            else {"node": requirement["node_id"]}
        )
        packet["role_fragments"].append(
            _role_fragment(
                registry,
                requirement["node_id"],
                requirement["role"],
                payload,
                context_plan["task_contract_digest"],
            )
        )
    for axis in axes:
        packet["role_fragments"].append(
            _role_fragment(
                registry,
                f"audit:{axis}",
                axis,
                {
                    "schema_version": "full_audit_axis_v1",
                    "audit": {
                        "axis": axis,
                        "schema_version": "audit_fragment_v2",
                        "verdict": "PASS",
                        "confidence": "high",
                        "findings": [],
                        "assumptions": [],
                        "consumption": {
                            "measurement_status": "unavailable",
                            "unavailable_reason": "platform telemetry unavailable",
                        },
                    },
                    "confirmed_decision_claim_ids": [],
                    "disputed_claim_ids": [],
                    "verification_outcomes": [],
                    "assumptions_count": 0,
                    "coverage_debt_count": 0,
                },
                context_plan["task_contract_digest"],
            )
        )
    _refresh_full_lineage(governance, packet, contract)
    errors = governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    )
    assert errors == [], errors
    return governance, contract, packet


def _controller(packet: dict, contract: dict) -> dict:
    return next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == contract["controller_node_id"]
    )


def _axis(packet: dict, axis: str) -> dict:
    return next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == f"audit:{axis}"
    )


def _rehash_axis(packet: dict, contract: dict, axis: str) -> None:
    assert _axis(packet, axis)
    _refresh_full_lineage(_load_governance(), packet, contract)


def _raw_high_finding() -> dict:
    return {
        "title": "high claim",
        "assertion": "high assertion",
        "severity": "HIGH",
        "classification": "FACT",
        "confidence": "high",
        "evidence": "source proof",
        "impact": "capital loss",
        "file": "program_code/x.py",
        "defect_type": ["other"],
        "symbol_anchor": "target",
    }


def test_full_audit_recomputes_aggregate_outcome_from_typed_votes() -> None:
    governance, contract, packet = _clean_packet()
    fragment = _axis(packet, "FA")
    raw = _raw_high_finding()
    fragment["payload"]["audit"].update({"verdict": "FINDINGS", "findings": [raw]})
    fragment.update({"work_status": "DONE_WITH_CONCERNS", "classification": "FACT"})
    outcome = {
        "claim_id": "claim-high-1",
        "claim_key": "program_code/x.py::target::high assertion::source proof",
        "axis": "FA",
        "severity": "HIGH",
        "defect_type": ["other"],
        "assertion": raw["assertion"],
        "evidence": raw["evidence"],
        "file": raw["file"],
        "symbol_anchor": raw["symbol_anchor"],
        "confirmed": False,
        "refuted": True,
        "disputed": False,
        "latent": False,
        "reachable": "not_applicable",
        "verifier_dissent": False,
        "verifier_votes": [
            {
                "view": "source",
                "refuted": True,
                "confidence": "high",
                "reason": "source disproves claim",
                "evidence": "source:e1",
                "reachable": None,
            },
            {
                "view": "impact",
                "refuted": True,
                "confidence": "high",
                "reason": "impact disproves claim",
                "evidence": "impact:e2",
                "reachable": None,
            },
        ],
        "verification_calls": 2,
    }
    fragment["payload"]["verification_outcomes"] = [
        {"outcome": outcome, "outcome_digest": _digest(outcome)}
    ]
    _rehash_axis(packet, contract, "FA")
    assert governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    ) == []

    missing_vote = deepcopy(packet)
    missing_fragment = _axis(missing_vote, "FA")
    missing_record = missing_fragment["payload"]["verification_outcomes"][0]
    missing_record["outcome"]["verifier_votes"][0]["producer_call_ref"] = "missing:vote"
    missing_record["outcome_digest"] = _digest(missing_record["outcome"])
    _controller(missing_vote, contract)["payload"]["axis_fragment_digests"]["audit:FA"] = _digest(missing_fragment)
    assert any(
        "verify:claim-high-1:source producer call is missing" in error
        for error in governance.validate_closure(missing_vote)
    )

    substituted_vote = deepcopy(packet)
    substituted_fragment = _axis(substituted_vote, "FA")
    substituted_record = substituted_fragment["payload"]["verification_outcomes"][0]
    substituted_record["outcome"]["verifier_votes"][1]["reason"] = "substituted after producer call"
    substituted_record["outcome_digest"] = _digest(substituted_record["outcome"])
    _controller(substituted_vote, contract)["payload"]["axis_fragment_digests"]["audit:FA"] = _digest(substituted_fragment)
    assert any(
        "verify:claim-high-1:impact producer call/result binding is invalid" in error
        for error in governance.validate_closure(substituted_vote)
    )

    forged = deepcopy(packet)
    forged_fragment = _axis(forged, "FA")
    forged_outcome = forged_fragment["payload"]["verification_outcomes"][0]["outcome"]
    forged_outcome.update({"confirmed": True, "refuted": False})
    forged_fragment["payload"]["verification_outcomes"][0]["outcome_digest"] = _digest(
        forged_outcome
    )
    _rehash_axis(forged, contract, "FA")
    assert any(
        "aggregate state disagrees with typed verifier votes" in error
        for error in governance.validate_closure(forged)
    )

    low_confidence = deepcopy(packet)
    low_fragment = _axis(low_confidence, "FA")
    low_outcome = low_fragment["payload"]["verification_outcomes"][0]["outcome"]
    for vote in low_outcome["verifier_votes"]:
        vote["confidence"] = "low"
    low_fragment["payload"]["verification_outcomes"][0]["outcome_digest"] = _digest(
        low_outcome
    )
    _rehash_axis(low_confidence, contract, "FA")
    assert any(
        "aggregate state disagrees with typed verifier votes" in error
        for error in governance.validate_closure(low_confidence)
    )


def test_full_audit_typed_dissent_requires_and_uses_third_vote() -> None:
    governance, contract, packet = _clean_packet()
    fragment = _axis(packet, "FA")
    raw = _raw_high_finding()
    fragment["payload"]["audit"].update({"verdict": "FINDINGS", "findings": [raw]})
    fragment.update({"work_status": "DONE_WITH_CONCERNS", "classification": "FACT"})
    outcome = {
        "claim_id": "claim-high-dissent",
        "claim_key": "program_code/x.py::target::high assertion::source proof",
        "axis": "FA",
        "severity": "HIGH",
        "defect_type": ["other"],
        "assertion": raw["assertion"],
        "evidence": raw["evidence"],
        "file": raw["file"],
        "symbol_anchor": raw["symbol_anchor"],
        "confirmed": False,
        "refuted": True,
        "disputed": False,
        "latent": False,
        "reachable": "reachable",
        "verifier_dissent": True,
        "verifier_votes": [
            {
                "view": "source",
                "refuted": True,
                "confidence": "high",
                "reason": "source refutes",
                "evidence": "source:e1",
                "reachable": None,
            },
            {
                "view": "impact",
                "refuted": False,
                "confidence": "high",
                "reason": "impact confirms",
                "evidence": "impact:e2",
                "reachable": None,
            },
            {
                "view": "third",
                "refuted": True,
                "confidence": "high",
                "reason": "third refutes and checks reachability",
                "evidence": "third:e3",
                "reachable": "reachable",
            },
        ],
        "verification_calls": 3,
    }
    fragment["payload"]["verification_outcomes"] = [
        {"outcome": outcome, "outcome_digest": _digest(outcome)}
    ]
    _rehash_axis(packet, contract, "FA")
    assert governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    ) == []

    hidden_dissent = deepcopy(packet)
    hidden_fragment = _axis(hidden_dissent, "FA")
    hidden_outcome = hidden_fragment["payload"]["verification_outcomes"][0]["outcome"]
    hidden_outcome["verifier_votes"] = hidden_outcome["verifier_votes"][:2]
    hidden_outcome.update(
        {
            "verifier_dissent": False,
            "reachable": "not_applicable",
            "verification_calls": 2,
        }
    )
    hidden_fragment["payload"]["verification_outcomes"][0]["outcome_digest"] = _digest(
        hidden_outcome
    )
    _rehash_axis(hidden_dissent, contract, "FA")
    errors = governance.validate_closure(hidden_dissent)
    assert any("dissent disagrees with typed verifier votes" in error for error in errors)
    assert any("aggregate state disagrees with typed verifier votes" in error for error in errors)


def _structural_debt(axis: str, finding: dict) -> dict:
    required = ("title", "assertion", "evidence", "file", "symbol_anchor")
    missing = [field for field in required if not str(finding.get(field) or "").strip()]
    return {
        "kind": "claim",
        "id": "invalid:" + _digest({"axis": axis, "finding": finding}),
        "owner": axis,
        "reason": "missing deterministic evidence fields: " + ",".join(missing),
    }


def _debt_projection(debt: dict) -> str:
    canonical = {
        "id": debt.get("id"),
        "kind": debt.get("kind"),
        "owner": debt.get("owner"),
        "reason": debt.get("reason"),
    }
    return "full_audit_debt:" + json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def test_full_audit_structural_debt_is_stable_and_losslessly_bound() -> None:
    governance, contract, packet = _clean_packet()
    fragment = _axis(packet, "FA")
    malformed = {
        "title": "low malformed finding",
        "assertion": "present assertion",
        "severity": "LOW",
        "classification": "FACT",
        "confidence": "high",
        "evidence": "",
        "impact": "minor",
        "file": "",
        "defect_type": ["other"],
        "symbol_anchor": "",
    }
    fragment["payload"]["audit"].update(
        {"verdict": "FINDINGS", "findings": [malformed]}
    )
    fragment.update({"work_status": "DONE_WITH_CONCERNS", "classification": "INFERENCE"})
    _rehash_axis(packet, contract, "FA")
    assert any(
        "structurally invalid finding lacks canonical coverage debt" in error
        for error in governance.validate_closure(packet)
    )

    acknowledged = deepcopy(packet)
    debt = _structural_debt("FA", malformed)
    projection = _debt_projection(debt)
    axis_fragment = _axis(acknowledged, "FA")
    axis_fragment["payload"]["coverage_debt_count"] = 1
    axis_fragment["gate_verdict"] = "UNVERIFIED"
    axis_fragment["concerns"] = [projection]
    controller = _controller(acknowledged, contract)
    controller["payload"].update(
        {
            "coverage_debt": [debt],
            "pass_eligible": False,
            "unverified_projection": [projection],
        }
    )
    controller.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "UNVERIFIED",
            "classification": "INFERENCE",
            "concerns": [projection],
        }
    )
    acknowledged.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "UNVERIFIED",
            "unverified": [projection],
        }
    )
    _rehash_axis(acknowledged, contract, "FA")
    assert governance.validate_closure(acknowledged) == []


def test_unrelated_debt_cannot_hide_an_unverified_decision_finding() -> None:
    governance, contract, packet = _clean_packet()
    fragment = _axis(packet, "FA")
    fragment["payload"]["audit"].update(
        {"verdict": "FINDINGS", "findings": [_raw_high_finding()]}
    )
    unrelated = {
        "kind": "claim",
        "id": "unrelated-claim",
        "owner": "CC",
        "claim_key": "unrelated::claim::key",
        "reason": "unrelated verification debt",
    }
    controller = _controller(packet, contract)
    controller["payload"]["coverage_debt"] = [unrelated]
    _rehash_axis(packet, contract, "FA")
    assert any(
        "full audit axis FA decision finding lacks outcome or exact claim debt" in error
        for error in governance.validate_closure(packet)
    )


def _adaptive_packet(
    governance: object,
    packet: dict,
    contract: dict,
    *,
    scope: str,
    expiry: str | None,
) -> dict:
    variant = deepcopy(packet)
    adjudicated = datetime.fromisoformat(
        packet["adjudicated_at"].replace("Z", "+00:00")
    )
    axes = contract["axes"]
    selected_set = {"CC", "FA", "AI-E"}
    selected_set.add(next(axis for axis in axes if axis not in selected_set))
    selected = [axis for axis in axes if axis in selected_set]
    bindings = [
        {
            "node_id": f"audit:{axis}",
            "role": axis,
            **governance.native_agent_binding(axis, "verification"),
            "node_class": "verification",
            "reason": "full audit admitted axis",
        }
        for axis in selected
    ]
    controller = _controller(variant, contract)
    approval_value = {"approved": True}
    approval_digest = _digest(approval_value)
    facts = deepcopy(variant["dispatch"]["task_facts"])
    facts["claim_inputs"] = {
        **facts.get("claim_inputs", {}),
        "adaptive_recall_approval": approval_digest,
    }
    route = governance.route_task(facts)
    context_plan = governance.compile_context("PM", route["task_facts"])
    context_artifact = governance.materialize_context_artifact(context_plan)
    source_by_name = {
        item["source"]: item for item in context_plan["sources"]
        if isinstance(item, dict) and isinstance(item.get("source"), str)
    }
    latest_source_observed = max(
        datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
        for item in source_by_name.values()
        if item.get("observed_at")
    )
    prior_adjudicated = datetime.fromisoformat(
        variant["adjudicated_at"].replace("Z", "+00:00")
    )
    variant["adjudicated_at"] = _z(max(
        prior_adjudicated,
        latest_source_observed + timedelta(microseconds=1),
    ))
    variant["dispatch"].update(
        task_facts=route["task_facts"],
        context_artifact=context_artifact,
        dag_digest=route["dag_digest"],
        required_role_nodes=route["required_role_nodes"],
    )
    rebound_authority = []
    for prior in variant["authority_refs"]:
        source = source_by_name.get(prior.get("source"))
        if prior.get("class") in {
            "normative_policy", "implementation_contract", "active_work_state",
        } and source is not None:
            rebound_authority.append(governance.build_authority_claim(
                authority_class=prior["class"], subject=prior["subject"],
                value=source["content"], source=source["source"],
                source_ref=f"context:{source['source']}",
                source_digest=source["content_digest"],
                observed_at=source["observed_at"], scope=prior["scope"],
                strength="direct", expiry=prior.get("expiry"),
            ))
        else:
            rebound_authority.append(prior)
    variant["authority_refs"] = rebound_authority
    controller["payload"].update(
        {
            "scheduler": "adaptive",
            "adaptive_recall_approved": True,
            "adaptive_recall_authority_digest": approval_digest,
            "expected_axes": selected,
            "admitted_axes": selected,
            "deferred_axes": [],
            "axis_bindings": bindings,
            "axis_fragment_digests": {
                node_id: digest
                for node_id, digest in controller["payload"]["axis_fragment_digests"].items()
                if node_id.removeprefix("audit:") in selected_set
            },
        }
    )
    variant["dispatch"]["admitted_role_nodes"] = [
        {
            **binding, "requires": [], "path_scope": [],
            "result_binding": "role_fragment",
        }
        for binding in bindings
    ]
    variant["role_fragments"] = [
        fragment
        for fragment in variant["role_fragments"]
        if not fragment["node_id"].startswith("audit:")
        or fragment["role"] in selected_set
    ]
    variant["skipped_roles"] = [
        item for item in route["skipped"] if item["role"] not in selected_set
    ]
    authority = governance.build_authority_claim(
        authority_class="claim_evidence",
        subject="adaptive_full_audit_recall",
        value=approval_value,
        source="full_audit_adaptive_recall_v1",
        source_ref="task_contract:claim_inputs:adaptive_recall_approval",
        source_digest=approval_digest,
        observed_at=variant["adjudicated_at"],
        scope=scope,
        strength="derived",
        expiry=expiry,
    )
    variant["authority_refs"].append(authority)
    _refresh_full_lineage(governance, variant, contract)
    return variant


def test_adaptive_recall_authority_requires_exact_scope_and_live_expiry() -> None:
    governance, contract, packet = _clean_packet()
    adjudicated = datetime.fromisoformat(
        packet["adjudicated_at"].replace("Z", "+00:00")
    )
    live_expiry = _z(adjudicated + timedelta(minutes=30))

    wrong_scope = _adaptive_packet(
        governance,
        packet,
        contract,
        scope="unrelated:scope",
        expiry=live_expiry,
    )
    assert "adaptive full audit recall authority scope is invalid" in governance.validate_closure(
        wrong_scope
    )

    missing_expiry = _adaptive_packet(
        governance,
        packet,
        contract,
        scope="full_audit:adaptive_recall",
        expiry=None,
    )
    assert "adaptive full audit recall authority requires expiry" in governance.validate_closure(
        missing_expiry
    )

    valid = _adaptive_packet(
        governance,
        packet,
        contract,
        scope="full_audit:adaptive_recall",
        expiry=live_expiry,
    )
    assert governance.validate_closure(
        valid, execution_attestation_verifier=_host_execution_verifier(valid)
    ) == []

    denied = deepcopy(valid)
    approval = next(
        ref
        for ref in denied["authority_refs"]
        if ref["subject"] == "adaptive_full_audit_recall"
    )
    approval["value"] = {"approved": False}
    approval["claim_digest"] = governance.authority_claim_digest(approval)
    assert "adaptive full audit recall authority does not approve recall" in (
        governance.validate_closure(denied)
    )


def test_adaptive_full_audit_inherits_mandatory_axes_from_canonical_route() -> None:
    governance, contract, packet = _clean_packet()
    adjudicated = datetime.fromisoformat(
        packet["adjudicated_at"].replace("Z", "+00:00")
    )
    variant = _adaptive_packet(
        governance,
        packet,
        contract,
        scope="full_audit:adaptive_recall",
        expiry=_z(adjudicated + timedelta(minutes=30)),
    )
    facts = deepcopy(variant["dispatch"]["task_facts"])
    facts["surfaces"] = sorted({*facts["surfaces"], "profitability"})
    route = governance.route_task(facts)
    context_plan = governance.compile_context("PM", route["task_facts"])
    variant["dispatch"].update(
        task_facts=route["task_facts"],
        context_artifact=governance.materialize_context_artifact(context_plan),
        dag_digest=route["dag_digest"],
        required_role_nodes=route["required_role_nodes"],
    )
    selected = set(_controller(variant, contract)["payload"]["admitted_axes"])
    _controller(variant, contract)["payload"]["selection_surfaces"] = facts["surfaces"]
    variant["skipped_roles"] = [
        item for item in route["skipped"] if item["role"] not in selected
    ]

    errors = governance.validate_closure(variant)

    assert "adaptive full audit expected_axes do not match deterministic selection" in errors


def test_full_audit_rejects_a_locally_reissued_budget_authority() -> None:
    governance, contract, packet = _clean_packet()
    context = packet["dispatch"]["context_artifact"]
    authority = json.loads(context["budget_authority_canonical"])
    authority["max_unique_nodes"] -= 1
    authority["max_call_attempts"] = authority["max_unique_nodes"] + authority["retry_budget"]
    forged_canonical = _canonical(authority)
    forged_digest = _digest(authority)
    wave_evidence = next(
        item for item in packet["evidence"] if item["kind"] == "workflow_wave_record_v1"
    )
    wave = wave_evidence["artifact"]
    wave["budget_authority"] = {
        "authority_digest": forged_digest,
        "authority_canonical": forged_canonical,
        "admitted_caps": _admitted_caps(authority),
    }
    wave["record_digest"] = _digest(
        {key: value for key, value in wave.items() if key != "record_digest"}
    )
    wave_evidence["digest"] = wave["record_digest"]
    controller = _controller(packet, contract)
    controller["payload"]["workflow_wave_record_digest"] = wave["record_digest"]
    controller["producer_call_ref"] = wave["record_digest"]
    controller["producer_call_receipt_digest"] = wave["record_digest"]

    errors = governance.validate_closure(packet)
    assert any(
        "workflow wave budget authority canonical bytes differ from admitted Context"
        in error for error in errors
    )


def test_full_audit_does_not_relax_normal_required_fragment_lineage() -> None:
    governance, _, packet = _clean_packet()
    fragment = next(
        item for item in packet["role_fragments"] if item["node_id"] == "pa_design"
    )
    fragment["summary"] = "substituted after the PA call"
    fragment["payload"] = {"unrelated": True}

    errors = governance.validate_closure(packet)

    assert any(
        "projection differs from producer call result" in error for error in errors
    )


def test_saved_workflow_binds_e2_and_never_regresses_unintegrated_fix_candidates() -> None:
    source = (ROOT / ".claude/workflows/openclaw-full-audit.js").read_text(
        encoding="utf-8"
    )
    axis_literal = re.search(r"const ALL_AXES = \[(.*?)\]", source)
    assert axis_literal and "'E2'" in axis_literal.group(1)
    assert "E2: 'review_fragment_v1'" in source
    assert "classification: gateVerdict === 'PASS' ? 'FACT'" in source

    for field in (
        "worktree_id",
        "base_head",
        "candidate_head",
        "patch_digest",
        "diff_digest",
        "review_evidence_digest",
    ):
        assert field in source
    assert "CANDIDATE_READY" in source
    assert "CANDIDATE_REVIEWED_NOT_INTEGRATED" in source
    assert "reviewMatchesCandidate" in source
    assert "integration_status: 'NOT_INTEGRATED'" in source
    assert "integration_status === 'APPLIED_VERIFIED'" in source
    assert ".fix.status === 'FIXED'" not in source
    regression_guard = source.index("if (integratedFixes.length)")
    regression_call = source.index("label: 'audit-regression'")
    assert regression_guard < regression_call


def _full_audit_workflow_context() -> tuple[object, dict, dict, list[str]]:
    governance = _load_governance()
    source_baseline = governance.capture_repository_baseline()
    task_prompt = "audit the admitted Full Audit workflow without widening authority"
    routed = governance.route_task(
        {
            "task_shape": "audit",
            "surfaces": ["agent_workflow", "full_audit", "profitability"],
            "risk": "high",
            "uncertainty": "high",
            "side_effect_class": "none",
            "task_prompt": task_prompt,
            "objective": task_prompt,
            "scope": [
                ".claude/workflows/openclaw-full-audit.js",
                "tests/structure/test_agent_governance_full_audit_adversarial.py",
            ],
            "acceptance_criteria": [
                "reject forged Context authority before any agent call"
            ],
            "hard_stops": [
                "no agent call before Context admission",
                "no runtime, external, or broker effect",
            ],
            "baseline": source_baseline,
            "direct_interfaces": ["context_artifact_v1", "full_audit_v3"],
            "previous_failure": "self-signed budget authority reached agent calls",
        }
    )
    plan = governance.compile_context("PM", routed["task_facts"])
    assert plan["budget"]["pass_allowed"] is True
    artifact = governance.materialize_context_artifact(plan)
    baseline = {
        **source_baseline,
        "runtime_head": None,
        "runtime_observed_at": None,
    }
    route_roles = list(
        dict.fromkeys(item["role"] for item in routed["required_role_nodes"])
    )
    return governance, artifact, baseline, route_roles


def test_full_audit_rejects_malformed_or_self_signed_context_before_agent_calls() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    forged_authority = {
        "schema_version": "context_budget_authority_v1",
        "envelope": "full_audit",
        "accounting_basis": "utf8_bytes_div4_planned_lower_bound_v1",
        "max_context_tokens_per_call": 999_999,
        "max_prompt_utf8_bytes_per_call": 3_999_992,
        "max_workflow_planned_input_tokens": 1_097_998_902,
        "max_unique_nodes": 999,
        "max_call_attempts": 1_098,
        "retry_budget": 99,
    }
    forged = deepcopy(artifact)
    forged_plan = json.loads(forged["canonical_plan"])
    forged_plan["budget"]["authority"] = forged_authority
    forged_plan["budget"]["authority_canonical"] = _canonical(forged_authority)
    forged_plan["budget"]["authority_digest"] = _digest(forged_authority)
    forged["canonical_plan"] = _canonical(forged_plan)
    forged["artifact_digest"] = "sha256:" + hashlib.sha256(
        forged["canonical_plan"].encode("utf-8")
    ).hexdigest()
    forged["budget_authority_canonical"] = _canonical(forged_authority)
    forged["budget_authority_digest"] = _digest(forged_authority)

    cases = [
        ({"schema_version": "context_artifact_v1"}, json.loads(artifact["budget_authority_canonical"])),
        (forged, forged_authority),
    ]
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
let calls = 0;
const agent = async (_prompt, options) => {
  calls += 1;
  if (options.label === 'seam-critic') return { reprobes: [] };
  return {
    schema_version: 'audit_fragment_v2', verdict: 'PASS', confidence: 'high',
    findings: [], assumptions: [],
    consumption: { measurement_status: 'unavailable', unavailable_reason: 'harness' },
  };
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
const pipeline = async () => [];
(async () => {
  try {
    await runner(__ARGS__, () => {}, () => {}, parallel, pipeline, agent);
    console.log(JSON.stringify({ ok: true, calls }));
  } catch (error) {
    console.log(JSON.stringify({ ok: false, calls, error: String(error.message || error) }));
  }
})().catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__",
        json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    )
    for context_artifact, authority in cases:
        run_args = {
            "context_artifact": context_artifact,
            "task_contract_digest": artifact["task_contract_digest"],
            "context_artifact_digest": context_artifact.get(
                "artifact_digest", artifact["artifact_digest"]
            ),
            "dirty_scope": json.loads(artifact["canonical_plan"])["task_contract"][
                "dirty_scope"
            ],
            "baseline": baseline,
            "route_required_roles": route_roles,
            "budget_authority_canonical": _canonical(authority),
            "budget_authority_digest": _digest(authority),
        }
        completed = subprocess.run(
            ["node", "-e", script.replace("__ARGS__", NODE_STDIN_ARGS)],
            cwd=ROOT,
            input=json.dumps(run_args),
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        outcome = json.loads(completed.stdout)
        assert outcome["ok"] is False, outcome
        assert outcome["calls"] == 0, outcome


def test_full_audit_workflow_preserves_null_retry_and_valid_call_lineage() -> None:
    import subprocess

    _governance, context_artifact, baseline, route_roles = (
        _full_audit_workflow_context()
    )
    budget_authority = json.loads(context_artifact["budget_authority_canonical"])
    budget_authority_canonical = context_artifact["budget_authority_canonical"]
    run_args = {
        "context_artifact": context_artifact,
        "baseline": baseline,
        "route_required_roles": route_roles,
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
const agent = async (_prompt, options) => {
  if (options.label === 'audit:CC') return null;
  if (options.label === 'seam-critic') return { reprobes: [] };
  if (options.label.startsWith('audit')) return {
    schema_version: 'audit_fragment_v2', verdict: 'PASS', confidence: 'high',
    findings: [], assumptions: [],
    consumption: { measurement_status: 'unavailable', unavailable_reason: 'harness' },
  };
  throw new Error(`unexpected call ${options.label}`);
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
const pipeline = async () => [];
(async () => console.log(JSON.stringify(await runner(__ARGS__, () => {}, () => {}, parallel, pipeline, agent))))()
  .catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__",
        json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, input=json.dumps(run_args), text=True,
        capture_output=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    governance = _load_governance()
    manifest = result["call_manifest"]
    wave = result["workflow_wave_record"]
    assert governance.validate_workflow_call_manifest(
        manifest,
        expected_task_contract_digest=context_artifact["task_contract_digest"],
        expected_context_artifact_digest=context_artifact["artifact_digest"],
    ) == []
    assert governance.validate_workflow_wave_record(
        wave,
        manifest,
        expected_task_contract_digest=context_artifact["task_contract_digest"],
        expected_context_artifact_digest=context_artifact["artifact_digest"],
    ) == []
    cc_calls = [record for record in manifest["records"] if record["node_id"] == "audit:CC"]
    assert [record["returned_null"] for record in cc_calls] == [True, False]
    assert cc_calls[1]["retry_parent_call_id"] == cc_calls[0]["logical_call_id"]
    assert wave["null_call_count"] == 1
    assert wave["retry_call_count"] == 1
    assert wave["final_null_node_count"] == 0
    assert wave["coverage_debt"] == []
    assert wave["budget_authority"] == {
        "authority_digest": context_artifact["budget_authority_digest"],
        "authority_canonical": budget_authority_canonical,
        "admitted_caps": {
            "max_context_tokens_per_call": budget_authority["max_context_tokens_per_call"],
            "max_prompt_utf8_bytes_per_call": budget_authority["max_prompt_utf8_bytes_per_call"],
            "max_workflow_planned_input_tokens": budget_authority["max_workflow_planned_input_tokens"],
            "max_unique_nodes": budget_authority["max_unique_nodes"],
            "max_call_attempts": budget_authority["max_call_attempts"],
            "retry_budget": budget_authority["retry_budget"],
        },
    }
    assert {"CC", "FA", "AI-E", "QC"}.issubset(
        result["shadow_selected_axes"]
    )
    assert all(
        fragment["consumption"]["measurement_status"] == "unavailable"
        for fragment in result["role_fragments"]
    )


def test_full_audit_rejects_legacy_continuation_before_any_agent_call() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    args = {
        "context_artifact": artifact, "baseline": baseline,
        "route_required_roles": route_roles, "continuation": {},
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
let calls = 0;
const agent = async () => { calls += 1; return null; };
(async () => {
  try { await runner(__ARGS__, () => {}, () => {}, async jobs => Promise.all(jobs.map(job => job())), async () => [], agent); }
  catch (error) { console.log(JSON.stringify({calls, error: String(error.message || error)})); return; }
  console.log(JSON.stringify({calls, error: null}));
})().catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, input=json.dumps(args), text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)
    assert outcome["calls"] == 0
    assert "new task with a newly admitted Context" in outcome["error"]
    source = (ROOT / ".claude/workflows/openclaw-full-audit.js").read_text()
    assert "continuation_execution_verifier" not in source
    assert "full_audit_continuation_v1" not in source


def test_full_audit_no_findings_is_lazy_fourteen_call_backstop() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    args = {
        "context_artifact": artifact, "baseline": baseline,
        "route_required_roles": route_roles,
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
let calls = 0;
const agent = async (_prompt, options) => {
  calls += 1;
  if (options.label === 'seam-critic') return {reprobes: []};
  if (options.label.startsWith('audit')) return {
    schema_version: 'audit_fragment_v2', verdict: 'PASS', confidence: 'high',
    findings: [], assumptions: [],
    consumption: {measurement_status: 'unavailable', unavailable_reason: 'harness'},
  };
  throw new Error(`unexpected call ${options.label}`);
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
(async () => {
  const result = await runner(__ARGS__, () => {}, () => {}, parallel, async () => [], agent);
  console.log(JSON.stringify({calls, result}));
})()
  .catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, input=json.dumps(args), text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)
    assert outcome["calls"] == 14  # 13 axes + one seam; no verifier/fix call.
    assert outcome["result"]["pass_eligible"] is True
    assert outcome["result"]["split_recommendation"] is None


def test_full_audit_44_node_ceiling_covers_thirteen_two_view_claims() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    args = {
        "context_artifact": artifact, "baseline": baseline,
        "route_required_roles": route_roles,
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
const consumption = {measurement_status: 'unavailable', unavailable_reason: 'harness'};
const agent = async (_prompt, options) => {
  if (options.label === 'seam-critic') return {reprobes: []};
  if (options.label.startsWith('audit')) {
    const axis = options.label.split(':').at(-1);
    return {schema_version: 'audit_fragment_v2', verdict: 'FINDINGS', confidence: 'high', findings: [{
      title: `${axis} claim`, assertion: `${axis} assertion`, severity: 'HIGH',
      classification: 'FACT', confidence: 'high', evidence: `${axis} evidence`,
      impact: 'material', file: `src/${axis}.py`, defect_type: ['other'],
      symbol_anchor: `${axis}.fn`, fix_hint: 'fix',
    }], assumptions: [], consumption};
  }
  if (options.label.startsWith('verify-')) return {
    refuted: true, confidence: 'high', reason: 'independently refuted', evidence: 'bound evidence',
  };
  throw new Error(`unexpected call ${options.label}`);
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
(async () => console.log(JSON.stringify(await runner(__ARGS__, () => {}, () => {}, parallel, async () => [], agent))))()
  .catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, input=json.dumps(args), text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["totals"]["distinct_decision_claims"] == 13
    assert result["totals"]["deferred_claims"] == 0
    assert result["totals"]["refuted"] == 13
    assert result["coverage_debt"] == []
    assert result["split_recommendation"] is None
    assert result["pass_eligible"] is True
    assert result["envelope"]["max_unique_nodes"] == 44
    assert result["envelope"]["max_call_attempts"] == 46
    assert result["envelope"]["max_workflow_planned_input_tokens"] == 4_416_000


def test_full_audit_overflow_emits_exact_cold_restart_recommendation() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    args = {
        "context_artifact": artifact, "baseline": baseline,
        "route_required_roles": route_roles,
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
const consumption = {measurement_status: 'unavailable', unavailable_reason: 'harness'};
const agent = async (_prompt, options) => {
  if (options.label === 'seam-critic') return {reprobes: []};
  if (options.label.startsWith('audit')) {
    const axis = options.label.split(':').at(-1);
    return {schema_version: 'audit_fragment_v2', verdict: 'FINDINGS', confidence: 'high',
      findings: [1, 2].map(index => ({
        title: `${axis} claim ${index}`, assertion: `${axis} assertion ${index}`,
        severity: 'HIGH', classification: 'FACT', confidence: 'high',
        evidence: `${axis} evidence ${index}`, impact: 'material',
        file: `src/${axis}.py`, defect_type: ['other'],
        symbol_anchor: `${axis}.fn${index}`, fix_hint: 'fix',
      })), assumptions: [], consumption};
  }
  if (options.label.startsWith('verify-')) return {
    refuted: true, confidence: 'high', reason: 'independently refuted', evidence: 'bound evidence',
  };
  throw new Error(`unexpected call ${options.label}`);
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
(async () => console.log(JSON.stringify(await runner(__ARGS__, () => {}, () => {}, parallel, async () => [], agent))))()
  .catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, input=json.dumps(args), text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    recommendation = result["split_recommendation"]
    deferred = [
        item for item in result["coverage_debt"]
        if item["kind"] == "claim" and "verification admission" in item["reason"]
    ]
    assert result["totals"]["deferred_claims"] == len(deferred) > 0
    assert result["pass_eligible"] is False
    assert recommendation["disposition"] == "NEW_TASK_COLD_RESTART_REQUIRED"
    assert recommendation["coverage_debt_digest"] == _digest(result["coverage_debt"])
    assert recommendation["unresolved_claim_ids"] == sorted(item["id"] for item in deferred)
    immutable_keys = {
        "::".join((
            finding["file"].lower(), finding["symbol_anchor"].lower(),
            finding["assertion"].lower(), finding["evidence"].lower(),
        ))
        for fragment in result["role_fragments"]
        if fragment["node_id"].startswith("audit:")
        for finding in fragment["payload"]["audit"]["findings"]
    }
    assert all(item["claim_key"] in immutable_keys for item in deferred)
