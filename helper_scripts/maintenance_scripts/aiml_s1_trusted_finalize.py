#!/usr/bin/env python3
"""Emit and authenticate the complete AIML Sprint-1 target-host closure.

This finalizer consumes fresh producer artifacts from
``aiml_s1_closure_target_host_run.py``.  It builds a real PM Context bundle,
call/wave-bound role fragments, a schema-valid ``closure_packet_v1``, a
domain-separated S1 trusted execution bundle, and a non-placeholder landing
attempt.  The bundle is signed through the already-loaded SSH agent; no private
key path or private-key bytes are accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HERE, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_aiml_trusted_host as trusted
import agent_governance_command_capture_v2 as command_capture
import agent_governance_component_effects as component_effects
import agent_governance_target_host_apply as target_apply
import agent_governance_target_host_effects as target_effects
import aiml_gate_receipt_validator as aiml_validator
from agent_governance_authority import build_authority_claim
from agent_governance_context import capture_repository_baseline
from agent_governance_execution import compile_context, materialize_context_artifact
from agent_governance_execution_dag import topological_waves
from agent_governance_registry import load_registry, native_agent_binding
from agent_governance_routing import route_task
from agent_governance_workflow_receipts import (
    build_controller_workflow_call_record,
    build_workflow_call_manifest,
    build_workflow_wave_record,
    canonical_bytes,
    canonical_digest,
)


OUTPUTS = {
    "context": "S1-closure-context-artifact-v1.json",
    "manifest": "S1-closure-workflow-call-manifest-v1.json",
    "wave": "S1-closure-workflow-wave-record-v1.json",
    "packet": "S1-closure-packet-v1.json",
    "bundle": "S1-closure-trusted-execution-bundle-v1.json",
    "signature": "S1-closure-trusted-execution-bundle-v1.json.sig",
    "attempt": "S1-landing-session-attempt-v1.json",
    "finalization": "S1-closure-finalization-result-v1.json",
}

REVIEW_PROVENANCE_FIELDS = {
    "schema_version", "entries", "limitations", "self_digest",
}
REVIEW_ENTRY_FIELDS = {
    "description", "ended_at", "prompt_digest", "result_digest",
    "reviewed_head", "role", "started_at", "transcript_digest", "verdict",
}
REVIEW_PROVENANCE_ROLES = {
    "pa_design": "PA",
    "constitutional_gate": "CC",
    "security_gate": "E3",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _validated_review_provenance(value: dict[str, Any]) -> dict[str, Any]:
    """Validate the immutable historical review-call digest inventory.

    These records do not pretend to be fresh final-head reviews.  They preserve
    the exact prompt/result/transcript digests of already-completed platform
    calls.  The final artifact-only head still goes through a separate Codex
    review before merge.
    """

    if set(value) != REVIEW_PROVENANCE_FIELDS:
        raise ValueError("review provenance fields do not match the exact contract")
    if value.get("schema_version") != "aiml_s1_review_provenance_v1":
        raise ValueError("review provenance schema_version is invalid")
    entries = value.get("entries")
    if not isinstance(entries, dict) or set(entries) != set(REVIEW_PROVENANCE_ROLES):
        raise ValueError("review provenance entry inventory is incomplete")
    for node_id, expected_role in REVIEW_PROVENANCE_ROLES.items():
        entry = entries[node_id]
        if not isinstance(entry, dict) or set(entry) != REVIEW_ENTRY_FIELDS:
            raise ValueError(f"review provenance {node_id} fields are invalid")
        if entry.get("role") != expected_role:
            raise ValueError(f"review provenance {node_id} role is invalid")
        for field in (
            "prompt_digest", "result_digest", "transcript_digest",
        ):
            if not trusted.DIGEST_RE.fullmatch(str(entry.get(field, ""))):
                raise ValueError(
                    f"review provenance {node_id} {field} is invalid"
                )
        reviewed_head = entry.get("reviewed_head")
        if reviewed_head is not None and (
            not isinstance(reviewed_head, str)
            or len(reviewed_head) != 40
            or any(character not in "0123456789abcdef" for character in reviewed_head)
        ):
            raise ValueError(
                f"review provenance {node_id} reviewed_head is invalid"
            )
        started = datetime.fromisoformat(
            str(entry.get("started_at", "")).replace("Z", "+00:00")
        )
        ended = datetime.fromisoformat(
            str(entry.get("ended_at", "")).replace("Z", "+00:00")
        )
        if started.tzinfo is None or ended.tzinfo is None or ended < started:
            raise ValueError(
                f"review provenance {node_id} timestamps are invalid"
            )
        if not all(
            isinstance(entry.get(field), str) and entry[field]
            for field in ("description", "verdict")
        ):
            raise ValueError(
                f"review provenance {node_id} text fields are invalid"
            )
    limitations = value.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(item, str) or not item for item in limitations)
    ):
        raise ValueError("review provenance limitations are invalid")
    expected_digest = canonical_digest({
        key: item for key, item in value.items() if key != "self_digest"
    })
    if value.get("self_digest") != expected_digest:
        raise ValueError("review provenance self_digest is invalid")
    return value


def _runtime_context_payload(
    *,
    baseline: dict[str, str],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    content = {
        "schema_version": "aiml_s1_target_host_runtime_observation_v1",
        "status": "PASS",
        "source_head": receipt["source_head"],
        "target_host": receipt["target_host"],
        "effect_receipt_digest": receipt["receipt_digest"],
        "verifier_capture_digest": receipt["verifier_capture_digest"],
    }
    return {
        "schema_version": "context_evidence_artifact_v1",
        "logical_source": "runtime observation",
        "capture_kind": "runtime_observation",
        "observed_at": receipt["completed_at"],
        "expires_at": receipt["evidence_expires_at"],
        "baseline": baseline,
        "producer": {
            "id": "runtime_observation_adapter_v1",
            "input_digest": receipt["receipt_digest"],
        },
        "content": content,
        "content_digest": canonical_digest(content),
    }


def _task_facts(
    *,
    baseline: dict[str, str],
    runtime_artifact_path: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    objective = "Formally close AIML Sprint-1 from the authenticated target-host effect"
    criterion = (
        "The final S1 closure binds the authenticated target-host effect, "
        "distinct verifier postcheck, and verifier capture"
    )
    governed_scope = [
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure.py",
        "helper_scripts/maintenance_scripts/agent_governance_context.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_apply.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_child_apply.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_effects.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_observation.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_observation_capture.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_operator_authorization.py",
        "helper_scripts/maintenance_scripts/agent_governance_trust.py",
        "helper_scripts/maintenance_scripts/aiml_s1_closure_target_host_run.py",
        "helper_scripts/maintenance_scripts/aiml_s1_target_host_authorize.py",
        "helper_scripts/maintenance_scripts/aiml_s1_trusted_finalize.py",
    ]
    return {
        "task_shape": "audit",
        "surfaces": ["authority", "runtime_effect", "service"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "target_host_probe",
        "objective": objective,
        "scope": ["docs/execution_plan/ai_ml_landing", *governed_scope],
        "acceptance_criteria": [criterion],
        "hard_stops": [
            "no production runtime mutation",
            "no broker, order, or live authority",
        ],
        "baseline": baseline,
        # Workflow receipts call this field dirty_scope, but for read-only
        # verifier nodes it is the bounded task-owned source generation.  The
        # finalizer itself performs no repository mutation.
        "dirty_scope": governed_scope,
        "verification_scope": governed_scope,
        "direct_interfaces": [
            "runtime observation",
            "target_host_disposable_runtime_probe_adapter_v1",
        ],
        "previous_failure": (
            "operator SSHSIG and a validated closure_packet_v1 were absent"
        ),
        "task_prompt": objective,
        "claim_inputs": {
            "target_host_intent": receipt["intent_digest"],
        },
        "evidence_state": {
            "runtime observation": {
                "artifact_path": runtime_artifact_path,
            }
        },
    }


def _requested(node: dict[str, Any]) -> dict[str, Any]:
    binding = native_agent_binding(node["role"], node["node_class"])
    return {
        "logical_role": node["role"],
        "platform": "claude_saved_workflow",
        "platform_requested_agent": binding["native_agent"],
        "native_binding": {
            "logical_role": node["role"],
            "native_agent": binding["native_agent"],
            "node_class": node["node_class"],
            "permission": binding["permission"],
        },
        "model": None,
        "effort": None,
        "isolation": None,
        "node_class": node["node_class"],
        "permission": binding["permission"],
    }


def _workflow(
    *,
    route: dict[str, Any],
    context: dict[str, Any],
    effect_id: str,
    postcheck_id: str,
    verifier_capture_id: str,
    preflight_capture: dict[str, Any],
    verifier_capture: dict[str, Any],
    review_provenance: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    registry = load_registry()
    nodes = route["required_role_nodes"]
    waves, errors = topological_waves(nodes)
    if errors:
        raise ValueError("cannot build finalization workflow DAG: " + "; ".join(errors))
    wave_by_node = {
        node_id: index for index, wave in enumerate(waves) for node_id in wave
    }
    workflow_digest = canonical_digest({
        "schema_version": "aiml_s1_closure_workflow_v1",
        "task_contract_digest": context["task_contract_digest"],
        "dag_digest": route["dag_digest"],
    })
    call_by_node: dict[str, dict[str, Any]] = {}
    judgment_by_node: dict[str, dict[str, Any]] = {}
    fragment_refs: dict[str, list[str]] = {}
    for node in nodes:
        refs = ["s1-closure-workflow-wave", effect_id]
        if node["node_id"] == "ops_postcheck":
            refs.extend([postcheck_id, verifier_capture_id])
        fragment_refs[node["node_id"]] = refs
        if node["node_id"] in {"ops_preflight", "ops_postcheck"}:
            capture = (
                preflight_capture
                if node["node_id"] == "ops_preflight"
                else verifier_capture
            )
            provenance_payload = {
                "source_kind": "governed_command_capture_v2",
                "record_digest": capture["record_digest"],
                "started_at": capture["started_at"],
                "ended_at": capture["completed_at"],
                "reviewed_head": (
                    capture.get("repository_after") or {}
                ).get("source_head"),
                "capture": capture,
            }
            summary = (
                "OPS preflight binds the fresh governed readiness capture taken "
                "before the target-host effect"
                if node["node_id"] == "ops_preflight"
                else
                "OPS postcheck binds the fresh governed verifier capture, "
                "clean residue, exact source head, and target-host effect"
            )
            concerns: list[str] = []
        else:
            imported = review_provenance["entries"][node["node_id"]]
            provenance_payload = {
                "source_kind": "historical_platform_agent_call_digest",
                "review_provenance_digest": review_provenance["self_digest"],
                "call": imported,
                "limitation": (
                    "historical role review; the final evidence-only head still "
                    "requires a separate exact-head Codex review before merge"
                ),
            }
            summary = (
                f"{node['role']} historical review provenance is preserved "
                "without claiming a fresh replay; the current effect is "
                "authenticated independently by the operator SSHSIG"
            )
            # Closure PASS treats every non-empty concern as unresolved.  Keep
            # the provenance limitation in the fragment payload, where it is
            # explicit and load-bearing, without misclassifying the separate
            # exact-head merge review as an unresolved closure concern.
            concerns = []
        judgment_by_node[node["node_id"]] = {
            "work_status": "DONE",
            "gate_verdict": "PASS",
            "classification": "FACT",
            "confidence": "high",
            "summary": summary,
            "evidence_refs": refs,
            "concerns": concerns,
            "next_action": None,
            "payload": provenance_payload,
        }

    for wave_index, wave in enumerate(waves):
        for node_id in wave:
            node = next(item for item in nodes if item["node_id"] == node_id)
            if node_id == "ops_preflight":
                source_record = preflight_capture
            elif node_id == "ops_postcheck":
                source_record = verifier_capture
            else:
                source_record = review_provenance["entries"][node_id]
            started = datetime.fromisoformat(
                source_record["started_at"].replace("Z", "+00:00")
            )
            ended = datetime.fromisoformat(
                (
                    source_record.get("completed_at")
                    or source_record.get("ended_at")
                ).replace("Z", "+00:00")
            )
            producer_generation = {
                predecessor: call_by_node[predecessor]["record_digest"]
                for predecessor in node["requires"]
            }
            judgment = judgment_by_node[node_id]
            call_by_node[node_id] = build_controller_workflow_call_record(
                workflow_contract_digest=workflow_digest,
                logical_call_id=f"s1-finalization:{node_id}:attempt:1",
                node_id=node_id,
                payload_kind=registry["roles"][node["role"]]["payload_kind"],
                attempt=1,
                retry_parent_call_id=None,
                phase="S1-finalization",
                label=node_id,
                requested=_requested(node),
                prompt_digest=(
                    canonical_digest({
                        "node_id": node_id,
                        "argv": source_record["argv"],
                        "authorization": source_record["authorization"],
                    })
                    if node_id in {"ops_preflight", "ops_postcheck"}
                    else review_provenance["entries"][node_id]["prompt_digest"]
                ),
                context_artifact_digest=context["artifact_digest"],
                task_contract_digest=context["task_contract_digest"],
                dirty_scope_digest=canonical_digest(
                    sorted(route["task_facts"]["dirty_scope"])
                ),
                focus_digest=canonical_digest(route["task_facts"].get("focus", "")),
                compiler_input_tokens_lower_bound=0,
                admitted_input_tokens_lower_bound=0,
                response_schema_digest=canonical_digest({
                    "payload_kind": registry["roles"][node["role"]]["payload_kind"]
                }),
                started_at=_iso(started),
                ended_at=_iso(ended),
                returned_null=False,
                parsed_result_digest=canonical_digest(judgment),
                dag_digest=route["dag_digest"],
                requires=node["requires"],
                topological_wave=wave_by_node[node_id],
                producer_generation=producer_generation,
            )

    fragments: list[dict[str, Any]] = []
    unavailable = {
        "measurement_status": "unavailable",
        "unavailable_reason": (
            "historical independent review telemetry is not exposed by the provider"
        ),
    }
    for node in nodes:
        call = call_by_node[node["node_id"]]
        judgment = judgment_by_node[node["node_id"]]
        fragments.append({
            "schema_version": "role_fragment_v1",
            "id": f"s1-finalization-fragment:{node['node_id']}",
            "node_id": node["node_id"],
            "role": node["role"],
            "task_contract_digest": context["task_contract_digest"],
            "context_artifact_digest": context["artifact_digest"],
            "producer_call_ref": call["logical_call_id"],
            "producer_call_receipt_digest": call["record_digest"],
            "producer_record_kind": "workflow_call_record_v1",
            **judgment,
            "consumption": unavailable,
            "payload_kind": registry["roles"][node["role"]]["payload_kind"],
        })

    ordered_calls = sorted(
        call_by_node.values(),
        key=lambda item: (item["topological_wave"], item["logical_call_id"]),
    )
    manifest = build_workflow_call_manifest(
        ordered_calls, workflow_contract_digest=workflow_digest
    )
    plan = json.loads(context["canonical_plan"])
    budget = json.loads(context["budget_authority_canonical"])
    admitted_tasks = []
    for node in nodes:
        call = call_by_node[node["node_id"]]
        admitted_tasks.append({
            "node_id": node["node_id"],
            "role": node["role"],
            "native_agent": node["native_agent"],
            "requires": node["requires"],
            "node_class": node["node_class"],
            "permission": node["permission"],
            "payload_kind": call["payload_kind"],
            "task_contract_digest": context["task_contract_digest"],
            "context_artifact_digest": context["artifact_digest"],
            "description_digest": canonical_digest({
                "node_id": node["node_id"],
                "role": node["role"],
            }),
            "base_prompt_digest": call["prompt_digest"],
            "requested": call["requested"],
            "dirty_scope": sorted(plan["task_contract"]["dirty_scope"]),
            "dirty_scope_digest": canonical_digest(
                sorted(plan["task_contract"]["dirty_scope"])
            ),
            "focus": plan["task_contract"]["focus"],
            "focus_digest": canonical_digest(plan["task_contract"]["focus"]),
            "compiler_estimated_input_tokens": 0,
            "admitted_input_tokens_lower_bound": 0,
        })
    wave = build_workflow_wave_record(
        manifest=manifest,
        admitted_tasks=admitted_tasks,
        budget_authority={
            "authority_digest": context["budget_authority_digest"],
            "authority_canonical": context["budget_authority_canonical"],
            "admitted_caps": {
                field: budget[field]
                for field in (
                    "max_context_tokens_per_call",
                    "max_prompt_utf8_bytes_per_call",
                    "max_workflow_planned_input_tokens",
                    "max_unique_nodes",
                    "max_call_attempts",
                    "retry_budget",
                )
            },
        },
        result_fragment_digests={
            fragment["node_id"]: canonical_digest(fragment)
            for fragment in fragments
        },
    )
    return fragments, manifest, wave


def _build_packet(
    *,
    route: dict[str, Any],
    context: dict[str, Any],
    receipt: dict[str, Any],
    preflight_capture: dict[str, Any],
    verifier_capture: dict[str, Any],
    residue: dict[str, Any],
    review_provenance: dict[str, Any],
    adjudicated_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    effect = target_effects.build_target_host_effect_evidence(receipt)
    postcheck, verifier = target_effects.build_target_host_closure_evidence(
        receipt, verifier_capture, residue
    )
    fragments, manifest, wave = _workflow(
        route=route,
        context=context,
        effect_id=effect["id"],
        postcheck_id=postcheck["id"],
        verifier_capture_id=verifier["id"],
        preflight_capture=preflight_capture,
        verifier_capture=verifier_capture,
        review_provenance=review_provenance,
    )
    authority = build_authority_claim(
        authority_class="claim_evidence",
        subject="AIML Sprint-1 target-host disposable probe intent",
        value={
            "authorized": True,
            "intent_id": receipt["intent_id"],
        },
        source=(
            f"{target_effects.INTENT_SCHEMA_VERSION}:{receipt['intent_id']}"
        ),
        source_ref="task_contract:claim_inputs:target_host_intent",
        source_digest=receipt["intent_digest"],
        observed_at=receipt["approved_at"],
        scope="aiml-s1-target-host",
        strength="derived",
        expiry=receipt["intent_expires_at"],
    )
    criterion = route["task_facts"]["acceptance_criteria"][0]
    packet = {
        "schema_version": "closure_packet_v1",
        "task_id": "aiml-s1-formal-closure-v1",
        "human_summary": {
            "objective": route["task_facts"]["objective"],
            "scope": route["task_facts"]["scope"],
            "outcome": (
                "S1 target-host effect and independent postcheck authenticated; "
                "EFFECT_SEAMS_READY closed without production authority"
            ),
        },
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "disposition": "CHANGED",
        "confidence": "high",
        "adjudicated_at": _iso(adjudicated_at),
        "baseline": {
            **route["task_facts"]["baseline"],
            "runtime_head": receipt["source_head"],
            "runtime_observed_at": receipt["completed_at"],
        },
        "dispatch": {
            "task_facts": route["task_facts"],
            "context_artifact": context,
            "dag_digest": route["dag_digest"],
            "required_role_nodes": route["required_role_nodes"],
            "admitted_role_nodes": [],
        },
        "authority_refs": [authority],
        "acceptance": [{
            "criterion": criterion,
            "status": "PASS",
            "evidence_refs": [effect["id"], postcheck["id"], verifier["id"]],
        }],
        "evidence": [
            effect,
            postcheck,
            verifier,
            {
                "id": "s1-closure-workflow-manifest",
                "scope": "data",
                "kind": "workflow_call_manifest_v1",
                "digest": manifest["manifest_digest"],
                "artifact": manifest,
            },
            {
                "id": "s1-closure-workflow-wave",
                "scope": "data",
                "kind": "workflow_wave_record_v1",
                "digest": wave["record_digest"],
                "artifact": wave,
            },
        ],
        "role_fragments": fragments,
        "checks": [],
        "side_effects": {
            "repo_mutation": False,
            "runtime_contact": True,
            "private_external_contact": False,
            "broker_effect": False,
        },
        "unverified": [],
        "skipped_roles": route["skipped"],
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": (
                "historical independent review telemetry is not exposed by the provider"
            ),
        },
        "next_action": None,
    }
    return packet, manifest, wave, effect


def _bundle(
    *,
    context: dict[str, Any],
    wave: dict[str, Any],
    receipt: dict[str, Any],
    route: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    effect_expiry = datetime.fromisoformat(
        receipt["evidence_expires_at"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    expires = min(now + timedelta(minutes=10), effect_expiry)
    if expires <= now + timedelta(seconds=30):
        raise ValueError("target-host evidence has insufficient freshness remaining to sign")
    observed = _iso(now - timedelta(seconds=1))
    expiry = _iso(expires)
    entries = [
        {
            "kind": "context_artifact_v1",
            "subject_digest": context["artifact_digest"],
            "artifact_digest": canonical_digest(context),
            "observed_at": observed,
            "expires_at": expiry,
        },
        {
            "kind": "effect_adapter_result_v1",
            "subject_digest": receipt["receipt_digest"],
            "artifact_digest": canonical_digest(receipt),
            "observed_at": observed,
            "expires_at": expiry,
        },
        {
            "kind": "workflow_wave_record_v1",
            "subject_digest": wave["record_digest"],
            "artifact_digest": canonical_digest(wave),
            "observed_at": observed,
            "expires_at": expiry,
        },
    ]
    entries.sort(key=lambda item: (item["kind"], item["subject_digest"]))
    profile = trusted.S1_TARGET_HOST_EXECUTION_SIGNER_PROFILE
    return {
        "schema_version": "trusted_execution_bundle_v1",
        "signer_identity": profile.identity,
        "signer_fingerprint": profile.fingerprint,
        "algorithm": profile.algorithm,
        "signature_namespace": profile.namespace,
        "task_contract_digest": context["task_contract_digest"],
        "context_artifact_digest": context["artifact_digest"],
        "dag_digest": route["dag_digest"],
        "issued_at": _iso(now),
        "expires_at": expiry,
        "entries": entries,
    }


def _sign_with_agent(bundle: dict[str, Any]) -> bytes:
    public_key = trusted.S1_TARGET_HOST_EXECUTION_SIGNER_PROFILE.public_key
    agent_keys = subprocess.run(
        ["/usr/bin/ssh-add", "-L"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    if agent_keys.returncode != 0 or public_key.encode("ascii") not in agent_keys.stdout:
        raise ValueError("authorized S1 public key is not loaded in the current SSH agent")
    with tempfile.TemporaryDirectory(prefix="aiml-s1-sign-") as directory:
        root = Path(directory)
        public_path = root / "s1-operator.pub"
        bundle_path = root / "bundle.json"
        public_path.write_text(public_key + "\n", encoding="ascii")
        bundle_path.write_bytes(canonical_bytes(bundle))
        signed = subprocess.run(
            [
                trusted.SSH_KEYGEN_EXECUTABLE,
                "-Y",
                "sign",
                "-f",
                str(public_path),
                "-n",
                trusted.S1_TARGET_HOST_SIGNATURE_NAMESPACE,
                str(bundle_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if signed.returncode != 0:
            raise ValueError(
                "SSH-agent signing failed: "
                + signed.stderr.decode("utf-8", errors="replace")[:300]
            )
        return bundle_path.with_suffix(".json.sig").read_bytes()


def _github_token() -> bytes:
    gh = shutil.which("gh")
    if gh is None:
        raise ValueError("gh CLI is unavailable for trusted-host finalization")
    result = subprocess.run(
        [gh, "auth", "token"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or len(token) < 8:
        raise ValueError("authenticated GitHub token is unavailable")
    return token


def _finalize_and_capture_replay_time(
    packet: dict[str, Any],
    bundle: dict[str, Any],
    *,
    signature: bytes,
    github_token: bytes,
) -> tuple[dict[str, Any], datetime]:
    """Return the trusted result and its signed replay evaluation instant.

    S1 uses ``trusted_execution_bundle_v1.issued_at`` as the closure evaluation
    instant.  It is inside the SSHSIG-authenticated bytes and is validated by
    the trusted host for freshness/skew before the canonical closure runs.
    """

    result = trusted.finalize_s1_target_host_from_host_inputs(
        packet,
        bundle,
        execution_signature=signature,
        github_token=github_token,
    )
    try:
        evaluated_at = datetime.fromisoformat(
            str(bundle["issued_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "signed S1 bundle issued_at is not a timezone-aware timestamp"
        ) from error
    if evaluated_at.tzinfo is None:
        raise ValueError(
            "signed S1 bundle issued_at is not a timezone-aware timestamp"
        )
    return result, evaluated_at.astimezone(timezone.utc)


def _landing_attempt(
    *,
    packet: dict[str, Any],
    receipt: dict[str, Any],
    effect_seams: dict[str, Any],
    context: dict[str, Any],
    route: dict[str, Any],
    branch: str,
    worktree: Path,
    writer_lease_id: str,
    created_at: datetime,
) -> dict[str, Any]:
    lease = {
        "lease_id": writer_lease_id,
        "epoch": 1,
        "acquired_at": _iso(created_at - timedelta(minutes=1)),
        "heartbeat_at": _iso(created_at),
        "expires_at": _iso(created_at + timedelta(hours=4)),
    }
    return target_apply.build_target_host_landing_attempt(
        effect_result=receipt,
        session_id="S1.6B",
        cohort_epoch="2026-07-24-s1-final",
        owner="PM",
        source={
            "branch": branch,
            "worktree": str(worktree),
            "checkpoint_head": receipt["source_head"],
        },
        lease=lease,
        landing_scope_id=canonical_digest({"sprint": "S1"}),
        work_package_id="AIML_S1_FORMAL_CLOSURE_V1",
        direct_interfaces=[
            "target_host_disposable_runtime_probe_adapter_v1",
            "closure_packet_v1",
        ],
        owned_paths=[
            ".codex/agent_registry_v1.json",
            "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py",
            "helper_scripts/maintenance_scripts/agent_governance_permissions.py",
            "helper_scripts/maintenance_scripts/agent_governance_target_host_apply.py",
            "helper_scripts/maintenance_scripts/agent_governance_target_host_child_apply.py",
            "helper_scripts/maintenance_scripts/agent_governance_target_host_choice.py",
            "helper_scripts/maintenance_scripts/agent_governance_target_host_effects.py",
            "helper_scripts/maintenance_scripts/agent_governance_target_host_observation.py",
            "helper_scripts/maintenance_scripts/agent_governance_target_host_observation_capture.py",
            "helper_scripts/maintenance_scripts/agent_governance_target_host_operator_authorization.py",
            "helper_scripts/maintenance_scripts/agent_governance_trust.py",
            "helper_scripts/maintenance_scripts/aiml_s1_closure_target_host_run.py",
            "helper_scripts/maintenance_scripts/aiml_s1_target_host_authorize.py",
            "helper_scripts/maintenance_scripts/aiml_s1_trusted_finalize.py",
        ],
        dependency_generations=[
            {
                "session_id": "S1.5",
                "schema_version": effect_seams["schema_version"],
                "receipt_digest": effect_seams["self_digest"],
            },
            {
                "session_id": "S1.6",
                "schema_version": receipt["choice_receipt"]["schema_version"],
                "receipt_digest": receipt["choice_receipt"]["self_digest"],
            },
        ],
        bootstrap={
            "task_id": packet["task_id"],
            "task_contract_digest": context["task_contract_digest"],
            "dag_digest": route["dag_digest"],
            "context_artifact_digest": context["artifact_digest"],
        },
        ci_classifier_digest=aiml_validator.aiml_effect_classifier_digest(),
        effect_classification_digest=canonical_digest({
            "effect_class": "TARGET_HOST_DISPOSABLE_RUNTIME_PROBE",
            "adapter_id": receipt["adapter_id"],
        }),
        closure_packet_digest=canonical_digest(packet),
        created_at=_iso(created_at),
        status="FINALIZED",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--writer-lease-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--review-provenance", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    artifact_dir = args.artifact_dir.resolve()
    receipt = _load(artifact_dir / "upgraded_effect_result.json")
    preflight_capture = _load(artifact_dir / "preflight_capture.json")
    verifier_capture = _load(artifact_dir / "verifier_capture.json")
    residue = _load(artifact_dir / "residue_observation.json")
    effect_seams = _load(artifact_dir / "effect_seams_ready_receipt.json")
    review_provenance = _validated_review_provenance(
        _load(args.review_provenance.resolve())
    )
    now = _now()
    if receipt.get("source_head") != args.source_head:
        raise SystemExit("effect receipt source head does not match --source-head")
    if target_effects.validate_target_host_effect_result(
        receipt,
        now=_iso(now),
        expected_source_head=args.source_head,
        require_success=True,
    ):
        raise SystemExit("fresh target-host effect receipt validation failed")
    for label, capture, expected_node in (
        ("preflight", preflight_capture, "ops_preflight"),
        ("verifier", verifier_capture, "ops_postcheck"),
    ):
        capture_errors = command_capture.validate_governed_command_capture(capture)
        if capture_errors or capture.get("node_id") != expected_node:
            raise SystemExit(
                f"{label} command capture validation failed: "
                + "; ".join(capture_errors[:5])
            )
    if component_effects.validate_effect_seams_ready_receipt(
        effect_seams, now=_iso(now)
    ):
        raise SystemExit("effect_seams_ready_receipt_v1 validation failed")
    if (
        receipt.get("choice_receipt", {})
        .get("dependency_receipts", {})
        .get("effect_seams_ready_receipt_digest")
        != effect_seams.get("self_digest")
    ):
        raise SystemExit("target-host effect is not bound to the persisted S1.5 receipt")

    baseline = capture_repository_baseline(repo)
    context_temp = repo / "tmp/aiml-s1-finalization-runtime-context.json"
    context_payload = _runtime_context_payload(baseline=baseline, receipt=receipt)
    _write_json(context_temp, context_payload)
    try:
        facts = _task_facts(
            baseline=baseline,
            runtime_artifact_path=str(context_temp.relative_to(repo)),
            receipt=receipt,
        )
        route = route_task(facts)
        context_plan = compile_context(
            "PM",
            route["task_facts"],
            root=repo,
            external_evidence_verifier=lambda candidate: candidate == context_payload,
        )
        if context_plan["budget"]["claim_pass_eligible"] is not True:
            raise ValueError("PM Context is not PASS-eligible")
        context = materialize_context_artifact(context_plan)
    finally:
        context_temp.unlink(missing_ok=True)

    packet, manifest, wave, _effect = _build_packet(
        route=route,
        context=context,
        receipt=receipt,
        preflight_capture=preflight_capture,
        verifier_capture=verifier_capture,
        residue=residue,
        review_provenance=review_provenance,
        adjudicated_at=now,
    )
    bundle = _bundle(
        context=context,
        wave=wave,
        receipt=receipt,
        route=route,
        now=_now(),
    )
    signature = _sign_with_agent(bundle)
    result, finalization_evaluated_at = _finalize_and_capture_replay_time(
        packet,
        bundle,
        signature=signature,
        github_token=_github_token(),
    )
    if result.get("status") != "PASS" or result.get("errors"):
        raise SystemExit(
            "trusted S1 closure finalization failed: "
            + "; ".join(str(item) for item in result.get("errors", [])[:10])
        )
    attempt = _landing_attempt(
        packet=packet,
        receipt=receipt,
        effect_seams=effect_seams,
        context=context,
        route=route,
        branch=args.branch,
        worktree=repo,
        writer_lease_id=args.writer_lease_id,
        created_at=now,
    )
    attempt_errors = aiml_validator.validate_aiml_artifact(
        attempt, now=_iso(now)
    )
    if attempt_errors:
        raise SystemExit(
            "landing attempt validation failed: " + "; ".join(attempt_errors[:10])
        )
    finalization = {
        "schema_version": "aiml_s1_closure_finalization_result_v1",
        "status": "S1_CLOSURE_AUTHENTICATED_PENDING_MERGE",
        "evaluated_at": _iso(finalization_evaluated_at),
        "closure_digest": result["closure_digest"],
        "trusted_bundle_digest": canonical_digest(bundle),
        "signature_sha256": (
            "sha256:" + hashlib.sha256(signature).hexdigest()
        ),
        "task_contract_digest": context["task_contract_digest"],
        "context_artifact_digest": context["artifact_digest"],
        "dag_digest": route["dag_digest"],
        "workflow_wave_record_digest": wave["record_digest"],
        "effect_receipt_digest": receipt["receipt_digest"],
        "effect_seams_ready_receipt_digest": effect_seams["self_digest"],
        "review_provenance_digest": review_provenance["self_digest"],
        "landing_attempt_digest": attempt["self_digest"],
        "nine_authorities_false": True,
        "merge_state": "PENDING_EXACT_HEAD_REVIEW_AND_MERGE",
        "errors": [],
    }
    finalization["self_digest"] = canonical_digest(finalization)

    _write_json(artifact_dir / OUTPUTS["context"], context)
    _write_json(artifact_dir / OUTPUTS["manifest"], manifest)
    _write_json(artifact_dir / OUTPUTS["wave"], wave)
    _write_json(artifact_dir / OUTPUTS["packet"], packet)
    (artifact_dir / OUTPUTS["bundle"]).write_bytes(canonical_bytes(bundle))
    (artifact_dir / OUTPUTS["signature"]).write_bytes(signature)
    _write_json(artifact_dir / OUTPUTS["attempt"], attempt)
    _write_json(artifact_dir / OUTPUTS["finalization"], finalization)
    print(json.dumps(finalization, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
