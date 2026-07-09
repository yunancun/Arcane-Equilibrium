"""Repository pass for two-phase ALR-derived-cache retention only."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ml_training.alr_retention_guardian import RetentionDecision, decide_retention_action


class AlrRetentionRepositoryError(ValueError):
    """Retention cannot proceed without an ALR-owned rebuildable cache contract."""


def run_retention_pass(
    connection: Any,
    *,
    now: datetime,
    grace_seconds: int,
    limit: int,
) -> dict[str, int]:
    """Reference-check, quarantine, recheck, and optionally sweep derived cache.

    Only rows from `learning.alr_derived_cache_entries` can be updated or
    deleted.  Every state-changing action appends a separate immutable event.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64:
        raise AlrRetentionRepositoryError("retention_limit_invalid")
    entries = _fetch_candidates(connection, limit=limit)
    totals = {
        "scanned": len(entries),
        "quarantined": 0,
        "restored": 0,
        "swept": 0,
        "retained": 0,
        "skipped": 0,
    }
    try:
        with connection.cursor() as cursor:
            for entry in entries:
                references = (
                    {entry["cache_artifact_hash"]} if entry.get("is_referenced") is True else set()
                )
                decision = decide_retention_action(
                    entry,
                    referenced_artifact_hashes=references,
                    now=now,
                    grace_seconds=grace_seconds,
                )
                changed = _apply_decision(cursor, entry, decision, now)
                if not changed:
                    totals["skipped"] += 1
                elif decision.action == "QUARANTINE":
                    totals["quarantined"] += 1
                elif decision.action == "RESTORE_REFERENCE":
                    totals["restored"] += 1
                elif decision.action == "SWEEP":
                    totals["swept"] += 1
                else:
                    totals["retained"] += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return totals


def _fetch_candidates(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT cache.cache_key, cache.cache_artifact_hash, cache.cache_kind, "
            "cache.owner_scope, cache.rebuildable, cache.cache_state, cache.created_at, "
            "cache.quarantined_at, cache.cache_content_hash, EXISTS ("
            "SELECT 1 FROM learning.alr_provenance_edges AS edge "
            "WHERE edge.from_artifact_hash = cache.cache_artifact_hash "
            "OR edge.to_artifact_hash = cache.cache_artifact_hash"
            ") AS is_referenced "
            "FROM learning.alr_derived_cache_entries AS cache "
            "ORDER BY cache.created_at ASC, cache.cache_key ASC LIMIT %s",
            (limit,),
        )
        rows = cursor.fetchall()
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise AlrRetentionRepositoryError("retention_rows_invalid")
    return [dict(row) for row in rows]


def _apply_decision(
    cursor: Any,
    entry: Mapping[str, Any],
    decision: RetentionDecision,
    now: datetime,
) -> bool:
    if decision.action in {"RETAIN_REFERENCE", "RETAIN_GRACE"}:
        return True
    if decision.action == "QUARANTINE":
        cursor.execute(
            "UPDATE learning.alr_derived_cache_entries "
            "SET cache_state = 'QUARANTINED', quarantined_at = %s "
            "WHERE cache_key = %s AND cache_state = 'ACTIVE' RETURNING cache_key",
            (now, decision.cache_key),
        )
    elif decision.action == "RESTORE_REFERENCE":
        cursor.execute(
            "UPDATE learning.alr_derived_cache_entries "
            "SET cache_state = 'ACTIVE', quarantined_at = NULL "
            "WHERE cache_key = %s AND cache_state = 'QUARANTINED' RETURNING cache_key",
            (decision.cache_key,),
        )
    elif decision.action == "SWEEP":
        cursor.execute(
            "DELETE FROM learning.alr_derived_cache_entries AS cache "
            "WHERE cache.cache_key = %s AND cache.cache_state = 'QUARANTINED' "
            "AND NOT EXISTS (SELECT 1 FROM learning.alr_provenance_edges AS edge "
            "WHERE edge.from_artifact_hash = cache.cache_artifact_hash "
            "OR edge.to_artifact_hash = cache.cache_artifact_hash) "
            "RETURNING cache.cache_key",
            (decision.cache_key,),
        )
    else:
        raise AlrRetentionRepositoryError("retention_action_invalid")
    if cursor.fetchone() is None:
        return False
    _insert_retention_event(cursor, entry, decision, now)
    return True


def _insert_retention_event(
    cursor: Any,
    entry: Mapping[str, Any],
    decision: RetentionDecision,
    now: datetime,
) -> None:
    payload = {
        "cache_key": decision.cache_key,
        "cache_artifact_hash": decision.cache_artifact_hash,
        "cache_content_hash": entry["cache_content_hash"],
        "action": decision.action,
        "reason": decision.reason,
        "reference_graph_hash": _canonical_sha256(
            {
                "cache_artifact_hash": decision.cache_artifact_hash,
                "referenced": entry.get("is_referenced") is True,
            }
        ),
        "recorded_at": now.isoformat(),
    }
    event_hash = _canonical_sha256(payload)
    cursor.execute(
        "INSERT INTO learning.alr_retention_events "
        "(event_hash, cache_key, cache_artifact_hash, cache_content_hash, action, "
        "reason, reference_graph_hash, canonical_payload) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
        "ON CONFLICT (event_hash) DO NOTHING",
        (
            event_hash,
            decision.cache_key,
            decision.cache_artifact_hash,
            entry["cache_content_hash"],
            decision.action,
            decision.reason,
            payload["reference_graph_hash"],
            _canonical_json(payload),
        ),
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
