"""Closed local schema semantics for the authenticated recovery anchor。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
TESTS = Path(__file__).resolve().parent
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, TESTS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_s2_5_recovery_anchor as anchor  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
from s2_5_recovery_anchor_testkit import (  # noqa: E402
    AppendingFakeWriter,
    FakeClock,
    FakeVerifier,
    MutableAnchorBackend,
    MutableFakeReader,
    manifest,
    seal,
)


SCHEMA_DIR = ROOT / ".codex" / "schemas"
SCHEMA_VERSIONS = frozenset({
    "s2_5_recovery_anchor_entry_v2",
    "s2_5_recovery_anchor_latest_v1",
    "s2_5_recovery_anchor_page_v1",
    "s2_5_recovery_anchor_prepared_append_v1",
    "s2_5_recovery_anchor_append_intent_v1",
    "s2_5_recovery_anchor_append_result_v1",
    "s2_5_recovery_anchor_readback_v1",
    "s2_5_recovery_anchor_postcheck_v1",
    "s2_5_recovery_anchor_rollback_v1",
})


def _samples():
    backend = MutableAnchorBackend()
    reader = MutableFakeReader(backend)
    protocol = anchor.AuthenticatedRecoveryAnchor(
        writer=AppendingFakeWriter(backend),
        reader=reader,
        verifier=FakeVerifier(),
        clock=FakeClock(),
    )
    prepared = protocol.prepare_append(manifest())
    packet = protocol.execute_prepared(prepared)
    latest_value, page_values = reader._latest_and_pages()
    return {
        "s2_5_recovery_anchor_entry_v2": packet["entry"],
        "s2_5_recovery_anchor_latest_v1": latest_value,
        "s2_5_recovery_anchor_page_v1": page_values[0],
        "s2_5_recovery_anchor_prepared_append_v1": prepared,
        "s2_5_recovery_anchor_append_intent_v1": packet["intent"],
        "s2_5_recovery_anchor_append_result_v1": packet["result"],
        "s2_5_recovery_anchor_readback_v1": packet["readback"],
        "s2_5_recovery_anchor_postcheck_v1": packet["postcheck"],
        "s2_5_recovery_anchor_rollback_v1": packet["rollback"],
    }


def _assert_every_object_closed(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
        for value in node.values():
            _assert_every_object_closed(value)
    elif isinstance(node, list):
        for value in node:
            _assert_every_object_closed(value)


@pytest.mark.parametrize("schema_version", sorted(SCHEMA_VERSIONS))
def test_anchor_schema_is_recursively_closed_and_accepts_its_typed_sample(
    schema_version,
):
    schema = json.loads(
        (SCHEMA_DIR / f"{schema_version}.schema.json").read_text(encoding="utf-8")
    )
    sample = _samples()[schema_version]
    assert schema_subset_errors(sample, schema, schema) == []
    assert anchor.validate_local_artifact(copy.deepcopy(sample)) == []
    _assert_every_object_closed(schema)


def test_anchor_schemas_are_local_only_and_central_schema_count_does_not_change():
    assert anchor._LOCAL_SCHEMAS == SCHEMA_VERSIONS
    assert SCHEMA_VERSIONS.isdisjoint(validator.SCHEMA_FILES)
    # The unrelated S2E disposable-test chain is the sole central increment.
    assert len(validator.SCHEMA_FILES) == 90


@pytest.mark.parametrize("schema_version", sorted(SCHEMA_VERSIONS))
def test_every_anchor_schema_rejects_extra_fields_and_boundary_escalation(
    schema_version,
):
    sample = _samples()[schema_version]
    extra = copy.deepcopy(sample)
    extra["caller_selected_path"] = "/tmp/escape"
    assert anchor.validate_local_artifact(seal(extra))

    escalated = copy.deepcopy(sample)
    escalated["evidence_class"] = "PLATFORM_OR_EXTERNAL_ATTESTED"
    escalated["production_effect"] = True
    escalated["production_effect_count"] = 1
    assert anchor.validate_local_artifact(seal(escalated))

    cross_profile = copy.deepcopy(sample)
    cross_profile["target_profile_id"] = "production-profile"
    assert anchor.validate_local_artifact(seal(cross_profile))


@pytest.mark.parametrize(
    "schema_version",
    [
        "s2_5_recovery_anchor_entry_v2",
        "s2_5_recovery_anchor_latest_v1",
        "s2_5_recovery_anchor_page_v1",
        "s2_5_recovery_anchor_append_intent_v1",
        "s2_5_recovery_anchor_append_result_v1",
        "s2_5_recovery_anchor_readback_v1",
        "s2_5_recovery_anchor_postcheck_v1",
        "s2_5_recovery_anchor_rollback_v1",
    ],
)
def test_resealed_semantic_contradictions_are_rejected(schema_version):
    artifact = copy.deepcopy(_samples()[schema_version])
    if schema_version == "s2_5_recovery_anchor_entry_v2":
        artifact["sequence"] = 2
        artifact["previous_anchor_digest"] = None
    elif schema_version == "s2_5_recovery_anchor_latest_v1":
        artifact["entry_count"] += 1
    elif schema_version == "s2_5_recovery_anchor_page_v1":
        artifact["cursor_out"] = "s2-5-anchor-cursor-" + "9" * 64
    elif schema_version == "s2_5_recovery_anchor_append_intent_v1":
        artifact["candidate_sequence"] += 1
    elif schema_version == "s2_5_recovery_anchor_append_result_v1":
        artifact["sequence"] = None
    elif schema_version == "s2_5_recovery_anchor_readback_v1":
        artifact["exact_version_match"] = True
    elif schema_version == "s2_5_recovery_anchor_postcheck_v1":
        artifact["full_chain_valid"] = True
    else:
        artifact["deletion_attempted"] = True
    assert anchor.validate_local_artifact(seal(artifact))


@pytest.mark.parametrize("invented_status", ["ROLLED_BACK", "DELETED", "RESTORED"])
def test_anchor_rollback_can_never_claim_immutable_entry_deletion(invented_status):
    rollback = copy.deepcopy(_samples()["s2_5_recovery_anchor_rollback_v1"])
    rollback["status"] = invented_status
    rollback["immutable_anchor_deleted"] = True
    rollback["deletion_attempted"] = True
    assert anchor.validate_local_artifact(seal(rollback))


@pytest.mark.parametrize(
    ("schema_version", "mutations"),
    [
        (
            "s2_5_recovery_anchor_readback_v1",
            {
                "status": "RECOVERY_REQUIRED",
                "exact_version_match": True,
                "checksum_match": True,
                "head_match": True,
                "failure_code": "forced_recovery",
            },
        ),
        (
            "s2_5_recovery_anchor_postcheck_v1",
            {
                "status": "RECOVERY_REQUIRED",
                "full_chain_valid": True,
                "identity_distinct": True,
                "failure_code": "forced_recovery",
            },
        ),
        (
            "s2_5_recovery_anchor_postcheck_v1",
            {
                "status": "UNVERIFIED",
                "full_chain_valid": True,
                "identity_distinct": True,
                "failure_code": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
            },
        ),
    ],
)
def test_resealed_failure_status_cannot_retain_pass_facts(
    schema_version, mutations
):
    artifact = copy.deepcopy(_samples()[schema_version])
    artifact.update(mutations)
    assert anchor.validate_local_artifact(seal(artifact))


def test_local_unverified_readback_cannot_be_resealed_as_pass():
    readback = copy.deepcopy(_samples()["s2_5_recovery_anchor_readback_v1"])
    assert readback["status"] == "UNVERIFIED"
    readback.update({
        "status": "PASS",
        "exact_version_match": True,
        "checksum_match": True,
        "head_match": True,
        "failure_code": None,
    })
    assert anchor.validate_local_artifact(seal(readback))


def test_local_unverified_postcheck_cannot_be_resealed_as_pass():
    postcheck = copy.deepcopy(_samples()["s2_5_recovery_anchor_postcheck_v1"])
    assert postcheck["status"] == "UNVERIFIED"
    postcheck.update({
        "status": "PASS",
        "full_chain_valid": True,
        "identity_distinct": True,
        "failure_code": None,
    })
    assert anchor.validate_local_artifact(seal(postcheck))
