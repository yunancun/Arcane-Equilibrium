from __future__ import annotations

import json
from typing import Any

import pytest

from ml_training import alr_freshness_runtime as runtime


def _row(scan_id: str, ts: str) -> dict[str, object]:
    return {
        "ts": ts,
        "scan_id": scan_id,
        "active_symbols": ["BTCUSDT"],
        "added": ["BTCUSDT"],
        "removed": [],
        "rejected_count": 0,
        "scan_duration_ms": 1,
        "candidates": [{"symbol": "BTCUSDT"}],
        "config": {},
    }


class _Connection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _no_existing_source_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime,
        "fetch_persisted_scanner_identity",
        lambda connection, *, scan_id, source_ts: None,
    )
    monkeypatch.setattr(
        runtime,
        "fetch_fresh_raw_only_holes",
        lambda connection, *, anchor_cursor, limit: [],
    )


def _parse(channel: str, payload: str) -> dict[str, Any]:
    if channel != "alr_scanner_snapshot_v1":
        raise ValueError("notification_channel_invalid")
    return json.loads(payload)


def test_exact_duplicate_and_out_of_order_notifications_never_advance_fresh_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    rows = {
        "scan-new": _row("scan-new", "2026-07-09T12:02:00Z"),
        "scan-late": _row("scan-late", "2026-07-09T11:59:00Z"),
    }
    monkeypatch.setattr(
        runtime,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )
    monkeypatch.setattr(
        runtime,
        "fetch_scanner_snapshot_by_identity",
        lambda connection, *, scan_id, ts_ms: rows[scan_id],
    )
    monkeypatch.setattr(
        runtime,
        "persist_scanner_cycle",
        lambda connection, cycle: {"status": "PERSISTED"},
    )
    monkeypatch.setattr(
        runtime,
        "record_consumer_event",
        lambda connection, **kwargs: events.append(kwargs["event_kind"]),
    )
    notifications = [
        (
            "alr_scanner_snapshot_v1",
            json.dumps({"scan_id": "scan-new", "ts_ms": 1783598520000}),
        ),
        (
            "alr_scanner_snapshot_v1",
            json.dumps({"scan_id": "scan-new", "ts_ms": 1783598520000}),
        ),
        (
            "alr_scanner_snapshot_v1",
            json.dumps({"scan_id": "scan-late", "ts_ms": 1783598340000}),
        ),
    ]

    result = runtime.drain_notified_identities(
        _Connection(),
        notifications,
        max_batch=8,
        session_id="00000000-0000-0000-0000-000000000001",
        parse_notification=_parse,
        notification_error_type=ValueError,
    )

    assert result["notifications_received"] == 3
    assert result["notifications_consumed"] == 3
    assert result["rows_seen"] == 2
    assert "LANE_CURSOR_ADVANCED" not in events
    assert "LANE_BOOTSTRAPPED" not in events


def test_contiguous_fresh_catch_up_walks_gap_then_already_ingested_exact_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = {
        "source_ts": "2026-07-09T12:00:00Z",
        "source_scan_id": "scan-0",
        "source_hash": "0" * 64,
    }
    gap = _row("scan-gap", "2026-07-09T12:01:00Z")
    exact = _row("scan-exact", "2026-07-09T12:02:00Z")
    events: list[tuple[str, str, str]] = []
    persisted_scan_ids: list[str] = []
    monkeypatch.setattr(
        runtime,
        "ensure_fresh_lane_bootstrap",
        lambda connection, *, session_id: {
            "fresh_cursor": cursor,
            "fresh_anchor": cursor,
            "historical_cursor": None,
        },
    )
    monkeypatch.setattr(
        runtime,
        "fetch_fresh_lane_rows",
        lambda connection, *, cursor_state, limit: [gap, exact],
    )
    monkeypatch.setattr(
        runtime,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )
    exact_hash = runtime.adapt_scanner_snapshot(exact)["source_hash"]
    monkeypatch.setattr(
        runtime,
        "fetch_persisted_scanner_identity",
        lambda connection, *, scan_id, source_ts: (
            {"source_key": f"{scan_id}|{source_ts}", "source_hash": exact_hash}
            if scan_id == "scan-exact"
            else None
        ),
    )

    def persist(connection: object, cycle: dict[str, Any]) -> dict[str, str]:
        persisted_scan_ids.append(cycle["source"]["scan_id"])
        return {"status": "PERSISTED"}

    monkeypatch.setattr(
        runtime,
        "persist_scanner_cycle",
        persist,
    )
    monkeypatch.setattr(
        runtime,
        "load_consumer_state",
        lambda connection: {
            "fresh_cursor": {
                "source_ts": "2026-07-09T12:02:00Z",
                "source_scan_id": "scan-exact",
                "source_hash": "2" * 64,
            },
            "fresh_anchor": cursor,
            "historical_cursor": None,
        },
    )

    def record(connection: object, **kwargs: Any) -> None:
        if kwargs["event_kind"] == "LANE_CURSOR_ADVANCED":
            events.append(
                (
                    kwargs["source_ts"],
                    kwargs["source_scan_id"],
                    kwargs["details"]["persistence_status"],
                )
            )

    monkeypatch.setattr(runtime, "record_consumer_event", record)

    result = runtime.drain_fresh_lane(
        _Connection(),
        session_id="00000000-0000-0000-0000-000000000001",
        max_batch=8,
    )

    assert events == [
        ("2026-07-09T12:01:00Z", "scan-gap", "PERSISTED"),
        ("2026-07-09T12:02:00Z", "scan-exact", "TRAVERSED"),
    ]
    assert persisted_scan_ids == ["scan-gap"]
    assert result["persisted"] == 1
    assert result["duplicates"] == 0


