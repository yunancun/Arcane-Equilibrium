"""Structural tests for the additive aiml_landing_session_attempt_v1 (S1 Wave A).

Proves the generalized S1+ attempt row validates through its OWN sibling semantic
path (_aiml_landing_work_package_errors + the aiml_landing_session_attempt_v1
branch), NOT the S0.3-hardcoded _s0_3_work_package_errors: a LANDING_SCOPE scope,
a non-const work_package_id, runtime_claim=true, side_effect_class=target_host_probe,
author-declared, cross-checked at closure required_effects with adapter_id==attempt adapter_id, and an
explicit closure_binding all pass; while applier==postcheck, adapter mismatch,
tampered self_digest/attempt_id, and an S0.* session_id (§13 C6) all fail closed.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402


D = "sha256:" + "1" * 64
HEAD = "a" * 40
NOW = "2026-07-23T12:05:00+00:00"
ADAPTER = "target_host_disposable_runtime_probe_adapter_v1"
OWNED = "helper_scripts/maintenance_scripts/agent_governance_target_host_effects.py"


def _build(
    *,
    session_id: str = "S1.6B",
    actor: str = "apply_node",
    verifier: str = "postcheck_node",
    adapter: str = ADAPTER,
) -> dict:
    scope_ref = {"kind": "LANDING_SCOPE", "landing_scope_id": D}
    attempt_key = {
        "session_id": session_id, "scope_ref": scope_ref,
        "cohort_epoch": "epoch-1", "attempt": 1,
    }
    artifact = {
        "schema_version": "aiml_landing_session_attempt_v1",
        "attempt_id": "PLACEHOLDER",
        "session_id": session_id,
        "scope_ref": scope_ref,
        "cohort_epoch": "epoch-1",
        "attempt": 1,
        "attempt_key": attempt_key,
        "attempt_phase": "SOURCE_BUILD",
        "status": "IN_PROGRESS",
        "owner": "E1",
        "lease": {
            "lease_id": "lease-1", "epoch": 1,
            "acquired_at": "2026-07-23T11:00:00+00:00",
            "heartbeat_at": "2026-07-23T11:30:00+00:00",
            "expires_at": "2026-07-23T13:00:00+00:00",
        },
        "source": {
            "branch": "agent/aiml-s1-formal-closure", "worktree": "/w",
            "baseline_head": HEAD, "checkpoint_head": "b" * 40,
        },
        "path_manifest": [OWNED],
        "work_package": {
            "work_package_id": "AIML-S1.6B-TARGET-HOST-EFFECT",
            "phase": "SOURCE_BUILD",
            "side_effect_class": "target_host_probe",
            "runtime_claim": True,
            "owned_path_manifest": [OWNED],
            "direct_interfaces": ["agent_governance_target_host_effects"],
        },
        "dependency_generations": [{
            "session_id": "S1.5",
            "schema_version": "effect_seams_ready_receipt_v1",
            "receipt_digest": D,
        }],
        "bootstrap_admission": {
            "task_id": "AIML-S1-6B-TARGET-HOST", "task_contract_digest": D,
            "dag_digest": D, "context_artifact_digest": D, "baseline_head": HEAD,
            "writer_lease_id": "lease-1",
        },
        "native_admission": {
            "node_id": "implementation", "role": "E1", "native_agent": "e1",
            "node_class": "work", "permission": "source_writer",
        },
        "dag_nodes": [{
            "node_id": "implementation", "node_class": "work",
            "permission": "source_writer", "requires": [], "writer_paths": [OWNED],
        }],
        "semantic_rechecks": ["path_ownership"],
        "ci_classifier": {
            "classifier_digest": D, "selected_workflows": ["structure"],
            "invocation_history": [], "failure_fingerprints": [],
        },
        "effect_classification_digest": D,
        "required_effects": [{
            "effect_class": "TARGET_HOST_DISPOSABLE_RUNTIME_PROBE",
            "adapter_id": adapter, "actor_node_id": actor,
            "rollback_contract": "atomic_pointer_swap+teardown+rmtree",
            "independent_postcheck_node_id": verifier, "status": "REQUIRED_PENDING",
        }],
        "adapter_id": adapter,
        "actor_node": actor,
        "rollback": "atomic_pointer_swap+teardown+rmtree",
        "independent_postcheck_node": verifier,
        "closure_binding": {
            "closure_packet_digest": D, "effect_receipt_digest": D,
            "effect_adapter_id": adapter,
        },
        "created_at": "2026-07-23T11:00:00+00:00",
        "self_digest": "PLACEHOLDER",
    }
    artifact["attempt_id"] = validator.session_attempt_identity_digest(artifact)
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


def _resign(artifact: dict) -> dict:
    artifact = copy.deepcopy(artifact)
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


def test_landing_attempt_positive() -> None:
    assert validator.validate_aiml_artifact(_build(), now=NOW) == []


def test_landing_attempt_uses_sibling_not_s0_3_const_path() -> None:
    # 一個既不是 S0.3 work_package_id、也不是 S0.3 direct_interfaces 的 landing attempt 仍通過:
    # 證明它走 sibling _aiml_landing_work_package_errors 而非 S0.3-hardcoded 分支。
    artifact = _build()
    assert artifact["work_package"]["work_package_id"] != "AIML-S0.3-GOVERNANCE-ADOPTION"
    assert artifact["bootstrap_admission"]["task_id"] != "AIML-S0-3-GOVERNANCE-V1"
    assert artifact["work_package"]["runtime_claim"] is True
    assert validator.validate_aiml_artifact(artifact, now=NOW) == []


def test_landing_attempt_rejects_applier_equals_postcheck() -> None:
    artifact = _resign(_build(actor="same", verifier="same"))
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("actor_node must differ from independent_postcheck_node" in e for e in errors)


def test_landing_attempt_rejects_required_effect_adapter_mismatch() -> None:
    artifact = _build()
    artifact["required_effects"][0]["adapter_id"] = "some_other_adapter_v1"
    artifact = _resign(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("required_effects adapter_id must equal" in e for e in errors)


def test_landing_attempt_rejects_closure_binding_adapter_mismatch() -> None:
    artifact = _build()
    artifact["closure_binding"]["effect_adapter_id"] = "some_other_adapter_v1"
    artifact = _resign(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("closure_binding effect_adapter_id must equal" in e for e in errors)


def test_landing_attempt_rejects_s0_session_id() -> None:
    # §13 C6:寬鬆的 S1 schema 不得用來重表 S0.x attempt(否則等於用寬鬆 pin 繞過 sealed S0.3)。
    artifact = _build(session_id="S0.3")
    artifact["attempt_key"]["session_id"] = "S0.3"
    artifact["attempt_id"] = validator.session_attempt_identity_digest(artifact)
    artifact = _resign(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("cannot re-express an S0.x session" in e for e in errors)


def test_landing_attempt_rejects_tampered_self_digest() -> None:
    artifact = _build()
    artifact["self_digest"] = "sha256:" + "0" * 64
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("self_digest is invalid" in e for e in errors)


def test_landing_attempt_rejects_tampered_attempt_id() -> None:
    artifact = _build()
    artifact["attempt_id"] = "sha256:" + "0" * 64
    artifact = _resign(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("attempt_id does not bind" in e for e in errors)


def test_landing_attempt_rejects_writer_paths_outside_manifest() -> None:
    artifact = _build()
    artifact["dag_nodes"][0]["writer_paths"] = ["helper_scripts/not_in_manifest.py"]
    artifact = _resign(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("writer paths exceed path_manifest" in e for e in errors)


def test_landing_attempt_rejects_unadmitted_side_effect_class() -> None:
    # broker_probe 之類不在 landing 白名單內 → schema enum 先拒。
    artifact = _build()
    artifact["work_package"]["side_effect_class"] = "deploy"
    artifact = _resign(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert errors
