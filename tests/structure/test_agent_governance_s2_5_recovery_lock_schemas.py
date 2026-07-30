"""Closed-schema acceptance for the disposable recovery dual-lock chain."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
TESTS = ROOT / "tests" / "structure"
for candidate in (HELPERS, ML_ROOT, TESTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_s2_5_recovery_lock as recovery_lock  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
from test_agent_governance_s2_5_recovery_lock import (  # noqa: E402
    HEAD,
    _RecordingLockDriver,
)


SCHEMA_DIR = ROOT / ".codex" / "schemas"
SCHEMA_VERSIONS = (
    "s2_5_recovery_lock_intent_v1",
    "s2_5_recovery_lock_result_v1",
    "s2_5_recovery_lock_postcheck_v1",
    "s2_5_recovery_lock_rollback_v1",
)


def _samples():
    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=_RecordingLockDriver(),
        source_head=HEAD,
    )
    return {
        outcome["intent"]["schema_version"]: outcome["intent"],
        outcome["result"]["schema_version"]: outcome["result"],
        outcome["postcheck"]["schema_version"]: outcome["postcheck"],
        outcome["rollback"]["schema_version"]: outcome["rollback"],
    }


def _assert_recursively_closed(schema):
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "object" or "properties" in schema:
        assert schema.get("additionalProperties") is False
    for key in ("properties", "$defs"):
        for child in schema.get(key, {}).values():
            _assert_recursively_closed(child)
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        for child in schema.get(key, []):
            _assert_recursively_closed(child)
    if isinstance(schema.get("items"), dict):
        _assert_recursively_closed(schema["items"])


@pytest.mark.parametrize("schema_version", SCHEMA_VERSIONS)
def test_lock_schema_is_recursively_closed_and_accepts_issued_receipt(schema_version):
    sample = _samples()[schema_version]
    schema = json.loads(
        (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(encoding="utf-8")
    )
    _assert_recursively_closed(schema)
    assert schema_subset_errors(sample, schema, schema) == []
    assert recovery_lock.validate_local_artifact(sample) == []


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("side_effect_class", "NONE"),
        ("target_class", "production"),
        ("production_effect", True),
        ("production_authority", True),
        ("production_effect_count", 1),
        ("runtime_observed", True),
    ],
)
def test_all_lock_receipts_reject_effect_runtime_or_authority_relabel(
    field, replacement
):
    for sample in _samples().values():
        forged = copy.deepcopy(sample)
        forged[field] = replacement
        forged["self_digest"] = validator.artifact_self_digest(forged)
        assert recovery_lock.validate_local_artifact(forged), (
            forged["schema_version"],
            field,
        )


@pytest.mark.parametrize(
    ("schema_version", "changes"),
    [
        (
            "s2_5_recovery_lock_result_v1",
            {"status": recovery_lock.STATUS_CONTENDED, "failure_code": "contended"},
        ),
        (
            "s2_5_recovery_lock_postcheck_v1",
            {"store_write_authority": True},
        ),
        (
            "s2_5_recovery_lock_rollback_v1",
            {"session_closed": False},
        ),
    ],
)
def test_lock_status_session_and_authority_contradictions_are_rejected(
    schema_version,
    changes,
):
    forged = copy.deepcopy(_samples()[schema_version])
    forged.update(changes)
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert recovery_lock.validate_local_artifact(forged)


def test_every_non_acquired_result_requires_a_typed_failure():
    schema_version = "s2_5_recovery_lock_result_v1"
    forged = copy.deepcopy(_samples()[schema_version])
    forged.update({
        "status": recovery_lock.STATUS_CONTENDED,
        "s2_4_lock_acquired": False,
        "s2_5_lock_acquired": False,
        "failure_code": None,
    })
    forged["self_digest"] = validator.artifact_self_digest(forged)
    schema = json.loads(
        (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert recovery_lock.validate_local_artifact(forged)
    assert schema_subset_errors(forged, schema, schema)


def test_not_required_rollback_forbids_release_claims_and_failure():
    outcome, lease = recovery_lock._acquire_recovery_dual_lock(
        driver=_RecordingLockDriver(),
        source_head=HEAD,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    assert lease is not None
    schema_version = "s2_5_recovery_lock_rollback_v1"
    valid = outcome["rollback"]
    assert valid["status"] == "NOT_REQUIRED"
    assert recovery_lock.validate_local_artifact(valid) == []
    forged = copy.deepcopy(valid)
    forged.update({
        "s2_5_release_attempted": True,
        "s2_5_released": True,
        "failure_code": "forged_not_required_failure",
    })
    forged["self_digest"] = validator.artifact_self_digest(forged)
    schema = json.loads(
        (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(
            encoding="utf-8"
        )
    )
    try:
        assert recovery_lock.validate_local_artifact(forged)
        assert schema_subset_errors(forged, schema, schema)
    finally:
        assert recovery_lock._release_lease(lease)["status"] == "RELEASED"


def test_each_not_required_rollback_contradiction_is_individually_rejected():
    outcome, lease = recovery_lock._acquire_recovery_dual_lock(
        driver=_RecordingLockDriver(),
        source_head=HEAD,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    assert lease is not None
    schema_version = "s2_5_recovery_lock_rollback_v1"
    schema = json.loads(
        (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(
            encoding="utf-8"
        )
    )
    mutations = (
        {"s2_5_release_attempted": True},
        {"s2_5_released": True},
        {"s2_4_release_attempted": True},
        {"s2_4_released": True},
        {"failure_code": "forged_not_required_failure"},
    )
    try:
        for mutation in mutations:
            forged = copy.deepcopy(outcome["rollback"])
            forged.update(mutation)
            forged["self_digest"] = validator.artifact_self_digest(forged)
            assert recovery_lock.validate_local_artifact(forged), mutation
            assert schema_subset_errors(forged, schema, schema), mutation
    finally:
        assert recovery_lock._release_lease(lease)["status"] == "RELEASED"
