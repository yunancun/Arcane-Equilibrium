from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ml_training.alr_health_repository import (
    AlrHealthRepositoryError,
    collect_health_snapshot,
    compute_health_semantic_hash,
    compute_health_snapshot_hash,
    persist_health_snapshot,
)


class _Connection:
    def __init__(
        self,
        *,
        fresh_raw_only_count: int = 1,
        ingest_lag_seconds: float = 120.0,
    ) -> None:
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.artifacts: set[str] = set()
        self.snapshots: set[str] = set()
        self.commits = 0
        self.rollbacks = 0
        self.fresh_raw_only_count = fresh_raw_only_count
        self.ingest_lag_seconds = ingest_lag_seconds
        self.latest_health_payload: dict[str, Any] | None = None
        self.latest_health_recorded_at: datetime | None = None
        self.database_now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

    def cursor(self) -> "_Cursor":
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.row: Any = None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        if "clock_timestamp() AS database_now" in sql:
            self.row = {
                "canonical_payload": self.connection.latest_health_payload,
                "recorded_at": self.connection.latest_health_recorded_at,
                "database_now": self.connection.database_now,
            }
        elif "AS source_event_count" in sql:
            self.row = {
                "raw_latest_ts": "2026-07-09T12:02:00Z",
                "alr_latest_source_ts": "2026-07-09T12:02:00Z",
                "fresh_cursor_ts": "2026-07-09T12:00:00Z",
                "fresh_cursor_scan_id": "scan-1",
                "fresh_cursor_hash": "a" * 64,
                "fresh_bootstrap_ts": "2026-07-09T11:00:00Z",
                "fresh_bootstrap_scan_id": "scan-bootstrap",
                "ingest_lag_seconds": self.connection.ingest_lag_seconds,
                "fresh_raw_only_count": self.connection.fresh_raw_only_count,
                "historical_backfill_remaining": 79_000,
                "notifications_received": 7,
                "notifications_consumed": 5,
                "notifications_duplicate": 0,
                "notifications_invalid": 1,
                "last_success_at": "2026-07-09T12:00:01Z",
                "failure_count": 2,
                "restart_count": 3,
                "unclean_recovery_count": 1,
                "last_failure_at": "2026-07-09T11:59:00Z",
                "last_failure_code": "RuntimeError",
                "source_event_count": 64,
                "untrained_source_cycle_count": 3,
                "oldest_untrained_source_ts": "2026-07-09T10:00:00Z",
                "oldest_untrained_age_seconds": 7200.0,
                "training_run_count": 2,
                "feedback_backlog_count": 1,
                "deferred_feedback_count": 1,
                "proof_packet_present_count": 0,
                "reward_record_count": 0,
                "source_duplicate_key_count": 0,
                "retention_entry_count": 0,
                "retention_payload_bytes": 0,
                "retention_event_count": 0,
                "run_authority_mismatch_count": 0,
                "feedback_authority_mismatch_count": 0,
            }
        elif "FROM learning.alr_training_runs AS run" in sql:
            self.row = {
                "run_hash": "b" * 64,
                "candidate_artifact_hash": "c" * 64,
                "run_status": "DEFER_EVIDENCE",
            }
        elif "INSERT INTO learning.alr_health_events" in sql:
            snapshot_hash = str(params[0])
            if snapshot_hash in self.connection.snapshots:
                self.row = None
            else:
                self.connection.snapshots.add(snapshot_hash)
                self.connection.latest_health_payload = json.loads(str(params[2]))
                self.connection.latest_health_recorded_at = self.connection.database_now
                self.row = (snapshot_hash,)
        elif "INSERT INTO learning.alr_artifact_nodes" in sql:
            artifact_hash = str(params[0])
            if artifact_hash in self.connection.artifacts:
                self.row = None
            else:
                self.connection.artifacts.add(artifact_hash)
                self.row = (artifact_hash,)

    def fetchone(self) -> Any:
        return self.row


