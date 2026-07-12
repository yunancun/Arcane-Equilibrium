from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "helper_scripts" / "maintenance_scripts" / "agent_governance.py"
SUPPORT_PATH = ROOT / "tests/structure/test_development_agent_governance.py"
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_profit_payloads import valid_probe_payload  # noqa: E402
from agent_governance_profit_external import (  # noqa: E402
    EXT_CAPTURE_DEBT,
    external_inventory_digest,
    validate_ext_capture_lineage,
)
_CLEAN_CACHE = None
ADMITTED_CAP_FIELDS = (
    "max_context_tokens_per_call", "max_prompt_utf8_bytes_per_call",
    "max_workflow_planned_input_tokens", "max_unique_nodes",
    "max_call_attempts", "retry_budget",
)
NODE_STDIN_ARGS = "JSON.parse(fs.readFileSync(0, 'utf8'))"


def _ext_probe_payload() -> dict:
    source = {
        "url": "https://example.invalid/official-policy",
        "claim_excerpt": "A sufficiently specific captured claim.",
        "opened_at": "2026-07-11T10:00:00Z",
        "content_digest": "sha256:" + "a" * 64,
        "citation_ref": "citation:official-policy",
        "capture_ref": "platform-capture:official-policy",
    }
    opportunity = {
        "id": "ext:1", "title": "Captured external mechanism", "mode": "learn",
        "hypothesis": "A captured public mechanism may transfer after local constraints.",
        "why_now": "Current official evidence is available.",
        "evidence_refs": ["platform-capture:official-policy"],
        "estimated_net_edge": "unknown pending local test", "estimated_cost": "low",
        "wall_break_probability": "unknown",
        "falsification": "Reject when local after-cost replay fails the preregistered threshold.",
        "classification": "INFERENCE", "confidence": "low",
        "sources": [source],
        "local_constraint_fit": "Map fees, capital, data, and authority before testing locally.",
    }
    payload = {
        "schema_version": "profit_probe_fragment_v2", "axis": "EXT",
        "work_status": "DONE", "verdict": "FINDINGS", "diagnoses": [],
        "opportunities": [opportunity],
        "evidence_refs": ["platform-capture:official-policy"],
        "negative_search_summary": "The search also checked obvious alternatives and found no stronger source.",
        "next_experiments": ["Run one preregistered local after-cost falsification replay."],
        "consumption": {"measurement_status": "unavailable"},
    }
    return payload


def test_ext_opportunity_requires_opened_public_web_capture_provenance() -> None:
    payload = _ext_probe_payload()
    assert valid_probe_payload(payload, "EXT")
    missing_capture = deepcopy(payload)
    del missing_capture["opportunities"][0]["sources"][0]["capture_ref"]
    assert not valid_probe_payload(missing_capture, "EXT")


def test_ext_capture_ref_must_resolve_trusted_inventory_not_repo_or_self_report() -> None:
    payload = _ext_probe_payload()
    ref = payload["opportunities"][0]["sources"][0]["capture_ref"]
    generic_wrapper = {
        "id": ref, "kind": "repository_capture_v1", "digest": "sha256:" + "1" * 64,
    }
    self_reported = {
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "record_digest": "sha256:" + "2" * 64,
        "schema_version": "external_evidence_capture_v1",
    }
    cases = [
        ({"external_evidence": {}, "external_policy_attested": set(), "outcome_attested": set()}, {}),
        ({"external_evidence": {}, "repositories": {ref: {}}, "external_policy_attested": set(), "outcome_attested": set()}, {ref: generic_wrapper}),
        ({"external_evidence": {ref: self_reported}, "external_policy_attested": set(), "outcome_attested": set()}, {ref: {"id": ref, "kind": "external_evidence_capture_v1"}}),
    ]
    for captures, evidence in cases:
        errors, ready = validate_ext_capture_lineage(
            payload, captures=captures, evidence_by_id=evidence,
            adjudicated_at="2026-07-11T10:01:00Z",
            coverage_debt=[deepcopy(EXT_CAPTURE_DEBT)],
        )
        assert ready is False
        assert any("does not resolve to trusted external capture inventory" in error for error in errors)


def test_ext_capture_lineage_binds_url_digest_time_ttl_citation_and_trust() -> None:
    payload = _ext_probe_payload()
    source = payload["opportunities"][0]["sources"][0]
    ref = source["capture_ref"]
    artifact = {
        "schema_version": "external_evidence_capture_v1",
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "capture_kind": "external_policy_snapshot",
        "url": source["url"], "content_digest": source["content_digest"],
        "observed_at": source["opened_at"], "expires_at": "2026-07-12T10:00:00Z",
        "citation_ref": source["citation_ref"],
        "selector": "policy-section-1", "excerpt": source["claim_excerpt"],
        "excerpt_digest": "sha256:" + hashlib.sha256(
            source["claim_excerpt"].encode("utf-8")
        ).hexdigest(),
    }
    artifact["record_digest"] = _digest(artifact)
    wrapper = {
        "id": ref, "kind": "external_evidence_capture_v1", "digest": artifact["record_digest"],
        "observed_at": artifact["observed_at"], "expiry": artifact["expires_at"],
    }
    captures = {
        "external_evidence": {ref: artifact}, "external_policy_attested": {ref},
        "outcome_attested": set(),
    }
    claim_inputs = {
        "public_web_capture_inventory": external_inventory_digest(
            {ref: wrapper["digest"]}
        )
    }
    errors, ready = validate_ext_capture_lineage(
        payload, captures=captures, evidence_by_id={ref: wrapper},
        adjudicated_at="2026-07-11T10:01:00Z", coverage_debt=[],
        claim_inputs=claim_inputs,
    )
    assert errors == [] and ready is True
    unbound_errors, unbound_ready = validate_ext_capture_lineage(
        payload, captures=captures, evidence_by_id={ref: wrapper},
        adjudicated_at="2026-07-11T10:01:00Z",
        coverage_debt=[deepcopy(EXT_CAPTURE_DEBT)], claim_inputs={},
    )
    assert unbound_ready is False
    assert any("not hash-bound by claim_inputs" in error for error in unbound_errors)

    for field, replacement in (
        ("url", "https://example.invalid/tampered"),
        ("content_digest", "sha256:" + "c" * 64),
        ("opened_at", "2026-07-11T09:59:00Z"),
        ("citation_ref", "citation:tampered"),
        ("claim_excerpt", "A forged interpretation not present in the captured quote."),
    ):
        tampered = deepcopy(payload)
        tampered["opportunities"][0]["sources"][0][field] = replacement
        tamper_errors, tamper_ready = validate_ext_capture_lineage(
            tampered, captures=captures, evidence_by_id={ref: wrapper},
            adjudicated_at="2026-07-11T10:01:00Z",
            coverage_debt=[deepcopy(EXT_CAPTURE_DEBT)],
            claim_inputs=claim_inputs,
        )
        assert tamper_ready is False
        assert any("differs from capture" in error for error in tamper_errors)

    expired = {**artifact, "expires_at": "2026-07-11T10:00:30Z"}
    ttl_errors, ttl_ready = validate_ext_capture_lineage(
        payload, captures={**captures, "external_evidence": {ref: expired}},
        evidence_by_id={ref: wrapper}, adjudicated_at="2026-07-11T10:01:00Z",
        coverage_debt=[deepcopy(EXT_CAPTURE_DEBT)],
        claim_inputs=claim_inputs,
    )
    assert ttl_ready is False
    assert any("TTL is invalid" in error for error in ttl_errors)


