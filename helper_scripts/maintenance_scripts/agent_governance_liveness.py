"""Pure liveness adjudication for development-agent controller activity."""

from __future__ import annotations

from datetime import datetime
from typing import Any


SUPPORTED_ACTIVITY_FIELDS = {
    "schema_version", "interface", "state", "observed_at",
}
TRANSCRIPT_DIAGNOSTIC_FIELDS = {
    "schema_version", "exists", "size_bytes", "mtime_ms",
}
ACTIVE_STATES = {"RUNNING", "WAITING"}
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
RUNAWAY_TRANSCRIPT_BYTES = 10 * 1024 * 1024


def _aware_instant(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_supported_activity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SUPPORTED_ACTIVITY_FIELDS:
        raise ValueError("supported_activity fields do not match canonical contract")
    if value.get("schema_version") != "supported_agent_activity_v1":
        raise ValueError("supported_activity schema_version is invalid")
    if value.get("interface") not in {"collaboration", "thread"}:
        raise ValueError("supported_activity interface is invalid")
    if value.get("state") not in ACTIVE_STATES | TERMINAL_STATES | {"UNAVAILABLE"}:
        raise ValueError("supported_activity state is invalid")
    if not _aware_instant(value.get("observed_at")):
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
    """Prefer supported controller activity over private transcript diagnostics."""

    activity = _validate_supported_activity(supported_activity)
    transcript = _validate_transcript_diagnostic(transcript_diagnostic)
    state = activity["state"]
    if state in ACTIVE_STATES:
        liveness_state = "RUNNING"
    elif state in TERMINAL_STATES:
        liveness_state = "TERMINAL"
    else:
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
        "primary_evidence": f"SUPPORTED_{activity['interface'].upper()}_ACTIVITY",
        "activity_state": state,
        "diagnostic_state": diagnostic_state,
        "transcript_diagnostic": dict(transcript),
        "automatic_stop": False,
    }