def _write_metrics(
    *,
    health_attempts: int = 4,
    health_suppressed: int = 3,
    decision_attempts: int = 5,
    decision_suppressed: int = 2,
) -> dict[str, Any]:
    return {
        "schema_version": "alr_write_metrics_v1",
        "scope": {
            "kind": "consumer_session_cumulative",
            "session_id": "00000000-0000-0000-0000-000000000001",
            "through_completed_health_attempt": health_attempts,
        },
        "health": {
            "attempts": health_attempts,
            "emitted": health_attempts - health_suppressed,
            "state_delta_writes": 1,
            "heartbeat_writes": 0,
            "writes_suppressed": health_suppressed,
            "rows_written": 2,
            "payload_bytes_written": 512,
            "suppression_ratio": health_suppressed / health_attempts
            if health_attempts
            else 0.0,
        },
        "decision": {
            "attempts": decision_attempts,
            "writes_suppressed": decision_suppressed,
            "duplicate_retries": 0,
            "artifact_rows_written": 15,
            "provenance_rows_written": 21,
            "run_rows_written": 3,
            "feedback_rows_written": 3,
            "defer_artifact_rows_written": 3,
            "payload_bytes_written": 3072,
            "source_rows_consumed": 15,
            "suppression_ratio": decision_suppressed / decision_attempts
            if decision_attempts
            else 0.0,
        },
        "feedback": {
            "attempts": 1,
            "persisted": 1,
            "duplicate_retries": 0,
            "persisted_ratio": 1.0,
            "duplicate_retry_ratio": 0.0,
            "artifact_rows_written": 3,
            "provenance_rows_written": 3,
            "event_rows_written": 1,
            "total_rows_written": 7,
            "payload_bytes_written": 256,
        },
    }


def test_collects_explicit_health_without_authority_expansion() -> None:
    connection = _Connection()
    snapshot = collect_health_snapshot(connection, source_head="a" * 40)

    assert snapshot["schema_version"] == "alr_health_snapshot_v2"
    assert snapshot["watermark"]["source_scan_id"] == "scan-1"
    assert snapshot["ingestion"] == {
        "status": "DEGRADED",
        "raw_latest_ts": "2026-07-09T12:02:00Z",
        "alr_latest_source_ts": "2026-07-09T12:02:00Z",
        "fresh_cursor_ts": "2026-07-09T12:00:00Z",
        "fresh_cursor_scan_id": "scan-1",
        "fresh_bootstrap_ts": "2026-07-09T11:00:00Z",
        "fresh_bootstrap_scan_id": "scan-bootstrap",
        "ingest_lag_seconds": 120.0,
        "fresh_raw_only_count": 1,
        "historical_backfill_remaining": 79_000,
        "alert": True,
    }
    assert snapshot["notifications"] == {
        "received": 7,
        "consumed": 5,
        "duplicate": 0,
        "invalid": 1,
    }
    assert snapshot["backlog"] == {
        "untrained_source_cycles": 3,
        "outcome_feedback": 1,
        "oldest_untrained_source_ts": "2026-07-09T10:00:00Z",
        "oldest_untrained_age_seconds": 7200.0,
        "starvation_alert": True,
    }
    assert snapshot["training"]["run_count"] == 2
    assert snapshot["evidence_gaps"]["deferred_feedback_count"] == 1
    assert snapshot["restart_recovery"]["source_duplicate_key_count"] == 0
    assert snapshot["retention"]["payload_bytes"] == 0
    assert snapshot["failure"]["count"] == 2
    assert snapshot["restart_recovery"]["restart_count"] == 3
    assert snapshot["authority_counters"] == {
        "run_authority_mismatch_count": 0,
        "feedback_authority_mismatch_count": 0,
        "exchange_contact_count": 0,
        "trading_action_count": 0,
        "order_or_probe_count": 0,
        "decision_lease_count": 0,
        "cost_gate_change_count": 0,
        "proof_claim_count": 0,
        "serving_promotion_count": 0,
        "latest_pointer_update_count": 0,
    }
    health_sql = connection.calls[0][0]
    fresh_gap_clause = health_sql.split("AS fresh_raw_only_count", 1)[0].rsplit(
        "(SELECT count(*) FROM trading.scanner_snapshots AS raw",
        1,
    )[1]
    assert "SELECT source_ts FROM fresh_boundary" in fresh_gap_clause
    last_success_clause = health_sql.split("AS last_success_at", 1)[0].rsplit(
        "(SELECT max(recorded_at) FROM learning.alr_consumer_events",
        1,
    )[1]
    assert "NOTIFICATION_CONSUMED" in last_success_clause
    assert "LANE_CURSOR_ADVANCED" in last_success_clause
    assert "LANE_BOOTSTRAPPED" in last_success_clause
    assert "LANE_SUCCESS" in last_success_clause


