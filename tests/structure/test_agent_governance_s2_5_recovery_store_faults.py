"""Crash/fault-window acceptance for the strict S2.5 recovery store."""

from __future__ import annotations

import os
import sys
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

import agent_governance_s2_5_recovery_store as store  # noqa: E402
from test_agent_governance_s2_5_recovery_store import (  # noqa: E402
    DIGEST,
    HEAD,
    _PosixFixtureDriver,
    _seed_fixture_manifest,
)


def _persist(driver, *, seed_fixture=True):
    if seed_fixture and not (
        driver.root / store.MANIFEST_BASENAME
    ).exists():
        _seed_fixture_manifest(driver.root)
    return store.S2_5RecoveryStore(driver).persist(
        source_head=HEAD,
        phase="PREPARED",
        unresolved_state_digest=DIGEST,
        anchor_head_digest=None,
        issued_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-01T00:05:00Z",
    )


class _FaultDriver(_PosixFixtureDriver):
    def __init__(self, root: Path, fault: str) -> None:
        super().__init__(root)
        self.fault = fault
        self.open_count = 0

    def open_parent_directory(self, *, path, flags):
        self.open_count += 1
        if self.fault == "postcheck_open_error" and self.open_count == 3:
            raise OSError("injected postcheck open failure")
        return super().open_parent_directory(path=path, flags=flags)

    def create_temp_file(self, **kwargs):
        if self.fault == "before_temp":
            raise store.RecoveryStoreCrash("before temp create")
        observed = super().create_temp_file(**kwargs)
        if self.fault.startswith("temp_fact:"):
            field, value = self.fault.removeprefix("temp_fact:").split("=", 1)
            observed[field] = {
                "uid": 999,
                "gid": 999,
                "mode": "0644",
                "nlink": 2,
                "device": -1,
                "is_regular_file": False,
            }[field]
        return observed

    def write_bytes(self, *, fd, payload):
        if self.fault == "before_write":
            raise store.RecoveryStoreCrash("before write")
        if self.fault == "short_write":
            return os.write(fd, payload[:-1])
        return super().write_bytes(fd=fd, payload=payload)

    def fsync_file(self, *, fd):
        if self.fault == "before_file_fsync":
            raise store.RecoveryStoreCrash("before file fsync")
        return super().fsync_file(fd=fd)

    def atomic_replace(self, **kwargs):
        if self.fault == "before_atomic_replace":
            raise store.RecoveryStoreCrash("before atomic replace")
        result = super().atomic_replace(**kwargs)
        if self.fault == "after_atomic_replace":
            raise store.RecoveryStoreCrash("after atomic replace")
        return result

    def fsync_parent_dir(self, *, fd):
        result = super().fsync_parent_dir(fd=fd)
        if self.fault == "after_directory_fsync":
            raise store.RecoveryStoreCrash("after directory fsync")
        return result


