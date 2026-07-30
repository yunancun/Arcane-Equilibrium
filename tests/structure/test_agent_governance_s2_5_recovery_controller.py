from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MAINTENANCE = ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING = ROOT / "program_code" / "ml_training"
for candidate in (MAINTENANCE, ML_TRAINING):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_s2_5_host_capture as host_capture  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_s2_5_disposable_profile as profile  # noqa: E402
import agent_governance_s2_5_recovery_controller as controller  # noqa: E402


HEAD = "1" * 40
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
D6 = "sha256:" + "6" * 64
START = "s2-5-" + "5" * 64
AUTHORIZATION_ID = "s2-5-auth-" + "7" * 64
TASK_DIGEST = "sha256:" + "8" * 64
FAILURE_OBSERVED = "2030-01-01T00:00:00+00:00"
FAILURE_EXPIRES = "2030-01-01T00:10:00+00:00"
ADMISSION_OBSERVED = "2030-01-01T00:20:00+00:00"
ADMISSION_EXPIRES = "2030-01-01T00:30:00+00:00"
TRUSTED_NOW = "2030-01-01T00:25:00+00:00"
ROOT_IDENTITY = {
    "canonical_path": profile.DISPOSABLE_STATE_ROOT,
    "device": 11,
    "inode": 22,
    "mode": "0700",
    "uid": profile.PROFILE_UID,
    "gid": profile.PROFILE_GID,
    "nlink": 2,
    "is_directory": True,
}
STATE_ROOT_ID = validator.canonical_digest(ROOT_IDENTITY)
JOURNAL_INVENTORY = [
    {
        "basename": START + ".journal.json",
        "start_id": START,
        "file_digest": D3,
        "journal_head_digest": D4,
        "terminal_state": "RECOVERY_REQUIRED",
    }
]
JOURNAL_SET_DIGEST = validator.canonical_digest({
    "schema_version": "s2_5_recovery_journal_set_v2",
    "entries": JOURNAL_INVENTORY,
})
_SIGNING_PROFILE: tuple[Path, str, str] | None = None


def _canonical_json(value: dict) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _seal(value: dict) -> dict:
    sealed = copy.deepcopy(value)
    sealed["self_digest"] = validator.artifact_self_digest(sealed)
    return sealed


def _replace_embedded_subject_artifact(
    subject: dict,
    *,
    json_field: str,
    digest_field: str,
    updates: dict,
) -> dict:
    rewritten = copy.deepcopy(subject)
    artifact = json.loads(rewritten[json_field])
    artifact.update(updates)
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    rewritten[json_field] = _canonical_json(artifact)
    rewritten[digest_field] = artifact["self_digest"]
    return rewritten


@pytest.fixture(autouse=True)
def _fixed_capture_trust_root(tmp_path, monkeypatch):
    global _SIGNING_PROFILE
    kit = __import__("s2_5_testkit")
    private_key, public_key, fingerprint = kit.mint_key(
        tmp_path, "s2-5-controller-host-capture"
    )
    monkeypatch.setattr(
        host_capture,
        "_load_recovery_host_capture_trust_root_public_key",
        lambda: public_key,
    )
    monkeypatch.setattr(
        host_capture,
        "RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT",
        fingerprint,
    )
    _SIGNING_PROFILE = (private_key, public_key, fingerprint)
    yield
    _SIGNING_PROFILE = None


def _capture(
    *,
    boot_id: str,
    observed_at: str,
    expires_at: str,
    source_head: str = HEAD,
) -> dict:
    assert _SIGNING_PROFILE is not None
    private_key, _public_key, fingerprint = _SIGNING_PROFILE
    signed = {
        "schema_version": host_capture.HOST_CAPTURE_SCHEMA_VERSION,
        "capture_profile": host_capture.HOST_CAPTURE_PROFILE,
        "source_head": source_head,
        "stable_host_facts": {
            "machine_id_digest": D1,
            "node_name": "disposable-systemd-test",
            "os_id": "linux",
            "architecture": "x86_64",
        },
        "host_identity": "",
        "node_identity": {
            "node_id": "s2-5-host-attestor",
            "role": "HOST_ATTESTOR",
            "permission": "read_only",
            "key_identity": "key:s2-5-host-attestor",
        },
        "process_identity": {
            "uid": 4300,
            "cgroup": "/system.slice/s2-5-host-capture.service",
        },
        "boot_manager_facts": {
            "boot_id": boot_id,
            "manager": "systemd",
            "manager_root": "/run/systemd/system",
            "unit_name": (
                "arcane-equilibrium-aiml-engine-scanner.service"
            ),
            "canonical_state_root": profile.DISPOSABLE_STATE_ROOT,
        },
        "observed_at": observed_at,
        "expires_at": expires_at,
        "side_effect_class": "DISPOSABLE_TEST",
        "production_effect": False,
        "production_authority": False,
        "target_class": "disposable_systemd",
    }
    signed["host_identity"] = (
        host_capture.derive_s2_5_recovery_host_identity(signed)
    )
    capture = {
        **signed,
        "signer_identity": (
            host_capture.RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY
        ),
        "signer_fingerprint": fingerprint,
        "signature_namespace": (
            host_capture.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE
        ),
        "signed_binding": copy.deepcopy(signed),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            private_key,
            validator._canonical_bytes(signed),
            namespace=(
                host_capture.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE
            ),
        ),
    }
    capture["self_digest"] = validator.artifact_self_digest(capture)
    return capture


