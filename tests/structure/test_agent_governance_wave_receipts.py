from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
sys.path.insert(0, str(HELPERS))

from agent_governance_context import capture_repository_baseline  # noqa: E402
from agent_governance_execution import (  # noqa: E402
    compile_context,
    materialize_context_artifact,
)
from agent_governance_registry import load_registry  # noqa: E402
from agent_governance_workflow_receipts import (  # noqa: E402
    canonical_digest,
    validate_workflow_call_manifest,
    validate_workflow_wave_record,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


def _wave_args(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "wave-test@example.invalid")
    _git(repo, "config", "user.name", "Wave Test")
    (repo / "local.md").write_text("controller-owned wave input\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    registry = deepcopy(load_registry())
    registry["context_packs"]["wave_test"] = ["local.md"]
    registry["roles"]["E2"]["context_packs"] = ["wave_test"]
    facts = {
        "task_shape": "review",
        "surfaces": ["agent_workflow"],
        "risk": "low",
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
        "direct_interfaces": ["agent-wave"],
        "previous_failure": "model output could spoof controller identity",
        "task_prompt": "Review immutable call binding for the admitted node.",
    }
    plan = compile_context("E2", facts, registry, repo)
    artifact = materialize_context_artifact(plan)
    tasks = [
        {
            "node_id": node_id,
            "payload_kind": "review_fragment_v1",
            "agentType": "E2",
            "native_agent": "E2",
            "node_class": "verification",
            "permission": "read_only",
            "prompt": "Review immutable call binding for the admitted node.",
            "description": f"wave-receipt-{node_id}",
            "contextArtifact": artifact,
        }
        for node_id in ("node-a", "node-b")
    ]
    tasks[0]["requires"] = []
    tasks[1]["requires"] = ["node-a"]
    tasks[1].update({"model": "sonnet", "effort": "high", "isolation": "worktree"})
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
            for task in tasks
        ],
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
  const agent = async (_prompt, option) => {
    seenSchemas.push(option.schema);
    seenCalls.push(option.label);
    if (mode === 'blocked' && option.label.includes('node-a')) return null;
    if (mode === 'retry' && option.phase === 'Wave' && option.label === 'node-a') return null;
    const value = judgment(option);
    if (mode === 'identity') return { ...value, role: 'spoofed-role' };
    if (mode === 'consumption') return { ...value, consumption: { measurement_status: 'measured', input_tokens: 1 } };
    return value;
  };
  try {
    const result = await runner(JSON.parse(JSON.stringify(baseArgs)), () => {}, () => {}, parallel, agent);
    return { ok: true, result, seenSchemas, seenCalls };
  } catch (error) {
    return { ok: false, error: String(error.message || error), seenSchemas, seenCalls };
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
            "model": None, "effort": None, "isolation": None,
            "node_class": "verification", "permission": "read_only",
        }
        for record in records
        if "node-a" in record["logical_call_id"]
    )
    assert node_b["requested"] == {
        "logical_role": "E2", "platform": "claude_saved_workflow",
        "platform_requested_agent": "E2",
        "native_binding": {"logical_role": "E2", "native_agent": "E2", "node_class": "verification", "permission": "read_only"},
        "model": "sonnet",
        "effort": "high",
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


def test_wave_rejects_unbound_or_cyclic_dag_and_never_runs_blocked_dependents(
    tmp_path: Path,
) -> None:
    wave_args = _wave_args(tmp_path)
    outcome = _run_harness(wave_args)
    blocked = outcome["blocked"]
    assert blocked["ok"] is True
    assert blocked["seenCalls"] == ["node-a", "relay:node-a"]
    assert blocked["result"]["results"] == {"node-a": None, "node-b": None}
    assert {item["node"] for item in blocked["result"]["retry_coverage_debt"]} == {
        "node-a",
        "node-b",
    }

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
    rejected = _run_harness(cyclic)["retry"]
    assert rejected["ok"] is False
    assert "contains a cycle" in rejected["error"]

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