def test_ext_without_host_capture_is_inference_debt_not_pass_evidence() -> None:
    payload = _ext_probe_payload()
    payload.update({"verdict": "NO_EVIDENCE", "opportunities": []})
    errors, ready = validate_ext_capture_lineage(
        payload,
        captures={"external_evidence": {}, "external_policy_attested": set(), "outcome_attested": set()},
        evidence_by_id={}, adjudicated_at="2026-07-11T10:01:00Z",
        coverage_debt=[deepcopy(EXT_CAPTURE_DEBT)],
    )
    assert errors == [] and ready is False
    missing_debt, _ = validate_ext_capture_lineage(
        payload,
        captures={"external_evidence": {}, "external_policy_attested": set(), "outcome_attested": set()},
        evidence_by_id={}, adjudicated_at="2026-07-11T10:01:00Z",
        coverage_debt=[],
    )
    assert "profit diagnosis EXT lacks exact trusted external-capture debt" in missing_debt


def _load_governance():
    spec = importlib.util.spec_from_file_location("agent_governance", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _host_execution_verifier(packet: dict):
    spec = importlib.util.spec_from_file_location("profit_attestation_support", SUPPORT_PATH)
    assert spec is not None and spec.loader is not None
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    return support._test_execution_attestation_verifier(packet)


def _canonical(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _fragment(
    registry: dict,
    *,
    node_id: str,
    role: str,
    task_contract_digest: str,
    payload: dict,
    summary: str | None = None,
) -> dict:
    return {
        "schema_version": "role_fragment_v1",
        "id": f"fragment:{node_id}",
        "node_id": node_id,
        "role": role,
        "task_contract_digest": task_contract_digest,
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "classification": "FACT",
        "confidence": "high",
        "summary": summary or f"{node_id} completed",
        "evidence_refs": ["ev-source-1", "ev-repo-authority"],
        "concerns": [],
        "next_action": {"owner": "PM", "action": "merge bound fragment"},
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform telemetry unavailable",
        },
        "payload_kind": registry["roles"][role]["payload_kind"],
        "payload": payload,
    }


def _refresh_profit_lineage(governance: object, packet: dict) -> None:
    context = packet["dispatch"]["context_artifact"]
    task = packet["dispatch"]["task_facts"]
    task_digest = context["task_contract_digest"]
    context_digest = context["artifact_digest"]
    dirty_scope = task["dirty_scope"]
    focus = task.get("focus", "")
    workflow_digest = _digest({"workflow": "profit-fixture", "context": context_digest})
    observed = packet["adjudicated_at"]
    controller = _controller_fragment(packet)
    fragment_by_node = {
        fragment["node_id"]: fragment
        for fragment in packet["role_fragments"]
        if fragment is not controller
    }
    dag_nodes, projection_errors = governance.delegated_execution_projection(
        packet["dispatch"]["required_role_nodes"],
        packet["dispatch"]["admitted_role_nodes"],
        excluded_nodes=governance.non_call_controller_node_ids(task),
    )
    assert projection_errors == [], projection_errors
    execution_waves, topology_errors = governance.topological_waves(dag_nodes)
    assert topology_errors == [], topology_errors
    dag_digest = governance.execution_dag_digest(dag_nodes)
    packet["dispatch"]["dag_digest"] = dag_digest
    task_by_node = {item["node_id"]: item for item in dag_nodes}
    calls = []
    result_fragments = {}
    built_calls: dict[str, dict] = {}
    for wave_index, wave_nodes in enumerate(execution_waves):
      for node in wave_nodes:
        fragment = fragment_by_node[node]
        task_spec = task_by_node[node]
        raw = fragment["payload"] if node.startswith(("evidence:", "probe:")) or node == "map:PA" else {
            key: fragment[key] for key in (
                "work_status", "gate_verdict", "classification", "confidence",
                "summary", "evidence_refs", "concerns", "next_action", "payload",
            )
        }
        call = governance.build_controller_workflow_call_record(
            workflow_contract_digest=workflow_digest,
            logical_call_id=f"profit-fixture:{node}:attempt:1", node_id=node,
            payload_kind=fragment["payload_kind"], attempt=1, retry_parent_call_id=None,
            phase="Wave", label=f"fixture:{node}",
            requested={
                "logical_role": fragment["role"],
                "platform": "claude_saved_workflow",
                "platform_requested_agent": task_spec["native_agent"],
                "native_binding": {
                    "logical_role": fragment["role"],
                    "native_agent": task_spec["native_agent"],
                    "node_class": task_spec["node_class"],
                    "permission": task_spec["permission"],
                },
                "node_class": task_spec["node_class"],
                "permission": task_spec["permission"],
                "model": None, "effort": None, "isolation": None,
            },
            prompt_digest=_digest({"prompt": node}), context_artifact_digest=context_digest,
            task_contract_digest=task_digest, dirty_scope_digest=_digest(dirty_scope),
            focus_digest=_digest(focus), compiler_input_tokens_lower_bound=0,
            admitted_input_tokens_lower_bound=0,
            response_schema_digest=_digest({"response": node}),
            started_at=observed, ended_at=observed, returned_null=False,
            parsed_result_digest=_digest(raw),
            dag_digest=dag_digest, requires=task_spec["requires"],
            topological_wave=wave_index,
            producer_generation={
                required: built_calls[required]["record_digest"]
                for required in task_spec["requires"]
            },
        )
        calls.append(call)
        built_calls[node] = call
        fragment.update({
            "context_artifact_digest": context_digest,
            "producer_record_kind": "workflow_call_record_v1",
            "producer_call_ref": call["logical_call_id"],
            "producer_call_receipt_digest": call["record_digest"],
        })
        result_fragments[node] = _digest(fragment)
    manifest = governance.build_workflow_call_manifest(calls, workflow_contract_digest=workflow_digest)
    call_by_node = {call["node_id"]: call for call in calls}
    admitted_tasks = [{
        "node_id": task_spec["node_id"], "role": task_spec["role"],
        "native_agent": task_spec["native_agent"],
        "requires": task_spec["requires"],
        "node_class": task_spec["node_class"], "permission": task_spec["permission"],
        "payload_kind": call_by_node[task_spec["node_id"]]["payload_kind"],
        "task_contract_digest": task_digest,
        "context_artifact_digest": context_digest,
        "description_digest": _digest(task_spec["node_id"]),
        "base_prompt_digest": call_by_node[task_spec["node_id"]]["prompt_digest"],
        "requested": call_by_node[task_spec["node_id"]]["requested"],
        "dirty_scope": dirty_scope, "dirty_scope_digest": _digest(dirty_scope),
        "focus": focus, "focus_digest": _digest(focus),
        "compiler_estimated_input_tokens": 0, "admitted_input_tokens_lower_bound": 0,
    } for task_spec in dag_nodes]
    authority = __import__("json").loads(context["budget_authority_canonical"])
    wave_core = {
        "schema_version": "workflow_wave_record_v1", "workflow_contract_digest": workflow_digest,
        "dag_digest": dag_digest,
        "execution_waves": execution_waves,
        "context_artifact_digests": {item["node_id"]: context_digest for item in admitted_tasks},
        "compiler_planned_input_tokens_lower_bound": 0,
        "admitted_planned_input_tokens_lower_bound": 0,
        "scheduled_call_compiler_input_tokens_lower_bound": 0,
        "scheduled_call_admitted_input_tokens_lower_bound": 0,
        "admitted_tasks": admitted_tasks, "call_manifest_digest": manifest["manifest_digest"],
        "call_record_digests": [call["record_digest"] for call in calls],
        "first_attempt_call_count": len(calls), "retry_call_count": 0,
        "null_call_count": 0, "final_null_node_count": 0,
        "coverage_debt": [],
        "budget_authority": {
            "authority_digest": context["budget_authority_digest"],
            "authority_canonical": context["budget_authority_canonical"],
            "admitted_caps": {
                field: authority[field] for field in ADMITTED_CAP_FIELDS
            },
        },
        "result_fragment_digests": result_fragments,
        "accounting_boundary": {
            "usage_measurement_status": "unavailable", "controller_overhead_status": "unavailable",
            "excluded_from_token_lower_bounds": ["semantic fixture has no platform telemetry or compiler estimate"],
        },
    }
    wave = {**wave_core, "record_digest": _digest(wave_core)}
    control = controller["payload"]
    control.update({
        "workflow_contract_digest": workflow_digest,
        "call_manifest_digest": manifest["manifest_digest"],
        "workflow_wave_record_digest": wave["record_digest"],
        "fragment_digests": {
            item["node_id"]: _digest(next(
                fragment for fragment in packet["role_fragments"]
                if fragment["node_id"] == item["node_id"]
            )) for item in control["fragment_bindings"]
        },
    })
    controller.update({
        "context_artifact_digest": context_digest,
        "producer_record_kind": "workflow_wave_record_v1",
        "producer_call_ref": wave["record_digest"],
        "producer_call_receipt_digest": wave["record_digest"],
    })
    packet["evidence"] = [
        item for item in packet["evidence"]
        if item["id"] not in {"ev-profit-call-manifest", "ev-profit-wave"}
    ] + [
        {"id": "ev-profit-call-manifest", "scope": "data", "kind": "workflow_call_manifest_v1", "digest": manifest["manifest_digest"], "artifact": manifest},
        {"id": "ev-profit-wave", "scope": "data", "kind": "workflow_wave_record_v1", "digest": wave["record_digest"], "artifact": wave},
    ]
    packet["consumption"] = {
        "measurement_status": "partial", "measurement_source": "orchestrator_receipt",
        "unavailable_reason": "actual platform usage unavailable in semantic fixture",
        "wave_record_refs": ["ev-profit-wave"],
        "missing_metrics": ["input_tokens", "output_tokens", "cache_read_tokens", "tool_calls", "wall_time_ms", "accepted_findings", "rework_count"],
        "planned_tokens": 0, "retry_count": 0, "fan_out": len(calls),
        "quality_reserve_used": False,
    }


def _clean_packet() -> tuple[object, dict, dict]:
    global _CLEAN_CACHE
    if _CLEAN_CACHE is not None:
        governance, contract, packet = _CLEAN_CACHE
        return governance, contract, deepcopy(packet)
    governance = _load_governance()
    registry = governance.load_registry()
    contract = registry["workflow_contracts"]["profit_diagnosis_v1"]
    observed = datetime.now(timezone.utc)
    adjudicated = observed + timedelta(minutes=1)
    expiry = observed + timedelta(hours=1)
    observed_at = observed.isoformat()
    adjudicated_at = adjudicated.isoformat()
    expiry_at = expiry.isoformat()
    task_baseline = governance.capture_repository_baseline()
    criterion = "profit diagnosis is complete and decision ready"
    priors = {
        "as_of": observed_at,
        "constraints": ["demo-only", "after-cost evidence required"],
    }
    priors_digest = _digest(priors)
    task_facts = {
        "task_shape": "analysis",
        "surfaces": ["profit_diagnosis"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "objective": "bind a complete profit diagnosis",
        "scope": "bounded profit diagnosis",
        "dirty_scope": sorted([
            ".claude/workflows/profit-diagnosis.js", "CLAUDE.md",
            "helper_scripts/maintenance_scripts/agent_governance_profit.py",
            "helper_scripts/maintenance_scripts/agent_governance_profit_payloads.py",
        ]),
        "claim_inputs": {"profit_priors": priors_digest},
        "acceptance_criteria": [criterion],
        "hard_stops": ["no runtime or broker effect"],
        "baseline": task_baseline,
        "direct_interfaces": ["profit-diagnosis.js", "validate_closure"],
        "previous_failure": "profit control could omit evidence debt",
    }
    route = governance.route_task(task_facts)
    context_plan = governance.compile_context("PM", route["task_facts"])
    context_artifact = governance.materialize_context_artifact(context_plan)
    task_contract_digest = context_artifact["task_contract_digest"]
    baseline = {
        **task_baseline,
        "runtime_head": None,
        "runtime_observed_at": None,
    }
    receipt = governance.build_source_review_receipt(
        producer_role="E2",
        command="review profit diagnosis closure fixture",
        baseline=baseline,
        criteria=[criterion],
        observed_at=observed_at,
        exit_code=0,
        stdout=b"profit diagnosis fixture verified",
        stderr=b"",
    )
    repository_capture = governance.capture_repository(route["task_facts"]["dirty_scope"])
    policy_source = next(item for item in context_plan["sources"] if item["source"] == "AGENTS.md")
    authority_refs = [
        governance.build_authority_claim(
            authority_class="normative_policy",
            subject="profit_diagnosis_policy",
            value=policy_source["content"],
            source=policy_source["source"],
            source_ref=f"context:{policy_source['source']}",
            source_digest=policy_source["content_digest"],
            observed_at=policy_source["observed_at"],
            scope="repo",
            strength="direct",
            expiry=None,
        ),
        governance.build_authority_claim(
            authority_class="claim_evidence",
            subject="profit_diagnosis_priors",
            value=deepcopy(priors),
            source="profit_diagnosis_priors_v1",
            source_ref="task_contract:claim_inputs:profit_priors",
            source_digest=priors_digest,
            observed_at=observed_at,
            scope="profit_diagnosis:priors",
            strength="derived",
            expiry=expiry_at,
        ),
    ]

    evidence_axes = contract["evidence_axes"]
    probe_axes = contract["probe_axes"]
    role_by_probe = {axis: ("QC" if axis == "EXT" else axis) for axis in probe_axes}
    role_fragments = [
        _fragment(
            registry,
            node_id="pa_design",
            role="PA",
            task_contract_digest=task_contract_digest,
            payload={"node": "pa_design"},
        )
    ]
    diagnosis_fragments = []
    for axis in evidence_axes:
        diagnosis_fragments.append(
            _fragment(
                registry,
                node_id=f"evidence:{axis}",
                role=axis,
                task_contract_digest=task_contract_digest,
                payload={
                    "schema_version": "profit_evidence_fragment_v2",
                    "axis": axis,
                    "work_status": "DONE",
                    "summary": f"{axis} evidence complete",
                    "facts": [
                        {
                            "id": f"{axis}-fact-1",
                            "classification": "FACT",
                            "scope": "source",
                            "evidence_ref": "ev-repo-authority",
                            "observation": f"{axis} fixture observation",
                            "observed_at": repository_capture["observed_at"],
                            "freshness": "fresh",
                            "limitation": "source-only semantic fixture",
                        }
                    ],
                    "gaps": [],
                    "consumption": {
                        "measurement_status": "unavailable",
                        "unavailable_reason": "platform telemetry unavailable",
                    },
                },
            )
        )
        diagnosis_fragments[-1]["evidence_refs"] = ["ev-repo-authority"]
    for axis in probe_axes:
        diagnosis_fragments.append(
            _fragment(
                registry,
                node_id=f"probe:{axis}",
                role=role_by_probe[axis],
                task_contract_digest=task_contract_digest,
                payload={
                    "schema_version": "profit_probe_fragment_v2",
                    "axis": axis,
                    "work_status": "DONE",
                    "verdict": "NO_EVIDENCE",
                    "diagnoses": [],
                    "opportunities": [],
                    "evidence_refs": ["ev-repo-authority"],
                    "negative_search_summary": f"{axis} search found no supported move",
                    "next_experiments": [f"repeat {axis} review after fresh evidence"],
                    "consumption": {
                        "measurement_status": "unavailable",
                        "unavailable_reason": "platform telemetry unavailable",
                    },
                },
            )
        )
        diagnosis_fragments[-1]["evidence_refs"] = ["ev-repo-authority"]
    ext_fragment = next(
        fragment for fragment in diagnosis_fragments
        if fragment["node_id"] == "probe:EXT"
    )
    ext_fragment.update(
        gate_verdict="CONDITIONAL", classification="INFERENCE",
        confidence="med", concerns=[EXT_CAPTURE_DEBT["reason"]],
    )
    diagnosis_fragments.append(
        _fragment(
            registry,
            node_id="map:PA",
            role="PA",
            task_contract_digest=task_contract_digest,
            payload={
                "schema_version": "profit_map_v2",
                "work_status": "DONE",
                "decision_ready": True,
                "top_moves": [],
                "negative_results": [
                    {
                        "axis": axis,
                        "searched": f"{axis} search found no supported move",
                        "result": "NO_EVIDENCE under current baseline and priors",
                        "next_review_condition": f"repeat {axis} review after fresh evidence",
                        "evidence_refs": ["ev-repo-authority"],
                    }
                    for axis in probe_axes
                ],
                "coverage_debt": [],
                "consumption": {
                    "measurement_status": "unavailable",
                    "unavailable_reason": "platform telemetry unavailable",
                },
            },
        )
    )
    diagnosis_fragments[-1]["evidence_refs"] = ["ev-repo-authority"]
    bindings = [
        {
            "node_id": fragment["node_id"], "role": fragment["role"],
            **governance.native_agent_binding(fragment["role"], "verification"),
            "node_class": "verification",
            "reason": (
                "profit map synthesis"
                if fragment["node_id"] == "map:PA"
                else "profit diagnosis admitted evidence/probe"
            ),
        }
        for fragment in diagnosis_fragments
    ]
    diagnosis_node_ids = [binding["node_id"] for binding in bindings]
    admissions = [
        {
            **binding,
            "requires": (
                sorted(node for node in diagnosis_node_ids if node != "map:PA")
                if binding["node_id"] == "map:PA"
                else ["pa_design"]
            ),
            "path_scope": [], "result_binding": "role_fragment",
        }
        for binding in bindings
    ]
    control_payload = {
        "schema_version": "profit_diagnosis_control_v1",
        "task_contract_digest": task_contract_digest,
        "context_artifact_digest": context_artifact["artifact_digest"],
        "budget_authority_digest": context_artifact["budget_authority_digest"],
        "hard_stops": task_facts["hard_stops"],
        "baseline": deepcopy(baseline),
        "baseline_digest": _digest(baseline),
        "scope": "bounded profit diagnosis",
        "focus": "",
        "priors_digest": priors_digest,
        "claim_inputs_digest": _digest({"profit_priors": priors_digest}),
        "expected_evidence_axes": deepcopy(evidence_axes),
        "admitted_evidence_axes": deepcopy(evidence_axes),
        "expected_probe_axes": deepcopy(probe_axes),
        "admitted_probe_axes": deepcopy(probe_axes),
        "deferred_probe_axes": [],
        "fragment_bindings": deepcopy(bindings),
        "fragment_digests": {
            fragment["node_id"]: _digest(fragment)
            for fragment in diagnosis_fragments
        },
        "coverage_debt": [deepcopy(EXT_CAPTURE_DEBT)],
        "map_node_id": "map:PA",
        "decision_ready": False,
        "pass_eligible": False,
        "unverified_projection": [
            "profit_diagnosis_debt:" + _canonical(EXT_CAPTURE_DEBT)
        ],
        "envelope": {
            "accounting_basis": "utf8_bytes_div4_planned_lower_bound_v1",
            "max_context_tokens_per_call": 480_000,
            "max_prompt_utf8_bytes_per_call": 1_919_996,
            "max_workflow_planned_input_tokens": 10_560_000,
            "max_unique_nodes": 20,
            "max_call_attempts": 22,
            "retry_budget": 2,
            "retry_capacity": 2,
            "estimated_tokens_per_evidence": 20_000,
            "estimated_tokens_per_probe": 24_000,
            "estimated_tokens_for_map": 30_000,
            "planned_input_tokens": 294_000,
            "planned_unique_nodes": 10,
            "planned_call_attempts": 12,
        },
    }
    role_fragments.append(
        _fragment(
            registry,
            node_id="profit_control",
            role="AI-E",
            task_contract_digest=task_contract_digest,
            payload=control_payload,
            summary="profit diagnosis controller ready",
        )
    )
    role_fragments[-1].update(
        work_status="DONE_WITH_CONCERNS", gate_verdict="CONDITIONAL",
        classification="INFERENCE", confidence="med",
        concerns=["profit_diagnosis_debt:" + _canonical(EXT_CAPTURE_DEBT)],
    )
    role_fragments.extend(diagnosis_fragments)
    admitted_roles = {binding["role"] for binding in bindings}
    packet = {
        "schema_version": "closure_packet_v1",
        "task_id": "profit-diagnosis-control",
        "human_summary": {
            "objective": "bind a complete profit diagnosis",
            "scope": "bounded profit diagnosis",
            "outcome": "profit diagnosis is decision ready",
        },
        "work_status": "DONE_WITH_CONCERNS",
        "gate_verdict": "CONDITIONAL",
        "disposition": "DEFERRED",
        "confidence": "med",
        "adjudicated_at": adjudicated_at,
        "baseline": baseline,
        "dispatch": {
            "task_facts": route["task_facts"],
            "context_artifact": context_artifact,
            "dag_digest": route["dag_digest"],
            "required_role_nodes": route["required_role_nodes"],
            "admitted_role_nodes": deepcopy(admissions),
        },
        "authority_refs": authority_refs,
        "acceptance": [
            {"criterion": criterion, "status": "UNVERIFIED", "evidence_refs": ["ev-source-1", "ev-repo-authority"]}
        ],
        "evidence": [
            {
                "id": "ev-source-1",
                "scope": "source",
                "kind": "source_review_receipt_v1",
                "digest": receipt["receipt_digest"],
                "observed_at": observed_at,
                "artifact": receipt,
            },
            {
                "id": "ev-repo-authority", "scope": "source",
                "kind": "repository_capture_v1",
                "digest": repository_capture["record_digest"],
                "observed_at": repository_capture["observed_at"],
                "artifact": repository_capture,
            },
        ],
        "role_fragments": role_fragments,
        "checks": [],
        "side_effects": {
            "repo_mutation": False,
            "runtime_contact": False,
            "private_external_contact": False,
            "broker_effect": False,
        },
        "unverified": ["profit_diagnosis_debt:" + _canonical(EXT_CAPTURE_DEBT)],
        "skipped_roles": [
            item for item in route["skipped"] if item["role"] not in admitted_roles
        ],
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform telemetry unavailable",
        },
        "next_action": {"owner": "PM", "action": "close"},
    }
    _refresh_profit_lineage(governance, packet)
    errors = governance.validate_closure(
        packet, execution_attestation_verifier=_host_execution_verifier(packet)
    )
    assert errors == [], errors
    _CLEAN_CACHE = (governance, contract, deepcopy(packet))
    return governance, contract, packet


def _control(packet: dict) -> dict:
    return next(
        fragment["payload"]
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "profit_control"
    )


def _controller_fragment(packet: dict) -> dict:
    return next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "profit_control"
    )


