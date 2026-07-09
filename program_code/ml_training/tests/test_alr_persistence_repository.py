from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ml_training.alr_persistence_repository import (
    AlrPersistenceConflict,
    AlrPersistenceError,
    build_persistence_plan,
    fetch_unseen_scanner_snapshots,
    fetch_unseen_scanner_snapshots_after,
    load_restart_state,
    persist_scanner_cycle,
)
from ml_training.alr_scanner_snapshot_adapter import adapt_scanner_snapshot


def _cycle() -> dict[str, object]:
    return adapt_scanner_snapshot(
        {
            "ts": "2026-07-09T12:00:00Z",
            "scan_id": "scan-1783598400000",
            "active_symbols": ["BTCUSDT", "ETHUSDT"],
            "added": ["ETHUSDT"],
            "removed": [],
            "rejected_count": 3,
            "scan_duration_ms": 47,
            "candidates": [{"symbol": "BTCUSDT", "final_score": 42.5}],
            "config": {"edge_routing": {"enabled": True}},
        }
    )


def test_builds_hash_bound_append_only_plan_for_new_scanner_cycle() -> None:
    plan = build_persistence_plan(_cycle())

    assert plan["source_key"] == "scan-1783598400000|2026-07-09T12:00:00Z"
    assert plan["source_hash"] == _cycle()["source_hash"]
    assert plan["source_table"] == "trading.scanner_snapshots"
    assert plan["ingest_event_kind"] == "PERSISTED"
    assert plan["watermark_event_kind"] == "ADVANCED"
    assert len(plan["ingest_event_hash"]) == 64
    assert plan["authority"] == {
        "exchange_authority": False,
        "trading_authority": False,
        "proof_authority": False,
        "serving_authority": False,
        "promotion_authority": False,
    }


class _LedgerConnection:
    def __init__(self) -> None:
        self.source_events: dict[str, dict[str, Any]] = {}
        self.ingest_events: list[dict[str, Any]] = []
        self.watermark_events: list[dict[str, Any]] = []
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.unseen_rows: list[dict[str, Any]] = []
        self.mapping_rows = False
        self.hide_source_once = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> "_LedgerCursor":
        return _LedgerCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _LedgerCursor:
    def __init__(self, connection: _LedgerConnection) -> None:
        self.connection = connection
        self.row: Any = None
        self.columns: tuple[str, ...] = ()

    def __enter__(self) -> "_LedgerCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        if "SELECT source_hash" in sql:
            self.columns = ("source_hash",)
            source_key = str(params[1])
            source = self.connection.source_events.get(source_key)
            if self.connection.hide_source_once:
                self.connection.hide_source_once = False
                self.row = None
            else:
                self.row = None if source is None else (source["source_hash"],)
        elif "FROM trading.scanner_snapshots AS scanner" in sql:
            self.row = self.connection.unseen_rows
        elif "INSERT INTO learning.alr_source_events" in sql:
            source_key = str(params[1])
            if source_key not in self.connection.source_events:
                self.connection.source_events[source_key] = {
                    "source_hash": params[4],
                    "source_scan_id": params[2],
                    "source_ts": params[3],
                }
                self.row = (params[4],)
            else:
                self.row = None
        elif "INSERT INTO learning.alr_ingest_events" in sql:
            self.connection.ingest_events.append(
                {"event_kind": params[2], "source_key": params[1]}
            )
        elif "INSERT INTO learning.alr_watermark_events" in sql:
            self.connection.watermark_events.append(
                {
                    "event_kind": params[5],
                    "source_key": params[1],
                    "source_ts": params[2],
                    "source_hash": params[4],
                }
            )
        elif "SELECT source_key FROM learning.alr_source_events" in sql:
            self.columns = ("source_key",)
            self.row = [(source_key,) for source_key in self.connection.source_events]
        elif "SELECT source_ts, source_scan_id, source_hash" in sql:
            self.columns = ("source_ts", "source_scan_id", "source_hash")
            advanced = [
                item
                for item in self.connection.watermark_events
                if item["event_kind"] == "ADVANCED"
            ]
            self.row = (
                None
                if not advanced
                else (
                    advanced[-1]["source_ts"],
                    self.connection.source_events[advanced[-1]["source_key"]]["source_scan_id"],
                    advanced[-1]["source_hash"],
                )
            )

    def fetchone(self) -> Any:
        if self.connection.mapping_rows and isinstance(self.row, tuple):
            return dict(zip(self.columns, self.row))
        return self.row

    def fetchall(self) -> Any:
        if self.connection.mapping_rows and isinstance(self.row, list):
            return [dict(zip(self.columns, row)) for row in self.row]
        return self.row


def test_persists_duplicate_and_restart_state_without_mutation() -> None:
    connection = _LedgerConnection()

    first = persist_scanner_cycle(connection, _cycle())
    second = persist_scanner_cycle(connection, _cycle())
    restart = load_restart_state(connection)

    assert first["status"] == "PERSISTED"
    assert second["status"] == "DUPLICATE"
    assert connection.commits == 2
    assert len(connection.source_events) == 1
    assert [item["event_kind"] for item in connection.ingest_events] == [
        "PERSISTED",
        "DUPLICATE",
    ]
    assert [item["event_kind"] for item in connection.watermark_events] == ["ADVANCED"]
    assert restart["processed_source_keys"] == {
        "scan-1783598400000|2026-07-09T12:00:00Z"
    }
    assert restart["watermark"] == {
        "ts": "2026-07-09T12:00:00Z",
        "scan_id": "scan-1783598400000",
        "source_hash": _cycle()["source_hash"],
    }
    assert not any(
        token in sql.upper()
        for sql, _ in connection.calls
        for token in ("UPDATE ", "DELETE ")
    )


