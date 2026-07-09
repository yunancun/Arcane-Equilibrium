"""Append-only persistence planning for evidence-only ALR scanner cycles."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


SOURCE_TABLE = "trading.scanner_snapshots"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_KEYS = (
    "exchange_authority",
    "trading_authority",
    "proof_authority",
    "serving_authority",
    "promotion_authority",
)


class AlrPersistenceError(ValueError):
    """A scanner cycle cannot become an immutable ALR ledger plan."""


class AlrPersistenceConflict(AlrPersistenceError):
    """An existing source identity has irreconcilable canonical content."""


def build_persistence_plan(cycle: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one P2-1 cycle and derive its immutable persistence records."""
    if not isinstance(cycle, Mapping):
        raise AlrPersistenceError("cycle_not_mapping")
    source = cycle.get("source")
    if not isinstance(source, Mapping):
        raise AlrPersistenceError("cycle_source_not_mapping")
    if source.get("table") != SOURCE_TABLE:
        raise AlrPersistenceError("cycle_source_table_invalid")
    source_key = _required_text(source.get("source_key"), "cycle_source_key")
    scan_id = _required_text(source.get("scan_id"), "cycle_scan_id")
    ts = _required_text(source.get("ts"), "cycle_ts")
    source_hash = _required_hash(cycle.get("source_hash"), "cycle_source_hash")
    schema_version = _required_text(cycle.get("schema_version"), "cycle_schema_version")
    payload = cycle.get("payload")
    if not isinstance(payload, Mapping):
        raise AlrPersistenceError("cycle_payload_not_mapping")
    _validate_authority(cycle.get("authority"))

    ingest_event = {
        "schema_version": "alr_ingest_event_v1",
        "source_table": SOURCE_TABLE,
        "source_key": source_key,
        "source_hash": source_hash,
        "cycle_schema_version": schema_version,
        "event_kind": "PERSISTED",
    }
    ingest_event_hash = _canonical_sha256(ingest_event)
    watermark_event_kind = "ADVANCED" if cycle.get("watermark_advanced") is True else "RETAINED_LATE"
    return {
        "source_table": SOURCE_TABLE,
        "source_key": source_key,
        "source_scan_id": scan_id,
        "source_ts": ts,
        "source_hash": source_hash,
        "cycle_schema_version": schema_version,
        "canonical_payload": dict(payload),
        "ingest_event_kind": "PERSISTED",
        "ingest_event_hash": ingest_event_hash,
        "watermark_event_kind": watermark_event_kind,
        "authority": {key: False for key in _AUTHORITY_KEYS},
    }


def persist_scanner_cycle(connection: Any, cycle: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically persist one scanner cycle or record an immutable duplicate event."""
    plan = build_persistence_plan(cycle)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_hash FROM learning.alr_source_events "
                "WHERE source_table = %s AND source_key = %s FOR SHARE",
                (plan["source_table"], plan["source_key"]),
            )
            existing = cursor.fetchone()
            if existing is not None:
                existing_hash = _row_value(existing, 0, "source_hash")
                if existing_hash != plan["source_hash"]:
                    raise AlrPersistenceConflict("source_hash_conflict")
                duplicate_plan = _record_duplicate(cursor, plan)
                connection.commit()
                return _result("DUPLICATE", duplicate_plan)

            _insert_artifact_node(cursor, plan["source_hash"], "scanner_cycle", plan["canonical_payload"])
            cursor.execute(
                "INSERT INTO learning.alr_source_events "
                "(source_table, source_key, source_scan_id, source_ts, source_hash, cycle_schema_version) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (source_table, source_key) DO NOTHING RETURNING source_hash",
                (
                    plan["source_table"],
                    plan["source_key"],
                    plan["source_scan_id"],
                    plan["source_ts"],
                    plan["source_hash"],
                    plan["cycle_schema_version"],
                ),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "SELECT source_hash FROM learning.alr_source_events "
                    "WHERE source_table = %s AND source_key = %s FOR SHARE",
                    (plan["source_table"], plan["source_key"]),
                )
                raced = cursor.fetchone()
                if raced is None:
                    raise AlrPersistenceError("source_identity_conflict")
                if _row_value(raced, 0, "source_hash") != plan["source_hash"]:
                    raise AlrPersistenceConflict("source_hash_conflict")
                duplicate_plan = _record_duplicate(cursor, plan)
                connection.commit()
                return _result("DUPLICATE", duplicate_plan)

            _insert_artifact_node(cursor, plan["ingest_event_hash"], "ingest_event", plan)
            _insert_ingest_event(cursor, plan)
            if plan["watermark_event_kind"] == "ADVANCED":
                cursor.execute(
                    "INSERT INTO learning.alr_watermark_events "
                    "(source_table, source_key, source_ts, source_scan_id, source_hash, "
                    "watermark_event_kind, event_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        plan["source_table"],
                        plan["source_key"],
                        plan["source_ts"],
                        plan["source_scan_id"],
                        plan["source_hash"],
                        plan["watermark_event_kind"],
                        _watermark_event_hash(plan),
                    ),
                )
            _insert_provenance_edge(cursor, plan)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _result("PERSISTED", plan)


def fetch_unseen_scanner_snapshots(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    """Read a bounded set of scanner rows that has no ALR source identity yet."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
        raise AlrPersistenceError("scanner_fetch_limit_invalid")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT scanner.ts, scanner.scan_id, scanner.active_symbols, scanner.added, "
            "scanner.removed, scanner.rejected_count, scanner.scan_duration_ms, "
            "scanner.candidates, scanner.config "
            "FROM trading.scanner_snapshots AS scanner "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM learning.alr_source_events AS alr "
            "WHERE alr.source_table = %s AND alr.source_scan_id = scanner.scan_id "
            "AND alr.source_ts = scanner.ts"
            ") ORDER BY scanner.ts ASC, scanner.scan_id ASC LIMIT %s",
            (SOURCE_TABLE, limit),
        )
        rows = cursor.fetchall()
    if not isinstance(rows, list):
        raise AlrPersistenceError("scanner_fetch_rows_not_list")
    if not all(isinstance(row, Mapping) for row in rows):
        raise AlrPersistenceError("scanner_fetch_row_not_mapping")
    return [dict(row) for row in rows]


