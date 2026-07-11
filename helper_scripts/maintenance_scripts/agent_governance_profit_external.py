"""Trusted public-web capture lineage for the profit EXT probe."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from typing import Any

from agent_governance_capture import PLATFORM_OR_EXTERNAL_ATTESTED


EXT_CAPTURE_DEBT = {
    "kind": "external_capture",
    "id": "EXT",
    "owner": "QC",
    "reason": "no trusted opened-public-URL capture inventory",
}
MAX_EXTERNAL_TTL = timedelta(days=30)


def external_inventory_digest(items: dict[str, str]) -> str:
    raw = json.dumps(
        items, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _sources(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result: list[dict[str, Any]] = []
    for opportunity in payload.get("opportunities", []):
        if not isinstance(opportunity, dict):
            continue
        result.extend(
            source for source in opportunity.get("sources", [])
            if isinstance(source, dict)
        )
    return result


def validate_ext_capture_lineage(
    payload: Any,
    *,
    captures: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    adjudicated_at: Any,
    coverage_debt: list[dict[str, Any]],
    claim_inputs: dict[str, str] | None = None,
) -> tuple[list[str], bool]:
    """Return errors and whether every EXT source has trusted fresh capture lineage."""

    errors: list[str] = []
    sources = _sources(payload)
    adjudicated = _time(adjudicated_at)
    trusted_ids = set(captures.get("external_policy_attested", set())) | set(
        captures.get("outcome_attested", set())
    )
    external_inventory = captures.get("external_evidence", {})
    valid_refs: set[str] = set()
    for index, source in enumerate(sources):
        label = f"profit diagnosis EXT source[{index}]"
        capture_ref = source.get("capture_ref")
        wrapper = evidence_by_id.get(str(capture_ref))
        artifact = external_inventory.get(str(capture_ref))
        if capture_ref not in trusted_ids or not isinstance(artifact, dict):
            errors.append(
                f"{label} capture_ref does not resolve to trusted external capture inventory"
            )
            continue
        if (
            artifact.get("trust_tier") != PLATFORM_OR_EXTERNAL_ATTESTED
            or artifact.get("schema_version") != "external_evidence_capture_v1"
        ):
            errors.append(f"{label} capture trust tier/record shape is invalid")
            continue
        observed = _time(artifact.get("observed_at"))
        expires = _time(artifact.get("expires_at"))
        if (
            adjudicated is None or observed is None or expires is None
            or observed > adjudicated or adjudicated >= expires
            or expires - observed > MAX_EXTERNAL_TTL
        ):
            errors.append(f"{label} capture observed_at/expiry TTL is invalid")
            continue
        if (
            source.get("url") != artifact.get("url")
            or source.get("content_digest") != artifact.get("content_digest")
            or source.get("opened_at") != artifact.get("observed_at")
            or source.get("citation_ref") != artifact.get("citation_ref")
            or source.get("claim_excerpt") != artifact.get("excerpt")
        ):
            errors.append(
                f"{label} URL/content/time/citation/excerpt differs from capture"
            )
            continue
        if (
            not isinstance(wrapper, dict)
            or wrapper.get("kind") != "external_evidence_capture_v1"
            or wrapper.get("digest") != artifact.get("record_digest")
            or wrapper.get("observed_at") != artifact.get("observed_at")
            or wrapper.get("expiry") != artifact.get("expires_at")
        ):
            errors.append(f"{label} evidence wrapper does not bind capture/TTL")
            continue
        valid_refs.add(str(capture_ref))

    ready = bool(sources) and len(valid_refs) == len(sources) and not errors
    if ready:
        inventory = {
            ref: str(evidence_by_id[ref].get("digest")) for ref in sorted(valid_refs)
        }
        expected_inventory_digest = external_inventory_digest(inventory)
        if not isinstance(claim_inputs, dict) or claim_inputs.get(
            "public_web_capture_inventory"
        ) != expected_inventory_digest:
            errors.append(
                "profit diagnosis EXT capture inventory is not hash-bound by claim_inputs"
            )
            ready = False
    debt_present = EXT_CAPTURE_DEBT in coverage_debt
    if not ready and not debt_present:
        errors.append("profit diagnosis EXT lacks exact trusted external-capture debt")
    if ready and debt_present:
        errors.append("profit diagnosis EXT carries stale external-capture debt")
    return errors, ready
