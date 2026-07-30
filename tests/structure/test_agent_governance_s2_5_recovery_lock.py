"""Recovery-only S2.4 -> S2.5 dual-lock contract tests."""

from __future__ import annotations

import sys
from inspect import signature
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_disposable_profile as profile  # noqa: E402
import agent_governance_s2_5_recovery_lock as recovery_lock  # noqa: E402
import agent_governance_s2_5_recovery_store as recovery_store  # noqa: E402


HEAD = "a" * 40


class _RecordingLockDriver:
    """Minimal injected driver; it performs no real host operation."""

    def __init__(
        self,
        *,
        contended_basename: str | None = None,
        close_failure_fd: int | None = None,
    ) -> None:
        self.calls: list[tuple[str, object]] = []
        self._next_fd = 10
        self._basename_by_fd: dict[int, str] = {}
        self._inode_by_basename: dict[str, int] = {}
        self._held: set[int] = set()
        self.contended_basename = contended_basename
        self.close_failure_fd = close_failure_fd
        self._root = {
            "device": 7,
            "inode": 11,
            "mode": "0700",
            "uid": profile.PROFILE_UID,
            "gid": profile.PROFILE_GID,
            "nlink": 2,
            "is_directory": True,
            "is_symlink": False,
        }

    def _fd(self) -> int:
        value = self._next_fd
        self._next_fd += 1
        return value

    def open_parent_directory(self, *, path, flags):
        self.calls.append(("open_parent_directory", path))
        return {**self._root, "fd": self._fd()}

    def openat_lock_file(self, *, parent_fd, basename, flags, mode):
        self.calls.append(("openat_lock_file", basename))
        fd = self._fd()
        self._basename_by_fd[fd] = basename
        self._inode_by_basename.setdefault(basename, fd + 100)
        return {"fd": fd, "created": False}

    def fstat_lock_file(self, *, fd):
        basename = self._basename_by_fd[fd]
        return {
            "device": self._root["device"],
            "inode": self._inode_by_basename[basename],
            "mode": "0600",
            "uid": profile.PROFILE_UID,
            "gid": profile.PROFILE_GID,
            "nlink": 1,
            "is_regular_file": True,
        }

    def openat_existing_lock_file(self, *, parent_fd, basename, flags):
        self.calls.append(("openat_existing_lock_file", basename))
        assert flags == recovery_lock.LOCK_EXISTING_FILE_OPEN_FLAGS
        fd = self._fd()
        self._basename_by_fd[fd] = basename
        return {"fd": fd}

    def flock_exclusive_nonblocking(self, *, fd):
        self.calls.append(("flock_exclusive_nonblocking", fd))
        acquired = self._basename_by_fd[fd] != self.contended_basename
        if acquired:
            self._held.add(fd)
        return acquired

    def lock_is_held(self, *, fd):
        self.calls.append(("lock_is_held", fd))
        return fd in self._held

    def close(self, *, fd):
        self.calls.append(("close", fd))
        if fd == self.close_failure_fd:
            raise OSError("injected close failure")
        self._held.discard(fd)


def test_simulation_acquires_and_releases_fixed_order_without_issuing_authority():
    assert profile.DISPOSABLE_LOCK_ROOT != profile.DISPOSABLE_STATE_ROOT
    assert not profile.DISPOSABLE_LOCK_ROOT.startswith(
        profile.DISPOSABLE_STATE_ROOT + "/"
    )
    assert profile.S2_4_RECOVERY_INSTALL_FENCE_LOCK_PATH == (
        f"{profile.DISPOSABLE_LOCK_ROOT}/"
        f"{profile.S2_4_RECOVERY_INSTALL_FENCE_LOCK_BASENAME}"
    )
    assert profile.S2_5_RECOVERY_LIFECYCLE_LOCK_PATH == (
        f"{profile.DISPOSABLE_LOCK_ROOT}/"
        f"{profile.S2_5_RECOVERY_LIFECYCLE_LOCK_BASENAME}"
    )

    driver = _RecordingLockDriver()
    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
    )

    assert outcome["status"] == recovery_lock.STATUS_ACQUIRED
    assert outcome["simulation_only"] is True
    assert outcome["store_write_authority"] is False
    assert "lock_token" not in outcome
    assert "session" not in outcome
    assert [
        value for name, value in driver.calls if name == "openat_lock_file"
    ] == [
        profile.S2_4_RECOVERY_INSTALL_FENCE_LOCK_BASENAME,
        profile.S2_5_RECOVERY_LIFECYCLE_LOCK_BASENAME,
    ]
    assert outcome["result"]["acquisition_order"] == ["S2.4", "S2.5"]
    assert outcome["result"]["production_effect"] is False
    assert outcome["result"]["production_effect_count"] == 0
    rollback = outcome["rollback"]
    assert rollback["status"] == "RELEASED"
    assert rollback["release_order"] == ["S2.5", "S2.4"]
    assert rollback["session_closed"] is True


class _HostileLockDriver(_RecordingLockDriver):
    def unlink(self):
        raise AssertionError("hostile method must never be called")


