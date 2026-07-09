from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ml_training.alr_consumer_repository import (
    FRESH_LANE,
    HISTORICAL_LANE,
    AlrConsumerRepositoryError,
    fetch_fresh_lane_rows,
    fetch_fresh_raw_only_holes,
    fetch_historical_lane_rows,
    load_consumer_state,
    record_consumer_event,
    start_consumer_session,
)


class _Connection:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.scanner_rows: list[dict[str, Any]] = []
        self.source_identities: dict[tuple[Any, str], str] = {}
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
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
        if sql.startswith("INSERT INTO learning.alr_consumer_events"):
            assert params is not None
            self.connection.events.append(
                {
                    "event_id": params[0],
                    "session_id": params[1],
                    "event_kind": params[2],
                    "lane": params[3],
                    "source_ts": params[4],
                    "source_scan_id": params[5],
                    "source_hash": params[6],
                }
            )
            self.row = None
        elif "SELECT started.session_id" in sql:
            open_sessions: list[str] = []
            for event in self.connection.events:
                if event["event_kind"] == "SESSION_STARTED":
                    session_id = event["session_id"]
                    terminal = any(
                        item["session_id"] == session_id
                        and item["event_kind"]
                        in {"SESSION_STOPPED", "SESSION_FAILED", "UNCLEAN_RECOVERY"}
                        for item in self.connection.events
                    )
                    if not terminal:
                        open_sessions.append(session_id)
            self.row = None if not open_sessions else {"session_id": open_sessions[-1]}
        elif "FROM learning.alr_consumer_events WHERE lane = %s" in sql:
            assert params is not None
            lane = params[0]
            rows = [
                event
                for event in self.connection.events
                if event["lane"] == lane
                and event["event_kind"] in {"LANE_BOOTSTRAPPED", "LANE_CURSOR_ADVANCED"}
            ]
            if "event_kind = 'LANE_BOOTSTRAPPED'" in sql:
                rows = [row for row in rows if row["event_kind"] == "LANE_BOOTSTRAPPED"]
            rows.sort(
                key=lambda row: (row["source_ts"], row["source_scan_id"], row["event_id"]),
                reverse="DESC" in sql,
            )
            self.row = None if not rows else rows[0]
        elif "SELECT source_hash FROM learning.alr_source_events" in sql:
            assert params is not None
            source_hash = self.connection.source_identities.get((params[1], params[2]))
            self.row = None if source_hash is None else {"source_hash": source_hash}
        elif "FROM trading.scanner_snapshots AS scanner" in sql:
            self.row = list(self.connection.scanner_rows)

    def fetchone(self) -> Any:
        return self.row

    def fetchall(self) -> Any:
        return self.row


def test_unclean_recovery_closes_each_prior_session_exactly_once() -> None:
    connection = _Connection()
    first = "00000000-0000-0000-0000-000000000001"
    second = "00000000-0000-0000-0000-000000000002"
    third = "00000000-0000-0000-0000-000000000003"

    assert start_consumer_session(connection, session_id=first) is None
    assert start_consumer_session(connection, session_id=second) == first
    assert start_consumer_session(connection, session_id=third) == second

    recoveries = [
        event for event in connection.events if event["event_kind"] == "UNCLEAN_RECOVERY"
    ]
    assert [event["session_id"] for event in recoveries] == [first, second]


def test_composite_lane_cursor_refuses_rewind_or_duplicate_append() -> None:
    connection = _Connection()
    connection.source_identities = {
        ("2026-07-09T12:00:00Z", "scan-b"): "a" * 64,
        ("2026-07-09T12:00:00Z", "scan-c"): "b" * 64,
        ("2026-07-09T12:00:00Z", "scan-a"): "c" * 64,
    }
    session_id = "00000000-0000-0000-0000-000000000001"
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="LANE_BOOTSTRAPPED",
        lane=FRESH_LANE,
        source_ts="2026-07-09T12:00:00Z",
        source_scan_id="scan-b",
        source_hash="a" * 64,
    )
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="LANE_CURSOR_ADVANCED",
        lane=FRESH_LANE,
        source_ts="2026-07-09T12:00:00Z",
        source_scan_id="scan-c",
        source_hash="b" * 64,
    )

    with pytest.raises(AlrConsumerRepositoryError, match="consumer_cursor_non_monotonic"):
        record_consumer_event(
            connection,
            session_id=session_id,
            event_kind="LANE_CURSOR_ADVANCED",
            lane=FRESH_LANE,
            source_ts="2026-07-09T12:00:00Z",
            source_scan_id="scan-a",
            source_hash="c" * 64,
        )


def test_cursor_event_requires_hash_matching_source_lineage() -> None:
    connection = _Connection()
    session_id = "00000000-0000-0000-0000-000000000001"
    connection.source_identities[("2026-07-09T12:00:00Z", "scan-0")] = "a" * 64

    with pytest.raises(AlrConsumerRepositoryError, match="consumer_cursor_source_missing"):
        record_consumer_event(
            connection,
            session_id=session_id,
            event_kind="LANE_BOOTSTRAPPED",
            lane=FRESH_LANE,
            source_ts="2026-07-09T11:59:00Z",
            source_scan_id="missing",
            source_hash="b" * 64,
        )

    with pytest.raises(AlrConsumerRepositoryError, match="consumer_cursor_source_hash_mismatch"):
        record_consumer_event(
            connection,
            session_id=session_id,
            event_kind="LANE_BOOTSTRAPPED",
            lane=FRESH_LANE,
            source_ts="2026-07-09T12:00:00Z",
            source_scan_id="scan-0",
            source_hash="b" * 64,
        )

    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="LANE_BOOTSTRAPPED",
        lane=FRESH_LANE,
        source_ts="2026-07-09T12:00:00Z",
        source_scan_id="scan-0",
        source_hash="a" * 64,
    )