def _unresolved_payload(
    *,
    failure_capture_digest: str,
    stable_root_id: str,
    state_root_id: str = STATE_ROOT_ID,
) -> dict:
    return {
        "schema_version": "s2_5_recovery_unresolved_payload_v2",
        "start_id": START,
        "reasons": ["effect outcome is not externally closed"],
        "task_digest": TASK_DIGEST,
        "stable_root_id": stable_root_id,
        "state_root_id": state_root_id,
        "journal_set_digest": JOURNAL_SET_DIGEST,
        "replay_ledger_head_digest": None,
        "pre_state": {
            "active_state": "inactive",
            "unit_file_state": "disabled",
            "n_restarts": 0,
            "invocation_id": "none",
        },
        "source_head": HEAD,
        "failure_host_capture_digest": failure_capture_digest,
        "side_effect_class": "DISPOSABLE_TEST",
        "production_effect": False,
        "production_authority": False,
        "target_class": "disposable_systemd",
    }


def _recovery_intent(
    *, authorization_id: str = AUTHORIZATION_ID
) -> dict:
    return _seal({
        "schema_version": "s2_5_recovery_controller_intent_ref_v2",
        "recovery_id": "s2-5-recovery-" + "9" * 64,
        "authorization_id": authorization_id,
        "task_digest": TASK_DIGEST,
        "start_id": START,
        "source_head": HEAD,
        "action": "ROLLBACK_TO_PRE_STATE",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "production_effect": False,
        "production_authority": False,
    })


def _phase_artifact(schema_version: str, **values) -> dict:
    return _seal({
        "schema_version": schema_version,
        "authorization_id": AUTHORIZATION_ID,
        "recovery_intent_digest": _recovery_intent()["self_digest"],
        "source_head": HEAD,
        "start_id": START,
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "production_effect": False,
        "production_authority": False,
        **values,
    })


def _replay_ledger(phase: str) -> dict:
    consumed = [] if phase == "PREPARED" else [AUTHORIZATION_ID]
    return {
        "schema_version": "s2_5_recovery_replay_projection_v2",
        "basename": "authorization-replay-ledger.json",
        "present": bool(consumed),
        "authorization_ids": consumed,
        "entry_count": len(consumed),
        "file_digest": D4 if consumed else None,
        "head_digest": D5 if consumed else None,
    }


def _subject(
    *,
    phase: str = "PREPARED",
    anchor_progress: str = "OUTBOX_PREPARED",
    generation: int = 1,
    previous_controller_state_digest: str | None = None,
    previous_manifest_digest: str | None = None,
) -> dict:
    failure_capture = _capture(
        boot_id="boot-old",
        observed_at=FAILURE_OBSERVED,
        expires_at=FAILURE_EXPIRES,
    )
    admission_capture = _capture(
        boot_id="boot-new",
        observed_at=ADMISSION_OBSERVED,
        expires_at=ADMISSION_EXPIRES,
    )
    stable_root_id = controller.derive_stable_root_id(admission_capture)
    unresolved = _unresolved_payload(
        failure_capture_digest=failure_capture["self_digest"],
        stable_root_id=stable_root_id,
    )
    intent = _recovery_intent()
    replay = _replay_ledger(phase)
    consumed = list(replay["authorization_ids"])
    consumption = (
        None
        if phase == "PREPARED"
        else _phase_artifact(
            "s2_5_recovery_consumption_ref_v2",
            replay_ledger_head_digest=replay["head_digest"],
        )
    )
    result = (
        None
        if phase in {"PREPARED", "CONSUMED"}
        else _phase_artifact(
            "s2_5_recovery_effect_result_ref_v2",
            status="RECOVERY_APPLIED",
        )
    )
    rollback = (
        None
        if phase in {"PREPARED", "CONSUMED"}
        else _phase_artifact(
            "s2_5_recovery_rollback_ref_v2",
            status="ROLLBACK_APPLIED",
        )
    )
    postcheck = (
        None
        if phase != "RESOLVED"
        else _phase_artifact(
            "s2_5_recovery_postcheck_ref_v2",
            status="RECOVERY_CLEARED",
        )
    )
    return {
        "schema_version": "s2_5_recovery_controller_candidate_v2",
        "controller_id": controller.derive_controller_id(
            stable_root_id=stable_root_id,
            source_head=HEAD,
        ),
        "phase": phase,
        "anchor_progress": anchor_progress,
        "generation": generation,
        "previous_controller_state_digest": (
            previous_controller_state_digest
        ),
        "previous_manifest_digest": previous_manifest_digest,
        "stable_host_facts": copy.deepcopy(
            admission_capture["stable_host_facts"]
        ),
        "host_identity": admission_capture["host_identity"],
        "canonical_state_root": profile.DISPOSABLE_STATE_ROOT,
        "stable_root_id": stable_root_id,
        "state_root_identity": copy.deepcopy(ROOT_IDENTITY),
        "state_root_id": STATE_ROOT_ID,
        "source_head": HEAD,
        "start_id": START,
        "task_digest": TASK_DIGEST,
        "operation": "RECOVER_DISPOSABLE_EFFECT",
        "authorization_id": AUTHORIZATION_ID,
        "unresolved_payload_json": _canonical_json(unresolved),
        "unresolved_state_digest": validator.canonical_digest(unresolved),
        "failure_host_capture_json": _canonical_json(failure_capture),
        "failure_host_capture_digest": failure_capture["self_digest"],
        "recovery_admission_capture_json": _canonical_json(
            admission_capture
        ),
        "recovery_admission_capture_digest": (
            admission_capture["self_digest"]
        ),
        "journal_inventory": copy.deepcopy(JOURNAL_INVENTORY),
        "journal_set_digest": JOURNAL_SET_DIGEST,
        "replay_ledger": replay,
        "replay_ledger_head_digest": replay["head_digest"],
        "consumed_authorization_ids": consumed,
        "recovery_intent_json": _canonical_json(intent),
        "recovery_intent_digest": intent["self_digest"],
        "consumption_proof_json": (
            _canonical_json(consumption) if consumption else None
        ),
        "consumption_proof_digest": (
            consumption["self_digest"] if consumption else None
        ),
        "effect_result_json": _canonical_json(result) if result else None,
        "effect_result_digest": result["self_digest"] if result else None,
        "rollback_result_json": (
            _canonical_json(rollback) if rollback else None
        ),
        "rollback_result_digest": (
            rollback["self_digest"] if rollback else None
        ),
        "independent_postcheck_json": (
            _canonical_json(postcheck) if postcheck else None
        ),
        "independent_postcheck_digest": (
            postcheck["self_digest"] if postcheck else None
        ),
        "prior_phase_anchor_proof_digest": None,
        "previous_external_sequence": 0,
        "previous_external_head_digest": None,
        "external_monotonic_floor": 0,
        "external_snapshot_id": "empty-anchor-snapshot",
        "external_latest_version_id": None,
        "trust_status": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": profile.PROFILE_ID,
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    }


