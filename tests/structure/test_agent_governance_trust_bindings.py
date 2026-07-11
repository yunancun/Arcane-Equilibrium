"""Cross-layer attacks that structural JSON validation alone cannot catch."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
from agent_governance_trust import _acceptance_errors  # noqa: E402
SUPPORT_PATH = ROOT / "tests/structure/test_development_agent_governance.py"


def _support():
    spec = importlib.util.spec_from_file_location("governance_trust_support", SUPPORT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _passing_packet():
    support = _support()
    governance = support._load_module()
    packet = support._valid_failed_review_closure()
    packet["gate_verdict"] = "PASS"
    packet["acceptance"][0]["status"] = "PASS"
    packet["role_fragments"][0].update(gate_verdict="PASS", concerns=[])
    support._refresh_standard_workflow_lineage(governance, packet)
    assert governance.validate_closure(
        packet,
        execution_attestation_verifier=support._test_execution_attestation_verifier(
            packet
        ),
    ) == []
    return support, governance, packet


def test_self_rehashed_authority_cannot_replace_pinned_source() -> None:
    _, governance, packet = _passing_packet()
    attacked = deepcopy(packet)
    claim = attacked["authority_refs"][0]
    claim["source_ref"] = "context:README.md"
    claim["digest"] = "sha256:" + "f" * 64
    claim["claim_digest"] = governance.authority_claim_digest(claim)

    errors = governance.validate_closure(attacked)

    assert any("exact pinned context source" in error for error in errors)

    semantic_swap = deepcopy(packet)
    claim = semantic_swap["authority_refs"][0]
    claim["value"] = {"live_mainnet_authorized": True}
    claim["claim_digest"] = governance.authority_claim_digest(claim)
    assert any(
        "deterministic identity projection" in error
        for error in governance.validate_closure(semantic_swap)
    )


def test_role_or_result_substitution_breaks_call_binding() -> None:
    _, governance, packet = _passing_packet()
    result_swap = deepcopy(packet)
    result_swap["role_fragments"][0]["summary"] = "substituted after the call"
    assert any(
        "projection differs from producer call result" in error
        for error in governance.validate_closure(result_swap)
    )

    role_swap = deepcopy(packet)
    fragment = role_swap["role_fragments"][0]
    fragment["role"] = "E2"
    fragment["payload_kind"] = governance.load_registry()["roles"]["E2"]["payload_kind"]
    assert any(
        "logical_role differs from expected role" in error
        for error in governance.validate_closure(role_swap)
    )


def test_manifest_wave_or_direct_capture_cannot_disappear() -> None:
    _, governance, packet = _passing_packet()
    missing_wave = deepcopy(packet)
    missing_wave["evidence"] = [
        item for item in missing_wave["evidence"]
        if item["kind"] != "workflow_wave_record_v1"
    ]
    errors = governance.validate_closure(missing_wave)
    assert any("missing call manifest" in error or "complete workflow wave" in error for error in errors)

    generic_source = deepcopy(packet)
    source_index = next(
        index for index, item in enumerate(generic_source["evidence"])
        if item["id"] == "ev-repository"
    )
    generic_source["evidence"][source_index] = {
        "id": "ev-repository", "scope": "source", "kind": "generic_digest",
        "digest": "sha256:" + "a" * 64,
    }
    errors = governance.validate_closure(generic_source)
    assert any("source/test PASS requires repository or command capture" in error for error in errors)
    assert any("lacks direct captured" in error for error in errors)


def test_rehashed_wave_cannot_hide_retry_or_consumption() -> None:
    support, governance, packet = _passing_packet()
    undercount = deepcopy(packet)
    undercount["consumption"]["planned_tokens"] += 1
    assert "closure orchestrator consumption planned_tokens differs from wave ledger" in (
        governance.validate_closure(undercount)
    )

    hidden_retry = deepcopy(packet)
    wrapper = next(
        item for item in hidden_retry["evidence"]
        if item["kind"] == "workflow_wave_record_v1"
    )
    wave = wrapper["artifact"]
    wave["retry_call_count"] = 1
    unsigned = {key: value for key, value in wave.items() if key != "record_digest"}
    wave["record_digest"] = support._canonical_digest(unsigned)
    wrapper["digest"] = wave["record_digest"]

    errors = governance.validate_closure(hidden_retry)

    assert any("retry count differs from manifest" in error for error in errors)


def test_ghost_wave_cannot_be_omitted_from_accounting_or_dispatch() -> None:
    support, governance, packet = _passing_packet()
    artifact = packet["dispatch"]["context_artifact"]
    plan = __import__("json").loads(artifact["canonical_plan"])
    task = plan["task_contract"]
    judgment = {
        "work_status": "DONE", "gate_verdict": "PASS", "classification": "FACT",
        "confidence": "high", "summary": "ghost", "evidence_refs": ["ev-repository"],
        "concerns": [], "next_action": {"owner": "PM", "action": "close"},
        "payload": {},
    }
    workflow_digest = support._canonical_digest({"workflow": "ghost"})
    call = governance.build_controller_workflow_call_record(
        workflow_contract_digest=workflow_digest,
        logical_call_id="ghost:ghost-review:attempt:1", node_id="ghost-review",
        payload_kind=governance.load_registry()["roles"]["E2"]["payload_kind"],
        attempt=1, retry_parent_call_id=None, phase="Wave", label="ghost-review",
        requested={
            "logical_role": "E2", "platform": "claude_saved_workflow",
            "platform_requested_agent": "E2",
            "native_binding": {
                "logical_role": "E2", "native_agent": "E2",
                "node_class": "verification", "permission": "read_only",
            },
            "model": None,
            "effort": None, "isolation": None,
            "node_class": "verification", "permission": "read_only",
        },
        prompt_digest=support._canonical_digest("ghost"),
        context_artifact_digest=artifact["artifact_digest"],
        task_contract_digest=artifact["task_contract_digest"],
        dirty_scope_digest=support._canonical_digest(task["dirty_scope"]),
        focus_digest=support._canonical_digest(task["focus"]),
        compiler_input_tokens_lower_bound=5_000,
        admitted_input_tokens_lower_bound=5_000,
        response_schema_digest=support._canonical_digest({"schema": "judgment"}),
        started_at=packet["adjudicated_at"], ended_at=packet["adjudicated_at"],
        returned_null=False, parsed_result_digest=support._canonical_digest(judgment),
    )
    manifest = governance.build_workflow_call_manifest(
        [call], workflow_contract_digest=workflow_digest
    )
    budget_value = __import__("json").loads(artifact["budget_authority_canonical"])
    wave = governance.build_workflow_wave_record(
        manifest=manifest,
        admitted_tasks=[
                {
                    "node_id": "ghost-review", "role": "E2",
                    "native_agent": "E2", "node_class": "verification",
                    "permission": "read_only",
                    "payload_kind": call["payload_kind"],
                "task_contract_digest": artifact["task_contract_digest"],
                "context_artifact_digest": artifact["artifact_digest"],
                "description_digest": support._canonical_digest("ghost"),
                "base_prompt_digest": call["prompt_digest"],
                "requested": call["requested"],
                "dirty_scope": sorted(task["dirty_scope"]),
                "dirty_scope_digest": support._canonical_digest(sorted(task["dirty_scope"])),
                "focus": task["focus"],
                "focus_digest": support._canonical_digest(task["focus"]),
                "compiler_estimated_input_tokens": 5_000,
                "admitted_input_tokens_lower_bound": 5_000,
            }
        ],
        budget_authority={
            "authority_digest": artifact["budget_authority_digest"],
            "authority_canonical": artifact["budget_authority_canonical"],
            "admitted_caps": {
                field: budget_value[field] for field in (
                    "max_context_tokens_per_call",
                    "max_prompt_utf8_bytes_per_call",
                    "max_workflow_planned_input_tokens",
                    "max_unique_nodes", "max_call_attempts", "retry_budget",
                )
            },
        },
        result_fragment_digests={"ghost-review": support._canonical_digest(judgment)},
    )
    packet["evidence"].extend(
        [
            {
                "id": "ev-ghost-manifest", "scope": "data",
                "kind": "workflow_call_manifest_v1", "digest": manifest["manifest_digest"],
                "artifact": manifest,
            },
            {
                "id": "ev-ghost-wave", "scope": "data",
                "kind": "workflow_wave_record_v1", "digest": wave["record_digest"],
                "artifact": wave,
            },
        ]
    )

    errors = governance.validate_closure(packet)

    assert "closure orchestrator consumption wave refs must exactly cover every captured wave" in errors
    assert any("ghost-review is not closure/dispatch bound" in error for error in errors)


def test_high_cost_standalone_call_cannot_bypass_manifest_wave_accounting() -> None:
    support, governance, packet = _passing_packet()
    artifact = packet["dispatch"]["context_artifact"]
    plan = __import__("json").loads(artifact["canonical_plan"])
    task = plan["task_contract"]
    result = {
        "work_status": "DONE", "gate_verdict": "PASS", "classification": "FACT",
        "confidence": "high", "summary": "unaccounted review",
        "evidence_refs": ["ev-repository"], "concerns": [],
        "next_action": {"owner": "PM", "action": "close"}, "payload": {},
    }
    call = governance.build_controller_workflow_call_record(
        workflow_contract_digest=support._canonical_digest({"workflow": "orphan"}),
        logical_call_id="orphan:review:attempt:1", node_id="orphan-review",
        payload_kind=governance.load_registry()["roles"]["E2"]["payload_kind"],
        attempt=1, retry_parent_call_id=None, phase="Wave", label="orphan-review",
        requested={
            "logical_role": "E2", "platform": "claude_saved_workflow",
            "platform_requested_agent": "E2",
            "native_binding": {
                "logical_role": "E2", "native_agent": "E2",
                "node_class": "verification", "permission": "read_only",
            },
            "model": None,
            "effort": None, "isolation": None,
            "node_class": "verification", "permission": "read_only",
        },
        prompt_digest=support._canonical_digest("orphan review"),
        context_artifact_digest=artifact["artifact_digest"],
        task_contract_digest=artifact["task_contract_digest"],
        dirty_scope_digest=support._canonical_digest(task["dirty_scope"]),
        focus_digest=support._canonical_digest(task["focus"]),
        compiler_input_tokens_lower_bound=500_001,
        admitted_input_tokens_lower_bound=500_001,
        response_schema_digest=support._canonical_digest({"schema": "judgment"}),
        started_at=packet["adjudicated_at"], ended_at=packet["adjudicated_at"],
        returned_null=False, parsed_result_digest=support._canonical_digest(result),
    )
    packet["evidence"].append(
        {
            "id": "ev-orphan-call", "scope": "data",
            "kind": "workflow_call_record_v1", "digest": call["record_digest"],
            "artifact": call,
        }
    )

    errors = governance.validate_closure(packet)

    assert any(
        "workflow call records lack a complete manifest/wave lineage" in error
        for error in errors
    )


def test_unit_or_usage_telemetry_cannot_substitute_runtime_or_e2e_outcome() -> None:
    packet = {
        "acceptance": [
            {"criterion": "observable business outcome", "status": "PASS", "evidence_refs": ["ev-unit"]}
        ]
    }
    fragments = {
        "e2e": {
            "gate_verdict": "PASS", "classification": "FACT", "confidence": "high",
            "evidence_refs": ["ev-unit"],
        }
    }
    captures = {
        "repositories": {}, "changes": {}, "commands": {"ev-unit": {}},
        "platform_attested": {"ev-unit"},
        "runtime_attested": set(), "outcome_attested": set(),
    }
    e2e_errors = _acceptance_errors(
        packet,
        captures=captures,
        fragments_by_node=fragments,
        expected_route={"task_facts": {"end_to_end_claim": True, "runtime_claim": False}},
    )
    runtime_errors = _acceptance_errors(
        packet,
        captures=captures,
        fragments_by_node=fragments,
        expected_route={"task_facts": {"end_to_end_claim": False, "runtime_claim": True}},
    )

    assert any("end-to-end PASS requires" in error for error in e2e_errors)
    assert any("runtime PASS requires" in error for error in runtime_errors)


def test_e4_real_local_command_capture_is_closure_reachable() -> None:
    support, governance, packet = _passing_packet()
    task_digest = packet["dispatch"]["context_artifact"]["task_contract_digest"]
    node_id = "admitted-local-regression"
    command = "python3 -m pytest tests/structure/test_agent_governance_capture.py -q"
    capture = governance.capture_command(
        role_id="E4",
        node_id=node_id,
        task_contract_digest=task_digest,
        command=command,
        scope=packet["dispatch"]["task_facts"]["dirty_scope"],
    )
    packet["evidence"].append(
        {
            "id": "ev-e4-command", "scope": "test",
            "kind": "command_capture_v1", "digest": capture["record_digest"],
            "artifact": capture,
        }
    )
    packet["checks"] = [
        {
            "id": "check-e4-real", "status": "EXECUTED", "command": command,
            "signature": capture["record_digest"],
            "evidence_ref": "ev-e4-command",
            "command_capture_ref": "ev-e4-command",
            "executed_at": capture["completed_at"],
        }
    ]
    packet["dispatch"]["admitted_role_nodes"] = [
        {
            "node_id": node_id, "role": "E4", "node_class": "verification",
            **governance.native_agent_binding("E4", "verification"),
            "requires": ["constitutional_gate"], "path_scope": [],
            "reason": "prove the local E4 test Adapter end to end",
            "result_binding": "role_fragment",
        }
    ]
    route = governance.route_task(packet["dispatch"]["task_facts"])
    packet["skipped_roles"] = [
        item for item in route["skipped"] if item["role"] != "E4"
    ]
    packet["role_fragments"].append(
        {
            "schema_version": "role_fragment_v1",
            "id": "fragment:e4-real", "node_id": node_id, "role": "E4",
            "task_contract_digest": task_digest,
            "context_artifact_digest": packet["dispatch"]["context_artifact"]["artifact_digest"],
            "producer_record_kind": "workflow_call_record_v1",
            "producer_call_ref": "pending", "producer_call_receipt_digest": "sha256:" + "0" * 64,
            "work_status": "DONE", "gate_verdict": "PASS",
            "classification": "FACT", "confidence": "high",
            "summary": "real local regression passed",
            "evidence_refs": ["ev-e4-command"], "concerns": [],
            "next_action": {"owner": "PM", "action": "consume captured regression"},
            "consumption": {
                "measurement_status": "unavailable",
                "unavailable_reason": "platform usage telemetry unavailable",
            },
            "payload_kind": governance.load_registry()["roles"]["E4"]["payload_kind"],
            "payload": {"command_capture_ref": "ev-e4-command"},
        }
    )
    support._refresh_standard_workflow_lineage(governance, packet)

    assert governance.validate_closure(
        packet,
        execution_attestation_verifier=support._test_execution_attestation_verifier(
            packet
        ),
    ) == []

    semantic_swap = deepcopy(packet)
    wrapper = next(
        item for item in semantic_swap["evidence"]
        if item["id"] == "ev-e4-command"
    )
    record = wrapper["artifact"]
    forged_output = b"substituted semantic test output\n"
    record["stdout"] = {
        "encoding": "base64",
        "content": __import__("base64").b64encode(forged_output).decode("ascii"),
        "bytes": len(forged_output),
        "digest": "sha256:" + __import__("hashlib").sha256(forged_output).hexdigest(),
    }
    record["record_digest"] = support._canonical_digest(
        {key: value for key, value in record.items() if key != "record_digest"}
    )
    wrapper["digest"] = record["record_digest"]
    semantic_swap["checks"][0]["signature"] = record["record_digest"]

    assert any(
        "command capture output does not reproduce under its trusted replay contract" in error
        for error in governance.validate_closure(semantic_swap)
    )
