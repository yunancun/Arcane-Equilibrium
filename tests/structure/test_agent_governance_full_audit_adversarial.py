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
    "max_followup_attempts", "max_total_model_turns", "max_wait_cycles",
    "max_no_delta_wakeups", "max_wall_clock_ms", "max_call_duration_ms",
    "max_wave_duration_ms", "max_concurrent_calls",
    "max_spawn_depth_from_root",
)
NODE_STDIN_ARGS = "JSON.parse(fs.readFileSync(0, 'utf8'))"


def _load_governance():
    spec = importlib.util.spec_from_file_location("agent_governance", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_support():
    spec = importlib.util.spec_from_file_location("full_audit_attestation_support", SUPPORT_PATH)
    assert spec is not None and spec.loader is not None
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    return support


def _host_execution_verifier(packet: dict):
    support = _load_support()
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


def _refresh_full_lineage(
    governance: object,
    packet: dict,
    contract: dict,
    *,
    recompile_context: bool = True,
) -> None:
    task = packet["dispatch"]["task_facts"]
    dirty_scope = task["dirty_scope"]
    focus = task.get("focus", "")
    controller = _controller(packet, contract)
    registry = governance.load_registry()
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
    dag_nodes, projection_errors = governance.task_execution_projection(
        packet["dispatch"]["required_role_nodes"],
        packet["dispatch"]["admitted_role_nodes"],
        task_facts=task,
    )
    assert projection_errors == [], projection_errors
    if recompile_context:
        context_plan = governance.compile_context(
            "PM",
            task,
            execution_dag=dag_nodes,
        )
        context = governance.materialize_context_artifact(context_plan)
        packet["dispatch"]["context_artifact"] = context
    else:
        context = packet["dispatch"]["context_artifact"]
        context_plan = json.loads(context["canonical_plan"])
    observed = _load_support()._bind_fixture_evaluation_clock(packet, context_plan)
    source_by_name = {
        source["source"]: source
        for source in context_plan["sources"]
        if isinstance(source, dict) and isinstance(source.get("source"), str)
    }
    packet["authority_refs"] = [
        governance.build_authority_claim(
            authority_class=claim["class"],
            subject=claim["subject"],
            value=source_by_name[claim["source"]]["content"],
            source=claim["source"],
            source_ref=f"context:{claim['source']}",
            source_digest=source_by_name[claim["source"]]["content_digest"],
            observed_at=source_by_name[claim["source"]]["observed_at"],
            scope=claim["scope"],
            strength="direct",
            expiry=claim.get("expiry"),
        )
        if (
            isinstance(claim, dict)
            and claim.get("class") in {
                "normative_policy", "implementation_contract", "active_work_state",
            }
            and claim.get("source_ref") == f"context:{claim.get('source')}"
            and claim.get("source") in source_by_name
        )
        else claim
        for claim in packet["authority_refs"]
    ]
    task_digest = context["task_contract_digest"]
    context_digest = context["artifact_digest"]
    workflow_digest = _digest(
        {"workflow": "full-audit-fixture", "context": context_digest}
    )
    calls = []
    results = {}
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
                **governance.requested_execution_binding(governance.load_registry()),
                "model": governance.load_registry()["saved_workflow_model_policy"]["role_models"][role],
                "effort": governance.load_registry()["saved_workflow_model_policy"]["role_efforts"][role],
                "isolation": None,
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
        "scheduler": "full",
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
    controller_requirement = next(
        requirement
        for requirement in route["required_role_nodes"]
        if requirement["node_id"] == contract["controller_node_id"]
    )
    packet["role_fragments"].append(
        _role_fragment(
            registry,
            controller_requirement["node_id"],
            controller_requirement["role"],
            deepcopy(controller_payload),
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


def _finding_claim_key(finding: dict) -> str:
    return "::".join(
        str(finding[field]).strip().lower()
        for field in ("file", "symbol_anchor", "assertion", "evidence")
    )


def _staged_claim_debt(claim_id: str, members: list[tuple[str, dict]]) -> dict:
    claim_key = _finding_claim_key(members[0][1])
    bound_axes = sorted({axis for axis, _finding in members})
    return {
        "kind": "staged_claim_verification",
        "id": claim_id,
        "owner": bound_axes[0],
        "claim_key": claim_key,
        "remediation_id": "MAE-005",
        "verification_state": "REQUIRES_HOST_CAPABILITY_PHASE",
        "bound_axes": bound_axes,
        "reason": (
            "dynamic claim verification requires a separately admitted "
            "host-capability verification phase"
        ),
    }


def _packet_with_staged_claim(
    members: list[tuple[str, dict]],
) -> tuple[object, dict, dict, dict]:
    governance, contract, packet = _clean_packet()
    for axis, raw in members:
        fragment = _axis(packet, axis)
        fragment["payload"]["audit"].update(
            {"verdict": "FINDINGS", "findings": [raw]}
        )
    debt = _staged_claim_debt("claim-0001", members)
    projection = _debt_projection(debt)
    for axis, _raw in members:
        fragment = _axis(packet, axis)
        fragment["payload"].update(
            {
                "confirmed_decision_claim_ids": [],
                "disputed_claim_ids": [],
                "verification_outcomes": [],
                "coverage_debt_count": 1,
            }
        )
        fragment.update(
            {
                "work_status": "DONE_WITH_CONCERNS",
                "gate_verdict": "UNVERIFIED",
                "classification": "INFERENCE",
                "concerns": [projection],
            }
        )
    controller = _controller(packet, contract)
    controller["payload"].update(
        {
            "coverage_debt": [debt],
            "disputed_count": 0,
            "decision_changing_findings": 0,
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
    packet.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "UNVERIFIED",
            "unverified": [projection],
        }
    )
    _rehash_axis(packet, contract, "FA")
    return governance, contract, packet, debt


def test_full_audit_refresh_rebinds_delayed_context_generation_clock() -> None:
    governance, contract, packet = _clean_packet()
    packet["adjudicated_at"] = "2000-01-01T00:00:00Z"

    _refresh_full_lineage(governance, packet, contract)

    plan = json.loads(packet["dispatch"]["context_artifact"]["canonical_plan"])
    source_observed = [
        datetime.fromisoformat(source["observed_at"].replace("Z", "+00:00"))
        for source in plan["sources"]
        if source.get("observed_at")
    ]
    source_expiry = [
        datetime.fromisoformat(source["expires_at"].replace("Z", "+00:00"))
        for source in plan["sources"]
        if source.get("expires_at")
    ]
    adjudicated = datetime.fromisoformat(
        packet["adjudicated_at"].replace("Z", "+00:00")
    )
    call_manifest = next(
        evidence["artifact"]
        for evidence in packet["evidence"]
        if evidence["kind"] == "workflow_call_manifest_v1"
    )

    assert max(source_observed) < adjudicated < min(source_expiry)
    assert all(
        call["started_at"] == packet["adjudicated_at"]
        and call["ended_at"] == packet["adjudicated_at"]
        for call in call_manifest["records"]
    )
    assert governance.validate_closure(
        packet,
        execution_attestation_verifier=_host_execution_verifier(packet),
        trusted_evaluated_at=adjudicated,
    ) == []


def test_full_audit_accepts_exact_mae005_staged_high_claim_without_outcome() -> None:
    governance, _contract, packet, _debt = _packet_with_staged_claim(
        [("FA", _raw_high_finding())]
    )

    assert governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    ) == []


def test_full_audit_stages_critical_and_goal_medium_without_false_verification() -> None:
    for severity, defect_type in (
        ("CRITICAL", ["other"]),
        ("MEDIUM", ["over-gate"]),
    ):
        raw = {**_raw_high_finding(), "severity": severity, "defect_type": defect_type}
        governance, _contract, packet, debt = _packet_with_staged_claim(
            [("FA", raw)]
        )
        fragment = _axis(packet, "FA")
        controller = next(
            item for item in packet["role_fragments"]
            if item["node_id"] == "ai_economics_review"
        )

        assert fragment["payload"]["verification_outcomes"] == []
        assert fragment["payload"]["confirmed_decision_claim_ids"] == []
        assert fragment["payload"]["disputed_claim_ids"] == []
        assert fragment["gate_verdict"] == "UNVERIFIED"
        assert controller["payload"]["coverage_debt"] == [debt]
        assert controller["payload"]["disputed_count"] == 0
        assert controller["payload"]["decision_changing_findings"] == 0
        assert controller["gate_verdict"] == "UNVERIFIED"
        assert governance.validate_closure(
            packet,
            execution_attestation_verifier=_host_execution_verifier(packet),
        ) == []


def test_full_audit_one_staged_claim_exact_covers_two_identical_high_axes() -> None:
    raw = _raw_high_finding()
    governance, _contract, packet, debt = _packet_with_staged_claim(
        [("CC", deepcopy(raw)), ("FA", deepcopy(raw))]
    )

    assert debt["bound_axes"] == ["CC", "FA"]
    assert [
        item for item in _controller(packet, _contract)["payload"]["coverage_debt"]
        if item["kind"] == "staged_claim_verification"
    ] == [debt]
    for axis in debt["bound_axes"]:
        fragment = _axis(packet, axis)
        assert fragment["payload"]["coverage_debt_count"] == 1
        assert fragment["payload"]["verification_outcomes"] == []
        assert fragment["payload"]["confirmed_decision_claim_ids"] == []
        assert fragment["payload"]["disputed_claim_ids"] == []
        assert fragment["gate_verdict"] == "UNVERIFIED"
    assert governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    ) == []


def test_full_audit_rejects_missing_staged_claim_axis_binding() -> None:
    raw = _raw_high_finding()
    governance, contract, packet, debt = _packet_with_staged_claim(
        [("CC", deepcopy(raw)), ("FA", deepcopy(raw))]
    )
    debt["bound_axes"] = ["CC"]
    projection = _debt_projection(debt)
    controller = _controller(packet, contract)
    controller["payload"]["unverified_projection"] = [projection]
    controller["concerns"] = [projection]
    packet["unverified"] = [projection]
    cc_fragment = _axis(packet, "CC")
    cc_fragment["concerns"] = [projection]
    fa_fragment = _axis(packet, "FA")
    fa_fragment["payload"]["coverage_debt_count"] = 0
    fa_fragment.update(
        {
            "work_status": "DONE",
            "gate_verdict": "PASS",
            "classification": "FACT",
            "concerns": [],
        }
    )
    _rehash_axis(packet, contract, "FA")

    errors = governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    )
    assert any(
        "bound_axes do not exact-cover raw findings" in error
        and "missing=['FA']; extra=[]" in error
        for error in errors
    )