def _transition(subject: dict, *, from_phase: str) -> dict:
    payload = {
        "schema_version": (
            "s2_5_recovery_controller_transition_v2"
        ),
        "transition_id": "",
        "from_phase": from_phase,
        "to_phase": subject["phase"],
        "generation": subject["generation"],
        "previous_controller_state_digest": subject[
            "previous_controller_state_digest"
        ],
        "candidate_subject": copy.deepcopy(subject),
        "candidate_subject_digest": (
            controller.derive_candidate_subject_digest(subject)
        ),
        "expected_external_sequence": subject[
            "previous_external_sequence"
        ],
        "expected_external_head_digest": subject[
            "previous_external_head_digest"
        ],
        "external_monotonic_floor": subject[
            "external_monotonic_floor"
        ],
        "expected_snapshot_id": subject["external_snapshot_id"],
        "expected_latest_version_id": subject[
            "external_latest_version_id"
        ],
        "issued_at": "2030-01-01T00:21:00+00:00",
        "expires_at": "2030-01-01T00:26:00+00:00",
        "evidence_class": "LOCAL_REPRODUCIBLE",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": profile.PROFILE_ID,
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    }
    payload["transition_id"] = controller.derive_transition_id(payload)
    return _seal(payload)


def _outbox(transition: dict) -> dict:
    subject = transition["candidate_subject"]
    request = {
        "schema_version": (
            "s2_5_recovery_anchor_compare_append_request_v2"
        ),
        "transition_digest": transition["self_digest"],
        "candidate_subject_digest": transition[
            "candidate_subject_digest"
        ],
        "prior_manifest_digest": subject["previous_manifest_digest"],
        "expected_external_sequence": transition[
            "expected_external_sequence"
        ],
        "expected_external_head_digest": transition[
            "expected_external_head_digest"
        ],
        "expected_snapshot_id": transition["expected_snapshot_id"],
        "expected_latest_version_id": transition[
            "expected_latest_version_id"
        ],
        "candidate_external_sequence": (
            transition["expected_external_sequence"] + 1
        ),
        "idempotency_key": "",
        "source_head": subject["source_head"],
        "start_id": subject["start_id"],
        "operation": subject["operation"],
        "phase": subject["phase"],
    }
    request["idempotency_key"] = (
        controller.derive_outbox_idempotency(request)
    )
    payload = {
        "schema_version": "s2_5_recovery_anchor_outbox_v1",
        "transition_json": _canonical_json(transition),
        "transition_digest": transition["self_digest"],
        "candidate_subject_digest": transition[
            "candidate_subject_digest"
        ],
        "prior_manifest_digest": subject["previous_manifest_digest"],
        "prepared_payload_json": _canonical_json(request),
        "prepared_payload_digest": validator.canonical_digest(request),
        "request_digest": validator.canonical_digest({
            "schema_version": "s2_5_recovery_anchor_request_bytes_v1",
            "canonical_json": _canonical_json(request),
        }),
        "idempotency_key": request["idempotency_key"],
        "expected_external_sequence": request[
            "expected_external_sequence"
        ],
        "expected_external_head_digest": request[
            "expected_external_head_digest"
        ],
        "expected_snapshot_id": request["expected_snapshot_id"],
        "expected_latest_version_id": request[
            "expected_latest_version_id"
        ],
        "candidate_external_sequence": request[
            "candidate_external_sequence"
        ],
        "prepared_at": "2030-01-01T00:22:00+00:00",
        "status": "PREPARED_NO_EFFECT",
        "effect_executed": False,
        "evidence_class": "LOCAL_REPRODUCIBLE",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": profile.PROFILE_ID,
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    }
    return _seal(payload)


