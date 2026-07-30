"""Real POSIX child-process proofs for the recovery-only dual lock."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_disposable_profile as profile  # noqa: E402
import agent_governance_s2_5_recovery_lock as recovery_lock  # noqa: E402


HEAD = "a" * 40


def _mode(observed: os.stat_result) -> str:
    return f"{stat.S_IMODE(observed.st_mode):04o}"


class _PosixRecoveryLockDriver:
    """Map only the fixed logical lock root to a real disposable local root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._open: set[int] = set()

    def _track(self, fd: int) -> int:
        self._open.add(fd)
        return fd

    def _require(self, fd: int) -> int:
        if fd not in self._open:
            raise RuntimeError("foreign_fd")
        return fd

    def open_parent_directory(self, *, path, flags):
        assert path == profile.DISPOSABLE_LOCK_ROOT
        assert flags == recovery_lock.LOCK_PARENT_OPEN_FLAGS
        fd = self._track(
            os.open(
                self.root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
        )
        observed = os.fstat(fd)
        return {
            "fd": fd,
            "device": observed.st_dev,
            "inode": observed.st_ino,
            "mode": _mode(observed),
            "uid": profile.PROFILE_UID,
            "gid": profile.PROFILE_GID,
            "nlink": observed.st_nlink,
            "is_directory": stat.S_ISDIR(observed.st_mode),
            "is_symlink": False,
        }

    def openat_lock_file(self, *, parent_fd, basename, flags, mode):
        assert basename in recovery_lock.LOCK_BASENAMES
        assert flags == recovery_lock.LOCK_FILE_OPEN_FLAGS
        existed = basename in os.listdir(self._require(parent_fd))
        fd = self._track(
            os.open(
                basename,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                mode,
                dir_fd=parent_fd,
            )
        )
        return {"fd": fd, "created": not existed}

    def fstat_lock_file(self, *, fd):
        observed = os.fstat(self._require(fd))
        return {
            "device": observed.st_dev,
            "inode": observed.st_ino,
            "mode": _mode(observed),
            "uid": profile.PROFILE_UID,
            "gid": profile.PROFILE_GID,
            "nlink": observed.st_nlink,
            "is_regular_file": stat.S_ISREG(observed.st_mode),
        }

    def openat_existing_lock_file(self, *, parent_fd, basename, flags):
        assert basename in recovery_lock.LOCK_BASENAMES
        assert flags == ("O_NOFOLLOW", "O_CLOEXEC")
        fd = self._track(os.open(
            basename,
            os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=self._require(parent_fd),
        ))
        return {"fd": fd}

    def flock_exclusive_nonblocking(self, *, fd):
        try:
            fcntl.flock(
                self._require(fd),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            return False
        return True

    def lock_is_held(self, *, fd):
        fcntl.flock(self._require(fd), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True

    def close(self, *, fd):
        os.close(self._require(fd))
        self._open.remove(fd)


def _child(mode: str, root: Path) -> int:
    driver = _PosixRecoveryLockDriver(root)
    def crash_while_held():
        os.write(
            1,
            (
                json.dumps({
                    "status": recovery_lock.STATUS_ACQUIRED,
                    "runtime_observed": False,
                })
                + "\n"
            ).encode("utf-8"),
        )
        os._exit(17)

    outcome = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
        while_held=(
            crash_while_held
            if mode == "--child-crash" else None
        ),
    )
    os.write(
        1,
        (
            json.dumps({
                "status": outcome["status"],
                "runtime_observed": outcome["result"]["runtime_observed"],
            })
            + "\n"
        ).encode("utf-8"),
    )
    return 0


def _run_child(mode: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), mode, str(root)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_independent_child_observes_real_kernel_contention_without_unlink(
    tmp_path,
) -> None:
    lock_root = tmp_path / "locks"
    lock_root.mkdir(mode=0o700)
    driver = _PosixRecoveryLockDriver(lock_root)
    observed = {}
    def contend_while_parent_holds():
        observed["child"] = _run_child("--child-try", lock_root)

    parent = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
        while_held=contend_while_parent_holds,
    )
    assert parent["status"] == recovery_lock.STATUS_ACQUIRED
    child = observed["child"]
    assert child.returncode == 0
    child_result = json.loads(child.stdout)
    assert child_result == {
        "status": recovery_lock.STATUS_CONTENDED,
        "runtime_observed": False,
    }
    assert sorted(path.name for path in lock_root.iterdir()) == sorted(
        recovery_lock.LOCK_BASENAMES
    )
    reacquired = _run_child("--child-try", lock_root)
    assert json.loads(reacquired.stdout)["status"] == recovery_lock.STATUS_ACQUIRED


def test_child_process_crash_releases_kernel_fds_and_preserves_lock_files(
    tmp_path,
) -> None:
    lock_root = tmp_path / "locks"
    lock_root.mkdir(mode=0o700)

    crashed = _run_child("--child-crash", lock_root)

    assert crashed.returncode == 17
    assert json.loads(crashed.stdout)["status"] == recovery_lock.STATUS_ACQUIRED
    before = {
        path.name: path.stat().st_ino
        for path in lock_root.iterdir()
    }
    driver = _PosixRecoveryLockDriver(lock_root)
    after_crash = recovery_lock._exercise_recovery_dual_lock_simulation(
        driver=driver,
        source_head=HEAD,
    )
    assert after_crash["status"] == recovery_lock.STATUS_ACQUIRED
    after = {
        path.name: path.stat().st_ino
        for path in lock_root.iterdir()
    }
    assert after == before
    assert sorted(after) == sorted(recovery_lock.LOCK_BASENAMES)


def test_replaced_lock_basenames_admit_session_b_but_invalidate_session_a(
    tmp_path,
) -> None:
    lock_root = tmp_path / "locks"
    lock_root.mkdir(mode=0o700)
    driver_a = _PosixRecoveryLockDriver(lock_root)
    outcome_a, lease_a = recovery_lock._acquire_recovery_dual_lock(
        driver=driver_a,
        source_head=HEAD,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    assert outcome_a["status"] == recovery_lock.STATUS_ACQUIRED
    assert lease_a is not None
    lease_a["transaction_active"] = True

    for basename in recovery_lock.LOCK_BASENAMES:
        (lock_root / basename).rename(lock_root / f"{basename}.replaced")
        replacement_fd = os.open(
            lock_root / basename,
            os.O_RDWR | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(replacement_fd)

    driver_b = _PosixRecoveryLockDriver(lock_root)
    outcome_b, lease_b = recovery_lock._acquire_recovery_dual_lock(
        driver=driver_b,
        source_head=HEAD,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    assert outcome_b["status"] == recovery_lock.STATUS_ACQUIRED
    assert lease_b is not None
    effect_performed = False
    try:
        with pytest.raises(
            recovery_lock.RecoveryDualLockError,
            match="lock_path_identity_changed",
        ):
            recovery_lock._verify_lease(
                lease_a,
                driver=driver_a,
                source_head=HEAD,
                require_transaction=True,
            )
            effect_performed = True
        assert effect_performed is False
    finally:
        lease_a["transaction_active"] = False
        assert recovery_lock._release_lease(lease_b)["status"] == "RELEASED"
        assert recovery_lock._release_lease(lease_a)["status"] == "RELEASED"


if __name__ == "__main__":
    raise SystemExit(_child(sys.argv[1], Path(sys.argv[2])))
