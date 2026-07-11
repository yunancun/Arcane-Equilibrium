"""Small cross-record invariants for effect, preflight, and postcheck evidence."""

from __future__ import annotations

from typing import Any


def deploy_evidence_identity_errors(
    receipt_id: str, receipt_wrapper: dict[str, Any], receipt: dict[str, Any],
    preflight: dict[str, Any], postcheck: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if len({receipt_id, preflight.get("id"), postcheck.get("id")}) != 3:
        errors.append("effect receipt, OPS preflight, and OPS postcheck must be distinct evidence")
    if len({receipt_wrapper.get("digest"), preflight.get("digest"), postcheck.get("digest")}) != 3:
        errors.append("effect receipt, OPS preflight, and OPS postcheck must have distinct content digests")
    for item, label in ((preflight, "preflight"), (postcheck, "postcheck")):
        if item.get("host") != receipt.get("target_host") or item.get("environment") != receipt.get("target_environment"):
            errors.append(f"OPS {label} host/environment does not match effect receipt")
    return errors
