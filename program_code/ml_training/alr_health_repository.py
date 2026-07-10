"""Append-only ALR health snapshot collection and persistence."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_NO_AUTHORITY = {
    "exchange_authority": False,
    "trading_authority": False,
    "order_or_probe_authority": False,
    "decision_lease_authority": False,
    "cost_gate_authority": False,
    "proof_authority": False,
    "serving_authority": False,
    "promotion_authority": False,
    "latest_authority": False,
}
_ZERO_AUTHORITY_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_promotion_count": 0,
    "latest_pointer_update_count": 0,
}


class AlrHealthRepositoryError(ValueError):
    """A health snapshot cannot be represented as zero-authority ALR state."""


def collect_health_snapshot(
    connection: Any,
    *,
    source_head: str,
    write_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """直接從 raw identity、durable cursor 與 consumer events 收集健康真相。"""
    if not isinstance(source_head, str) or not _HEX40_RE.fullmatch(source_head):
        raise AlrHealthRepositoryError("health_source_head_invalid")
    with connection.cursor() as cursor:
        cursor.execute(
            "WITH fresh_cursor AS ("
            "SELECT source_ts, source_scan_id, source_hash "
            "FROM learning.alr_consumer_events WHERE lane = 'FRESH' "
            "AND event_kind IN ('LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED') "
            "ORDER BY source_ts DESC, source_scan_id DESC, event_id DESC LIMIT 1"
            "), fresh_boundary AS ("
            "SELECT source_ts, source_scan_id FROM learning.alr_consumer_events "
            "WHERE lane = 'FRESH' AND event_kind = 'LANE_BOOTSTRAPPED' "
            "ORDER BY source_ts ASC, source_scan_id ASC, event_id ASC LIMIT 1"
            "), raw_latest AS ("
            "SELECT max(ts) AS raw_latest_ts FROM trading.scanner_snapshots"
            "), alr_latest AS ("
            "SELECT max(source_ts) AS alr_latest_source_ts "
            "FROM learning.alr_source_events"
            "), untrained_oldest AS ("
            "SELECT min(source.source_ts) AS oldest_untrained_source_ts "
            "FROM learning.alr_source_events AS source WHERE NOT EXISTS ("
            "SELECT 1 FROM learning.alr_provenance_edges AS edge "
            "WHERE edge.from_artifact_hash = source.source_hash "
            "AND edge.edge_role = 'training_input')"
            ") SELECT "
            "(SELECT raw_latest_ts FROM raw_latest) AS raw_latest_ts, "
            "(SELECT alr_latest_source_ts FROM alr_latest) AS alr_latest_source_ts, "
            "(SELECT source_ts FROM fresh_cursor) AS fresh_cursor_ts, "
            "(SELECT source_scan_id FROM fresh_cursor) AS fresh_cursor_scan_id, "
            "(SELECT source_hash FROM fresh_cursor) AS fresh_cursor_hash, "
            "(SELECT source_ts FROM fresh_boundary) AS fresh_bootstrap_ts, "
            "(SELECT source_scan_id FROM fresh_boundary) AS fresh_bootstrap_scan_id, "
            "CASE WHEN (SELECT raw_latest_ts FROM raw_latest) IS NULL "
            "OR (SELECT source_ts FROM fresh_cursor) IS NULL THEN NULL ELSE "
            "GREATEST(EXTRACT(EPOCH FROM ((SELECT raw_latest_ts FROM raw_latest) "
            "- (SELECT source_ts FROM fresh_cursor))), 0)::double precision "
            "END AS ingest_lag_seconds, "
            "(SELECT count(*) FROM trading.scanner_snapshots AS raw "
            "WHERE ((SELECT source_ts FROM fresh_boundary) IS NULL OR "
            "(raw.ts, raw.scan_id) > ((SELECT source_ts FROM fresh_boundary), "
            "(SELECT source_scan_id FROM fresh_boundary))) AND NOT EXISTS ("
            "SELECT 1 FROM learning.alr_source_events AS alr "
            "WHERE alr.source_table = 'trading.scanner_snapshots' "
            "AND alr.source_ts = raw.ts AND alr.source_scan_id = raw.scan_id"
            ")) AS fresh_raw_only_count, "
            "(SELECT count(*) FROM trading.scanner_snapshots AS raw "
            "WHERE (SELECT source_ts FROM fresh_boundary) IS NOT NULL "
            "AND (raw.ts, raw.scan_id) < ((SELECT source_ts FROM fresh_boundary), "
            "(SELECT source_scan_id FROM fresh_boundary)) AND NOT EXISTS ("
            "SELECT 1 FROM learning.alr_source_events AS alr "
            "WHERE alr.source_table = 'trading.scanner_snapshots' "
            "AND alr.source_ts = raw.ts AND alr.source_scan_id = raw.scan_id"
            ")) AS historical_backfill_remaining, "
            "(SELECT count(*) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'NOTIFICATION_RECEIVED') AS notifications_received, "
            "(SELECT count(*) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'NOTIFICATION_CONSUMED') AS notifications_consumed, "
            "(SELECT count(*) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'NOTIFICATION_DUPLICATE') AS notifications_duplicate, "
            "(SELECT count(*) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'NOTIFICATION_INVALID') AS notifications_invalid, "
            "(SELECT max(recorded_at) FROM learning.alr_consumer_events "
            "WHERE event_kind IN ('NOTIFICATION_CONSUMED', "
            "'LANE_CURSOR_ADVANCED', 'LANE_BOOTSTRAPPED', "
            "'LANE_SUCCESS')) AS last_success_at, "
            "(SELECT count(*) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'SESSION_FAILED') AS failure_count, "
            "GREATEST((SELECT count(*) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'SESSION_STARTED') - 1, 0) AS restart_count, "
            "(SELECT count(*) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'UNCLEAN_RECOVERY') AS unclean_recovery_count, "
            "(SELECT max(recorded_at) FROM learning.alr_consumer_events "
            "WHERE event_kind = 'SESSION_FAILED') AS last_failure_at, "
            "(SELECT error_code FROM learning.alr_consumer_events "
            "WHERE event_kind = 'SESSION_FAILED' "
            "ORDER BY recorded_at DESC, event_id DESC LIMIT 1) AS last_failure_code, "
            "(SELECT count(*) FROM learning.alr_source_events) AS source_event_count, "
            "(SELECT count(*) FROM learning.alr_source_events AS source WHERE NOT EXISTS ("
            "SELECT 1 FROM learning.alr_provenance_edges AS edge "
            "WHERE edge.from_artifact_hash = source.source_hash "
            "AND edge.edge_role = 'training_input')) AS untrained_source_cycle_count, "
            "(SELECT oldest_untrained_source_ts FROM untrained_oldest) "
            "AS oldest_untrained_source_ts, "
            "CASE WHEN (SELECT oldest_untrained_source_ts FROM untrained_oldest) IS NULL "
            "OR (SELECT alr_latest_source_ts FROM alr_latest) IS NULL THEN NULL ELSE "
            "GREATEST(EXTRACT(EPOCH FROM ((SELECT alr_latest_source_ts FROM alr_latest) "
            "- (SELECT oldest_untrained_source_ts FROM untrained_oldest))), 0)::double precision "
            "END AS oldest_untrained_age_seconds, "
            "(SELECT count(*) FROM learning.alr_training_runs) AS training_run_count, "
            "(SELECT count(*) FROM learning.alr_training_runs AS run WHERE NOT EXISTS ("
            "SELECT 1 FROM learning.alr_outcome_feedback_events AS feedback "
            "WHERE feedback.run_hash = run.run_hash)) AS feedback_backlog_count, "
            "(SELECT count(*) FROM learning.alr_outcome_feedback_events "
            "WHERE feedback_status = 'DEFER_EVIDENCE') AS deferred_feedback_count, "
            "(SELECT count(*) FROM learning.alr_outcome_feedback_events "
            "WHERE proof_packet_present) AS proof_packet_present_count, "
            "(SELECT coalesce(sum(reward_record_count), 0) FROM learning.alr_outcome_feedback_events) AS reward_record_count, "
            "(SELECT count(*) FROM (SELECT source_table, source_key, count(*) "
            "FROM learning.alr_source_events GROUP BY source_table, source_key HAVING count(*) > 1) AS duplicates) AS source_duplicate_key_count, "
            "(SELECT count(*) FROM learning.alr_derived_cache_entries) AS retention_entry_count, "
            "(SELECT coalesce(sum(octet_length(cache_payload::text)), 0) FROM learning.alr_derived_cache_entries) AS retention_payload_bytes, "
            "(SELECT count(*) FROM learning.alr_retention_events) AS retention_event_count, "
            "(SELECT count(*) FROM learning.alr_training_runs WHERE "
            "no_authority <> '{\"exchange_authority\": false, \"trading_authority\": false, \"order_or_probe_authority\": false, \"decision_lease_authority\": false, \"cost_gate_authority\": false, \"proof_authority\": false, \"serving_authority\": false, \"promotion_authority\": false, \"latest_authority\": false}'::jsonb "
            "OR authority_counters <> '{\"exchange_contact_count\": 0, \"trading_action_count\": 0, \"order_or_probe_count\": 0, \"decision_lease_count\": 0, \"cost_gate_change_count\": 0, \"proof_claim_count\": 0, \"serving_or_promotion_count\": 0}'::jsonb) AS run_authority_mismatch_count, "
            "(SELECT count(*) FROM learning.alr_outcome_feedback_events WHERE "
            "no_authority <> '{\"exchange_authority\": false, \"trading_authority\": false, \"order_or_probe_authority\": false, \"decision_lease_authority\": false, \"cost_gate_authority\": false, \"proof_authority\": false, \"serving_authority\": false, \"promotion_authority\": false, \"latest_authority\": false}'::jsonb "
            "OR authority_counters <> '{\"exchange_contact_count\": 0, \"trading_action_count\": 0, \"order_or_probe_count\": 0, \"decision_lease_count\": 0, \"cost_gate_change_count\": 0, \"proof_claim_count\": 0, \"serving_or_promotion_count\": 0}'::jsonb) AS feedback_authority_mismatch_count"
        )
        metrics = cursor.fetchone()
        cursor.execute(
            "SELECT run.run_hash, run.candidate_artifact_hash, run.run_status "
            "FROM learning.alr_training_runs AS run "
            "ORDER BY run.created_at DESC, run.run_hash DESC LIMIT 1"
        )
        latest_run = cursor.fetchone()
    metric = _mapping(metrics, "health_metrics_invalid")
    ingest_lag_seconds = _nullable_nonnegative_number(metric, "ingest_lag_seconds")
    fresh_raw_only_count = _nonnegative(metric, "fresh_raw_only_count")
    ingestion_alert = fresh_raw_only_count > 0 or (
        ingest_lag_seconds is not None and ingest_lag_seconds > 0
    )
    snapshot: dict[str, Any] = {
        "schema_version": "alr_health_snapshot_v2",
        "source_head": source_head,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "watermark": _fresh_watermark(metric),
        "ingestion": {
            "status": "DEGRADED" if ingestion_alert else "HEALTHY",
            "raw_latest_ts": _nullable_text(metric.get("raw_latest_ts")),
            "alr_latest_source_ts": _nullable_text(metric.get("alr_latest_source_ts")),
            "fresh_cursor_ts": _nullable_text(metric.get("fresh_cursor_ts")),
            "fresh_cursor_scan_id": _nullable_text(metric.get("fresh_cursor_scan_id")),
            "fresh_bootstrap_ts": _nullable_text(metric.get("fresh_bootstrap_ts")),
            "fresh_bootstrap_scan_id": _nullable_text(
                metric.get("fresh_bootstrap_scan_id")
            ),
            "ingest_lag_seconds": ingest_lag_seconds,
            "fresh_raw_only_count": fresh_raw_only_count,
            "historical_backfill_remaining": _nonnegative(
                metric,
                "historical_backfill_remaining",
            ),
            "alert": ingestion_alert,
        },
        "notifications": {
            "received": _nonnegative(metric, "notifications_received"),
            "consumed": _nonnegative(metric, "notifications_consumed"),
            "duplicate": _nonnegative(metric, "notifications_duplicate"),
            "invalid": _nonnegative(metric, "notifications_invalid"),
        },
        "backlog": {
            "untrained_source_cycles": _nonnegative(
                metric,
                "untrained_source_cycle_count",
            ),
            "outcome_feedback": _nonnegative(metric, "feedback_backlog_count"),
            "oldest_untrained_source_ts": _nullable_text(
                metric.get("oldest_untrained_source_ts")
            ),
            "oldest_untrained_age_seconds": _nullable_nonnegative_number(
                metric,
                "oldest_untrained_age_seconds",
            ),
            "starvation_alert": bool(
                metric.get("oldest_untrained_age_seconds") is not None
                and float(metric["oldest_untrained_age_seconds"]) >= 3600.0
                and int(metric.get("untrained_source_cycle_count", 0)) > 0
            ),
        },
        "target": _latest_target(latest_run),
        "training": {
            "source_event_count": _nonnegative(metric, "source_event_count"),
            "run_count": _nonnegative(metric, "training_run_count"),
        },
        "evidence_gaps": {
            "deferred_feedback_count": _nonnegative(metric, "deferred_feedback_count"),
            "proof_packet_present_count": _nonnegative(metric, "proof_packet_present_count"),
            "reward_record_count": _nonnegative(metric, "reward_record_count"),
        },
        "failure": {
            "count": _nonnegative(metric, "failure_count"),
            "last_failure_at": _nullable_text(metric.get("last_failure_at")),
            "last_failure_code": _nullable_text(metric.get("last_failure_code")),
        },
        "restart_recovery": {
            "watermark_present": metric.get("fresh_cursor_ts") is not None,
            "restart_count": _nonnegative(metric, "restart_count"),
            "unclean_recovery_count": _nonnegative(metric, "unclean_recovery_count"),
            "last_success_at": _nullable_text(metric.get("last_success_at")),
            "source_duplicate_key_count": _nonnegative(metric, "source_duplicate_key_count"),
        },
        "retention": {
            "entry_count": _nonnegative(metric, "retention_entry_count"),
            "payload_bytes": _nonnegative(metric, "retention_payload_bytes"),
            "event_count": _nonnegative(metric, "retention_event_count"),
        },
        "authority_counters": {
            "run_authority_mismatch_count": _nonnegative(metric, "run_authority_mismatch_count"),
            "feedback_authority_mismatch_count": _nonnegative(metric, "feedback_authority_mismatch_count"),
            **_ZERO_AUTHORITY_COUNTERS,
        },
        "no_authority": dict(_NO_AUTHORITY),
    }
    if write_metrics is not None:
        snapshot["write_metrics"] = _normalize_write_metrics(write_metrics)
    snapshot["snapshot_hash"] = compute_health_snapshot_hash(snapshot)
    return snapshot


def compute_health_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(snapshot))
    payload.pop("snapshot_hash", None)
    return _canonical_sha256(payload)


def compute_health_semantic_hash(snapshot: Mapping[str, Any]) -> str:
    """Hash observable health state without emission time or write counters."""
    payload = copy.deepcopy(dict(snapshot))
    payload.pop("snapshot_hash", None)
    payload.pop("observed_at", None)
    payload.pop("write_metrics", None)
    return _canonical_sha256(payload)


def persist_health_snapshot(
    connection: Any,
    snapshot: Mapping[str, Any],
    *,
    heartbeat_seconds: int = 300,
) -> dict[str, Any]:
    """持久化 immutable snapshot 與可索引 typed freshness projections。"""
    snapshot_hash = snapshot.get("snapshot_hash")
    if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
        raise AlrHealthRepositoryError("health_snapshot_hash_invalid")
    if snapshot_hash != compute_health_snapshot_hash(snapshot):
        raise AlrHealthRepositoryError("health_snapshot_hash_mismatch")
    if snapshot.get("no_authority") != _NO_AUTHORITY:
        raise AlrHealthRepositoryError("health_no_authority_invalid")
    if (
        isinstance(heartbeat_seconds, bool)
        or not isinstance(heartbeat_seconds, int)
        or not 60 <= heartbeat_seconds <= 86_400
    ):
        raise AlrHealthRepositoryError("health_heartbeat_seconds_invalid")
    try:
        semantic_state_changed, heartbeat_due = _health_emission_decision(
            connection,
            snapshot=snapshot,
            heartbeat_seconds=heartbeat_seconds,
        )
        if not semantic_state_changed and not heartbeat_due:
            connection.commit()
            return {
                "status": "SUPPRESSED_NO_DELTA",
                "snapshot_hash": snapshot_hash,
                "semantic_state_changed": False,
                "heartbeat_due": False,
                "rows_written": 0,
                "payload_bytes_written": 0,
                "writes_suppressed": 1,
            }
        projections = _health_projections(snapshot)
        canonical_snapshot = _canonical_json(snapshot)
    except Exception:
        connection.rollback()
        raise
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO learning.alr_artifact_nodes "
                "(artifact_hash, artifact_kind, canonical_payload) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (artifact_hash) DO NOTHING RETURNING artifact_hash",
                (snapshot_hash, "health_snapshot", canonical_snapshot),
            )
            artifact_inserted = cursor.fetchone()
            artifact_rows_written = int(artifact_inserted is not None)
            if artifact_inserted is not None and _row_value(
                artifact_inserted,
                0,
                "artifact_hash",
            ) != snapshot_hash:
                raise AlrHealthRepositoryError(
                    "health_artifact_insert_hash_mismatch"
                )
            cursor.execute(
                "INSERT INTO learning.alr_health_events "
                "(snapshot_hash, source_head, canonical_payload, raw_latest_ts, "
                "alr_latest_source_ts, fresh_cursor_ts, fresh_cursor_scan_id, "
                "fresh_bootstrap_ts, fresh_bootstrap_scan_id, ingest_lag_seconds, "
                "fresh_raw_only_count, historical_backfill_remaining, "
                "notifications_received, notifications_consumed, notifications_invalid, "
                "notifications_duplicate, "
                "last_success_at, failure_count, restart_count, unclean_recovery_count, "
                "untrained_source_cycle_count, ingestion_alert) "
                "VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (snapshot_hash) DO NOTHING RETURNING snapshot_hash",
                (
                    snapshot_hash,
                    snapshot["source_head"],
                    canonical_snapshot,
                    projections["raw_latest_ts"],
                    projections["alr_latest_source_ts"],
                    projections["fresh_cursor_ts"],
                    projections["fresh_cursor_scan_id"],
                    projections["fresh_bootstrap_ts"],
                    projections["fresh_bootstrap_scan_id"],
                    projections["ingest_lag_seconds"],
                    projections["fresh_raw_only_count"],
                    projections["historical_backfill_remaining"],
                    projections["notifications_received"],
                    projections["notifications_consumed"],
                    projections["notifications_invalid"],
                    projections["notifications_duplicate"],
                    projections["last_success_at"],
                    projections["failure_count"],
                    projections["restart_count"],
                    projections["unclean_recovery_count"],
                    projections["untrained_source_cycle_count"],
                    projections["ingestion_alert"],
                ),
            )
            health_event_inserted = cursor.fetchone()
            if health_event_inserted is None:
                raise AlrHealthRepositoryError(
                    "health_event_insert_conflict"
                )
            if _row_value(
                health_event_inserted,
                0,
                "snapshot_hash",
            ) != snapshot_hash:
                raise AlrHealthRepositoryError(
                    "health_event_insert_hash_mismatch"
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "status": "PERSISTED",
        "snapshot_hash": snapshot_hash,
        "emission_reason": "STATE_DELTA"
        if semantic_state_changed
        else "HEARTBEAT",
        "semantic_state_changed": semantic_state_changed,
        "heartbeat_due": heartbeat_due,
        "rows_written": artifact_rows_written + 1,
        "payload_bytes_written": len(canonical_snapshot.encode("utf-8"))
        * (artifact_rows_written + 1),
        "writes_suppressed": 0,
    }


def _health_emission_decision(
    connection: Any,
    *,
    snapshot: Mapping[str, Any],
    heartbeat_seconds: int,
) -> tuple[bool, bool]:
    _aware_datetime(
        snapshot.get("observed_at"),
        "health_observed_at_invalid",
    )
    current_semantic_hash = compute_health_semantic_hash(snapshot)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT latest.canonical_payload, latest.recorded_at, "
            "clock_timestamp() AS database_now "
            "FROM (VALUES (1)) AS singleton(value) LEFT JOIN LATERAL ("
            "SELECT canonical_payload, recorded_at "
            "FROM learning.alr_health_events "
            "ORDER BY recorded_at DESC, snapshot_hash DESC LIMIT 1"
            ") AS latest ON TRUE"
        )
        latest = cursor.fetchone()
    if latest is None:
        raise AlrHealthRepositoryError("health_database_clock_missing")
    previous_payload_value = _row_value(latest, 0, "canonical_payload")
    previous_recorded_at_value = _row_value(latest, 1, "recorded_at")
    database_now = _aware_datetime(
        _row_value(latest, 2, "database_now"),
        "health_database_clock_invalid",
    )
    if previous_payload_value is None and previous_recorded_at_value is None:
        return True, False
    if previous_payload_value is None or previous_recorded_at_value is None:
        raise AlrHealthRepositoryError("health_previous_event_incomplete")
    previous_payload = _mapping(
        previous_payload_value,
        "health_previous_payload_invalid",
    )
    previous_recorded_at = _aware_datetime(
        previous_recorded_at_value,
        "health_previous_recorded_at_invalid",
    )
    semantic_state_changed = (
        compute_health_semantic_hash(previous_payload) != current_semantic_hash
    )
    elapsed_seconds = (database_now - previous_recorded_at).total_seconds()
    if elapsed_seconds < 0:
        raise AlrHealthRepositoryError("health_database_clock_regressed")
    return semantic_state_changed, elapsed_seconds >= heartbeat_seconds


def _fresh_watermark(value: Mapping[str, Any]) -> dict[str, Any] | None:
    if value.get("fresh_cursor_ts") is None:
        return None
    return {
        "source_ts": _text(value.get("fresh_cursor_ts")),
        "source_scan_id": _text(value.get("fresh_cursor_scan_id")),
        "source_hash": _text(value.get("fresh_cursor_hash")),
    }


def _health_projections(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    ingestion = _mapping(snapshot.get("ingestion"), "health_ingestion_invalid")
    notifications = _mapping(
        snapshot.get("notifications"),
        "health_notifications_invalid",
    )
    failure = _mapping(snapshot.get("failure"), "health_failure_invalid")
    restart = _mapping(
        snapshot.get("restart_recovery"),
        "health_restart_recovery_invalid",
    )
    backlog = _mapping(snapshot.get("backlog"), "health_backlog_invalid")
    ingestion_alert = ingestion.get("alert")
    if not isinstance(ingestion_alert, bool):
        raise AlrHealthRepositoryError("health_ingestion_alert_invalid")
    return {
        "raw_latest_ts": ingestion.get("raw_latest_ts"),
        "alr_latest_source_ts": ingestion.get("alr_latest_source_ts"),
        "fresh_cursor_ts": ingestion.get("fresh_cursor_ts"),
        "fresh_cursor_scan_id": ingestion.get("fresh_cursor_scan_id"),
        "fresh_bootstrap_ts": ingestion.get("fresh_bootstrap_ts"),
        "fresh_bootstrap_scan_id": ingestion.get("fresh_bootstrap_scan_id"),
        "ingest_lag_seconds": ingestion.get("ingest_lag_seconds"),
        "fresh_raw_only_count": _nonnegative(ingestion, "fresh_raw_only_count"),
        "historical_backfill_remaining": _nonnegative(
            ingestion,
            "historical_backfill_remaining",
        ),
        "notifications_received": _nonnegative(notifications, "received"),
        "notifications_consumed": _nonnegative(notifications, "consumed"),
        "notifications_invalid": _nonnegative(notifications, "invalid"),
        "notifications_duplicate": _nonnegative(notifications, "duplicate"),
        "last_success_at": restart.get("last_success_at"),
        "failure_count": _nonnegative(failure, "count"),
        "restart_count": _nonnegative(restart, "restart_count"),
        "unclean_recovery_count": _nonnegative(restart, "unclean_recovery_count"),
        "untrained_source_cycle_count": _nonnegative(
            backlog,
            "untrained_source_cycles",
        ),
        "ingestion_alert": ingestion_alert,
    }


def _latest_target(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    row = _mapping(value, "health_target_invalid")
    return {
        "run_hash": _text(row.get("run_hash")),
        "candidate_artifact_hash": _text(row.get("candidate_artifact_hash")),
        "run_status": _text(row.get("run_status")),
    }


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, KeyError, TypeError) as exc:
        raise AlrHealthRepositoryError("health_previous_row_invalid") from exc


def _aware_datetime(value: Any, reason: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AlrHealthRepositoryError(reason) from exc
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AlrHealthRepositoryError(reason)
    return value.astimezone(timezone.utc)


def _mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrHealthRepositoryError(reason)
    return value


def _nonnegative(value: Mapping[str, Any], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise AlrHealthRepositoryError(f"health_metric_invalid:{field}")
    return item


def _nullable_nonnegative_number(
    value: Mapping[str, Any],
    field: str,
) -> float | int | None:
    item = value.get(field)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, (int, float)) or item < 0:
        raise AlrHealthRepositoryError(f"health_metric_invalid:{field}")
    return item


def _nullable_text(value: Any) -> str | None:
    return None if value is None else _text(value)


def _normalize_write_metrics(value: Any) -> dict[str, Any]:
    metrics = _mapping(value, "health_write_metrics_invalid")
    if set(metrics) != {
        "schema_version",
        "scope",
        "health",
        "decision",
        "feedback",
    }:
        raise AlrHealthRepositoryError("health_write_metrics_fields_invalid")
    if metrics.get("schema_version") != "alr_write_metrics_v1":
        raise AlrHealthRepositoryError("health_write_metrics_schema_invalid")
    scope = _mapping(metrics.get("scope"), "health_write_metrics_scope_invalid")
    if set(scope) != {
        "kind",
        "session_id",
        "through_completed_health_attempt",
    }:
        raise AlrHealthRepositoryError("health_write_metrics_scope_fields_invalid")
    if scope.get("kind") != "consumer_session_cumulative":
        raise AlrHealthRepositoryError("health_write_metrics_scope_kind_invalid")
    session_id = scope.get("session_id")
    if not isinstance(session_id, str) or not _UUID_RE.fullmatch(session_id):
        raise AlrHealthRepositoryError("health_write_metrics_session_id_invalid")
    health = _metric_group(
        metrics.get("health"),
        name="health",
        integer_fields={
            "attempts",
            "emitted",
            "state_delta_writes",
            "heartbeat_writes",
            "writes_suppressed",
            "rows_written",
            "payload_bytes_written",
        },
    )
    decision = _metric_group(
        metrics.get("decision"),
        name="decision",
        integer_fields={
            "attempts",
            "writes_suppressed",
            "duplicate_retries",
            "artifact_rows_written",
            "provenance_rows_written",
            "run_rows_written",
            "feedback_rows_written",
            "defer_artifact_rows_written",
            "payload_bytes_written",
            "source_rows_consumed",
        },
    )
    feedback_value = _mapping(
        metrics.get("feedback"),
        "health_write_metrics_feedback_invalid",
    )
    feedback_integer_fields = {
        "attempts",
        "persisted",
        "duplicate_retries",
        "artifact_rows_written",
        "provenance_rows_written",
        "event_rows_written",
        "total_rows_written",
        "payload_bytes_written",
    }
    feedback_ratio_fields = {"persisted_ratio", "duplicate_retry_ratio"}
    if set(feedback_value) != feedback_integer_fields | feedback_ratio_fields:
        raise AlrHealthRepositoryError(
            "health_write_metrics_feedback_fields_invalid"
        )
    feedback = _integer_metric_group(
        {
            field: feedback_value.get(field)
            for field in feedback_integer_fields
        },
        name="feedback",
        integer_fields=feedback_integer_fields,
    )
    through_attempt = scope.get("through_completed_health_attempt")
    if (
        isinstance(through_attempt, bool)
        or not isinstance(through_attempt, int)
        or through_attempt != health["attempts"]
    ):
        raise AlrHealthRepositoryError("health_write_metrics_scope_attempt_invalid")
    if (
        health["emitted"] + health["writes_suppressed"] != health["attempts"]
        or health["state_delta_writes"] + health["heartbeat_writes"]
        != health["emitted"]
    ):
        raise AlrHealthRepositoryError("health_write_metrics_health_totals_invalid")
    if (
        decision["writes_suppressed"] > decision["attempts"]
        or decision["duplicate_retries"] > decision["attempts"]
    ):
        raise AlrHealthRepositoryError("health_write_metrics_decision_totals_invalid")
    if (
        feedback["persisted"] + feedback["duplicate_retries"]
        != feedback["attempts"]
        or feedback["total_rows_written"]
        != feedback["artifact_rows_written"]
        + feedback["provenance_rows_written"]
        + feedback["event_rows_written"]
    ):
        raise AlrHealthRepositoryError("health_write_metrics_feedback_totals_invalid")
    feedback_attempts = feedback["attempts"]
    expected_persisted_ratio = (
        feedback["persisted"] / feedback_attempts
        if feedback_attempts
        else 0.0
    )
    expected_duplicate_ratio = (
        feedback["duplicate_retries"] / feedback_attempts
        if feedback_attempts
        else 0.0
    )
    persisted_ratio = _bounded_ratio(
        feedback_value.get("persisted_ratio"),
        "health_write_metrics_feedback_persisted_ratio_invalid",
    )
    duplicate_ratio = _bounded_ratio(
        feedback_value.get("duplicate_retry_ratio"),
        "health_write_metrics_feedback_duplicate_ratio_invalid",
    )
    if (
        abs(persisted_ratio - expected_persisted_ratio) > 1e-12
        or abs(duplicate_ratio - expected_duplicate_ratio) > 1e-12
    ):
        raise AlrHealthRepositoryError(
            "health_write_metrics_feedback_ratio_mismatch"
        )
    feedback["persisted_ratio"] = persisted_ratio
    feedback["duplicate_retry_ratio"] = duplicate_ratio
    return {
        "schema_version": "alr_write_metrics_v1",
        "scope": {
            "kind": "consumer_session_cumulative",
            "session_id": session_id,
            "through_completed_health_attempt": through_attempt,
        },
        "health": health,
        "decision": decision,
        "feedback": feedback,
    }


def _metric_group(
    value: Any,
    *,
    name: str,
    integer_fields: set[str],
) -> dict[str, Any]:
    group = _mapping(value, f"health_write_metrics_{name}_invalid")
    if set(group) != integer_fields | {"suppression_ratio"}:
        raise AlrHealthRepositoryError(
            f"health_write_metrics_{name}_fields_invalid"
        )
    normalized = _integer_metric_group(
        {field: group.get(field) for field in integer_fields},
        name=name,
        integer_fields=integer_fields,
    )
    ratio = group.get("suppression_ratio")
    if (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or not 0.0 <= float(ratio) <= 1.0
    ):
        raise AlrHealthRepositoryError(
            f"health_write_metrics_{name}_ratio_invalid"
        )
    denominator = normalized["attempts"]
    numerator_key = (
        "writes_suppressed" if name in {"health", "decision"} else "suppressed"
    )
    expected_ratio = (
        normalized[numerator_key] / denominator if denominator else 0.0
    )
    if abs(float(ratio) - expected_ratio) > 1e-12:
        raise AlrHealthRepositoryError(
            f"health_write_metrics_{name}_ratio_mismatch"
        )
    normalized["suppression_ratio"] = float(ratio)
    return normalized


def _integer_metric_group(
    value: Any,
    *,
    name: str,
    integer_fields: set[str],
) -> dict[str, int]:
    group = _mapping(value, f"health_write_metrics_{name}_invalid")
    if set(group) != integer_fields:
        raise AlrHealthRepositoryError(
            f"health_write_metrics_{name}_fields_invalid"
        )
    normalized: dict[str, int] = {}
    for field in sorted(integer_fields):
        item = group.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise AlrHealthRepositoryError(
                f"health_write_metrics_{name}_{field}_invalid"
            )
        normalized[field] = item
    return normalized


def _bounded_ratio(value: Any, reason: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise AlrHealthRepositoryError(reason)
    return float(value)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
