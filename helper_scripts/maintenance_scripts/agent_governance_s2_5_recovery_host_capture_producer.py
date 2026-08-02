#!/usr/bin/env python3
"""Produce one fixed-profile, capability-signed S2.5 host capture.

The public entrypoint accepts no identity, path, key, clock, unit, cgroup, UID,
or state-root input.  The separately installed signer capability is responsible
for admitting only the fixed recovery-runner execution context before signing.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import agent_governance_s2_5_disposable_profile as profile
import agent_governance_s2_host_kernel as host_kernel
from aiml_gate_receipt_s2_5_host_capture import (
    HOST_CAPTURE_ADMISSION_CLASS,
    HOST_CAPTURE_ADMISSION_SCHEMA_VERSION,
    HOST_CAPTURE_NODE_ID,
    HOST_CAPTURE_PROFILE,
    HOST_CAPTURE_SCHEMA_VERSION,
    HOST_CAPTURE_SIGNER_CAPABILITY_PATH,
    HOST_CAPTURE_SIGNER_CAPABILITY_PROTOCOL,
    RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE,
    RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY,
    RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT,
    derive_s2_5_recovery_host_identity,
    recovery_host_capture_signed_bytes,
    validate_s2_5_recovery_host_capture,
)
from aiml_gate_receipt_schema_core import artifact_self_digest


MACHINE_ID_PATH = Path("/etc/machine-id")
OS_RELEASE_PATH = Path("/etc/os-release")
BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
SELF_CGROUP_PATH = Path("/proc/self/cgroup")
CAPTURE_TTL = timedelta(minutes=5)
MAX_FACT_BYTES = 64 * 1024


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_fixed_fact(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"{label} must be one regular file")
        if metadata.st_size > MAX_FACT_BYTES:
            raise ValueError(f"{label} size is invalid")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FACT_BYTES:
                raise ValueError(f"{label} exceeds the size limit")
            chunks.append(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if not raw:
        raise ValueError(f"{label} is empty")
    return raw


def _git_source_head() -> str:
    kernel = host_kernel.HostExecutionKernel(
        session=host_kernel.SESSION_S2_5_RECOVERY_HOST_CAPTURE
    )
    try:
        for argv in host_kernel.RECOVERY_HOST_CAPTURE_CLEAN_ARGV:
            kernel.run(argv)
        head = kernel.run(host_kernel.RECOVERY_HOST_CAPTURE_HEAD_ARGV).strip()
    except host_kernel.S2HostKernelError as error:
        raise ValueError(
            "host capture source checkout is unavailable or has tracked changes"
        ) from error
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise ValueError("host capture source head is invalid")
    return head


def _os_id() -> str:
    raw = _read_fixed_fact(OS_RELEASE_PATH, label="os-release")
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("ID="):
            value = line[3:].strip().strip('"').strip("'")
            if value and value.replace("_", "").replace("-", "").isalnum():
                return value
    raise ValueError("os-release ID is absent or invalid")


def _unified_cgroup() -> str:
    raw = _read_fixed_fact(SELF_CGROUP_PATH, label="self cgroup")
    matches = [
        line.split("::", 1)[1]
        for line in raw.decode("utf-8").splitlines()
        if line.startswith("0::")
    ]
    if len(matches) != 1 or not matches[0].startswith("/"):
        raise ValueError("host capture requires one unified cgroup path")
    return matches[0]


def _admission_provenance() -> dict[str, Any]:
    return {
        "schema_version": HOST_CAPTURE_ADMISSION_SCHEMA_VERSION,
        "admission_class": HOST_CAPTURE_ADMISSION_CLASS,
        "capability_protocol": HOST_CAPTURE_SIGNER_CAPABILITY_PROTOCOL,
        "capability_path": HOST_CAPTURE_SIGNER_CAPABILITY_PATH,
        "node_id": HOST_CAPTURE_NODE_ID,
        "role": "HOST_ATTESTOR",
        "permission": "read_only",
        "uid": profile.PROFILE_UID,
        "cgroup": profile.RECOVERY_RUNNER_CGROUP,
        "unit_name": profile.RECOVERY_RUNNER_UNIT,
        "canonical_state_root": profile.DISPOSABLE_STATE_ROOT,
        "signer_identity": RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY,
        "signer_fingerprint": RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT,
    }


def _invoke_fixed_signer_capability(payload: bytes) -> str:
    path = Path(HOST_CAPTURE_SIGNER_CAPABILITY_PATH)
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or not stat.S_IMODE(metadata.st_mode) & 0o111
    ):
        raise ValueError("fixed host-capture signer capability is not trusted")
    try:
        return host_kernel.HostExecutionKernel(
            session=host_kernel.SESSION_S2_5_RECOVERY_HOST_CAPTURE
        ).sign_recovery_host_capture(payload)
    except host_kernel.S2HostKernelError as error:
        raise ValueError("fixed host-capture signer capability denied the request") from error


def capture_s2_5_recovery_host() -> dict[str, Any]:
    """Capture, sign, and validate the one code-owned disposable profile."""

    observed = datetime.now(timezone.utc)
    uid = os.geteuid()
    cgroup = _unified_cgroup()
    if uid != profile.PROFILE_UID or cgroup != profile.RECOVERY_RUNNER_CGROUP:
        raise ValueError("host capture is outside the fixed recovery-runner admission")
    stable_facts = {
        "machine_id_digest": _sha256(
            _read_fixed_fact(MACHINE_ID_PATH, label="machine-id").strip()
        ),
        "node_name": os.uname().nodename,
        "os_id": _os_id(),
        "architecture": platform.machine(),
    }
    capture: dict[str, Any] = {
        "schema_version": HOST_CAPTURE_SCHEMA_VERSION,
        "capture_profile": HOST_CAPTURE_PROFILE,
        "source_head": _git_source_head(),
        "stable_host_facts": stable_facts,
        "host_identity": "",
        "node_identity": {
            "node_id": HOST_CAPTURE_NODE_ID,
            "role": "HOST_ATTESTOR",
            "permission": "read_only",
            "key_identity": RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY,
        },
        "process_identity": {"uid": uid, "cgroup": cgroup},
        "boot_manager_facts": {
            "boot_id": _read_fixed_fact(BOOT_ID_PATH, label="boot-id")
            .decode("ascii")
            .strip(),
            "manager": "systemd",
            "manager_root": profile.USER_MANAGER_ROOT,
            "unit_name": profile.RECOVERY_RUNNER_UNIT,
            "canonical_state_root": profile.DISPOSABLE_STATE_ROOT,
        },
        "admission_provenance": _admission_provenance(),
        "observed_at": observed.isoformat(),
        "expires_at": (observed + CAPTURE_TTL).isoformat(),
        "side_effect_class": "DISPOSABLE_TEST",
        "production_effect": False,
        "production_authority": False,
        "target_class": profile.PROFILE_TARGET_CLASS,
    }
    capture["host_identity"] = derive_s2_5_recovery_host_identity(capture)
    capture["signer_identity"] = RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY
    capture["signer_fingerprint"] = RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT
    capture["signature_namespace"] = RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE
    signed_keys = {
        "schema_version", "capture_profile", "source_head", "stable_host_facts",
        "host_identity", "node_identity", "process_identity", "boot_manager_facts",
        "admission_provenance", "observed_at", "expires_at", "side_effect_class",
        "production_effect", "production_authority", "target_class",
    }
    capture["signed_binding"] = {
        key: capture[key] for key in signed_keys
    }
    capture["sshsig_armored"] = _invoke_fixed_signer_capability(
        recovery_host_capture_signed_bytes(capture)
    )
    capture["self_digest"] = artifact_self_digest(capture)
    errors = validate_s2_5_recovery_host_capture(capture, now=observed)
    if errors:
        raise ValueError("produced host capture is invalid: " + "; ".join(errors))
    return capture


def main(argv: list[str] | None = None) -> int:
    if list(sys.argv[1:] if argv is None else argv):
        raise SystemExit("host-capture producer accepts no arguments")
    artifact = capture_s2_5_recovery_host()
    print(json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
