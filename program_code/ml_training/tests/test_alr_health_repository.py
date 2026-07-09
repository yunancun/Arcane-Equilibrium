from __future__ import annotations

from pathlib import Path
from typing import Any

from ml_training.alr_health_repository import (
    collect_health_snapshot,
    persist_health_snapshot,
)


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.snapshots: set[str] = set()
        self.commits = 0
        self.rollbacks = 0

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
        if "FROM learning.alr_watermark_events" in sql:
            self.row = {
                "source_ts": "2026-07-09T12:00:00Z",
                "source_scan_id": "scan-1",
                "source_hash": "a" * 64,
            }
        elif "AS source_event_count" in sql:
            self.row = {
                "source_event_count": 64,
                "scanner_backlog_count": 3,
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
    snapshot = collect_health_snapshot(_Connection(), source_head="a" * 40)

    assert snapshot["schema_version"] == "alr_health_snapshot_v1"
    assert snapshot["watermark"]["source_scan_id"] == "scan-1"
    assert snapshot["backlog"] == {"scanner_cycles": 3, "outcome_feedback": 1}
    assert snapshot["training"]["run_count"] == 2
    assert snapshot["evidence_gaps"]["deferred_feedback_count"] == 1
    assert snapshot["restart_recovery"]["source_duplicate_key_count"] == 0
    assert snapshot["retention"]["payload_bytes"] == 0
    assert snapshot["failure"]["count"] == 0
    assert snapshot["authority_counters"] == {
        "run_authority_mismatch_count": 0,
        "feedback_authority_mismatch_count": 0,
        "exchange_contact_count": 0,
        "trading_action_count": 0,
        "proof_claim_count": 0,
        "serving_or_promotion_count": 0,
    }


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


def test_v155_is_append_only_health_under_alr_schema() -> None:
    migration = Path(__file__).parents[3] / "sql/migrations/V155__alr_health_state.sql"
    source = migration.read_text(encoding="utf-8")

    assert "learning.alr_health_events" in source
    assert "health_snapshot" in source
    assert "REVOKE UPDATE, DELETE ON learning.alr_health_events FROM PUBLIC" in source
    assert "DROP TABLE" not in source
    assert "ALTER TABLE trading." not in source