def _debt_projection(debt: dict) -> str:
    return "profit_diagnosis_debt:" + _canonical(debt)


def _defer_probe(packet: dict, axis: str) -> None:
    control = _control(packet)
    node_id = f"probe:{axis}"
    control["admitted_probe_axes"].remove(axis)
    control["deferred_probe_axes"].append(axis)
    control["envelope"]["planned_input_tokens"] -= control["envelope"][
        "estimated_tokens_per_probe"
    ]
    control["envelope"]["planned_unique_nodes"] -= 1
    control["envelope"]["planned_call_attempts"] -= 1
    control["fragment_bindings"] = [
        item for item in control["fragment_bindings"] if item["node_id"] != node_id
    ]
    control["fragment_digests"].pop(node_id)
    packet["dispatch"]["admitted_role_nodes"] = [
        item
        for item in packet["dispatch"]["admitted_role_nodes"]
        if item["node_id"] != node_id
    ]
    next(
        item for item in packet["dispatch"]["admitted_role_nodes"]
        if item["node_id"] == "map:PA"
    )["requires"].remove(node_id)
    packet["role_fragments"] = [
        fragment for fragment in packet["role_fragments"] if fragment["node_id"] != node_id
    ]
    map_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"]["negative_results"] = [
        item
        for item in map_fragment["payload"]["negative_results"]
        if item["axis"] != axis
    ]
    control["fragment_digests"]["map:PA"] = _digest(map_fragment)
    debt = {
        "kind": "axis",
        "id": axis,
        "reason": "deferred by max_unique_nodes/max_workflow_planned_input_tokens envelope",
        "owner": "QC" if axis == "EXT" else axis,
    }
    projection = _debt_projection(debt)
    control.update(
        {
            "coverage_debt": [debt],
            "decision_ready": False,
            "pass_eligible": False,
            "unverified_projection": [projection],
        }
    )
    controller = _controller_fragment(packet)
    controller.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "CONDITIONAL",
            "classification": "INFERENCE",
            "confidence": "med",
            "concerns": [projection],
        }
    )
    packet.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "UNVERIFIED",
            "confidence": "med",
            "unverified": [projection],
        }
    )
    _refresh_profit_lineage(_load_governance(), packet)