def test_full_audit_rejects_forged_staged_claim_axis_binding() -> None:
    raw = _raw_high_finding()
    governance, contract, packet, debt = _packet_with_staged_claim(
        [("CC", deepcopy(raw)), ("FA", deepcopy(raw))]
    )
    debt["bound_axes"] = ["CC", "E2", "FA"]
    projection = _debt_projection(debt)
    controller = _controller(packet, contract)
    controller["payload"]["unverified_projection"] = [projection]
    controller["concerns"] = [projection]
    packet["unverified"] = [projection]
    for axis in debt["bound_axes"]:
        fragment = _axis(packet, axis)
        fragment["payload"]["coverage_debt_count"] = 1
        fragment.update(
            {
                "work_status": "DONE_WITH_CONCERNS",
                "gate_verdict": "UNVERIFIED",
                "classification": "INFERENCE",
                "concerns": [projection],
            }
        )
    _rehash_axis(packet, contract, "E2")

    errors = governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    )
    assert any(
        "bound_axes do not exact-cover raw findings" in error
        and "missing=[]; extra=['E2']" in error
        for error in errors
    )


def test_closure_rejects_sixteen_node_wave_bound_to_fourteen_node_context() -> None:
    governance, contract, packet = _clean_packet()
    task = packet["dispatch"]["task_facts"]
    registry = governance.load_registry()
    task_digest = packet["dispatch"]["context_artifact"]["task_contract_digest"]
    extras = [
        {
            "node_id": "legacy-extra:PA",
            "role": "PA",
            "requires": ["audit:FA"],
        },
        {
            "node_id": "legacy-extra:CC",
            "role": "CC",
            "requires": ["legacy-extra:PA"],
        },
    ]
    for extra in extras:
        packet["dispatch"]["admitted_role_nodes"].append({
            "node_id": extra["node_id"],
            "role": extra["role"],
            **governance.native_agent_binding(extra["role"], "verification"),
            "node_class": "verification",
            "requires": extra["requires"],
            "path_scope": [],
            "reason": "legacy unbound extra call regression fixture",
            "result_binding": "role_fragment",
        })
        packet["role_fragments"].append(
            _role_fragment(
                registry,
                extra["node_id"],
                extra["role"],
                {"node": extra["node_id"]},
                task_digest,
            )
        )
    fixed_plan = governance.compile_context("PM", task)
    assert fixed_plan["execution_dag_binding"]["node_count"] == 14
    packet["dispatch"]["context_artifact"] = (
        governance.materialize_context_artifact(fixed_plan)
    )

    _refresh_full_lineage(
        governance,
        packet,
        contract,
        recompile_context=False,
    )

    wave = next(
        item["artifact"]
        for item in packet["evidence"]
        if item["kind"] == "workflow_wave_record_v1"
    )
    assert len(wave["admitted_tasks"]) == 16
    errors = governance.validate_closure(
        packet,
        execution_attestation_verifier=_host_execution_verifier(packet),
    )
    assert any(
        "admitted task core differs from Context execution DAG binding" in error
        for error in errors
    )
    assert any(
        "dag_digest differs from Context execution DAG binding" in error
        for error in errors
    )


def test_full_audit_closure_rejects_missing_fixed_route_representative() -> None:
    governance, _contract, packet = _clean_packet()
    packet["dispatch"]["admitted_role_nodes"] = [
        node
        for node in packet["dispatch"]["admitted_role_nodes"]
        if node["node_id"] != "audit:CC"
    ]
    packet["role_fragments"] = [
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] != "audit:CC"
    ]

    errors = governance.validate_closure(
        packet,
        execution_attestation_verifier=_host_execution_verifier(packet),
    )

    assert any(
        "specialized full_audit dispatch omits fixed call admission audit:CC"
        in error
        for error in errors
    )


def test_full_audit_rejects_inline_typed_votes_without_host_executor_phase() -> None:
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
    try:
        _rehash_axis(packet, contract, "FA")
    except ValueError as error:
        assert not isinstance(error, governance.SpecializedWorkflowSplitRequired)
        message = str(error)
        assert "adds unrouted call nodes" in message
        assert "verify:claim-high-1:impact" in message
        assert "verify:claim-high-1:source" in message
    else:
        raise AssertionError("inline verifier calls bypassed route authorization")


def test_full_audit_rejects_inline_third_vote_without_host_executor_phase() -> None:
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
    try:
        _rehash_axis(packet, contract, "FA")
    except ValueError as error:
        assert not isinstance(error, governance.SpecializedWorkflowSplitRequired)
        message = str(error)
        assert "adds unrouted call nodes" in message
        assert "verify:claim-high-dissent:impact" in message
        assert "verify:claim-high-dissent:source" in message
        assert "verify:claim-high-dissent:third" in message
    else:
        raise AssertionError("inline third verifier bypassed route authorization")