def test_write_metrics_are_durable_but_do_not_create_semantic_delta() -> None:
    first = collect_health_snapshot(
        _Connection(),
        source_head="a" * 40,
        write_metrics=_write_metrics(),
    )
    changed_metrics = collect_health_snapshot(
        _Connection(),
        source_head="a" * 40,
        write_metrics=_write_metrics(
            health_attempts=10,
            health_suppressed=9,
            decision_attempts=10,
            decision_suppressed=7,
        ),
    )
    changed_metrics["observed_at"] = first["observed_at"]
    changed_metrics["snapshot_hash"] = compute_health_snapshot_hash(
        changed_metrics
    )

    assert first["write_metrics"]["health"]["suppression_ratio"] == 0.75
    assert first["write_metrics"]["decision"]["suppression_ratio"] == 0.4
    assert first["snapshot_hash"] != changed_metrics["snapshot_hash"]
    assert compute_health_semantic_hash(first) == compute_health_semantic_hash(
        changed_metrics
    )


def test_persists_health_snapshot_append_only() -> None:
    connection = _Connection()
    snapshot = collect_health_snapshot(connection, source_head="a" * 40)

    result = persist_health_snapshot(connection, snapshot)

    assert result["status"] == "PERSISTED"
    assert len(connection.snapshots) == 1
    assert not any(
        token in sql.upper()
        for sql, _ in connection.calls
        for token in ("UPDATE ", "DELETE ")
    )


