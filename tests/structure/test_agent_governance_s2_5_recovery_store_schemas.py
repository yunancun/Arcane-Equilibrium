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
import agent_governance_s2_5_recovery_store as store  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


SCHEMA_DIR = ROOT / ".codex" / "schemas"
DIGEST = "sha256:" + "1" * 64
HEAD = "a" * 40
STATE_ROOT_IDENTITY = {
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
}
STATE_ROOT_ID = validator.canonical_digest(STATE_ROOT_IDENTITY)
STORE_ID = "s2-5-store-" + validator.canonical_digest({
    "profile_id": "s2_5_recovery_user_systemd_disposable_v1",
    "state_root_id": STATE_ROOT_ID,
}).removeprefix("sha256:")
EMPTY_JOURNAL_SET_DIGEST = validator.canonical_digest({
    "schema_version": "s2_5_recovery_journal_set_v1",
    "entries": [],
})
COMMON = {
    "side_effect_class": "DISPOSABLE_TEST",
    "target_class": "disposable_systemd",
    "target_profile_id": "s2_5_recovery_user_systemd_disposable_v1",
    "production_effect": False,
    "production_authority": False,
    "production_effect_count": 0,
}
SIMULATION_SESSION = {
    "session_class": "SIMULATION_ONLY",
    "store_write_authority": False,
}


def _seal(value):
    value["self_digest"] = validator.artifact_self_digest(value)
    return value


SAMPLES = {
    "s2_5_recovery_store_manifest_v1": _seal({
        "schema_version": "s2_5_recovery_store_manifest_v1",
        "store_id": STORE_ID,
        "state_root_id": STATE_ROOT_ID,
        "source_head": HEAD,
        "generation": 1,
        "phase": "PREPARED",
        "previous_manifest_digest": None,
        "unresolved_state_digest": DIGEST,
        "anchor_head_digest": None,
        "consumed_authorization_ids": [],
        "state_root_identity": STATE_ROOT_IDENTITY,
        "journal_inventory": [],
        "journal_set_digest": EMPTY_JOURNAL_SET_DIGEST,
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
        "state_root_id": STATE_ROOT_ID,
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
        "state_root_id": STATE_ROOT_ID,
        "source_head": HEAD,
        "operation": "PREPARE",
        "expected_previous_manifest_digest": None,
        "prior_manifest_discriminator_digest": DIGEST,
        "candidate_manifest_digest": DIGEST,
        "issued_at": "2030-01-01T00:00:00Z",
        "expires_at": "2030-01-01T00:05:00Z",
        "recovery_lock_intent_digest": DIGEST,
        "recovery_lock_result_digest": DIGEST,
        "recovery_lock_postcheck_digest": DIGEST,
        "recovery_lock_chain_digest": DIGEST,
        **SIMULATION_SESSION,
        **COMMON,
    }),
    "s2_5_recovery_store_result_v1": _seal({
        "schema_version": "s2_5_recovery_store_result_v1",
        "intent_digest": DIGEST,
        "prior_manifest_discriminator_digest": DIGEST,
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "manifest_digest": DIGEST,
        "file_fsynced": True,
        "atomic_replace": True,
        "directory_fsynced": True,
        "parent_identity_rechecked": True,
        "candidate_temp_identity": {
            "device": 1,
            "inode": 3,
            "mode": "0600",
            "uid": 1000,
            "gid": 1000,
            "nlink": 1,
            "is_regular_file": True,
        },
        "failure_code": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        **SIMULATION_SESSION,
        **COMMON,
    }),
    "s2_5_recovery_store_postcheck_v1": _seal({
        "schema_version": "s2_5_recovery_store_postcheck_v1",
        "result_digest": DIGEST,
        "manifest_digest": DIGEST,
        "readback_digest": DIGEST,
        "manifest_match": True,
        "manifest_identity_match": True,
        "parent_identity_match": True,
        "temp_residue_absent": True,
        "status": "PASS",
        "failure_code": None,
        **SIMULATION_SESSION,
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
        **SIMULATION_SESSION,
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
def test_local_semantic_validator_accepts_each_closed_sample(schema_version):
    assert store.validate_local_artifact(copy.deepcopy(SAMPLES[schema_version])) == []


@pytest.mark.parametrize(
    ("case", "schema_version"),
    [
        ("local_result_committed", "s2_5_recovery_store_result_v1"),
        ("pending_without_durability", "s2_5_recovery_store_result_v1"),
        ("pass_without_matches", "s2_5_recovery_store_postcheck_v1"),
        ("not_required_but_unsafe", "s2_5_recovery_store_rollback_v1"),
        ("same_anchor_identities", "s2_5_recovery_anchor_entry_v1"),
        ("anchor_sequence_without_predecessor", "s2_5_recovery_anchor_entry_v1"),
        ("reversed_intent_ttl", "s2_5_recovery_store_intent_v1"),
        ("oversized_intent_ttl", "s2_5_recovery_store_intent_v1"),
        ("resolved_gen9_without_lineage", "s2_5_recovery_store_manifest_v1"),
    ],
)
def test_resealed_semantic_contradictions_are_rejected(case, schema_version):
    forged = copy.deepcopy(SAMPLES[schema_version])
    if case == "local_result_committed":
        forged["status"] = "COMMITTED"
    elif case == "pending_without_durability":
        for field in (
            "file_fsynced",
            "atomic_replace",
            "directory_fsynced",
            "parent_identity_rechecked",
        ):
            forged[field] = False
    elif case == "pass_without_matches":
        forged["manifest_match"] = False
        forged["manifest_identity_match"] = False
        forged["parent_identity_match"] = False
        forged["temp_residue_absent"] = False
    elif case == "not_required_but_unsafe":
        forged["temp_residue_absent"] = False
        forged["operator_action_required"] = True
    elif case == "same_anchor_identities":
        forged["readback_verifier_identity"] = forged["append_actor_identity"]
    elif case == "anchor_sequence_without_predecessor":
        forged["sequence"] = 2
        forged["previous_anchor_digest"] = None
    elif case == "reversed_intent_ttl":
        forged["expires_at"] = "2029-12-31T23:59:59Z"
    elif case == "oversized_intent_ttl":
        forged["expires_at"] = "2030-01-01T00:05:01Z"
    else:
        forged.update({
            "generation": 9,
            "phase": "RESOLVED",
            "previous_manifest_digest": None,
            "unresolved_state_digest": None,
            "anchor_head_digest": None,
            "consumed_authorization_ids": [],
        })
    forged["self_digest"] = validator.artifact_self_digest(forged)

    assert store.validate_local_artifact(forged), case
    if case not in {
        "same_anchor_identities",
        "reversed_intent_ttl",
        "oversized_intent_ttl",
    }:
        schema = json.loads(
            (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(
                encoding="utf-8"
            )
        )
        assert schema_subset_errors(forged, schema, schema), case


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
    # S2E launch and independent external-evidence contracts are unrelated
    # central increments; these local schemas remain outside that registry.
    assert len(validator.SCHEMA_FILES) == 93
    assert set(SAMPLES).isdisjoint(validator.SCHEMA_FILES)


@pytest.mark.parametrize(
    "schema_version",
    [
        "s2_5_recovery_store_intent_v1",
        "s2_5_recovery_store_result_v1",
        "s2_5_recovery_store_postcheck_v1",
        "s2_5_recovery_store_rollback_v1",
    ],
)
def test_simulation_session_cannot_claim_store_write_authority(schema_version):
    forged = copy.deepcopy(SAMPLES[schema_version])
    forged["store_write_authority"] = True
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert store.validate_local_artifact(forged)