def _pending_state(subject: dict, *, from_phase: str) -> tuple[dict, dict, dict]:
    transition = _transition(subject, from_phase=from_phase)
    outbox = _outbox(transition)
    state = _seal({
        "schema_version": "s2_5_recovery_controller_state_v2",
        "candidate_subject": copy.deepcopy(subject),
        "candidate_subject_digest": (
            controller.derive_candidate_subject_digest(subject)
        ),
        "pending_outbox": outbox,
        "pending_outbox_digest": outbox["self_digest"],
        "attached_anchor_proof": None,
        "attached_anchor_proof_digest": None,
        "trust_status": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": profile.PROFILE_ID,
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    })
    return transition, outbox, state


def _proof(
    pending: dict,
    *,
    confirmed_subject_digest: str,
    source_head: str = HEAD,
) -> dict:
    outbox = pending["pending_outbox"]
    transition = json.loads(outbox["transition_json"])
    return _seal({
        "schema_version": "s2_5_recovery_anchor_proof_v1",
        "outbox_prepared_state_digest": pending["self_digest"],
        "outbox_candidate_subject_digest": pending[
            "candidate_subject_digest"
        ],
        "confirmed_candidate_subject_digest": confirmed_subject_digest,
        "transition_json": _canonical_json(transition),
        "transition_digest": transition["self_digest"],
        "outbox_json": _canonical_json(outbox),
        "outbox_digest": outbox["self_digest"],
        "idempotency_key": outbox["idempotency_key"],
        "source_head": source_head,
        "start_id": pending["candidate_subject"]["start_id"],
        "phase": pending["candidate_subject"]["phase"],
        "object_id": "object-1",
        "version_id": "version-1",
        "checksum": D4,
        "sequence": outbox["candidate_external_sequence"],
        "previous_head_digest": outbox[
            "expected_external_head_digest"
        ],
        "head_digest": D6,
        "external_monotonic_floor": outbox[
            "candidate_external_sequence"
        ],
        "snapshot_id": "snapshot-1",
        "latest_version_id": "version-1",
        "exact_readback_digest": D2,
        "enumeration_digest": D3,
        "latest_digest": D4,
        "writer_identity_digest": D1,
        "reader_identity_digest": D2,
        "verifier_identity_digest": D3,
        "immutable_readback": False,
        "full_chain_valid": False,
        "identity_distinct": False,
        "authenticated_response": False,
        "failure_code": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        "evidence_class": "LOCAL_REPRODUCIBLE",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": profile.PROFILE_ID,
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    })


def _proof_state(
    pending: dict,
    *,
    previous_manifest_digest: str,
) -> tuple[dict, dict]:
    subject = copy.deepcopy(pending["candidate_subject"])
    subject.update({
        "anchor_progress": "PROOF_ATTACHED_UNVERIFIED",
        "generation": subject["generation"] + 1,
        "previous_controller_state_digest": pending["self_digest"],
        "previous_manifest_digest": previous_manifest_digest,
    })
    proof = _proof(
        pending,
        confirmed_subject_digest=(
            controller.derive_candidate_subject_digest(subject)
        ),
    )
    state = _seal({
        "schema_version": "s2_5_recovery_controller_state_v2",
        "candidate_subject": subject,
        "candidate_subject_digest": (
            controller.derive_candidate_subject_digest(subject)
        ),
        "pending_outbox": None,
        "pending_outbox_digest": None,
        "attached_anchor_proof": proof,
        "attached_anchor_proof_digest": proof["self_digest"],
        "trust_status": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": profile.PROFILE_ID,
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    })
    return proof, state


def _next_phase_pending(
    previous: dict,
    *,
    phase: str,
    previous_manifest_digest: str,
) -> tuple[dict, dict, dict]:
    subject = _subject(
        phase=phase,
        generation=previous["candidate_subject"]["generation"] + 1,
        previous_controller_state_digest=previous["self_digest"],
        previous_manifest_digest=previous_manifest_digest,
    )
    proof = previous["attached_anchor_proof"]
    subject.update({
        "prior_phase_anchor_proof_digest": proof["self_digest"],
        "previous_external_sequence": proof["sequence"],
        "previous_external_head_digest": proof["head_digest"],
        "external_monotonic_floor": proof["external_monotonic_floor"],
        "external_snapshot_id": proof["snapshot_id"],
        "external_latest_version_id": proof["latest_version_id"],
    })
    return _pending_state(
        subject,
        from_phase=previous["candidate_subject"]["phase"],
    )


def _manifest(
    state: dict,
    *,
    previous_manifest_digest: str | None = None,
    generation: int | None = None,
) -> dict:
    subject = state["candidate_subject"]
    return _seal({
        "schema_version": "s2_5_recovery_store_manifest_v2",
        "store_id": controller.derive_store_id(STATE_ROOT_ID),
        "stable_root_id": subject["stable_root_id"],
        "state_root_id": STATE_ROOT_ID,
        "source_head": HEAD,
        "generation": (
            subject["generation"] if generation is None else generation
        ),
        "phase": subject["phase"],
        "anchor_progress": subject["anchor_progress"],
        "previous_manifest_digest": previous_manifest_digest,
        "controller_state": copy.deepcopy(state),
        "controller_state_digest": state["self_digest"],
        "pending_outbox": copy.deepcopy(state["pending_outbox"]),
        "pending_outbox_digest": state["pending_outbox_digest"],
        "attached_anchor_proof": copy.deepcopy(
            state["attached_anchor_proof"]
        ),
        "attached_anchor_proof_digest": state[
            "attached_anchor_proof_digest"
        ],
        "state_root_identity": copy.deepcopy(ROOT_IDENTITY),
        "journal_inventory": copy.deepcopy(
            subject["journal_inventory"]
        ),
        "journal_set_digest": subject["journal_set_digest"],
        "replay_ledger": copy.deepcopy(subject["replay_ledger"]),
        "trust_status": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": profile.PROFILE_ID,
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    })


