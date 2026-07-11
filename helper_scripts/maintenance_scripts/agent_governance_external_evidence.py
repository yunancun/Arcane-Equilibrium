"""Out-of-band trusted public external-policy/outcome evidence Interface."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_governance_capture import PLATFORM_OR_EXTERNAL_ATTESTED


ExternalEvidenceVerifier = Callable[[dict[str, Any]], bool]
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FIELDS = {
    "schema_version", "trust_tier", "capture_kind", "url", "content_digest",
    "observed_at", "expires_at", "citation_ref", "selector", "excerpt",
    "excerpt_digest", "record_digest",
}
CAPTURE_KINDS = {"external_policy_snapshot", "external_outcome_snapshot"}
MAX_TTL = timedelta(days=30)
MAX_EXCERPT_WORDS = 25
MAX_EXCERPT_CHARS = 500


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _record_digest(record: dict[str, Any]) -> str:
    return _digest_bytes(_canonical({
        key: value for key, value in record.items() if key != "record_digest"
    }))


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def validate_external_evidence_capture(
    record: Any,
    *,
    verifier: ExternalEvidenceVerifier | None = None,
    adjudicated_at: Any = None,
) -> list[str]:
    """Validate canonical capture shape and require an out-of-band host verifier."""

    if not isinstance(record, dict):
        return ["external evidence capture must be an object"]
    errors: list[str] = []
    if set(record) != FIELDS:
        errors.append("external evidence capture fields do not match contract")
    if record.get("schema_version") != "external_evidence_capture_v1":
        errors.append("external evidence capture schema_version is invalid")
    if record.get("trust_tier") != PLATFORM_OR_EXTERNAL_ATTESTED:
        errors.append("external evidence capture trust tier is invalid")
    if record.get("capture_kind") not in CAPTURE_KINDS:
        errors.append("external evidence capture kind is invalid")
    if not isinstance(record.get("url"), str) or not record["url"].startswith("https://"):
        errors.append("external evidence capture URL must be public HTTPS")
    for field in ("content_digest", "excerpt_digest"):
        if not DIGEST_RE.fullmatch(str(record.get(field, ""))):
            errors.append(f"external evidence capture {field} is invalid")
    for field in ("citation_ref", "selector"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            errors.append(f"external evidence capture {field} is invalid")
    excerpt = record.get("excerpt")
    if (
        not isinstance(excerpt, str) or not excerpt.strip()
        or len(excerpt) > MAX_EXCERPT_CHARS
        or len(excerpt.split()) > MAX_EXCERPT_WORDS
    ):
        errors.append("external evidence capture excerpt exceeds bounded quote contract")
    elif record.get("excerpt_digest") != _digest_bytes(excerpt.encode("utf-8")):
        errors.append("external evidence capture excerpt digest is invalid")
    observed = _time(record.get("observed_at"))
    expires = _time(record.get("expires_at"))
    adjudicated = (
        _time(adjudicated_at)
        if adjudicated_at is not None
        else datetime.now(timezone.utc)
    )
    if observed is None or expires is None or observed >= expires or expires - observed > MAX_TTL:
        errors.append("external evidence capture freshness interval/TTL is invalid")
    elif not observed <= adjudicated < expires:
        errors.append("external evidence capture is stale at adjudication")
    try:
        expected_digest = _record_digest(record)
    except (TypeError, ValueError):
        expected_digest = None
        errors.append("external evidence capture is not canonical JSON")
    if record.get("record_digest") != expected_digest:
        errors.append("external evidence capture self-digest is invalid")
    try:
        verified = verifier is not None and verifier(record) is True
    except Exception:
        verified = False
    if not verified:
        errors.append("external evidence capture lacks out-of-band host verification")
    return errors
