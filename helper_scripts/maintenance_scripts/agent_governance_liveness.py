"""Pure liveness adjudication for development-agent controller activity."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / ".codex/agent_registry_v1.json"
SUPPORTED_ACTIVITY_FIELDS = {
    "schema_version", "interface", "state", "observed_at",
}
TRANSCRIPT_DIAGNOSTIC_FIELDS = {
    "schema_version", "exists", "size_bytes", "mtime_ms",
}
ACTIVE_STATES = {"RUNNING", "WAITING"}
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
RUNAWAY_TRANSCRIPT_BYTES = 10 * 1024 * 1024
LIVENESS_POLICY_FIELDS = {
    "schema_version",
    "policy_id",
    "max_observation_age_seconds",
    "max_future_skew_seconds",
    "clock_source",
    "policy_digest",
}
EXPECTED_LIVENESS_POLICY_UNSIGNED = {
    "schema_version": "agent_liveness_policy_v1",
    "policy_id": "supported_activity_freshness_v1",
    "max_observation_age_seconds": 60,
    "max_future_skew_seconds": 0,
    "clock_source": "trusted_system_utc_no_caller_override_v1",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def liveness_policy_digest(policy: dict[str, Any]) -> str:
    """Return the canonical digest for one Registry-owned liveness policy."""

    unsigned = {
        key: value for key, value in policy.items() if key != "policy_digest"
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def registry_liveness_policy_errors(registry: dict[str, Any]) -> list[str]:
    """Validate the exact fail-closed supported-activity freshness policy."""

    policy = registry.get("liveness_policy")
    if not isinstance(policy, dict) or set(policy) != LIVENESS_POLICY_FIELDS:
        return [
            "liveness_policy must contain the exact agent_liveness_policy_v1 fields"
        ]
    unsigned = {
        key: value for key, value in policy.items() if key != "policy_digest"
    }
    errors: list[str] = []
    try:
        exact_policy_match = (
            _canonical_bytes(unsigned)
            == _canonical_bytes(EXPECTED_LIVENESS_POLICY_UNSIGNED)
        )
    except (TypeError, ValueError):
        exact_policy_match = False
    if not exact_policy_match:
        errors.append(
            "liveness_policy must preserve the exact 60-second maximum age, "
            "zero future skew, and trusted system UTC clock with no caller override"
        )
    try:
        expected_digest = liveness_policy_digest(policy)
    except (TypeError, ValueError):
        errors.append("liveness_policy is not canonical JSON")
    else:
        if policy.get("policy_digest") != expected_digest:
            errors.append("liveness_policy.policy_digest differs from authority")
    return errors


@lru_cache(maxsize=1)
def _registry_liveness_policy() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    errors = registry_liveness_policy_errors(registry)
    if errors:
        raise ValueError("; ".join(errors))
    return registry["liveness_policy"]


def _trusted_utc_now() -> datetime:
    """Read system UTC; the public Interface intentionally has no ``now`` seam."""

    return datetime.now(timezone.utc)


def _parse_aware_instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _canonical_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_supported_activity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SUPPORTED_ACTIVITY_FIELDS:
        raise ValueError("supported_activity fields do not match canonical contract")
    if value.get("schema_version") != "supported_agent_activity_v1":
        raise ValueError("supported_activity schema_version is invalid")
    if value.get("interface") not in {"collaboration", "thread"}:
        raise ValueError("supported_activity interface is invalid")
    if value.get("state") not in ACTIVE_STATES | TERMINAL_STATES | {"UNAVAILABLE"}:
        raise ValueError("supported_activity state is invalid")
    if _parse_aware_instant(value.get("observed_at")) is None:
        raise ValueError("supported_activity observed_at must be timezone-aware")
    return value


def _validate_transcript_diagnostic(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != TRANSCRIPT_DIAGNOSTIC_FIELDS:
        raise ValueError(
            "transcript_diagnostic fields do not match canonical contract"
        )
    if value.get("schema_version") != "private_jsonl_liveness_diagnostic_v1":
        raise ValueError("transcript_diagnostic schema_version is invalid")
    exists = value.get("exists")
    if not isinstance(exists, bool):
        raise ValueError("transcript_diagnostic exists must be boolean")
    if not exists:
        if value.get("size_bytes") is not None or value.get("mtime_ms") is not None:
            raise ValueError(
                "missing transcript cannot claim size_bytes or mtime_ms"
            )
        return value
    for field in ("size_bytes", "mtime_ms"):
        field_value = value.get(field)
        if (
            not isinstance(field_value, int)
            or isinstance(field_value, bool)
            or field_value < 0
        ):
            raise ValueError(
                f"present transcript {field} must be a non-negative integer"
            )
    return value


def adjudicate_agent_liveness(
    *,
    supported_activity: dict[str, Any],
    transcript_diagnostic: dict[str, Any],
) -> dict[str, Any]:
    """Classify caller activity without treating it as host-authenticated proof."""

    activity = _validate_supported_activity(supported_activity)
    transcript = _validate_transcript_diagnostic(transcript_diagnostic)
    policy = _registry_liveness_policy()
    observed_at = _parse_aware_instant(activity["observed_at"])
    assert observed_at is not None
    adjudicated_at: datetime | None = None
    try:
        candidate_now = _trusted_utc_now()
        if (
            not isinstance(candidate_now, datetime)
            or candidate_now.tzinfo is None
            or candidate_now.utcoffset() is None
        ):
            raise ValueError("trusted system UTC clock is not timezone-aware")
        adjudicated_at = candidate_now.astimezone(timezone.utc)
    except Exception:
        freshness = "UNVERIFIABLE"
    else:
        age_seconds = (adjudicated_at - observed_at).total_seconds()
        if age_seconds < -policy["max_future_skew_seconds"]:
            freshness = "FUTURE"
        elif age_seconds > policy["max_observation_age_seconds"]:
            freshness = "STALE"
        else:
            freshness = "FRESH"
    state = activity["state"]
    # The public pure interface receives a caller-constructed mapping. Timestamp
    # arithmetic can describe that claim's freshness, but cannot authenticate
    # host acquisition, monotonic identity/sequence/head, or replay resistance.
    # Until a managed host Adapter supplies such proof out of band, every caller
    # activity claim therefore fails closed.
    liveness_state = "UNKNOWN"
    if not transcript["exists"]:
        diagnostic_state = "UNAVAILABLE"
    elif transcript["size_bytes"] > RUNAWAY_TRANSCRIPT_BYTES:
        diagnostic_state = "RUNAWAY_SUSPECT"
    else:
        diagnostic_state = "AVAILABLE"
    return {
        "schema_version": "agent_liveness_adjudication_v1",
        "liveness_state": liveness_state,
        "primary_evidence": "CALLER_ACTIVITY_UNVERIFIED",
        "activity_verification_status": "EXTERNAL_LIMIT",
        "activity_verification_reason": (
            "MANAGED_HOST_ACTIVITY_ADAPTER_UNAVAILABLE"
        ),
        "activity_state": state,
        "activity_observed_at": _canonical_instant(observed_at),
        "adjudicated_at": (
            _canonical_instant(adjudicated_at)
            if adjudicated_at is not None
            else None
        ),
        "activity_freshness": freshness,
        "liveness_policy_id": policy["policy_id"],
        "liveness_policy_digest": policy["policy_digest"],
        "max_observation_age_seconds": policy[
            "max_observation_age_seconds"
        ],
        "diagnostic_state": diagnostic_state,
        "transcript_diagnostic": dict(transcript),
        "automatic_stop": False,
    }
