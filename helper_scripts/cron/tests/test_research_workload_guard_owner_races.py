import json
import os
import subprocess
import time
from pathlib import Path

from helper_scripts.cron.tests.test_research_workload_guard import (
    GUARD,
    _run,
    _with_fake_flock,
)


def _with_reclaim_date_barrier(
    tmp_path: Path,
    env: dict[str, str],
    barrier: Path,
    release: Path,
) -> dict[str, str]:
    date = tmp_path / "bin/date"
    date.write_text(
        """#!/usr/bin/env bash
if [[ "${RESEARCH_GUARD_TEST_RECLAIM_BARRIER:-0}" == "1" ]]; then
  : > "$RESEARCH_GUARD_TEST_BARRIER_PATH"
  while [[ ! -e "$RESEARCH_GUARD_TEST_RELEASE_PATH" ]]; do sleep 0.01; done
fi
exec /bin/date "$@"
""",
        encoding="utf-8",
    )
    date.chmod(0o755)
    return {
        **env,
        "RESEARCH_GUARD_TEST_BARRIER_PATH": str(barrier),
        "RESEARCH_GUARD_TEST_RELEASE_PATH": str(release),
    }


def _write_stale_none_owner(owner: Path, token: str, heartbeat_file: Path) -> None:
    owner.write_text(
        json.dumps(
            {
                "schema_version": "research_job_owner_v1",
                "lane": "alpha",
                "source_head": "old-head",
                "pid": 99999999,
                "proc_start_ticks": 1,
                "token": token,
                "scope_unit": "none",
                "control_group": "none",
                "acquired_epoch": 0,
                "heartbeat_epoch": 0,
                "heartbeat_file": str(heartbeat_file),
                "progress_seq": 0,
                "stage": "ACQUIRED",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_reclaim_wins_owner_mutex_blocks_delayed_same_token_bind(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    heartbeat = tmp_path / "heartbeat"
    barrier = tmp_path / "reclaim-snapshotted"
    release = tmp_path / "release-reclaim"
    token = "6" * 32
    unit = f"openclaw-research-track-alpha-{token}.scope"
    control_group = f"/app.slice/{unit}"
    _write_stale_none_owner(owner, token, heartbeat)
    env = _with_reclaim_date_barrier(
        tmp_path,
        _with_fake_flock(
            tmp_path,
            {
                **os.environ,
                "OPENCLAW_DATA_DIR": str(tmp_path / "data"),
                "OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC": "0",
            },
        ),
        barrier,
        release,
    )
    reclaim_env = {**env, "RESEARCH_GUARD_TEST_RECLAIM_BARRIER": "1"}
    reclaimer = subprocess.Popen(
        [
            "bash",
            "-c",
            f"set -euo pipefail; source {GUARD!s}; "
            f"RESEARCH_GUARD_OWNER_PATH={owner!s}; "
            "_research_guard_reclaim_stale_owner alpha",
        ],
        env=reclaim_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    binder: subprocess.Popen[str] | None = None
    binder_was_serialized = False
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not barrier.exists():
            time.sleep(0.01)
        assert barrier.exists()
        binder = subprocess.Popen(
            [
                "bash",
                "-c",
                f"set -euo pipefail; source {GUARD!s}; set +e; "
                f"_research_guard_bind_owner_control_group {owner!s} {token} "
                f"{unit} {control_group} {heartbeat!s}; rc=$?; set -e; "
                '[[ "$rc" -eq 75 ]]',
            ],
            env={**env, "RESEARCH_GUARD_TEST_RECLAIM_BARRIER": "0"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.2)
        binder_was_serialized = binder.poll() is None
    finally:
        release.touch()
        stdout, stderr = reclaimer.communicate(timeout=8)
        if binder is not None:
            binder_stdout, binder_stderr = binder.communicate(timeout=8)

    assert binder is not None
    assert binder_was_serialized
    assert binder.returncode == 0, (binder_stdout, binder_stderr)
    assert reclaimer.returncode == 0, (stdout, stderr)
    assert not owner.exists()


def test_stale_reclaim_full_snapshot_cas_rejects_same_token_generation_drift(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    heartbeat = tmp_path / "heartbeat"
    barrier = tmp_path / "reclaim-snapshotted"
    release = tmp_path / "release-reclaim"
    token = "7" * 32
    _write_stale_none_owner(owner, token, heartbeat)
    env = _with_reclaim_date_barrier(
        tmp_path,
        _with_fake_flock(
            tmp_path,
            {
                **os.environ,
                "OPENCLAW_DATA_DIR": str(tmp_path / "data"),
                "OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC": "0",
                "RESEARCH_GUARD_TEST_RECLAIM_BARRIER": "1",
            },
        ),
        barrier,
        release,
    )
    reclaimer = subprocess.Popen(
        [
            "bash",
            "-c",
            f"set -euo pipefail; source {GUARD!s}; "
            f"RESEARCH_GUARD_OWNER_PATH={owner!s}; "
            "_research_guard_reclaim_stale_owner alpha",
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not barrier.exists():
            time.sleep(0.01)
        assert barrier.exists()
        payload = json.loads(owner.read_text())
        payload["heartbeat_epoch"] = 1
        payload["progress_seq"] = 1
        payload["stage"] = "SAME_TOKEN_GENERATION_DRIFT"
        replacement = tmp_path / "owner-replacement.json"
        replacement.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(replacement, owner)
    finally:
        release.touch()
        stdout, stderr = reclaimer.communicate(timeout=8)

    assert reclaimer.returncode == 75, (stdout, stderr)
    assert owner.exists()
    preserved = json.loads(owner.read_text())
    assert preserved["token"] == token
    assert preserved["stage"] == "SAME_TOKEN_GENERATION_DRIFT"


def test_bind_wins_before_reclaim_preserves_bound_owner_and_blocks_successor(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    heartbeat = tmp_path / "heartbeat"
    token = "8" * 32
    unit = f"openclaw-research-track-alpha-{token}.scope"
    control_group = f"/app.slice/{unit}"
    _write_stale_none_owner(owner, token, heartbeat)
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(tmp_path / "data"),
            "OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC": "0",
        },
    )
    completed = _run(
        f"""
_research_guard_bind_owner_control_group \
  {owner!s} {token} {unit} {control_group} {heartbeat!s}
_research_guard_wait_cgroup_empty() {{ return 75; }}
RESEARCH_GUARD_OWNER_PATH={owner!s}
set +e
_research_guard_reclaim_stale_owner alpha
reclaim_rc=$?
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head successor-head --heartbeat-file {tmp_path / 'successor-heartbeat'}
acquire_rc=$?
set -e
[[ "$reclaim_rc" -eq 75 && "$acquire_rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(owner.read_text())
    assert payload["token"] == token
    assert payload["scope_unit"] == unit
    assert payload["control_group"] == control_group
    assert payload["stage"] == "SCOPE_BOUND"
