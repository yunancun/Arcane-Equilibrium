"""Cross-layer attacks that structural JSON validation alone cannot catch."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
import agent_governance_trust as trust  # noqa: E402
from agent_governance_capture import capture_repository  # noqa: E402
from agent_governance_capture_binding import collect_capture_evidence  # noqa: E402
from agent_governance_repository_changes import capture_repository_change  # noqa: E402
from agent_governance_trust import _acceptance_errors  # noqa: E402
SUPPORT_PATH = ROOT / "tests/structure/test_development_agent_governance.py"


def _support():
    spec = importlib.util.spec_from_file_location("governance_trust_support", SUPPORT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


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


def test_capture_binding_accepts_committed_change_endpoint_after_task_baseline(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "capture-binding-commit"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "binding@example.invalid")
    _git(repo, "config", "user.name", "Binding Test")
    (repo / "owned.py").write_text("before\n", encoding="utf-8")
    _git(repo, "add", "owned.py")
    _git(repo, "commit", "-qm", "fixture")
    baseline = capture_repository(["owned.py"], root=repo)
    (repo / "owned.py").write_text("after\n", encoding="utf-8")
    _git(repo, "add", "owned.py")
    _git(repo, "commit", "-qm", "owned commit")
    task_digest = "sha256:" + "a" * 64
    change = capture_repository_change(
        before=baseline, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1", scope=["owned.py"],
        owned_before=baseline, root=repo,
    )
    captured = collect_capture_evidence(
        [{
            "id": "change:implementation", "scope": "source",
            "kind": "repository_change_record_v1",
            "digest": change["record_digest"], "artifact": change,
        }],
        expected_scope=["owned.py"],
        expected_source_head=baseline["source_head"],
        expected_task_contract_digest=task_digest,
        expected_context_artifact_digest="sha256:" + "b" * 64,
        require_current_repository=False,
    )

    assert captured["errors"] == []
    assert captured["changes"] == {"change:implementation": change}


def test_refresh_rebinds_delayed_packet_to_new_context_generation_clock() -> None:
    support, governance, packet = _passing_packet()
    packet["adjudicated_at"] = "2000-01-01T00:00:00Z"

    support._refresh_standard_workflow_lineage(governance, packet)

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
        execution_attestation_verifier=support._test_execution_attestation_verifier(
            packet
        ),
        trusted_evaluated_at=adjudicated.astimezone(timezone.utc),
    ) == []


def test_trusted_clock_before_refreshed_context_generation_still_fails_closed() -> None:
    support, governance, packet = _passing_packet()
    plan = json.loads(packet["dispatch"]["context_artifact"]["canonical_plan"])
    rolled_back = min(
        datetime.fromisoformat(source["observed_at"].replace("Z", "+00:00"))
        for source in plan["sources"]
        if source.get("observed_at")
    ) - timedelta(microseconds=1)
    stale = deepcopy(packet)
    stale["adjudicated_at"] = rolled_back.isoformat().replace("+00:00", "Z")

    errors = governance.validate_closure(
        stale,
        execution_attestation_verifier=support._test_execution_attestation_verifier(
            stale
        ),
        trusted_evaluated_at=rolled_back.astimezone(timezone.utc),
    )

    assert any(
        "dispatch context artifact invalid" in error
        and "expired or not yet valid" in error
        for error in errors
    )
    assert any("authority claim is observed after adjudication" in error for error in errors)


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
            **governance.requested_execution_binding(governance.load_registry()),
            "model": governance.load_registry()["saved_workflow_model_policy"]["role_models"]["E2"],
            "effort": governance.load_registry()["saved_workflow_model_policy"]["role_efforts"]["E2"], "isolation": None,
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
            "admitted_caps": governance.execution_admitted_caps(budget_value),
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
            **governance.requested_execution_binding(governance.load_registry()),
            "model": governance.load_registry()["saved_workflow_model_policy"]["role_models"]["E2"],
            "effort": governance.load_registry()["saved_workflow_model_policy"]["role_efforts"]["E2"], "isolation": None,
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


def test_effect_receipt_cannot_substitute_a_reviewers_own_wave_result(
    monkeypatch,
) -> None:
    """PA/CC/E3 must cite their authenticated call result, not an effect."""

    monkeypatch.setattr(
        trust,
        "validate_role_fragment_producer",
        lambda *_args, **_kwargs: [],
    )
    fragment = {
        "node_id": "pa_design",
        "role": "PA",
        "gate_verdict": "PASS",
        "evidence_refs": ["effect:target-host"],
    }
    captures = {
        "repositories": {},
        "changes": {},
        "commands": {},
        "waves": {},
        "waves_by_id": {},
        "platform_attested": set(),
        "calls": {},
    }

    errors = trust._fragment_errors(
        {"pa_design": fragment},
        captures=captures,
        valid_effect_receipt_ids={"effect:target-host"},
        task_contract_digest="sha256:" + "a" * 64,
        context_artifact_digest="sha256:" + "b" * 64,
        specialized_surfaces=set(),
        effect_or_ops_nodes={"target_host_disposable_runtime_probe_adapter_v1"},
    )

    assert any("own authenticated workflow result" in error for error in errors)


def test_reviewer_fragment_accepts_its_authenticated_wave_owned_result(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        trust,
        "validate_role_fragment_producer",
        lambda *_args, **_kwargs: [],
    )
    fragment = {
        "node_id": "pa_design",
        "role": "PA",
        "gate_verdict": "PASS",
        "evidence_refs": ["s1-workflow-wave"],
    }
    wave = {
        "result_fragment_digests": {
            "pa_design": trust.canonical_digest(fragment),
        },
    }
    captures = {
        "repositories": {},
        "changes": {},
        "commands": {},
        "waves": {"sha256:" + "c" * 64: wave},
        "waves_by_id": {"s1-workflow-wave": wave},
        "platform_attested": set(),
        "calls": {},
    }

    errors = trust._fragment_errors(
        {"pa_design": fragment},
        captures=captures,
        valid_effect_receipt_ids={"effect:target-host"},
        task_contract_digest="sha256:" + "a" * 64,
        context_artifact_digest="sha256:" + "b" * 64,
        specialized_surfaces=set(),
        effect_or_ops_nodes={"target_host_disposable_runtime_probe_adapter_v1"},
    )

    assert errors == []


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
