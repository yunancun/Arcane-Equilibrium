#!/usr/bin/python3
"""Sealed one-shot repair for the learning-lane runtime generation pin.

The exact repository helper remains the only writer used for the successful
effect.  This wrapper adds immutable admission facts, holds the natural-lane
flock across the write and postcheck, verifies source-generation MATCH, and
restores the exact previous bytes if the helper or any postcheck fails.

It does not query PostgreSQL, contact a broker, restart a service, or change
engine/API/ALR/watchdog/cron/auth/risk/order/probe state.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA = "p0a_generation_pin_apply_v1"
EXPECTED_HEAD = "cf42f8196f16ccefb4e94a041e2f96b722b97df6"
OLD_HEAD = "94380563f1e3b72875d166fca4f22af6e37f90d9"
OLD_PIN_SHA256 = (
    "b47dda5ba9a47ef96563ad40712bee78194b42b0fc84de3753b6da8b0c0334f4"
)
OLD_PIN_BASE64 = (
    "ewogICJoZWFkIjogIjk0MzgwNTYzZjFlM2I3Mjg3NWQxNjZmY2E0ZjIyYWY2ZTM3"
    "ZjkwZDkiLAogICJkZXJpdmVkX2F0X3V0YyI6ICIyMDI2LTA3LTE2VDIxOjA0OjQ2"
    "WiIsCiAgIndyaXRlciI6ICJkZXJpdmVfZXhwZWN0ZWRfc291cmNlX2hlYWQuc2gi"
    "LAogICJiYXNlX2RpciI6ICIvaG9tZS9uY3l1L0J5Yml0T3BlbkNsYXcvc3J2Igp9"
    "Cg=="
)
EXPECTED_HELPER_SHA256 = (
    "aeb2e0e3099a36820d04858c207d06174a975b4e2bbb6493760bb67a3f1eb130"
)
EXPECTED_CRONTAB_SHA256 = (
    "7ff294a632256c849f35ed8ea3d635842b9044c5495b703b4aef01e2ed26697b"
)
EXPECTED_UID = 1000
EXPECTED_GID = 1000
EXPECTED_OLD_PIN_DEV = 66312
EXPECTED_OLD_PIN_INO = 61374882
EXPECTED_LANE_LOCK_DEV = 66312
EXPECTED_LANE_LOCK_INO = 60613559

REPO = Path("/home/ncyu/BybitOpenClaw/srv")
DATA = Path("/home/ncyu/BybitOpenClaw/var/openclaw")
HELPER = REPO / "helper_scripts/deploy/derive_expected_source_head.sh"
PIN_DIR = DATA / "runtime_generation"
PIN = PIN_DIR / "expected_source_head.json"
LANE_LOCK = DATA / "locks/cost_gate_learning_lane_cron.lock"
LANE_OWNER = (
    DATA / "locks/cost_gate_learning_lane_cron.owner.owner.json"
)
CANONICAL_AUTH = Path(
    "/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json"
)
KNOWN_INERT_AUTH = Path(
    "/home/ncyu/BybitOpenClaw/var/openclaw/"
    "runtime_recovery_demo_read_secrets_0a4d38ee/live/authorization.json"
)

SYSTEM_ENV = {
    "HOME": "/home/ncyu",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "USER": "ncyu",
    "LOGNAME": "ncyu",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "XDG_RUNTIME_DIR": "/run/user/1000",
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
DERIVE_ENV = {
    **SYSTEM_ENV,
    "OPENCLAW_BASE_DIR": str(REPO),
    "OPENCLAW_DATA_DIR": str(DATA),
}
UNIT_NAMES = (
    "openclaw-trading-api.service",
    "openclaw-watchdog.service",
    "openclaw-alr-shadow.service",
)
UNIT_PROPERTIES = (
    "ActiveState",
    "SubState",
    "MainPID",
    "ExecMainStartTimestampMonotonic",
    "NRestarts",
    "InvocationID",
    "ControlGroup",
)
GENERATION_ENV_NAMES = (
    "OPENCLAW_EXPECTED_SOURCE_HEAD",
    "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD",
    "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD",
)
LANE_PROCESS_NEEDLES = (
    "cost_gate_learning_lane_cron.sh",
    "demo_order_to_fill_gap_audit.py",
    "demo_data_flow_monitor.py",
    "cost_gate_reject_counterfactual.py",
    "cost_gate_learning_lane.outcome_review",
)
APPLY_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class PinApplyError(RuntimeError):
    """Fail-closed admission or postcheck error."""


class HelperProcessGroupUnverified(PinApplyError):
    """The helper process group could not be proven fully quiescent."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env or SYSTEM_ENV,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        evidence = {
            "argv": [Path(argv[0]).name, *argv[1:]],
            "returncode": completed.returncode,
            "stdout_sha256": sha256_bytes(completed.stdout.encode()),
            "stderr_sha256": sha256_bytes(completed.stderr.encode()),
        }
        raise PinApplyError(
            "command_failed:"
            + sha256_bytes(
                json.dumps(
                    evidence, sort_keys=True, separators=(",", ":")
                ).encode()
            )
        )
    return completed