def test_health_write_metrics_count_only_rows_inserted_after_artifact_dedup() -> None:
    connection = _Connection()
    snapshot = collect_health_snapshot(connection, source_head="a" * 40)
    connection.artifacts.add(snapshot["snapshot_hash"])

    result = persist_health_snapshot(connection, snapshot)

    canonical_payload_bytes = len(
        json.dumps(
            snapshot,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    assert result["status"] == "PERSISTED"
    assert result["rows_written"] == 1
    assert result["payload_bytes_written"] == canonical_payload_bytes


def test_same_semantic_health_is_suppressed_before_heartbeat() -> None:
    connection = _Connection()
    first = collect_health_snapshot(connection, source_head="a" * 40)
    first["observed_at"] = "2026-07-10T12:00:00Z"
    first["snapshot_hash"] = compute_health_snapshot_hash(first)

    first_result = persist_health_snapshot(
        connection,
        first,
        heartbeat_seconds=300,
    )

    connection.database_now = datetime(
        2026, 7, 10, 12, 4, 59, tzinfo=timezone.utc
    )
    repeated = copy.deepcopy(first)
    repeated["observed_at"] = "2026-07-10T12:04:59Z"
    repeated["snapshot_hash"] = compute_health_snapshot_hash(repeated)
    repeated_result = persist_health_snapshot(
        connection,
        repeated,
        heartbeat_seconds=300,
    )

    assert first_result["status"] == "PERSISTED"
    assert first_result["emission_reason"] == "STATE_DELTA"
    assert repeated_result == {
        "status": "SUPPRESSED_NO_DELTA",
        "snapshot_hash": repeated["snapshot_hash"],
        "semantic_state_changed": False,
        "heartbeat_due": False,
        "rows_written": 0,
        "payload_bytes_written": 0,
        "writes_suppressed": 1,
    }
    assert len(connection.snapshots) == 1


def test_same_semantic_health_emits_at_bounded_heartbeat() -> None:
    connection = _Connection()
    first = collect_health_snapshot(connection, source_head="a" * 40)
    first["observed_at"] = "2026-07-10T12:00:00Z"
    first["snapshot_hash"] = compute_health_snapshot_hash(first)
    persist_health_snapshot(connection, first, heartbeat_seconds=300)

    connection.database_now = datetime(
        2026, 7, 10, 12, 5, tzinfo=timezone.utc
    )
    heartbeat = copy.deepcopy(first)
    heartbeat["observed_at"] = "2026-07-10T12:05:00Z"
    heartbeat["snapshot_hash"] = compute_health_snapshot_hash(heartbeat)
    result = persist_health_snapshot(
        connection,
        heartbeat,
        heartbeat_seconds=300,
    )

    assert result["status"] == "PERSISTED"
    assert result["emission_reason"] == "HEARTBEAT"
    assert result["semantic_state_changed"] is False
    assert result["heartbeat_due"] is True
    assert result["rows_written"] == 2
    assert result["payload_bytes_written"] > 0
    assert result["writes_suppressed"] == 0
    assert len(connection.snapshots) == 2


def test_semantic_health_delta_emits_before_heartbeat() -> None:
    connection = _Connection()
    first = collect_health_snapshot(connection, source_head="a" * 40)
    first["observed_at"] = "2026-07-10T12:00:00Z"
    first["snapshot_hash"] = compute_health_snapshot_hash(first)
    persist_health_snapshot(connection, first, heartbeat_seconds=300)

    connection.database_now = datetime(
        2026, 7, 10, 12, 0, 1, tzinfo=timezone.utc
    )
    changed = copy.deepcopy(first)
    changed["observed_at"] = "2026-07-10T12:00:01Z"
    changed["backlog"]["untrained_source_cycles"] += 1
    changed["snapshot_hash"] = compute_health_snapshot_hash(changed)
    result = persist_health_snapshot(
        connection,
        changed,
        heartbeat_seconds=300,
    )

    assert result["status"] == "PERSISTED"
    assert result["emission_reason"] == "STATE_DELTA"
    assert result["semantic_state_changed"] is True
    assert result["heartbeat_due"] is False
    assert len(connection.snapshots) == 2


def test_database_clock_bounds_heartbeat_despite_application_clock_skew() -> None:
    connection = _Connection()
    first = collect_health_snapshot(connection, source_head="a" * 40)
    first["observed_at"] = "2026-07-10T20:00:00Z"
    first["snapshot_hash"] = compute_health_snapshot_hash(first)
    persist_health_snapshot(connection, first, heartbeat_seconds=300)

    connection.database_now = datetime(
        2026, 7, 10, 12, 5, tzinfo=timezone.utc
    )
    heartbeat = copy.deepcopy(first)
    heartbeat["observed_at"] = "2026-07-10T08:00:00Z"
    heartbeat["snapshot_hash"] = compute_health_snapshot_hash(heartbeat)

    result = persist_health_snapshot(
        connection,
        heartbeat,
        heartbeat_seconds=300,
    )

    assert result["status"] == "PERSISTED"
    assert result["emission_reason"] == "HEARTBEAT"


def test_database_clock_regression_fails_closed_without_another_snapshot() -> None:
    connection = _Connection()
    first = collect_health_snapshot(connection, source_head="a" * 40)
    first["observed_at"] = "2026-07-10T12:00:00Z"
    first["snapshot_hash"] = compute_health_snapshot_hash(first)
    persist_health_snapshot(connection, first, heartbeat_seconds=300)

    connection.database_now = datetime(
        2026, 7, 10, 11, 59, 59, tzinfo=timezone.utc
    )
    repeated = copy.deepcopy(first)
    repeated["observed_at"] = "2026-07-10T12:01:00Z"
    repeated["snapshot_hash"] = compute_health_snapshot_hash(repeated)

    with pytest.raises(
        AlrHealthRepositoryError,
        match="health_database_clock_regressed",
    ):
        persist_health_snapshot(
            connection,
            repeated,
            heartbeat_seconds=300,
        )

    assert connection.rollbacks == 1
    assert len(connection.snapshots) == 1


def test_metric_only_change_is_suppressed_then_checkpointed_at_heartbeat() -> None:
    connection = _Connection()
    first = collect_health_snapshot(
        connection,
        source_head="a" * 40,
        write_metrics=_write_metrics(),
    )
    first["observed_at"] = "2026-07-10T12:00:00Z"
    first["snapshot_hash"] = compute_health_snapshot_hash(first)
    persist_health_snapshot(connection, first, heartbeat_seconds=300)

    latest_metrics = _write_metrics(
        health_attempts=10,
        health_suppressed=9,
        decision_attempts=10,
        decision_suppressed=7,
    )
    connection.database_now = datetime(
        2026, 7, 10, 12, 0, 1, tzinfo=timezone.utc
    )
    changed = copy.deepcopy(first)
    changed["observed_at"] = "2026-07-10T12:00:01Z"
    changed["write_metrics"] = latest_metrics
    changed["snapshot_hash"] = compute_health_snapshot_hash(changed)
    suppressed = persist_health_snapshot(
        connection,
        changed,
        heartbeat_seconds=300,
    )

    assert suppressed["status"] == "SUPPRESSED_NO_DELTA"
    assert len(connection.snapshots) == 1

    connection.database_now = datetime(
        2026, 7, 10, 12, 5, tzinfo=timezone.utc
    )
    heartbeat = copy.deepcopy(changed)
    heartbeat["observed_at"] = "2026-07-10T12:05:00Z"
    heartbeat["snapshot_hash"] = compute_health_snapshot_hash(heartbeat)
    persisted = persist_health_snapshot(
        connection,
        heartbeat,
        heartbeat_seconds=300,
    )

    assert persisted["emission_reason"] == "HEARTBEAT"
    assert connection.latest_health_payload is not None
    assert connection.latest_health_payload["write_metrics"] == latest_metrics


def test_rejects_inconsistent_write_metric_ratio() -> None:
    invalid = _write_metrics()
    invalid["decision"]["suppression_ratio"] = 0.9

    with pytest.raises(
        AlrHealthRepositoryError,
        match="health_write_metrics_decision_ratio_mismatch",
    ):
        collect_health_snapshot(
            _Connection(),
            source_head="a" * 40,
            write_metrics=invalid,
        )


def test_rejects_inconsistent_feedback_metric_ratio() -> None:
    invalid = _write_metrics()
    invalid["feedback"]["persisted_ratio"] = 0.5

    with pytest.raises(
        AlrHealthRepositoryError,
        match="health_write_metrics_feedback_ratio_mismatch",
    ):
        collect_health_snapshot(
            _Connection(),
            source_head="a" * 40,
            write_metrics=invalid,
        )


def test_old_hole_alert_clears_only_after_anchor_partition_repair() -> None:
    before = collect_health_snapshot(
        _Connection(fresh_raw_only_count=1, ingest_lag_seconds=0.0),
        source_head="a" * 40,
    )
    after = collect_health_snapshot(
        _Connection(fresh_raw_only_count=0, ingest_lag_seconds=0.0),
        source_head="a" * 40,
    )

    assert before["ingestion"]["status"] == "DEGRADED"
    assert before["ingestion"]["alert"] is True
    assert after["ingestion"]["status"] == "HEALTHY"
    assert after["ingestion"]["alert"] is False


def test_v155_is_append_only_health_under_alr_schema() -> None:
    migration = Path(__file__).parents[3] / "sql/migrations/V155__alr_health_state.sql"
    source = migration.read_text(encoding="utf-8")

    assert "learning.alr_health_events" in source
    assert "health_snapshot" in source
    assert "REVOKE UPDATE, DELETE ON learning.alr_health_events FROM PUBLIC" in source
    assert "DROP TABLE" not in source
    assert "ALTER TABLE trading." not in source
