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


class AlrHealthRepositoryError(ValueError):
    """A health snapshot cannot be represented as zero-authority ALR state."""


def collect_health_snapshot(connection: Any, *, source_head: str) -> dict[str, Any]:
    """Collect database-local health metrics without reading scanner payloads."""
    if not isinstance(source_head, str) or not _HEX40_RE.fullmatch(source_head):
        raise AlrHealthRepositoryError("health_source_head_invalid")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_ts, source_scan_id, source_hash "
            "FROM learning.alr_watermark_events "
            "WHERE watermark_event_kind = 'ADVANCED' "
            "ORDER BY source_ts DESC, source_scan_id DESC LIMIT 1"
        )
        watermark = cursor.fetchone()
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM learning.alr_source_events) AS source_event_count, "
            "(SELECT count(*) FROM learning.alr_source_events AS source WHERE NOT EXISTS ("
            "SELECT 1 FROM learning.alr_provenance_edges AS edge "
            "WHERE edge.from_artifact_hash = source.source_hash "
            "AND edge.edge_role = 'training_input')) AS scanner_backlog_count, "
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
    snapshot: dict[str, Any] = {
        "schema_version": "alr_health_snapshot_v1",
        "source_head": source_head,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "watermark": _watermark(watermark),
        "backlog": {
            "scanner_cycles": _nonnegative(metric, "scanner_backlog_count"),
            "outcome_feedback": _nonnegative(metric, "feedback_backlog_count"),
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
        "failure": {"count": 0, "last_failure": None},
        "restart_recovery": {
            "watermark_present": watermark is not None,
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
            "exchange_contact_count": 0,
            "trading_action_count": 0,
            "proof_claim_count": 0,
            "serving_or_promotion_count": 0,
        },
        "no_authority": dict(_NO_AUTHORITY),
    }
    snapshot["snapshot_hash"] = compute_health_snapshot_hash(snapshot)
    return snapshot


def compute_health_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(snapshot))
    payload.pop("snapshot_hash", None)
    return _canonical_sha256(payload)


def persist_health_snapshot(connection: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Persist one immutable health snapshot and its artifact node."""
    snapshot_hash = snapshot.get("snapshot_hash")
    if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
        raise AlrHealthRepositoryError("health_snapshot_hash_invalid")
    if snapshot_hash != compute_health_snapshot_hash(snapshot):
        raise AlrHealthRepositoryError("health_snapshot_hash_mismatch")
    if snapshot.get("no_authority") != _NO_AUTHORITY:
        raise AlrHealthRepositoryError("health_no_authority_invalid")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO learning.alr_artifact_nodes "
                "(artifact_hash, artifact_kind, canonical_payload) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (artifact_hash) DO NOTHING",
                (snapshot_hash, "health_snapshot", _canonical_json(snapshot)),
            )
            cursor.execute(
                "INSERT INTO learning.alr_health_events "
                "(snapshot_hash, source_head, canonical_payload) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (snapshot_hash) DO NOTHING",
                (snapshot_hash, snapshot["source_head"], _canonical_json(snapshot)),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {"status": "PERSISTED", "snapshot_hash": snapshot_hash}


def _watermark(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    row = _mapping(value, "health_watermark_invalid")
    return {
        "source_ts": _text(row.get("source_ts")),
        "source_scan_id": _text(row.get("source_scan_id")),
        "source_hash": _text(row.get("source_hash")),
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


def _mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrHealthRepositoryError(reason)
    return value


def _nonnegative(value: Mapping[str, Any], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise AlrHealthRepositoryError(f"health_metric_invalid:{field}")
    return item


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