def test_invalid_notification_is_counted_without_stopping_valid_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_kinds: list[str] = []
    monkeypatch.setattr(
        runtime,
        "record_consumer_event",
        lambda connection, **kwargs: event_kinds.append(kwargs["event_kind"]),
    )
    monkeypatch.setattr(
        runtime,
        "fetch_scanner_snapshot_by_identity",
        lambda connection, *, scan_id, ts_ms: _row(scan_id, "2026-07-09T12:00:00Z"),
    )
    monkeypatch.setattr(
        runtime,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )
    monkeypatch.setattr(
        runtime,
        "persist_scanner_cycle",
        lambda connection, cycle: {"status": "PERSISTED"},
    )

    result = runtime.drain_notified_identities(
        _Connection(),
        [
            ("bad", "{}"),
            (
                "alr_scanner_snapshot_v1",
                json.dumps({"scan_id": "scan-ok", "ts_ms": 1783598400000}),
            ),
        ],
        max_batch=8,
        session_id="00000000-0000-0000-0000-000000000001",
        parse_notification=_parse,
        notification_error_type=ValueError,
    )

    assert result["notifications_received"] == 2
    assert result["notifications_invalid"] == 1
    assert result["notifications_consumed"] == 1
    assert event_kinds.count("NOTIFICATION_INVALID") == 1


