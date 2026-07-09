from __future__ import annotations

from pathlib import Path
from typing import Any

from ml_training.alr_health_repository import (
    collect_health_snapshot,
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
        self.snapshots: set[str] = set()
        self.commits = 0
        self.rollbacks = 0
        self.fresh_raw_only_count = fresh_raw_only_count
        self.ingest_lag_seconds = ingest_lag_seconds

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
        if "AS source_event_count" in sql:
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
            self.connection.snapshots.add(str(params[0]))
            self.row = None

    def fetchone(self) -> Any:
        return self.row


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
