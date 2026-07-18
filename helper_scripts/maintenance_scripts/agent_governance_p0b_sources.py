"""Fail-closed repository-byte bindings for P0-B runtime components."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


COMMON_COMPONENT_CLAIMS = {
    "p0b_adapter_source": (
        "helper_scripts/maintenance_scripts/p0b_alr_current_head_rollforward_v1.py"
    ),
    "p0b_adapter_tests": "tests/helper_scripts/test_p0b_alr_current_head_rollforward_v1.py",
    "p0b_base_adapter_source": (
        "helper_scripts/maintenance_scripts/p0a_generation_pin_apply_v1.py"
    ),
    "p0b_generation_apply_source": (
        "helper_scripts/maintenance_scripts/p0b_generation_pin_apply_current_head_v1.py"
    ),
}
PHASE_COMPONENT_CLAIMS = {
    "stage": {
        "p0b_private_bundle_stager_source": (
            "helper_scripts/maintenance_scripts/p0b_psycopg_private_bundle_stage_v1.py"
        ),
        "p0b_private_bundle_stager_tests": (
            "tests/helper_scripts/test_p0b_psycopg_private_bundle_stage_v1.py"
        ),
    },
    "cutover": {
        "p0b_observer_source": (
            "helper_scripts/maintenance_scripts/"
            "p0b_alr_current_head_two_cycle_observer_v2.py"
        ),
        "p0b_observer_tests": (
            "tests/helper_scripts/test_p0b_alr_current_head_two_cycle_observer_v2.py"
        ),
        "p0b_observer_dependency_source": (
            "helper_scripts/maintenance_scripts/p0b_alr_two_natural_cycle_observer_v1.py"
        ),
    },
}


def component_claim_paths(phase: str) -> dict[str, str]:
    if phase not in PHASE_COMPONENT_CLAIMS:
        raise ValueError(f"invalid P0-B source phase: {phase}")
    return {**COMMON_COMPONENT_CLAIMS, **PHASE_COMPONENT_CLAIMS[phase]}


def _identity(observed: os.stat_result) -> tuple[int, ...]:
    return (
        observed.st_dev, observed.st_ino, observed.st_uid, observed.st_gid,
        observed.st_mode, observed.st_nlink, observed.st_size,
        observed.st_mtime_ns, observed.st_ctime_ns,
    )


def _secure_digest(path: Path) -> str:
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise OSError("component must be a single-link regular file")
        hasher = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            hasher.update(chunk)
        after = os.fstat(descriptor)
        path_after = os.stat(path, follow_symlinks=False)
        if _identity(before) != _identity(after) or _identity(after) != _identity(
            path_after
        ):
            raise OSError("component identity changed while hashing")
        return "sha256:" + hasher.hexdigest()
    finally:
        os.close(descriptor)


def component_claim_digests(root: Path, phase: str) -> dict[str, str]:
    """Hash exact checked-in bytes; missing/non-files fail closed."""

    digests: dict[str, str] = {}
    for claim, relative in component_claim_paths(phase).items():
        path = root / relative
        try:
            digests[claim] = _secure_digest(path)
        except OSError as error:
            raise OSError(f"{relative}: {error}") from error
    return digests


def validate_component_claims(
    claims: dict[str, str], *, root: Path, phase: str
) -> list[str]:
    try:
        expected = component_claim_digests(root, phase)
    except (FileNotFoundError, OSError, ValueError) as error:
        return [f"P0-B component source inventory unavailable: {error}"]
    return [
        f"P0-B {claim} does not match exact repository bytes"
        for claim, digest in expected.items()
        if claims.get(claim) != digest
    ]