def test_rejects_same_source_key_with_different_hash_and_rolls_back() -> None:
    connection = _LedgerConnection()
    persist_scanner_cycle(connection, _cycle())
    conflicting = adapt_scanner_snapshot(
        {
            **_cycle()["payload"],
            "candidates": [{"symbol": "BTCUSDT", "final_score": 999.0}],
        }
    )

    with pytest.raises(AlrPersistenceConflict, match="source_hash_conflict"):
        persist_scanner_cycle(connection, conflicting)

    assert connection.rollbacks == 1
    assert len(connection.source_events) == 1
    assert [item["event_kind"] for item in connection.ingest_events] == ["PERSISTED"]


def test_supports_mapping_rows_from_real_dict_cursor() -> None:
    connection = _LedgerConnection()
    connection.mapping_rows = True

    persist_scanner_cycle(connection, _cycle())
    duplicate = persist_scanner_cycle(connection, _cycle())
    restart = load_restart_state(connection)

    assert duplicate["status"] == "DUPLICATE"
    assert restart["watermark"]["scan_id"] == "scan-1783598400000"


def test_concurrent_source_insert_race_is_normalized_to_duplicate() -> None:
    connection = _LedgerConnection()
    persist_scanner_cycle(connection, _cycle())
    connection.hide_source_once = True

    result = persist_scanner_cycle(connection, _cycle())

    assert result["status"] == "DUPLICATE"
    assert connection.rollbacks == 0
    assert len(connection.source_events) == 1


def test_reads_only_unseen_scanner_snapshots_with_a_bounded_query() -> None:
    connection = _LedgerConnection()
    connection.unseen_rows = [{"scan_id": "scan-2", "ts": "2026-07-09T12:01:00Z"}]

    rows = fetch_unseen_scanner_snapshots(connection, limit=2)

    assert rows == connection.unseen_rows
    scanner_calls = [call for call in connection.calls if "trading.scanner_snapshots" in call[0]]
    assert len(scanner_calls) == 1
    sql, params = scanner_calls[0]
    assert "NOT EXISTS" in sql
    assert params == ("trading.scanner_snapshots", 2)
    assert "UPDATE" not in sql.upper()
    assert "DELETE" not in sql.upper()


def test_reads_only_unseen_scanner_rows_after_a_valid_utc_cursor() -> None:
    connection = _LedgerConnection()
    connection.unseen_rows = [{"scan_id": "scan-3", "ts": "2026-07-09T12:02:00Z"}]

    rows = fetch_unseen_scanner_snapshots_after(
        connection,
        after_ts="2026-07-09T12:01:00Z",
        limit=3,
    )

    assert rows == connection.unseen_rows
    scanner_calls = [call for call in connection.calls if "trading.scanner_snapshots" in call[0]]
    assert len(scanner_calls) == 1
    sql, params = scanner_calls[0]
    assert "scanner.ts > %s" in sql
    assert "NOT EXISTS" in sql
    assert params == ("2026-07-09T12:01:00.000000+00:00", "trading.scanner_snapshots", 3)
    assert "UPDATE" not in sql.upper()
    assert "DELETE" not in sql.upper()


@pytest.mark.parametrize("after_ts", ["", "2026-07-09T12:01:00", "not-a-timestamp"])
def test_rejects_an_ambiguous_or_invalid_reconciliation_cursor(after_ts: str) -> None:
    with pytest.raises(AlrPersistenceError, match="scanner_fetch_after_timestamp_invalid"):
        fetch_unseen_scanner_snapshots_after(
            _LedgerConnection(),
            after_ts=after_ts,
            limit=3,
        )


def test_repository_keeps_alr_shadow_reads_select_only() -> None:
    connection = _LedgerConnection()

    persist_scanner_cycle(connection, _cycle())

    assert all("FOR SHARE" not in sql.upper() for sql, _ in connection.calls)


def test_v151_is_append_only_alr_owned_and_non_destructive() -> None:
    migration = (
        Path(__file__).parents[3]
        / "sql/migrations/V151__alr_persistence_foundation.sql"
    )
    source = migration.read_text(encoding="utf-8")

    for table in (
        "alr_artifact_nodes",
        "alr_source_events",
        "alr_ingest_events",
        "alr_watermark_events",
        "alr_provenance_edges",
    ):
        assert f"learning.{table}" in source
        assert f"REVOKE UPDATE, DELETE ON learning.{table}" in source
    assert "GRANT USAGE ON SCHEMA learning TO trading_ai" in source
    for scanner_mutation in (
        "INSERT INTO trading.scanner_snapshots",
        "UPDATE trading.scanner_snapshots",
        "DELETE FROM trading.scanner_snapshots",
        "ALTER TABLE trading.scanner_snapshots",
    ):
        assert scanner_mutation not in source
    assert "DROP TABLE" not in source
    assert "ALTER TABLE trading." not in source
