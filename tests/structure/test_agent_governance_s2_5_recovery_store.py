"""Focused behavioral tests for the disposable S2.5 recovery manifest store."""

from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import sys
from inspect import signature
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

MANIFEST_SCHEMA = (
    ROOT / ".codex/schemas/s2_5_recovery_store_manifest_v1.schema.json"
)
LOCAL_SCHEMA_VERSIONS = (
    "s2_5_recovery_store_manifest_v1",
    "s2_5_recovery_anchor_entry_v1",
    "s2_5_recovery_store_intent_v1",
    "s2_5_recovery_store_result_v1",
    "s2_5_recovery_store_postcheck_v1",
    "s2_5_recovery_store_rollback_v1",
)
HEAD = "a" * 40
DIGEST = "sha256:" + "b" * 64
START_ID = "s2-5-" + "1" * 64
AUTHORIZATION_ID = "s2-5-auth-" + "2" * 64


def _mode(value: os.stat_result) -> str:
    return f"{stat.S_IMODE(value.st_mode):04o}"


class _PosixFixtureDriver:
    """Map the code-owned logical root to a real temporary directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.paths: list[str] = []
        self.open_fds: set[int] = set()

    def _track(self, fd: int) -> int:
        self.open_fds.add(fd)
        return fd

    def _root_observation(self, fd: int) -> dict[str, object]:
        observed = os.fstat(fd)
        return {
            "fd": fd,
            "device": observed.st_dev,
            "inode": observed.st_ino,
            "mode": _mode(observed),
            "uid": 1000,
            "gid": 1000,
            # The real target is Linux/systemd.  Darwin APFS changes a directory's
            # reported nlink as ordinary files are added, unlike the target filesystem.
            "nlink": 2,
            "is_directory": stat.S_ISDIR(observed.st_mode),
            "is_symlink": False,
        }

    def open_parent_directory(self, *, path, flags):
        import agent_governance_s2_5_recovery_store as store

        self.paths.append(path)
        assert path == store.DISPOSABLE_STATE_ROOT
        assert flags == store.PARENT_OPEN_FLAGS
        fd = self._track(
            os.open(
                self.root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
        )
        return self._root_observation(fd)

    def fstat_parent(self, *, fd):
        return self._root_observation(fd)

    def list_basenames(self, *, parent_fd):
        assert parent_fd in self.open_fds
        return sorted(os.listdir(parent_fd))

    def read_file_observation(self, *, parent_fd, basename, flags):
        import agent_governance_s2_5_recovery_store as store

        assert flags == store.READ_OPEN_FLAGS
        try:
            fd = os.open(
                basename,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return None
        try:
            observed = os.fstat(fd)
            chunks = []
            while True:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
            return {
                "bytes": b"".join(chunks),
                "device": observed.st_dev,
                "inode": observed.st_ino,
                "mode": _mode(observed),
                "uid": 1000,
                "gid": 1000,
                "nlink": observed.st_nlink,
                "is_regular_file": stat.S_ISREG(observed.st_mode),
            }
        finally:
            os.close(fd)

    def create_temp_file(self, *, parent_fd, basename, flags, mode):
        import agent_governance_s2_5_recovery_store as store

        assert basename == store.MANIFEST_TEMP_BASENAME
        assert flags == store.TEMP_OPEN_FLAGS
        fd = self._track(
            os.open(
                basename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                mode,
                dir_fd=parent_fd,
            )
        )
        observed = os.fstat(fd)
        return {
            "fd": fd,
            "device": observed.st_dev,
            "inode": observed.st_ino,
            "mode": _mode(observed),
            "uid": 1000,
            "gid": 1000,
            "nlink": observed.st_nlink,
            "is_regular_file": stat.S_ISREG(observed.st_mode),
        }

    def write_bytes(self, *, fd, payload):
        return os.write(fd, payload)

    def fsync_file(self, *, fd):
        os.fsync(fd)

    def atomic_replace(self, *, parent_fd, from_basename, to_basename):
        os.rename(
            from_basename,
            to_basename,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )

    def fsync_parent_dir(self, *, fd):
        os.fsync(fd)

    def close(self, *, fd):
        self.open_fds.remove(fd)
        os.close(fd)


def _seal(value):
    import aiml_gate_receipt_validator as validator

    value["self_digest"] = validator.artifact_self_digest(value)
    return value


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _seed_fixture_manifest(root: Path) -> dict:
    """Seed a fixture-only genesis; the public store intentionally cannot do this."""

    import agent_governance_s2_5_recovery_store as store

    driver = _PosixFixtureDriver(root)
    recovery_store = store.S2_5RecoveryStore(driver)
    observed_root = recovery_store._open_root()
    try:
        snapshot = recovery_store._snapshot(observed_root["fd"], observed_root)
        assert snapshot["manifest_observation"] is None
        candidate = recovery_store._candidate(
            snapshot,
            None,
            source_head=HEAD,
            phase="PREPARED",
            unresolved_state_digest=DIGEST,
            anchor_head_digest=None,
        )
    finally:
        recovery_store._close(observed_root["fd"])
    _write_json(root / store.MANIFEST_BASENAME, candidate)
    assert driver.open_fds == set()
    return candidate


def _snapshot_fixture(root: Path) -> dict:
    import agent_governance_s2_5_recovery_store as store

    recovery_store = store.S2_5RecoveryStore(_PosixFixtureDriver(root))
    observed_root = recovery_store._open_root()
    try:
        return recovery_store._snapshot(observed_root["fd"], observed_root)
    finally:
        recovery_store._close(observed_root["fd"])


def _reseal_chain_artifact(value: dict) -> dict:
    import aiml_gate_receipt_validator as validator

    for entry in value["history"] if "history" in value else value["entries"]:
        entry["entry_digest"] = validator.canonical_digest({
            key: item for key, item in entry.items() if key != "entry_digest"
        })
    value["self_digest"] = validator.artifact_self_digest(value)
    return value


def _valid_journal(*, replay_ledger_head=None) -> dict:
    import aiml_gate_receipt_validator as validator

    entry = {
        "seq": 0,
        "state": "TERMINAL_FAILED",
        "updated_at": "2030-01-01T00:00:00+00:00",
        "lock_release_status": "S2_5_LIFECYCLE_LOCK_RELEASED",
        "prev_entry_digest": None,
        "fsynced": True,
    }
    entry["entry_digest"] = validator.canonical_digest(entry)
    return _seal({
        "schema_version": "s2_5_start_journal_v2_informal",
        "start_id": START_ID,
        "append_only": True,
        "integrity_broken": False,
        "prior_payload_digest": None,
        "state": "TERMINAL_FAILED",
        "updated_at": "2030-01-01T00:00:00+00:00",
        "history": [entry],
        "replay_ledger_head": replay_ledger_head,
    })


def _valid_ledger() -> dict:
    import agent_governance_s2_5_recovery_store as store
    import aiml_gate_receipt_validator as validator

    entry = {
        "seq": 0,
        "prev_entry_digest": None,
        "authorization_id": AUTHORIZATION_ID,
        "start_id": START_ID,
        "consumed_at": "2030-01-01T00:00:00+00:00",
        "fsynced": True,
    }
    entry["entry_digest"] = validator.canonical_digest(entry)
    return _seal({
        "schema_version": "s2_5_authorization_replay_ledger_v1",
        "ledger_path": (
            f"{store.DISPOSABLE_STATE_ROOT}/{store.REPLAY_LEDGER_BASENAME}"
        ),
        "entries": [entry],
        "append_only": True,
    })


def _persist_with_inventory(root: Path):
    import agent_governance_s2_5_recovery_store as store

    ledger = _valid_ledger()
    ledger_head = {
        "entry_count": len(ledger["entries"]),
        "tail_entry_digest": ledger["entries"][-1]["entry_digest"],
    }
    journal = _valid_journal(replay_ledger_head=ledger_head)
    _write_json(root / f"{START_ID}.journal.json", journal)
    _write_json(root / store.REPLAY_LEDGER_BASENAME, ledger)
    _seed_fixture_manifest(root)
    driver = _PosixFixtureDriver(root)
    recovery_store = store.S2_5RecoveryStore(driver)
    outcome = recovery_store._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )
    return driver, outcome


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("append_only", False),
        ("integrity_broken", True),
        ("entry_fsynced", False),
        ("tail_updated_at", "2030-01-01T00:00:01+00:00"),
        ("nonterminal_state", "APPLYING"),
    ],
)
def test_snapshot_rejects_journal_weaker_than_the_canonical_wal(
    tmp_path, mutation, value
) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    journal = _valid_journal()
    if mutation == "entry_fsynced":
        journal["history"][-1]["fsynced"] = value
    elif mutation == "tail_updated_at":
        journal["updated_at"] = value
    elif mutation == "nonterminal_state":
        journal["state"] = value
        journal["history"][-1]["state"] = value
    else:
        journal[mutation] = value
        if mutation == "integrity_broken":
            journal["prior_payload_digest"] = DIGEST
    _write_json(
        root / f"{START_ID}.journal.json",
        _reseal_chain_artifact(journal),
    )

    with pytest.raises(store.RecoveryStoreError) as caught:
        _snapshot_fixture(root)

    assert caught.value.code == "journal_integrity_failed"


@pytest.mark.parametrize(
    ("field", "value"),
    [("fsynced", False), ("start_id", "caller-arbitrary")],
)
def test_snapshot_rejects_replay_ledger_weaker_than_canonical_attestation(
    tmp_path, field, value
) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    ledger = _valid_ledger()
    ledger["entries"][0][field] = value
    _write_json(
        root / store.REPLAY_LEDGER_BASENAME,
        _reseal_chain_artifact(ledger),
    )

    with pytest.raises(store.RecoveryStoreError) as caught:
        _snapshot_fixture(root)

    assert caught.value.code == "replay_ledger_integrity_failed"


def test_terminal_journal_head_must_be_covered_by_the_exact_ledger(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    ledger = _valid_ledger()
    journal = _valid_journal(replay_ledger_head={
        "entry_count": 1,
        "tail_entry_digest": "sha256:" + "9" * 64,
    })
    _write_json(root / f"{START_ID}.journal.json", journal)
    _write_json(root / store.REPLAY_LEDGER_BASENAME, ledger)

    with pytest.raises(store.RecoveryStoreError) as caught:
        _snapshot_fixture(root)

    assert caught.value.code == "journal_replay_ledger_coverage_failed"


def test_manifest_schema_binds_root_identity_and_exact_durable_inventory() -> None:
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))

    required = set(schema["required"])
    assert {
        "state_root_identity",
        "journal_inventory",
        "journal_set_digest",
        "replay_ledger",
        "production_effect_count",
    } <= required
    assert schema["properties"]["journal_inventory"]["type"] == "array"
    assert schema["properties"]["journal_inventory"]["uniqueItems"] is True
    assert schema["properties"]["production_effect_count"] == {"const": 0}


def test_every_local_store_artifact_pins_zero_production_effects() -> None:
    for schema_version in LOCAL_SCHEMA_VERSIONS:
        schema = json.loads(
            (
                ROOT / f".codex/schemas/{schema_version}.schema.json"
            ).read_text(encoding="utf-8")
        )
        assert "production_effect_count" in schema["required"], schema_version
        assert schema["properties"]["production_effect_count"] == {"const": 0}


def test_profile_is_the_code_owned_uid_1000_user_manager_runtime() -> None:
    import agent_governance_s2_5_recovery_store as store

    expected_path = (
        "/run/user/1000/arcane-equilibrium-aiml-s2e/s2_5-recovery"
    )
    assert store.DISPOSABLE_STATE_ROOT == expected_path
    assert store.PROFILE_ID == "s2_5_recovery_user_systemd_disposable_v1"
    for schema_version in LOCAL_SCHEMA_VERSIONS:
        schema = json.loads(
            (
                ROOT / f".codex/schemas/{schema_version}.schema.json"
            ).read_text(encoding="utf-8")
        )
        assert "target_profile_id" in schema["required"], schema_version
        assert schema["properties"]["target_profile_id"] == {
            "const": store.PROFILE_ID
        }
    manifest_schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    identity = manifest_schema["$defs"]["stateRootIdentity"]["properties"]
    assert identity["canonical_path"] == {"const": expected_path}
    assert identity["uid"] == {"const": 1000}
    assert identity["gid"] == {"const": 1000}


def test_public_writer_has_no_caller_path_unit_nonce_or_identity_surface() -> None:
    import agent_governance_s2_5_recovery_store as store

    assert not hasattr(store.S2_5RecoveryStore, "persist")
    assert set(signature(store.persist_fixed_profile).parameters) == {
        "source_head",
        "controller_state",
    }
    assert not hasattr(store.S2_5RecoveryStore, "simulate_persist")
    assert set(signature(store.simulate_persist).parameters) == {
        "source_head",
        "phase",
        "unresolved_state_digest",
        "anchor_head_digest",
        "issued_at",
        "expires_at",
    }


def test_public_simulation_rejects_substituted_callable_without_invocation() -> None:
    import agent_governance_s2_5_recovery_store as store

    class Trap:
        invoked = False

        def __call__(self, *args, **kwargs):
            self.invoked = True
            raise AssertionError("substituted callable must not run")

    trap = Trap()
    with pytest.raises(TypeError):
        store.simulate_persist(
            source_head=HEAD,
            phase="PREPARED",
            unresolved_state_digest=DIGEST,
            anchor_head_digest=None,
            issued_at="2030-01-01T00:00:00Z",
            expires_at="2030-01-01T00:05:00Z",
            driver=trap,
        )
    assert trap.invoked is False

    outcome = store.simulate_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )
    assert outcome["effect_performed"] is False
    assert outcome["store_write_authority"] is False


def test_simulation_never_mints_a_store_accepted_session_or_authority(
    tmp_path,
) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    _seed_fixture_manifest(root)
    driver = _PosixFixtureDriver(root)
    outcome = store.S2_5RecoveryStore(driver)._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )

    assert outcome["simulation_only"] is True
    assert outcome["store_write_authority"] is False
    for name in ("intent", "result", "postcheck", "rollback"):
        assert outcome[name]["session_class"] == "SIMULATION_ONLY"
        assert outcome[name]["store_write_authority"] is False
        assert store.validate_local_artifact(outcome[name]) == []


def test_simulation_guards_every_store_effect_boundary(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    _seed_fixture_manifest(root)
    outcome = store.S2_5RecoveryStore(
        _PosixFixtureDriver(root)
    )._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )

    assert outcome["result"]["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert outcome["guarded_effect_stages"] == [
        "POST_ACQUIRE_FINAL",
        "TEMP_CREATE",
        "TEMP_WRITE",
        "TEMP_FILE_FSYNC",
        "ATOMIC_REPLACE",
        "PARENT_DIRECTORY_FSYNC",
    ]


def test_fixed_writer_source_has_no_injected_driver_callback_or_bearer_token() -> None:
    import agent_governance_s2_5_recovery_lock as recovery_lock
    import agent_governance_s2_5_recovery_store as store

    assert not hasattr(recovery_lock, "release_recovery_dual_lock")
    source = (
        HELPERS / "agent_governance_s2_5_recovery_store.py"
    ).read_text(encoding="utf-8")
    fixed = source[source.index("def persist_fixed_profile("):]
    header = fixed[:fixed.index(") -> dict[str, Any]:")]
    assert "driver:" not in header
    assert "callback" not in header
    assert "lock_token" not in source
    for name in (
        "FixedPosixRecoveryDriver",
        "FixedRecoverySession",
        "active_sessions",
    ):
        assert not hasattr(store, name), name


def test_public_fixed_writer_has_no_closure_capability_registry() -> None:
    import agent_governance_s2_5_recovery_store as store

    assert store.persist_fixed_profile.__closure__ is None


def test_arbitrary_driver_cannot_resolve_fixed_store_write_authority() -> None:
    import agent_governance_s2_5_recovery_store as store

    class ArbitraryDriver:
        pass

    session = SimpleNamespace(
        active=True,
        driver=ArbitraryDriver(),
        source_head=HEAD,
        lease={"transaction_active": True},
    )
    with pytest.raises(store.RecoveryStoreError) as caught:
        store._resolve_recovery_session(
            driver=session.driver,
            source_head=HEAD,
            session_context=session,
        )

    assert caught.value.code == "fixed_recovery_session_invalid"


def test_forged_fixed_session_is_rejected_before_state_root_io(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _PosixFixtureDriver(root)
    with pytest.raises(store.RecoveryStoreError) as caught:
        store.S2_5RecoveryStore(driver)._persist_with_guard(
            session_context=object(),
            source_head=HEAD,
            phase="PREPARED",
            unresolved_state_digest=DIGEST,
            anchor_head_digest=None,
            issued_at="2030-01-01T00:00:00Z",
            expires_at="2030-01-01T00:05:00Z",
        )

    assert caught.value.code == "fixed_recovery_session_invalid"
    assert driver.paths == []


def test_public_persist_cannot_bootstrap_an_empty_root(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _PosixFixtureDriver(root)

    with pytest.raises(store.RecoveryStoreError) as caught:
        store.S2_5RecoveryStore(driver)._exercise_simulation_persist(
            source_head=HEAD,
            phase="PREPARED",
            unresolved_state_digest=DIGEST,
            anchor_head_digest=None,
            issued_at="2030-01-01T00:00:00Z",
            expires_at="2030-01-01T00:05:00Z",
        )

    assert caught.value.code == "verified_external_bootstrap_required"
    assert list(root.iterdir()) == []


def test_deleted_manifest_cannot_be_rebuilt_by_ordinary_persist(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    _seed_fixture_manifest(root)
    driver = _PosixFixtureDriver(root)
    recovery_store = store.S2_5RecoveryStore(driver)
    recovery_store._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )
    (root / store.MANIFEST_BASENAME).unlink()

    with pytest.raises(store.RecoveryStoreError) as caught:
        recovery_store._exercise_simulation_persist(
            source_head=HEAD,
            phase="PREPARED",
            unresolved_state_digest=DIGEST,
            anchor_head_digest=None,
            issued_at="2030-01-01T00:00:00Z",
            expires_at="2030-01-01T00:05:00Z",
        )

    assert caught.value.code == "verified_external_bootstrap_required"
    assert not (root / store.MANIFEST_BASENAME).exists()


def test_store_commits_only_to_code_owned_root_and_returns_typed_chain(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "mapped-code-owned-root"
    root.mkdir(mode=0o700)
    _seed_fixture_manifest(root)
    driver = _PosixFixtureDriver(root)

    outcome = store.S2_5RecoveryStore(driver)._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )

    assert outcome["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert driver.paths and set(driver.paths) == {store.DISPOSABLE_STATE_ROOT}
    assert outcome["result"]["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert outcome["result"]["file_fsynced"] is True
    assert outcome["result"]["atomic_replace"] is True
    assert outcome["result"]["directory_fsynced"] is True
    assert outcome["postcheck"]["status"] == "PASS"
    assert outcome["rollback"]["status"] == "NOT_REQUIRED"
    assert outcome["manifest"]["journal_inventory"] == []
    assert outcome["manifest"]["replay_ledger"]["present"] is False
    assert store.validate_local_artifact(outcome["intent"]) == []
    assert store.validate_local_artifact(outcome["result"]) == []
    assert store.validate_local_artifact(outcome["postcheck"]) == []
    assert store.validate_local_artifact(outcome["rollback"]) == []
    assert store.validate_local_artifact(outcome["manifest"]) == []
    assert sorted(path.name for path in root.iterdir()) == [store.MANIFEST_BASENAME]
    assert driver.open_fds == set()


def test_manifest_binds_exact_journal_set_and_replay_ledger_head(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    driver, outcome = _persist_with_inventory(root)

    inventory = outcome["manifest"]["journal_inventory"]
    assert [item["basename"] for item in inventory] == [
        f"{START_ID}.journal.json"
    ]
    assert inventory[0]["journal_head_digest"] == (
        _valid_journal()["history"][-1]["entry_digest"]
    )
    assert outcome["manifest"]["replay_ledger"] == {
        "basename": "authorization-replay-ledger.json",
        "present": True,
        "file_digest": outcome["manifest"]["replay_ledger"]["file_digest"],
        "entry_count": 1,
        "head_digest": _valid_ledger()["entries"][-1]["entry_digest"],
    }
    assert outcome["manifest"]["consumed_authorization_ids"] == [AUTHORIZATION_ID]
    assert driver.open_fds == set()


@pytest.mark.parametrize("removed_basename", ["journal", "ledger"])
def test_ordinary_persist_rejects_inventory_shrink(tmp_path, removed_basename) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver, _ = _persist_with_inventory(root)
    target = (
        root / f"{START_ID}.journal.json"
        if removed_basename == "journal"
        else root / store.REPLAY_LEDGER_BASENAME
    )
    target.unlink()

    with pytest.raises(store.RecoveryStoreError) as caught:
        store.S2_5RecoveryStore(driver)._exercise_simulation_persist(
            source_head=HEAD,
            phase="PREPARED",
            unresolved_state_digest=DIGEST,
            anchor_head_digest=None,
            issued_at="2030-01-01T00:00:00Z",
            expires_at="2030-01-01T00:05:00Z",
        )

    assert caught.value.code == {
        "journal": "manifest_integrity_failed",
        "ledger": "journal_replay_ledger_coverage_failed",
    }[removed_basename]


def test_ordinary_persist_rejects_unanchored_inventory_growth(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    _seed_fixture_manifest(root)
    driver = _PosixFixtureDriver(root)
    added_start_id = "s2-5-" + "3" * 64
    journal = _valid_journal()
    journal["start_id"] = added_start_id
    journal["self_digest"] = __import__(
        "aiml_gate_receipt_validator"
    ).artifact_self_digest(journal)
    _write_json(root / f"{added_start_id}.journal.json", journal)

    with pytest.raises(store.RecoveryStoreError) as caught:
        store.S2_5RecoveryStore(driver)._exercise_simulation_persist(
            source_head=HEAD,
            phase="PREPARED",
            unresolved_state_digest=DIGEST,
            anchor_head_digest=None,
            issued_at="2030-01-01T00:00:00Z",
            expires_at="2030-01-01T00:05:00Z",
        )

    assert caught.value.code == "manifest_integrity_failed"


def test_unlinked_journal_never_re_admits_the_manifest(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver, _ = _persist_with_inventory(root)
    (root / f"{START_ID}.journal.json").unlink()

    verdict = store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)

    assert verdict["status"] == store.STATUS_RECOVERY_REQUIRED
    assert verdict["reasons"] == ["manifest_integrity_failed"]


def test_missing_manifest_over_existing_durable_inventory_is_not_genesis(
    tmp_path,
) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver, _ = _persist_with_inventory(root)
    (root / store.MANIFEST_BASENAME).unlink()

    verdict = store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)

    assert verdict["status"] == store.STATUS_RECOVERY_REQUIRED
    assert verdict["reasons"] == ["manifest_missing_for_nonempty_state_root"]


def test_extra_or_renamed_state_file_fails_closed(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver, _ = _persist_with_inventory(root)
    (root / "unexpected.json").write_text("{}", encoding="utf-8")
    os.chmod(root / "unexpected.json", 0o600)
    assert store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)["status"] == (
        store.STATUS_RECOVERY_REQUIRED
    )

    (root / "unexpected.json").unlink()
    renamed = root / ("s2-5-" + "3" * 64 + ".journal.json")
    (root / f"{START_ID}.journal.json").rename(renamed)
    assert store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)["status"] == (
        store.STATUS_RECOVERY_REQUIRED
    )


def test_corrupt_or_hardlinked_manifest_fails_closed(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    _seed_fixture_manifest(root)
    driver = _PosixFixtureDriver(root)
    persisted = store.S2_5RecoveryStore(driver)
    persisted._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )
    manifest = root / store.MANIFEST_BASENAME
    original = manifest.read_bytes()
    manifest.write_text("{", encoding="utf-8")
    assert persisted.inspect(source_head=HEAD)["status"] == (
        store.STATUS_RECOVERY_REQUIRED
    )

    manifest.write_bytes(original)
    os.chmod(manifest, 0o600)
    os.link(manifest, root / "manifest-hardlink")
    assert persisted.inspect(source_head=HEAD)["status"] == (
        store.STATUS_RECOVERY_REQUIRED
    )


def test_full_root_replacement_is_detected_even_with_copied_manifest(tmp_path) -> None:
    import agent_governance_s2_5_recovery_store as store

    original = tmp_path / "original"
    original.mkdir(mode=0o700)
    _seed_fixture_manifest(original)
    driver = _PosixFixtureDriver(original)
    store.S2_5RecoveryStore(driver)._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    shutil.copy2(
        original / store.MANIFEST_BASENAME,
        replacement / store.MANIFEST_BASENAME,
    )
    driver.root = replacement

    verdict = store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)

    assert verdict["status"] == store.STATUS_RECOVERY_REQUIRED
    assert verdict["reasons"] == ["manifest_integrity_failed"]


def test_coherent_v1_local_reseal_requires_explicit_external_bootstrap(
    tmp_path,
) -> None:
    import agent_governance_s2_5_recovery_store as store
    import aiml_gate_receipt_validator as validator

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    _seed_fixture_manifest(root)
    driver = _PosixFixtureDriver(root)
    outcome = store.S2_5RecoveryStore(driver)._exercise_simulation_persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )
    journal = _valid_journal()
    journal_path = root / f"{START_ID}.journal.json"
    _write_json(journal_path, journal)
    manifest = outcome["manifest"]
    manifest["journal_inventory"] = [{
        "basename": journal_path.name,
        "start_id": START_ID,
        "file_digest": "sha256:" + __import__("hashlib").sha256(
            journal_path.read_bytes()
        ).hexdigest(),
        "journal_head_digest": journal["history"][-1]["entry_digest"],
    }]
    manifest["journal_set_digest"] = validator.canonical_digest({
        "schema_version": "s2_5_recovery_journal_set_v1",
        "entries": manifest["journal_inventory"],
    })
    manifest["self_digest"] = validator.artifact_self_digest(manifest)
    _write_json(root / store.MANIFEST_BASENAME, manifest)

    verdict = store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)

    assert verdict == {
        "status": "RECOVERY_REQUIRED_LEGACY_DIGEST_ONLY",
        "manifest": None,
        "reasons": ["legacy_manifest_external_bootstrap_required"],
        "auto_upgrade_allowed": False,
        "external_bootstrap_required": True,
        "effect_admitted": False,
        "clear_admitted": False,
        "production_effect": False,
        "production_authority": False,
    }