def _genesis() -> tuple[dict, dict, dict, dict]:
    transition, outbox, state = _pending_state(
        _subject(),
        from_phase="GENESIS",
    )
    return transition, outbox, state, _manifest(state)


def test_v1_digest_only_manifest_is_never_auto_migrated():
    assert controller.classify_legacy_manifest({
        "schema_version": "s2_5_recovery_store_manifest_v1",
        "unresolved_state_digest": D1,
    }) == {
        "status": "RECOVERY_REQUIRED_LEGACY_DIGEST_ONLY",
        "auto_upgrade_allowed": False,
        "external_bootstrap_required": True,
        "effect_admitted": False,
        "clear_admitted": False,
        "production_effect": False,
        "production_authority": False,
    }


def test_generation_one_is_only_prepared_outbox_genesis():
    _transition_value, _outbox_value, state, manifest = _genesis()
    assert controller.validate_controller_artifact(state) == []
    assert controller.validate_controller_artifact(manifest) == []
    assert controller.validate_fresh_controller_admission(
        state, trusted_now=TRUSTED_NOW
    ) == []

    for field, value in (
        ("phase", "RESOLVED"),
        ("anchor_progress", "PROOF_ATTACHED_UNVERIFIED"),
        ("previous_external_sequence", 7),
        ("previous_external_head_digest", D1),
    ):
        mutated_subject = copy.deepcopy(state["candidate_subject"])
        mutated_subject[field] = value
        _t, _o, mutated = _pending_state(
            mutated_subject,
            from_phase="GENESIS",
        )
        assert controller.validate_controller_artifact(mutated)


def test_full_signed_captures_bind_stable_root_and_fresh_admission():
    _transition_value, _outbox_value, state, _manifest_value = _genesis()
    subject = state["candidate_subject"]
    failure = json.loads(subject["failure_host_capture_json"])
    admission = json.loads(subject["recovery_admission_capture_json"])
    assert host_capture.validate_s2_5_recovery_host_capture_integrity(
        failure
    ) == []
    assert host_capture.validate_s2_5_recovery_host_capture_integrity(
        admission
    ) == []
    assert subject["stable_root_id"] == (
        controller.derive_stable_root_id(admission)
    )

    stale = controller.validate_fresh_controller_admission(
        state, trusted_now="2030-01-01T00:31:00+00:00"
    )
    assert any("stale" in error for error in stale)

    rewritten = copy.deepcopy(subject)
    rewritten["stable_root_id"] = D1
    _t, _o, bad_state = _pending_state(
        rewritten, from_phase="GENESIS"
    )
    assert controller.validate_controller_artifact(bad_state)


def test_candidate_subject_closes_outbox_over_every_next_state_field():
    transition, outbox, state, _manifest_value = _genesis()
    assert transition["candidate_subject_digest"] == (
        state["candidate_subject_digest"]
    )
    assert outbox["candidate_subject_digest"] == (
        state["candidate_subject_digest"]
    )

    mutated = copy.deepcopy(state)
    mutated["candidate_subject"]["recovery_admission_capture_digest"] = D1
    mutated["candidate_subject_digest"] = (
        controller.derive_candidate_subject_digest(
            mutated["candidate_subject"]
        )
    )
    mutated["self_digest"] = validator.artifact_self_digest(mutated)
    errors = controller.validate_controller_artifact(mutated)
    assert any("candidate subject" in error for error in errors)


def test_persisted_outbox_rejects_illegal_phase_and_external_cas_substitution():
    _transition_value, _outbox_value, pending, first_manifest = _genesis()
    _proof_value, attached = _proof_state(
        pending,
        previous_manifest_digest=first_manifest["self_digest"],
    )
    attached_manifest = _manifest(
        attached,
        previous_manifest_digest=first_manifest["self_digest"],
    )
    _t, _o, consumed = _next_phase_pending(
        attached,
        phase="CONSUMED",
        previous_manifest_digest=attached_manifest["self_digest"],
    )
    assert controller.validate_controller_state_successor(
        attached, consumed
    ) == []

    illegal_subject = copy.deepcopy(consumed["candidate_subject"])
    _t, _o, illegal = _pending_state(
        illegal_subject,
        from_phase="RESOLVED",
    )
    assert any(
        "illegal controller phase transition" in error
        for error in controller.validate_controller_artifact(illegal)
    )

    substituted_subject = copy.deepcopy(consumed["candidate_subject"])
    substituted_subject.update({
        "previous_external_sequence": 100,
        "previous_external_head_digest": D1,
        "external_monotonic_floor": 100,
        "external_snapshot_id": "attacker-snapshot",
        "external_latest_version_id": "attacker-version",
    })
    _t, _o, substituted = _pending_state(
        substituted_subject,
        from_phase="PREPARED",
    )
    assert controller.validate_controller_state_successor(
        attached, substituted
    )