def test_profit_control_clean_packet_passes_public_closure_validation() -> None:
    _clean_packet()


def test_profit_control_recomputes_the_canonical_priors_digest() -> None:
    governance, _contract, packet = _clean_packet()
    priors_ref = next(
        ref
        for ref in packet["authority_refs"]
        if ref["source"] == "profit_diagnosis_priors_v1"
    )
    priors_ref["value"] = {"substituted": True}
    priors_ref["claim_digest"] = governance.authority_claim_digest(priors_ref)

    assert "profit diagnosis priors value does not match its canonical digest" in (
        governance.validate_closure(packet)
    )
    governance, _contract, stale = _clean_packet()
    stale_ref = next(ref for ref in stale["authority_refs"] if ref["source"] == "profit_diagnosis_priors_v1")
    stale_ref.update({"class": "normative_policy", "expiry": None})
    stale_ref["claim_digest"] = governance.authority_claim_digest(stale_ref)
    assert "profit diagnosis priors are not hash/scope-bound authority" in governance.validate_closure(stale)


def test_profit_control_recomputes_the_canonical_baseline_digest() -> None:
    governance, _contract, packet = _clean_packet()
    _control(packet)["baseline_digest"] = "sha256:" + "f" * 64

    assert "profit diagnosis baseline digest is not canonical" in (
        governance.validate_closure(packet)
    )


