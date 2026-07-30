#!/usr/bin/env python3
"""Pure central semantics for the signed S2.5 recovery host-capture ABI.

The leaf validates a caller-supplied observation only.  It never captures host
facts, selects a key/profile, performs an effect, or grants production authority.
"""

from __future__ import annotations

import hmac
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import agent_governance_aiml_trusted_host as _trusted_host
from aiml_gate_receipt_schema_core import (
    _canonical_bytes,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
)


HOST_CAPTURE_SCHEMA_VERSION = "s2_5_recovery_host_capture_v1"
HOST_CAPTURE_PROFILE = "DISPOSABLE_SYSTEMD_RECOVERY_HOST"
RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY = (
    "aiml-s2-5-recovery-host-capture-attestor-v1"
)
RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE = (
    "arcane-equilibrium-aiml-s2-5-recovery-host-capture"
)
RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH = Path(
    "/etc/arcane-equilibrium/trust/s2-5-recovery-host-capture.pub"
)
RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT = (
    "SHA256:2u6gW8YQXyZc0nR1mM3vA4bB5cC6dD7eE8fF9gG0hHI"
)
MAX_HOST_CAPTURE_TTL = timedelta(minutes=15)
_SIGNED_BINDING_KEYS = frozenset({
    "schema_version", "capture_profile", "source_head", "stable_host_facts",
    "host_identity", "node_identity", "process_identity", "boot_manager_facts",
    "observed_at", "expires_at", "side_effect_class", "production_effect",
    "production_authority", "target_class",
})
_HOST_CAPTURE_KEYS = _SIGNED_BINDING_KEYS | frozenset({
    "signer_identity", "signer_fingerprint", "signature_namespace",
    "signed_binding", "sshsig_armored", "self_digest",
})
_STABLE_HOST_FACT_KEYS = frozenset({
    "machine_id_digest", "node_name", "os_id", "architecture",
})
_NODE_KEYS = frozenset({"node_id", "role", "permission", "key_identity"})
_PROCESS_KEYS = frozenset({"uid", "cgroup"})
_BOOT_MANAGER_KEYS = frozenset({
    "boot_id", "manager", "manager_root", "unit_name", "canonical_state_root",
})


