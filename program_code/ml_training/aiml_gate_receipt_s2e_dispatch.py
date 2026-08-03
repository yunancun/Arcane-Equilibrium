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
    if schema_version == "s2e_durability_anchor_attestation_v1":
        return [
            "s2e durability anchor attestation "
            "EXTERNAL_VERIFICATION_PENDING: exact append-only head/generation, "
            "off-host latest-generation readback and fixed-root anchor SSHSIG "
            "are required"
        ]
    if schema_version == "s2e_durability_anchor_floor_v1":
        # floor 只有從 git commit 位元組讀出、且通過整條檔案歷史檢查時才有意義;
        # 對 caller 遞來的單份 floor 物件,中央驗證器恆回 typed pending。
        return [
            "s2e durability anchor floor EXTERNAL_VERIFICATION_PENDING: the "
            "committed floor must be read from its own Git history with an "
            "ancestor chain and a strictly increasing generation"
        ]
    if schema_version == "s2e_predecessor_registry_attestation_v1":
        return [
            "s2e predecessor registry attestation "
            "EXTERNAL_VERIFICATION_PENDING: exact candidate/predecessor/ledger "
            "context and fixed-root registry SSHSIG are required"
        ]
    return []
