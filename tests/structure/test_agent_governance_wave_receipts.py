from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
sys.path.insert(0, str(HELPERS))

import agent_governance_workflow_receipts as workflow_receipts  # noqa: E402
from agent_governance_context import capture_repository_baseline  # noqa: E402
from agent_governance_execution import (  # noqa: E402
    compile_context,
    materialize_context_artifact,
    route_task,
)
from agent_governance_registry import load_registry  # noqa: E402
from agent_governance_execution_policy import (  # noqa: E402
    requested_execution_binding,
    surface_profile_binding,
)
from agent_governance_execution_dag import (  # noqa: E402
    compile_context_execution_dag_binding,
    delegated_execution_projection,
    non_call_controller_node_ids,
)
from agent_governance_workflow_receipts import (  # noqa: E402
    build_workflow_wave_record,
    canonical_digest,
    validate_workflow_call_manifest,
    validate_workflow_wave_record,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


def _wave_args(
    tmp_path: Path,
    *,
    risk: str = "low",
    node_count: int = 2,
    independent: bool = False,
) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "wave-test@example.invalid")
    _git(repo, "config", "user.name", "Wave Test")
    (repo / "AGENTS.md").write_text(
        "Wave fixture entry rules.\n",
        encoding="utf-8",
    )
    (repo / "CLAUDE.md").write_text(
        "# Product Boundary\n"
        "Wave fixture product boundary.\n\n"
        "# Root Principles\n"
        "Wave fixture root principles.\n\n"
        "# Hard Boundaries\n"
        "Wave fixture hard boundaries.\n",
        encoding="utf-8",
    )
    (repo / "local.md").write_text("controller-owned wave input\n", encoding="utf-8")
    (repo / "docs" / "_indexes").mkdir(parents=True)
    (repo / "docs" / "README.md").write_text(
        "wave fixture documentation\n",
        encoding="utf-8",
    )
    (repo / "docs" / "_indexes" / "wave.md").write_text(
        "wave fixture index\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    # Saved workflows admit only the repository-canonical Registry generation.
    # The fixture therefore provides the canonical pack sources instead of
    # self-signing a test-only Registry variant.
    registry = load_registry()
    facts = {
        "task_shape": "query" if risk == "low" else "review",
        "surfaces": ["governance"],
        "risk": risk,
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "objective": "verify controller-owned wave call receipts",
        "scope": ["local.md"],
        "dirty_scope": ["local.md"],
        "focus": "call identity and consumption truth",
        "acceptance_criteria": ["every agent call is content-addressed"],
        "hard_stops": ["no runtime effect"],
        "baseline": capture_repository_baseline(repo),
        "direct_interfaces": [] if risk == "low" else ["agent-wave"],
        "previous_failure": "model output could spoof controller identity",
        "task_prompt": "Review immutable call binding for the admitted node.",
    }
    routed = route_task(facts, registry=registry)
    execution_dag, projection_errors = delegated_execution_projection(
        routed["required_role_nodes"],
        [],
        excluded_nodes=non_call_controller_node_ids(facts),
        registry=registry,
    )
    assert projection_errors == []
    assert len(execution_dag) <= node_count
    for index in range(len(execution_dag), node_count):
        execution_dag.append({
            "node_id": f"node-{chr(ord('a') + index)}",
            "role": "E2",
            "native_agent": "E2",
            "requires": (
                []
                if independent or not execution_dag
                else [execution_dag[-1]["node_id"]]
            ),
            "node_class": "verification",
            "permission": "read_only",
        })
    task_specs = [
        {
            "node_id": task["node_id"],
            "payload_kind": registry["roles"][task["role"]]["payload_kind"],
            "agentType": task["role"],
            "native_agent": task["native_agent"],
            "requires": task["requires"],
            "node_class": task["node_class"],
            "permission": task["permission"],
            "prompt": "Review immutable call binding for the admitted node.",
            "description": f"wave-receipt-{task['node_id']}",
        }
        for task in execution_dag
    ]
    plan = compile_context(
        "E2",
        facts,
        registry,
        repo,
        execution_dag=execution_dag,
    )
    artifacts_by_role = {
        "E2": materialize_context_artifact(plan, registry),
    }
    for role in {task["role"] for task in execution_dag} - {"E2"}:
        role_plan = compile_context(
            role,
            facts,
            registry,
            repo,
            execution_dag=execution_dag,
        )
        assert (
            role_plan["budget"]["authority_digest"]
            == plan["budget"]["authority_digest"]
        )
        artifacts_by_role[role] = materialize_context_artifact(
            role_plan,
            registry,
        )
    tasks = [
        {**task, "contextArtifact": artifacts_by_role[task["agentType"]]}
        for task in task_specs
    ]
    model_policy = load_registry()["saved_workflow_model_policy"]
    if len(tasks) > 1:
        tasks[1].update({
            "model": model_policy["model"],
            "effort": model_policy["role_efforts"][tasks[1]["agentType"]],
            "isolation": "worktree",
        })
    dag_core = {
        "schema_version": "agent_wave_execution_dag_v1",
        "nodes": execution_dag,
    }
    authority = plan["budget"]["authority"]
    return {
        "tasks": tasks,
        "dag_digest": canonical_digest(dag_core),
        "budget": {
            "max_unique_nodes": authority["max_unique_nodes"],
            "max_call_attempts": authority["max_call_attempts"],
            "retry_budget": 1,
            "max_workflow_planned_input_tokens": authority["max_workflow_planned_input_tokens"],
            "authority_digest": plan["budget"]["authority_digest"],
        },
    }


def _run_harness(wave_args: dict) -> dict:
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'agent', source);
const baseArgs = __ARGS__;
const retryNode = baseArgs.tasks[0].node_id;
const parallel = async jobs => Promise.all(jobs.map(job => job()));
const canonical = value => {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  throw new Error('non-canonical value');
};
const digest = async value => {
  const bytes = new TextEncoder().encode(canonical(value));
  const hash = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return `sha256:${[...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`;
};
const judgment = option => ({
  work_status: 'DONE', gate_verdict: 'PASS', classification: 'FACT', confidence: 'high',
  summary: `reviewed ${option.label}`, evidence_refs: [`evidence:${option.label}`], concerns: [],
  next_action: { owner: 'PM', action: 'merge controller-bound fragment' },
  payload: { observed_label: option.label },
});
async function execute(mode) {
  const seenSchemas = [];
  const seenCalls = [];
  let activeCalls = 0;
  let peakCalls = 0;
  const agent = async (_prompt, option) => {
    seenSchemas.push(option.schema);
    seenCalls.push(option.label);
    activeCalls += 1;
    peakCalls = Math.max(peakCalls, activeCalls);
    await Promise.resolve();
    let value = judgment(option);
    if (mode === 'blocked' && option.label.includes(retryNode)) value = null;
    else if (mode === 'retry' && option.phase === 'Wave' && option.label === retryNode) value = null;
    else if (mode === 'identity') value = { ...value, role: 'spoofed-role' };
    else if (mode === 'consumption') value = { ...value, consumption: { measurement_status: 'measured', input_tokens: 1 } };
    activeCalls -= 1;
    return value;
  };
  try {
    const result = await runner(JSON.parse(JSON.stringify(baseArgs)), () => {}, () => {}, parallel, agent);
    return { ok: true, result, seenSchemas, seenCalls, peakCalls };
  } catch (error) {
    return { ok: false, error: String(error.message || error), seenSchemas, seenCalls, peakCalls };
  }
}
(async () => {
  const retry = await execute('retry');
  const blocked = await execute('blocked');
  const identity = await execute('identity');
  const consumption = await execute('consumption');
  if (!retry.ok) {
    console.log(JSON.stringify({ retry, blocked, identity, consumption }));
    return;
  }
  const records = retry.result.call_manifest.records;
  const recordChecks = await Promise.all(records.map(async record => {
    const { record_digest, ...core } = record;
    return (await digest(core)) === record_digest;
  }));
  const { manifest_digest, ...manifestCore } = retry.result.call_manifest;
  const { record_digest: waveDigest, ...waveCore } = retry.result.wave_record;
  const tampered = JSON.parse(JSON.stringify(records[0]));
  tampered.label += ':tampered';
  const tamperedClaim = tampered.record_digest;
  delete tampered.record_digest;
  const fragmentChecks = {};
  for (const [node, fragment] of Object.entries(retry.result.results)) {
    fragmentChecks[node] = (await digest(fragment)) === retry.result.wave_record.result_fragment_digests[node];
  }
  const judgmentFields = ['work_status', 'gate_verdict', 'classification', 'confidence', 'summary', 'evidence_refs', 'concerns', 'next_action', 'payload'];
  const producerChecks = {};
  for (const [node, fragment] of Object.entries(retry.result.results)) {
    const producer = records.find(record => record.logical_call_id === fragment.producer_call_ref);
    const projected = Object.fromEntries(judgmentFields.map(field => [field, fragment[field]]));
    producerChecks[node] = Boolean(
      producer && producer.record_digest === fragment.producer_call_receipt_digest &&
      producer.parsed_result_digest === await digest(projected)
    );
  }
  console.log(JSON.stringify({
    retry,
    blocked,
    identity,
    consumption,
    integrity: {
      workflow_contract_check: (await digest(retry.result.workflow_contract)) === retry.result.workflow_contract_digest,
      record_checks: recordChecks,
      manifest_check: (await digest(manifestCore)) === manifest_digest,
      wave_check: (await digest(waveCore)) === waveDigest,
      tamper_detected: (await digest(tampered)) !== tamperedClaim,
      fragment_checks: fragmentChecks,
      producer_checks: producerChecks,
    },
  }));
})().catch(error => { console.error(error); process.exit(1); });
""".replace("__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/agent-wave.js"))).replace(
        "__ARGS__", json.dumps(wave_args)
    )
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _python_wave_kwargs(result: dict) -> dict:
    wave = result["wave_record"]
    return {
        "manifest": result["call_manifest"],
        "admitted_tasks": wave["admitted_tasks"],
        "budget_authority": wave["budget_authority"],
        "result_fragment_digests": wave["result_fragment_digests"],
        "coverage_debt": wave["coverage_debt"],
        "accounting_boundary": wave["accounting_boundary"],
    }


def test_python_wave_builder_supplies_registry_surface_to_structural_assembler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_harness(_wave_args(tmp_path))["retry"]["result"]
    canonical_surface = surface_profile_binding(
        "claude_saved_workflow_v1",
        load_registry(),
    )
    assembled_profiles: list[dict | None] = []
    assembled_event_counts: list[int] = []
    real_assemble = (
        workflow_receipts._assemble_structural_execution_event_ledger
    )

    def record_assembly(*args, **kwargs):
        assembled_profiles.append(deepcopy(kwargs.get("surface_profile")))
        assembled_event_counts.append(len(args[2]))
        return real_assemble(*args, **kwargs)

    monkeypatch.setattr(
        workflow_receipts,
        "_assemble_structural_execution_event_ledger",
        record_assembly,
    )

    wave = build_workflow_wave_record(**_python_wave_kwargs(result))

    assert assembled_profiles == [
        canonical_surface["profile"]
    ]
    assert assembled_event_counts == [
        1 + len(result["call_manifest"]["records"])
    ]
    assert (
        wave["execution_event_ledger"]["surface_profile_digest"]
        == canonical_surface["digest"]
    )
    assert validate_workflow_wave_record(wave, result["call_manifest"]) == []


def test_wave_validator_exactly_binds_context_execution_dag(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path)
    context_plan = json.loads(
        wave_args["tasks"][0]["contextArtifact"]["canonical_plan"]
    )
    result = _run_harness(wave_args)["retry"]["result"]
    wave = result["wave_record"]
    manifest = result["call_manifest"]
    binding = context_plan["execution_dag_binding"]

    assert validate_workflow_wave_record(
        wave,
        manifest,
        expected_execution_dag_binding=binding,
    ) == []

    smaller_binding = compile_context_execution_dag_binding(
        binding["nodes"][:-1],
    )
    errors = validate_workflow_wave_record(
        wave,
        manifest,
        expected_execution_dag_binding=smaller_binding,
    )
    assert any(
        "admitted task core differs from Context execution DAG binding" in error
        for error in errors
    )
    assert any(
        "dag_digest differs from Context execution DAG binding" in error
        for error in errors
    )


def test_python_wave_receipt_rebuild_is_deterministic_and_structural_only(
    tmp_path: Path,
) -> None:
    result = _run_harness(_wave_args(tmp_path))["retry"]["result"]
    kwargs = _python_wave_kwargs(result)

    first = build_workflow_wave_record(**kwargs)
    rebuilt = build_workflow_wave_record(**kwargs)

    assert rebuilt == first
    assert rebuilt["record_digest"] == first["record_digest"]


def test_python_wave_builder_rejects_invalid_manifest_before_assembly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_harness(_wave_args(tmp_path))["retry"]["result"]
    forged_manifest = deepcopy(result["call_manifest"])
    generic_surface = surface_profile_binding("generic_host_v1", load_registry())
    requested = forged_manifest["records"][0]["requested"]
    requested["surface_profile_id"] = "generic_host_v1"
    requested["surface_profile_digest"] = generic_surface["digest"]
    record = forged_manifest["records"][0]
    record["record_digest"] = canonical_digest(
        {key: value for key, value in record.items() if key != "record_digest"}
    )
    forged_manifest["manifest_digest"] = canonical_digest(
        {
            key: value
            for key, value in forged_manifest.items()
            if key != "manifest_digest"
        }
    )
    assemblies = 0

    def reject_assembly(*args, **kwargs):
        nonlocal assemblies
        assemblies += 1
        raise AssertionError("invalid manifest reached receipt assembly")

    monkeypatch.setattr(
        workflow_receipts,
        "_assemble_structural_execution_event_ledger",
        reject_assembly,
    )

    with pytest.raises(ValueError, match="invalid workflow call manifest"):
        build_workflow_wave_record(
            **{
                **_python_wave_kwargs(result),
                "manifest": forged_manifest,
            }
        )

    assert assemblies == 0


def test_wave_controller_owns_identity_and_records_every_retry(tmp_path: Path) -> None:
    wave_args = _wave_args(tmp_path)
    outcome = _run_harness(wave_args)
    retry = outcome["retry"]
    assert retry["ok"] is True
    result = retry["result"]
    assert result["schema_version"] == "agent_wave_result_v3"

    records = result["call_manifest"]["records"]
    assert len(records) == 3
    assert len({record["logical_call_id"] for record in records}) == 3
    first = next(
        record
        for record in records
        if record["logical_call_id"] == "agent-wave:node-a:attempt:1"
    )
    retried = next(record for record in records if record["attempt"] == 2)
    assert first["returned_null"] is True
    assert retried["retry_parent_call_id"] == first["logical_call_id"]
    assert retried["logical_call_id"] == "agent-wave:node-a:attempt:2"
    assert retried["phase"] == "Retry"
    assert retry["seenCalls"] == ["node-a", "relay:node-a", "node-b"]
    assert all(record["schema_version"] == "workflow_call_record_v1" for record in records)
    assert all(record["started_at"] <= record["ended_at"] for record in records)
    assert all(record["node_id"] in {"node-a", "node-b"} for record in records)
    assert [record["node_id"] for record in records] == ["node-a", "node-a", "node-b"]
    assert [record["topological_wave"] for record in records] == [0, 0, 1]
    assert first["requires"] == [] and first["producer_generation"] == {}
    node_b = next(record for record in records if "node-b" in record["logical_call_id"])
    assert node_b["requires"] == ["node-a"]
    assert node_b["producer_generation"] == {"node-a": retried["record_digest"]}
    assert all(record["payload_kind"] == "review_fragment_v1" for record in records)
    for digest_field in (
        "workflow_contract_digest",
        "prompt_digest",
        "context_artifact_digest",
        "task_contract_digest",
        "response_schema_digest",
    ):
        assert all(record[digest_field].startswith("sha256:") for record in records)
    assert all(
        record["requested"]
        == {
            "logical_role": "E2", "platform": "claude_saved_workflow",
            "platform_requested_agent": "E2",
            "native_binding": {"logical_role": "E2", "native_agent": "E2", "node_class": "verification", "permission": "read_only"},
            **requested_execution_binding(load_registry()),
            "model": load_registry()["saved_workflow_model_policy"]["model"],
            "effort": load_registry()["saved_workflow_model_policy"]["role_efforts"]["E2"],
            "isolation": None,
            "node_class": "verification", "permission": "read_only",
        }
        for record in records
        if "node-a" in record["logical_call_id"]
    )
    assert node_b["requested"] == {
        "logical_role": "E2", "platform": "claude_saved_workflow",
        "platform_requested_agent": "E2",
        "native_binding": {"logical_role": "E2", "native_agent": "E2", "node_class": "verification", "permission": "read_only"},
        **requested_execution_binding(load_registry()),
        "model": load_registry()["saved_workflow_model_policy"]["model"],
        "effort": load_registry()["saved_workflow_model_policy"]["role_efforts"]["E2"],
        "isolation": "worktree",
        "node_class": "verification",
        "permission": "read_only",
    }
    assert all(record["dirty_scope_digest"].startswith("sha256:") for record in records)
    assert all(record["focus_digest"].startswith("sha256:") for record in records)

    wave = result["wave_record"]
    assert wave["schema_version"] == "workflow_wave_record_v1"
    assert wave["first_attempt_call_count"] == 2
    assert wave["retry_call_count"] == 1
    assert wave["null_call_count"] == 1
    assert wave["final_null_node_count"] == 0
    assert [
        event["outcome"]
        for event in wave["execution_event_ledger"]["events"]
    ] == ["completed", "null", "completed", "completed"]
    assert wave["coverage_debt"] == []
    assert wave["dag_digest"] == wave_args["dag_digest"]
    assert wave["execution_waves"] == [["node-a"], ["node-b"]]
    assert wave["compiler_planned_input_tokens_lower_bound"] == sum(
        task["compiler_estimated_input_tokens"] for task in wave["admitted_tasks"]
    )
    assert wave["admitted_planned_input_tokens_lower_bound"] == sum(
        task["admitted_input_tokens_lower_bound"] for task in wave["admitted_tasks"]
    )
    retry_record = next(record for record in records if record["attempt"] == 2)
    assert wave["scheduled_call_compiler_input_tokens_lower_bound"] == (
        wave["compiler_planned_input_tokens_lower_bound"]
        + retry_record["compiler_input_tokens_lower_bound"]
    )
    assert wave["scheduled_call_admitted_input_tokens_lower_bound"] == (
        wave["admitted_planned_input_tokens_lower_bound"]
        + retry_record["admitted_input_tokens_lower_bound"]
    )
    assert wave["accounting_boundary"]["controller_overhead_status"] == "unavailable"
    assert all(task["dirty_scope"] == ["local.md"] for task in wave["admitted_tasks"])
    assert all(task["focus"] == "call identity and consumption truth" for task in wave["admitted_tasks"])
    assert [task["requires"] for task in wave["admitted_tasks"]] == [[], ["node-a"]]
    assert validate_workflow_call_manifest(result["call_manifest"]) == []
    assert validate_workflow_wave_record(wave, result["call_manifest"]) == []

    for node, fragment in result["results"].items():
        assert fragment["id"] == f"agent-wave:{node}"
        assert fragment["node_id"] == node
        assert fragment["role"] == "E2"
        assert fragment["payload_kind"] == "review_fragment_v1"
        assert fragment["context_artifact_digest"] == result["context_artifact_digests"][node]
        assert fragment["producer_record_kind"] == "workflow_call_record_v1"
        assert fragment["consumption"] == {
            "measurement_status": "unavailable",
            "unavailable_reason": "agent-wave platform did not expose trusted per-call usage telemetry",
        }
        assert set(fragment["consumption"]) == {
            "measurement_status",
            "unavailable_reason",
        }

    assert outcome["integrity"] == {
        "workflow_contract_check": True,
        "record_checks": [True, True, True],
        "manifest_check": True,
        "wave_check": True,
        "tamper_detected": True,
        "fragment_checks": {"node-a": True, "node-b": True},
        "producer_checks": {"node-a": True, "node-b": True},
    }


def test_wave_uses_compiler_bound_standard_authority_for_five_exact_nodes(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path, node_count=5, independent=True)
    plans = [
        json.loads(task["contextArtifact"]["canonical_plan"])
        for task in wave_args["tasks"]
    ]
    assert all(
        plan["execution_dag_binding"]["node_count"] == 5
        and plan["execution_dag_binding"]["edge_count"] == 0
        and plan["budget"]["envelope"] == "standard"
        for plan in plans
    )

    admitted = _run_harness(wave_args)["retry"]

    assert admitted["ok"] is True
    assert admitted["seenCalls"] == [
        "node-a", "node-b", "node-c", "node-d", "node-e", "relay:node-a",
    ]
    authority = json.loads(
        admitted["result"]["wave_record"]["budget_authority"][
            "authority_canonical"
        ]
    )
    assert authority["envelope"] == "standard"
    assert authority["max_unique_nodes"] == 8

    forged = deepcopy(wave_args)
    four_node_dag = plans[0]["execution_dag_binding"]["nodes"][:4]
    forged_binding = {
        "schema_version": "context_execution_dag_binding_v1",
        "dag_digest": __import__(
            "agent_governance_execution_dag"
        ).execution_dag_digest(four_node_dag),
        "node_count": 4,
        "edge_count": 0,
        "nodes": four_node_dag,
    }
    for task in forged["tasks"]:
        artifact = task["contextArtifact"]
        plan = json.loads(artifact["canonical_plan"])
        plan["execution_dag_binding"] = forged_binding
        artifact["canonical_plan"] = json.dumps(
            plan,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        artifact["artifact_digest"] = canonical_digest(plan)
    rejected = _run_harness(forged)["retry"]
    assert rejected["ok"] is False
    assert rejected["seenCalls"] == []
    assert "DAG-bound" in rejected["error"]


def test_wave_rejects_identity_and_consumption_in_model_judgment(tmp_path: Path) -> None:
    outcome = _run_harness(_wave_args(tmp_path))
    assert outcome["identity"]["ok"] is False
    assert "controller-owned judgment fields" in outcome["identity"]["error"]
    assert outcome["consumption"]["ok"] is False
    assert "controller-owned judgment fields" in outcome["consumption"]["error"]

    allowed = {
        "work_status",
        "gate_verdict",
        "classification",
        "confidence",
        "summary",
        "evidence_refs",
        "concerns",
        "next_action",
        "payload",
    }
    for execution in (outcome["retry"], outcome["identity"], outcome["consumption"]):
        assert execution["seenSchemas"]
        assert set(execution["seenSchemas"][0]["properties"]) == allowed
        assert execution["seenSchemas"][0]["additionalProperties"] is False

    workflow = (ROOT / ".claude/workflows/agent-wave.js").read_text(encoding="utf-8")
    assert "actual_input_tokens" not in workflow
    assert "actual_output_tokens" not in workflow
    assert "input_tokens: judgment" not in workflow
    assert "schema: JUDGMENT_SCHEMA" in workflow


def test_wave_scheduler_never_exceeds_context_authority_capacity(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path, node_count=4, independent=True)

    outcome = _run_harness(wave_args)["retry"]

    assert outcome["ok"] is True
    assert outcome["peakCalls"] == 2
    assert outcome["result"]["wave_record"]["budget_authority"]["admitted_caps"][
        "max_concurrent_calls"
    ] == 2


def test_wave_scheduler_refills_capacity_before_slower_calls_finish(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path, node_count=4, independent=True)
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'agent', source);
const parallel = async jobs => Promise.all(jobs.map(job => job()));
const events = [];
let activeCalls = 0;
let peakCalls = 0;
let releaseSlowCall;
let slowCallTimedOut = false;
const replacementStarted = new Promise(resolve => { releaseSlowCall = resolve; });
const agent = async (_prompt, option) => {
  events.push(`start:${option.label}`);
  activeCalls += 1;
  peakCalls = Math.max(peakCalls, activeCalls);
  if (option.label === 'node-c') releaseSlowCall();
  if (option.label === 'node-a') {
    const release = await Promise.race([
      replacementStarted.then(() => 'replacement'),
      new Promise(resolve => setTimeout(() => resolve('timeout'), 100)),
    ]);
    slowCallTimedOut = release === 'timeout';
  } else {
    await Promise.resolve();
  }
  activeCalls -= 1;
  events.push(`end:${option.label}`);
  return {
    work_status: 'DONE', gate_verdict: 'PASS', classification: 'FACT',
    confidence: 'high', summary: `reviewed ${option.label}`,
    evidence_refs: [`evidence:${option.label}`], concerns: [],
    next_action: { owner: 'PM', action: 'integrate' }, payload: {},
  };
};
(async () => {
  const result = await runner(__ARGS__, () => {}, () => {}, parallel, agent);
  console.log(JSON.stringify({
    ok: true,
    events,
    peakCalls,
    slowCallTimedOut,
    maxConcurrentCalls: result.wave_record.budget_authority.admitted_caps.max_concurrent_calls,
  }));
})().catch(error => {
  console.log(JSON.stringify({ ok: false, error: String(error.message || error), events, peakCalls, slowCallTimedOut }));
});
""".replace("__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/agent-wave.js"))).replace(
        "__ARGS__", json.dumps(wave_args)
    )
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)

    assert outcome["ok"] is True
    assert outcome["slowCallTimedOut"] is False
    assert outcome["events"].index("start:node-c") < outcome["events"].index(
        "end:node-a"
    )
    assert outcome["peakCalls"] == outcome["maxConcurrentCalls"] == 2