def test_proof_is_exactly_bound_but_never_promotes_external_trust():
    _transition_value, _outbox_value, pending, first_manifest = _genesis()
    proof, attached = _proof_state(
        pending,
        previous_manifest_digest=first_manifest["self_digest"],
    )
    assert controller.validate_controller_artifact(proof) == []
    assert controller.validate_controller_artifact(attached) == []
    assert controller.validate_controller_state_successor(
        pending, attached
    ) == []
    assert attached["candidate_subject"]["anchor_progress"] == (
        "PROOF_ATTACHED_UNVERIFIED"
    )
    assert attached["trust_status"] == (
        "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    )

    wrong_source_proof = copy.deepcopy(proof)
    wrong_source_proof["source_head"] = "2" * 40
    wrong_source_proof["self_digest"] = validator.artifact_self_digest(
        wrong_source_proof
    )
    wrong_source = copy.deepcopy(attached)
    wrong_source["attached_anchor_proof"] = wrong_source_proof
    wrong_source["attached_anchor_proof_digest"] = wrong_source_proof[
        "self_digest"
    ]
    wrong_source["self_digest"] = validator.artifact_self_digest(
        wrong_source
    )
    assert controller.validate_controller_artifact(wrong_source)

    claimed = copy.deepcopy(proof)
    claimed.update({
        "evidence_class": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "immutable_readback": True,
        "full_chain_valid": True,
        "identity_distinct": True,
        "authenticated_response": True,
        "failure_code": None,
    })
    claimed["self_digest"] = validator.artifact_self_digest(claimed)
    assert controller.validate_controller_artifact(claimed)


def test_manifest_generation_and_successor_predecessors_are_exact():
    _transition_value, _outbox_value, pending, first = _genesis()
    _proof_value, attached = _proof_state(
        pending,
        previous_manifest_digest=first["self_digest"],
    )
    second = _manifest(
        attached,
        previous_manifest_digest=first["self_digest"],
    )
    assert controller.validate_manifest_successor(first, second) == []

    generation_999 = copy.deepcopy(second)
    generation_999["generation"] = 999
    generation_999["self_digest"] = validator.artifact_self_digest(
        generation_999
    )
    assert controller.validate_controller_artifact(generation_999)

    fork = copy.deepcopy(second)
    fork["previous_manifest_digest"] = D1
    fork["controller_state"]["candidate_subject"][
        "previous_manifest_digest"
    ] = D1
    fork["controller_state"]["candidate_subject_digest"] = (
        controller.derive_candidate_subject_digest(
            fork["controller_state"]["candidate_subject"]
        )
    )
    fork["controller_state"]["self_digest"] = (
        validator.artifact_self_digest(fork["controller_state"])
    )
    fork["controller_state_digest"] = fork["controller_state"][
        "self_digest"
    ]
    fork["self_digest"] = validator.artifact_self_digest(fork)
    assert controller.validate_manifest_successor(first, fork)


def test_phase_chain_consumes_exactly_once_then_freezes_replay():
    _transition_value, _outbox_value, pending, first = _genesis()
    _proof_value, prepared_proof = _proof_state(
        pending, previous_manifest_digest=first["self_digest"]
    )
    prepared_proof_manifest = _manifest(
        prepared_proof, previous_manifest_digest=first["self_digest"]
    )
    _t, _o, consumed = _next_phase_pending(
        prepared_proof,
        phase="CONSUMED",
        previous_manifest_digest=prepared_proof_manifest["self_digest"],
    )
    assert controller.validate_controller_state_successor(
        prepared_proof, consumed
    ) == []
    assert consumed["candidate_subject"]["consumed_authorization_ids"] == [
        AUTHORIZATION_ID
    ]

    consumed_manifest = _manifest(
        consumed,
        previous_manifest_digest=prepared_proof_manifest["self_digest"],
    )
    _proof_value, consumed_proof = _proof_state(
        consumed,
        previous_manifest_digest=consumed_manifest["self_digest"],
    )
    consumed_proof_manifest = _manifest(
        consumed_proof,
        previous_manifest_digest=consumed_manifest["self_digest"],
    )
    _t, _o, committed = _next_phase_pending(
        consumed_proof,
        phase="COMMITTED",
        previous_manifest_digest=consumed_proof_manifest["self_digest"],
    )
    assert controller.validate_controller_state_successor(
        consumed_proof, committed
    ) == []

    duplicate_subject = copy.deepcopy(committed["candidate_subject"])
    duplicate_subject["consumed_authorization_ids"] *= 2
    duplicate_subject["replay_ledger"]["authorization_ids"] *= 2
    duplicate_subject["replay_ledger"]["entry_count"] = 2
    _t, _o, duplicate = _pending_state(
        duplicate_subject,
        from_phase="CONSUMED",
    )
    assert controller.validate_controller_artifact(duplicate)
    assert controller.validate_controller_state_successor(
        consumed_proof, duplicate
    )


def test_resolved_requires_committed_result_rollback_and_independent_postcheck():
    resolved_subject = _subject(
        phase="RESOLVED",
        generation=7,
        previous_controller_state_digest=D1,
        previous_manifest_digest=D2,
    )
    _t, _o, resolved = _pending_state(
        resolved_subject,
        from_phase="COMMITTED",
    )
    assert controller.validate_controller_artifact(resolved) == []

    for json_field, digest_field in (
        ("effect_result_json", "effect_result_digest"),
        ("rollback_result_json", "rollback_result_digest"),
        (
            "independent_postcheck_json",
            "independent_postcheck_digest",
        ),
    ):
        missing_subject = copy.deepcopy(resolved_subject)
        missing_subject[json_field] = None
        missing_subject[digest_field] = None
        _t, _o, missing = _pending_state(
            missing_subject,
            from_phase="COMMITTED",
        )
        assert controller.validate_controller_artifact(missing)


def test_manifest_requires_unique_active_journal_and_exact_replay_id_set():
    _transition_value, _outbox_value, state, manifest = _genesis()
    duplicate = copy.deepcopy(manifest)
    duplicate_entry = copy.deepcopy(duplicate["journal_inventory"][0])
    duplicate_entry["file_digest"] = D1
    duplicate["journal_inventory"].append(duplicate_entry)
    duplicate["journal_set_digest"] = validator.canonical_digest({
        "schema_version": "s2_5_recovery_journal_set_v2",
        "entries": duplicate["journal_inventory"],
    })
    duplicate["self_digest"] = validator.artifact_self_digest(duplicate)
    assert controller.validate_controller_artifact(duplicate)

    missing_active = copy.deepcopy(manifest)
    missing_active["journal_inventory"] = []
    missing_active["journal_set_digest"] = validator.canonical_digest({
        "schema_version": "s2_5_recovery_journal_set_v2",
        "entries": [],
    })
    missing_active["self_digest"] = validator.artifact_self_digest(
        missing_active
    )
    assert controller.validate_controller_artifact(missing_active)

    wrong_ids = copy.deepcopy(manifest)
    wrong_ids["replay_ledger"]["authorization_ids"] = [AUTHORIZATION_ID]
    wrong_ids["replay_ledger"]["entry_count"] = 1
    wrong_ids["replay_ledger"]["present"] = True
    wrong_ids["replay_ledger"]["file_digest"] = D4
    wrong_ids["replay_ledger"]["head_digest"] = D5
    wrong_ids["self_digest"] = validator.artifact_self_digest(wrong_ids)
    assert controller.validate_controller_artifact(wrong_ids)


def test_retry_bytes_are_exact_and_no_local_clear_or_effect_api_exists():
    _transition_value, outbox, state, _manifest_value = _genesis()
    assert controller.validate_controller_artifact(outbox) == []
    request = json.loads(outbox["prepared_payload_json"])
    assert request["idempotency_key"] == outbox["idempotency_key"]
    assert request["candidate_subject_digest"] == (
        state["candidate_subject_digest"]
    )

    forbidden = {
        "record",
        "resolve",
        "acquire",
        "release",
        "execute",
        "persist",
        "driver",
        "session",
        "lease",
        "token",
        "clear",
    }
    assert forbidden.isdisjoint(set(dir(controller)))


@pytest.mark.parametrize(
    ("json_field", "digest_field", "status"),
    (
        (
            "effect_result_json",
            "effect_result_digest",
            "RECOVERY_NOT_APPLIED",
        ),
        (
            "rollback_result_json",
            "rollback_result_digest",
            "ROLLBACK_NOT_APPLIED",
        ),
        (
            "independent_postcheck_json",
            "independent_postcheck_digest",
            "RECOVERY_UNRESOLVED",
        ),
    ),
)
def test_terminal_phase_rejects_coherently_resealed_non_success_receipts(
    json_field,
    digest_field,
    status,
):
    subject = _replace_embedded_subject_artifact(
        _subject(
            phase="RESOLVED",
            generation=7,
            previous_controller_state_digest=D1,
            previous_manifest_digest=D2,
        ),
        json_field=json_field,
        digest_field=digest_field,
        updates={"status": status},
    )
    _transition_value, _outbox_value, state = _pending_state(
        subject,
        from_phase="COMMITTED",
    )
    errors = controller.validate_controller_artifact(state)
    assert any("status" in error for error in errors)


def test_consumed_phase_binds_receipt_to_exact_replay_head():
    _transition_value, _outbox_value, pending, first = _genesis()
    _proof_value, attached = _proof_state(
        pending,
        previous_manifest_digest=first["self_digest"],
    )
    attached_manifest = _manifest(
        attached,
        previous_manifest_digest=first["self_digest"],
    )
    _t, _o, consumed = _next_phase_pending(
        attached,
        phase="CONSUMED",
        previous_manifest_digest=attached_manifest["self_digest"],
    )
    subject = _replace_embedded_subject_artifact(
        consumed["candidate_subject"],
        json_field="consumption_proof_json",
        digest_field="consumption_proof_digest",
        updates={"replay_ledger_head_digest": D1},
    )
    _t, _o, substituted = _pending_state(
        subject,
        from_phase="PREPARED",
    )
    artifact_errors = controller.validate_controller_artifact(substituted)
    successor_errors = controller.validate_controller_state_successor(
        attached,
        substituted,
    )
    assert any("replay" in error for error in artifact_errors)
    assert any("replay" in error for error in successor_errors)


def test_embedded_recovery_intent_cannot_hide_production_authority():
    subject = _replace_embedded_subject_artifact(
        _subject(),
        json_field="recovery_intent_json",
        digest_field="recovery_intent_digest",
        updates={
            "side_effect_class": "PRODUCTION",
            "target_class": "production_systemd",
            "production_effect": True,
            "production_authority": True,
        },
    )
    _transition_value, _outbox_value, state = _pending_state(
        subject,
        from_phase="GENESIS",
    )
    errors = controller.validate_controller_artifact(state)
    assert any("recovery intent" in error and "boundary" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("active_state", "active"),
        ("unit_file_state", "enabled"),
        ("n_restarts", -999),
        ("invocation_id", {"forged": True}),
    ),
)
def test_unresolved_pre_state_is_the_fixed_disposable_baseline(field, value):
    subject = _subject()
    unresolved = json.loads(subject["unresolved_payload_json"])
    unresolved["pre_state"][field] = value
    subject["unresolved_payload_json"] = _canonical_json(unresolved)
    subject["unresolved_state_digest"] = validator.canonical_digest(unresolved)
    _transition_value, _outbox_value, state = _pending_state(
        subject,
        from_phase="GENESIS",
    )
    artifact_errors = controller.validate_controller_artifact(state)
    fresh_errors = controller.validate_fresh_controller_admission(
        state,
        trusted_now=TRUSTED_NOW,
    )
    assert any("pre_state" in error for error in artifact_errors)
    assert any("pre_state" in error for error in fresh_errors)


