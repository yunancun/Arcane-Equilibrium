"""Pure two-phase retention decisions for ALR-owned rebuildable cache only."""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


OWNER_SCOPE = "ALR_OWNED_REBUILDABLE"
ACTIVE = "ACTIVE"
QUARANTINED = "QUARANTINED"


class AlrRetentionGuardianError(ValueError):
    """A retention candidate is outside the ALR-owned rebuildable boundary."""


@dataclass(frozen=True)
class RetentionDecision:
    cache_key: str
    cache_artifact_hash: str
    action: str
    next_state: str | None
    delete_cache: bool
    reason: str
    quarantine_until: datetime | None
    authority_counters: dict[str, int]


def decide_retention_action(
    entry: Mapping[str, Any],
    *,
    referenced_artifact_hashes: Set[str],
    now: datetime,
    grace_seconds: int,
) -> RetentionDecision:
    """Choose retain/quarantine/restore/sweep after a complete reference check."""
    cache_key = _required_text(entry.get("cache_key"), "cache_key")
    artifact_hash = _required_hash(entry.get("cache_artifact_hash"), "cache_artifact_hash")
    _required_text(entry.get("cache_kind"), "cache_kind")
    if entry.get("owner_scope") != OWNER_SCOPE:
        raise AlrRetentionGuardianError("cache_owner_scope_invalid")
    if entry.get("rebuildable") is not True:
        raise AlrRetentionGuardianError("cache_rebuildable_required")
    state = entry.get("cache_state")
    if state not in {ACTIVE, QUARANTINED}:
        raise AlrRetentionGuardianError("cache_state_invalid")
    checked_at = _aware_utc(now, "now")
    if isinstance(grace_seconds, bool) or not isinstance(grace_seconds, int) or grace_seconds < 60:
        raise AlrRetentionGuardianError("grace_seconds_invalid")

    referenced = artifact_hash in referenced_artifact_hashes
    if referenced:
        if state == QUARANTINED:
            return _decision(
                cache_key,
                artifact_hash,
                "RESTORE_REFERENCE",
                ACTIVE,
                False,
                "reference_reappeared_during_grace",
                None,
            )
        return _decision(
            cache_key,
            artifact_hash,
            "RETAIN_REFERENCE",
            ACTIVE,
            False,
            "reference_graph_nonempty",
            None,
        )
    if state == ACTIVE:
        return _decision(
            cache_key,
            artifact_hash,
            "QUARANTINE",
            QUARANTINED,
            False,
            "unreferenced_alr_owned_rebuildable_cache",
            checked_at + timedelta(seconds=grace_seconds),
        )

    quarantined_at = _aware_utc(entry.get("quarantined_at"), "quarantined_at")
    deadline = quarantined_at + timedelta(seconds=grace_seconds)
    if checked_at < deadline:
        return _decision(
            cache_key,
            artifact_hash,
            "RETAIN_GRACE",
            QUARANTINED,
            False,
            "grace_window_not_elapsed",
            deadline,
        )
    return _decision(
        cache_key,
        artifact_hash,
        "SWEEP",
        None,
        True,
        "unreferenced_after_grace_recheck",
        deadline,
    )


def _decision(
    cache_key: str,
    artifact_hash: str,
    action: str,
    next_state: str | None,
    delete_cache: bool,
    reason: str,
    quarantine_until: datetime | None,
) -> RetentionDecision:
    return RetentionDecision(
        cache_key=cache_key,
        cache_artifact_hash=artifact_hash,
        action=action,
        next_state=next_state,
        delete_cache=delete_cache,
        reason=reason,
        quarantine_until=quarantine_until,
        authority_counters={"derived_cache_delete_count": 1 if delete_cache else 0},
    )


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AlrRetentionGuardianError(f"{field}_invalid")
    return value


def _required_hash(value: Any, field: str) -> str:
    text = _required_text(value, field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise AlrRetentionGuardianError(f"{field}_invalid")
    return text


def _aware_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AlrRetentionGuardianError(f"{field}_invalid")
    return value.astimezone(timezone.utc)
