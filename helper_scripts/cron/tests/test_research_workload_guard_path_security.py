import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
GUARD = REPO_ROOT / "helper_scripts/cron/lib/research_workload_guard.sh"
GUARD_FS = REPO_ROOT / "helper_scripts/cron/lib/research_workload_guard_fs.py"
_FS_SPEC = importlib.util.spec_from_file_location("research_workload_guard_fs", GUARD_FS)
assert _FS_SPEC is not None and _FS_SPEC.loader is not None
_FS = importlib.util.module_from_spec(_FS_SPEC)
_FS_SPEC.loader.exec_module(_FS)


def _with_real_fcntl_flock(tmp_path: Path, env: dict[str, str]) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    flock = fake_bin / "flock"
    flock.write_text(
        """#!/usr/bin/env python3
import fcntl
import sys

args = sys.argv[1:]
fd = int(args[-1])
if "-u" in args:
    operation = fcntl.LOCK_UN
else:
    operation = fcntl.LOCK_EX
    if "-n" in args:
        operation |= fcntl.LOCK_NB
try:
    fcntl.flock(fd, operation)
except BlockingIOError:
    raise SystemExit(1)
""",
        encoding="utf-8",
    )
    flock.chmod(0o755)
    return {**env, "PATH": f"{fake_bin}:{env['PATH']}"}


def _run(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"set -euo pipefail\nsource {GUARD!s}\n{script}"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_private_path_hardening_uses_exclusive_nofollow_files() -> None:
    guard_src = GUARD.read_text(encoding="utf-8")
    fs_src = GUARD_FS.read_text(encoding="utf-8")
    assert 'getattr(os, "O_NOFOLLOW", 0)' in fs_src
    assert "os.O_EXCL" in fs_src
    assert "os.fchmod(fd, 0o600)" in fs_src
    assert "src_dir_fd=parent_fd" in fs_src
    assert "dst_dir_fd=parent_fd" in fs_src
    assert "os.path.realpath(raw)" not in fs_src
    assert "tempfile.mkstemp" not in guard_src
    assert 'tmp = f"{path}.tmp.{os.getpid()}"' not in guard_src
    assert 'tmp = f"{out}.tmp.{os.getpid()}"' not in guard_src


def test_missing_component_symlink_insertion_loses_mkdirat_race_fail_closed(
    tmp_path: Path,
) -> None:
    redirected_target = tmp_path / "service-owned-target"
    redirected_target.mkdir()
    lexical_parent = tmp_path / "inserted-after-missing"
    attempted = lexical_parent / "private-leaf"
    inserted = False

    def insert_symlink(parent_fd: int, component: str) -> None:
        nonlocal inserted
        if not inserted and component == lexical_parent.name:
            os.symlink(redirected_target, component, dir_fd=parent_fd)
            inserted = True

    with pytest.raises(OSError):
        _FS.prepare_private_dir(
            str(attempted),
            before_missing_create=insert_symlink,
        )

    assert inserted
    assert lexical_parent.is_symlink()
    assert not list(redirected_target.iterdir())


@pytest.mark.parametrize(
    ("wrapper_name", "log_name"),
    [
        ("alpha_discovery_throughput_cron.sh", "alpha_discovery_throughput_cron.log"),
        ("cost_gate_learning_lane_cron.sh", "cost_gate_learning_lane_cron.log"),
        ("polymarket_leadlag_ic_cron.sh", "polymarket_leadlag_ic_cron.log"),
    ],
)
def test_wrapper_rejects_untrusted_log_parent_before_any_log_write(
    tmp_path: Path, wrapper_name: str, log_name: str
) -> None:
    data_dir = tmp_path / "data"
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True)
    log_dir.chmod(0o777)
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel\n", encoding="utf-8")
    (log_dir / log_name).symlink_to(victim)
    wrapper = REPO_ROOT / "helper_scripts/cron" / wrapper_name
    completed = subprocess.run(
        ["bash", str(wrapper)],
        env={
            **os.environ,
            "OPENCLAW_BASE_DIR": str(REPO_ROOT),
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_DIR": str(
                data_dir / "demo_order_to_fill_gap"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert victim.read_text(encoding="utf-8") == "sentinel\n"
    assert (log_dir / log_name).is_symlink()


def test_secure_normal_directory_and_guard_files_are_mode_0600(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    heartbeat = tmp_path / "alpha.heartbeat"
    output = tmp_path / "alpha.json"
    env = _with_real_fcntl_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {heartbeat!s}
trap research_guard_release EXIT INT TERM
printf '{{"ok":true}}\n' > {output!s}
research_guard_complete --completion-path {output!s}
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state_dir = data_dir / "research_workload_guard/alpha"
    assert stat.S_IMODE(state_dir.stat().st_mode) & 0o022 == 0
    paths = [
        Path(f"{lock_dir}.flock"),
        Path(f"{lock_dir}.owner.json.mutation.flock"),
        heartbeat,
        *state_dir.glob("*.state.json"),
        *state_dir.glob("*.completion.json"),
    ]
    assert len(paths) == 5
    for path in paths:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("suffix", [".flock", ".owner.json.mutation.flock"])
def test_preseeded_lock_symlink_fails_closed_without_touching_victim(
    tmp_path: Path, suffix: str
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel\n", encoding="utf-8")
    Path(f"{lock_dir}{suffix}").symlink_to(victim)
    env = _with_real_fcntl_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    completed = _run(
        f"""
set +e
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert victim.read_text(encoding="utf-8") == "sentinel\n"
    assert Path(f"{lock_dir}{suffix}").is_symlink()
    assert not Path(f"{lock_dir}.owner.json").exists()


def test_user_owned_symlink_parent_is_rejected_before_file_creation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    redirect = tmp_path / "redirect"
    redirect.symlink_to(target, target_is_directory=True)
    env = _with_real_fcntl_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(tmp_path / "data")},
    )
    completed = _run(
        f"""
set +e
research_guard_acquire --lane alpha --lock-dir {redirect / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not list(target.iterdir())


def test_group_or_world_writable_private_parent_fails_closed(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    unsafe.chmod(0o777)
    env = _with_real_fcntl_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(tmp_path / "data")},
    )
    completed = _run(
        f"""
set +e
research_guard_acquire --lane alpha --lock-dir {unsafe / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not list(unsafe.iterdir())


def test_non_service_owned_lock_parent_fails_closed(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("requires a non-root service identity")
    env = _with_real_fcntl_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(tmp_path / "data")},
    )
    completed = _run(
        f"""
set +e
research_guard_acquire --lane alpha \
  --lock-dir /research-guard-wrong-owner-{os.getpid()}.lock.d \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