class _TransientMainParentCloseFailureDriver(_RecordingLockDriver):
    """Fail the acquired session's parent close once, then permit cleanup."""

    def __init__(self) -> None:
        super().__init__()
        self._main_parent_fd: int | None = None
        self._main_parent_close_failed = False

    def open_parent_directory(self, *, path, flags):
        opened = super().open_parent_directory(path=path, flags=flags)
        if self._main_parent_fd is None:
            self._main_parent_fd = opened["fd"]
        return opened

    def close(self, *, fd):
        if fd == self._main_parent_fd and not self._main_parent_close_failed:
            self.calls.append(("close", fd))
            self._main_parent_close_failed = True
            raise OSError("injected transient main-parent close failure")
        super().close(fd=fd)


def test_hostile_driver_shape_is_rejected_before_any_driver_engagement():
    driver = _HostileLockDriver()

    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
    )

    assert outcome["status"] == recovery_lock.STATUS_REJECTED
    assert outcome["result"]["failure_code"] == "driver_destructive_surface"
    assert outcome["result"]["driver_engaged"] is False
    assert driver.calls == []
    assert outcome["store_write_authority"] is False


def test_every_forbidden_driver_method_is_individually_fail_closed():
    assert set(recovery_lock.FORBIDDEN_LOCK_METHODS) == {
        "chmod",
        "chown",
        "remove",
        "rename",
        "rmdir",
        "truncate",
        "unlink",
        "unlink_lock",
    }
    for method in recovery_lock.FORBIDDEN_LOCK_METHODS:
        driver = _RecordingLockDriver()
        setattr(driver, method, lambda: None)
        outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
            driver=driver,
            source_head=HEAD,
        )
        assert outcome["status"] == recovery_lock.STATUS_REJECTED, method
        assert driver.calls == [], method


def test_second_lock_contention_releases_the_already_acquired_first_lock():
    driver = _RecordingLockDriver(
        contended_basename=profile.S2_5_RECOVERY_LIFECYCLE_LOCK_BASENAME
    )

    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
    )

    assert outcome["status"] == recovery_lock.STATUS_CONTENDED
    assert outcome["result"]["first_lock_released_after_second_failure"] is True
    assert outcome["rollback"]["status"] == "RELEASED_AFTER_PARTIAL_ACQUIRE"
    assert outcome["rollback"]["s2_4_release_attempted"] is True
    assert outcome["rollback"]["s2_4_released"] is True
    assert outcome["store_write_authority"] is False


def test_transient_parent_close_failure_after_dual_acquire_releases_full_chain():
    driver = _TransientMainParentCloseFailureDriver()

    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
    )

    lock_fds = [
        value
        for name, value in driver.calls
        if name == "flock_exclusive_nonblocking"
    ]
    assert len(lock_fds) == 2
    assert outcome["status"] == recovery_lock.STATUS_RECOVERY_REQUIRED
    assert outcome["result"]["status"] == recovery_lock.STATUS_RECOVERY_REQUIRED
    assert outcome["result"]["failure_code"] == "lock_parent_close_failed"
    assert outcome["result"]["s2_4_lock_acquired"] is False
    assert outcome["result"]["s2_5_lock_acquired"] is False
    rollback = outcome["rollback"]
    assert rollback["status"] == "RELEASED"
    assert rollback["s2_5_release_attempted"] is True
    assert rollback["s2_5_released"] is True
    assert rollback["s2_4_release_attempted"] is True
    assert rollback["s2_4_released"] is True
    assert rollback["session_closed"] is True
    assert rollback["failure_code"] is None
    assert recovery_lock.validate_local_artifact(rollback) == []


def test_release_attempts_both_locks_and_invalidates_even_when_s2_5_close_fails():
    driver = _RecordingLockDriver()
    def fail_s2_5_release():
        lock_fds = [
            value
            for name, value in driver.calls
            if name == "flock_exclusive_nonblocking"
        ]
        driver.close_failure_fd = lock_fds[1]

    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
        while_held=fail_s2_5_release,
    )
    rollback = outcome["rollback"]
    lock_fds = [
        value for name, value in driver.calls if name == "flock_exclusive_nonblocking"
    ]

    release_closes = [
        value for name, value in driver.calls if name == "close"
        and value in lock_fds
    ]
    assert release_closes == [lock_fds[1], lock_fds[0]]
    assert rollback["status"] == "RECOVERY_REQUIRED"
    assert rollback["s2_5_release_attempted"] is True
    assert rollback["s2_5_released"] is False
    assert rollback["s2_4_release_attempted"] is True
    assert rollback["s2_4_released"] is True
    assert rollback["session_closed"] is False
    assert recovery_lock.validate_local_artifact(rollback) == []


def test_ordinary_s2_4_verdict_shape_cannot_forge_store_authority():
    forged_ordinary_verdict = {
        "status": "INSTALL_LOCK_ACQUIRED",
        "lock_token": object(),
    }
    assert forged_ordinary_verdict["status"] != recovery_lock.STATUS_ACQUIRED
    assert not hasattr(recovery_lock, "require_recovery_dual_lock_token")
    assert not hasattr(recovery_store.S2_5RecoveryStore, "persist")


