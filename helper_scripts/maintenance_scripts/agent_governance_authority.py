"""Typed authority claim integrity, freshness, and conflict resolution."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any

from agent_governance_registry import load_registry


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CLAIM_FIELDS = {
    "class", "subject", "value", "source", "source_ref", "digest", "claim_digest",
    "observed_at", "scope", "strength", "expiry",
}
EPHEMERAL_CLASSES = {
    "active_work_state", "runtime_observation", "external_policy", "claim_evidence",
}
EPHEMERAL_MAX_TTL = {
    "active_work_state": timedelta(hours=4),
    "runtime_observation": timedelta(minutes=15),
    "external_policy": timedelta(days=30),
    "claim_evidence": timedelta(hours=4),
}
STRENGTH_RANK = {"asserted": 0, "derived": 1, "direct": 2}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def authority_claim_digest(claim: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in claim.items() if key != "claim_digest"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def build_authority_claim(
    *,
    authority_class: str,
    subject: str,
    value: Any,
    source: str,
    source_ref: str,
    source_digest: str,
    observed_at: str,
    scope: str,
    strength: str,
    expiry: str | None,
) -> dict[str, Any]:
    claim = {
        "class": authority_class,
        "subject": subject,
        "value": value,
        "source": source,
        "source_ref": source_ref,
        "digest": source_digest,
        "observed_at": observed_at,
        "scope": scope,
        "strength": strength,
        "expiry": expiry,
    }
    claim["claim_digest"] = authority_claim_digest(claim)
    return claim


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def validate_authority_claim(
    claim: Any,
    *,
    adjudicated_at: str | None = None,
) -> list[str]:
    if not isinstance(claim, dict) or set(claim) != CLAIM_FIELDS:
        return ["authority claim fields are invalid"]
    errors: list[str] = []
    classes = set(load_registry()["authority_classes"])
    authority_class = claim.get("class")
    if not isinstance(authority_class, str) or authority_class not in classes:
        errors.append("authority class is invalid")
    for field in ("subject", "source", "source_ref", "scope"):
        if not isinstance(claim.get(field), str) or not claim.get(field, "").strip():
            errors.append(f"authority {field} is empty")
    strength = claim.get("strength")
    if not isinstance(strength, str) or strength not in STRENGTH_RANK:
        errors.append("authority strength is invalid")
    if not DIGEST_RE.fullmatch(str(claim.get("digest", ""))):
        errors.append("authority source digest is invalid")
    try:
        expected_claim_digest = authority_claim_digest(claim)
    except (TypeError, ValueError):
        expected_claim_digest = None
        errors.append("authority claim value is not canonical JSON")
    if claim.get("claim_digest") != expected_claim_digest:
        errors.append("authority claim digest is stale or forged")
    try:
        observed = _time(claim.get("observed_at"))
    except (TypeError, ValueError):
        observed = None
        errors.append("authority observed_at is invalid")
    expiry_value = claim.get("expiry")
    expiry: datetime | None = None
    if expiry_value is not None:
        try:
            expiry = _time(expiry_value)
            if observed is not None and expiry <= observed:
                errors.append("authority expiry is not after observation")
            maximum_ttl = EPHEMERAL_MAX_TTL.get(authority_class) if isinstance(authority_class, str) else None
            if observed is not None and maximum_ttl is not None and expiry - observed > maximum_ttl:
                errors.append("authority expiry exceeds the class freshness limit")
        except (TypeError, ValueError):
            errors.append("authority expiry is invalid")
    if isinstance(authority_class, str) and authority_class in EPHEMERAL_CLASSES and expiry is None:
        errors.append("ephemeral authority class requires expiry")
    if adjudicated_at is not None:
        try:
            adjudicated = _time(adjudicated_at)
            if observed is not None and observed > adjudicated:
                errors.append("authority claim is observed after adjudication")
            if expiry is not None and adjudicated >= expiry:
                errors.append("authority claim is stale at adjudication")
        except (TypeError, ValueError):
            errors.append("authority adjudicated_at is invalid")
    return errors


def resolve_authority_claims(
    claims: Any,
    *,
    adjudicated_at: str | None = None,
) -> dict[str, Any]:
    """Resolve within class/subject/scope and expose every cross-class conflict."""

    if not isinstance(claims, list):
        return {
            "schema_version": "authority_decision_v2", "status": "INVALID",
            "gate_verdict": "BLOCKED", "claims": [], "winner": None,
        }
    if not claims:
        return {
            "schema_version": "authority_decision_v2", "status": "MISSING",
            "gate_verdict": "BLOCKED", "claims": [], "winner": None,
        }
    invalid = [
        index for index, claim in enumerate(claims)
        if validate_authority_claim(claim, adjudicated_at=adjudicated_at)
    ]
    if invalid:
        return {
            "schema_version": "authority_decision_v2", "status": "INVALID",
            "gate_verdict": "BLOCKED", "claims": claims, "winner": None,
            "invalid_indexes": invalid,
        }
    subjects = sorted({claim["subject"] for claim in claims})
    if len(subjects) > 1:
        decisions = {
            subject: resolve_authority_claims(
                [claim for claim in claims if claim["subject"] == subject],
                adjudicated_at=adjudicated_at,
            )
            for subject in subjects
        }
        blocked = any(item["gate_verdict"] == "BLOCKED" for item in decisions.values())
        return {
            "schema_version": "authority_decision_v2", "status": "MULTI_SUBJECT",
            "gate_verdict": "BLOCKED" if blocked else "PASS",
            "claims": claims, "winner": None, "decisions": decisions,
        }
    scopes = {claim["scope"] for claim in claims}
    if len(scopes) != 1:
        return {
            "schema_version": "authority_decision_v2", "status": "SCOPE_CONFLICT",
            "gate_verdict": "BLOCKED", "claims": claims, "winner": None,
        }

    by_class: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        by_class.setdefault(claim["class"], []).append(claim)
    selected: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, list[dict[str, Any]]] = {}
    for authority_class, class_claims in by_class.items():
        strongest = max(STRENGTH_RANK[item["strength"]] for item in class_claims)
        strong_claims = [
            item for item in class_claims if STRENGTH_RANK[item["strength"]] == strongest
        ]
        freshest = max(_time(item["observed_at"]) for item in strong_claims)
        finalists = [item for item in strong_claims if _time(item["observed_at"]) == freshest]
        values = {_canonical_bytes(item["value"]) for item in finalists}
        if len(values) != 1:
            conflicts[authority_class] = finalists
            continue
        selected[authority_class] = sorted(finalists, key=_canonical_bytes)[-1]
    if conflicts:
        return {
            "schema_version": "authority_decision_v2",
            "status": "CONFLICT_WITHIN_CLASS", "gate_verdict": "BLOCKED",
            "claims": claims, "winner": None, "tied_conflicts": conflicts,
        }
    selected_values = [_canonical_bytes(item["value"]) for item in selected.values()]
    if len(selected) > 1:
        aligned = all(value == selected_values[0] for value in selected_values[1:])
        return {
            "schema_version": "authority_decision_v2",
            "status": "ALIGNED" if aligned else "CONFLICT",
            "gate_verdict": "PASS" if aligned else "BLOCKED",
            "claims": claims, "winner": None, "selected_within_class": selected,
        }
    winner = next(iter(selected.values()))
    return {
        "schema_version": "authority_decision_v2",
        "status": "FRESHEST_WITHIN_CLASS" if len(claims) > 1 else "SINGLE_CLASS",
        "gate_verdict": "PASS", "claims": claims, "winner": winner,
        "selected_within_class": selected,
    }