def test_short_write_returns_typed_failure_chain_and_leaves_visible_residue(
    tmp_path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _FaultDriver(root, "short_write")

    outcome = _persist(driver)

    assert outcome["status"] == store.STATUS_RECOVERY_REQUIRED
    assert outcome["result"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["result"]["failure_code"] == "manifest_temp_write_short"
    assert outcome["result"]["file_fsynced"] is False
    assert outcome["result"]["atomic_replace"] is False
    assert outcome["postcheck"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["rollback"]["operator_action_required"] is True
    assert (root / store.MANIFEST_TEMP_BASENAME).exists()
    assert store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)["status"] == (
        store.STATUS_RECOVERY_REQUIRED
    )
    for receipt in (
        outcome["intent"],
        outcome["result"],
        outcome["postcheck"],
        outcome["rollback"],
    ):
        assert store.validate_local_artifact(receipt) == []


@pytest.mark.parametrize(
    "fault",
    ["before_write", "before_file_fsync", "before_atomic_replace"],
)
def test_pre_replace_crash_leaves_temp_residue_that_blocks_restart(
    tmp_path, fault
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _FaultDriver(root, fault)

    with pytest.raises(store.RecoveryStoreCrash):
        _persist(driver)

    assert (root / store.MANIFEST_TEMP_BASENAME).exists()
    assert store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)["status"] == (
        store.STATUS_RECOVERY_REQUIRED
    )


def test_crash_before_temp_creation_preserves_seed_and_restart_observes_it(
    tmp_path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _FaultDriver(root, "before_temp")

    with pytest.raises(store.RecoveryStoreCrash):
        _persist(driver)

    assert sorted(path.name for path in root.iterdir()) == [store.MANIFEST_BASENAME]
    assert store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)["status"] == (
        store.STATUS_UNVERIFIED
    )


@pytest.mark.parametrize("fault", ["after_atomic_replace", "after_directory_fsync"])
def test_post_replace_crash_never_upgrades_local_bytes_to_trusted(
    tmp_path, fault
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _FaultDriver(root, fault)

    with pytest.raises(store.RecoveryStoreCrash):
        _persist(driver)

    assert (root / store.MANIFEST_BASENAME).is_file()
    assert not (root / store.MANIFEST_TEMP_BASENAME).exists()
    assert store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)["status"] == (
        store.STATUS_UNVERIFIED
    )


def test_independent_readback_failure_returns_recovery_chain(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _FaultDriver(root, "postcheck_open_error")

    outcome = _persist(driver)

    assert outcome["result"]["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert outcome["postcheck"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["postcheck"]["failure_code"] == (
        "manifest_independent_readback_failed"
    )
    assert outcome["postcheck"]["manifest_match"] is False
    assert outcome["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["status"] == store.STATUS_RECOVERY_REQUIRED


class _OSErrorDriver(_PosixFixtureDriver):
    def __init__(self, root: Path, fault: str) -> None:
        super().__init__(root)
        self.fault = fault

    def write_bytes(self, **kwargs):
        if self.fault == "write":
            raise OSError("injected write fault")
        return super().write_bytes(**kwargs)

    def fsync_file(self, **kwargs):
        if self.fault == "file_fsync":
            raise OSError("injected file fsync fault")
        return super().fsync_file(**kwargs)

    def atomic_replace(self, **kwargs):
        if self.fault == "atomic_replace":
            raise OSError("injected rename fault")
        return super().atomic_replace(**kwargs)

    def fsync_parent_dir(self, **kwargs):
        if self.fault == "directory_fsync":
            raise OSError("injected directory fsync fault")
        return super().fsync_parent_dir(**kwargs)


@pytest.mark.parametrize(
    ("fault", "failure_code"),
    [
        ("write", "manifest_temp_write_failed"),
        ("file_fsync", "manifest_temp_fsync_failed"),
        ("atomic_replace", "manifest_atomic_replace_failed"),
        ("directory_fsync", "manifest_directory_fsync_failed"),
    ],
)
def test_non_crash_io_faults_return_complete_typed_chain(
    tmp_path, fault, failure_code
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    outcome = _persist(_OSErrorDriver(root, fault))

    assert outcome["status"] == store.STATUS_RECOVERY_REQUIRED
    assert outcome["result"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["result"]["failure_code"] == failure_code
    assert outcome["postcheck"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["rollback"]["status"] == "RECOVERY_REQUIRED"
    for receipt in (
        outcome["intent"],
        outcome["result"],
        outcome["postcheck"],
        outcome["rollback"],
    ):
        assert store.validate_local_artifact(receipt) == []


@pytest.mark.parametrize(
    "fault",
    [
        "before_temp",
        "before_write",
        "before_file_fsync",
        "before_atomic_replace",
        "after_atomic_replace",
        "after_directory_fsync",
    ],
)
def test_restart_after_true_crash_emits_a_typed_recovery_attempt_chain(
    tmp_path, fault
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    with pytest.raises(store.RecoveryStoreCrash):
        _persist(_FaultDriver(root, fault))

    recovery = _persist(_PosixFixtureDriver(root))

    assert recovery["status"] in {
        store.STATUS_RECOVERY_REQUIRED,
        store.STATUS_UNVERIFIED,
    }
    for receipt in (
        recovery["intent"],
        recovery["result"],
        recovery["postcheck"],
        recovery["rollback"],
    ):
        assert store.validate_local_artifact(receipt) == []


@pytest.mark.parametrize(
    "fault",
    [
        "temp_fact:uid=bad",
        "temp_fact:gid=bad",
        "temp_fact:mode=bad",
        "temp_fact:nlink=bad",
        "temp_fact:device=bad",
        "temp_fact:is_regular_file=bad",
    ],
)
def test_temp_identity_or_shape_substitution_returns_typed_recovery(
    tmp_path, fault
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _FaultDriver(root, fault)

    outcome = _persist(driver)

    assert outcome["status"] == store.STATUS_RECOVERY_REQUIRED
    assert outcome["result"]["failure_code"] == "manifest_temp_precheck_failed"
    assert outcome["result"]["atomic_replace"] is False
    assert outcome["rollback"]["operator_action_required"] is True


class _ReadFactDriver(_PosixFixtureDriver):
    def __init__(self, root: Path, field: str, value) -> None:
        super().__init__(root)
        self.field = field
        self.value = value
        self.mutate = False

    def read_file_observation(self, **kwargs):
        observed = super().read_file_observation(**kwargs)
        if (
            self.mutate
            and kwargs["basename"] == store.MANIFEST_BASENAME
            and observed is not None
        ):
            observed[self.field] = self.value
        return observed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uid", 999),
        ("gid", 999),
        ("mode", "0644"),
        ("nlink", 2),
        ("device", -1),
        ("is_regular_file", False),
    ],
)
def test_existing_manifest_file_facts_are_revalidated_on_every_read(
    tmp_path, field, value
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _ReadFactDriver(root, field, value)
    _persist(driver)
    driver.mutate = True

    verdict = store.S2_5RecoveryStore(driver).inspect(source_head=HEAD)

    assert verdict["status"] == store.STATUS_RECOVERY_REQUIRED
    assert verdict["reasons"] == ["state_file_precheck_failed"]


class _RootFactDriver(_PosixFixtureDriver):
    def __init__(self, root: Path, field: str, value) -> None:
        super().__init__(root)
        self.field = field
        self.value = value

    def open_parent_directory(self, **kwargs):
        observed = super().open_parent_directory(**kwargs)
        observed[self.field] = self.value
        return observed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uid", 999),
        ("gid", 999),
        ("mode", "0755"),
        ("nlink", 0),
        ("device", None),
        ("inode", 0),
        ("is_directory", False),
        ("is_symlink", True),
    ],
)
def test_state_root_identity_or_shape_substitution_is_rejected_before_intent(
    tmp_path, field, value
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _RootFactDriver(root, field, value)

    with pytest.raises(store.RecoveryStoreError) as caught:
        _persist(driver, seed_fixture=False)

    assert caught.value.code == "state_root_precheck_failed"
    assert list(root.iterdir()) == []


class _ReplacementDriver(_PosixFixtureDriver):
    def __init__(self, root: Path, replacement: Path) -> None:
        super().__init__(root)
        self.replacement = replacement
        self.opens = 0

    def open_parent_directory(self, *, path, flags):
        self.opens += 1
        if self.opens == 2:
            self.root = self.replacement
        return super().open_parent_directory(path=path, flags=flags)


def test_root_replacement_between_fsync_and_rename_is_typed_and_not_renamed(
    tmp_path,
) -> None:
    original = tmp_path / "original"
    replacement = tmp_path / "replacement"
    original.mkdir(mode=0o700)
    replacement.mkdir(mode=0o700)
    driver = _ReplacementDriver(original, replacement)

    outcome = _persist(driver)

    assert outcome["result"]["failure_code"] == (
        "state_root_replaced_before_atomic_replace"
    )
    assert outcome["result"]["file_fsynced"] is True
    assert outcome["result"]["parent_identity_rechecked"] is False
    assert outcome["result"]["atomic_replace"] is False
    assert (original / store.MANIFEST_TEMP_BASENAME).exists()
    assert list(replacement.iterdir()) == []


class _TempSwapDriver(_PosixFixtureDriver):
    def fsync_file(self, *, fd):
        super().fsync_file(fd=fd)
        temp = self.root / store.MANIFEST_TEMP_BASENAME
        temp.unlink()
        temp.write_text('{"attacker":"replacement"}', encoding="utf-8")
        os.chmod(temp, 0o600)


def test_temp_basename_swap_after_fsync_is_rejected_before_atomic_replace(
    tmp_path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _TempSwapDriver(root)

    outcome = _persist(driver)

    assert outcome["status"] == store.STATUS_RECOVERY_REQUIRED
    assert outcome["result"]["failure_code"] == "manifest_temp_identity_changed"
    assert outcome["result"]["atomic_replace"] is False
    assert (root / store.MANIFEST_BASENAME).exists()
    assert (root / store.MANIFEST_TEMP_BASENAME).exists()


class _LateExactTempSwapDriver(_PosixFixtureDriver):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.replacement_inode = None

    def atomic_replace(self, **kwargs):
        temp = self.root / store.MANIFEST_TEMP_BASENAME
        exact_candidate_bytes = temp.read_bytes()
        temp.unlink()
        temp.write_bytes(exact_candidate_bytes)
        os.chmod(temp, 0o600)
        self.replacement_inode = temp.stat().st_ino
        return super().atomic_replace(**kwargs)


def test_exact_byte_temp_swap_after_identity_check_requires_recovery(
    tmp_path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _LateExactTempSwapDriver(root)

    outcome = _persist(driver)

    candidate_identity = outcome["result"]["candidate_temp_identity"]
    assert candidate_identity["inode"] != driver.replacement_inode
    assert outcome["postcheck"]["manifest_match"] is True
    assert outcome["postcheck"]["manifest_identity_match"] is False
    assert outcome["postcheck"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["postcheck"]["failure_code"] == (
        "manifest_candidate_identity_mismatch"
    )
    assert outcome["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert outcome["rollback"]["operator_action_required"] is True
    assert outcome["status"] == store.STATUS_RECOVERY_REQUIRED


class _OrderDriver(_PosixFixtureDriver):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.events: list[str] = []

    def create_temp_file(self, **kwargs):
        self.events.append("create_temp")
        return super().create_temp_file(**kwargs)

    def write_bytes(self, **kwargs):
        self.events.append("write_full")
        return super().write_bytes(**kwargs)

    def fsync_file(self, **kwargs):
        self.events.append("file_fsync")
        return super().fsync_file(**kwargs)

    def atomic_replace(self, **kwargs):
        self.events.append("atomic_replace")
        return super().atomic_replace(**kwargs)

    def fsync_parent_dir(self, **kwargs):
        self.events.append("directory_fsync")
        return super().fsync_parent_dir(**kwargs)

    def read_file_observation(self, **kwargs):
        observed = super().read_file_observation(**kwargs)
        if kwargs["basename"] == store.MANIFEST_BASENAME and observed is not None:
            self.events.append("independent_readback")
        return observed


def test_success_order_places_independent_readback_after_directory_fsync(
    tmp_path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    driver = _OrderDriver(root)

    outcome = _persist(driver)

    assert outcome["status"] == store.STATUS_UNVERIFIED
    assert driver.events == [
        "independent_readback",
        "create_temp",
        "write_full",
        "file_fsync",
        "independent_readback",
        "atomic_replace",
        "directory_fsync",
        "independent_readback",
    ]