def test_profit_control_requires_the_exact_canonical_admission_inventory() -> None:
    governance, _contract, packet = _clean_packet()
    control_binding = next(
        item
        for item in _control(packet)["fragment_bindings"]
        if item["node_id"] == "probe:QC"
    )
    dispatch_binding = next(
        item
        for item in packet["dispatch"]["admitted_role_nodes"]
        if item["node_id"] == "probe:QC"
    )
    control_binding["reason"] = "rewritten admission reason"
    dispatch_binding["reason"] = "rewritten admission reason"

    assert "profit diagnosis fragment bindings are not the canonical admitted inventory" in (
        governance.validate_closure(packet)
    )


def test_profit_control_rejects_fragment_content_or_digest_substitution() -> None:
    governance, _contract, packet = _clean_packet()
    probe = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "probe:IB"
    )
    probe["payload"]["negative_search_summary"] = "substituted after control digest"

    assert "profit diagnosis fragment probe:IB digest is invalid" in (
        governance.validate_closure(packet)
    )


def test_profit_lineage_rejects_missing_cross_role_cross_task_result_and_fake_refs() -> None:
    governance, _contract, packet = _clean_packet()

    def fragment(target: dict, node: str) -> dict:
        return next(item for item in target["role_fragments"] if item["node_id"] == node)

    def manifest(target: dict) -> dict:
        return next(
            item["artifact"] for item in target["evidence"]
            if item["kind"] == "workflow_call_manifest_v1"
        )

    missing = deepcopy(packet)
    fragment(missing, "evidence:OPS")["producer_call_ref"] = "missing:call"
    assert any(
        "evidence:OPS producer call is missing" in error
        for error in governance.validate_closure(missing)
    )

    cross_role = deepcopy(packet)
    ops = fragment(cross_role, "evidence:OPS")
    mit_call = next(
        call for call in manifest(cross_role)["records"] if call["node_id"] == "evidence:MIT"
    )
    ops.update({
        "producer_call_ref": mit_call["logical_call_id"],
        "producer_call_receipt_digest": mit_call["record_digest"],
    })
    errors = governance.validate_closure(cross_role)
    assert any("evidence:OPS producer call/result binding is invalid" in error for error in errors)
    assert any("evidence:OPS producer role/null state is invalid" in error for error in errors)

    cross_task = deepcopy(packet)
    manifest(cross_task)["records"][0]["task_contract_digest"] = "sha256:" + "f" * 64
    assert any(
        "task_contract_digest" in error or "self-digest" in error
        for error in governance.validate_closure(cross_task)
    )

    cross_result = deepcopy(packet)
    fragment(cross_result, "probe:QC")["payload"]["negative_search_summary"] = "substituted after call"
    assert any(
        "probe:QC producer call/result binding is invalid" in error
        for error in governance.validate_closure(cross_result)
    )

    fake_receipt = deepcopy(packet)
    fragment(fake_receipt, "map:PA")["producer_call_receipt_digest"] = "sha256:" + "0" * 64
    assert any(
        "map:PA producer call/result binding is invalid" in error
        for error in governance.validate_closure(fake_receipt)
    )


def test_profit_facts_reject_future_runtime_prose_missing_debt_and_duplicate_ids() -> None:
    governance, _contract, packet = _clean_packet()

    def evidence_fragment(target: dict, axis: str) -> dict:
        return next(
            item for item in target["role_fragments"]
            if item["node_id"] == f"evidence:{axis}"
        )

    future = deepcopy(packet)
    future_fact = evidence_fragment(future, "OPS")["payload"]["facts"][0]
    future_fact["observed_at"] = (
        datetime.fromisoformat(future["adjudicated_at"]) + timedelta(minutes=1)
    ).isoformat()
    assert any(
        "OPS fact OPS-fact-1 is future-dated" in error
        for error in governance.validate_closure(future)
    )

    freshness_lie = deepcopy(packet)
    evidence_fragment(freshness_lie, "OPS")["payload"]["facts"][0]["freshness"] = "recent"
    assert any(
        "OPS FACT OPS-fact-1 freshness/TTL is invalid" in error
        for error in governance.validate_closure(freshness_lie)
    )

    expired_capture = deepcopy(packet)
    next(
        item for item in expired_capture["evidence"]
        if item["id"] == "ev-repo-authority"
    )["expiry"] = expired_capture["adjudicated_at"]
    expired_errors = governance.validate_closure(expired_capture)
    assert any("OPS FACT OPS-fact-1 freshness/TTL is invalid" in error for error in expired_errors)
    assert any("OPS has no fresh captured FACT or exact debt" in error for error in expired_errors)

    runtime_prose = deepcopy(packet)
    runtime_fact = evidence_fragment(runtime_prose, "OPS")["payload"]["facts"][0]
    runtime_fact.update({
        "scope": "runtime", "evidence_ref": "ev-repo-authority",
        "observation": "fabricated future runtime success prose",
    })
    runtime_errors = governance.validate_closure(runtime_prose)
    assert any("FACT OPS-fact-1 lacks scope-appropriate captured evidence" in error for error in runtime_errors)
    assert any("fact OPS-fact-1 lacks exact attestation debt" in error for error in runtime_errors)

    invented_ref = deepcopy(packet)
    invented_fact = evidence_fragment(invented_ref, "MIT")["payload"]["facts"][0]
    invented_fact.update({"evidence_ref": "invented:prose", "observation": "plausible but uncaptured data claim"})
    assert any(
        "FACT MIT-fact-1 lacks scope-appropriate captured evidence" in error
        for error in governance.validate_closure(invented_ref)
    )

    inference_only = deepcopy(packet)
    evidence_fragment(inference_only, "AI-E")["payload"]["facts"][0]["classification"] = "INFERENCE"
    assert any(
        "AI-E has no fresh captured FACT or exact debt" in error
        for error in governance.validate_closure(inference_only)
    )

    duplicate = deepcopy(packet)
    evidence_fragment(duplicate, "MIT")["payload"]["facts"][0]["id"] = "OPS-fact-1"
    assert "profit diagnosis fact ids must be globally unique" in governance.validate_closure(duplicate)

    hidden_ref = deepcopy(packet)
    evidence_fragment(hidden_ref, "OPS")["evidence_refs"] = ["ev-source-1"]
    assert "profit diagnosis evidence fragment evidence:OPS evidence_refs differ from facts" in governance.validate_closure(hidden_ref)


