import hashlib
import json
import os
import signal
import shutil
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
GUARD = REPO_ROOT / "helper_scripts/cron/lib/research_workload_guard.sh"


def _with_fake_flock(
    tmp_path: Path, env: dict[str, str], *, control_group_rc: int = 0
) -> dict[str, str]:
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
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        f"""#!/usr/bin/env bash
args="$*"
case "$args" in
  *"ControlGroup"*)
    unit=""
    for arg in "$@"; do [[ "$arg" == *.scope ]] && unit="$arg"; done
    [[ -n "$unit" ]] || exit 1
    printf '/app.slice/%s\n' "$unit"
    exit {control_group_rc}
    ;;
  *"is-active"*) exit 3 ;;
  *" kill "*) exit 0 ;;
  *"MemoryMax"*) printf 'infinity\\n'; exit 0 ;;
  *"MemorySwapMax"*) printf 'infinity\\n'; exit 0 ;;
  *"TasksMax"*) printf 'infinity\\n'; exit 0 ;;
  *" Slice "*) printf 'app.slice\\n'; exit 0 ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    systemd_run = fake_bin / "systemd-run"
    systemd_run.write_text(
        "#!/usr/bin/env bash\n"
        "while (( $# )); do [[ \"$1\" == \"--\" ]] && { shift; break; }; shift; done\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    grep = fake_bin / "grep"
    grep.write_text(
        "#!/usr/bin/env bash\n"
        "[[ \"$*\" == *\"/proc/self/cgroup\"* ]] && exit 0\n"
        "exec /usr/bin/grep \"$@\"\n",
        encoding="utf-8",
    )
    for path in (systemctl, systemd_run, grep):
        path.chmod(0o755)
    return {**env, "PATH": f"{fake_bin}:{env['PATH']}"}


def _with_fake_systemd(
    tmp_path: Path,
    env: dict[str, str],
    *,
    slice_high: str = "25769803776",
    slice_max: str = "34359738368",
    slice_swap: str = "0",
    scope_max: str = "12884901888",
    scope_swap: str = "0",
    scope_tasks: str = "32",
    scope_slice: str = "openclaw-research.slice",
    track_max: str = "infinity",
    track_swap: str = "infinity",
    track_tasks: str = "infinity",
    track_slice: str = "app.slice",
    control_group_basename: str = "__MATCH_UNIT__",
    cgroup_match: bool = True,
    is_active_rc: int = 3,
    slice_high_rc: int = 0,
    slice_max_rc: int = 0,
    slice_swap_rc: int = 0,
    scope_max_rc: int = 0,
    scope_swap_rc: int = 0,
    scope_tasks_rc: int = 0,
    scope_slice_rc: int = 0,
    track_max_rc: int = 0,
    track_swap_rc: int = 0,
    track_tasks_rc: int = 0,
    track_slice_rc: int = 0,
) -> dict[str, str]:
    result = _with_fake_flock(tmp_path, env)
    fake_bin = tmp_path / "bin"
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        f"""#!/usr/bin/env bash
args="$*"
case "$args" in
  *"ControlGroup"*)
    unit=""
    for arg in "$@"; do [[ "$arg" == *.scope ]] && unit="$arg"; done
    [[ -n "$unit" ]] || exit 1
    basename={control_group_basename!r}
    [[ "$basename" == __MATCH_UNIT__ ]] && basename="$unit"
    printf '/app.slice/%s\n' "$basename"
    exit 0
    ;;
  *"is-active"*) exit {is_active_rc} ;;
  *" kill "*) exit 0 ;;
  *"openclaw-research-track-"*"MemoryMax"*) printf '%s\\n' {track_max!r}; exit {track_max_rc} ;;
  *"openclaw-research-track-"*"MemorySwapMax"*) printf '%s\\n' {track_swap!r}; exit {track_swap_rc} ;;
  *"openclaw-research-track-"*"TasksMax"*) printf '%s\\n' {track_tasks!r}; exit {track_tasks_rc} ;;
  *"openclaw-research-track-"*" Slice "*) printf '%s\\n' {track_slice!r}; exit {track_slice_rc} ;;
  *"openclaw-research.slice"*"MemoryHigh"*) printf '%s\\n' {slice_high!r}; exit {slice_high_rc} ;;
  *"openclaw-research.slice"*"MemoryMax"*) printf '%s\\n' {slice_max!r}; exit {slice_max_rc} ;;
  *"openclaw-research.slice"*"MemorySwapMax"*) printf '%s\\n' {slice_swap!r}; exit {slice_swap_rc} ;;
  *"MemoryMax"*) printf '%s\\n' {scope_max!r}; exit {scope_max_rc} ;;
  *"MemorySwapMax"*) printf '%s\\n' {scope_swap!r}; exit {scope_swap_rc} ;;
  *"TasksMax"*) printf '%s\\n' {scope_tasks!r}; exit {scope_tasks_rc} ;;
  *" Slice "*) printf '%s\\n' {scope_slice!r}; exit {scope_slice_rc} ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    systemd_run = fake_bin / "systemd-run"
    systemd_run.write_text(
        "#!/usr/bin/env bash\n"
        "while (( $# )); do [[ \"$1\" == \"--\" ]] && { shift; break; }; shift; done\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    grep = fake_bin / "grep"
    cgroup_rc = 0 if cgroup_match else 1
    grep.write_text(
        "#!/usr/bin/env bash\n"
        f"[[ \"$*\" == *\"/proc/self/cgroup\"* ]] && exit {cgroup_rc}\n"
        "exec /usr/bin/grep \"$@\"\n",
        encoding="utf-8",
    )
    for path in (systemctl, systemd_run, grep):
        path.chmod(0o755)
    return result


def _with_fake_publish_tools(
    tmp_path: Path, env: dict[str, str], *, fail_cp: bool = False, fail_mv: int = 0
) -> dict[str, str]:
    result = _with_fake_flock(tmp_path, env)
    fake_bin = tmp_path / "bin"
    (fake_bin / "cp").write_text(
        "#!/usr/bin/env bash\n" + ("exit 74\n" if fail_cp else "exec /bin/cp \"$@\"\n"),
        encoding="utf-8",
    )
    (fake_bin / "mv").write_text(
        "#!/usr/bin/env bash\n"
        f"count_file={str(tmp_path / 'mv.count')!r}\n"
        "count=0; [[ -f \"$count_file\" ]] && count=$(cat \"$count_file\")\n"
        "count=$((count + 1)); printf '%s\\n' \"$count\" > \"$count_file\"\n"
        f"[[ \"$count\" == {fail_mv!r} ]] && exit 74\n"
        "exec /bin/mv \"$@\"\n",
        encoding="utf-8",
    )
    for name in ("cp", "mv"):
        (fake_bin / name).chmod(0o755)
    return result


def _run(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"set -euo pipefail\nsource {GUARD!s}\n{script}"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_off_success_records_complete_manifest(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    heartbeat = tmp_path / "alpha.heartbeat"
    output = tmp_path / "alpha.json"
    env = _with_fake_flock(tmp_path, {
        **os.environ,
        "OPENCLAW_DATA_DIR": str(data_dir),
        "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
    })
    completed = _run(
        f"""
research_guard_acquire \\
  --lane alpha \\
  --lock-dir {lock_dir!s} \\
  --source-head test-head \\
  --heartbeat-file {heartbeat!s}
trap research_guard_release EXIT INT TERM
research_guard_run_stage \\
  --lane alpha \\
  --memory-max-bytes 12884901888 \\
  --tasks-max 32 \\
  -- bash -c 'printf "{{\"ok\":true}}\\n" > "$1"' _ {output!s}
research_guard_complete --completion-path {output!s}
""",
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    states = list((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    manifests = list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )
    assert len(states) == 1
    assert len(manifests) == 1
    assert json.loads(states[0].read_text())["status"] == "COMPLETE"
    manifest = json.loads(manifests[0].read_text())
    assert manifest["status"] == "COMPLETE"
    assert manifest["completion_paths"] == [str(output)]
    assert not Path(f"{lock_dir}.owner.json").exists()


def test_nonzero_stage_never_creates_completion_manifest(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output = tmp_path / "partial.json"
    later_marker = tmp_path / "must-not-run-after-incomplete"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \\
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \\
  --tasks-max 32 -- \\
  bash -c 'printf partial > "$1"; exit 23' _ {output!s}
rc=$?
set -e
[[ "$rc" -eq 23 ]]
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- touch {later_marker!s}
later_rc=$?
set -e
[[ "$later_rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    assert json.loads(state.read_text())["status"] == "INCOMPLETE"
    assert not list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )
    assert not later_marker.exists()


def test_sigkill_137_marks_resource_exhaustion_and_refuses_later_stage(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    later_marker = tmp_path / "must-not-run-after-137"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'exit 137'
rc=$?
set -e
[[ "$rc" -eq 137 ]]
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- touch {later_marker!s}
later_rc=$?
set -e
[[ "$later_rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "resource_exhausted_oom_or_sigkill"
    assert payload["rc"] == 137
    assert not later_marker.exists()
    assert not list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )


def test_publisher_before_complete_marks_incomplete_and_is_not_visible(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    candidate = tmp_path / "must-not-publish-before-complete.json"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane cost --lock-dir {tmp_path / 'cost.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
set +e
research_guard_run_stage --lane cost --memory-max-bytes 12884901888 \
  --tasks-max 32 --preserve-completion-manifest-on-failure -- \
  touch {candidate!s}
rc=$?
set -e
[[ "$rc" -eq 64 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/cost").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "publisher_before_complete"
    assert payload["rc"] == 64
    assert not candidate.exists()
    assert not list(
        (data_dir / "research_workload_guard/cost").glob("*.completion.json")
    )


def test_post_completion_publisher_failure_keeps_manifest_but_marks_incomplete(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    output = tmp_path / "review.json"
    candidate = tmp_path / "candidate.json"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane cost --lock-dir {tmp_path / 'cost.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
printf '{{"complete":true}}\n' > {output!s}
research_guard_complete --completion-path {output!s}
set +e
research_guard_run_stage --lane cost --memory-max-bytes 12884901888 \
  --tasks-max 32 --preserve-completion-manifest-on-failure -- \
  bash -c 'cp "$1" "$2"; exit 23' _ {output!s} {candidate!s}
rc=$?
set -e
[[ "$rc" -eq 23 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/cost").glob("*.state.json"))
    manifest = next(
        (data_dir / "research_workload_guard/cost").glob("*.completion.json")
    )
    assert json.loads(state.read_text())["status"] == "INCOMPLETE"
    manifest_payload = json.loads(manifest.read_text())
    assert manifest_payload["completion_paths"] == [str(output)]
    assert manifest_payload["sha256_by_path"][str(output)] == hashlib.sha256(
        candidate.read_bytes()
    ).hexdigest()
    assert candidate.read_bytes() == output.read_bytes()


def test_post_link_candidate_sigkill_has_prior_manifest_and_incomplete_state(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    output = tmp_path / "review.json"
    candidate = tmp_path / "candidate.json"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane cost --lock-dir {tmp_path / 'cost.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
printf '{{"complete":true}}\n' > {output!s}
research_guard_complete --completion-path {output!s}
set +e
research_guard_run_stage --lane cost --memory-max-bytes 12884901888 \
  --tasks-max 32 --preserve-completion-manifest-on-failure -- \
  bash -c 'cp "$1" "$2"; kill -KILL "$$"' _ {output!s} {candidate!s}
rc=$?
set -e
[[ "$rc" -eq 137 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/cost").glob("*.state.json"))
    state_payload = json.loads(state.read_text())
    assert state_payload["status"] == "INCOMPLETE"
    assert state_payload["reason"] == "resource_exhausted_oom_or_sigkill"
    assert state_payload["rc"] == 137
    manifest = next(
        (data_dir / "research_workload_guard/cost").glob("*.completion.json")
    )
    manifest_payload = json.loads(manifest.read_text())
    assert candidate.read_bytes() == output.read_bytes()
    assert manifest_payload["sha256_by_path"][str(output)] == hashlib.sha256(
        candidate.read_bytes()
    ).hexdigest()


def test_completion_heartbeat_failure_removes_manifest_and_marks_incomplete(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    output = tmp_path / "output.json"
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
printf complete > {output!s}
rm -f {str(lock_dir) + '.owner.json'}
set +e
research_guard_complete --completion-path {output!s}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "completion_heartbeat_failed"
    assert not list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )


def test_completion_manifest_writer_failure_cannot_leave_complete_state(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    output = tmp_path / "output.json"
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
printf complete > {output!s}
mkdir "$RESEARCH_GUARD_COMPLETION_PATH"
set +e
research_guard_complete --completion-path {output!s}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "completion_manifest_write_failed"
    assert Path(f"{tmp_path / 'alpha.lock.d'}.owner.json").exists()
    assert not any(
        path.is_file()
        for path in (data_dir / "research_workload_guard/alpha").glob(
            "*.completion.json"
        )
    )


def test_publisher_start_heartbeat_failure_preserves_upstream_manifest_only(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "cost.lock.d"
    output = tmp_path / "review.json"
    candidate = tmp_path / "candidate.json"
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    completed = _run(
        f"""
research_guard_acquire --lane cost --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
printf complete > {output!s}
research_guard_complete --completion-path {output!s}
rm -f {str(lock_dir) + '.owner.json'}
set +e
research_guard_run_stage --lane cost --memory-max-bytes 12884901888 \
  --tasks-max 32 --preserve-completion-manifest-on-failure -- \
  cp {output!s} {candidate!s}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/cost").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "stage_start_heartbeat_failed"
    assert not candidate.exists()
    assert len(
        list((data_dir / "research_workload_guard/cost").glob("*.completion.json"))
    ) == 1


def test_publisher_complete_heartbeat_failure_has_prior_upstream_manifest(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "cost.lock.d"
    output = tmp_path / "review.json"
    candidate = tmp_path / "candidate.json"
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    completed = _run(
        f"""
research_guard_acquire --lane cost --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
printf complete > {output!s}
research_guard_complete --completion-path {output!s}
set +e
research_guard_run_stage --lane cost --memory-max-bytes 12884901888 \
  --tasks-max 32 --preserve-completion-manifest-on-failure -- \
  bash -c 'cp "$1" "$2"; rm -f "$3"' _ {output!s} {candidate!s} \
  {str(lock_dir) + '.owner.json'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next((data_dir / "research_workload_guard/cost").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "stage_complete_heartbeat_failed"
    assert candidate.read_bytes() == output.read_bytes()
    manifest = next(
        (data_dir / "research_workload_guard/cost").glob("*.completion.json")
    )
    manifest_payload = json.loads(manifest.read_text())
    assert manifest_payload["sha256_by_path"][str(output)] == hashlib.sha256(
        candidate.read_bytes()
    ).hexdigest()


def test_publisher_failure_state_writer_error_removes_false_complete_and_keeps_owner(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "cost.lock.d"
    output = tmp_path / "review.json"
    real_python = shutil.which("python3")
    assert real_python is not None
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    fake_python = tmp_path / "bin/python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "[[ \"${2:-}\" == state-write && \"${4:-}\" == INCOMPLETE ]] && exit 75\n"
        f"exec {real_python!r} \"$@\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    completed = _run(
        f"""
research_guard_acquire --lane cost --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
printf complete > {output!s}
research_guard_complete --completion-path {output!s}
set +e
research_guard_run_stage --lane cost --memory-max-bytes 12884901888 \
  --tasks-max 32 --preserve-completion-manifest-on-failure -- \
  bash -c 'exit 23'
rc=$?
set -e
[[ "$rc" -eq 23 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    owner = Path(f"{lock_dir}.owner.json")
    assert owner.exists()
    assert json.loads(owner.read_text())["stage"].startswith("INCOMPLETE:")
    assert not list((data_dir / "research_workload_guard/cost").glob("*.state.json"))
    assert len(
        list((data_dir / "research_workload_guard/cost").glob("*.completion.json"))
    ) == 1


def test_dead_owner_is_reclaimed_only_after_identity_and_heartbeat_proof(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    owner.write_text(
        json.dumps(
            {
                "schema_version": "research_job_owner_v1",
                "lane": "alpha",
                "source_head": "old-head",
                "pid": 99999999,
                "proc_start_ticks": 1,
                "token": "a" * 32,
                "scope_unit": "none",
                "control_group": "none",
                "heartbeat_epoch": 0,
            }
        ),
        encoding="utf-8",
    )
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
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head new-head --heartbeat-file {tmp_path / 'heartbeat'}
research_guard_release
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not owner.exists()


def test_scoped_stale_owner_is_not_reclaimed_without_stored_cgroup_empty_proof(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    token = "c" * 32
    unit = f"openclaw-research-track-alpha-{token}.scope"
    control_group = f"/app.slice/{unit}"
    owner.write_text(
        json.dumps(
            {
                "schema_version": "research_job_owner_v1",
                "lane": "alpha",
                "source_head": "old-head",
                "pid": 99999999,
                "proc_start_ticks": 1,
                "token": token,
                "scope_unit": unit,
                "control_group": control_group,
                "heartbeat_epoch": 0,
            }
        ),
        encoding="utf-8",
    )
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
_research_guard_wait_cgroup_empty() {{ [[ "$1" == {control_group!s} ]] || return 64; return 75; }}
set +e
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head new-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(owner.read_text())["token"] == token


def test_scoped_stale_owner_rejects_unrelated_empty_control_group(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    token = "e" * 32
    unit = f"openclaw-research-track-alpha-{token}.scope"
    owner.write_text(
        json.dumps(
            {
                "schema_version": "research_job_owner_v1",
                "lane": "alpha",
                "source_head": "old-head",
                "pid": 99999999,
                "proc_start_ticks": 1,
                "token": token,
                "scope_unit": unit,
                "control_group": "/app.slice/unrelated-empty.scope",
                "heartbeat_epoch": 0,
            }
        ),
        encoding="utf-8",
    )
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
_research_guard_wait_cgroup_empty() {{ return 0; }}
set +e
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head new-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(owner.read_text())["token"] == token


def test_stale_owner_reclaim_rejects_cross_lane_metadata(tmp_path: Path) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    token = "f" * 32
    unit = f"openclaw-research-track-cost-{token}.scope"
    owner.write_text(
        json.dumps(
            {
                "schema_version": "research_job_owner_v1",
                "lane": "cost",
                "source_head": "old-head",
                "pid": 99999999,
                "proc_start_ticks": 1,
                "token": token,
                "scope_unit": unit,
                "control_group": f"/app.slice/{unit}",
                "heartbeat_epoch": 0,
            }
        ),
        encoding="utf-8",
    )
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
_research_guard_wait_cgroup_empty() {{ return 0; }}
set +e
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head new-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(owner.read_text())["lane"] == "cost"


def test_scoped_stale_owner_reclaims_after_stored_cgroup_empty_proof(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    token = "d" * 32
    unit = f"openclaw-research-track-alpha-{token}.scope"
    control_group = f"/app.slice/{unit}"
    owner.write_text(
        json.dumps(
            {
                "schema_version": "research_job_owner_v1",
                "lane": "alpha",
                "source_head": "old-head",
                "pid": 99999999,
                "proc_start_ticks": 1,
                "token": token,
                "scope_unit": unit,
                "control_group": control_group,
                "heartbeat_epoch": 0,
            }
        ),
        encoding="utf-8",
    )
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
_research_guard_wait_cgroup_empty() {{ [[ "$1" == {control_group!s} ]]; }}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head new-head --heartbeat-file {tmp_path / 'heartbeat'}
research_guard_release
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not owner.exists()


def test_live_owner_metadata_is_never_reclaimed_by_old_heartbeat(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
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
if [[ -r /proc/$$/stat ]]; then
  current_start="$(awk '{{print $22}}' /proc/$$/stat)"
else
  current_start="$(ps -o lstart= -p "$$" | cksum | awk '{{print $1}}')"
fi
python3 -c 'import json,sys; json.dump({{"schema_version":"research_job_owner_v1","lane":"alpha","source_head":"old-head","pid":int(sys.argv[2]),"proc_start_ticks":int(sys.argv[3]),"token":"b"*32,"scope_unit":"none","control_group":"none","heartbeat_epoch":0}}, open(sys.argv[1], "w"))' \
  {owner!s} "$$" "$current_start"
set +e
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head new-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(owner.read_text())["token"] == "b" * 32


def test_owner_writer_failure_cannot_report_successful_acquire(tmp_path: Path) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    data_dir = tmp_path / "data"
    real_python = shutil.which("python3")
    assert real_python is not None
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    fake_python = tmp_path / "bin/python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "[[ \"${2:-}\" == owner-create && \"${3:-}\" == *.owner.json ]] && exit 75\n"
        f"exec {real_python!r} \"$@\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
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
    assert not Path(f"{lock_dir}.owner.json").exists()
    assert not list((data_dir / "research_workload_guard/alpha").glob("*.state.json"))


def test_owner_token_mismatch_heartbeat_blocks_payload_and_marks_incomplete(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    data_dir = tmp_path / "data"
    marker = tmp_path / "must-not-run"
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["token"]="replacement"; open(p,"w").write(json.dumps(d))' {owner!s}
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- touch {marker!s}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    assert json.loads(owner.read_text())["token"] == "replacement"
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "stage_start_heartbeat_failed"


def test_enabled_scope_contract_reads_back_memory_swap_and_scrubs_environment() -> None:
    src = GUARD.read_text(encoding="utf-8")
    assert 'MemoryHigh --value' in src
    assert 'MemoryMax --value' in src
    assert 'MemorySwapMax --value' in src
    assert 'scope_swap="0"' in src
    assert '--property="MemorySwapMax=${scope_swap}"' in src
    assert 'TasksMax --value' in src
    assert '_research_guard_scrub_environment' in src
    assert 'done < <(compgen -e)' in src
    assert 'env -i' not in src


def test_legacy_lock_directory_fails_closed_without_age_eviction(
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    lock_dir.mkdir()
    os.utime(lock_dir, (1, 1))
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(tmp_path / "data")},
    )
    completed = _run(
        f"""
set +e
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \\
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert lock_dir.is_dir()


def test_release_is_aba_safe_and_idempotent(tmp_path: Path) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(tmp_path / "data")},
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \\
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["token"]="replacement"; open(p,"w").write(json.dumps(d))' {owner!s}
research_guard_release
research_guard_release
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(owner.read_text())["token"] == "replacement"


def test_release_preserves_owner_when_state_is_unreadable(tmp_path: Path) -> None:
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(tmp_path / "data")},
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
printf '{{' > "$RESEARCH_GUARD_STATE_PATH"
research_guard_release
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert owner.exists()


def test_enabled_containment_fails_closed_without_verified_systemd(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    marker = tmp_path / "must-not-run"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "1",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/definitely/missing/systemd-user-bus",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \\
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \\
  --tasks-max 32 -- \\
  bash -c 'touch "$1"' _ {marker!s}
rc=$?
set -e
[[ "$rc" -ne 0 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()


def test_default_off_tracking_scope_is_unbounded_and_fork_closed() -> None:
    src = GUARD.read_text(encoding="utf-8")
    assert 'openclaw-research-track-${lane}-${RESEARCH_GUARD_TOKEN}.scope' in src
    assert 'scope_slice="app.slice"' in src
    assert 'scope_memory="infinity"' in src
    assert 'scope_swap="infinity"' in src
    assert 'scope_tasks="infinity"' in src
    assert 'grep -Fxq "0::${control_group}" /proc/self/cgroup' in src
    assert '            "$@" &' not in src


def test_async_scope_launch_defers_signal_until_child_pid_is_bound() -> None:
    src = GUARD.read_text(encoding="utf-8")
    pending = src.index('RESEARCH_GUARD_LAUNCH_STATE="pending"')
    deferred_term = src.index("trap '_research_guard_defer_signal TERM 143' TERM", pending)
    launched = src.index('        ) &', deferred_term)
    pid_bound = src.index('RESEARCH_GUARD_CHILD_PID=$!', launched)
    committed = src.index('RESEARCH_GUARD_LAUNCH_STATE="bound"', pid_bound)
    restored_term = src.index("trap 'research_guard_abort_signal TERM 143' TERM", committed)
    assert pending < deferred_term < launched < pid_bound < committed < restored_term
    assert "is-active" not in src


@pytest.mark.parametrize(
    ("control_group_rc", "owner_retained"),
    [(0, False), (1, True)],
    ids=["cgroup-bound", "cgroup-query-failed"],
)
def test_real_term_in_async_launch_gap_is_deferred_until_pid_binding(
    tmp_path: Path, control_group_rc: int, owner_retained: bool
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    debug_marker = tmp_path / "debug-signal-fired"
    payload_marker = tmp_path / "payload-must-not-start"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
            "OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC": "0",
        },
        control_group_rc=control_group_rc,
    )
    fake_systemd_run = tmp_path / "bin/systemd-run"
    fake_systemd_run.write_text(
        "#!/usr/bin/env bash\n"
        "sleep 5\n"
        "while (( $# )); do [[ \"$1\" == \"--\" ]] && { shift; break; }; shift; done\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    fake_systemd_run.chmod(0o755)
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
_research_guard_wait_cgroup_empty() {{ return 0; }}
_signal_exact_launch_gap() {{
  local background_pid=""
  set +u
  background_pid="$!"
  set -u
  if [[ "${{BASH_SUBSHELL:-0}}" == "0" && \
        "${{RESEARCH_GUARD_LAUNCH_STATE:-idle}}" == "pending" && \
        -n "$background_pid" && ! -e {debug_marker!s} ]]; then
    : > {debug_marker!s}
    kill -TERM "$$"
  fi
  return 0
}}
set -T
trap _signal_exact_launch_gap DEBUG
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- touch {payload_marker!s}
""",
        env,
    )

    assert completed.returncode == 143, completed.stderr
    assert debug_marker.exists()
    assert not payload_marker.exists()
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "signal_term"
    owner = Path(f"{lock_dir}.owner.json")
    if owner_retained:
        owner_payload = json.loads(owner.read_text())
        assert owner_payload["scope_unit"] == "none"
        assert owner_payload["control_group"] == "none"
        recovered = _run(
            f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head recovered-head --heartbeat-file {tmp_path / 'recovered-heartbeat'}
research_guard_release
""",
            env,
        )
        assert recovered.returncode == 0, recovered.stderr
        assert not owner.exists()
    else:
        assert not owner.exists()


def test_control_group_binding_requires_exact_unit_basename_and_canonical_path() -> None:
    unit = "openclaw-research-track-alpha-" + ("a" * 32) + ".scope"
    script = f"""
_research_guard_control_group_matches_unit "/app.slice/{unit}" "{unit}"
for bad in \
  "/app.slice/unrelated.scope" \
  "/app.slice/./{unit}" \
  "/app.slice/../{unit}"; do
  set +e
  _research_guard_control_group_matches_unit "$bad" "{unit}"
  rc=$?
  set -e
  [[ "$rc" -eq 75 ]]
done
"""
    completed = _run(script, {**os.environ})
    assert completed.returncode == 0, completed.stderr


def test_cgroup_empty_proof_requires_populated_zero_or_removed_exact_group(
    tmp_path: Path,
) -> None:
    cgroup_root = tmp_path / "cgroup"
    parent = cgroup_root / "app.slice"
    group = parent / "openclaw-research-track-alpha.scope"
    group.mkdir(parents=True)
    (cgroup_root / "cgroup.controllers").write_text("memory pids\n", encoding="utf-8")
    events = group / "cgroup.events"
    env = _with_fake_flock(tmp_path, {**os.environ})

    events.write_text("populated 0\nfrozen 0\n", encoding="utf-8")
    empty = _run(
        f'_research_guard_wait_cgroup_empty "/app.slice/{group.name}" {cgroup_root!s} 1',
        env,
    )
    assert empty.returncode == 0, empty.stderr

    events.write_text("populated 1\nfrozen 0\n", encoding="utf-8")
    populated = _run(
        f"""
set +e
_research_guard_wait_cgroup_empty "/app.slice/{group.name}" {cgroup_root!s} 1
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )
    assert populated.returncode == 0, populated.stderr

    shutil.rmtree(group)
    removed = _run(
        f'_research_guard_wait_cgroup_empty "/app.slice/{group.name}" {cgroup_root!s} 1',
        env,
    )
    assert removed.returncode == 0, removed.stderr

    (cgroup_root / "cgroup.controllers").unlink()
    untrusted_absence = _run(
        f"""
set +e
_research_guard_wait_cgroup_empty "/app.slice/{group.name}" {cgroup_root!s} 1
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
        env,
    )
    assert untrusted_absence.returncode == 0, untrusted_absence.stderr


def test_payload_observes_token_bound_control_group_before_exec(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    observed = tmp_path / "owner-at-payload.json"
    env = _with_fake_flock(
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
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["control_group"] != "none"; assert p["control_group"].endswith(p["scope_unit"]); json.dump(p, open(sys.argv[2], "w"))' \
  {str(lock_dir) + '.owner.json'} {observed!s}
research_guard_complete --completion-path {observed!s}
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(observed.read_text())
    assert payload["scope_unit"].endswith(".scope")
    assert payload["control_group"].endswith(payload["scope_unit"])


def test_atomic_scope_bind_rejects_preexisting_split_owner(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    heartbeat = tmp_path / "heartbeat"
    env = _with_fake_flock(
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
unit="openclaw-research-track-alpha-${{RESEARCH_GUARD_TOKEN}}.scope"
control_group="/app.slice/${{unit}}"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); p["scope_unit"]=sys.argv[2]; p["control_group"]="none"; json.dump(p, open(sys.argv[1], "w"), sort_keys=True)' \
  "$RESEARCH_GUARD_OWNER_PATH" "$unit"
if _research_guard_bind_owner_control_group \
  "$RESEARCH_GUARD_OWNER_PATH" "$RESEARCH_GUARD_TOKEN" "$unit" \
  "$control_group" "$RESEARCH_GUARD_HEARTBEAT_FILE"; then
  exit 99
fi
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(owner.read_text())
    assert payload["scope_unit"].endswith(".scope")
    assert payload["control_group"] == "none"


def test_sigkill_owner_from_real_stage_reclaims_only_after_bound_cgroup_is_empty(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    pid_file = tmp_path / "payload-pid"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
            "OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC": "0",
        },
    )
    script = f"""set -euo pipefail
source {GUARD!s}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'printf "%s\\n" "$$" > "$1"; exec sleep 30' _ {pid_file!s}
"""
    proc = subprocess.Popen(
        ["bash", "-c", script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    payload_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if pid_file.exists() and pid_file.read_text().strip():
                payload_pid = int(pid_file.read_text().strip())
                break
            time.sleep(0.02)
        assert payload_pid is not None
        owner_payload = json.loads(owner.read_text())
        assert owner_payload["control_group"] != "none"
        assert owner_payload["control_group"].endswith(owner_payload["scope_unit"])
        proc.kill()
        proc.wait(timeout=5)
        os.kill(payload_pid, signal.SIGKILL)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if payload_pid is not None:
            try:
                os.kill(payload_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    old_token = json.loads(owner.read_text())["token"]
    recovered = _run(
        f"""
_research_guard_wait_cgroup_empty() {{ return 0; }}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head recovered-head --heartbeat-file {tmp_path / 'recovered-heartbeat'}
[[ "$RESEARCH_GUARD_TOKEN" != {old_token!s} ]]
research_guard_release
""",
        env,
    )
    assert recovered.returncode == 0, recovered.stderr
    assert not owner.exists()


def test_sigkill_before_scope_bind_leaves_recoverable_none_none_owner(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    launcher_pid_file = tmp_path / "launcher-pid"
    payload_marker = tmp_path / "payload-must-not-run"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
            "OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC": "0",
            "FAKE_LAUNCHER_PID_FILE": str(launcher_pid_file),
        },
    )
    fake_systemd_run = tmp_path / "bin/systemd-run"
    fake_systemd_run.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$$\" > \"$FAKE_LAUNCHER_PID_FILE\"\n"
        "exec sleep 30\n",
        encoding="utf-8",
    )
    fake_systemd_run.chmod(0o755)
    script = f"""set -euo pipefail
source {GUARD!s}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- touch {payload_marker!s}
"""
    proc = subprocess.Popen(
        ["bash", "-c", script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    launcher_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if launcher_pid_file.exists() and launcher_pid_file.read_text().strip():
                launcher_pid = int(launcher_pid_file.read_text().strip())
                break
            time.sleep(0.02)
        assert launcher_pid is not None
        owner_payload = json.loads(owner.read_text())
        assert owner_payload["scope_unit"] == "none"
        assert owner_payload["control_group"] == "none"
        proc.kill()
        proc.wait(timeout=5)
        os.kill(launcher_pid, signal.SIGKILL)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if launcher_pid is not None:
            try:
                os.kill(launcher_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    assert not payload_marker.exists()
    recovered = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head recovered-head --heartbeat-file {tmp_path / 'recovered-heartbeat'}
research_guard_release
""",
        env,
    )
    assert recovered.returncode == 0, recovered.stderr
    assert not owner.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"track_max": "1"}, id="tracking-memory-max"),
        pytest.param({"track_swap": "0"}, id="tracking-swap-max"),
        pytest.param({"track_tasks": "32"}, id="tracking-tasks-max"),
        pytest.param({"track_slice": "openclaw-research.slice"}, id="tracking-parent"),
        pytest.param({"cgroup_match": False}, id="tracking-cgroup-membership"),
        pytest.param({"track_max_rc": 1}, id="tracking-memory-query-error"),
        pytest.param({"track_swap_rc": 1}, id="tracking-swap-query-error"),
        pytest.param({"track_tasks_rc": 1}, id="tracking-tasks-query-error"),
        pytest.param({"track_slice_rc": 1}, id="tracking-parent-query-error"),
        pytest.param(
            {"control_group_basename": "unrelated.scope"},
            id="tracking-control-group-mismatch",
        ),
    ],
)
def test_wrong_default_off_tracking_readback_fails_closed_before_payload(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    data_dir = tmp_path / "data"
    marker = tmp_path / "must-not-run"
    env = _with_fake_systemd(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
        **overrides,
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'touch "$1"' _ {marker!s}
rc=$?
set -e
[[ "$rc" -eq 125 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "stage_nonzero"
    assert payload["rc"] == 125


def test_verified_systemd_scope_runs_and_records_complete(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    marker = tmp_path / "ran-in-verified-scope"
    env = _with_fake_systemd(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "1",
        },
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'printf verified > "$1"' _ {marker!s}
research_guard_complete --completion-path {marker!s}
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert marker.read_text() == "verified"
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    assert json.loads(state.read_text())["status"] == "COMPLETE"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"slice_high": "1"}, id="aggregate-memory-high"),
        pytest.param({"slice_max": "1"}, id="aggregate-memory-max"),
        pytest.param({"slice_swap": "1"}, id="aggregate-swap"),
        pytest.param({"scope_max": "1"}, id="scope-memory-max"),
        pytest.param({"scope_swap": "1"}, id="scope-swap"),
        pytest.param({"scope_tasks": "31"}, id="scope-tasks"),
        pytest.param({"scope_slice": "wrong.slice"}, id="scope-parent"),
        pytest.param({"cgroup_match": False}, id="cgroup-membership"),
        pytest.param({"slice_high_rc": 1}, id="aggregate-memory-high-query-error"),
        pytest.param({"slice_max_rc": 1}, id="aggregate-memory-max-query-error"),
        pytest.param({"slice_swap_rc": 1}, id="aggregate-swap-query-error"),
        pytest.param({"scope_max_rc": 1}, id="scope-memory-max-query-error"),
        pytest.param({"scope_swap_rc": 1}, id="scope-swap-query-error"),
        pytest.param({"scope_tasks_rc": 1}, id="scope-tasks-query-error"),
        pytest.param({"scope_slice_rc": 1}, id="scope-parent-query-error"),
    ],
)
def test_wrong_systemd_readback_fails_closed_before_payload(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    data_dir = tmp_path / "data"
    marker = tmp_path / "must-not-run"
    env = _with_fake_systemd(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "1",
        },
        **overrides,
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
set +e
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'touch "$1"' _ {marker!s}
rc=$?
set -e
[[ "$rc" -eq 125 ]]
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "stage_nonzero"
    assert payload["rc"] == 125
    assert not list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )


def test_term_kills_owner_bound_fork_tree_before_releasing_owner(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    pid_file = tmp_path / "child-pids"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    script = f"""set -euo pipefail
source {GUARD!s}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT
trap 'research_guard_abort_signal INT 130' INT
trap 'research_guard_abort_signal TERM 143' TERM
bash -c 'sleep 30 & grand=$!; printf "%s %s\\n" "$$" "$grand" > "$1"; wait "$grand"' _ {pid_file!s} &
RESEARCH_GUARD_CHILD_PID=$!
wait "$RESEARCH_GUARD_CHILD_PID"
"""
    proc = subprocess.Popen(
        ["bash", "-c", script],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    child_pids: list[int] = []
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if pid_file.exists() and pid_file.read_text().strip():
                child_pids = [int(value) for value in pid_file.read_text().split()]
                break
            time.sleep(0.02)
        assert len(child_pids) == 2
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 143, (stdout, stderr)
        for child_pid in child_pids:
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid, 0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for child_pid in child_pids:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "signal_term"
    assert payload["rc"] == 143
    assert not Path(f"{lock_dir}.owner.json").exists()
    assert not list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )


def test_term_escalates_for_ignoring_descendant_before_owner_release(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    pid_file = tmp_path / "ignoring-child-pids"
    env = _with_fake_flock(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
    )
    script = f"""set -euo pipefail
source {GUARD!s}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT
trap 'research_guard_abort_signal TERM 143' TERM
bash -c 'trap "" TERM; sleep 30 & grand=$!; printf "%s %s\\n" "$$" "$grand" > "$1"; wait "$grand"' _ {pid_file!s} &
RESEARCH_GUARD_CHILD_PID=$!
wait "$RESEARCH_GUARD_CHILD_PID"
"""
    proc = subprocess.Popen(
        ["bash", "-c", script],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    child_pids: list[int] = []
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if pid_file.exists() and pid_file.read_text().strip():
                child_pids = [int(value) for value in pid_file.read_text().split()]
                break
            time.sleep(0.02)
        assert len(child_pids) == 2
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=8)
        assert proc.returncode == 143, (stdout, stderr)
        for child_pid in child_pids:
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid, 0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for child_pid in child_pids:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    assert not Path(f"{lock_dir}.owner.json").exists()
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "signal_term"


def test_late_daemon_after_pid_snapshot_preserves_owner_without_dead_scope_proof(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    root_pid_file = tmp_path / "root-pid"
    late_pid_file = tmp_path / "late-pid"
    spawned_flag = tmp_path / "late-spawned"
    env = _with_fake_systemd(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
            "LATE_PID_FILE": str(late_pid_file),
            "LATE_SPAWNED_FLAG": str(spawned_flag),
        },
        is_active_rc=4,
    )
    fake_pgrep = tmp_path / "bin/pgrep"
    fake_pgrep.write_text(
        """#!/usr/bin/env python3
import os
import subprocess
import sys

flag = os.environ["LATE_SPAWNED_FLAG"]
if not os.path.exists(flag):
    open(flag, "w", encoding="utf-8").close()
    late = subprocess.Popen(
        ["bash", "-c", 'trap "" TERM; exec sleep 30'],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    with open(os.environ["LATE_PID_FILE"], "w", encoding="utf-8") as fh:
        fh.write(f"{late.pid}\\n")
os.execv("/usr/bin/pgrep", ["pgrep", *sys.argv[1:]])
""",
        encoding="utf-8",
    )
    fake_pgrep.chmod(0o755)
    script = f"""set -euo pipefail
source {GUARD!s}
_research_guard_wait_cgroup_empty() {{ return 75; }}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT
trap 'research_guard_abort_signal TERM 143' TERM
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'printf "%s\\n" "$$" > "$1"; sleep 30' _ {root_pid_file!s}
"""
    proc = subprocess.Popen(
        ["bash", "-c", script],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    late_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if root_pid_file.exists() and root_pid_file.read_text().strip():
                break
            time.sleep(0.02)
        assert root_pid_file.exists()
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=8)
        assert proc.returncode == 143, (stdout, stderr)
        assert late_pid_file.exists()
        late_pid = int(late_pid_file.read_text().strip())
        os.kill(late_pid, 0)
        assert Path(f"{lock_dir}.owner.json").exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if late_pid is not None:
            try:
                os.kill(late_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("is_active_rc", [3, 4], ids=["inactive", "unknown"])
def test_unproven_scope_death_preserves_owner_metadata(
    tmp_path: Path, is_active_rc: int
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    owner = Path(f"{lock_dir}.owner.json")
    env = _with_fake_systemd(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "1",
        },
        is_active_rc=is_active_rc,
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
unit="openclaw-research-alpha-${{RESEARCH_GUARD_TOKEN}}.scope"
control_group="/app.slice/${{unit}}"
_research_guard_bind_owner_control_group \
  "$RESEARCH_GUARD_OWNER_PATH" "$RESEARCH_GUARD_TOKEN" "$unit" \
  "$control_group" "$RESEARCH_GUARD_HEARTBEAT_FILE"
RESEARCH_GUARD_SCOPE_UNIT="$unit"
RESEARCH_GUARD_CONTROL_GROUP="$control_group"
research_guard_abort_signal TERM 143
""",
        env,
    )

    assert completed.returncode == 143, completed.stderr
    assert owner.exists()
    owner_payload = json.loads(owner.read_text())
    assert owner_payload["scope_unit"].endswith(".scope")
    assert owner_payload["control_group"].endswith(owner_payload["scope_unit"])
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "signal_term"
    assert payload["rc"] == 143
    assert not list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )


def test_process_tree_discovery_error_preserves_owner_metadata(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    pid_file = tmp_path / "child-pid"
    env = _with_fake_systemd(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
        is_active_rc=4,
    )
    fake_pgrep = tmp_path / "bin/pgrep"
    fake_pgrep.write_text("#!/usr/bin/env bash\nexit 2\n", encoding="utf-8")
    fake_pgrep.chmod(0o755)
    script = f"""set -euo pipefail
source {GUARD!s}
_research_guard_wait_cgroup_empty() {{ return 75; }}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT
trap 'research_guard_abort_signal TERM 143' TERM
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'printf "%s\\n" "$$" > "$1"; exec sleep 30' _ {pid_file!s}
"""
    proc = subprocess.Popen(
        ["bash", "-c", script],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    child_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if pid_file.exists() and pid_file.read_text().strip():
                child_pid = int(pid_file.read_text().strip())
                break
            time.sleep(0.02)
        assert child_pid is not None
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=8)
        assert proc.returncode == 143
        # Discovery failure intentionally leaves the payload unproven. Terminate
        # that known test payload before draining inherited pipes so its PID
        # cannot be reused during delayed best-effort cleanup.
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child_pid = None
        proc.communicate(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    owner = Path(f"{lock_dir}.owner.json")
    assert owner.exists()
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "signal_term"


def test_identity_query_error_during_death_wait_preserves_owner_metadata(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    pid_file = tmp_path / "child-pid"
    env = _with_fake_systemd(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
        is_active_rc=3,
    )
    script = f"""set -euo pipefail
source {GUARD!s}
_research_guard_wait_cgroup_empty() {{ return 75; }}
_research_guard_identity_alive() {{ return 75; }}
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT
trap 'research_guard_abort_signal TERM 143' TERM
research_guard_run_stage --lane alpha --memory-max-bytes 12884901888 \
  --tasks-max 32 -- bash -c 'printf "%s\\n" "$$" > "$1"; exec sleep 30' _ {pid_file!s}
"""
    proc = subprocess.Popen(
        ["bash", "-c", script],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    child_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if pid_file.exists() and pid_file.read_text().strip():
                child_pid = int(pid_file.read_text().strip())
                break
            time.sleep(0.02)
        assert child_pid is not None
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 143, (stdout, stderr)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    assert Path(f"{lock_dir}.owner.json").exists()
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "signal_term"


def test_dead_root_before_snapshot_preserves_owner_metadata(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    lock_dir = tmp_path / "alpha.lock.d"
    env = _with_fake_flock(
        tmp_path,
        {**os.environ, "OPENCLAW_DATA_DIR": str(data_dir)},
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
RESEARCH_GUARD_CHILD_PID=99999999
research_guard_abort_signal TERM 143
""",
        env,
    )

    assert completed.returncode == 143, completed.stderr
    assert Path(f"{lock_dir}.owner.json").exists()
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    payload = json.loads(state.read_text())
    assert payload["status"] == "INCOMPLETE"
    assert payload["reason"] == "signal_term"


@pytest.mark.parametrize("fail_mv", [1, 2], ids=["markdown-move", "json-move"])
def test_alpha_json_authority_is_never_replaced_on_pair_publish_failure(
    tmp_path: Path, fail_mv: int
) -> None:
    data_dir = tmp_path / "data"
    latest_json = tmp_path / "latest.json"
    latest_md = tmp_path / "latest.md"
    stage_json = tmp_path / "stage.json"
    stage_md = tmp_path / "stage.md"
    latest_json.write_text("old-json")
    latest_md.write_text("old-md")
    stage_json.write_text("new-json")
    stage_md.write_text("new-md")
    env = _with_fake_publish_tools(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
        fail_mv=fail_mv,
    )
    completed = _run(
        f"""
research_guard_acquire --lane alpha --lock-dir {tmp_path / 'alpha.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
set +e
research_guard_publish_json_pair {stage_json!s} {latest_json!s} \
  {stage_md!s} {latest_md!s}
rc=$?
set -e
[[ "$rc" -eq 74 ]]
research_guard_incomplete pair_publish_failed "$rc"
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    assert latest_json.read_text() == "old-json"
    assert latest_md.read_text() == ("old-md" if fail_mv == 1 else "new-md")
    state = next((data_dir / "research_workload_guard/alpha").glob("*.state.json"))
    assert json.loads(state.read_text())["status"] == "INCOMPLETE"
    assert not list(
        (data_dir / "research_workload_guard/alpha").glob("*.completion.json")
    )


@pytest.mark.parametrize(
    "failure",
    ["harness", "history", "completion", "copy", "move", "success"],
)
def test_polymarket_sequence_never_publishes_latest_on_partial_failure(
    tmp_path: Path, failure: str
) -> None:
    data_dir = tmp_path / "data"
    output = tmp_path / "report.json"
    history = tmp_path / "history.json"
    latest = tmp_path / "latest.json"
    missing = tmp_path / "missing.json"
    latest.write_text("old-latest")
    env = _with_fake_publish_tools(
        tmp_path,
        {
            **os.environ,
            "OPENCLAW_DATA_DIR": str(data_dir),
            "OPENCLAW_RESEARCH_CONTAINMENT_ENABLED": "0",
        },
        fail_cp=failure == "copy",
        fail_mv=1 if failure == "move" else 0,
    )
    completed = _run(
        f"""
research_guard_acquire --lane polymarket --lock-dir {tmp_path / 'poly.lock.d'} \
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
trap research_guard_release EXIT INT TERM
harness_rc=0
set +e
research_guard_run_stage --lane polymarket --memory-max-bytes 6442450944 \
  --tasks-max 32 -- bash -c '[[ "$1" == harness ]] && exit 23; printf new-report > "$2"' \
  _ {failure} {output!s}
harness_rc=$?
set -e
history_rc=0
if (( harness_rc == 0 )); then
  set +e
  research_guard_run_stage --lane polymarket --memory-max-bytes 6442450944 \
    --tasks-max 32 -- bash -c '[[ "$1" == history ]] && exit 24; printf new-history > "$2"' \
    _ {failure} {history!s}
  history_rc=$?
  set -e
fi
complete_rc=0
if (( harness_rc == 0 && history_rc == 0 )); then
  set +e
  if [[ {failure!r} == completion ]]; then
    research_guard_complete --completion-path {output!s} --completion-path {missing!s}
  else
    research_guard_complete --completion-path {output!s} --completion-path {history!s}
  fi
  complete_rc=$?
  set -e
fi
publish_rc=0
if (( harness_rc == 0 && history_rc == 0 && complete_rc == 0 )); then
  set +e
  research_guard_publish_latest {output!s} {latest!s}
  publish_rc=$?
  set -e
  if (( publish_rc != 0 )); then
    research_guard_incomplete latest_publish_failed "$publish_rc"
  fi
elif (( harness_rc != 0 || history_rc != 0 )); then
  research_guard_incomplete harness_or_history_incomplete "$((harness_rc + history_rc))"
fi
""",
        env,
    )

    assert completed.returncode == 0, completed.stderr
    state = next(
        (data_dir / "research_workload_guard/polymarket").glob("*.state.json")
    )
    payload = json.loads(state.read_text())
    manifests = list(
        (data_dir / "research_workload_guard/polymarket").glob("*.completion.json")
    )
    if failure == "success":
        assert latest.read_text() == "new-report"
        assert payload["status"] == "COMPLETE"
        assert len(manifests) == 1
    else:
        assert latest.read_text() == "old-latest"
        assert payload["status"] == "INCOMPLETE"
        assert not manifests


def test_live_flock_owner_is_refused_when_flock_is_available(tmp_path: Path) -> None:
    flock = shutil.which("flock")
    if flock is None:
        import pytest

        pytest.skip("flock unavailable on this host")
    lock_dir = tmp_path / "alpha.lock.d"
    lock_file = Path(f"{lock_dir}.flock")
    lock_file.touch()
    holder = subprocess.Popen(
        ["bash", "-c", f'exec 218>"{lock_file}"; flock -n 218; sleep 10']
    )
    try:
        env = {**os.environ, "OPENCLAW_DATA_DIR": str(tmp_path / "data")}
        completed = _run(
            f"""
set +e
research_guard_acquire --lane alpha --lock-dir {lock_dir!s} \\
  --source-head test-head --heartbeat-file {tmp_path / 'heartbeat'}
rc=$?
set -e
[[ "$rc" -eq 75 ]]
""",
            env,
        )
        assert completed.returncode == 0, completed.stderr
    finally:
        holder.terminate()
        holder.wait(timeout=5)