def test_full_audit_quarantines_malformed_inline_outcomes_and_votes() -> None:
    governance, _contract, base_packet = _clean_packet()
    raw = {
        **_raw_high_finding(),
        "severity": "MEDIUM",
        "defect_type": ["over-gate"],
    }

    def valid_outcome() -> dict:
        return {
            "claim_id": "claim-malformed-inline",
            "claim_key": _finding_claim_key(raw),
            "axis": "FA",
            "severity": raw["severity"],
            "defect_type": list(raw["defect_type"]),
            "assertion": raw["assertion"],
            "evidence": raw["evidence"],
            "file": raw["file"],
            "symbol_anchor": raw["symbol_anchor"],
            "confirmed": True,
            "refuted": False,
            "disputed": False,
            "latent": False,
            "reachable": "not_applicable",
            "verifier_dissent": False,
            "verifier_votes": [
                {
                    "view": view,
                    "refuted": False,
                    "confidence": "high",
                    "reason": f"{view} confirms",
                    "evidence": f"{view}:evidence",
                    "reachable": None,
                    "producer_record_kind": "workflow_call_record_v1",
                    "producer_call_ref": f"call:{view}",
                    "producer_call_receipt_digest": "sha256:" + "a" * 64,
                }
                for view in ("source", "impact")
            ],
            "verification_calls": 2,
        }

    cases = [
        (
            "verification outcome types are invalid",
            lambda outcome: outcome.update({"defect_type": [{}]}),
        ),
        (
            "verification outcome types are invalid",
            lambda outcome: outcome.update({"claim_key": []}),
        ),
        (
            "verification outcome types are invalid",
            lambda outcome: outcome.update({"severity": []}),
        ),
        (
            "verification outcome types are invalid",
            lambda outcome: outcome.update({"reachable": {}}),
        ),
        (
            "verifier vote view is invalid",
            lambda outcome: outcome["verifier_votes"][0].update({"view": []}),
        ),
        (
            "verifier vote evidence is invalid",
            lambda outcome: outcome["verifier_votes"][0].update(
                {"confidence": []}
            ),
        ),
        (
            "third verifier reachability is invalid",
            lambda outcome: outcome["verifier_votes"][0].update(
                {"view": "third", "reachable": {}}
            ),
        ),
        (
            "verifier vote evidence is invalid",
            lambda outcome: outcome["verifier_votes"][0].update(
                {"producer_call_receipt_digest": []}
            ),
        ),
    ]
    for expected_error, mutate in cases:
        packet = deepcopy(base_packet)
        fragment = _axis(packet, "FA")
        fragment["payload"]["audit"].update(
            {"verdict": "FINDINGS", "findings": [deepcopy(raw)]}
        )
        outcome = valid_outcome()
        mutate(outcome)
        fragment["payload"]["verification_outcomes"] = [
            {"outcome": outcome, "outcome_digest": _digest(outcome)}
        ]

        errors = governance.validate_closure(
            packet,
            execution_attestation_verifier=_host_execution_verifier(packet),
        )

        assert any(expected_error in error for error in errors), (
            expected_error,
            errors,
        )


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
    for field in (
        "claim_key", "remediation_id", "verification_state", "bound_axes",
    ):
        if debt.get(field) is not None:
            canonical[field] = debt[field]
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

    missing_field = deepcopy(acknowledged)
    missing_finding = _axis(missing_field, "FA")["payload"]["audit"]["findings"][0]
    missing_finding.pop("evidence")
    forged_debt = _structural_debt("FA", missing_finding)
    forged_projection = _debt_projection(forged_debt)
    missing_axis = _axis(missing_field, "FA")
    missing_axis["concerns"] = [forged_projection]
    missing_controller = _controller(missing_field, contract)
    missing_controller["payload"]["coverage_debt"] = [forged_debt]
    missing_controller["payload"]["unverified_projection"] = [forged_projection]
    missing_controller["concerns"] = [forged_projection]
    missing_field["unverified"] = [forged_projection]
    _rehash_axis(missing_field, contract, "FA")
    missing_errors = governance.validate_closure(missing_field)
    assert any(
        "raw audit violates FINDINGS_SCHEMA" in error
        and "missing required property evidence" in error
        for error in missing_errors
    )
    assert any(
        "structural finding debt is not one-to-one" in error
        for error in missing_errors
    )


def test_full_audit_python_schema_mirror_covers_the_complete_model_result() -> None:
    full_audit = __import__("agent_governance_full_audit")
    valid_finding = {
        **_raw_high_finding(),
        "severity": "LOW",
        "root_anchor": "root",
        "fix_hint": "fix",
    }
    valid = {
        "schema_version": "audit_fragment_v2",
        "verdict": "FINDINGS",
        "confidence": "high",
        "findings": [valid_finding],
        "assumptions": [{"note": "bounded", "why_unproven": "no runtime"}],
        "consumption": {
            "measurement_status": "measured",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "tool_calls": 0,
            "wall_time_ms": 0,
        },
    }
    assert full_audit._raw_audit_schema_violations(valid) == []

    invalid: list[tuple[str, dict]] = []
    for field in (
        "schema_version", "verdict", "confidence", "findings", "assumptions",
        "consumption",
    ):
        invalid.append((
            f"missing top-level {field}",
            {key: value for key, value in valid.items() if key != field},
        ))
    invalid.extend([
        ("top-level extra", {**valid, "undeclared": True}),
        ("bad schema", {**valid, "schema_version": "audit_fragment_v3"}),
        ("bad verdict", {**valid, "verdict": "PWN"}),
        ("bad confidence type", {**valid, "confidence": 7}),
        ("findings type", {**valid, "findings": {}}),
        ("assumptions type", {**valid, "assumptions": 7}),
        (
            "assumption missing",
            {**valid, "assumptions": [{"note": "bounded"}]},
        ),
        (
            "assumption type",
            {
                **valid,
                "assumptions": [{"note": 7, "why_unproven": "no runtime"}],
            },
        ),
        ("assumption item type", {**valid, "assumptions": [7]}),
        (
            "assumption extra",
            {
                **valid,
                "assumptions": [{
                    "note": "bounded", "why_unproven": "no runtime", "extra": 1,
                }],
            },
        ),
        ("consumption type", {**valid, "consumption": []}),
        ("consumption missing status", {**valid, "consumption": {}}),
        (
            "consumption status",
            {**valid, "consumption": {"measurement_status": "bogus"}},
        ),
        (
            "consumption negative",
            {
                **valid,
                "consumption": {
                    "measurement_status": "measured", "input_tokens": -1,
                },
            },
        ),
        (
            "consumption non-integer",
            {
                **valid,
                "consumption": {
                    "measurement_status": "measured", "tool_calls": 1.5,
                },
            },
        ),
        (
            "consumption extra",
            {
                **valid,
                "consumption": {
                    "measurement_status": "unavailable", "extra": 1,
                },
            },
        ),
    ])
    for field in (
        "title", "assertion", "severity", "classification", "confidence",
        "evidence", "impact", "file", "defect_type", "symbol_anchor",
    ):
        missing = deepcopy(valid)
        missing["findings"][0].pop(field)
        invalid.append((f"finding missing {field}", missing))
    for field in (
        "title", "assertion", "severity", "classification", "confidence",
        "evidence", "impact", "file", "symbol_anchor", "root_anchor", "fix_hint",
    ):
        wrong_type = deepcopy(valid)
        wrong_type["findings"][0][field] = 7
        invalid.append((f"finding {field} type", wrong_type))
    for field, value in (
        ("severity", "HIGHER"),
        ("classification", "CERTAIN"),
        ("confidence", "very-high"),
    ):
        wrong_enum = deepcopy(valid)
        wrong_enum["findings"][0][field] = value
        invalid.append((f"finding {field} enum", wrong_enum))
    for label, value in (
        ("scalar string", "other"),
        ("scalar integer", 7),
        ("object", {"type": "other"}),
        ("non-string item", [7]),
        ("object item", [{"type": "other"}]),
        ("unknown enum", ["not-a-defect-type"]),
    ):
        wrong_defect = deepcopy(valid)
        wrong_defect["findings"][0].update(
            {"severity": "MEDIUM", "defect_type": value}
        )
        invalid.append((f"finding defect_type {label}", wrong_defect))
    high_scalar_defect = deepcopy(valid)
    high_scalar_defect["findings"][0].update(
        {"severity": "HIGH", "defect_type": "other"}
    )
    invalid.append(("HIGH finding scalar defect_type", high_scalar_defect))
    for metric in (
        "input_tokens", "output_tokens", "cache_read_tokens", "tool_calls",
        "wall_time_ms",
    ):
        for label, value in (("negative", -1), ("float", 1.5), ("boolean", True)):
            wrong_metric = deepcopy(valid)
            wrong_metric["consumption"][metric] = value
            invalid.append((f"consumption {metric} {label}", wrong_metric))
    wrong_unavailable_reason = deepcopy(valid)
    wrong_unavailable_reason["consumption"]["unavailable_reason"] = 7
    invalid.append(("consumption unavailable_reason type", wrong_unavailable_reason))
    finding_extra = deepcopy(valid)
    finding_extra["findings"][0]["undeclared"] = True
    invalid.append(("finding extra", finding_extra))

    for label, malformed in invalid:
        assert full_audit._raw_audit_schema_violations(malformed), label


