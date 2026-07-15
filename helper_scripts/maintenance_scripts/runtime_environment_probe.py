#!/usr/bin/env python3
"""Local-only, non-secret runtime identity probe for the Deploy Adapter.

The probe reads a fixed allowlist from the current engine process and local
filesystem.  It never opens a network socket, contacts a broker, mutates a
service, or serializes raw process environment and secret paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

IMPLEMENTATION_DIR = Path(__file__).resolve().parent
if str(IMPLEMENTATION_DIR) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_DIR))

from agent_governance_effects import build_runtime_environment_attestation  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
PROC_ROOT = Path("/proc")
ENGINE_NAME = "openclaw-engine"
MAX_ENVIRONMENT_BYTES = 1024 * 1024
MAX_ENDPOINT_BYTES = 32
ATTESTATION_TTL = timedelta(minutes=5)
GIT_EXECUTABLE = "/usr/bin/git"
PGREP_EXECUTABLE = "/usr/bin/pgrep"
ENVIRONMENT_PROJECTOR = "/usr/bin/grep"
SANITIZED_COMMAND_ENV = {"LC_ALL": "C"}
BOOLEAN_KEYS = (
    "OPENCLAW_ALLOW_MAINNET",
    "OPENCLAW_ENABLE_PAPER",
    "OPENCLAW_DEMO_LEARNING_LANE_WRITER",
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED",
    "OPENCLAW_CANARY_MODE",
)
PATH_KEYS = ("OPENCLAW_DATA_DIR", "OPENCLAW_SECRETS_DIR")
ALLOWED_ENVIRONMENT_KEYS = frozenset((*BOOLEAN_KEYS, *PATH_KEYS))
ENVIRONMENT_PROJECTION_PATTERN = (
    "^(" + "|".join(sorted(ALLOWED_ENVIRONMENT_KEYS)) + ")="
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _hostname() -> str:
    return socket.gethostname()


def _git_text(*args: str) -> str:
    return subprocess.run(
        [GIT_EXECUTABLE, *args], cwd=REPO_ROOT, check=True, text=True,
        capture_output=True, env=SANITIZED_COMMAND_ENV,
    ).stdout.strip()


def _engine_pids() -> list[int]:
    completed = subprocess.run(
        [PGREP_EXECUTABLE, "-x", ENGINE_NAME], check=False, text=True,
        capture_output=True, env=SANITIZED_COMMAND_ENV,
    )
    if completed.returncode == 1:
        return []
    if completed.returncode != 0:
        raise OSError("pgrep failed")
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        if not line.isascii() or not line.isdigit() or int(line) <= 0:
            raise ValueError("pgrep output is invalid")
        pids.add(int(line))
    return sorted(pids)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def _environment_projection(pid: int) -> tuple[bytes, list[str]]:
    """Return only exact allowlisted entries; raw process environment stays outside Python."""

    try:
        completed = subprocess.run(
            [
                ENVIRONMENT_PROJECTOR, "-z", "-E",
                ENVIRONMENT_PROJECTION_PATTERN, "--",
                str(PROC_ROOT / str(pid) / "environ"),
            ],
            check=False,
            capture_output=True,
            env=SANITIZED_COMMAND_ENV,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return b"", ["PROCESS_ENV_PROJECTION_UNAVAILABLE"]
    if completed.returncode not in {0, 1}:
        return b"", ["PROCESS_ENV_PROJECTION_UNAVAILABLE"]
    if len(completed.stdout) > MAX_ENVIRONMENT_BYTES:
        return b"", ["PROCESS_ENV_PROJECTION_OVERSIZE"]
    return completed.stdout, []


def _read_allowlisted_environment(pid: int) -> tuple[dict[str, str], list[str]]:
    raw, blockers = _environment_projection(pid)
    if blockers:
        return {}, blockers
    selected: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        key_bytes, separator, value_bytes = entry.partition(b"=")
        if not separator:
            continue
        try:
            key = key_bytes.decode("ascii")
        except UnicodeDecodeError:
            continue
        if key not in ALLOWED_ENVIRONMENT_KEYS:
            continue
        if key in selected:
            blockers.append(f"PROCESS_ENV_DUPLICATE:{key}")
            continue
        try:
            selected[key] = value_bytes.decode("utf-8")
        except UnicodeDecodeError:
            blockers.append(f"PROCESS_ENV_VALUE_INVALID:{key}")
    for key in sorted(ALLOWED_ENVIRONMENT_KEYS):
        if key not in selected or not selected[key]:
            blockers.append(f"PROCESS_ENV_REQUIRED_MISSING:{key}")
    return selected, blockers


def _strict_boolean(value: str, key: str) -> tuple[bool | None, str | None]:
    if value == "0":
        return False, None
    if value == "1":
        return True, None
    return None, f"RUNTIME_BOOLEAN_INVALID:{key}"


def _safe_directory_identity(value: str, code: str) -> tuple[Path | None, str | None]:
    path = Path(value)
    try:
        if not path.is_absolute() or path.is_symlink():
            return None, code
        resolved = path.resolve(strict=True)
        if not resolved.is_dir():
            return None, code
    except OSError:
        return None, code
    return resolved, None


def _endpoint_identity(secrets_root: Path) -> tuple[str | None, str | None, str | None]:
    endpoint = secrets_root / "live/bybit_endpoint"
    try:
        if endpoint.is_symlink():
            return None, None, "ENDPOINT_METADATA_UNSAFE"
        resolved = endpoint.resolve(strict=True)
        resolved.relative_to(secrets_root)
        before = endpoint.lstat()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(endpoint, flags)
        try:
            observed = os.fstat(descriptor)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_uid != os.geteuid()
                or observed.st_mode & 0o077
                or not 0 < observed.st_size <= MAX_ENDPOINT_BYTES
                or (before.st_dev, before.st_ino) != (observed.st_dev, observed.st_ino)
            ):
                return None, None, "ENDPOINT_METADATA_UNSAFE"
            raw = os.read(descriptor, MAX_ENDPOINT_BYTES + 1)
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        return None, None, "ENDPOINT_METADATA_MISSING"
    except (OSError, ValueError):
        return None, None, "ENDPOINT_METADATA_UNSAFE"
    if raw in {b"mainnet", b"mainnet\n"}:
        return None, None, "MAINNET_ENDPOINT_FORBIDDEN"
    if raw not in {b"demo", b"demo\n"}:
        return None, None, "ENDPOINT_METADATA_UNSAFE"
    return "bybit_demo", _sha256_bytes(raw), None


def _process_start_ticks(pid: int) -> str:
    raw = (PROC_ROOT / str(pid) / "stat").read_text(
        encoding="ascii", errors="strict"
    )
    tail = raw.rsplit(") ", 1)
    if len(tail) != 2:
        raise ValueError("process stat is invalid")
    fields = tail[1].split()
    if len(fields) <= 19 or not fields[19].isdigit() or int(fields[19]) <= 0:
        raise ValueError("process start ticks are invalid")
    return fields[19]


def _process_identity(pid: int) -> tuple[dict[str, Any], list[str]]:
    process_root = PROC_ROOT / str(pid)
    exe = process_root / "exe"
    cwd = process_root / "cwd"
    expected_binary = REPO_ROOT / "rust/target/release/openclaw-engine"
    blockers: list[str] = []
    facts: dict[str, Any] = {}
    try:
        exe_target_text = os.readlink(exe)
        facts["exe_link"] = exe_target_text
        if exe_target_text.endswith(" (deleted)"):
            blockers.append("PROCESS_EXE_DELETED")
        elif not Path(exe_target_text).is_absolute():
            blockers.append("PROCESS_EXE_UNEXPECTED")
        else:
            exe_target = Path(exe_target_text).resolve(strict=True)
            expected = expected_binary.resolve(strict=True)
            if exe_target != expected:
                blockers.append("PROCESS_EXE_UNEXPECTED")
            else:
                facts["process_identity_digest"] = _sha256_file(exe)
    except OSError:
        blockers.append("PROCESS_EXE_UNREADABLE")
    try:
        if Path(os.readlink(cwd)).resolve(strict=True) != REPO_ROOT.resolve(strict=True):
            blockers.append("PROCESS_CWD_MISMATCH")
    except OSError:
        blockers.append("PROCESS_CWD_UNREADABLE")
    try:
        facts["process_start_ticks"] = _process_start_ticks(pid)
    except (OSError, UnicodeError, ValueError):
        blockers.append("PROCESS_START_IDENTITY_UNREADABLE")
    return facts, blockers


def probe_runtime_environment(
    *, phase: str, expected_host: str, expected_source_head: str, now: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return an existing canonical attestation or sorted typed blocker codes."""

    blockers: list[str] = []
    if phase not in {"preflight", "postcheck"}:
        blockers.append("PHASE_UNSUPPORTED")
    try:
        observed = _parse_time(now)
    except (TypeError, ValueError):
        blockers.append("PROBE_TIME_INVALID")
        observed = None
    host = _hostname()
    if host != expected_host:
        blockers.append("HOST_MISMATCH")
    try:
        source_head = _git_text("rev-parse", "HEAD")
        if source_head != expected_source_head:
            blockers.append("SOURCE_HEAD_MISMATCH")
        if _git_text("status", "--porcelain", "--untracked-files=all"):
            blockers.append("SOURCE_TREE_DIRTY")
    except (OSError, subprocess.CalledProcessError):
        source_head = ""
        blockers.append("SOURCE_REPOSITORY_UNREADABLE")

    try:
        pids = _engine_pids()
    except (OSError, ValueError):
        pids = []
        blockers.append("PROCESS_DISCOVERY_UNAVAILABLE")
    if not pids:
        blockers.append("PROCESS_NOT_FOUND")
    elif len(pids) != 1:
        blockers.append("PROCESS_AMBIGUOUS")
    if len(pids) != 1:
        return None, sorted(set(blockers))

    pid = pids[0]
    process_facts, process_blockers = _process_identity(pid)
    blockers.extend(process_blockers)
    selected, environment_blockers = _read_allowlisted_environment(pid)
    blockers.extend(environment_blockers)
    booleans: dict[str, bool] = {}
    for key in BOOLEAN_KEYS:
        if key not in selected:
            continue
        parsed, blocker = _strict_boolean(selected[key], key)
        if blocker:
            blockers.append(blocker)
        elif parsed is not None:
            booleans[key] = parsed
    if booleans.get("OPENCLAW_ALLOW_MAINNET") is True:
        blockers.append("ALLOW_MAINNET_ENABLED")

    data_dir: Path | None = None
    secrets_dir: Path | None = None
    if "OPENCLAW_DATA_DIR" in selected:
        data_dir, blocker = _safe_directory_identity(
            selected["OPENCLAW_DATA_DIR"], "DATA_DIR_UNSAFE"
        )
        if blocker:
            blockers.append(blocker)
    if "OPENCLAW_SECRETS_DIR" in selected:
        secrets_dir, blocker = _safe_directory_identity(
            selected["OPENCLAW_SECRETS_DIR"], "SECRETS_DIR_UNSAFE"
        )
        if blocker:
            blockers.append(blocker)
    endpoint_class: str | None = None
    endpoint_digest: str | None = None
    if secrets_dir is not None:
        endpoint_class, endpoint_digest, blocker = _endpoint_identity(secrets_dir)
        if blocker:
            blockers.append(blocker)

    try:
        pids_after = _engine_pids()
        current_link = os.readlink(PROC_ROOT / str(pid) / "exe")
        current_start_ticks = _process_start_ticks(pid)
        current_digest = _sha256_file(PROC_ROOT / str(pid) / "exe")
        if (
            pids_after != [pid]
            or current_link != process_facts.get("exe_link")
            or current_start_ticks != process_facts.get("process_start_ticks")
            or current_digest != process_facts.get("process_identity_digest")
        ):
            blockers.append("PROCESS_IDENTITY_RACE")
    except (OSError, UnicodeError, ValueError):
        blockers.append("PROCESS_IDENTITY_RACE")
    if secrets_dir is not None:
        endpoint_class_after, endpoint_digest_after, endpoint_blocker = (
            _endpoint_identity(secrets_dir)
        )
        if endpoint_blocker:
            blockers.append(endpoint_blocker)
        elif (
            endpoint_class_after != endpoint_class
            or endpoint_digest_after != endpoint_digest
        ):
            blockers.append("ENDPOINT_METADATA_DRIFT")
    try:
        source_head_after = _git_text("rev-parse", "HEAD")
        source_status_after = _git_text(
            "status", "--porcelain", "--untracked-files=all"
        )
        if source_head_after != source_head:
            blockers.append("SOURCE_HEAD_DRIFT")
        if source_status_after:
            blockers.append("SOURCE_TREE_DRIFT")
    except (OSError, subprocess.CalledProcessError):
        blockers.append("SOURCE_REPOSITORY_DRIFT_UNREADABLE")
    blockers = sorted(set(blockers))
    if blockers:
        return None, blockers

    assert observed is not None
    assert data_dir is not None and secrets_dir is not None
    assert endpoint_class is not None and endpoint_digest is not None
    config_projection = {
        "schema_version": "runtime_environment_config_identity_v1",
        "allow_mainnet": booleans["OPENCLAW_ALLOW_MAINNET"],
        "enable_paper": booleans["OPENCLAW_ENABLE_PAPER"],
        "demo_learning_lane_writer": booleans[
            "OPENCLAW_DEMO_LEARNING_LANE_WRITER"
        ],
        "bounded_probe_adapter_enabled": booleans[
            "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED"
        ],
        "canary_mode": booleans["OPENCLAW_CANARY_MODE"],
        "data_dir_identity_digest": _sha256_bytes(str(data_dir).encode("utf-8")),
        "secrets_dir_identity_digest": _sha256_bytes(
            str(secrets_dir).encode("utf-8")
        ),
        "endpoint_file_identity_digest": endpoint_digest,
    }
    expires = observed + ATTESTATION_TTL
    attestation = build_runtime_environment_attestation(
        phase=phase,
        host=host,
        source_head=source_head,
        config_identity_digest=_sha256_bytes(_canonical_bytes(config_projection)),
        actual_endpoint_class=endpoint_class,
        allow_mainnet=False,
        runtime_mode="live_demo",
        authorization_scope="live_demo_only",
        process_identity_digest=process_facts["process_identity_digest"],
        observed_at=observed.isoformat(),
        expires_at=expires.isoformat(),
    )
    return attestation, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("preflight", "postcheck"))
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--expected-source-head", required=True)
    args = parser.parse_args(argv)
    attestation, blockers = probe_runtime_environment(
        phase=args.phase,
        expected_host=args.expected_host,
        expected_source_head=args.expected_source_head,
        now=datetime.now().astimezone().isoformat(),
    )
    result = {
        "schema_version": "runtime_environment_probe_result_v1",
        "status": "PASS" if attestation is not None else "BLOCKED",
        "blocker_codes": blockers,
        "attestation": attestation,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if attestation is not None else 4


if __name__ == "__main__":
    raise SystemExit(main())
