"""Public behavior for the controller-v2 durable recovery store."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
for candidate in (
    ROOT / "helper_scripts" / "maintenance_scripts",
    ROOT / "program_code" / "ml_training",
    ROOT / "tests" / "structure",
):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_s2_5_disposable_profile as profile  # noqa: E402
import agent_governance_s2_5_recovery_controller as controller  # noqa: E402
import agent_governance_s2_5_recovery_store as store  # noqa: E402
import agent_governance_s2_5_recovery_store_v2 as store_v2  # noqa: E402
import test_agent_governance_s2_5_recovery_controller as controller_cases  # noqa: E402
from test_agent_governance_s2_5_recovery_store import (  # noqa: E402
    HEAD as LEGACY_HEAD,
    _PosixFixtureDriver,
    _seed_fixture_manifest,
    _snapshot_fixture,
    _write_json,
)


def _canonical_json(value: dict) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _seal(value: dict) -> dict:
    sealed = copy.deepcopy(value)
    sealed["self_digest"] = validator.artifact_self_digest(sealed)
    return sealed


@pytest.fixture
def controller_case_signing(tmp_path, monkeypatch):
    delegated = controller_cases._fixed_capture_trust_root.__wrapped__(
        tmp_path,
        monkeypatch,
    )
    next(delegated)
    try:
        yield
    finally:
        try:
            next(delegated)
        except StopIteration:
            pass


def _root_identity(root: Path) -> dict:
    observed = root.stat()
    return {
        "canonical_path": profile.DISPOSABLE_STATE_ROOT,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "mode": f"{stat.S_IMODE(observed.st_mode):04o}",
        "uid": profile.PROFILE_UID,
        "gid": profile.PROFILE_GID,
        "nlink": 2,
        "is_directory": True,
    }


def _seed_terminal_journal(root: Path) -> list[dict]:
    entry = {
        "seq": 0,
        "state": "TERMINAL_FAILED",
        "updated_at": "2030-01-01T00:00:00+00:00",
        "lock_release_status": "S2_5_LIFECYCLE_LOCK_RELEASED",
        "prev_entry_digest": None,
        "fsynced": True,
    }
    entry["entry_digest"] = validator.canonical_digest(entry)
    journal = _seal({
        "schema_version": "s2_5_start_journal_v2_informal",
        "start_id": controller_cases.START,
        "append_only": True,
        "integrity_broken": False,
        "prior_payload_digest": None,
        "state": "TERMINAL_FAILED",
        "updated_at": "2030-01-01T00:00:00+00:00",
        "history": [entry],
        "replay_ledger_head": None,
    })
    path = root / f"{controller_cases.START}.journal.json"
    _write_json(path, journal)
    return [{
        "basename": path.name,
        "start_id": controller_cases.START,
        "file_digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "journal_head_digest": entry["entry_digest"],
        "terminal_state": "TERMINAL_FAILED",
    }]


def _manifest(state: dict) -> dict:
    subject = state["candidate_subject"]
    return _seal({
        "schema_version": controller.MANIFEST_SCHEMA,
        "store_id": controller.derive_store_id(subject["state_root_id"]),
        "stable_root_id": subject["stable_root_id"],
        "state_root_id": subject["state_root_id"],
        "source_head": subject["source_head"],
        "generation": subject["generation"],
        "phase": subject["phase"],
        "anchor_progress": subject["anchor_progress"],
        "previous_manifest_digest": subject["previous_manifest_digest"],
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
        "state_root_identity": copy.deepcopy(
            subject["state_root_identity"]
        ),
        "journal_inventory": copy.deepcopy(subject["journal_inventory"]),
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


def _seed_v2_genesis(root: Path) -> dict:
    identity = _root_identity(root)
    inventory = _seed_terminal_journal(root)
    journal_set_digest = validator.canonical_digest({
        "schema_version": "s2_5_recovery_journal_set_v2",
        "entries": inventory,
    })
    subject = controller_cases._subject()
    subject.update({
        "state_root_identity": identity,
        "state_root_id": validator.canonical_digest(identity),
        "journal_inventory": inventory,
        "journal_set_digest": journal_set_digest,
    })
    unresolved = json.loads(subject["unresolved_payload_json"])
    unresolved.update({
        "state_root_id": subject["state_root_id"],
        "journal_set_digest": journal_set_digest,
    })
    subject["unresolved_payload_json"] = _canonical_json(unresolved)
    subject["unresolved_state_digest"] = validator.canonical_digest(
        unresolved
    )
    _transition, _outbox, state = controller_cases._pending_state(
        subject,
        from_phase="GENESIS",
    )
    manifest = _manifest(state)
    assert controller.validate_controller_artifact(manifest) == []
    _write_json(root / store.MANIFEST_BASENAME, manifest)
    return manifest


def _map_fixed_profile_to_fixture(
    *,
    monkeypatch,
    state_root: Path,
    lock_root: Path,
) -> None:
    real_open = os.open
    real_fstat = os.fstat
    mapped = {
        store.DISPOSABLE_STATE_ROOT: str(state_root),
        store.recovery_lock.DISPOSABLE_LOCK_ROOT: str(lock_root),
    }

    def fixture_open(path, flags, mode=0o777, *, dir_fd=None):
        selected = mapped.get(str(path), path)
        if dir_fd is None:
            return real_open(selected, flags, mode)
        return real_open(selected, flags, mode, dir_fd=dir_fd)

    def fixed_profile_fstat(fd):
        observed = real_fstat(fd)
        return SimpleNamespace(
            st_mode=observed.st_mode,
            st_dev=observed.st_dev,
            st_ino=observed.st_ino,
            st_uid=profile.PROFILE_UID,
            st_gid=profile.PROFILE_GID,
            st_nlink=(
                2 if stat.S_ISDIR(observed.st_mode) else observed.st_nlink
            ),
        )

    monkeypatch.setattr(store.os, "open", fixture_open)
    monkeypatch.setattr(store.os, "fstat", fixed_profile_fstat)


def test_inspect_reconstructs_exact_external_bootstrap_v2_genesis(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    expected = _seed_v2_genesis(root)
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: controller_cases.TRUSTED_NOW,
    )

    verdict = store.S2_5RecoveryStore(
        _PosixFixtureDriver(root)
    ).inspect(source_head=controller_cases.HEAD)

    assert verdict == {
        "status": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        "manifest": expected,
        "reasons": [
            "the durable controller state is locally reproducible but "
            "external anchor trust remains unverified"
        ],
    }


@pytest.mark.parametrize("schema_version", ([], {}))
def test_inspect_types_non_string_manifest_schema_as_recovery_required(
    tmp_path,
    controller_case_signing,
    schema_version,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    manifest = _seed_v2_genesis(root)
    manifest["schema_version"] = schema_version
    _write_json(root / store.MANIFEST_BASENAME, manifest)

    verdict = store.S2_5RecoveryStore(
        _PosixFixtureDriver(root)
    ).inspect(source_head=controller_cases.HEAD)

    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["manifest"] is None
    assert verdict["reasons"] == ["manifest_integrity_failed"]


def test_inspect_rejects_boolean_manifest_wrapper_sequences(
    tmp_path,
    controller_case_signing,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    manifest = _seed_v2_genesis(root)
    manifest["pending_outbox"]["expected_external_sequence"] = False
    manifest["pending_outbox"]["candidate_external_sequence"] = True
    manifest["self_digest"] = validator.artifact_self_digest(manifest)
    _write_json(root / store.MANIFEST_BASENAME, manifest)

    verdict = store.S2_5RecoveryStore(
        _PosixFixtureDriver(root)
    ).inspect(source_head=controller_cases.HEAD)

    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["manifest"] is None
    assert verdict["reasons"] == ["manifest_integrity_failed"]


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("replay_ledger", "entry_count"), False),
        (("production_effect_count",), False),
    ),
)
def test_inspect_rejects_boolean_manifest_wrapper_integer_fields(
    tmp_path,
    controller_case_signing,
    path,
    value,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    manifest = _seed_v2_genesis(root)
    target = manifest
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    manifest["self_digest"] = validator.artifact_self_digest(manifest)
    _write_json(root / store.MANIFEST_BASENAME, manifest)

    verdict = store.S2_5RecoveryStore(
        _PosixFixtureDriver(root)
    ).inspect(source_head=controller_cases.HEAD)

    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["manifest"] is None
    assert verdict["reasons"] == ["manifest_integrity_failed"]


def test_v2_successor_rejects_expired_pending_transition(
    monkeypatch,
    controller_case_signing,
) -> None:
    _transition, _outbox, pending, first = controller_cases._genesis()
    _proof, attached = controller_cases._proof_state(
        pending,
        previous_manifest_digest=first["self_digest"],
    )
    attached_manifest = controller_cases._manifest(
        attached,
        previous_manifest_digest=first["self_digest"],
    )
    _transition, _outbox, consumed = controller_cases._next_phase_pending(
        attached,
        phase="CONSUMED",
        previous_manifest_digest=attached_manifest["self_digest"],
    )
    subject = consumed["candidate_subject"]
    snapshot = {
        "state_root_identity": copy.deepcopy(
            subject["state_root_identity"]
        ),
        "state_root_id": subject["state_root_id"],
        "controller_journal_inventory": copy.deepcopy(
            subject["journal_inventory"]
        ),
        "controller_journal_set_digest": subject["journal_set_digest"],
        "controller_replay_ledger": copy.deepcopy(
            subject["replay_ledger"]
        ),
    }
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: "2030-01-01T00:27:00+00:00",
    )

    candidate, errors = store_v2.build_successor_manifest(
        consumed,
        attached_manifest,
        snapshot,
        source_head=controller_cases.HEAD,
    )

    assert candidate is None
    assert any("pending transition is expired" in error for error in errors)


def test_inspect_classifies_historical_expired_outbox_without_corruption(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    expected = _seed_v2_genesis(root)
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: "2030-01-01T00:27:00+00:00",
    )

    verdict = store.S2_5RecoveryStore(
        _PosixFixtureDriver(root)
    ).inspect(source_head=controller_cases.HEAD)

    assert verdict == {
        "status": "OUTBOX_EXPIRED_REFRESH_REQUIRED",
        "manifest": expected,
        "reasons": ["pending transition is expired"],
    }


def test_proof_attachment_can_persist_after_original_admission_expiry(
    monkeypatch,
    controller_case_signing,
) -> None:
    _transition, _outbox, pending, first = controller_cases._genesis()
    _proof, attached = controller_cases._proof_state(
        pending,
        previous_manifest_digest=first["self_digest"],
    )
    subject = attached["candidate_subject"]
    snapshot = {
        "state_root_identity": copy.deepcopy(
            subject["state_root_identity"]
        ),
        "state_root_id": subject["state_root_id"],
        "controller_journal_inventory": copy.deepcopy(
            subject["journal_inventory"]
        ),
        "controller_journal_set_digest": subject["journal_set_digest"],
        "controller_replay_ledger": copy.deepcopy(
            subject["replay_ledger"]
        ),
    }
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: "2030-01-01T00:31:00+00:00",
    )

    candidate, errors = store_v2.build_successor_manifest(
        attached,
        first,
        snapshot,
        source_head=controller_cases.HEAD,
    )

    assert errors == []
    assert candidate is not None
    assert candidate["controller_state"] == attached


@pytest.mark.parametrize("rewrite_terminal_state", (False, True))
def test_live_prepared_to_consumed_projection_is_durably_reachable(
    tmp_path,
    monkeypatch,
    controller_case_signing,
    rewrite_terminal_state,
) -> None:
    state_root = tmp_path / "state"
    lock_root = tmp_path / "locks"
    state_root.mkdir(mode=0o700)
    lock_root.mkdir(mode=0o700)
    first = _seed_v2_genesis(state_root)
    _proof, attached = controller_cases._proof_state(
        first["controller_state"],
        previous_manifest_digest=first["self_digest"],
    )
    _map_fixed_profile_to_fixture(
        monkeypatch=monkeypatch,
        state_root=state_root,
        lock_root=lock_root,
    )
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: controller_cases.TRUSTED_NOW,
    )
    proof_outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD,
        controller_state=attached,
    )
    assert proof_outcome["status"] == (
        "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    )
    previous = proof_outcome["store"]["manifest"]

    ledger_entry = {
        "seq": 0,
        "prev_entry_digest": None,
        "authorization_id": controller_cases.AUTHORIZATION_ID,
        "start_id": controller_cases.START,
        "consumed_at": "2030-01-01T00:25:00+00:00",
        "fsynced": True,
    }
    ledger_entry["entry_digest"] = validator.canonical_digest(ledger_entry)
    ledger = _seal({
        "schema_version": "s2_5_authorization_replay_ledger_v1",
        "ledger_path": (
            f"{store.DISPOSABLE_STATE_ROOT}/"
            f"{store.REPLAY_LEDGER_BASENAME}"
        ),
        "entries": [ledger_entry],
        "append_only": True,
    })
    _write_json(
        state_root / store.REPLAY_LEDGER_BASENAME,
        ledger,
    )
    journal_path = (
        state_root / f"{controller_cases.START}.journal.json"
    )
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["replay_ledger_head"] = {
        "entry_count": 1,
        "tail_entry_digest": ledger_entry["entry_digest"],
    }
    if rewrite_terminal_state:
        journal["state"] = "TERMINAL_SUCCESS"
        journal["history"][-1]["state"] = "TERMINAL_SUCCESS"
        journal["history"][-1]["entry_digest"] = validator.canonical_digest({
            key: value
            for key, value in journal["history"][-1].items()
            if key != "entry_digest"
        })
    journal["self_digest"] = validator.artifact_self_digest(journal)
    _write_json(journal_path, journal)
    snapshot = _snapshot_fixture(state_root)

    _transition, _outbox, consumed = (
        controller_cases._next_phase_pending(
            previous["controller_state"],
            phase="CONSUMED",
            previous_manifest_digest=previous["self_digest"],
        )
    )
    subject = copy.deepcopy(consumed["candidate_subject"])
    previous_subject = previous["controller_state"]["candidate_subject"]
    subject.update({
        "state_root_identity": copy.deepcopy(
            previous_subject["state_root_identity"]
        ),
        "state_root_id": previous_subject["state_root_id"],
        "journal_inventory": copy.deepcopy(
            snapshot["controller_journal_inventory"]
        ),
        "journal_set_digest": snapshot[
            "controller_journal_set_digest"
        ],
        "replay_ledger": copy.deepcopy(
            snapshot["controller_replay_ledger"]
        ),
        "replay_ledger_head_digest": snapshot[
            "controller_replay_ledger"
        ]["head_digest"],
        "consumed_authorization_ids": list(
            snapshot["_ledger_authorization_ids"]
        ),
        "unresolved_payload_json": previous_subject[
            "unresolved_payload_json"
        ],
        "unresolved_state_digest": previous_subject[
            "unresolved_state_digest"
        ],
    })
    subject = controller_cases._replace_embedded_subject_artifact(
        subject,
        json_field="consumption_proof_json",
        digest_field="consumption_proof_digest",
        updates={
            "replay_ledger_head_digest": subject[
                "replay_ledger_head_digest"
            ],
        },
    )
    _transition, _outbox, consumed = controller_cases._pending_state(
        subject,
        from_phase="PREPARED",
    )

    assert controller.validate_controller_artifact(consumed) == []
    successor_errors = controller.validate_controller_state_successor(
        previous["controller_state"],
        consumed,
    )
    if rewrite_terminal_state:
        assert "phase transition changed immutable journal history or state" in (
            successor_errors
        )
    else:
        assert successor_errors == []
    outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD,
        controller_state=consumed,
    )
    if rewrite_terminal_state:
        assert outcome["status"] == "RECOVERY_REQUIRED"
        assert outcome["store"] is None
        assert outcome["store_failure"] == "controller_successor_invalid"
        return
    assert outcome["store_failure_detail"] is None, outcome[
        "store_failure_detail"
    ]
    assert outcome["store_failure"] is None
    assert outcome["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert outcome["store"]["manifest"]["phase"] == "CONSUMED"


def test_fixed_writer_durably_attaches_exact_unverified_anchor_proof(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    state_root = tmp_path / "state"
    lock_root = tmp_path / "locks"
    state_root.mkdir(mode=0o700)
    lock_root.mkdir(mode=0o700)
    previous = _seed_v2_genesis(state_root)
    _proof, successor = controller_cases._proof_state(
        previous["controller_state"],
        previous_manifest_digest=previous["self_digest"],
    )
    assert controller.validate_controller_state_successor(
        previous["controller_state"],
        successor,
    ) == []
    _map_fixed_profile_to_fixture(
        monkeypatch=monkeypatch,
        state_root=state_root,
        lock_root=lock_root,
    )
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: controller_cases.TRUSTED_NOW,
        raising=False,
    )

    outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD,
        controller_state=successor,
    )

    assert outcome["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert outcome["store_failure"] is None
    persisted = outcome["store"]
    assert persisted["manifest"]["controller_state"] == successor
    assert persisted["intent"]["issued_at"] == controller_cases.TRUSTED_NOW
    assert persisted["intent"]["expires_at"] == (
        "2030-01-01T00:30:00+00:00"
    )
    assert persisted["intent"]["prior_manifest_discriminator_digest"].startswith(
        "sha256:"
    )
    assert persisted["result"]["prior_manifest_discriminator_digest"] == (
        persisted["intent"]["prior_manifest_discriminator_digest"]
    )
    assert persisted["result"]["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert persisted["postcheck"]["status"] == "PASS"
    assert persisted["rollback"]["status"] == "NOT_REQUIRED"
    for name in ("intent", "result", "postcheck", "rollback"):
        assert persisted[name]["side_effect_class"] == "DISPOSABLE_TEST"
        assert persisted[name]["production_effect"] is False
        assert persisted[name]["production_authority"] is False
    verdict = store.S2_5RecoveryStore(
        _PosixFixtureDriver(state_root)
    ).inspect(source_head=controller_cases.HEAD)
    assert verdict["manifest"] == persisted["manifest"]
    assert verdict["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"


def test_unavailable_fixed_profile_stops_before_store_write(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    controller_state = _seed_v2_genesis(root)["controller_state"]
    manifest_bytes = (root / store.MANIFEST_BASENAME).read_bytes()
    calls: list[str] = []
    real_open = os.open

    def unavailable_open(path, flags, *args, **kwargs):
        if str(path) == store.recovery_lock.DISPOSABLE_LOCK_ROOT:
            calls.append(str(path))
            raise FileNotFoundError(path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(store.os, "open", unavailable_open)

    outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD,
        controller_state=controller_state,
    )

    assert outcome["status"] == "LOCAL_REPRODUCIBLE_UNVERIFIED"
    assert outcome["store"] is None
    assert outcome["production_effect"] is False
    assert outcome["production_authority"] is False
    assert calls == [store.recovery_lock.DISPOSABLE_LOCK_ROOT]
    assert (root / store.MANIFEST_BASENAME).read_bytes() == manifest_bytes


def test_fixed_writer_allows_late_proof_attachment_but_requires_anchor(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    state_root = tmp_path / "state"
    lock_root = tmp_path / "locks"
    state_root.mkdir(mode=0o700)
    lock_root.mkdir(mode=0o700)
    previous = _seed_v2_genesis(state_root)
    _proof, successor = controller_cases._proof_state(
        previous["controller_state"],
        previous_manifest_digest=previous["self_digest"],
    )
    before = (state_root / store.MANIFEST_BASENAME).read_bytes()
    _map_fixed_profile_to_fixture(
        monkeypatch=monkeypatch,
        state_root=state_root,
        lock_root=lock_root,
    )
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: "2030-01-01T00:31:00+00:00",
    )

    outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD,
        controller_state=successor,
    )

    assert outcome["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert outcome["store_failure"] is None
    assert outcome["store"]["manifest"]["controller_state"] == successor
    assert outcome["store"]["result"]["status"] == (
        "EXTERNAL_VERIFICATION_PENDING"
    )
    assert outcome["lock"]["rollback"]["status"] == "RELEASED"
    assert (state_root / store.MANIFEST_BASENAME).read_bytes() != before
    assert not (state_root / store.MANIFEST_TEMP_BASENAME).exists()


def test_fixed_writer_rejects_structurally_valid_manifest_fork(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    state_root = tmp_path / "state"
    lock_root = tmp_path / "locks"
    state_root.mkdir(mode=0o700)
    lock_root.mkdir(mode=0o700)
    previous = _seed_v2_genesis(state_root)
    _proof, fork = controller_cases._proof_state(
        previous["controller_state"],
        previous_manifest_digest=controller_cases.D1,
    )
    assert controller.validate_controller_artifact(fork) == []
    before = (state_root / store.MANIFEST_BASENAME).read_bytes()
    _map_fixed_profile_to_fixture(
        monkeypatch=monkeypatch,
        state_root=state_root,
        lock_root=lock_root,
    )
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: controller_cases.TRUSTED_NOW,
    )

    outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD,
        controller_state=fork,
    )

    assert outcome["status"] == "RECOVERY_REQUIRED"
    assert outcome["store"] is None
    assert outcome["store_failure"] == "controller_successor_invalid"
    assert outcome["lock"]["rollback"]["status"] == "RELEASED"
    assert (state_root / store.MANIFEST_BASENAME).read_bytes() == before
    assert not (state_root / store.MANIFEST_TEMP_BASENAME).exists()


def test_fixed_writer_never_auto_upgrades_v1_manifest(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    candidate_root = tmp_path / "candidate"
    legacy_root = tmp_path / "legacy"
    lock_root = tmp_path / "locks"
    candidate_root.mkdir(mode=0o700)
    legacy_root.mkdir(mode=0o700)
    lock_root.mkdir(mode=0o700)
    v2 = _seed_v2_genesis(candidate_root)
    _proof, successor = controller_cases._proof_state(
        v2["controller_state"],
        previous_manifest_digest=v2["self_digest"],
    )
    _seed_fixture_manifest(legacy_root)
    before = (legacy_root / store.MANIFEST_BASENAME).read_bytes()
    _map_fixed_profile_to_fixture(
        monkeypatch=monkeypatch,
        state_root=legacy_root,
        lock_root=lock_root,
    )

    outcome = store.persist_fixed_profile(
        source_head=LEGACY_HEAD,
        controller_state=successor,
    )

    assert outcome["status"] == "RECOVERY_REQUIRED"
    assert outcome["store"] is None
    assert outcome["store_failure"] == (
        "legacy_manifest_external_bootstrap_required"
    )
    assert (legacy_root / store.MANIFEST_BASENAME).read_bytes() == before
    assert not (legacy_root / store.MANIFEST_TEMP_BASENAME).exists()


def test_v2_short_write_returns_typed_recovery_and_visible_residue(
    tmp_path,
    monkeypatch,
    controller_case_signing,
) -> None:
    state_root = tmp_path / "state"
    lock_root = tmp_path / "locks"
    state_root.mkdir(mode=0o700)
    lock_root.mkdir(mode=0o700)
    previous = _seed_v2_genesis(state_root)
    _proof, successor = controller_cases._proof_state(
        previous["controller_state"],
        previous_manifest_digest=previous["self_digest"],
    )
    before = (state_root / store.MANIFEST_BASENAME).read_bytes()
    _map_fixed_profile_to_fixture(
        monkeypatch=monkeypatch,
        state_root=state_root,
        lock_root=lock_root,
    )
    monkeypatch.setattr(
        store_v2,
        "_trusted_now",
        lambda: controller_cases.TRUSTED_NOW,
    )
    mapped_open = store.os.open
    real_write = os.write
    temp_fd: list[int] = []

    def tracking_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = mapped_open(path, flags, mode, dir_fd=dir_fd)
        if str(path) == store.MANIFEST_TEMP_BASENAME:
            temp_fd[:] = [fd]
        return fd

    def short_write(fd, payload):
        if temp_fd and fd == temp_fd[0]:
            return real_write(fd, payload[:-1])
        return real_write(fd, payload)

    monkeypatch.setattr(store.os, "open", tracking_open)
    monkeypatch.setattr(store.os, "write", short_write)

    outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD,
        controller_state=successor,
    )

    assert outcome["status"] == "RECOVERY_REQUIRED"
    assert outcome["store_failure"] is None
    failed = outcome["store"]
    assert failed["result"]["failure_code"] == "manifest_temp_write_short"
    assert failed["result"]["status"] == "RECOVERY_REQUIRED"
    assert failed["postcheck"]["status"] == "RECOVERY_REQUIRED"
    assert failed["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert failed["rollback"]["operator_action_required"] is True
    for name in ("intent", "result", "postcheck", "rollback"):
        assert store.validate_local_artifact(failed[name]) == []
        assert failed[name]["side_effect_class"] == "DISPOSABLE_TEST"
    assert (state_root / store.MANIFEST_BASENAME).read_bytes() == before
    assert (state_root / store.MANIFEST_TEMP_BASENAME).is_file()
    assert store.S2_5RecoveryStore(
        _PosixFixtureDriver(state_root)
    ).inspect(source_head=controller_cases.HEAD)["status"] == (
        "RECOVERY_REQUIRED"
    )


@pytest.mark.parametrize(
    "mutation_kind",
    ("changed_bytes_with_old_digest", "identical_bytes_on_new_inode"),
)
def test_v2_pre_replace_cas_rejects_prior_discriminator_change(
    tmp_path, monkeypatch, controller_case_signing, mutation_kind
) -> None:
    state_root = tmp_path / "state"
    lock_root = tmp_path / "locks"
    state_root.mkdir(mode=0o700)
    lock_root.mkdir(mode=0o700)
    previous = _seed_v2_genesis(state_root)
    _proof, successor = controller_cases._proof_state(
        previous["controller_state"],
        previous_manifest_digest=previous["self_digest"],
    )
    manifest_path = state_root / store.MANIFEST_BASENAME
    prior_inode = manifest_path.stat().st_ino
    replacement_path = tmp_path / "replacement-manifest.json"
    if mutation_kind == "identical_bytes_on_new_inode":
        replacement_path.write_bytes(manifest_path.read_bytes())
        os.chmod(replacement_path, 0o600)
    _map_fixed_profile_to_fixture(
        monkeypatch=monkeypatch,
        state_root=state_root,
        lock_root=lock_root,
    )
    monkeypatch.setattr(
        store_v2, "_trusted_now", lambda: controller_cases.TRUSTED_NOW
    )
    mapped_open = store.os.open
    real_fsync = os.fsync
    temp_fd: list[int] = []
    changed: list[bool] = []

    def tracking_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = mapped_open(path, flags, mode, dir_fd=dir_fd)
        if str(path) == store.MANIFEST_TEMP_BASENAME:
            temp_fd[:] = [fd]
        return fd

    def mutate_prior_after_temp_fsync(fd):
        real_fsync(fd)
        if temp_fd and fd == temp_fd[0] and not changed:
            if mutation_kind == "identical_bytes_on_new_inode":
                os.replace(replacement_path, manifest_path)
            else:
                prior = json.loads(manifest_path.read_text(encoding="utf-8"))
                prior["phase"] = "RESOLVED"
                _write_json(manifest_path, prior)
            changed.append(True)

    monkeypatch.setattr(store.os, "open", tracking_open)
    monkeypatch.setattr(store.os, "fsync", mutate_prior_after_temp_fsync)

    outcome = store.persist_fixed_profile(
        source_head=controller_cases.HEAD, controller_state=successor
    )

    assert changed == [True]
    if mutation_kind == "identical_bytes_on_new_inode":
        assert manifest_path.stat().st_ino != prior_inode
    assert outcome["status"] == "RECOVERY_REQUIRED"
    assert outcome["store_failure"] is None
    failed = outcome["store"]
    assert failed["result"]["failure_code"] == "manifest_changed_during_manifest_write"
    assert failed["result"]["atomic_replace"] is False
    assert failed["postcheck"]["status"] == "RECOVERY_REQUIRED"