def test_notification_burst_larger_than_max_batch_preserves_every_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetched: list[str] = []
    monkeypatch.setattr(runtime, "record_consumer_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runtime,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )

    def fetch(connection: object, *, scan_id: str, ts_ms: int) -> dict[str, object]:
        del connection
        fetched.append(scan_id)
        minute = ts_ms // 60_000 % 60
        return _row(scan_id, f"2026-07-09T12:{minute:02d}:00Z")

    monkeypatch.setattr(runtime, "fetch_scanner_snapshot_by_identity", fetch)
    monkeypatch.setattr(
        runtime,
        "persist_scanner_cycle",
        lambda connection, cycle: {"status": "PERSISTED"},
    )
    notifications = [
        (
            "alr_scanner_snapshot_v1",
            json.dumps({"scan_id": f"scan-{index}", "ts_ms": 1783598400000 + index * 60_000}),
        )
        for index in range(3)
    ]

    result = runtime.drain_notified_identities(
        _Connection(),
        notifications,
        max_batch=2,
        session_id="00000000-0000-0000-0000-000000000001",
        parse_notification=_parse,
        notification_error_type=ValueError,
    )

    assert fetched == ["scan-0", "scan-1", "scan-2"]
    assert result["notifications_consumed"] == 3
    assert result["persisted"] == 3


def test_exact_existing_identity_is_consumed_without_duplicate_source_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row("scan-existing", "2026-07-09T12:00:00Z")
    source_hash = runtime.adapt_scanner_snapshot(row)["source_hash"]
    event_details: list[dict[str, Any]] = []
    event_kinds: list[str] = []
    monkeypatch.setattr(
        runtime,
        "fetch_scanner_snapshot_by_identity",
        lambda connection, *, scan_id, ts_ms: row,
    )
    monkeypatch.setattr(
        runtime,
        "fetch_persisted_scanner_identity",
        lambda connection, *, scan_id, source_ts: {
            "source_key": f"{scan_id}|{source_ts}",
            "source_hash": source_hash,
        },
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )
    monkeypatch.setattr(
        runtime,
        "persist_scanner_cycle",
        lambda *args, **kwargs: pytest.fail("existing exact identity must not be re-persisted"),
    )

    def record(connection: object, **kwargs: Any) -> None:
        event_kinds.append(kwargs["event_kind"])
        if kwargs["event_kind"] == "NOTIFICATION_CONSUMED":
            event_details.append(kwargs.get("details", {}))

    monkeypatch.setattr(runtime, "record_consumer_event", record)

    result = runtime.drain_notified_identities(
        _Connection(),
        [
            (
                "alr_scanner_snapshot_v1",
                json.dumps({"scan_id": "scan-existing", "ts_ms": 1783598400000}),
            )
        ],
        max_batch=1,
        session_id="00000000-0000-0000-0000-000000000001",
        parse_notification=_parse,
        notification_error_type=ValueError,
    )

    assert result["duplicates"] == 0
    assert result["persisted"] == 0
    assert event_details == [{"source_state": "ALREADY_PERSISTED"}]
    assert event_kinds.count("NOTIFICATION_DUPLICATE") == 1


def test_fresh_lane_repairs_anchor_partition_hole_without_rewinding_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = {
        "source_ts": "2026-07-09T12:00:00Z",
        "source_scan_id": "scan-0",
        "source_hash": "0" * 64,
    }
    cursor = {
        "source_ts": "2026-07-09T12:02:00Z",
        "source_scan_id": "scan-z",
        "source_hash": "2" * 64,
    }
    holes = [
        _row("scan-gap", "2026-07-09T12:01:00Z"),
        _row("scan-a", "2026-07-09T12:02:00Z"),
    ]
    persisted: list[str] = []
    cursor_events: list[str] = []
    monkeypatch.setattr(
        runtime,
        "ensure_fresh_lane_bootstrap",
        lambda connection, *, session_id: {
            "fresh_cursor": cursor,
            "fresh_anchor": anchor,
            "historical_cursor": None,
        },
    )
    monkeypatch.setattr(
        runtime,
        "fetch_fresh_raw_only_holes",
        lambda connection, *, anchor_cursor, limit: holes,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "fetch_fresh_lane_rows",
        lambda connection, *, cursor_state, limit: [],
    )
    monkeypatch.setattr(
        runtime,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )
    monkeypatch.setattr(
        runtime,
        "persist_scanner_cycle",
        lambda connection, cycle: persisted.append(cycle["source"]["scan_id"])
        or {"status": "PERSISTED"},
    )
    monkeypatch.setattr(
        runtime,
        "load_consumer_state",
        lambda connection: {
            "fresh_cursor": cursor,
            "fresh_anchor": anchor,
            "historical_cursor": None,
        },
    )
    monkeypatch.setattr(
        runtime,
        "record_consumer_event",
        lambda connection, **kwargs: cursor_events.append(kwargs["event_kind"]),
    )

    result = runtime.drain_fresh_lane(
        _Connection(),
        session_id="00000000-0000-0000-0000-000000000001",
        max_batch=8,
    )

    assert persisted == ["scan-gap", "scan-a"]
    assert "LANE_CURSOR_ADVANCED" not in cursor_events
    assert result["persisted"] == 2


def test_restart_after_persist_before_cursor_traverses_without_duplicate_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = {
        "source_ts": "2026-07-09T12:00:00Z",
        "source_scan_id": "scan-0",
        "source_hash": "0" * 64,
    }
    row = _row("scan-1", "2026-07-09T12:01:00Z")
    row_hash = runtime.adapt_scanner_snapshot(row)["source_hash"]
    current_cursor = dict(anchor)
    source_persisted = False
    persist_calls = 0
    crash_once = True
    traversed: list[str] = []

    monkeypatch.setattr(
        runtime,
        "ensure_fresh_lane_bootstrap",
        lambda connection, *, session_id: {
            "fresh_cursor": dict(current_cursor),
            "fresh_anchor": anchor,
            "historical_cursor": None,
        },
    )
    monkeypatch.setattr(
        runtime,
        "fetch_fresh_lane_rows",
        lambda connection, *, cursor_state, limit: [row],
    )
    monkeypatch.setattr(
        runtime,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )

    def existing(connection: object, *, scan_id: str, source_ts: str) -> dict[str, str] | None:
        if not source_persisted:
            return None
        return {"source_key": f"{scan_id}|{source_ts}", "source_hash": row_hash}

    def persist(connection: object, cycle: dict[str, Any]) -> dict[str, str]:
        nonlocal source_persisted, persist_calls
        source_persisted = True
        persist_calls += 1
        return {"status": "PERSISTED"}

    def record(connection: object, **kwargs: Any) -> None:
        nonlocal crash_once, current_cursor
        if kwargs["event_kind"] != "LANE_CURSOR_ADVANCED":
            return
        if crash_once:
            crash_once = False
            raise RuntimeError("crash_after_persist_before_cursor")
        current_cursor = {
            "source_ts": kwargs["source_ts"],
            "source_scan_id": kwargs["source_scan_id"],
            "source_hash": kwargs["source_hash"],
        }
        traversed.append(kwargs["details"]["persistence_status"])

    monkeypatch.setattr(runtime, "fetch_persisted_scanner_identity", existing)
    monkeypatch.setattr(runtime, "persist_scanner_cycle", persist)
    monkeypatch.setattr(runtime, "record_consumer_event", record)
    monkeypatch.setattr(
        runtime,
        "load_consumer_state",
        lambda connection: {
            "fresh_cursor": dict(current_cursor),
            "fresh_anchor": anchor,
            "historical_cursor": None,
        },
    )

    with pytest.raises(RuntimeError, match="crash_after_persist_before_cursor"):
        runtime.drain_fresh_lane(
            _Connection(),
            session_id="00000000-0000-0000-0000-000000000001",
            max_batch=8,
        )
    recovered = runtime.drain_fresh_lane(
        _Connection(),
        session_id="00000000-0000-0000-0000-000000000002",
        max_batch=8,
    )

    assert persist_calls == 1
    assert traversed == ["TRAVERSED"]
    assert recovered["duplicates"] == 0
    assert current_cursor["source_scan_id"] == "scan-1"