def test_profit_probe_rejects_incomplete_nested_diagnosis_content() -> None:
    governance, _contract, packet = _clean_packet()
    probe = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "probe:QC"
    )
    probe["payload"]["diagnoses"] = [
        {
            "area": "leak",
            "title": "incomplete diagnosis",
            "classification": "INFERENCE",
            "evidence_refs": ["ev-repo-authority"],
        }
    ]
    probe["payload"]["verdict"] = "FINDINGS"
    _refresh_profit_lineage(governance, packet)

    assert any(
        "profit diagnosis probe fragment probe:QC payload is invalid" in error
        for error in governance.validate_closure(packet)
    )


def test_profit_probe_recomputes_fragment_evidence_refs_from_nested_content() -> None:
    governance, _contract, packet = _clean_packet()
    probe = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "probe:QC"
    )
    probe["payload"]["diagnoses"] = [
        {
            "id": "QC-diagnosis-1",
            "area": "leak",
            "title": "bounded diagnosis",
            "classification": "INFERENCE",
            "evidence_refs": ["ev-repo-authority"],
            "blocker": "source-only evidence",
            "net_profit_impact": "requires measurement",
            "confidence": "med",
        }
    ]
    probe["payload"]["verdict"] = "FINDINGS"
    probe["evidence_refs"] = ["ev-repo-authority", "ev-source-1"]
    _refresh_profit_lineage(governance, packet)

    assert any(
        "probe fragment probe:QC evidence_refs differ from nested content" in error
        for error in governance.validate_closure(packet)
    )


def test_profit_probe_rejects_incomplete_nested_opportunity_content() -> None:
    governance, _contract, packet = _clean_packet()
    probe = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "probe:MIT"
    )
    probe["payload"]["opportunities"] = [
        {
            "title": "incomplete opportunity",
            "mode": "learn",
            "evidence_refs": ["ev-repo-authority"],
        }
    ]
    probe["payload"]["verdict"] = "FINDINGS"
    _refresh_profit_lineage(governance, packet)

    assert any(
        "profit diagnosis probe fragment probe:MIT payload is invalid" in error
        for error in governance.validate_closure(packet)
    )


def test_profit_map_recomputes_complete_negative_result_projection() -> None:
    governance, _contract, packet = _clean_packet()
    map_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"]["negative_results"][0]["searched"] = (
        "different search summary with the same axis"
    )
    _refresh_profit_lineage(governance, packet)

    assert any(
        "map negative results differ from probe projections" in error
        for error in governance.validate_closure(packet)
    )


def test_profit_map_requires_source_opportunity_and_evidence_ids() -> None:
    governance, _contract, packet = _clean_packet()
    map_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"]["top_moves"] = [
        {
            "rank": 1,
            "title": "unbound candidate move",
            "mode": "learn",
            "roi_rationale": "cannot be ranked without exact source ids",
            "wall_break_probability": "unknown",
            "evidence_level": "INFERENCE",
            "falsification": "fresh evidence reverses the expected value",
            "next_step": "capture the missing lineage",
            "owner": "AI-E",
        }
    ]
    _refresh_profit_lineage(governance, packet)

    assert any(
        "map top move source lineage is invalid" in error
        for error in governance.validate_closure(packet)
    )


def test_profit_control_rejects_rehashed_non_contract_fragment_payloads() -> None:
    governance, _contract, packet = _clean_packet()
    evidence = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "evidence:MIT"
    )
    evidence["payload"]["schema_version"] = "substituted_payload_v1"
    _control(packet)["fragment_digests"]["evidence:MIT"] = _digest(evidence)

    assert "profit diagnosis evidence fragment evidence:MIT payload is invalid" in (
        governance.validate_closure(packet)
    )


def test_profit_control_cannot_cherry_pick_a_deferred_probe_or_omit_its_debt() -> None:
    governance, _contract, packet = _clean_packet()
    _defer_probe(packet, "EXT")
    assert governance.validate_closure(packet) == []

    control = _control(packet)
    control["coverage_debt"] = []
    control["unverified_projection"] = []
    _controller_fragment(packet)["concerns"] = []
    packet["unverified"] = []

    assert "profit diagnosis deferred probe EXT lacks debt" in (
        governance.validate_closure(packet)
    )


def test_profit_control_requires_debt_for_incomplete_mandatory_evidence() -> None:
    governance, _contract, packet = _clean_packet()
    evidence_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "evidence:OPS"
    )
    evidence_fragment["payload"]["work_status"] = "BLOCKED"
    _control(packet)["fragment_digests"]["evidence:OPS"] = _digest(evidence_fragment)

    errors = governance.validate_closure(packet)
    assert "profit diagnosis mandatory evidence OPS is incomplete without debt" in errors
    assert "profit diagnosis evidence fragment evidence:OPS status disagrees with payload" in errors


def test_profit_control_recomputes_map_readiness_from_the_bound_map_fragment() -> None:
    governance, _contract, packet = _clean_packet()
    map_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"]["work_status"] = "BLOCKED"
    _control(packet)["fragment_digests"]["map:PA"] = _digest(map_fragment)

    errors = governance.validate_closure(packet)
    assert "profit diagnosis non-ready map lacks canonical debt" in errors
    assert "profit diagnosis map:PA producer call/result binding is invalid" in errors
    assert "profit diagnosis non-ready map lacks canonical debt" in errors


def test_profit_control_requires_debt_for_an_incomplete_admitted_probe() -> None:
    governance, _contract, packet = _clean_packet()
    probe_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "probe:MIT"
    )
    probe_fragment["payload"].update(
        {"work_status": "BLOCKED", "verdict": "BLOCKED"}
    )
    _control(packet)["fragment_digests"]["probe:MIT"] = _digest(probe_fragment)

    errors = governance.validate_closure(packet)
    assert "profit diagnosis admitted probe MIT is incomplete without debt" in errors
    assert "profit diagnosis probe fragment probe:MIT status disagrees with payload" in errors


def test_profit_control_requires_canonical_debt_for_a_non_ready_map() -> None:
    governance, _contract, packet = _clean_packet()
    map_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"]["decision_ready"] = False
    map_fragment.update(
        {
            "gate_verdict": "CONDITIONAL",
            "classification": "INFERENCE",
            "confidence": "med",
        }
    )
    control = _control(packet)
    control["fragment_digests"]["map:PA"] = _digest(map_fragment)
    control.update({"decision_ready": False, "pass_eligible": False})
    _controller_fragment(packet).update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "CONDITIONAL",
            "classification": "INFERENCE",
            "confidence": "med",
        }
    )
    packet.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "UNVERIFIED",
            "confidence": "med",
        }
    )

    assert "profit diagnosis non-ready map lacks canonical debt" in (
        governance.validate_closure(packet)
    )