def _exact(value: Any, keys: frozenset[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    actual = set(value)
    if actual == keys:
        return []
    return [
        f"{label} keys are not closed: missing={sorted(keys - actual)}, "
        f"extra={sorted(actual - keys)}"
    ]


def derive_s2_5_recovery_host_identity(capture: dict[str, Any]) -> str:
    """Derive the restart-stable host identity from signed stable host facts."""

    stable = capture.get("stable_host_facts")
    digest = canonical_digest({
        "schema_version": "s2_5_recovery_stable_host_identity_v1",
        "stable_host_facts": stable,
    })
    return "host:" + digest.split(":", 1)[1]


def recovery_host_capture_signed_bytes(capture: dict[str, Any]) -> bytes:
    """Canonical bytes authenticated by the fixed host-capture profile."""

    return _canonical_bytes(capture["signed_binding"])


def _read_fixed_recovery_host_capture_public_key(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("host-capture trust root is not a regular file")
        if metadata.st_nlink != 1:
            raise ValueError("host-capture trust root must have one hard link")
        if metadata.st_uid not in {0, os.geteuid()}:
            raise ValueError("host-capture trust root owner is not trusted")
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            raise ValueError("host-capture trust root is group/world writable")
        if metadata.st_size < 16 or metadata.st_size > 4096:
            raise ValueError("host-capture trust-root key size is invalid")
        payload = os.read(descriptor, metadata.st_size + 1)
    finally:
        os.close(descriptor)
    try:
        public_key = payload.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ValueError("host-capture trust root is not ASCII") from error
    parts = public_key.split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("host-capture trust root must be ssh-ed25519")
    return " ".join(parts[:2])


def _load_recovery_host_capture_trust_root_public_key() -> str:
    return _read_fixed_recovery_host_capture_public_key(
        RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH
    )


def _signature_errors(capture: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        public_key = _load_recovery_host_capture_trust_root_public_key()
        actual = _trusted_host.ssh_public_key_fingerprint(public_key)
    except (OSError, ValueError) as error:
        return [f"host capture fixed trust root is unavailable or invalid: {error}"]
    expected = RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT
    if not hmac.compare_digest(actual, expected):
        errors.append("host capture fixed trust-root fingerprint mismatch")
    if not hmac.compare_digest(str(capture.get("signer_fingerprint")), expected):
        errors.append("host capture signer fingerprint is invalid")
    signature = str(capture.get("sshsig_armored") or "").encode("ascii", "replace")
    if not _trusted_host._verify_ssh_signature(
        recovery_host_capture_signed_bytes(capture),
        signature,
        public_key=public_key,
        identity=RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY,
        namespace=RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE,
    ):
        errors.append("host capture SSHSIG is invalid")
    return errors


def validate_s2_5_recovery_host_capture(
    capture: Any, *, now: str | datetime | None = None
) -> list[str]:
    """Validate closed shape, derivations, freshness, and fixed-profile SSHSIG."""

    errors = _exact(capture, _HOST_CAPTURE_KEYS, "host capture")
    if not isinstance(capture, dict):
        return errors
    if now is None:
        errors.append("host capture validation requires explicit trusted current time")
    errors.extend(_exact(
        capture.get("signed_binding"), _SIGNED_BINDING_KEYS,
        "host capture signed_binding",
    ))
    errors.extend(_exact(
        capture.get("stable_host_facts"), _STABLE_HOST_FACT_KEYS,
        "host capture stable_host_facts",
    ))
    errors.extend(_exact(
        capture.get("node_identity"), _NODE_KEYS, "host capture node_identity"
    ))
    errors.extend(_exact(
        capture.get("process_identity"), _PROCESS_KEYS,
        "host capture process_identity",
    ))
    errors.extend(_exact(
        capture.get("boot_manager_facts"), _BOOT_MANAGER_KEYS,
        "host capture boot_manager_facts",
    ))
    signed = capture.get("signed_binding")
    if isinstance(signed, dict) and signed != {
        key: capture.get(key) for key in _SIGNED_BINDING_KEYS
    }:
        errors.append("host capture signed_binding differs from the exact capture")
    if capture.get("host_identity") != derive_s2_5_recovery_host_identity(capture):
        errors.append("host capture host_identity does not derive from stable host facts")
    node = capture.get("node_identity")
    if isinstance(node, dict) and (
        node.get("role") != "HOST_ATTESTOR"
        or node.get("permission") != "read_only"
    ):
        errors.append("host capture node must be the read-only HOST_ATTESTOR")
    manager = capture.get("boot_manager_facts")
    if isinstance(manager, dict) and (
        manager.get("manager") != "systemd"
        or manager.get("manager_root") != "/run/systemd/system"
        or manager.get("unit_name")
        != "arcane-equilibrium-aiml-engine-scanner.service"
    ):
        errors.append("host capture manager facts are not the fixed systemd target")
    if capture.get("capture_profile") != HOST_CAPTURE_PROFILE:
        errors.append("host capture profile is invalid")
    if capture.get("signer_identity") != RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY:
        errors.append("host capture signer identity is invalid")
    if capture.get("signature_namespace") != (
        RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE
    ):
        errors.append("host capture SSHSIG namespace is invalid")
    if capture.get("side_effect_class") != "DISPOSABLE_TEST":
        errors.append("host capture side_effect_class must be DISPOSABLE_TEST")
    if capture.get("production_effect") is not False:
        errors.append("host capture production_effect must be false")
    if capture.get("production_authority") is not False:
        errors.append("host capture production_authority must be false")
    if capture.get("target_class") != "disposable_systemd":
        errors.append("host capture target_class must be disposable_systemd")
    try:
        observed = _parse_timestamp(str(capture.get("observed_at")))
        expires = _parse_timestamp(str(capture.get("expires_at")))
        if observed >= expires:
            errors.append("host capture observed_at must precede expires_at")
        if expires - observed > MAX_HOST_CAPTURE_TTL:
            errors.append("host capture validity window exceeds 15 minutes")
        if now is not None:
            current = _parse_timestamp(now) if isinstance(now, str) else now
            if not isinstance(current, datetime) or current.tzinfo is None:
                raise ValueError("now must be timezone-aware")
            if current < observed:
                errors.append("host capture observed_at is in the future")
            if current >= expires:
                errors.append("host capture is stale")
    except (TypeError, ValueError) as error:
        errors.append(f"host capture timestamps are invalid: {error}")
    if capture.get("self_digest") != artifact_self_digest(capture):
        errors.append("host capture self_digest does not bind the canonical artifact")
    if isinstance(signed, dict):
        errors.extend(_signature_errors(capture))
    return errors
