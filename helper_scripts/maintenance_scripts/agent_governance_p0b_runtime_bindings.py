"""Exact semantic validation for pre-admission P0-B runtime binding artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_schema import schema_subset_errors


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / ".codex/schemas/phase_runtime_bindings_v1.schema.json"
)
RUNTIME_ROOT = Path(
    "/home/ncyu/BybitOpenClaw/var/openclaw/runtime_recovery/"
    "alr-current-head-rollforward"
)
PRIVATE_DESTINATION = "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps"
AUTH_METADATA_PATHS = {
    "/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json",
    "/home/ncyu/BybitOpenClaw/var/openclaw/"
    "runtime_recovery_demo_read_secrets_0a4d38ee/live/authorization.json",
}
SECTIONS = {
    "source_attestation": "p0b_runtime_source_binding",
    "protected_runtime_baseline": "p0b_runtime_protected_binding",
    "phase_paths": "p0b_runtime_paths_binding",
    "inventories": "p0b_runtime_inventories_binding",
    "lineage": "p0b_runtime_lineage_binding",
}


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _digest(value: Any) -> str:
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


def _expected_paths(artifact: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    intent_id = intent.get("intent_id")
    if intent.get("phase") == "stage":
        staging_root = RUNTIME_ROOT / "staging" / str(intent_id)
        return {
            "staging_root": str(staging_root),
            "cron_destination": str(staging_root / "cron-scratch"),
            "sealed_destination": str(staging_root / "sealed"),
            "publisher_receipt_path": str(staging_root / "staging-publisher-result.json"),
            "private_deps_receipt_path": str(staging_root / "private-deps-receipt.json"),
            "private_deps_destination": PRIVATE_DESTINATION,
            "phase1_receipt_path": str(RUNTIME_ROOT / f"{intent_id}.phase1.json"),
            "phase1_closure_path": str(
                RUNTIME_ROOT / f"{intent_id}.phase1.closure.json"
            ),
        }
    lineage = artifact.get("lineage", {})
    return {
        "phase1_receipt_path": lineage.get("phase1_receipt", {}).get("path"),
        "phase1_closure_path": lineage.get("phase1_closure", {}).get("path"),
        "live_destination": "/home/ncyu/.local/share/openclaw/alr-candidate-evidence",
        "provisional_cutover_path": str(
            RUNTIME_ROOT / f"{intent_id}.phase2.provisional.json"
        ),
        "observer_input_path": str(
            RUNTIME_ROOT / f"{intent_id}.phase2.observer-input.json"
        ),
    }


def validate_phase_runtime_bindings(
    artifact: Any, *, intent: dict[str, Any]
) -> list[str]:
    """Validate exact schema, canonical digests, claims, old state, and paths."""

    if not isinstance(artifact, dict):
        return ["P0-B phase runtime bindings must be an object"]
    schema = _schema()
    errors = [
        f"P0-B phase runtime bindings schema violation: {error}"
        for error in schema_subset_errors(artifact, schema, schema)
    ]
    artifact_digest = _digest({
        key: value for key, value in artifact.items() if key != "artifact_digest"
    })
    expected_top = {
        "phase": intent.get("phase"),
        "intent_id": intent.get("intent_id"),
        "target_head": intent.get("expected_source_head"),
        "artifact_digest": artifact_digest,
    }
    for field, expected in expected_top.items():
        if artifact.get(field) != expected:
            errors.append(f"P0-B phase runtime bindings {field} mismatch")
    claims = intent.get("claim_bindings", {})
    if artifact_digest != claims.get("p0b_phase_runtime_bindings"):
        errors.append("P0-B phase runtime bindings artifact is not claim-bound")
    section_claims = artifact.get("section_claims", {})
    for section, claim in SECTIONS.items():
        section_digest = _digest(artifact.get(section))
        if section_claims.get(section) != {"claim": claim, "digest": section_digest}:
            errors.append(f"P0-B {section} section_claim is not canonical")
        if claims.get(claim) != section_digest:
            errors.append(f"P0-B {section} is not exact claim-bound")

    source = artifact.get("source_attestation", {})
    source_snapshot = source.get("source", {})
    target_head = intent.get("expected_source_head")
    if any(source_snapshot.get(field) != target_head for field in (
        "head", "origin_main", "remote_origin_main"
    )):
        errors.append("P0-B runtime source snapshot is not exact fresh target head")
    if source.get("source_tree_digest") != _digest(source.get("execution_tree")):
        errors.append("P0-B runtime source tree digest mismatch")

    protected = artifact.get("protected_runtime_baseline", {})
    canonical_protected = {
        "protected_digest": _digest(protected.get("protected")),
        "pin_consumer_inventory_digest": _digest(
            protected.get("pin_consumer_inventory")
        ),
        "runtime_identity_digest": _digest(protected.get("runtime_identity")),
    }
    for field, expected in canonical_protected.items():
        if protected.get(field) != expected:
            errors.append(f"P0-B protected runtime {field} mismatch")
    runtime_identity = protected.get("runtime_identity", {})
    baseline = protected.get("service_baseline", {})
    old_head = intent.get("expected_old_runtime_source_head")
    if runtime_identity.get("source_head") != old_head:
        errors.append("P0-B protected runtime old source head mismatch")
    if any(baseline.get(field) != old_head for field in ("unit_head", "pin_head")):
        errors.append("P0-B protected unit/pin head mismatch")
    if "sha256:" + str(baseline.get("pin_sha256", "")) != intent.get(
        "expected_old_pin_digest"
    ):
        errors.append("P0-B protected old pin digest mismatch")
    expected_intent_digests = {
        "source_tree_digest": source.get("source_tree_digest"),
        "pin_consumer_inventory_digest": protected.get(
            "pin_consumer_inventory_digest"
        ),
        "runtime_identity_digest": protected.get("runtime_identity_digest"),
    }
    for suffix, observed in expected_intent_digests.items():
        if intent.get(f"expected_{suffix}") != observed:
            errors.append(f"P0-B intent expected_{suffix} mismatch")

    inventories = artifact.get("inventories", {})
    for name in (
        "live_inventory", "completion_inventory", "producer_inventory",
        "ledger_inventory", "lane_effective_config",
    ):
        if inventories.get(f"{name}_digest") != _digest(inventories.get(name)):
            errors.append(f"P0-B {name} canonical digest mismatch")
    auth_metadata = protected.get("protected", {}).get("auth_metadata", [])
    auth_paths = [
        item.get("path") for item in auth_metadata if isinstance(item, dict)
    ] if isinstance(auth_metadata, list) else []
    if len(auth_paths) != 2 or set(auth_paths) != AUTH_METADATA_PATHS:
        errors.append("P0-B protected auth metadata path inventory is not exact")

    paths = artifact.get("phase_paths", {})
    if paths != _expected_paths(artifact, intent):
        errors.append("P0-B phase runtime path values are not exact")
    try:
        observed = _parse_time(str(artifact.get("observed_at", "")))
        expiry = _parse_time(str(artifact.get("expires_at", "")))
        if not observed < expiry or expiry - observed > timedelta(minutes=15):
            errors.append("P0-B phase runtime bindings TTL exceeds fifteen minutes")
    except (TypeError, ValueError):
        errors.append("P0-B phase runtime binding timestamps are invalid")
    return errors