def test_full_audit_python_schema_mirror_matches_saved_workflow_source() -> None:
    import subprocess

    workflow = ROOT / ".claude/workflows/openclaw-full-audit.js"
    extractor = r"""
const fs = require('fs')
const vm = require('vm')
const source = fs.readFileSync(process.argv[1], 'utf8')
const defectStart = source.indexOf('const DEFECT_TYPES =')
const defectEnd = source.indexOf('const GOAL_TYPES =', defectStart)
const schemaStart = source.indexOf('const FINDINGS_SCHEMA =', defectEnd)
const schemaEnd = source.indexOf('const SEAM_SCHEMA =', schemaStart)
if ([defectStart, defectEnd, schemaStart, schemaEnd].some(value => value < 0)) {
  throw new Error('saved workflow FINDINGS_SCHEMA markers are missing')
}
const program = [
  source.slice(defectStart, defectEnd),
  source.slice(schemaStart, schemaEnd),
  'JSON.stringify(FINDINGS_SCHEMA)',
].join('\n')
process.stdout.write(vm.runInNewContext(program, Object.create(null)))
"""
    completed = subprocess.run(
        ["node", "-e", extractor, str(workflow)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    saved_schema = json.loads(completed.stdout)
    python_schema = deepcopy(
        __import__("agent_governance_full_audit").RAW_AUDIT_FINDINGS_SCHEMA
    )

    def normalize_schema(value):
        if isinstance(value, dict):
            return {
                key: (
                    sorted(normalize_schema(item) for item in item_value)
                    if key in {"enum", "required"}
                    and isinstance(item_value, list)
                    else normalize_schema(item_value)
                )
                for key, item_value in value.items()
            }
        if isinstance(value, list):
            return [normalize_schema(item) for item in value]
        return value

    assert normalize_schema(python_schema) == normalize_schema(saved_schema)


def test_full_audit_raw_findings_fail_closed_against_declared_schema() -> None:
    valid = {**_raw_high_finding(), "severity": "LOW"}
    governance, contract, packet = _clean_packet()
    fragment = _axis(packet, "FA")
    fragment["payload"]["audit"].update(
        {"verdict": "FINDINGS", "findings": [deepcopy(valid)]}
    )
    _refresh_full_lineage(governance, packet, contract)
    assert governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    ) == []

    valid_audit = deepcopy(fragment["payload"]["audit"])
    invalid_cases = {
        "unknown severity": {
            **valid_audit,
            "findings": [{**valid, "severity": "HIGHER"}],
        },
        "medium scalar defect type": {
            **valid_audit,
            "findings": [{
                **valid, "severity": "MEDIUM", "defect_type": 7,
            }],
        },
        "top-level extra": {**valid_audit, "undeclared": "hidden"},
        "invalid verdict": {**valid_audit, "verdict": "PWN"},
        "assumptions scalar": {**valid_audit, "assumptions": 7},
        "invalid consumption": {
            **valid_audit,
            "consumption": {"measurement_status": "bogus", "extra": 1},
        },
    }
    for label, malformed_audit in invalid_cases.items():
        governance, contract, packet = _clean_packet()
        fragment = _axis(packet, "FA")
        fragment["payload"]["audit"] = {
            "axis": "FA",
            **deepcopy(malformed_audit),
        }
        _refresh_full_lineage(governance, packet, contract)
        errors = governance.validate_closure(
            packet, execution_attestation_verifier=_host_execution_verifier(packet)
        )

        assert any(
            "raw audit violates FINDINGS_SCHEMA" in error
            for error in errors
        ), (label, errors)


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


def test_adaptive_recall_self_digest_cannot_replace_platform_authority() -> None:
    governance, contract, packet = _clean_packet()
    adjudicated = datetime.fromisoformat(
        packet["adjudicated_at"].replace("Z", "+00:00")
    )
    live_expiry = _z(adjudicated + timedelta(minutes=30))

    variants = [
        _adaptive_packet(
            governance,
            packet,
            contract,
            scope="unrelated:scope",
            expiry=live_expiry,
        ),
        _adaptive_packet(
            governance,
            packet,
            contract,
            scope="full_audit:adaptive_recall",
            expiry=None,
        ),
        _adaptive_packet(
            governance,
            packet,
            contract,
            scope="full_audit:adaptive_recall",
            expiry=live_expiry,
        ),
    ]
    for variant in variants:
        errors = governance.validate_closure(
            variant,
            execution_attestation_verifier=_host_execution_verifier(variant),
        )
        assert "EXTERNAL_LIMIT_RECALL_AUTHORITY" in errors
        assert (
            "caller-declared adaptive recall approval cannot authorize "
            "reduced execution"
        ) in errors
        assert (
            "self-digested adaptive recall authority cannot authorize "
            "reduced execution"
        ) in errors
        assert "claim_evidence cannot authorize adaptive full audit recall" in errors


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
        item for item in packet["role_fragments"] if item["node_id"] == "audit:CC"
    )
    fragment["payload"]["audit"]["confidence"] = "low"

    errors = governance.validate_closure(packet)

    assert any(
        "full audit audit:CC producer call/result binding is invalid" in error
        for error in errors
    )


def test_saved_workflow_has_no_unbound_dynamic_verify_or_fix_call_path() -> None:
    source = (ROOT / ".claude/workflows/openclaw-full-audit.js").read_text(
        encoding="utf-8"
    )
    axis_literal = re.search(r"const ALL_AXES = \[(.*?)\]", source)
    assert axis_literal and "'E2'" in axis_literal.group(1)
    assert "E2: 'review_fragment_v1'" in source
    assert "classification: gateVerdict === 'PASS' ? 'FACT'" in source

    for forbidden in (
        "function verificationJob(",
        "label: `verify-",
        "label: `fix:",
        "label: `review:",
        "CANDIDATE_READY",
        "CANDIDATE_REVIEWED_NOT_INTEGRATED",
        "reviewMatchesCandidate",
        "integration_status: 'NOT_INTEGRATED'",
    ):
        assert forbidden not in source
    assert "const admittedClaims = []" in source
    assert (
        "dynamic claim verification requires a separately admitted "
        "host-capability verification phase"
    ) in source
    assert (
        "dynamic fix/review requires a separately admitted "
        "host-capability phase"
    ) in source
    assert "integration_status === 'APPLIED_VERIFIED'" not in source
    assert "if (integratedFixes.length)" not in source
    assert "label: 'audit-regression'" not in source
    assert "const regression = null" in source


