"""Adversarial tests for independent S2E durability/registry trust roots."""

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

import aiml_gate_receipt_s2e_external_evidence as evidence  # noqa: E402
import test_agent_governance_s2e_launch_receipts as support  # noqa: E402


HEAD = "a" * 40
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
ANCHOR = datetime(2030, 1, 1, tzinfo=timezone.utc)
ANCHOR_LOCATOR = "host:append-only-durability-anchor:s2e-aiml"
REPLICA_LOCATOR = "replica:offhost-append-only:nas-s2e-aiml"
# 兩台機器的 SSH host key 指紋(disposable fixture 值,形制與真實 keyscan 輸出相同)。
ANCHOR_HOST_FINGERPRINT = "SHA256:" + "A" * 43
REPLICA_HOST_FINGERPRINT = "SHA256:" + "B" * 43


def _key_profile(
    tmp_path: Path,
    name: str,
    identity: str,
    namespace: str,
    klass: str,
    host_fingerprint: str | None = None,
):
    private, public, fingerprint = __import__("s2_5_testkit").mint_key(
        tmp_path, name
    )
    profile = {
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
    if host_fingerprint is not None:
        profile["host_fingerprint"] = host_fingerprint
    return private, profile


@pytest.fixture
def trust_profiles(tmp_path, monkeypatch):
    anchor_private, anchor_profile = _key_profile(
        tmp_path,
        "s2e_durability_anchor",
        evidence.DURABILITY_ANCHOR_IDENTITY,
        evidence.DURABILITY_ANCHOR_NAMESPACE,
        "HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1",
        host_fingerprint=ANCHOR_HOST_FINGERPRINT,
    )
    replica_private, replica_profile = _key_profile(
        tmp_path,
        "s2e_offhost_replica",
        evidence.OFFHOST_REPLICA_IDENTITY,
        evidence.OFFHOST_REPLICA_NAMESPACE,
        "OFFHOST_APPEND_ONLY_REPLICA_READBACK_V1",
        host_fingerprint=REPLICA_HOST_FINGERPRINT,
    )
    registry_private, registry_profile = _key_profile(
        tmp_path,
        "s2e_predecessor_registry",
        evidence.PREDECESSOR_REGISTRY_IDENTITY,
        evidence.PREDECESSOR_REGISTRY_NAMESPACE,
        "HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
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
        "_load_durability_anchor_trust_root",
        lambda: (anchor_profile, []),
    )
    monkeypatch.setattr(
        evidence,
        "_load_offhost_replica_trust_root",
        lambda: (replica_profile, []),
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
        "anchor_private": anchor_private,
        "anchor_profile": anchor_profile,
        "replica_private": replica_private,
        "replica_profile": replica_profile,
        "registry_private": registry_private,
        "registry_profile": registry_profile,
        "receipt_profile": receipt_profile,
        "tmp_path": tmp_path,
    }


def _sign_anchor(core: dict, trust_profiles: dict) -> dict:
    signed = evidence.durability_anchor_signed_bytes(core)
    artifact = {
        **core,
        "signed_core_digest": "sha256:" + hashlib.sha256(signed).hexdigest(),
    }
    artifact["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": artifact["signed_core_digest"],
        "signature": support._sign_sshsig(
            trust_profiles["anchor_private"],
            signed,
            namespace=evidence.DURABILITY_ANCHOR_NAMESPACE,
            directory=trust_profiles["tmp_path"],
        ),
    }
    artifact["attestation_digest"] = (
        evidence.durability_anchor_attestation_digest(artifact)
    )
    return artifact


def _sign_replica_readback(readback: dict, trust_profiles: dict) -> dict:
    for field in ("signed_core_digest", "signature"):
        readback.pop(field, None)
    signed = evidence.offhost_replica_readback_signed_bytes(readback)
    readback["signed_core_digest"] = "sha256:" + hashlib.sha256(signed).hexdigest()
    readback["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": readback["signed_core_digest"],
        "signature": support._sign_sshsig(
            trust_profiles["replica_private"],
            signed,
            namespace=evidence.OFFHOST_REPLICA_NAMESPACE,
            directory=trust_profiles["tmp_path"],
        ),
    }
    return readback


def _mirror_replica_readback(core: dict, trust_profiles: dict) -> dict:
    """副本忠實鏡像 anchor 的四個值,並由第二把 key 在自己的時間窗內重簽。"""

    readback = core.get("offhost_replica_readback") or {}
    readback.update({
        "schema_version": evidence.OFFHOST_REPLICA_READBACK_SCHEMA,
        "replica_locator": core["offhost_replica_locator"],
        "replica_host_fingerprint": readback.get(
            "replica_host_fingerprint", REPLICA_HOST_FINGERPRINT
        ),
        "observed_anchor_locator": core["anchor_locator"],
        "replica_generation": core["anchor_generation"],
        "replica_previous_head_digest": core["previous_anchor_head_digest"],
        "replica_entry_digest": core["anchor_entry_digest"],
        "replica_head_digest": core["anchor_head_digest"],
        "observed_at": readback.get(
            "observed_at", (ANCHOR + timedelta(seconds=4)).isoformat()
        ),
        "expires_at": readback.get(
            "expires_at", (ANCHOR + timedelta(minutes=5)).isoformat()
        ),
        "signer": {
            "role": "OFFHOST_REPLICA_READBACK_ATTESTOR",
            "identity": evidence.OFFHOST_REPLICA_IDENTITY,
            "namespace": evidence.OFFHOST_REPLICA_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": trust_profiles["replica_profile"]["key_fingerprint"],
        },
    })
    return _sign_replica_readback(readback, trust_profiles)


def _reseal_anchor(core: dict, trust_profiles: dict) -> dict:
    """重算 entry/head 與 replica 鏡像後重簽,確保只有被測欄位是變因。"""

    core["anchor_entry_digest"] = evidence.durability_anchor_entry_digest(core)
    core["anchor_head_digest"] = evidence.durability_anchor_head_digest(core)
    core["offhost_replica_readback"] = _mirror_replica_readback(core, trust_profiles)
    return _sign_anchor(core, trust_profiles)


def _anchor_case(trust_profiles: dict) -> dict:
    core = {
        "schema_version": evidence.DURABILITY_ANCHOR_SCHEMA,
        "purpose": "ATTEST_S2E_APPEND_ONLY_DURABILITY_AND_OFFHOST_READBACK",
        "evidence_class": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "anchor_class": "HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1",
        "anchor_locator": ANCHOR_LOCATOR,
        "anchor_host_fingerprint": ANCHOR_HOST_FINGERPRINT,
        "launch_id": evidence.LAUNCH_ID,
        "terminal_payload_digest": D1,
        "anchor_generation": 1,
        "previous_anchor_head_digest": None,
        "anchor_entry_digest": "",
        "anchor_head_digest": "",
        "offhost_replica_locator": REPLICA_LOCATOR,
        "offhost_replica_readback": {},
        "observed_at": (ANCHOR + timedelta(seconds=5)).isoformat(),
        "expires_at": (ANCHOR + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "DURABILITY_ANCHOR_ATTESTOR",
            "identity": evidence.DURABILITY_ANCHOR_IDENTITY,
            "namespace": evidence.DURABILITY_ANCHOR_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": trust_profiles["anchor_profile"]["key_fingerprint"],
        },
    }
    return _reseal_anchor(core, trust_profiles)


def _forge_anchor(artifact: dict, trust_profiles: dict, mutate) -> dict:
    forged = deepcopy(artifact)
    for field in ("signed_core_digest", "signature", "attestation_digest"):
        forged.pop(field)
    mutate(forged)
    return _reseal_anchor(forged, trust_profiles)


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
        "registry_class": "HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
        "registry_locator": "registry:host-append-only:s2e",
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


def _validate_registry(artifact, candidate, predecessor, entry):
    return evidence.validate_s2e_predecessor_registry_attestation(
        artifact,
        candidate=candidate,
        predecessor_receipt=predecessor,
        acceptance_review_bundle_digest="sha256:" + "4" * 64,
        prior_consumption_ledger_digest="sha256:" + "5" * 64,
        expected_consumption_entry=entry,
        expected_result_ledger_digest="sha256:" + "6" * 64,
        now=ANCHOR + timedelta(minutes=1),
    )


def test_independent_anchor_and_registry_attestations_validate(trust_profiles):
    anchor = _anchor_case(trust_profiles)
    assert evidence.validate_s2e_durability_anchor_attestation(
        anchor,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    ) == []
    registry, candidate, predecessor, entry = _registry_case(trust_profiles)
    assert _validate_registry(registry, candidate, predecessor, entry) == []


@pytest.mark.parametrize(
    ("locator", "expected"),
    (
        ("memory:fake-anchor", "fixture or local"),
        ("file:///tmp/fake-anchor", "outside the admitted host append-only"),
        ("unix:/run/fake-anchor.sock", "outside the admitted host append-only"),
        ("https://anchor.example.test", "outside the admitted host append-only"),
        ("aws:s3-object-lock-attestor:x", "outside the admitted host append-only"),
        (" memory:fake-anchor", "does not match pattern"),
    ),
)
def test_anchor_rejects_non_host_class_or_noncanonical_locator(
    trust_profiles, locator, expected
):
    forged = _forge_anchor(
        _anchor_case(trust_profiles),
        trust_profiles,
        lambda value: value.update(anchor_locator=locator),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        forged,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize(
    ("locator", "expected"),
    (
        ("memory:fake-replica", "fixture or local"),
        ("file:///tmp/fake-replica", "outside the admitted off-host"),
        ("host:append-only-durability-anchor:s2e-aiml", "outside the admitted off-host"),
        (" replica:offhost-append-only:x", "does not match pattern"),
    ),
)
def test_anchor_rejects_non_offhost_replica_locator(
    trust_profiles, locator, expected
):
    forged = _forge_anchor(
        _anchor_case(trust_profiles),
        trust_profiles,
        lambda value: value.update(offhost_replica_locator=locator),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        forged,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    (
        (
            "replica_head_digest",
            "sha256:" + "e" * 64,
            "durability anchor replica replica_head_digest does not mirror the anchor",
        ),
        (
            "replica_entry_digest",
            "sha256:" + "e" * 64,
            "durability anchor replica replica_entry_digest does not mirror the anchor",
        ),
        (
            "replica_generation",
            7,
            "durability anchor replica replica_generation does not mirror the anchor",
        ),
        (
            "replica_previous_head_digest",
            "sha256:" + "e" * 64,
            "durability anchor replica replica_previous_head_digest does not "
            "mirror the anchor",
        ),
    ),
)
def test_anchor_rejects_replica_that_does_not_mirror_the_anchor(
    trust_profiles, field, value, expected
):
    """副本不是獨立計數器,是同一條 ledger 的忠實鏡像;任一值不合即 fail closed。"""

    artifact = _anchor_case(trust_profiles)
    forged = deepcopy(artifact)
    for name in ("signed_core_digest", "signature", "attestation_digest"):
        forged.pop(name)
    forged["offhost_replica_readback"][field] = value
    _sign_replica_readback(forged["offhost_replica_readback"], trust_profiles)
    forged = _sign_anchor(forged, trust_profiles)
    errors = evidence.validate_s2e_durability_anchor_attestation(
        forged,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert expected in errors, errors


def test_anchor_rejects_readback_without_the_second_signature(trust_profiles):
    """第二把簽章是 §LW1「單一簽章不能防 rollback」的唯一結構性答覆。"""

    artifact = _anchor_case(trust_profiles)
    forged = deepcopy(artifact)
    for name in ("signed_core_digest", "signature", "attestation_digest"):
        forged.pop(name)
    # anchor writer 自己改寫 replica head 後只重簽 anchor 側:replica 簽章立即失配。
    forged["offhost_replica_readback"]["replica_head_digest"] = "sha256:" + "e" * 64
    forged = _sign_anchor(forged, trust_profiles)
    errors = evidence.validate_s2e_durability_anchor_attestation(
        forged,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert "durability anchor replica readback signed core digest is invalid" in (
        errors
    ), errors
    assert "durability anchor replica readback SSHSIG verification failed" in errors


def test_anchor_rejects_replica_signed_by_the_anchor_key(trust_profiles, monkeypatch):
    """同一把 key 簽兩次不成立 2-of-2,必須被 distinct-fingerprint 擋下。"""

    monkeypatch.setattr(
        evidence,
        "_load_offhost_replica_trust_root",
        lambda: (trust_profiles["anchor_profile"], []),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        _anchor_case(trust_profiles),
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert (
        "durability anchor replica readback key is not independent from "
        "durability anchor"
    ) in errors, errors


def test_anchor_rejects_replica_on_the_same_host_identity(trust_profiles):
    """host fingerprint 相同 = 副本沒有在別台機器上,選的是可外部核對的判準。"""

    artifact = _anchor_case(trust_profiles)
    forged = deepcopy(artifact)
    for name in ("signed_core_digest", "signature", "attestation_digest"):
        forged.pop(name)
    forged["offhost_replica_readback"]["replica_host_fingerprint"] = (
        ANCHOR_HOST_FINGERPRINT
    )
    _sign_replica_readback(forged["offhost_replica_readback"], trust_profiles)
    forged = _sign_anchor(forged, trust_profiles)
    errors = evidence.validate_s2e_durability_anchor_attestation(
        forged,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert (
        "durability anchor replica host identity is not independent from the "
        "anchor host"
    ) in errors, errors
    assert (
        "durability anchor replica host fingerprint differs from its fixed "
        "trust root"
    ) in errors


def test_anchor_rejects_anchor_host_fingerprint_off_its_trust_root(trust_profiles):
    forged = _forge_anchor(
        _anchor_case(trust_profiles),
        trust_profiles,
        lambda value: value.update(
            anchor_host_fingerprint="SHA256:" + "C" * 43
        ),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        forged,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert (
        "durability anchor host fingerprint differs from its fixed trust root"
    ) in errors, errors


def test_replica_readback_carries_its_own_freshness_window(trust_profiles):
    """replica 有自己的 ≤10min 窗;窗長上界恆檢查,不因任何參數放寬。"""

    artifact = _anchor_case(trust_profiles)
    forged = deepcopy(artifact)
    for name in ("signed_core_digest", "signature", "attestation_digest"):
        forged.pop(name)
    forged["offhost_replica_readback"]["expires_at"] = (
        ANCHOR + timedelta(minutes=30)
    ).isoformat()
    _sign_replica_readback(forged["offhost_replica_readback"], trust_profiles)
    forged = _sign_anchor(forged, trust_profiles)
    for require_current in (True, False):
        errors = evidence.validate_s2e_durability_anchor_attestation(
            forged,
            terminal_payload_digest=D1,
            now=ANCHOR + timedelta(minutes=1),
            require_current_freshness=require_current,
        )
        assert (
            "durability anchor replica readback freshness window exceeds ten minutes"
        ) in errors, (require_current, errors)


def test_replica_flag_fields_are_rejected_by_schema(trust_profiles):
    """三個 const: true 旗標已刪除;它們現在是 additionalProperties 違規。"""

    artifact = deepcopy(_anchor_case(trust_profiles))
    artifact["offhost_replica_readback"]["ack"] = True
    errors = evidence.validate_s2e_durability_anchor_attestation(
        artifact,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("ack" in error for error in errors), errors


def test_anchor_rejects_generation_head_discontinuity(trust_profiles):
    cases = (
        {"previous_anchor_head_digest": "sha256:" + "e" * 64},
        {"anchor_generation": 2, "previous_anchor_head_digest": None},
    )
    for updates in cases:
        forged = _forge_anchor(
            _anchor_case(trust_profiles),
            trust_profiles,
            lambda value, updates=updates: value.update(updates),
        )
        errors = evidence.validate_s2e_durability_anchor_attestation(
            forged,
            terminal_payload_digest=D1,
            now=ANCHOR + timedelta(minutes=1),
        )
        assert any("continuity" in error for error in errors), errors


def test_anchor_rejects_payload_binding_and_stale_window(trust_profiles):
    artifact = _anchor_case(trust_profiles)
    errors = evidence.validate_s2e_durability_anchor_attestation(
        artifact,
        terminal_payload_digest="sha256:" + "f" * 64,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any(
        "terminal_payload_digest binding differs" in error for error in errors
    ), errors

    stale = _forge_anchor(
        artifact,
        trust_profiles,
        lambda value: value.update(
            observed_at=(ANCHOR - timedelta(hours=1)).isoformat(),
            expires_at=(ANCHOR - timedelta(minutes=55)).isoformat(),
        ),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        stale,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("stale" in error for error in errors), errors

    over_ttl = _forge_anchor(
        artifact,
        trust_profiles,
        lambda value: value.update(
            expires_at=(ANCHOR + timedelta(minutes=30)).isoformat()
        ),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        over_ttl,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("ten minutes" in error for error in errors), errors


def test_anchor_rejects_attestation_predating_readback(trust_profiles):
    forged = _forge_anchor(
        _anchor_case(trust_profiles),
        trust_profiles,
        lambda value: value.update(
            observed_at=(ANCHOR + timedelta(seconds=1)).isoformat()
        ),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        forged,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("predates off-host readback" in error for error in errors), errors


@pytest.mark.parametrize(
    "locator",
    (
        "memory:s2e-registry",
        " local:s2e-registry",
        "registry:test:s2e",
        "registry:external-append-only:s2e",
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
    errors = _validate_registry(artifact, candidate, predecessor, entry)
    assert errors
    assert all("registry_locator" in error for error in errors), errors


def test_anchor_and_registry_reject_same_key_custody(trust_profiles, monkeypatch):
    anchor = _anchor_case(trust_profiles)
    monkeypatch.setattr(
        evidence,
        "_load_s2e_receipt_signer_profile",
        lambda: (trust_profiles["anchor_profile"], []),
    )
    errors = evidence.validate_s2e_durability_anchor_attestation(
        anchor,
        terminal_payload_digest=D1,
        now=ANCHOR + timedelta(minutes=1),
    )
    assert any("not independent" in error for error in errors), errors

    registry, candidate, predecessor, entry = _registry_case(trust_profiles)
    monkeypatch.setattr(
        evidence,
        "_load_s2e_receipt_signer_profile",
        lambda: (trust_profiles["registry_profile"], []),
    )
    errors = _validate_registry(registry, candidate, predecessor, entry)
    assert any("not independent" in error for error in errors), errors


def test_registry_rejects_anchor_shared_key_custody(trust_profiles, monkeypatch):
    """registry 與 durability anchor 必須是兩份 custody,共用即 fail closed。"""

    registry, candidate, predecessor, entry = _registry_case(trust_profiles)
    monkeypatch.setattr(
        evidence,
        "_load_durability_anchor_trust_root",
        lambda: (trust_profiles["registry_profile"], []),
    )
    errors = _validate_registry(registry, candidate, predecessor, entry)
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
        errors = _validate_registry(forged, candidate, predecessor, entry)
        assert any(expected in error for error in errors), errors


def test_absent_attestations_never_validate():
    assert evidence.validate_s2e_durability_anchor_attestation(
        None,
        terminal_payload_digest=D1,
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
