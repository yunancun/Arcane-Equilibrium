"""Exact closure-side validation for the successful P0-B observer-v2 receipt."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_schema import schema_subset_errors


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / ".codex/schemas/p0b_alr_rollforward_effect_result_v1.schema.json"
)


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def validate_observer_result(
    observer: Any,
    *,
    receipt: dict[str, Any],
    provisional: dict[str, Any],
) -> list[str]:
    """Validate exact observer bytes and one-way lineage against admitted claims."""

    if not isinstance(observer, dict):
        return ["P0-B observer result must be an object"]
    schema = _schema()
    errors = [
        f"P0-B observer result schema violation: {error}"
        for error in schema_subset_errors(
            observer, schema["$defs"]["observerResult"], schema
        )
    ]
    claims = receipt.get("claim_bindings", {})
    lineage = observer.get("lineage", {})
    target_head = receipt.get("source_head")
    active_identity = provisional.get("active_identity")
    exact = {
        "target_head": (observer.get("target_head"), target_head),
        "phase2_identity": (lineage.get("phase2_identity"), active_identity),
        "runtime_identity": (
            observer.get("runtime_and_cycles", {}).get("runtime_identity"),
            active_identity,
        ),
        "cutover_authorization_digest": (
            lineage.get("cutover_authorization_digest"),
            provisional.get("cutover_authorization_digest"),
        ),
        "protected_baseline_digest": (
            lineage.get("protected_baseline_digest"),
            claims.get("p0b_protected_runtime_baseline"),
        ),
        "phase1_closure_digest": (
            lineage.get("phase1_closure_digest"), claims.get("p0b_phase1_closure")
        ),
        "sealed_lineage_bundle_digest": (
            lineage.get("sealed_lineage_bundle_digest"),
            claims.get("p0b_sealed_lineage_bundle"),
        ),
        "target_source_attestation_digest": (
            lineage.get("target_source_attestation_digest"),
            claims.get("p0b_target_source_attestation"),
        ),
        "cutover_runtime_bindings_artifact_digest": (
            lineage.get("cutover_runtime_bindings_artifact_digest"),
            claims.get("p0b_phase_runtime_bindings"),
        ),
        "private_deps_manifest_sha256": (
            lineage.get("private_deps_manifest_sha256"),
            provisional.get("private_deps_manifest_sha256"),
        ),
        "live_board_sha256": (
            lineage.get("live_board_sha256"),
            provisional.get("live_board", {}).get("sha256"),
        ),
        "private_deps_receipt_sha256": (
            lineage.get("private_deps_receipt_sha256"),
            provisional.get("private_deps_receipt", {}).get("sha256"),
        ),
    }
    for name, (observed, expected) in exact.items():
        if observed != expected:
            errors.append(f"P0-B observer {name} lineage mismatch")
    prefixed_raw = {
        "observer_source_sha256": "p0b_observer_source",
        "phase1_receipt_sha256": "p0b_phase1_receipt",
        "private_deps_receipt_sha256": "p0b_private_bundle_receipt",
    }
    for field, claim in prefixed_raw.items():
        if "sha256:" + str(lineage.get(field, "")) != claims.get(claim):
            errors.append(f"P0-B observer {field} is not claim-bound")
    if "sha256:" + str(lineage.get("provisional_cutover_sha256", "")) != (
        _canonical_digest(provisional)
    ):
        errors.append("P0-B observer provisional cutover bytes mismatch")
    runtime = observer.get("runtime_and_cycles", {})
    startup = observer.get("startup_reconciliation", {})
    if runtime.get("session_id") != startup.get("session_id") or runtime.get(
        "session_started_at_utc"
    ) != startup.get("session_started_at_utc"):
        errors.append("P0-B observer session identity is not exact across surfaces")
    private = observer.get("private_dependencies", {})
    if private.get("receipt_sha256") != lineage.get(
        "private_deps_receipt_sha256"
    ) or private.get("manifest_sha256") != lineage.get("private_deps_manifest_sha256"):
        errors.append("P0-B observer private dependency evidence is not lineage-bound")
    try:
        if _parse_time(str(observer.get("observed_at_utc", ""))) < _parse_time(
            str(observer.get("observer_not_before_utc", ""))
        ):
            errors.append("P0-B observer completed before its not-before boundary")
    except (TypeError, ValueError):
        errors.append("P0-B observer timestamps are invalid")
    return errors