def git(*args: str) -> str:
    return run(
        ["/usr/bin/git", "-C", str(REPO), *args],
        env=SYSTEM_ENV,
    ).stdout.strip()


def parse_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PinApplyError("pin_timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise PinApplyError("pin_timestamp_naive")
    return parsed.astimezone(timezone.utc)


def _identity_from_stat(st: os.stat_result) -> dict[str, Any]:
    return {
        "dev": st.st_dev,
        "ino": st.st_ino,
        "uid": st.st_uid,
        "gid": st.st_gid,
        "mode": stat.S_IMODE(st.st_mode),
        "size": st.st_size,
        "nlink": st.st_nlink,
    }


def read_regular_bytes(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise PinApplyError(f"path_unavailable:{path.name}") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise PinApplyError(f"symlink_rejected:{path.name}")
    if not stat.S_ISREG(path_stat.st_mode):
        raise PinApplyError(f"non_regular_file:{path.name}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    chunks: list[bytes] = []
    try:
        opened_stat = os.fstat(fd)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or (opened_stat.st_dev, opened_stat.st_ino)
            != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise PinApplyError(f"path_replaced_during_read:{path.name}")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final_stat = os.fstat(fd)
        if (
            final_stat.st_size != opened_stat.st_size
            or final_stat.st_mtime_ns != opened_stat.st_mtime_ns
        ):
            raise PinApplyError(f"path_changed_during_read:{path.name}")
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) != opened_stat.st_size:
        raise PinApplyError(f"path_short_read:{path.name}")
    result = _identity_from_stat(opened_stat)
    result["sha256"] = sha256_bytes(raw)
    return raw, result


def file_identity(path: Path, *, include_hash: bool = False) -> dict[str, Any]:
    if include_hash:
        _raw, result = read_regular_bytes(path)
        return result
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise PinApplyError(f"path_unavailable:{path.name}") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise PinApplyError(f"symlink_rejected:{path.name}")
    if not stat.S_ISREG(path_stat.st_mode):
        raise PinApplyError(f"non_regular_file:{path.name}")
    return _identity_from_stat(path_stat)


def capture_verified_helper(
    *,
    path: Path = HELPER,
    expected_identity: dict[str, Any],
    expected_sha256: str = EXPECTED_HELPER_SHA256,
    expected_uid: int = EXPECTED_UID,
    expected_gid: int = EXPECTED_GID,
) -> tuple[bytes, dict[str, Any]]:
    """Capture the exact verified helper bytes that will be executed."""

    raw, identity = read_regular_bytes(path)
    if identity != expected_identity:
        raise PinApplyError("helper_identity_changed_before_execution")
    if (
        identity["sha256"] != expected_sha256
        or identity["uid"] != expected_uid
        or identity["gid"] != expected_gid
        or identity["nlink"] != 1
    ):
        raise PinApplyError("helper_execution_identity_mismatch")
    return raw, identity


def _helper_process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise HelperProcessGroupUnverified(
            "helper_process_group_permission_denied"
        ) from exc
    return True


def _kill_and_reap_helper_group(
    process: subprocess.Popen[bytes],
) -> tuple[bytes, bytes]:
    try:
        block_apply_signals()
        return _kill_and_reap_helper_group_after_signal_block(process)
    except HelperProcessGroupUnverified:
        raise
    except BaseException as exc:
        raise HelperProcessGroupUnverified(
            "helper_process_group_cleanup_interrupted"
        ) from exc


def _kill_and_reap_helper_group_after_signal_block(
    process: subprocess.Popen[bytes],
) -> tuple[bytes, bytes]:
    pgid = process.pid
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise HelperProcessGroupUnverified(
            "helper_process_group_kill_failed"
        ) from exc
    try:
        stdout, stderr = process.communicate(timeout=5)
    except BaseException as exc:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as kill_exc:
            raise HelperProcessGroupUnverified(
                "helper_process_group_rekill_failed"
            ) from kill_exc
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=5)
        except BaseException as reap_exc:
            raise HelperProcessGroupUnverified(
                "helper_process_group_reap_failed"
            ) from reap_exc
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            block_apply_signals()
    deadline = time.monotonic() + 2
    while _helper_process_group_exists(pgid) and time.monotonic() < deadline:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            break
        except OSError as exc:
            raise HelperProcessGroupUnverified(
                "helper_process_group_drain_kill_failed"
            ) from exc
        time.sleep(0.01)
    if process.returncode is None or _helper_process_group_exists(pgid):
        raise HelperProcessGroupUnverified(
            "helper_process_group_quiescence_unverified"
        )
    return stdout, stderr


def run_verified_helper(
    raw: bytes,
    *,
    timeout: float = 30,
    cwd: Path = REPO,
    bash_path: str = "/usr/bin/bash",
) -> subprocess.CompletedProcess[bytes]:
    """Run captured bytes in an isolated group that is reaped before return."""

    argv = [
        bash_path,
        "--noprofile",
        "--norc",
        "-s",
        "--",
    ]
    previous_signal_mask = block_apply_signals()
    group_quiescence_verified = False
    try:
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=DERIVE_ENV,
                stdin=subprocess.PIPE,
                text=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except BaseException as exc:
            # APPLY_SIGNALS are already blocked, so a real operator signal
            # cannot unwind this spawn window.  Any other BaseException raised
            # before Popen returns leaves child creation unknowable to this
            # process and therefore forbids a verified rollback claim.
            raise HelperProcessGroupUnverified(
                "helper_spawn_outcome_unverified"
            ) from exc
        try:
            stdout, stderr = process.communicate(input=raw, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill_and_reap_helper_group(process)
            group_quiescence_verified = True
            raise PinApplyError("verified_helper_timeout") from exc
        except BaseException:
            _kill_and_reap_helper_group(process)
            group_quiescence_verified = True
            raise
        if _helper_process_group_exists(process.pid):
            _kill_and_reap_helper_group(process)
            group_quiescence_verified = True
            raise PinApplyError("verified_helper_descendant_survived")
        group_quiescence_verified = True
        completed = subprocess.CompletedProcess(
            argv,
            process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        if completed.returncode != 0:
            evidence = {
                "argv": [Path(argv[0]).name, *argv[1:]],
                "returncode": completed.returncode,
                "stdout_sha256": sha256_bytes(completed.stdout),
                "stderr_sha256": sha256_bytes(completed.stderr),
                "executed_sha256": sha256_bytes(raw),
            }
            raise PinApplyError(
                "verified_helper_failed:"
                + sha256_bytes(
                    json.dumps(
                        evidence, sort_keys=True, separators=(",", ":")
                    ).encode()
                )
            )
        return completed
    finally:
        if group_quiescence_verified:
            restore_apply_signal_mask(previous_signal_mask)
        else:
            # A one-shot apply must keep the effect signals blocked until its
            # FAIL_CLOSED_UNVERIFIED receipt is flushed and the process exits.
            block_apply_signals()


def validate_new_pin(
    path: Path,
    *,
    started_at: datetime,
    finished_at: datetime,
    expected_uid: int = EXPECTED_UID,
    expected_gid: int = EXPECTED_GID,
) -> dict[str, Any]:
    raw, identity = read_regular_bytes(path)
    if (
        identity["mode"] != 0o600
        or identity["uid"] != expected_uid
        or identity["gid"] != expected_gid
        or identity["nlink"] != 1
    ):
        raise PinApplyError("new_pin_identity_mismatch")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PinApplyError("new_pin_json_invalid") from exc
    required = {"head", "derived_at_utc", "writer", "base_dir"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise PinApplyError("new_pin_fields_mismatch")
    if any(not isinstance(payload[key], str) for key in required):
        raise PinApplyError("new_pin_non_string_field")
    if (
        payload["head"] != EXPECTED_HEAD
        or payload["writer"] != "derive_expected_source_head.sh"
        or payload["base_dir"] != str(REPO)
    ):
        raise PinApplyError("new_pin_value_mismatch")
    derived = parse_utc(payload["derived_at_utc"])
    tolerance = timedelta(seconds=2)
    if not started_at - tolerance <= derived <= finished_at + tolerance:
        raise PinApplyError("new_pin_timestamp_outside_apply_window")
    return {"identity": identity, "payload": payload}


def fsync_path_and_parent(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    parent_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def atomic_restore_pin(
    path: Path,
    raw: bytes,
    *,
    expected_uid: int = EXPECTED_UID,
    expected_gid: int = EXPECTED_GID,
) -> dict[str, Any]:
    temp = path.parent / (
        f".{path.name}.rollback-{os.getpid()}-{time.time_ns()}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, expected_uid, expected_gid)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise PinApplyError("rollback_short_write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temp, path)
        fsync_path_and_parent(path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    identity = file_identity(path, include_hash=True)
    if (
        identity["sha256"] != sha256_bytes(raw)
        or identity["mode"] != 0o600
        or identity["uid"] != expected_uid
        or identity["gid"] != expected_gid
        or identity["nlink"] != 1
    ):
        raise PinApplyError("rollback_verification_failed")
    return identity


def process_start_ticks(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[21]
    except (OSError, IndexError) as exc:
        raise PinApplyError(f"process_identity_unavailable:{pid}") from exc


def unit_snapshot(name: str) -> dict[str, str]:
    argv = ["/usr/bin/systemctl", "--user", "show", name]
    for field in UNIT_PROPERTIES:
        argv.extend(("-p", field))
    completed = run(argv)
    result: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    try:
        pid = int(result.get("MainPID") or "0")
    except ValueError as exc:
        raise PinApplyError(f"unit_pid_invalid:{name}") from exc
    result["ProcessStartTicks"] = process_start_ticks(pid) if pid else ""
    if (
        result.get("ActiveState") != "active"
        or result.get("SubState") != "running"
        or not pid
    ):
        raise PinApplyError(f"unit_not_running:{name}")
    return result


def engine_processes() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            exe = os.readlink(proc / "exe")
            if Path(exe).name != "openclaw-engine":
                continue
            fields = (proc / "stat").read_text().split()
            result.append(
                {
                    "pid": int(proc.name),
                    "ppid": int(fields[3]),
                    "pgid": int(fields[4]),
                    "start_ticks": fields[21],
                    "exe": exe,
                    "exe_sha256": sha256_bytes(
                        Path(f"/proc/{proc.name}/exe").read_bytes()
                    ),
                }
            )
        except (OSError, IndexError, ValueError):
            continue
    result.sort(key=lambda row: row["pid"])
    if len(result) != 1:
        raise PinApplyError("engine_process_topology_mismatch")
    return result


def auth_metadata() -> list[dict[str, Any]]:
    paths = {CANONICAL_AUTH, KNOWN_INERT_AUTH}
    result = []
    for path in sorted(paths, key=str):
        row: dict[str, Any] = {"path": str(path), "exists": path.exists()}
        if path.exists():
            identity = file_identity(path, include_hash=False)
            row.update(
                {
                    key: identity[key]
                    for key in ("dev", "ino", "uid", "gid", "mode", "size", "nlink")
                }
            )
        result.append(row)
    return result


def crontab_snapshot() -> dict[str, Any]:
    completed = run(["/usr/bin/crontab", "-l"])
    raw = completed.stdout.encode()
    active = "\n".join(
        line
        for line in completed.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    for name in GENERATION_ENV_NAMES:
        if re.search(rf"(^|\s){re.escape(name)}=", active):
            raise PinApplyError(f"inline_generation_override_present:{name}")
    result = {
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "generation_overrides": [],
    }
    if result["sha256"] != EXPECTED_CRONTAB_SHA256:
        raise PinApplyError("crontab_identity_drift")
    return result


def lane_processes() -> list[int]:
    result: list[int] = []
    own_pid = os.getpid()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == own_pid:
            continue
        try:
            command = (proc / "cmdline").read_bytes().decode(
                errors="replace"
            )
        except OSError:
            continue
        if any(needle in command for needle in LANE_PROCESS_NEEDLES):
            result.append(int(proc.name))
    return sorted(result)


def active_cost_scopes() -> list[str]:
    completed = run(
        [
            "/usr/bin/systemctl",
            "--user",
            "list-units",
            "--type=scope",
            "--state=active",
            "--no-legend",
            "--no-pager",
        ]
    )
    return sorted(
        line.split()[0]
        for line in completed.stdout.splitlines()
        if line.strip()
        and line.split()[0].startswith("openclaw-research-cost-")
    )


def temp_residue() -> list[str]:
    return sorted(
        path.name for path in PIN_DIR.glob(".expected_source_head.*")
    )


def acquire_lane_lock() -> int:
    try:
        before = LANE_LOCK.lstat()
    except OSError as exc:
        raise PinApplyError("lane_lock_unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise PinApplyError("lane_lock_type_mismatch")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(LANE_LOCK, flags)
    try:
        opened = os.fstat(fd)
        expected = (
            EXPECTED_LANE_LOCK_DEV,
            EXPECTED_LANE_LOCK_INO,
            EXPECTED_UID,
            EXPECTED_GID,
            0o600,
            1,
        )
        observed = (
            opened.st_dev,
            opened.st_ino,
            opened.st_uid,
            opened.st_gid,
            stat.S_IMODE(opened.st_mode),
            opened.st_nlink,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or observed != expected
            or (before.st_dev, before.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            raise PinApplyError("lane_lock_fd_identity_mismatch")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        after = LANE_LOCK.lstat()
        if (
            stat.S_ISLNK(after.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or (
                after.st_dev,
                after.st_ino,
                after.st_uid,
                after.st_gid,
                stat.S_IMODE(after.st_mode),
                after.st_nlink,
            )
            != expected
            or (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
            != (after.st_dev, after.st_ino)
        ):
            raise PinApplyError("lane_lock_path_replaced_after_flock")
    except BaseException:
        os.close(fd)
        raise
    return fd


def source_snapshot() -> dict[str, Any]:
    if (
        REPO.resolve() != REPO
        or DATA.resolve() != DATA
        or HELPER.resolve() != HELPER
        or PIN_DIR.resolve() != PIN_DIR
    ):
        raise PinApplyError("canonical_path_mismatch")
    if os.getuid() != EXPECTED_UID or os.getgid() != EXPECTED_GID:
        raise PinApplyError("runtime_identity_mismatch")
    branch = git("symbolic-ref", "--short", "HEAD")
    head = git("rev-parse", "HEAD")
    status_text = git("status", "--porcelain=v1", "--untracked-files=all")
    helper_identity = file_identity(HELPER, include_hash=True)
    if (
        branch != "main"
        or head != EXPECTED_HEAD
        or status_text
        or helper_identity["sha256"] != EXPECTED_HELPER_SHA256
        or helper_identity["nlink"] != 1
    ):
        raise PinApplyError("source_or_helper_identity_drift")
    return {
        "branch": branch,
        "head": head,
        "clean": True,
        "helper": helper_identity,
    }


def old_pin_snapshot() -> tuple[bytes, dict[str, Any]]:
    raw, identity = read_regular_bytes(PIN)
    if (
        raw != base64.b64decode(OLD_PIN_BASE64)
        or identity["sha256"] != OLD_PIN_SHA256
        or identity["dev"] != EXPECTED_OLD_PIN_DEV
        or identity["ino"] != EXPECTED_OLD_PIN_INO
        or identity["uid"] != EXPECTED_UID
        or identity["gid"] != EXPECTED_GID
        or identity["mode"] != 0o600
        or identity["nlink"] != 1
    ):
        raise PinApplyError("old_pin_identity_drift")
    payload = json.loads(raw)
    if payload.get("head") != OLD_HEAD:
        raise PinApplyError("old_pin_head_drift")
    return raw, identity


def collateral_snapshot() -> dict[str, Any]:
    engine = engine_processes()
    return {
        "units": {name: unit_snapshot(name) for name in UNIT_NAMES},
        "engine": engine,
        "auth_metadata": auth_metadata(),
        "crontab": crontab_snapshot(),
    }


def assert_lane_quiescent() -> dict[str, Any]:
    processes = lane_processes()
    scopes = active_cost_scopes()
    if LANE_OWNER.exists() or processes or scopes:
        raise PinApplyError("natural_lane_not_quiescent")
    return {
        "owner_exists": False,
        "processes": [],
        "active_cost_scopes": [],
    }


def post_generation_match() -> dict[str, Any]:
    research_root = REPO / "helper_scripts/research"
    sys.path.insert(0, str(research_root))
    try:
        from cost_gate_learning_lane.source_generation import (
            classify_source_generation,
            resolve_expected_source_head,
        )
    finally:
        try:
            sys.path.remove(str(research_root))
        except ValueError:
            pass
    resolution = resolve_expected_source_head(
        None, data_dir=DATA, env={}
    )
    classification = classify_source_generation(REPO, resolution.get("head"))
    if (
        resolution.get("source") != "pin_file"
        or resolution.get("error") is not None
        or resolution.get("head") != EXPECTED_HEAD
        or classification.get("status") != "MATCH"
        or classification.get("current_source_head") != EXPECTED_HEAD
        or classification.get("expected_source_head") != EXPECTED_HEAD
        or classification.get("blockers") != []
    ):
        raise PinApplyError("source_generation_postcheck_not_match")
    return {
        "resolution": resolution,
        "classification": {
            key: classification.get(key)
            for key in (
                "status",
                "reason",
                "expected_source_head",
                "current_source_head",
                "blockers",
            )
        },
    }


def preflight(*, lock_fd: int | None = None) -> dict[str, Any]:
    owned_fd = lock_fd
    if owned_fd is None:
        owned_fd = acquire_lane_lock()
    try:
        source = source_snapshot()
        _old_raw, pin_identity = old_pin_snapshot()
        lane = assert_lane_quiescent()
        collateral = collateral_snapshot()
        residue = temp_residue()
        if residue:
            raise PinApplyError("pin_temp_residue_present")
        return {
            "schema": SCHEMA,
            "status": "PREFLIGHT_PASS",
            "source": source,
            "old_pin": pin_identity,
            "lane": lane,
            "collateral": collateral,
            "temp_residue": residue,
            "broker_contact_performed": False,
            "pg_access_performed": False,
            "service_restart_performed": False,
        }
    finally:
        if lock_fd is None:
            fcntl.flock(owned_fd, fcntl.LOCK_UN)
            os.close(owned_fd)


def failpoint(_name: str) -> None:
    """No-op production seam used only by isolated transaction tests."""


def block_apply_signals() -> set[signal.Signals]:
    return signal.pthread_sigmask(signal.SIG_BLOCK, APPLY_SIGNALS)


def restore_apply_signal_mask(previous: set[signal.Signals]) -> None:
    signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def emit_and_flush(payload: dict[str, Any]) -> None:
    emit(payload)
    sys.stdout.flush()


def apply_once() -> int:
    lock_fd: int | None = None
    old_raw = b""
    helper_started = False
    previous_handlers = {
        signum: signal.getsignal(signum) for signum in APPLY_SIGNALS
    }

    def _abort_on_signal(signum: int, _frame: Any) -> None:
        block_apply_signals()
        raise PinApplyError(f"apply_interrupted_by_signal:{signum}")

    for signum in APPLY_SIGNALS:
        signal.signal(signum, _abort_on_signal)
    try:
        lock_fd = acquire_lane_lock()
        before = preflight(lock_fd=lock_fd)
        old_raw, _old_identity = old_pin_snapshot()
        helper_raw, helper_identity = capture_verified_helper(
            expected_identity=before["source"]["helper"]
        )
        started = utc_now()
        # Block effect signals before entering the spawn window.  The helper
        # runner restores only to this already-blocked mask after it has proved
        # the complete helper process group absent, so no pending operator
        # signal can create an untracked child or interrupt post-write checks.
        block_apply_signals()
        helper_started = True
        completed = run_verified_helper(helper_raw)
        failpoint("after_helper_write")
        fsync_path_and_parent(PIN)
        finished = utc_now()
        new_pin = validate_new_pin(
            PIN, started_at=started, finished_at=finished
        )
        generation = post_generation_match()
        after_source = source_snapshot()
        after_lane = assert_lane_quiescent()
        after_collateral = collateral_snapshot()
        after_residue = temp_residue()
        if (
            after_source != before["source"]
            or after_lane != before["lane"]
            or after_collateral != before["collateral"]
            or after_residue != before["temp_residue"]
        ):
            raise PinApplyError("postcheck_collateral_drift")
        failpoint("after_postcheck")
        payload = {
            "schema": SCHEMA,
            "status": "APPLIED_POSTCHECK_PASS",
            "started_at": started.isoformat(),
            "completed_at": finished.isoformat(),
            "old_pin_sha256": OLD_PIN_SHA256,
            "new_pin": new_pin,
            "generation": generation,
            "helper_result": {
                "returncode": completed.returncode,
                "executed_sha256": sha256_bytes(helper_raw),
                "identity": helper_identity,
                "stdout_sha256": sha256_bytes(completed.stdout),
                "stderr_sha256": sha256_bytes(completed.stderr),
            },
            "source": after_source,
            "lane": after_lane,
            "collateral": after_collateral,
            "temp_residue": after_residue,
            "broker_contact_performed": False,
            "pg_access_performed": False,
            "service_restart_performed": False,
        }
        failpoint("before_success_emit")
        block_apply_signals()
        emit_and_flush(payload)
        return 0
    except BaseException as exc:
        block_apply_signals()
        payload: dict[str, Any]
        if isinstance(exc, HelperProcessGroupUnverified):
            payload = {
                "schema": SCHEMA,
                "status": "FAIL_CLOSED_UNVERIFIED",
                "error_type": type(exc).__name__,
                "error_digest": sha256_bytes(str(exc).encode()),
                "rollback_attempted": False,
                "rollback_blocker": "helper_process_group_not_quiescent",
            }
        elif helper_started and old_raw:
            try:
                restored = atomic_restore_pin(PIN, old_raw)
                payload = {
                    "schema": SCHEMA,
                    "status": "FAILED_ROLLBACK_VERIFIED",
                    "error_type": type(exc).__name__,
                    "error_digest": sha256_bytes(str(exc).encode()),
                    "restored_pin": restored,
                }
            except BaseException as rollback_exc:
                payload = {
                    "schema": SCHEMA,
                    "status": "FAIL_CLOSED_UNVERIFIED",
                    "error_type": type(exc).__name__,
                    "error_digest": sha256_bytes(str(exc).encode()),
                    "rollback_error_type": type(rollback_exc).__name__,
                    "rollback_error_digest": sha256_bytes(
                        str(rollback_exc).encode()
                    ),
                }
        else:
            payload = {
                "schema": SCHEMA,
                "status": "BLOCKED_NO_EFFECT",
                "error_type": type(exc).__name__,
                "error_digest": sha256_bytes(str(exc).encode()),
            }
        try:
            emit_and_flush(payload)
        except BaseException:
            encoded = (
                json.dumps(
                    {
                        "schema": SCHEMA,
                        "status": payload["status"],
                        "receipt_channel": "stderr_fallback",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
            try:
                os.write(2, encoded)
            except OSError:
                pass
        return 4
    finally:
        block_apply_signals()
        try:
            failpoint("before_cleanup_unlock")
        except BaseException as cleanup_exc:
            try:
                os.write(
                    2,
                    (
                        json.dumps(
                            {
                                "schema": SCHEMA,
                                "status": "CLEANUP_FAILPOINT_CAUGHT",
                                "error_digest": sha256_bytes(
                                    str(cleanup_exc).encode()
                                ),
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode(),
                )
            except OSError:
                pass
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.apply:
        return apply_once()
    try:
        payload = preflight()
    except BaseException as exc:
        emit(
            {
                "schema": SCHEMA,
                "status": (
                    "FAIL_CLOSED_UNVERIFIED"
                    if "FAIL_CLOSED_UNVERIFIED" in str(exc)
                    else "BLOCKED_OR_ROLLED_BACK"
                ),
                "error_type": type(exc).__name__,
                "error_digest": sha256_bytes(str(exc).encode()),
            }
        )
        return 4
    emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