def test_simulation_result_has_no_replayable_session_or_driver_reference():
    driver = _RecordingLockDriver()
    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
    )
    assert "session" not in outcome
    assert "lease" not in outcome
    assert "driver" not in outcome
    assert outcome["postcheck"]["session_class"] == "SIMULATION_ONLY"
    assert outcome["postcheck"]["store_write_authority"] is False


def test_public_simulation_surface_has_no_path_order_or_identity_selection():
    assert set(signature(recovery_lock.simulate_recovery_dual_lock).parameters) == {
        "source_head",
    }
    outcome = recovery_lock.simulate_recovery_dual_lock(source_head=HEAD)
    assert outcome["effect_performed"] is False
    assert outcome["store_write_authority"] is False
    source = (
        HELPERS / "agent_governance_s2_5_recovery_lock.py"
    ).read_text(encoding="utf-8")
    assert "import agent_governance_s2_4_lock" not in source
    assert "from agent_governance_s2_4_lock" not in source


def test_pending_rejected_and_contended_paths_all_emit_valid_typed_chains():
    outcomes = [
        recovery_lock._exercise_recovery_dual_lock_simulation(
            driver=None,
            source_head=HEAD,
        ),
        recovery_lock._exercise_recovery_dual_lock_simulation(
            driver=_HostileLockDriver(),
            source_head=HEAD,
        ),
        recovery_lock._exercise_recovery_dual_lock_simulation(
            driver=_RecordingLockDriver(
                contended_basename=(
                    profile.S2_5_RECOVERY_LIFECYCLE_LOCK_BASENAME
                )
            ),
            source_head=HEAD,
        ),
    ]
    assert [outcome["status"] for outcome in outcomes] == [
        recovery_lock.STATUS_PENDING,
        recovery_lock.STATUS_REJECTED,
        recovery_lock.STATUS_CONTENDED,
    ]
    for outcome in outcomes:
        for name in ("intent", "result", "postcheck", "rollback"):
            assert recovery_lock.validate_local_artifact(outcome[name]) == []
            assert outcome[name]["side_effect_class"] == "DISPOSABLE_TEST"
            assert outcome[name]["runtime_observed"] is False
            assert outcome[name]["production_effect"] is False
            assert outcome[name]["production_effect_count"] == 0


def test_cc_e3_b2_002_public_api_cannot_issue_authority_from_a_driver():
    assert not hasattr(recovery_lock, "acquire_recovery_dual_lock")
    assert not hasattr(recovery_store.S2_5RecoveryStore, "persist")
    assert set(signature(recovery_store.persist_fixed_profile).parameters) == {
        "source_head",
        "controller_state",
        "issued_at",
        "expires_at",
    }


def test_cc_e3_b2_003_session_state_is_closure_private():
    for name in (
        "_RecoveryDualLockToken",
        "_TOKEN_SEAL",
        "_LIVE_LOCK_TOKENS",
        "recovery_dual_lock_is_held",
        "require_recovery_dual_lock_token",
    ):
        assert not hasattr(recovery_lock, name), name


def test_cc_e3_b2_004_no_public_release_can_race_the_store_transaction():
    assert not hasattr(recovery_lock, "release_recovery_dual_lock")


def test_cc_e3_b2_004_internal_release_is_denied_during_transaction():
    driver = _RecordingLockDriver()
    outcome, lease = recovery_lock._acquire_recovery_dual_lock(
        driver=driver,
        source_head=HEAD,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    assert outcome["status"] == recovery_lock.STATUS_ACQUIRED
    assert lease is not None
    lease["transaction_active"] = True
    before = list(driver.calls)

    denied = recovery_lock._release_lease(lease)

    assert denied["status"] == "RECOVERY_REQUIRED"
    assert denied["failure_code"] == "fixed_recovery_transaction_active"
    assert denied["session_closed"] is False
    assert driver.calls == before
    assert recovery_lock._verify_lease(
        lease,
        driver=driver,
        source_head=HEAD,
        require_transaction=True,
    )["recovery_lock_chain_digest"] == outcome["postcheck"]["lock_chain_digest"]
    lease["transaction_active"] = False
    assert recovery_lock._release_lease(lease)["status"] == "RELEASED"


def test_fixed_session_final_post_acquire_check_revalidates_both_held_fds():
    driver = _RecordingLockDriver()
    outcome, lease = recovery_lock._acquire_recovery_dual_lock(
        driver=driver,
        source_head=HEAD,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    assert outcome["status"] == recovery_lock.STATUS_ACQUIRED
    assert lease is not None
    held_checks = [
        fd for name, fd in driver.calls if name == "lock_is_held"
    ]
    assert held_checks == [lease["s2_4_fd"], lease["s2_5_fd"]]
    assert recovery_lock._release_lease(lease)["status"] == "RELEASED"