def _full_audit_workflow_context(
    *,
    claim_inputs: dict[str, str] | None = None,
) -> tuple[object, dict, dict, list[str]]:
    governance = _load_governance()
    source_baseline = governance.capture_repository_baseline()
    task_prompt = "audit the admitted Full Audit workflow without widening authority"
    task_facts = {
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
    if claim_inputs is not None:
        task_facts["claim_inputs"] = claim_inputs
    routed = governance.route_task(task_facts)
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

    divergent = deepcopy(artifact)
    divergent_plan = json.loads(divergent["canonical_plan"])
    bound_nodes = divergent_plan["execution_dag_binding"]["nodes"]
    divergent_plan["execution_dag_binding"] = __import__(
        "agent_governance_execution_dag"
    ).compile_context_execution_dag_binding(bound_nodes[:1])
    divergent["canonical_plan"] = _canonical(divergent_plan)
    divergent["artifact_digest"] = _digest(divergent_plan)

    def extra(node_id: str) -> dict:
        return {
            "node_id": node_id,
            "role": "E2",
            **_governance.native_agent_binding("E2", "verification"),
            "requires": ["seam:critic"],
            "node_class": "verification",
        }

    def artifact_with_nodes(nodes: list[dict]) -> dict:
        candidate = deepcopy(artifact)
        candidate_plan = json.loads(candidate["canonical_plan"])
        candidate_plan["execution_dag_binding"] = __import__(
            "agent_governance_execution_dag"
        ).compile_context_execution_dag_binding(nodes)
        candidate["canonical_plan"] = _canonical(candidate_plan)
        candidate["artifact_digest"] = _digest(candidate_plan)
        return candidate

    def artifact_with_routed_nodes(
        nodes: list[dict],
        contract_updates: dict | None = None,
    ) -> dict:
        candidate = deepcopy(artifact)
        candidate_plan = json.loads(candidate["canonical_plan"])
        candidate_plan["task_contract"].update(
            contract_updates or {"end_to_end_claim": True}
        )
        candidate_plan["task_contract_digest"] = _digest(
            candidate_plan["task_contract"]
        )
        candidate_plan["execution_dag_binding"] = __import__(
            "agent_governance_execution_dag"
        ).compile_context_execution_dag_binding(nodes)
        candidate.update(
            __import__(
                "agent_governance_context_projection"
            ).materialize_semantic_context(
                candidate_plan,
                _governance.load_registry(),
            )
        )
        candidate["task_contract_digest"] = candidate_plan[
            "task_contract_digest"
        ]
        candidate["canonical_plan"] = _canonical(candidate_plan)
        candidate["artifact_digest"] = _digest(candidate_plan)
        return candidate

    def artifact_with_raw_nodes(nodes: list[dict]) -> dict:
        candidate = deepcopy(artifact)
        candidate_plan = json.loads(candidate["canonical_plan"])
        candidate_plan["execution_dag_binding"] = {
            "schema_version": "context_execution_dag_binding_v1",
            "dag_digest": _governance.execution_dag_digest(nodes),
            "node_count": len(nodes),
            "edge_count": sum(len(node["requires"]) for node in nodes),
            "nodes": nodes,
        }
        candidate["canonical_plan"] = _canonical(candidate_plan)
        candidate["artifact_digest"] = _digest(candidate_plan)
        return candidate

    business_acceptance = {
        "node_id": "business_acceptance",
        "role": "QA",
        "native_agent": "QA",
        "requires": ["audit:CC", "audit:QC"],
        "node_class": "verification",
        "permission": "read_only",
    }
    superset = artifact_with_routed_nodes([
        *bound_nodes, business_acceptance,
    ])
    unrelated_superset = artifact_with_nodes([
        *bound_nodes, extra("extra:unrouted"),
    ])
    forged_fixed_only = artifact_with_routed_nodes(bound_nodes)
    dual_specialized = artifact_with_routed_nodes(
        [*bound_nodes, business_acceptance],
        {
            "end_to_end_claim": False,
            "surfaces": ["full_audit", "profit_diagnosis"],
        },
    )
    effectful_specialized = artifact_with_routed_nodes(
        bound_nodes,
        {
            "runtime_claim": True,
            "side_effect_class": "target_host_probe",
            "surfaces": [
                "agent_workflow", "full_audit", "profitability",
                "runtime_effect",
            ],
        },
    )
    fixed_ids = {node["node_id"] for node in bound_nodes}
    source_split_cases = []
    for source_write_updates in (
        {
            "task_shape": "implementation",
            "side_effect_class": "repo_write",
            "surfaces": ["full_audit", "python"],
        },
        {
            "task_shape": "docs",
            "side_effect_class": "docs_write",
            "surfaces": ["docs", "full_audit"],
        },
        {
            "task_shape": "test",
            "side_effect_class": "local_test",
            "surfaces": ["full_audit", "python"],
        },
    ):
        source_write_contract = deepcopy(
            json.loads(artifact["canonical_plan"])["task_contract"]
        )
        source_write_contract.update(source_write_updates)
        source_write_route = _governance.route_task(source_write_contract)
        source_write_projection, source_write_errors = __import__(
            "agent_governance_execution_dag"
        ).task_execution_projection(
            source_write_route["required_role_nodes"],
            [],
            task_facts=source_write_route["task_facts"],
            registry=_governance.load_registry(),
        )
        assert source_write_errors == []
        source_write_extra_ids = sorted(
            node["node_id"]
            for node in source_write_projection
            if node["node_id"] not in fixed_ids
        )
        assert source_write_extra_ids
        source_split_cases.append((
            artifact_with_routed_nodes(
                source_write_projection,
                source_write_updates,
            ),
            json.loads(artifact["budget_authority_canonical"]),
            "SPECIALIZED_WORKFLOW_SPLIT_REQUIRED",
            source_write_extra_ids,
        ))
    omitted_nodes = [
        deepcopy(node)
        for node in bound_nodes
        if node["node_id"] != "audit:A3"
    ]
    next(
        node for node in omitted_nodes if node["node_id"] == "seam:critic"
    )["requires"].remove("audit:A3")
    mixed_omission = artifact_with_routed_nodes(
        [*omitted_nodes, business_acceptance]
    )
    substituted_nodes = deepcopy(bound_nodes)
    next(
        node for node in substituted_nodes if node["node_id"] == "audit:A3"
    ).update({"role": "E2", "native_agent": "E2"})
    mixed_substitution = artifact_with_routed_nodes(
        [*substituted_nodes, business_acceptance]
    )
    cyclic_extra_a = extra("extra:a")
    cyclic_extra_b = extra("extra:b")
    cyclic_extra_a["requires"] = ["extra:b"]
    cyclic_extra_b["requires"] = ["extra:a"]
    cyclic_superset = artifact_with_raw_nodes(
        [*bound_nodes, cyclic_extra_a, cyclic_extra_b]
    )
    unicode_superset = artifact_with_raw_nodes([
        *bound_nodes,
        extra("\U0001f600"),
        extra("\ue000"),
    ])
    non_string_requires = extra("extra:non-string-requires")
    non_string_requires["requires"] = [1, 2]
    malformed_requires_superset = artifact_with_raw_nodes(
        [*bound_nodes, non_string_requires]
    )

    cases = [
        (
            {"schema_version": "context_artifact_v1"},
            json.loads(artifact["budget_authority_canonical"]),
            None,
            None,
        ),
        (forged, forged_authority, None, None),
        (
            divergent,
            json.loads(artifact["budget_authority_canonical"]),
            None,
            None,
        ),
        (
            superset,
            json.loads(artifact["budget_authority_canonical"]),
            "SPECIALIZED_WORKFLOW_SPLIT_REQUIRED",
            ["business_acceptance"],
        ),
        (
            forged_fixed_only,
            json.loads(artifact["budget_authority_canonical"]),
            "does not authorize the exact task route",
            None,
        ),
        (
            dual_specialized,
            json.loads(artifact["budget_authority_canonical"]),
            "does not authorize the exact task route",
            None,
        ),
        (
            effectful_specialized,
            json.loads(artifact["budget_authority_canonical"]),
            "does not authorize the exact task route",
            None,
        ),
        *source_split_cases,
        (
            unrelated_superset,
            json.loads(artifact["budget_authority_canonical"]),
            "does not authorize the exact task route",
            None,
        ),
        (
            mixed_omission,
            json.loads(artifact["budget_authority_canonical"]),
            "Full Audit Context execution DAG binding",
            None,
        ),
        (
            mixed_substitution,
            json.loads(artifact["budget_authority_canonical"]),
            "Full Audit Context execution DAG binding",
            None,
        ),
        (
            cyclic_superset,
            json.loads(artifact["budget_authority_canonical"]),
            "Full Audit Context execution DAG binding",
            None,
        ),
        (
            unicode_superset,
            json.loads(artifact["budget_authority_canonical"]),
            "Full Audit Context execution DAG binding",
            None,
        ),
        (
            malformed_requires_superset,
            json.loads(artifact["budget_authority_canonical"]),
            "Full Audit Context execution DAG binding",
            None,
        ),
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
    console.log(JSON.stringify({
      ok: false, calls, error: String(error.message || error),
      error_code: error.error_code || null,
      surface: error.surface || null,
      extra_node_ids: error.extra_node_ids || null,
    }));
  }
})().catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__",
        json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    )
    for context_artifact, authority, expected_error, expected_extra_ids in cases:
        case_plan = json.loads(context_artifact.get(
            "canonical_plan", artifact["canonical_plan"]
        ))
        case_baseline = baseline
        if case_plan["task_contract"].get("runtime_claim"):
            case_baseline = {
                **baseline,
                "runtime_head": baseline["source_head"],
                "runtime_observed_at": _z(datetime.now(timezone.utc)),
            }
        run_args = {
            "context_artifact": context_artifact,
            "task_contract_digest": context_artifact.get(
                "task_contract_digest", artifact["task_contract_digest"]
            ),
            "context_artifact_digest": context_artifact.get(
                "artifact_digest", artifact["artifact_digest"]
            ),
            "dirty_scope": json.loads(context_artifact.get(
                "canonical_plan", artifact["canonical_plan"]
            ))["task_contract"][
                "dirty_scope"
            ],
            "baseline": case_baseline,
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
        if expected_error is not None:
            assert expected_error in outcome["error"]
        if expected_extra_ids is None:
            assert outcome["error_code"] is None
            assert outcome["surface"] is None
            assert outcome["extra_node_ids"] is None
        else:
            assert outcome["error_code"] == "SPECIALIZED_WORKFLOW_SPLIT_REQUIRED"
            assert outcome["surface"] == "full_audit"
            assert outcome["extra_node_ids"] == expected_extra_ids
            assert all(node_id in outcome["error"] for node_id in expected_extra_ids)


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
        "admitted_caps": _admitted_caps(budget_authority),
    }
    assert {"CC", "FA", "AI-E", "QC"}.issubset(
        result["shadow_selected_axes"]
    )
    assert all(
        fragment["consumption"]["measurement_status"] == "unavailable"
        for fragment in result["role_fragments"]
    )


