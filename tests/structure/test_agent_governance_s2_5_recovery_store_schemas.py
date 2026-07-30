"""Closed local schemas for the disposable S2.5 recovery store."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


SCHEMA_DIR = ROOT / ".codex" / "schemas"
DIGEST = "sha256:" + "1" * 64
HEAD = "a" * 40
STORE_ID = "s2-5-store-" + "2" * 64
COMMON = {
    "side_effect_class": "DISPOSABLE_TEST",
    "target_class": "disposable_systemd",
    "target_profile_id": "s2_5_recovery_user_systemd_disposable_v1",
    "production_effect": False,
    "production_authority": False,
    "production_effect_count": 0,
}


def _seal(value):
    value["self_digest"] = validator.artifact_self_digest(value)
    return value


SAMPLES = {
    "s2_5_recovery_store_manifest_v1": _seal({
        "schema_version": "s2_5_recovery_store_manifest_v1",
        "store_id": STORE_ID,
        "state_root_id": DIGEST,
        "source_head": HEAD,
        "generation": 1,
        "phase": "PREPARED",
        "previous_manifest_digest": None,
        "unresolved_state_digest": DIGEST,
        "anchor_head_digest": None,
        "consumed_authorization_ids": [],
        "state_root_identity": {
            "canonical_path": (
                "/run/user/1000/arcane-equilibrium-aiml-s2e/s2_5-recovery"
            ),
            "device": 1,
            "inode": 2,
            "mode": "0700",
            "uid": 1000,
            "gid": 1000,
            "nlink": 2,
            "is_directory": True,
        },
        "journal_inventory": [],
        "journal_set_digest": DIGEST,
        "replay_ledger": {
            "basename": "authorization-replay-ledger.json",
            "present": False,
            "file_digest": None,
            "entry_count": 0,
            "head_digest": None,
        },
        **COMMON,
    }),
    "s2_5_recovery_anchor_entry_v1": _seal({
        "schema_version": "s2_5_recovery_anchor_entry_v1",
        "store_id": STORE_ID,
        "state_root_id": DIGEST,
        "source_head": HEAD,
        "sequence": 1,
        "previous_anchor_digest": None,
        "manifest_digest": DIGEST,
        "unresolved_state_digest": DIGEST,
        "authorization_id": None,
        "entry_status": "PREPARED",
        "append_actor_identity": "append-owner",
        "readback_verifier_identity": "independent-reader",
        **COMMON,
    }),
    "s2_5_recovery_store_intent_v1": _seal({
        "schema_version": "s2_5_recovery_store_intent_v1",
        "store_id": STORE_ID,
        "state_root_id": DIGEST,
        "source_head": HEAD,
        "operation": "PREPARE",
        "expected_previous_manifest_digest": None,
        "candidate_manifest_digest": DIGEST,
        "issued_at": "2030-01-01T00:00:00Z",
        "expires_at": "2030-01-01T00:05:00Z",
        **COMMON,
    }),
    "s2_5_recovery_store_result_v1": _seal({
        "schema_version": "s2_5_recovery_store_result_v1",
        "intent_digest": DIGEST,
        "status": "COMMITTED",
        "manifest_digest": DIGEST,
        "file_fsynced": True,
        "atomic_replace": True,
        "directory_fsynced": True,
        "parent_identity_rechecked": True,
        "failure_code": None,
        **COMMON,
    }),
    "s2_5_recovery_store_postcheck_v1": _seal({
        "schema_version": "s2_5_recovery_store_postcheck_v1",
        "result_digest": DIGEST,
        "manifest_digest": DIGEST,
        "readback_digest": DIGEST,
        "manifest_match": True,
        "parent_identity_match": True,
        "temp_residue_absent": True,
        "status": "PASS",
        "failure_code": None,
        **COMMON,
    }),
    "s2_5_recovery_store_rollback_v1": _seal({
        "schema_version": "s2_5_recovery_store_rollback_v1",
        "intent_digest": DIGEST,
        "result_digest": DIGEST,
        "status": "NOT_REQUIRED",
        "restored_manifest_digest": None,
        "temp_residue_absent": True,
        "operator_action_required": False,
        **COMMON,
    }),
}


@pytest.mark.parametrize("schema_version", sorted(SAMPLES))
def test_local_recovery_store_schema_is_closed_and_accepts_typed_sample(schema_version):
    schema = json.loads(
        (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(encoding="utf-8")
    )
    assert schema_subset_errors(SAMPLES[schema_version], schema, schema) == []
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("schema_version", sorted(SAMPLES))
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("side_effect_class", "NONE"),
        ("target_class", "production"),
        ("target_profile_id", "caller-selected-profile"),
        ("production_effect", True),
        ("production_authority", True),
        ("production_effect_count", 1),
    ],
)
def test_local_recovery_store_schemas_reject_effect_or_authority_relabel(
    schema_version, field, replacement
):
    schema = json.loads(
        (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(encoding="utf-8")
    )
    forged = copy.deepcopy(SAMPLES[schema_version])
    forged[field] = replacement
    forged["self_digest"] = validator.artifact_self_digest(
        {key: value for key, value in forged.items() if key != "self_digest"}
    )
    assert schema_subset_errors(forged, schema, schema)


def test_local_store_schemas_do_not_expand_central_runtime_closure():
    assert len(validator.SCHEMA_FILES) == 88
    assert set(SAMPLES).isdisjoint(validator.SCHEMA_FILES)