def test_profit_control_requires_each_map_coverage_debt_item_losslessly() -> None:
    governance, _contract, packet = _clean_packet()
    map_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"].update(
        {"decision_ready": False, "coverage_debt": ["unresolved ranking evidence"]}
    )
    map_fragment.update(
        {
            "gate_verdict": "CONDITIONAL",
            "classification": "INFERENCE",
            "confidence": "med",
        }
    )
    control = _control(packet)
    control["fragment_digests"]["map:PA"] = _digest(map_fragment)
    control.update({"decision_ready": False, "pass_eligible": False})
    _controller_fragment(packet).update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "CONDITIONAL",
            "classification": "INFERENCE",
            "confidence": "med",
        }
    )
    packet.update(
        {
            "work_status": "DONE_WITH_CONCERNS",
            "gate_verdict": "UNVERIFIED",
            "confidence": "med",
        }
    )

    assert "profit diagnosis map coverage debt PA:1 is not losslessly bound" in (
        governance.validate_closure(packet)
    )


def test_profit_control_projection_is_exact_in_controller_and_closure() -> None:
    governance, _contract, packet = _clean_packet()
    _defer_probe(packet, "EXT")

    stale_closure = deepcopy(packet)
    stale_closure["unverified"].append(
        "profit_diagnosis_debt:"
        + _canonical(
            {"kind": "axis", "id": "stale", "reason": "stale", "owner": "PM"}
        )
    )
    assert "profit diagnosis closure unverified projection is not canonical" in (
        governance.validate_closure(stale_closure)
    )

    hidden_controller = deepcopy(packet)
    _controller_fragment(hidden_controller)["concerns"] = []
    assert "profit diagnosis controller concerns omit or change debt" in (
        governance.validate_closure(hidden_controller)
    )


def test_profit_control_controller_status_is_derived_from_readiness() -> None:
    governance, _contract, packet = _clean_packet()
    _defer_probe(packet, "EXT")
    _controller_fragment(packet)["gate_verdict"] = "PASS"

    assert "profit diagnosis controller status disagrees with readiness" in (
        governance.validate_closure(packet)
    )


def test_profit_control_recomputes_envelope_and_retry_reserve() -> None:
    governance, _contract, packet = _clean_packet()
    envelope = _control(packet)["envelope"]
    envelope["planned_input_tokens"] = 1
    envelope["retry_capacity"] = 0
    envelope["planned_unique_nodes"] = 4
    envelope["planned_call_attempts"] = 4

    errors = governance.validate_closure(packet)
    assert "profit diagnosis retry capacity disagrees with its envelope" in errors
    assert "profit diagnosis planned token estimate is inconsistent" in errors
    assert "profit diagnosis planned call attempts are inconsistent" in errors
    governance, _contract, understated = _clean_packet()
    understated_envelope = _control(understated)["envelope"]
    understated_envelope.update({"estimated_tokens_per_evidence": 1, "estimated_tokens_per_probe": 1, "estimated_tokens_for_map": 1})
    assert "profit diagnosis envelope exceeds governed bounds" in governance.validate_closure(understated)


def test_profit_control_rejects_empty_semantic_success_and_focus_drift() -> None:
    governance, _contract, packet = _clean_packet()
    evidence = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "evidence:OPS"
    )
    evidence["payload"]["facts"] = []
    _control(packet)["fragment_digests"]["evidence:OPS"] = _digest(evidence)
    assert "profit diagnosis evidence fragment evidence:OPS payload is invalid" in (
        governance.validate_closure(packet)
    )

    governance, _contract, empty_map = _clean_packet()
    map_fragment = next(
        fragment
        for fragment in empty_map["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"].update(top_moves=[], negative_results=[])
    _control(empty_map)["fragment_digests"]["map:PA"] = _digest(map_fragment)
    errors = governance.validate_closure(empty_map)
    assert "profit diagnosis map negative results differ from probe projections" in errors
    assert "profit diagnosis map negative results differ from probe projections" in errors

    governance, _contract, focus_drift = _clean_packet()
    _control(focus_drift)["focus"] = "unadmitted focus substitution"
    assert "profit diagnosis focus differs from admitted task contract" in (
        governance.validate_closure(focus_drift)
    )


def test_ranked_profit_moves_need_captured_actual_consumption_or_debt() -> None:
    governance, _contract, packet = _clean_packet()
    map_fragment = next(
        fragment
        for fragment in packet["role_fragments"]
        if fragment["node_id"] == "map:PA"
    )
    map_fragment["payload"]["top_moves"] = [
        {
            "rank": 1,
            "title": "candidate move",
            "mode": "learn",
            "roi_rationale": "requires captured actual workflow cost before ranking",
            "wall_break_probability": "unknown",
            "evidence_level": "INFERENCE",
            "regime_caveat": "fixture",
            "falsification": "captured cost makes net value negative",
            "next_step": "capture platform usage",
            "owner": "AI-E",
            "source_opportunity_ids": ["missing-opportunity"],
            "evidence_refs": ["ev-repo-authority"],
        }
    ]
    _control(packet)["fragment_digests"]["map:PA"] = _digest(map_fragment)
    errors = governance.validate_closure(packet)
    assert (
        "profit diagnosis ranked moves require actual-consumption debt when telemetry is unavailable"
        in errors
    )
    assert "profit diagnosis map:PA producer call/result binding is invalid" in errors


def test_profit_workflow_binds_canonical_baseline_priors_and_consumption_plan() -> None:
    governance = _load_governance()
    source_baseline = governance.capture_repository_baseline()
    baseline = {**source_baseline, "runtime_head": None, "runtime_observed_at": None}
    priors = {"constraints": ["demo-only"], "as_of": "2026-07-10T12:00:00Z"}
    task_prompt = "Run the canonical bounded profit diagnosis."
    context_plan = governance.compile_context("PM", {
        "task_shape": "analysis", "surfaces": ["profit_diagnosis"],
        "risk": "high", "uncertainty": "low",
        "runtime_claim": False, "end_to_end_claim": False,
        "objective": "bind profit diagnosis workflow", "scope": "bounded profit diagnosis",
        "dirty_scope": [".claude/workflows/profit-diagnosis.js"],
        "acceptance_criteria": ["preserve canonical Context authority"],
        "hard_stops": ["no runtime or broker effect"], "baseline": source_baseline,
        "direct_interfaces": ["profit-diagnosis.js"],
        "previous_failure": "workflow accepted digest-only context",
        "claim_inputs": {"profit_priors": _digest(priors)},
        "task_prompt": task_prompt,
    })
    context_artifact = governance.materialize_context_artifact(context_plan)
    args = {
        "context_artifact": context_artifact,
        "baseline": baseline,
        "priors": priors,
        "priors_digest": _digest(priors),
    }
    script_template = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'agent', source);
