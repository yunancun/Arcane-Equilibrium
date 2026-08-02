"""S2E-specific branch for the central AI/ML artifact validator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from aiml_gate_receipt_s2e_launch import (
    validate_receipt_carrier_attestation,
    validate_s2e_launch_genesis_receipt,
    validate_s2e_launch_wave_receipt,
)


def s2e_launch_artifact_errors(
    artifact: Any,
    *,
    schema_version: str,
    repo_root: Path,
    now: str | datetime | None,
) -> list[str]:
    """Apply the S2E-specific branch of the central artifact validator."""

    if schema_version == "s2e_launch_genesis_receipt_v1":
        return validate_s2e_launch_genesis_receipt(
            artifact, repo_root=repo_root
        )
    if schema_version == "s2e_launch_wave_receipt_v1":
        return validate_s2e_launch_wave_receipt(artifact, repo_root=repo_root)
    if schema_version == "receipt_carrier_attestation_v1":
        return validate_receipt_carrier_attestation(
            artifact, payload_receipt=None, repo_root=repo_root, now=now
        )
    if schema_version == "s2e_launch_acceptance_review_bundle_v1":
        return [
            "s2e acceptance review bundle EXTERNAL_VERIFICATION_PENDING: exact "
            "candidate, governed capture, fixed-root SSHSIG, and external WORM "
            "evidence are required"
        ]
    if schema_version == "s2e_launch_consumption_bootstrap_authority_v1":
        return [
            "s2e consumption bootstrap authority "
            "EXTERNAL_VERIFICATION_PENDING: exact candidate, predecessor "
            "chain, acceptance review, fixed-root SSHSIG, and trusted "
            "single-use registry evidence are required"
        ]
    return []