def test_cursor_recovery_uses_composite_identity_not_recorded_event_order() -> None:
    connection = _Connection()
    connection.events = [
        {
            "event_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000001",
            "event_kind": "LANE_BOOTSTRAPPED",
            "lane": FRESH_LANE,
            "source_ts": "2026-07-09T12:00:00Z",
            "source_scan_id": "scan-0",
            "source_hash": "0" * 64,
        },
        {
            "event_id": "00000000-0000-0000-0000-000000000002",
            "session_id": "00000000-0000-0000-0000-000000000001",
            "event_kind": "LANE_CURSOR_ADVANCED",
            "lane": FRESH_LANE,
            "source_ts": "2026-07-09T12:02:00Z",
            "source_scan_id": "scan-2",
            "source_hash": "2" * 64,
        },
        {
            "event_id": "00000000-0000-0000-0000-000000000003",
            "session_id": "00000000-0000-0000-0000-000000000001",
            "event_kind": "LANE_CURSOR_ADVANCED",
            "lane": FRESH_LANE,
            "source_ts": "2026-07-09T12:01:00Z",
            "source_scan_id": "scan-1",
            "source_hash": "1" * 64,
        },
    ]

    state = load_consumer_state(connection)

    assert state["fresh_cursor"]["source_scan_id"] == "scan-2"


def test_fresh_catch_up_includes_already_ingested_rows_and_history_is_separate() -> None:
    connection = _Connection()
    connection.scanner_rows = [{"ts": "2026-07-09T12:01:00Z", "scan_id": "scan-2"}]
    fresh_cursor = {
        "source_ts": "2026-07-09T12:00:00Z",
        "source_scan_id": "scan-1",
    }

    assert fetch_fresh_lane_rows(
        connection,
        cursor_state=fresh_cursor,
        limit=32,
    ) == connection.scanner_rows
    fresh_sql, fresh_params = connection.calls[-1]
    assert "(scanner.ts, scanner.scan_id) >" in fresh_sql
    assert "NOT EXISTS" not in fresh_sql
    assert fresh_params == ("2026-07-09T12:00:00Z", "scan-1", 32)

    assert fetch_fresh_raw_only_holes(
        connection,
        anchor_cursor=fresh_cursor,
        limit=4,
    ) == connection.scanner_rows
    repair_sql, repair_params = connection.calls[-1]
    assert "(scanner.ts, scanner.scan_id) >" in repair_sql
    assert "NOT EXISTS" in repair_sql
    assert "ORDER BY scanner.ts DESC, scanner.scan_id DESC" in repair_sql
    assert repair_params == (
        "2026-07-09T12:00:00Z",
        "scan-1",
        "trading.scanner_snapshots",
        4,
    )

    assert fetch_historical_lane_rows(
        connection,
        after_cursor=None,
        before_cursor=fresh_cursor,
        limit=8,
    ) == connection.scanner_rows
    history_sql, history_params = connection.calls[-1]
    assert "(scanner.ts, scanner.scan_id) <" in history_sql
    assert history_params == ("2026-07-09T12:00:00Z", "scan-1", 8)


def test_v156_and_role_contract_are_append_only_learning_scope() -> None:
    root = Path(__file__).parents[3]
    migration = (root / "sql/migrations/V156__alr_consumer_freshness_state.sql").read_text(
        encoding="utf-8"
    )
    contract = (root / "sql/contracts/alr_shadow_role_contract_v1.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS learning.alr_consumer_events" in migration
    for field in (
        "raw_latest_ts",
        "alr_latest_source_ts",
        "ingest_lag_seconds",
        "fresh_raw_only_count",
        "historical_backfill_remaining",
        "notifications_received",
        "notifications_consumed",
        "notifications_duplicate",
        "notifications_invalid",
        "last_success_at",
        "failure_count",
        "restart_count",
    ):
        assert field in migration
    assert "REVOKE UPDATE, DELETE ON learning.alr_consumer_events" in migration
    assert "alr_source_events_cursor_lineage_uniq" in migration
    assert "alr_consumer_events_source_lineage_fk" in migration
    assert "alr_health_events_freshness_nonnegative_check" in migration
    assert "NOT VALID" not in migration
    assert "conrelid = 'learning.alr_consumer_events'::regclass" in migration
    assert "lane, source_ts DESC, source_scan_id DESC, event_id DESC" in migration
    assert "session_id, recorded_at ASC, event_id ASC" in migration
    assert "event_kind, recorded_at DESC" in migration
    assert "GRANT SELECT, INSERT ON TABLE learning.alr_consumer_events TO alr_shadow" in contract
    for mutation in ("INSERT INTO trading.", "UPDATE trading.", "DELETE FROM trading."):
        assert mutation not in migration