const prompts = [];
const injectNull = __INJECT_NULL__;
const runtimeFact = __RUNTIME_FACT__;
const oversizedProbe = __OVERSIZED_PROBE__;
const consumption = { measurement_status: 'unavailable', unavailable_reason: 'harness' };
const agent = async (prompt, options) => {
  prompts.push({ prompt, label: options.label });
  if (injectNull && options.label === 'evidence:OPS') return null;
  if (options.label.startsWith('evidence:') || options.label.startsWith('evidence-relay:')) {
    const axis = options.label.split(':').at(-1);
    const unattested = runtimeFact && axis === 'OPS';
    return { schema_version: 'profit_evidence_fragment_v2', axis, work_status: 'DONE', summary: `${axis} done`, facts: [{ id: `${axis}-fact-1`, classification: unattested ? 'INFERENCE' : 'FACT', scope: unattested ? 'runtime' : 'source', evidence_ref: unattested ? null : 'ev-repo-authority', observation: `${axis} harness observation`, observed_at: '2026-07-11T12:00:00Z', freshness: 'fresh', limitation: 'source-only harness' }], gaps: [], consumption };
  }
  if (options.label.startsWith('probe:') || options.label.startsWith('probe-relay:')) {
    const axis = options.label.split(':').at(-1);
    const negative = oversizedProbe && axis === 'QC' ? 'Z'.repeat(2000000) : `${axis} searched with no supported move`;
    return { schema_version: 'profit_probe_fragment_v2', axis, work_status: 'DONE', verdict: 'NO_EVIDENCE', diagnoses: [], opportunities: [], evidence_refs: ['ev-repo-authority'], negative_search_summary: negative, next_experiments: [`repeat ${axis} after fresh evidence`], consumption };
  }
  const negative_results = ['QC', 'BB', 'IB', 'MIT', 'AI-E', 'EXT'].map(axis => ({ axis, searched: `${axis} searched with no supported move`, result: 'NO_EVIDENCE under current baseline and priors', next_review_condition: `repeat ${axis} after fresh evidence`, evidence_refs: ['ev-repo-authority'] }));
  return { schema_version: 'profit_map_v2', work_status: 'DONE', decision_ready: __MAP_READY__, top_moves: [], negative_results, coverage_debt: [], consumption };
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
(async () => {
  const result = await runner(__ARGS__, () => {}, () => {}, parallel, agent);
  console.log(JSON.stringify({ result, prompts }));
})().catch(error => { console.error(error); process.exit(1); });
"""

    def run(
        run_args: dict, *, map_ready: bool, null_first: bool = False,
        runtime_fact: bool = False, oversized_probe: bool = False,
    ) -> dict:
        script = (
            script_template.replace(
                "__WORKFLOW__",
                json.dumps(str(ROOT / ".claude/workflows/profit-diagnosis.js")),
            )
            .replace("__ARGS__", NODE_STDIN_ARGS)
            .replace("__MAP_READY__", "true" if map_ready else "false")
            .replace("__INJECT_NULL__", "true" if null_first else "false")
            .replace("__RUNTIME_FACT__", "true" if runtime_fact else "false")
            .replace("__OVERSIZED_PROBE__", "true" if oversized_probe else "false")
        )
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            input=json.dumps(run_args),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return {"_error": completed.stderr}
        return json.loads(completed.stdout)

    output = run(args, map_ready=True)
    oversized = run(args, map_ready=False, oversized_probe=True)
    assert "call map:PA final bound prompt exceeds" in oversized["_error"]
    assert governance.validate_workflow_call_manifest(
        output["result"]["call_manifest"],
        expected_task_contract_digest=context_artifact["task_contract_digest"],
        expected_context_artifact_digest=context_artifact["artifact_digest"],
    ) == []
    assert governance.validate_workflow_wave_record(
        output["result"]["workflow_wave_record"],
        output["result"]["call_manifest"],
        expected_task_contract_digest=context_artifact["task_contract_digest"],
        expected_context_artifact_digest=context_artifact["artifact_digest"],
    ) == []
    assert all(
        fragment["consumption"]["measurement_status"] == "unavailable"
        and fragment["producer_call_ref"]
        and fragment["producer_call_receipt_digest"]
        for fragment in output["result"]["role_fragments"]
    )
    retried = run(args, map_ready=True, null_first=True)["result"]
    ops_calls = [
        record for record in retried["call_manifest"]["records"]
        if record["node_id"] == "evidence:OPS"
    ]
    assert [record["returned_null"] for record in ops_calls] == [True, False]
    assert ops_calls[1]["retry_parent_call_id"] == ops_calls[0]["logical_call_id"]
    assert retried["workflow_wave_record"]["null_call_count"] == 1
    assert retried["workflow_wave_record"]["retry_call_count"] == 1
    assert retried["workflow_wave_record"]["final_null_node_count"] == 0
    unattested = run(args, map_ready=False, runtime_fact=True)["result"]
    assert {
        "kind": "evidence_fact", "id": "OPS:OPS-fact-1",
        "reason": "runtime observation requires platform/external-attested capture",
        "owner": "OPS",
    } in unattested["coverage_debt"]
    assert {
        "kind": "evidence_fact", "id": "OPS:fresh_fact",
        "reason": "no fresh source/data FACT with typed evidence_ref", "owner": "OPS",
    } in unattested["coverage_debt"]
    ops_fragment = next(
        item for item in unattested["role_fragments"] if item["node_id"] == "evidence:OPS"
    )
    assert ops_fragment["gate_verdict"] == "CONDITIONAL"
    assert ops_fragment["evidence_refs"] == [f"profit:priors:{args['priors_digest']}"]
    control = output["result"]["control_fragment"]["payload"]
    assert control["baseline_digest"] == _digest(baseline)
    assert control["hard_stops"] == ["no runtime or broker effect"]
    assert control["context_artifact_digest"] == context_artifact["artifact_digest"]
    assert control["budget_authority_digest"] == context_artifact["budget_authority_digest"]
    assert control["envelope"] == {
        "accounting_basis": "utf8_bytes_div4_planned_lower_bound_v1",
        "max_context_tokens_per_call": 480_000,
        "max_prompt_utf8_bytes_per_call": 1_919_996,
        "max_workflow_planned_input_tokens": 10_560_000,
        "max_unique_nodes": 20,
        "max_call_attempts": 22,
        "retry_budget": 2,
        "retry_capacity": 2,
        "estimated_tokens_per_evidence": 20_000,
        "estimated_tokens_per_probe": 24_000,
        "estimated_tokens_for_map": 30_000,
        "planned_input_tokens": 294_000,
        "planned_unique_nodes": 10,
        "planned_call_attempts": 12,
    }
    rendered_prompts = [item["prompt"] for item in output["prompts"]]
    assert all("[object Object]" not in prompt for prompt in rendered_prompts)
    assert any(_canonical(baseline) in prompt for prompt in rendered_prompts)
    assert any(_canonical(priors) in prompt for prompt in rendered_prompts)
    workflow_source = (ROOT / ".claude/workflows/profit-diagnosis.js").read_text()
    assert all(token in workflow_source for token in ("measurement_source", "telemetry_digest", "missing_metrics", "retry_count", "wall_time_ms", "rework_count"))
    assert "720000" not in workflow_source
    assert "maxAgents > 24" not in workflow_source
    assert "retryBudget > 4" not in workflow_source
    assert all(
        item["prompt"].startswith(context_artifact["shared_task_context_canonical"] + "\n\n")
        for item in output["prompts"]
    )

    def self_signed_artifact(mutate) -> dict:
        forged_artifact = deepcopy(context_artifact)
        forged_plan = json.loads(forged_artifact["canonical_plan"])
        mutate(forged_plan)
        forged_contract_digest = _digest(forged_plan["task_contract"])
        forged_plan["task_contract_digest"] = forged_contract_digest
        forged_artifact["task_contract_digest"] = forged_contract_digest
        forged_artifact["canonical_plan"] = _canonical(forged_plan)
        forged_artifact["artifact_digest"] = "sha256:" + hashlib.sha256(
            forged_artifact["canonical_plan"].encode("utf-8")
        ).hexdigest()
        return forged_artifact

    attacks = {
        "controller role": lambda plan: plan.__setitem__("role", "AI-E"),
        "profit surface": lambda plan: plan["task_contract"].__setitem__(
            "surfaces", []
        ),
        "omitted mandatory": lambda plan: plan["omitted_mandatory"].append(
            "hard_stops"
        ),
        "source producer": lambda plan: plan["sources"][0].__setitem__(
            "producer", "caller_rehash_v1"
        ),
        "source TTL": lambda plan: plan["sources"][0].__setitem__(
            "expires_at", "2099-01-01T00:00:00+00:00"
        ),
        "budget action": lambda plan: plan["budget"].__setitem__(
            "action", "use_quality_reserve"
            if plan["budget"]["action"] == "within_target"
            else "within_target"
        ),
    }
    for label, mutate in attacks.items():
        attacked = run(
            {**args, "context_artifact": self_signed_artifact(mutate)},
            map_ready=False,
        )
        assert "_error" in attacked, f"self-signed {label} reached agent calls"

    constrained = run({**args, "max_unique_nodes": 4}, map_ready=False)
    assert "caps must equal Context budget authority" in constrained["_error"]
