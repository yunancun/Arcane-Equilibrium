"""Trusted evaluation-time binding for governance closure validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


MAX_TRUSTED_EVALUATION_SKEW = timedelta(seconds=60)


def resolve_evaluation_time(
    adjudicated_value: Any,
    trusted_evaluated_at: datetime | None,
) -> tuple[datetime | None, str, list[str]]:
    """Bind packet time to a trusted host clock without caller rollback."""

    errors: list[str] = []
    packet_timestamp = str(adjudicated_value or "")
    try:
        adjudicated_at = datetime.fromisoformat(
            packet_timestamp.replace("Z", "+00:00")
        )
        if adjudicated_at.tzinfo is None:
            raise ValueError("timezone missing")
    except (TypeError, ValueError):
        adjudicated_at = None
        errors.append("adjudicated_at must be a timezone-aware timestamp")

    evaluation_time = adjudicated_at
    if trusted_evaluated_at is not None:
        if trusted_evaluated_at.tzinfo is None:
            errors.append("trusted_evaluated_at must be timezone-aware")
        else:
            evaluation_time = trusted_evaluated_at.astimezone(timezone.utc)
            if (
                adjudicated_at is not None
                and abs(evaluation_time - adjudicated_at.astimezone(timezone.utc))
                > MAX_TRUSTED_EVALUATION_SKEW
            ):
                errors.append(
                    "packet adjudicated_at is not bound to trusted host evaluation time"
                )

    evaluation_timestamp = packet_timestamp
    if trusted_evaluated_at is not None and evaluation_time is not None:
        evaluation_timestamp = evaluation_time.isoformat()
    return evaluation_time, evaluation_timestamp, errors
