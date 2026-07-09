from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ml_training.alr_retention_repository import run_retention_pass


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)


def _entry(*, state: str = "ACTIVE", referenced: bool = False) -> dict[str, Any]:
    return {
        "cache_key": "cache-1",
        "cache_artifact_hash": "a" * 64,
        "cache_kind": "scanner_statistical_features_v1",
        "owner_scope": "ALR_OWNED_REBUILDABLE",
        "rebuildable": True,
        "cache_state": state,
        "created_at": NOW - timedelta(days=2),
        "quarantined_at": NOW - timedelta(hours=2) if state == "QUARANTINED" else None,
        "is_referenced": referenced,
        "cache_content_hash": "b" * 64,
    }


class _Connection:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.events: list[str] = []
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
        if "DELETE FROM learning.alr_derived_cache_entries" in sql:
            self.connection.entry["deleted"] = True
            self.row = (self.connection.entry["cache_key"],)
        elif "FROM learning.alr_derived_cache_entries AS cache" in sql:
            self.row = [] if self.connection.entry.get("deleted") else [self.connection.entry]
        elif "SET cache_state = 'QUARANTINED'" in sql:
            self.connection.entry["cache_state"] = "QUARANTINED"
            self.connection.entry["quarantined_at"] = params[0]
            self.row = (self.connection.entry["cache_key"],)
        elif "SET cache_state = 'ACTIVE'" in sql:
            self.connection.entry["cache_state"] = "ACTIVE"
            self.connection.entry["quarantined_at"] = None
            self.row = (self.connection.entry["cache_key"],)
        elif "INSERT INTO learning.alr_retention_events" in sql:
            self.connection.events.append(str(params[0]))
            self.row = None

    def fetchone(self) -> Any:
        return self.row

    def fetchall(self) -> Any:
        return self.row


def test_first_unreferenced_pass_quarantines_and_records_event() -> None:
    connection = _Connection(_entry())

    result = run_retention_pass(connection, now=NOW, grace_seconds=3600, limit=4)

    assert result == {
        "scanned": 1,
        "quarantined": 1,
        "restored": 0,
        "swept": 0,
        "retained": 0,
        "skipped": 0,
    }
    assert connection.entry["cache_state"] == "QUARANTINED"
    assert len(connection.events) == 1
    assert not any("DELETE FROM" in sql for sql, _ in connection.calls)


def test_grace_expired_unreferenced_pass_sweeps_only_cache_entry() -> None:
    connection = _Connection(_entry(state="QUARANTINED"))

    result = run_retention_pass(connection, now=NOW, grace_seconds=3600, limit=4)

    assert result["swept"] == 1
    assert connection.entry["deleted"] is True
    assert len(connection.events) == 1
    delete_sql = [sql for sql, _ in connection.calls if "DELETE FROM" in sql]
    assert len(delete_sql) == 1
    assert "learning.alr_derived_cache_entries" in delete_sql[0]


def test_referenced_quarantine_is_restored_not_deleted() -> None:
    connection = _Connection(_entry(state="QUARANTINED", referenced=True))

    result = run_retention_pass(connection, now=NOW, grace_seconds=3600, limit=4)

    assert result["restored"] == 1
    assert result["swept"] == 0
    assert connection.entry["cache_state"] == "ACTIVE"


def test_v154_is_limited_to_alr_owned_rebuildable_cache() -> None:
    migration = (
        Path(__file__).parents[3]
        / "sql/migrations/V154__alr_retention_guardian.sql"
    )
    source = migration.read_text(encoding="utf-8")

    assert "learning.alr_derived_cache_entries" in source
    assert "ALR_OWNED_REBUILDABLE" in source
    assert "learning.alr_retention_events" in source
    assert "DELETE FROM learning.alr_derived_cache_entries" not in source
    assert "DROP TABLE" not in source
    assert "ALTER TABLE trading." not in source