def test_full_audit_persistent_null_aborts_before_unbound_seam_call() -> None:
    import subprocess

    _governance, context_artifact, baseline, route_roles = (
        _full_audit_workflow_context()
    )
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
const calls = [];
const agent = async (_prompt, options) => {
  calls.push(options.label);
  if (['audit:CC', 'audit-relay:CC'].includes(options.label)) return null;
  if (options.label === 'seam-critic') return { reprobes: [] };
  if (options.label.startsWith('audit')) return {
    schema_version: 'audit_fragment_v2', verdict: 'PASS', confidence: 'high',
    findings: [], assumptions: [],
    consumption: { measurement_status: 'unavailable', unavailable_reason: 'harness' },
  };
  throw new Error(`unexpected call ${options.label}`);
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
(async () => {
  try {
    await runner(__ARGS__, () => {}, () => {}, parallel, async () => [], agent);
    console.log(JSON.stringify({ calls, error: null }));
  } catch (error) {
    console.log(JSON.stringify({ calls, error: String(error.message || error) }));
  }
})().catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__",
        json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        input=json.dumps(run_args),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)
    assert outcome["error"].startswith("FULL_AUDIT_TERMINAL_NULL_V1:")
    terminal = json.loads(outcome["error"].split(":", 1)[1])
    assert terminal == {
        "disposition": "ABORTED_BEFORE_SEAM",
        "node_ids": ["audit:CC"],
        "reason": (
            "fixed pre-call DAG cannot emit a complete axes+seam wave "
            "after final null"
        ),
        "schema_version": "full_audit_terminal_null_v1",
    }
    assert outcome["calls"].count("audit:CC") == 1
    assert outcome["calls"].count("audit-relay:CC") == 1
    assert "seam-critic" not in outcome["calls"]
    assert len(outcome["calls"]) == 14


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


def test_full_audit_defaults_to_full_and_reduced_mode_is_external_limit() -> None:
    import subprocess

    source = (ROOT / ".claude/workflows/openclaw-full-audit.js").read_text(
        encoding="utf-8"
    )
    assert "const scheduler = config.scheduler || 'full'" in source
    assert "const candidateAxes = requestedAxes" in source
    assert "throw new Error('EXTERNAL_LIMIT_RECALL_AUTHORITY')" in source

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
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
  const pipeline = async () => { throw new Error('saved Full Audit must not invoke dynamic fix/review pipeline'); };
  const result = await runner(__ARGS__, () => {}, () => {}, parallel, pipeline, agent);
  console.log(JSON.stringify({calls, result}));
})()
  .catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)

    args = {
        "context_artifact": artifact,
        "baseline": baseline,
        "route_required_roles": route_roles,
    }
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, input=json.dumps(args), text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)
    assert outcome["result"]["scheduler"] == "full"
    assert outcome["result"]["axes"] == [
        "CC", "FA", "E2", "E3", "BB", "IB", "OPS",
        "QC", "MIT", "AI-E", "E5", "A3", "R4",
    ]
    assert outcome["calls"] == 14
    assert outcome["result"]["coverage_debt"] == []
    assert outcome["result"]["pass_eligible"] is True

    tier_override = subprocess.run(
        ["node", "-e", script], cwd=ROOT,
        input=json.dumps({**args, "cheap_model": "claude-sonnet-5"}),
        text=True, capture_output=True, check=False,
    )
    assert tier_override.returncode != 0
    assert "cannot override Registry saved-workflow model policy" in tier_override.stderr

    denied = subprocess.run(
        ["node", "-e", script], cwd=ROOT,
        input=json.dumps({**args, "scheduler": "adaptive"}),
        text=True, capture_output=True, check=False,
    )
    assert denied.returncode != 0
    assert "EXTERNAL_LIMIT_RECALL_AUTHORITY" in denied.stderr