def test_schema_invalid_nested_containers_fail_closed_without_exceptions():
    transition, outbox, state, manifest = _genesis()
    proof, attached = _proof_state(
        state,
        previous_manifest_digest=manifest["self_digest"],
    )
    containers = ([], ["PREPARED"], {}, {"phase": "PREPARED"})
    malformed: list[dict] = []

    for field in ("from_phase", "to_phase"):
        for value in containers:
            candidate = copy.deepcopy(transition)
            candidate[field] = copy.deepcopy(value)
            candidate["transition_id"] = controller.derive_transition_id(candidate)
            candidate["self_digest"] = validator.artifact_self_digest(candidate)
            malformed.append(candidate)

    for field in (
        "writer_identity_digest",
        "reader_identity_digest",
        "verifier_identity_digest",
    ):
        for value in containers:
            candidate = copy.deepcopy(proof)
            candidate[field] = copy.deepcopy(value)
            candidate["self_digest"] = validator.artifact_self_digest(candidate)
            malformed.append(candidate)

    for value in containers:
        candidate = copy.deepcopy(state)
        candidate["candidate_subject"]["phase"] = copy.deepcopy(value)
        candidate["candidate_subject_digest"] = (
            controller.derive_candidate_subject_digest(
                candidate["candidate_subject"]
            )
        )
        candidate["self_digest"] = validator.artifact_self_digest(candidate)
        malformed.append(candidate)

    assert len(malformed) == 24
    for candidate in malformed:
        assert controller.validate_controller_artifact(candidate)

    bad_transition = copy.deepcopy(transition)
    bad_transition["from_phase"] = []
    bad_transition["transition_id"] = controller.derive_transition_id(
        bad_transition
    )
    bad_transition["self_digest"] = validator.artifact_self_digest(
        bad_transition
    )
    assert controller.validate_controller_transition(state, bad_transition)

    bad_state = copy.deepcopy(attached)
    bad_state["candidate_subject"]["generation"] = {}
    bad_state["candidate_subject_digest"] = (
        controller.derive_candidate_subject_digest(
            bad_state["candidate_subject"]
        )
    )
    bad_state["self_digest"] = validator.artifact_self_digest(bad_state)
    assert controller.validate_controller_state_successor(state, bad_state)

    bad_manifest = copy.deepcopy(manifest)
    bad_manifest["generation"] = {}
    bad_manifest["self_digest"] = validator.artifact_self_digest(bad_manifest)
    assert controller.validate_manifest_successor(manifest, bad_manifest)

    for value in ([], {}):
        bad_schema = copy.deepcopy(state)
        bad_schema["schema_version"] = copy.deepcopy(value)
        bad_schema["self_digest"] = validator.artifact_self_digest(bad_schema)
        assert controller.validate_controller_artifact(bad_schema)

    bad_pending = copy.deepcopy(state)
    bad_pending["pending_outbox"] = {"schema_version": []}
    bad_pending["pending_outbox_digest"] = D1
    bad_pending["self_digest"] = validator.artifact_self_digest(bad_pending)
    assert controller.validate_controller_artifact(bad_pending)

    request = json.loads(outbox["prepared_payload_json"])
    request["expected_external_sequence"] = []
    malformed_request = copy.deepcopy(outbox)
    malformed_request["prepared_payload_json"] = _canonical_json(request)
    malformed_request["prepared_payload_digest"] = (
        validator.canonical_digest(request)
    )
    malformed_request["request_digest"] = validator.canonical_digest({
        "schema_version": "s2_5_recovery_anchor_request_bytes_v1",
        "canonical_json": malformed_request["prepared_payload_json"],
    })
    malformed_request["self_digest"] = validator.artifact_self_digest(
        malformed_request
    )
    assert controller.validate_controller_artifact(malformed_request)

    for field, value in (("basename", []), ("start_id", {})):
        bad_inventory = copy.deepcopy(manifest)
        bad_inventory["journal_inventory"][0][field] = value
        bad_inventory["self_digest"] = validator.artifact_self_digest(
            bad_inventory
        )
        assert controller.validate_controller_artifact(bad_inventory)

    bad_replay = copy.deepcopy(manifest)
    bad_replay["replay_ledger"]["authorization_ids"] = [[]]
    bad_replay["self_digest"] = validator.artifact_self_digest(bad_replay)
    assert controller.validate_controller_artifact(bad_replay)