def load_restart_state(connection: Any) -> dict[str, Any]:
    """Rebuild idempotency and monotonic cursor state from immutable ledger rows."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_key FROM learning.alr_source_events "
            "WHERE source_table = %s ORDER BY source_key",
            (SOURCE_TABLE,),
        )
        processed_source_keys = {
            _row_value(row, 0, "source_key") for row in cursor.fetchall()
        }
        cursor.execute(
            "SELECT source_ts, source_scan_id, source_hash "
            "FROM learning.alr_watermark_events "
            "WHERE source_table = %s AND watermark_event_kind = 'ADVANCED' "
            "ORDER BY source_ts DESC, source_scan_id DESC LIMIT 1",
            (SOURCE_TABLE,),
        )
        watermark = cursor.fetchone()
    return {
        "processed_source_keys": processed_source_keys,
        "watermark": (
            None
            if watermark is None
            else {
                "ts": _row_value(watermark, 0, "source_ts"),
                "scan_id": _row_value(watermark, 1, "source_scan_id"),
                "source_hash": _row_value(watermark, 2, "source_hash"),
            }
        ),
    }


def _duplicate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    duplicate = dict(plan)
    duplicate["ingest_event_kind"] = "DUPLICATE"
    duplicate["ingest_event_hash"] = _canonical_sha256(
        {
            "schema_version": "alr_ingest_event_v1",
            "source_table": duplicate["source_table"],
            "source_key": duplicate["source_key"],
            "source_hash": duplicate["source_hash"],
            "event_kind": "DUPLICATE",
        }
    )
    return duplicate


def _record_duplicate(cursor: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    duplicate_plan = _duplicate_plan(plan)
    _insert_artifact_node(
        cursor,
        duplicate_plan["ingest_event_hash"],
        "ingest_event",
        duplicate_plan,
    )
    _insert_ingest_event(cursor, duplicate_plan)
    return duplicate_plan


def _insert_artifact_node(cursor: Any, artifact_hash: str, artifact_kind: str, payload: Mapping[str, Any]) -> None:
    cursor.execute(
        "INSERT INTO learning.alr_artifact_nodes "
        "(artifact_hash, artifact_kind, canonical_payload) VALUES (%s, %s, %s::jsonb) "
        "ON CONFLICT (artifact_hash) DO NOTHING",
        (artifact_hash, artifact_kind, _canonical_json(payload)),
    )


def _insert_ingest_event(cursor: Any, plan: Mapping[str, Any]) -> None:
    cursor.execute(
        "INSERT INTO learning.alr_ingest_events "
        "(source_table, source_key, ingest_event_kind, event_hash) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (event_hash) DO NOTHING",
        (
            plan["source_table"],
            plan["source_key"],
            plan["ingest_event_kind"],
            plan["ingest_event_hash"],
        ),
    )


def _insert_provenance_edge(cursor: Any, plan: Mapping[str, Any]) -> None:
    edge_hash = _canonical_sha256(
        {
            "from_artifact_hash": plan["source_hash"],
            "to_artifact_hash": plan["ingest_event_hash"],
            "edge_role": "ingested_from",
        }
    )
    cursor.execute(
        "INSERT INTO learning.alr_provenance_edges "
        "(edge_hash, from_artifact_hash, to_artifact_hash, edge_role) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (edge_hash) DO NOTHING",
        (edge_hash, plan["source_hash"], plan["ingest_event_hash"], "ingested_from"),
    )


def _watermark_event_hash(plan: Mapping[str, Any]) -> str:
    return _canonical_sha256(
        {
            "source_table": plan["source_table"],
            "source_key": plan["source_key"],
            "source_hash": plan["source_hash"],
            "event_kind": plan["watermark_event_kind"],
        }
    )


def _result(status: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "source_key": plan["source_key"],
        "source_hash": plan["source_hash"],
        "ingest_event_hash": plan["ingest_event_hash"],
        "watermark_event_kind": plan["watermark_event_kind"],
        "authority": dict(plan["authority"]),
    }


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


def _validate_authority(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise AlrPersistenceError("cycle_authority_not_mapping")
    if value.get("scanner_evidence_only") is not True:
        raise AlrPersistenceError("cycle_scanner_evidence_only_required")
    for key in _AUTHORITY_KEYS:
        if value.get(key) is not False:
            raise AlrPersistenceError(f"cycle_authority_not_denied:{key}")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AlrPersistenceError(f"{field}_invalid")
    return value


def _required_hash(value: Any, field: str) -> str:
    text = _required_text(value, field)
    if not _HEX64_RE.fullmatch(text):
        raise AlrPersistenceError(f"{field}_invalid")
    return text


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