def test_registry_declares_reduced_full_audit_external_limit() -> None:
    governance = _load_governance()
    registry = governance.load_registry()
    policy = registry["workflow_contracts"]["full_audit_v3"][
        "recall_authority"
    ]

    assert policy == {
        "schema_version": "full_audit_recall_authority_policy_v1",
        "status": "EXTERNAL_LIMIT_RECALL_AUTHORITY",
        "required_trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "saved_workflow_verifier": "unavailable",
        "closure_verifier": "unavailable",
    }
    assert governance.validate_registry(registry, ROOT) == []
    closure_schema = json.loads(
        (ROOT / ".codex/schemas/closure_packet_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    control = closure_schema["$defs"]["fullAuditControl"]["properties"]
    assert control["scheduler"] == {"const": "full"}
    assert control["adaptive_recall_approved"] == {"const": False}
    assert control["adaptive_recall_authority_digest"] == {"type": "null"}


def test_adaptive_or_reduced_full_audit_self_authority_fails_before_calls() -> None:
    import subprocess

    approval_digest = _digest({"approved": True})
    _governance, artifact, baseline, route_roles = _full_audit_workflow_context(
        claim_inputs={"adaptive_recall_approval": approval_digest},
    )
    base = {
        "context_artifact": artifact,
        "baseline": baseline,
        "route_required_roles": route_roles,
    }
    cases = [
        {
            **base,
            "scheduler": "adaptive",
            "adaptive_recall_approved": True,
            "adaptive_recall_authority_digest": approval_digest,
        },
        {**base, "scheduler": "adaptive_shadow"},
        {**base, "scheduler": "full", "axes": ["CC", "FA"]},
    ]
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
let calls = 0;
const agent = async () => { calls += 1; return null; };
(async () => {
  try {
    await runner(__ARGS__, () => {}, () => {}, async jobs => Promise.all(jobs.map(job => job())), async () => [], agent);
    console.log(JSON.stringify({calls, error: null}));
  } catch (error) {
    console.log(JSON.stringify({calls, error: String(error.message || error)}));
  }
})().catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__",
        json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)

    for run_args in cases:
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            input=json.dumps(run_args),
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        outcome = json.loads(completed.stdout)
        assert outcome["calls"] == 0, outcome
        assert outcome["error"] == "EXTERNAL_LIMIT_RECALL_AUTHORITY"


def test_canonical_full_audit_skill_matches_executable_registry_contract() -> None:
    import subprocess

    governance = _load_governance()
    registry = governance.load_registry()
    budget = registry["budget_envelopes"]["full_audit"]
    skill = (
        ROOT / ".claude/skills/ultracode-full-audit/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "`full` is the only currently executable scheduler" in skill
    assert 'scheduler: "full"' in skill
    assert 'scheduler: "adaptive_shadow"' not in skill
    assert "judgment_model" not in skill
    assert "20 agents" not in skill
    assert "20/96k" not in skill
    for field in (
        "max_unique_nodes",
        "max_call_attempts",
        "max_context_tokens_per_call",
        "max_workflow_planned_input_tokens",
        "retry_budget",
        "max_concurrent_calls",
    ):
        assert f"`{field}` = `{budget[field]}`" in skill
    invocation = re.search(r"```javascript\n(.*?)\n```", skill, re.DOTALL)
    assert invocation
    harness = r"""
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const dispatchFullAudit = new Function(
  `${input.source}\nreturn dispatchFullAudit;`
)();
const contextArtifact = { schema_version: 'context_artifact_v1', marker: 'exact' };
const result = dispatchFullAudit({
  Workflow: value => value,
  contextArtifact,
  admissionNowMs: 1760000000000,
  baseline: { source_head: 'a'.repeat(40) },
  scope: ['AGENTS.md'],
  dirtyScope: ['AGENTS.md'],
  surfaces: ['agent_workflow', 'full_audit'],
  focus: 'bounded',
  routeRequiredRoles: ['CC', 'AI-E'],
});
let invalidClockError = null;
try {
  dispatchFullAudit({
    Workflow: value => value, contextArtifact, admissionNowMs: 0,
    baseline: {}, scope: [], dirtyScope: [], surfaces: [],
    routeRequiredRoles: [],
  });
} catch (error) {
  invalidClockError = String(error.message || error);
}
console.log(JSON.stringify({ result, invalidClockError }));
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        input=json.dumps({"source": invocation.group(1)}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    evaluated = json.loads(completed.stdout)
    assert evaluated["result"] == {
        "name": "openclaw-full-audit",
        "args": {
            "context_artifact": {
                "schema_version": "context_artifact_v1",
                "marker": "exact",
            },
            "admission_now_ms": 1760000000000,
            "baseline": {"source_head": "a" * 40},
            "scope": ["AGENTS.md"],
            "dirty_scope": ["AGENTS.md"],
            "surfaces": ["agent_workflow", "full_audit"],
            "focus": "bounded",
            "scheduler": "full",
            "route_required_roles": ["CC", "AI-E"],
            "run_sequence": 0,
            "fix": False,
        },
    }
    assert evaluated["invalidClockError"] == (
        "dispatch-side admissionNowMs must be positive epoch-ms"
    )


def test_full_audit_no_findings_is_lazy_fourteen_call_backstop() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    args = {
        "context_artifact": artifact, "baseline": baseline,
        "route_required_roles": route_roles, "scheduler": "full",
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


def test_full_audit_scheduler_refills_a_slot_before_a_slow_axis_finishes() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    args = {
        "context_artifact": artifact,
        "baseline": baseline,
        "route_required_roles": route_roles,
        "scheduler": "full",
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
const events = [];
let active = 0;
let peak = 0;
let releaseReplacement;
let slowTimedOut = false;
const replacementStarted = new Promise(resolve => { releaseReplacement = resolve; });
const agent = async (_prompt, options) => {
  events.push(`start:${options.label}`);
  active += 1;
  peak = Math.max(peak, active);
  if (options.label === 'audit:E3') releaseReplacement();
  if (options.label === 'audit:CC') {
    const release = await Promise.race([
      replacementStarted.then(() => 'replacement'),
      new Promise(resolve => setTimeout(() => resolve('timeout'), 100)),
    ]);
    slowTimedOut = release === 'timeout';
  } else {
    await Promise.resolve();
  }
  active -= 1;
  events.push(`end:${options.label}`);
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
  console.log(JSON.stringify({result, events, peak, slowTimedOut}));
})()
  .catch(error => { console.error(error); process.exit(1); });
""".replace(
        "__WORKFLOW__",
        json.dumps(str(ROOT / ".claude/workflows/openclaw-full-audit.js")),
    ).replace("__ARGS__", NODE_STDIN_ARGS)
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        input=json.dumps(args),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)

    assert outcome["slowTimedOut"] is False
    assert outcome["events"].index("start:audit:E3") < outcome["events"].index(
        "end:audit:CC"
    )
    assert outcome["peak"] == json.loads(
        artifact["budget_authority_canonical"]
    )["max_concurrent_calls"] == 3
    assert outcome["result"]["pass_eligible"] is True


def test_full_audit_real_workflow_closes_with_exact_fixed_admissions() -> None:
    import subprocess

    governance, contract, packet = _clean_packet()
    artifact = packet["dispatch"]["context_artifact"]
    baseline = packet["baseline"]
    route_roles = list(dict.fromkeys(
        item["role"] for item in packet["dispatch"]["required_role_nodes"]
    ))
    args = {
        "context_artifact": artifact, "baseline": baseline,
        "route_required_roles": route_roles, "scheduler": "full",
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'pipeline', 'agent', source);
const consumption = {measurement_status: 'unavailable', unavailable_reason: 'harness'};
let active = 0;
let peak = 0;
const labels = [];
const agent = async (_prompt, options) => {
  labels.push(options.label);
  active += 1;
  peak = Math.max(peak, active);
  try {
    await new Promise(resolve => setTimeout(resolve, 5));
    if (options.label === 'seam-critic') return {reprobes: []};
    if (options.label.startsWith('audit')) {
      const axis = options.label.split(':').at(-1);
      const claimAxis = ['CC', 'FA'].includes(axis) ? 'shared' : axis;
      const severity = axis === 'E2' ? 'CRITICAL' : axis === 'E3' ? 'MEDIUM' : 'HIGH';
      const defectType = axis === 'E3' ? ['over-gate'] : ['other'];
      return {schema_version: 'audit_fragment_v2', verdict: 'FINDINGS', confidence: 'high', findings: [{
        title: `${claimAxis} claim`, assertion: `${claimAxis} assertion`, severity,
        classification: 'FACT', confidence: 'high', evidence: `${claimAxis} evidence`,
        impact: 'material', file: `src/${claimAxis}.py`, defect_type: defectType,
        symbol_anchor: `${claimAxis}.fn`, fix_hint: 'fix',
      }], assumptions: [], consumption};
    }
    throw new Error(`unexpected call ${options.label}`);
  } finally {
    active -= 1;
  }
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
(async () => {
  const pipeline = async () => { throw new Error('saved Full Audit must not invoke dynamic fix/review pipeline'); };
  const result = await runner(__ARGS__, () => {}, () => {}, parallel, pipeline, agent);
  console.log(JSON.stringify({result, peak, labels}));
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
    result = outcome["result"]
    admitted_concurrency = json.loads(
        artifact["budget_authority_canonical"]
    )["max_concurrent_calls"]
    assert outcome["peak"] <= admitted_concurrency
    assert len(outcome["labels"]) == 14
    assert set(outcome["labels"]) == {
        *{f"audit:{axis}" for axis in _load_governance().load_registry()[
            "workflow_contracts"
        ]["full_audit_v3"]["axes"]},
        "seam-critic",
    }
    binding = json.loads(artifact["canonical_plan"])["execution_dag_binding"]
    wave = result["workflow_wave_record"]
    actual_nodes = [
        {
            field: task[field]
            for field in (
                "node_id", "role", "native_agent", "requires",
                "node_class", "permission",
            )
        }
        for task in wave["admitted_tasks"]
    ]
    assert actual_nodes == binding["nodes"]
    assert wave["dag_digest"] == binding["dag_digest"]
    assert wave["first_attempt_call_count"] == binding["node_count"]
    closure_admissions = result["closure_admissions"]
    closure_core = [
        {
            field: admission[field]
            for field in (
                "node_id", "role", "native_agent", "requires",
                "node_class", "permission",
            )
        }
        for admission in closure_admissions
    ]
    assert closure_core == binding["nodes"]
    assert closure_admissions[-1] == {
        "node_id": "seam:critic",
        "role": "CC",
        **governance.native_agent_binding("CC", "verification"),
        "node_class": "verification",
        "requires": sorted(
            f"audit:{axis}"
            for axis in governance.load_registry()["workflow_contracts"][
                "full_audit_v3"
            ]["axes"]
        ),
        "path_scope": [],
        "reason": "full audit cross-axis seam critic",
        "result_binding": "nested_payload",
    }
    assert result["totals"]["distinct_decision_claims"] == 12
    assert result["totals"]["exact_duplicate_claims_saved"] == 1
    assert result["totals"]["deferred_claims"] == 12
    assert result["totals"]["refuted"] == 0
    assert result["totals"]["disputed"] == 0
    assert {
        fragment["payload"]["audit"]["findings"][0]["severity"]
        for fragment in result["role_fragments"][1:]
    } == {"CRITICAL", "HIGH", "MEDIUM"}
    assert all(
        item["kind"] == "staged_claim_verification"
        and item["remediation_id"] == "MAE-005"
        and item["verification_state"] == "REQUIRES_HOST_CAPABILITY_PHASE"
        and item["bound_axes"] == sorted(set(item["bound_axes"]))
        and item["owner"] == item["bound_axes"][0]
        and "host-capability verification phase" in item["reason"]
        for item in result["coverage_debt"]
    )
    shared_debt = next(
        item for item in result["coverage_debt"]
        if item["claim_key"].startswith("src/shared.py::shared.fn::")
    )
    assert shared_debt["bound_axes"] == ["CC", "FA"]
    assert sum(
        item["claim_key"] == shared_debt["claim_key"]
        for item in result["coverage_debt"]
    ) == 1
    controller = result["role_fragments"][0]
    assert controller["payload"]["disputed_count"] == 0
    assert controller["payload"]["decision_changing_findings"] == 0
    assert controller["gate_verdict"] == "UNVERIFIED"
    for fragment in result["role_fragments"][1:]:
        assert fragment["payload"]["confirmed_decision_claim_ids"] == []
        assert fragment["payload"]["disputed_claim_ids"] == []
        assert fragment["payload"]["verification_outcomes"] == []
        assert fragment["payload"]["coverage_debt_count"] == 1
        assert fragment["gate_verdict"] == "UNVERIFIED"
    assert result["pass_eligible"] is False
    assert result["fixes"] == []
    assert result["regression"] is None
    assert result["envelope"]["max_verification_calls"] == 0
    assert result["envelope"]["reserved_verification_calls"] == 0
    assert result["envelope"]["reserved_fix_pairs"] == 0
    assert result["envelope"]["verification_calls"] == 0
    assert result["envelope"]["max_unique_nodes"] == 44
    assert result["envelope"]["max_call_attempts"] == 46
    assert result["envelope"]["max_workflow_planned_input_tokens"] == 4_416_000

    packet["role_fragments"] = result["role_fragments"]
    packet["dispatch"]["admitted_role_nodes"] = deepcopy(closure_admissions)
    workflow_evidence = []
    for fragment in result["role_fragments"]:
        for index, evidence_id in enumerate(fragment["evidence_refs"]):
            if any(item["id"] == evidence_id for item in workflow_evidence):
                continue
            artifact = (
                {
                    "axis": fragment["role"],
                    "finding": fragment["payload"]["audit"]["findings"][index],
                }
                if fragment["node_id"].startswith("audit:")
                and fragment["payload"]["audit"]["findings"]
                else {"baseline": baseline}
            )
            workflow_evidence.append(
                {
                    "id": evidence_id,
                    "scope": "data",
                    "kind": "full_audit_immutable_evidence_v1",
                    "digest": _digest(artifact),
                }
            )
    packet["evidence"] = [
        item for item in packet["evidence"]
        if item["kind"] not in {
            "workflow_call_manifest_v1", "workflow_wave_record_v1",
        }
    ] + workflow_evidence + [
        {
            "id": "ev-full-call-manifest",
            "scope": "data",
            "kind": "workflow_call_manifest_v1",
            "digest": result["call_manifest"]["manifest_digest"],
            "artifact": result["call_manifest"],
        },
        {
            "id": "ev-full-wave",
            "scope": "data",
            "kind": "workflow_wave_record_v1",
            "digest": result["workflow_wave_record"]["record_digest"],
            "artifact": result["workflow_wave_record"],
        },
    ]
    packet.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "UNVERIFIED",
            "unverified": controller["payload"]["unverified_projection"],
            "acceptance": [
                {
                    "criterion": packet["acceptance"][0]["criterion"],
                    "status": "UNVERIFIED",
                    "evidence_refs": controller["evidence_refs"],
                }
            ],
            "consumption": {
                **result["consumption"],
                "wave_record_refs": ["ev-full-wave"],
            },
        }
    )
    assert governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    ) == []

    missing_seam = deepcopy(packet)
    missing_seam["dispatch"]["admitted_role_nodes"] = [
        admission
        for admission in missing_seam["dispatch"]["admitted_role_nodes"]
        if admission["node_id"] != "seam:critic"
    ]
    missing_errors = governance.validate_closure(
        missing_seam,
        execution_attestation_verifier=_host_execution_verifier(missing_seam),
    )
    assert any(
        "omits fixed call admission seam:critic" in error
        for error in missing_errors
    )

    tampered_seam = deepcopy(packet)
    seam_admission = next(
        admission
        for admission in tampered_seam["dispatch"]["admitted_role_nodes"]
        if admission["node_id"] == "seam:critic"
    )
    seam_admission["requires"] = seam_admission["requires"][1:]
    tamper_errors = governance.validate_closure(
        tampered_seam,
        execution_attestation_verifier=_host_execution_verifier(tampered_seam),
    )
    assert any(
        "substitutes fixed call node seam:critic" in error
        for error in tamper_errors
    )


def test_full_audit_overflow_emits_exact_cold_restart_recommendation() -> None:
    import subprocess

    _governance, artifact, baseline, route_roles = _full_audit_workflow_context()
    args = {
        "context_artifact": artifact, "baseline": baseline,
        "route_required_roles": route_roles, "scheduler": "full",
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
        if item["kind"] == "staged_claim_verification"
        and "host-capability verification phase" in item["reason"]
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
