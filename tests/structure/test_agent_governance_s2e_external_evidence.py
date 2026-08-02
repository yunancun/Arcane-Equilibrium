"""Adversarial tests for independent S2E external-evidence trust roots."""

from __future__ import annotations

import hashlib
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
STRUCTURE = ROOT / "tests" / "structure"
for candidate in (HELPERS, ML_ROOT, STRUCTURE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_terminal_receipt_external_sink as external_sink  # noqa: E402
import agent_governance_terminal_receipt_sink as terminal_sink  # noqa: E402
import aiml_gate_receipt_s2e_external_evidence as evidence  # noqa: E402
import test_agent_governance_s2e_launch_receipts as support  # noqa: E402


HEAD = "a" * 40
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
ANCHOR = datetime(2030, 1, 1, tzinfo=timezone.utc)


def _key_profile(tmp_path: Path, name: str, identity: str, namespace: str, klass: str):
    private, public, fingerprint = __import__("s2_5_testkit").mint_key(
        tmp_path, name
    )
    return private, {
        "schema_version": name + "_trust_root_v1",
        "signer_identity": identity,
        "signature_namespace": namespace,
        "algorithm": "SSH-ED25519",
        "key_generation": "independent_off_repo_ed25519_v1",
        "anchor": "fixed_off_repo_public_trust_root_v1",
        "public_key": public,
        "key_fingerprint": fingerprint,
        "attestor_class": klass,
    }


@pytest.fixture
def trust_profiles(tmp_path, monkeypatch):
    worm_private, worm_profile = _key_profile(
        tmp_path,
        "s2e_external_worm_provider",
        evidence.EXTERNAL_WORM_PROVIDER_IDENTITY,
        evidence.EXTERNAL_WORM_PROVIDER_NAMESPACE,
        "S3_OBJECT_LOCK_EXTERNAL_ATTESTOR_V1",
    )
    registry_private, registry_profile = _key_profile(
        tmp_path,
        "s2e_predecessor_registry",
        evidence.PREDECESSOR_REGISTRY_IDENTITY,
        evidence.PREDECESSOR_REGISTRY_NAMESPACE,
        "EXTERNAL_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
    )
    receipt_private, receipt_profile = _key_profile(
        tmp_path,
        "s2e_receipt_signer",
        "aiml-s2e-receipt-signer-v1",
        "arcane-equilibrium-aiml-s2e-receipts",
        "S2E_RECEIPT_SIGNER_V1",
    )
    del receipt_private
    monkeypatch.setattr(
        evidence,
        "_load_external_worm_provider_trust_root",
        lambda: (worm_profile, []),
    )
    monkeypatch.setattr(
        evidence,
        "_load_predecessor_registry_trust_root",
        lambda: (registry_profile, []),
    )
    monkeypatch.setattr(
        evidence,
        "_load_s2e_receipt_signer_profile",
        lambda: (receipt_profile, []),
    )
    return {
        "worm_private": worm_private,
        "worm_profile": worm_profile,
        "registry_private": registry_private,
        "registry_profile": registry_profile,
        "receipt_profile": receipt_profile,
        "tmp_path": tmp_path,
    }


def _worm_triplet(*, compliance: bool = True):
    payload = {
        "schema_version": "s2e-external-evidence-test-payload-v1",
        "payload_digest": D1,
    }
    intent = external_sink.build_external_worm_append_intent(
        intent_id="s2e-external-provider-test",
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=HEAD,
        landing_scope_id=D2,
        learning_runtime_digest=D3,
        terminal_payload_digest=terminal_sink.terminal_payload_digest(payload),
        append_actor_id="s2e-provider-writer",
        approved_by="PM",
        approved_at=ANCHOR.isoformat(),
        expires_at=(ANCHOR + timedelta(hours=2)).isoformat(),
        endpoint="https://s3.us-east-1.amazonaws.com",
        region="us-east-1",
        bucket="s2e-object-lock-evidence",
        object_lock_mode="COMPLIANCE" if compliance else "GOVERNANCE",
        retain_until=(ANCHOR + timedelta(days=30)).isoformat(),
        credential_channel_id="iam-role:s2e-evidence",
        compliance_operator_approved=compliance,
        now=(ANCHOR + timedelta(seconds=1)).isoformat(),
    )
    client = support._DisposableObjectLockS3()
    result = external_sink.apply_external_worm_append(
        intent,
        s3_client=client,
        append_actor_id="s2e-provider-writer",
        terminal_payload=payload,
        started_at=(ANCHOR + timedelta(seconds=2)).isoformat(),
        completed_at=(ANCHOR + timedelta(seconds=3)).isoformat(),
    )
    readback = external_sink.independent_readback_ack(
        result,
        intent,
        s3_client=client,
        verifier_actor_id="s2e-provider-independent-reader",
        observed_at=(ANCHOR + timedelta(seconds=4)).isoformat(),
    )
    return intent, result, readback


def _sign_provider(core: dict, trust_profiles: dict) -> dict:
    signed = evidence.external_worm_provider_signed_bytes(core)
    artifact = {
        **core,
        "signed_core_digest": "sha256:" + hashlib.sha256(signed).hexdigest(),
    }
    artifact["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": artifact["signed_core_digest"],
        "signature": support._sign_sshsig(
            trust_profiles["worm_private"],
            signed,
            namespace=evidence.EXTERNAL_WORM_PROVIDER_NAMESPACE,
            directory=trust_profiles["tmp_path"],
        ),
    }
    artifact["attestation_digest"] = (
        evidence.external_worm_provider_attestation_digest(artifact)
    )
    return artifact


def _provider_attestation(trust_profiles: dict, triplet=None) -> tuple[dict, tuple]:
    intent, result, readback = triplet or _worm_triplet()
    destination = intent["destination_contract"]
    core = {
        "schema_version": evidence.EXTERNAL_WORM_SCHEMA,
        "purpose": "ATTEST_S2E_EXTERNAL_WORM_IMMUTABLE_READBACK",
        "evidence_class": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "provider_class": "S3_OBJECT_LOCK_EXTERNAL_ATTESTOR_V1",
        "provider_locator": "aws:s3-object-lock-attestor:external-account",
        "external_intent_digest": intent["external_intent_digest"],
        "external_result_digest": result["result_digest"],
        "external_readback_ack_digest": readback["ack_digest"],
        "terminal_payload_digest": intent["append_intent"]["payload_binding"][
            "terminal_payload_digest"
        ],
        "destination": {
            field: destination[field]
            for field in (
                "endpoint",
                "region",
                "bucket",
                "credential_channel_id",
                "object_lock_mode",
                "retain_until",
            )
        },
        "immutable_object": {
            "record_locator": result["record_locator"],
            "object_version_id": result["object_version_id"],
            "checksum_sha256": result["checksum_sha256"],
            "append_status": result["append_status"],
            "readback_ack": readback["ack"],
            "immutability_proven": readback["immutability_proven"],
            "object_lock_enabled": readback["object_lock_enabled"],
        },
        "observed_at": (ANCHOR + timedelta(seconds=5)).isoformat(),
        "expires_at": (ANCHOR + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "EXTERNAL_WORM_PROVIDER_ATTESTOR",
            "identity": evidence.EXTERNAL_WORM_PROVIDER_IDENTITY,
            "namespace": evidence.EXTERNAL_WORM_PROVIDER_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": trust_profiles["worm_profile"]["key_fingerprint"],
        },
    }
    return _sign_provider(core, trust_profiles), (intent, result, readback)


def _sign_registry(core: dict, trust_profiles: dict) -> dict:
    signed = evidence.predecessor_registry_signed_bytes(core)
    artifact = {
        **core,
        "signed_core_digest": "sha256:" + hashlib.sha256(signed).hexdigest(),
    }
    artifact["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": artifact["signed_core_digest"],
        "signature": support._sign_sshsig(
            trust_profiles["registry_private"],
            signed,
            namespace=evidence.PREDECESSOR_REGISTRY_NAMESPACE,
            directory=trust_profiles["tmp_path"],
        ),
    }
    artifact["attestation_digest"] = (
        evidence.predecessor_registry_attestation_digest(artifact)
    )
    return artifact


def _registry_case(trust_profiles: dict):
    candidate = {
        "payload_digest": D1,
        "wave": "S2E-LW1",
        "source_head": HEAD,
    }
    predecessor = {"payload_digest": D2}
    expected_entry = {"entry_digest": D3}
    core = {
        "schema_version": evidence.PREDECESSOR_REGISTRY_SCHEMA,
        "purpose": "ATTEST_S2E_PREDECESSOR_SINGLE_USE_GRANT",
        "evidence_class": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "registry_class": "EXTERNAL_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
        "registry_locator": "registry:external-append-only:s2e",
        "launch_id": evidence.LAUNCH_ID,
        "slot_id": evidence.s2e_predecessor_registry_slot_id(D2),
        "predecessor_payload_digest": D2,
        "successor_candidate_payload_digest": D1,
        "successor_wave": "S2E-LW1",
        "successor_source_head": HEAD,
        "acceptance_review_bundle_digest": "sha256:" + "4" * 64,
        "prior_consumption_ledger_digest": "sha256:" + "5" * 64,
        "expected_consumption_entry_digest": D3,
        "expected_result_ledger_digest": "sha256:" + "6" * 64,
        "decision": "GRANTED_ONCE",
        "conflicting_grant_absent": True,
        "registry_generation": 1,
        "previous_registry_head_digest": None,
        "registry_entry_digest": "",
        "registry_head_digest": "",
        "observed_at": (ANCHOR + timedelta(seconds=5)).isoformat(),
        "expires_at": (ANCHOR + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "PREDECESSOR_REGISTRY_ATTESTOR",
            "identity": evidence.PREDECESSOR_REGISTRY_IDENTITY,
            "namespace": evidence.PREDECESSOR_REGISTRY_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": trust_profiles["registry_profile"]["key_fingerprint"],
        },
    }
    core["registry_entry_digest"] = evidence.predecessor_registry_entry_digest(core)
    core["registry_head_digest"] = evidence.predecessor_registry_head_digest(core)
    return _sign_registry(core, trust_profiles), candidate, predecessor, expected_entry


def test_independent_provider_and_registry_attestations_validate(trust_profiles):
    provider, triplet = _provider_attestation(trust_profiles)
    assert evidence.validate_s2e_external_worm_provider_attestation(
        provider,
        external_append_intent=triplet[0],
        external_append_result=triplet[1],
        external_readback_ack=triplet[2],
        now=ANCHOR + timedelta(minutes=1),
    ) == []
    registry, candidate, predecessor, entry = _registry_case(trust_profiles)
    assert evidence.validate_s2e_predecessor_registry_attestation(
        registry,
        candidate=candidate,
        predecessor_receipt=predecessor,
        acceptance_review_bundle_digest="sha256:" + "4" * 64,
        prior_consumption_ledger_digest="sha256:" + "5" * 64,
        expected_consumption_entry=entry,
        expected_result_ledger_digest="sha256:" + "6" * 64,
        now=ANCHOR + timedelta(minutes=1),
    ) == []


def test_provider_rejects_non_s3_class_locator_and_cross_bound_result(
    trust_profiles,
):
    artifact, triplet = _provider_attestation(trust_profiles)
    for mutate, expected in (
        (lambda value: value.update(provider_locator="memory:fake-s3"), "fixture or local"),
        (
            lambda value: value.update(provider_locator="file:///tmp/fake-s3"),
            "outside the admitted external S3 Object Lock provider class",
        ),
        (
            lambda value: value.update(provider_locator="unix:/run/fake-s3.sock"),
            "outside the admitted external S3 Object Lock provider class",
        ),
        (
            lambda value: value.update(provider_locator="https://s3.example.test"),
            "outside the admitted external S3 Object Lock provider class",
        ),
        (
            lambda value: value.update(provider_locator=" memory:fake-s3"),
            "does not match pattern",
        ),
        (
            lambda value: value.update(external_result_digest="sha256:" + "f" * 64),
            "binding differs",
        ),
    ):
        forged = deepcopy(artifact)
        for field in ("signed_core_digest", "signature", "attestation_digest"):
            forged.pop(field)
        mutate(forged)
        forged = _sign_provider(forged, trust_profiles)
        errors = evidence.validate_s2e_external_worm_provider_attestation(
            forged,
            external_append_intent=triplet[0],
            external_append_result=triplet[1],
            external_readback_ack=triplet[2],
            now=ANCHOR + timedelta(minutes=1),
        )
        assert any(expected in error for error in errors), errors


@pytest.mark.parametrize(
    "locator",
    (
        "memory:s2e-registry",
        " local:s2e-registry",
        "registry:test:s2e",
    ),
)
def test_registry_rejects_local_or_noncanonical_locator(
    trust_profiles, locator
):
    artifact, candidate, predecessor, entry = _registry_case(trust_profiles)
    for field in ("signed_core_digest", "signature", "attestation_digest"):
        artifact.pop(field)
    artifact["registry_locator"] = locator
    artifact["registry_entry_digest"] = evidence.predecessor_registry_entry_digest(
        artifact
    )
    artifact["registry_head_digest"] = evidence.predecessor_registry_head_digest(
        artifact
    )
    artifact = _sign_registry(artifact, trust_profiles)
    errors = evidence.validate_s2e_predecessor_registry_attestation(
        artifact,
        candidate=candidate,
        predecessor_receipt=predecessor,
        acceptance_review_bundle_digest="sha256:" + "4" * 64,
        prior_consumption_ledger_digest="sha256:" + "5" * 64,
        expected_consumption_entry=entry,
        expected_result_ledger_digest="sha256:" + "6" * 64,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert errors
    assert all("registry_locator" in error for error in errors), errors


def test_provider_rejects_governance_mode_even_with_valid_signature(trust_profiles):
    triplet = _worm_triplet(compliance=False)
    artifact, _ = _provider_attestation(trust_profiles, triplet)
    errors = evidence.validate_s2e_external_worm_provider_attestation(
        artifact,
        external_append_intent=triplet[0],
        external_append_result=triplet[1],
        external_readback_ack=triplet[2],
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("COMPLIANCE" in error for error in errors), errors


def test_provider_and_registry_reject_same_key_custody(trust_profiles, monkeypatch):
    provider, triplet = _provider_attestation(trust_profiles)
    monkeypatch.setattr(
        evidence,
        "_load_s2e_receipt_signer_profile",
        lambda: (trust_profiles["worm_profile"], []),
    )
    errors = evidence.validate_s2e_external_worm_provider_attestation(
        provider,
        external_append_intent=triplet[0],
        external_append_result=triplet[1],
        external_readback_ack=triplet[2],
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("not independent" in error for error in errors), errors

    registry, candidate, predecessor, entry = _registry_case(trust_profiles)
    monkeypatch.setattr(
        evidence,
        "_load_s2e_receipt_signer_profile",
        lambda: (trust_profiles["registry_profile"], []),
    )
    errors = evidence.validate_s2e_predecessor_registry_attestation(
        registry,
        candidate=candidate,
        predecessor_receipt=predecessor,
        acceptance_review_bundle_digest="sha256:" + "4" * 64,
        prior_consumption_ledger_digest="sha256:" + "5" * 64,
        expected_consumption_entry=entry,
        expected_result_ledger_digest="sha256:" + "6" * 64,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("not independent" in error for error in errors), errors


def test_registry_rejects_cross_candidate_head_fork_and_stale(trust_profiles):
    artifact, candidate, predecessor, entry = _registry_case(trust_profiles)
    cases = (
        ({"successor_candidate_payload_digest": "sha256:" + "f" * 64}, "binding differs"),
        ({"previous_registry_head_digest": "sha256:" + "e" * 64}, "continuity"),
        (
            {
                "observed_at": (ANCHOR - timedelta(hours=1)).isoformat(),
                "expires_at": (ANCHOR - timedelta(minutes=50)).isoformat(),
            },
            "stale",
        ),
    )
    for updates, expected in cases:
        forged = deepcopy(artifact)
        for field in ("signed_core_digest", "signature", "attestation_digest"):
            forged.pop(field)
        forged.update(updates)
        forged["registry_entry_digest"] = evidence.predecessor_registry_entry_digest(
            forged
        )
        forged["registry_head_digest"] = evidence.predecessor_registry_head_digest(
            forged
        )
        forged = _sign_registry(forged, trust_profiles)
        errors = evidence.validate_s2e_predecessor_registry_attestation(
            forged,
            candidate=candidate,
            predecessor_receipt=predecessor,
            acceptance_review_bundle_digest="sha256:" + "4" * 64,
            prior_consumption_ledger_digest="sha256:" + "5" * 64,
            expected_consumption_entry=entry,
            expected_result_ledger_digest="sha256:" + "6" * 64,
            now=ANCHOR + timedelta(minutes=1),
        )
        assert any(expected in error for error in errors), errors


def test_absent_attestations_never_validate():
    assert evidence.validate_s2e_external_worm_provider_attestation(
        None,
        external_append_intent=None,
        external_append_result=None,
        external_readback_ack=None,
        now=ANCHOR,
    )
    assert evidence.validate_s2e_predecessor_registry_attestation(
        None,
        candidate={},
        predecessor_receipt={},
        acceptance_review_bundle_digest=D1,
        prior_consumption_ledger_digest=D2,
        expected_consumption_entry={},
        expected_result_ledger_digest=D3,
        now=ANCHOR,
    )