def test_wave_scheduler_stops_dequeue_and_settles_in_flight_calls_on_error(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path, node_count=4, independent=True)
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'agent', source);
const parallel = async jobs => Promise.all(jobs.map(job => job()));
const events = [];
let activeCalls = 0;
let peakCalls = 0;
const agent = async (_prompt, option) => {
  events.push(`start:${option.label}`);
  activeCalls += 1;
  peakCalls = Math.max(peakCalls, activeCalls);
  if (option.label === 'node-a') {
    activeCalls -= 1;
    events.push('throw:node-a');
    throw new Error('agent boom');
  }
  await new Promise(resolve => setTimeout(resolve, 20));
  activeCalls -= 1;
  events.push(`end:${option.label}`);
  return {
    work_status: 'DONE', gate_verdict: 'PASS', classification: 'FACT',
    confidence: 'high', summary: `reviewed ${option.label}`,
    evidence_refs: [`evidence:${option.label}`], concerns: [],
    next_action: { owner: 'PM', action: 'integrate' }, payload: {},
  };
};
(async () => {
  try {
    await runner(__ARGS__, () => {}, () => {}, parallel, agent);
    console.log(JSON.stringify({ ok: true, events, peakCalls }));
  } catch (error) {
    events.push(`caught:${String(error.message || error)}`);
    await new Promise(resolve => setTimeout(resolve, 80));
    console.log(JSON.stringify({ ok: false, error: String(error.message || error), events, peakCalls }));
  }
})().catch(error => { console.error(error); process.exit(1); });
""".replace("__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/agent-wave.js"))).replace(
        "__ARGS__", json.dumps(wave_args)
    )
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)

    assert outcome["ok"] is False
    assert outcome["error"] == "agent boom"
    assert outcome["events"] == [
        "start:node-a",
        "throw:node-a",
        "start:node-b",
        "end:node-b",
        "caught:agent boom",
    ]
    assert outcome["peakCalls"] <= 2


def test_wave_rejects_caller_model_or_effort_override_before_agent_call(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path)
    wave_args["tasks"][0]["effort"] = "max"

    outcome = _run_harness(wave_args)["retry"]

    assert outcome["ok"] is False
    assert outcome["seenCalls"] == []
    assert "differs from Registry saved-workflow policy" in outcome["error"]


def test_wave_rejects_unbound_or_cyclic_dag_and_never_runs_blocked_dependents(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path)
    outcome = _run_harness(wave_args)
    blocked = outcome["blocked"]
    assert blocked["seenCalls"] == ["node-a", "relay:node-a"]
    if blocked["ok"]:
        errors = validate_workflow_wave_record(
            blocked["result"]["wave_record"],
            blocked["result"]["call_manifest"],
        )
        assert errors == [], (
            "a blocked workflow must never emit a workflow_wave_record_v1 that "
            f"its canonical validator rejects: {errors}"
        )
    assert blocked["ok"] is False
    assert "required predecessor did not complete" in blocked["error"]
    assert "workflow_wave_record_v1" in blocked["error"]
    assert "result" not in blocked

    forged = deepcopy(wave_args)
    forged["dag_digest"] = "sha256:" + "0" * 64
    rejected = _run_harness(forged)["retry"]
    assert rejected["ok"] is False
    assert "dag_digest differs" in rejected["error"]

    cyclic = deepcopy(wave_args)
    cyclic["tasks"][0]["requires"] = ["node-b"]
    dag_core = {
        "schema_version": "agent_wave_execution_dag_v1",
        "nodes": [
            {
                "node_id": task["node_id"],
                "role": task["agentType"],
                "native_agent": task["native_agent"],
                "requires": task["requires"],
                "node_class": task["node_class"],
                "permission": task["permission"],
            }
            for task in cyclic["tasks"]
        ],
    }
    cyclic["dag_digest"] = canonical_digest(dag_core)
    cyclic_binding = {
        "schema_version": "context_execution_dag_binding_v1",
        "dag_digest": cyclic["dag_digest"],
        "node_count": len(dag_core["nodes"]),
        "edge_count": sum(
            len(node["requires"]) for node in dag_core["nodes"]
        ),
        "nodes": dag_core["nodes"],
    }
    for task in cyclic["tasks"]:
        artifact = task["contextArtifact"]
        plan = json.loads(artifact["canonical_plan"])
        plan["execution_dag_binding"] = cyclic_binding
        artifact["canonical_plan"] = json.dumps(
            plan,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        artifact["artifact_digest"] = canonical_digest(plan)
    rejected = _run_harness(cyclic)["retry"]
    assert rejected["ok"] is False
    assert rejected["seenCalls"] == []
    assert "execution DAG binding is invalid" in rejected["error"]

    substituted = deepcopy(wave_args)
    substituted["tasks"][0]["native_agent"] = "E4-verifier"
    rejected = _run_harness(substituted)["retry"]
    assert rejected["ok"] is False
    assert rejected["seenCalls"] == []
    assert "native_agent" in rejected["error"]

    valid = outcome["retry"]["result"]
    reordered_manifest = deepcopy(valid["call_manifest"])
    reordered_manifest["records"] = [
        reordered_manifest["records"][2],
        *reordered_manifest["records"][:2],
    ]
    reordered_manifest["manifest_digest"] = canonical_digest(
        {key: value for key, value in reordered_manifest.items() if key != "manifest_digest"}
    )
    reordered_wave = deepcopy(valid["wave_record"])
    reordered_wave["call_manifest_digest"] = reordered_manifest["manifest_digest"]
    reordered_wave["call_record_digests"] = [
        record["record_digest"] for record in reordered_manifest["records"]
    ]
    reordered_wave["record_digest"] = canonical_digest(
        {key: value for key, value in reordered_wave.items() if key != "record_digest"}
    )
    errors = validate_workflow_wave_record(reordered_wave, reordered_manifest)
    assert "workflow call manifest order regresses across topological waves" in errors
    assert any("producer generation is incomplete" in error for error in errors)


def test_wave_validator_enforces_bound_surface_event_coverage(
    tmp_path: Path,
) -> None:
    result = _run_harness(_wave_args(tmp_path, risk="medium"))["retry"]["result"]
    wave = deepcopy(result["wave_record"])
    ledger = wave["execution_event_ledger"]
    retry_event = next(
        event for event in ledger["events"] if event["kind"] == "retry"
    )
    retry_event["kind"] = "follow_up"
    ledger["ledger_digest"] = canonical_digest(
        {
            key: value
            for key, value in ledger.items()
            if key != "ledger_digest"
        }
    )
    wave["record_digest"] = canonical_digest(
        {
            key: value
            for key, value in wave.items()
            if key != "record_digest"
        }
    )

    assert validate_workflow_wave_record(
        wave,
        result["call_manifest"],
    ) == [
        "execution event 2 surface profile does not attest follow_up",
        "workflow wave sampling event 1 kind differs from manifest call",
    ]


def test_wave_validator_binds_sampling_event_semantics_to_manifest(
    tmp_path: Path,
) -> None:
    result = _run_harness(_wave_args(tmp_path))["retry"]["result"]
    wave = deepcopy(result["wave_record"])
    ledger = wave["execution_event_ledger"]
    root_event = next(
        event for event in ledger["events"] if event["kind"] == "root_turn"
    )
    retry_event = next(
        event for event in ledger["events"] if event["kind"] == "retry"
    )
    retry_event["kind"] = "model_call"
    retry_event["parent_event_id"] = root_event["event_id"]
    ledger["ledger_digest"] = canonical_digest(
        {
            key: value
            for key, value in ledger.items()
            if key != "ledger_digest"
        }
    )
    wave["record_digest"] = canonical_digest(
        {
            key: value
            for key, value in wave.items()
            if key != "record_digest"
        }
    )

    assert validate_workflow_wave_record(
        wave,
        result["call_manifest"],
    ) == [
        "workflow wave sampling event 1 kind differs from manifest call",
        "workflow wave sampling event 1 parent_event_id differs from manifest call",
    ]


def test_wave_validator_rejects_a_self_signed_forged_execution_policy(
    tmp_path: Path,
) -> None:
    result = _run_harness(_wave_args(tmp_path))["retry"]["result"]
    wave = deepcopy(result["wave_record"])
    authority = json.loads(wave["budget_authority"]["authority_canonical"])
    authority["max_wall_clock_ms"] += 1
    authority_canonical = json.dumps(
        authority,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    authority_digest = canonical_digest(authority)
    wave["budget_authority"]["authority_canonical"] = authority_canonical
    wave["budget_authority"]["authority_digest"] = authority_digest
    wave["budget_authority"]["admitted_caps"]["max_wall_clock_ms"] += 1
    ledger = wave["execution_event_ledger"]
    ledger["policy_digest"] = authority_digest
    ledger["ledger_digest"] = canonical_digest(
        {
            key: value
            for key, value in ledger.items()
            if key != "ledger_digest"
        }
    )
    wave["record_digest"] = canonical_digest(
        {
            key: value
            for key, value in wave.items()
            if key != "record_digest"
        }
    )

    assert validate_workflow_wave_record(
        wave,
        result["call_manifest"],
    ) == [
        "workflow wave execution budget policy differs from the live Registry authority"
    ]
