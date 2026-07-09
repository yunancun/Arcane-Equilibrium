from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ml_training import alr_event_consumer as consumer
from ml_training.alr_event_consumer import (
    ALR_SCANNER_NOTIFY_CHANNEL,
    AlrEventConsumerError,
    acquire_single_instance,
    drain_notified_backlog,
    event_consumer_loop,
    read_local_dsn_file,
    runtime_file_lock,
    release_single_instance,
    parse_scanner_notification,
    process_outcome_feedback_backlog,
    run_operational_backlog,
    wait_for_pg_notifications,
)


def _notification_payload(**overrides: object) -> str:
    payload: dict[str, object] = {
        "schema_version": "alr_scanner_notification_v1",
        "scan_id": "scan-1783598400000",
        "ts_ms": 1783598400000,
    }
    payload.update(overrides)
    return json.dumps(payload, sort_keys=True)


def test_accepts_only_identity_bound_scanner_notification() -> None:
    event = parse_scanner_notification(
        ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload()
    )

    assert event == {
        "schema_version": "alr_scanner_notification_v1",
        "scan_id": "scan-1783598400000",
        "ts_ms": 1783598400000,
    }


def test_rejects_wrong_channel_or_payload_expansion() -> None:
    with pytest.raises(AlrEventConsumerError, match="notification_channel_invalid"):
        parse_scanner_notification("other_channel", _notification_payload())

    with pytest.raises(AlrEventConsumerError, match="notification_fields_invalid"):
        parse_scanner_notification(
            ALR_SCANNER_NOTIFY_CHANNEL,
            _notification_payload(candidates=[{"symbol": "BTCUSDT"}]),
        )


def _scanner_row(scan_id: str, ts: str) -> dict[str, object]:
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


class _DrainConnection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_coalesces_notification_burst_into_one_bounded_drain(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched_limits: list[int] = []
    persisted: list[str] = []

    monkeypatch.setattr(
        consumer,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )

    def fetch(connection: object, *, limit: int) -> list[dict[str, object]]:
        fetched_limits.append(limit)
        return [
            _scanner_row("scan-1", "2026-07-09T12:00:00Z"),
            _scanner_row("scan-2", "2026-07-09T12:01:00Z"),
        ]

    monkeypatch.setattr(consumer, "fetch_unseen_scanner_snapshots", fetch)

    def persist(connection: object, cycle: dict[str, object]) -> dict[str, object]:
        persisted.append(str(cycle["source_hash"]))
        return {"status": "PERSISTED"}

    monkeypatch.setattr(consumer, "persist_scanner_cycle", persist)
    notifications = [
        (ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload()),
        (ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload()),
    ]

    connection = _DrainConnection()
    result = drain_notified_backlog(connection, notifications, max_batch=2)

    assert result == {
        "notifications_seen": 2,
        "rows_seen": 2,
        "persisted": 2,
        "duplicates": 0,
    }
    assert fetched_limits == [2]
    assert len(persisted) == 2
    assert connection.commits == 1
    assert connection.rollbacks == 0


class _LockCursor:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "_LockCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))

    def fetchone(self) -> tuple[bool]:
        return (self.acquired,)


class _LockConnection:
    def __init__(self, acquired: bool) -> None:
        self.cursor_value = _LockCursor(acquired)
        self.commits = 0

    def cursor(self) -> _LockCursor:
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1


def test_single_instance_lock_is_fail_closed_and_released() -> None:
    busy = _LockConnection(False)
    assert acquire_single_instance(busy) is False

    available = _LockConnection(True)
    assert acquire_single_instance(available) is True
    release_single_instance(available)

    statements = [sql for sql, _ in available.cursor_value.calls]
    assert any("pg_try_advisory_lock" in sql for sql in statements)
    assert any("pg_advisory_unlock" in sql for sql in statements)
    assert available.commits == 2


def test_runtime_file_lock_rejects_a_second_process(tmp_path: Path) -> None:
    lock_path = tmp_path / "alr-shadow" / "consumer.lock"

    with runtime_file_lock(lock_path):
        with pytest.raises(AlrEventConsumerError, match="runtime_file_lock_busy"):
            with runtime_file_lock(lock_path):
                pass

    with runtime_file_lock(lock_path):
        pass


def test_event_loop_reconciles_once_then_only_drains_on_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drains: list[list[tuple[str, str]]] = []
    waits = 0

    def drain(
        connection: object,
        notifications: list[tuple[str, str]],
        *,
        max_batch: int,
    ) -> dict[str, int]:
        drains.append(notifications)
        return {
            "notifications_seen": len(notifications),
            "rows_seen": len(notifications),
            "persisted": len(notifications),
            "duplicates": 0,
        }

    monkeypatch.setattr(consumer, "drain_notified_backlog", drain)

    def wait_for_notifications(connection: object, *, timeout_seconds: float) -> list[tuple[str, str]]:
        nonlocal waits
        waits += 1
        if waits == 1:
            return []
        return [(ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload())]

    result = event_consumer_loop(
        object(),
        max_batch=2,
        should_stop=lambda: waits >= 3,
        wait_for_notifications=wait_for_notifications,
    )

    assert drains == [[], [(ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload())]]
    assert result == {
        "drains": 2,
        "notifications_seen": 1,
        "rows_seen": 1,
        "persisted": 1,
        "duplicates": 0,
    }


def test_operational_backlog_is_bounded_and_deferred_without_training_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetched_limits: list[int] = []
    cycles = [
        {
            "source_hash": f"{ordinal:064x}",
            "source_key": f"scan-{ordinal}|2026-07-09T12:0{ordinal}:00Z",
            "source_ts": f"2026-07-09T12:0{ordinal}:00Z",
            "canonical_payload": {"candidates": [{"symbol": "BTCUSDT"}]},
        }
        for ordinal in range(1, 4)
    ]
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: fetched_limits.append(limit) or cycles,
    )
    monkeypatch.setattr(
        consumer,
        "build_scanner_statistical_experiment",
        lambda **kwargs: {"research_only": True},
    )
    monkeypatch.setattr(
        consumer,
        "persist_statistical_run",
        lambda connection, result: {"status": "PERSISTED"},
    )

    result = run_operational_backlog(
        object(),
        source_head="a" * 40,
        max_batch=128,
    )

    assert fetched_limits == [64]
    assert result == {
        "training_runs": 1,
        "training_duplicates": 0,
        "training_deferred": 0,
        "training_insufficient_source_cycles": 0,
    }


def test_operational_backlog_requires_a_pinned_source_head() -> None:
    with pytest.raises(AlrEventConsumerError, match="operational_source_head_invalid"):
        run_operational_backlog(object(), source_head="unknown", max_batch=32)


def test_feedback_backlog_persists_absence_and_requests_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "run_hash": "a" * 64,
            "candidate_artifact_hash": "b" * 64,
            "candidate_artifact": {"candidate_scope": {}},
        }
    ]
    monkeypatch.setattr(
        consumer,
        "fetch_unreviewed_outcome_runs",
        lambda connection, *, limit: rows,
    )
    monkeypatch.setattr(
        consumer,
        "build_outcome_feedback",
        lambda **kwargs: {"feedback": "absent-evidence"},
    )
    monkeypatch.setattr(
        consumer,
        "persist_outcome_feedback",
        lambda connection, feedback: {
            "status": "PERSISTED",
            "feedback_status": "DEFER_EVIDENCE",
            "rotate_next_target": True,
            "global_stop": False,
        },
    )

    result = process_outcome_feedback_backlog(object(), max_batch=8)

    assert result == {
        "feedback_persisted": 1,
        "feedback_duplicates": 0,
        "feedback_deferred": 1,
        "feedback_rotations": 1,
        "feedback_boundary_blocks": 0,
    }


def test_event_loop_processes_feedback_before_next_target_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        consumer,
        "drain_notified_backlog",
        lambda connection, notifications, *, max_batch: {
            "notifications_seen": len(notifications),
            "rows_seen": 0,
            "persisted": 0,
            "duplicates": 0,
        },
    )
    monkeypatch.setattr(
        consumer,
        "process_outcome_feedback_backlog",
        lambda connection, *, max_batch: calls.append("feedback")
        or {
            "feedback_persisted": 1,
            "feedback_duplicates": 0,
            "feedback_deferred": 1,
            "feedback_rotations": 1,
            "feedback_boundary_blocks": 0,
        },
    )
    monkeypatch.setattr(
        consumer,
        "run_operational_backlog",
        lambda connection, *, source_head, max_batch: calls.append("target")
        or {
            "training_runs": 1,
            "training_duplicates": 0,
            "training_deferred": 0,
            "training_insufficient_source_cycles": 0,
        },
    )

    result = event_consumer_loop(
        object(),
        max_batch=8,
        should_stop=lambda: True,
        wait_for_notifications=lambda *args, **kwargs: [],
        source_head="a" * 40,
    )

    assert calls == ["feedback", "target"]
    assert result["feedback_rotations"] == 1
    assert result["training_runs"] == 1


def test_dsn_file_must_be_private_and_explicitly_local(tmp_path: Path) -> None:
    dsn_file = tmp_path / "alr-shadow.dsn"
    dsn_file.write_text(
        "host=127.0.0.1 port=5432 dbname=trading_ai user=alr_shadow password=not-a-real-secret\n",
        encoding="utf-8",
    )
    dsn_file.chmod(0o600)

    assert "host=127.0.0.1" in read_local_dsn_file(dsn_file)

    dsn_file.chmod(0o644)
    with pytest.raises(AlrEventConsumerError, match="dsn_file_permissions_invalid"):
        read_local_dsn_file(dsn_file)

    dsn_file.chmod(0o600)
    linked_dsn = tmp_path / "linked.dsn"
    linked_dsn.symlink_to(dsn_file)
    with pytest.raises(AlrEventConsumerError, match="dsn_file_not_regular"):
        read_local_dsn_file(linked_dsn)


def test_listen_wait_returns_identity_pairs_only_when_socket_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        def __init__(self) -> None:
            self.notifies = [
                SimpleNamespace(
                    channel=ALR_SCANNER_NOTIFY_CHANNEL,
                    payload=_notification_payload(),
                )
            ]
            self.polls = 0

        def poll(self) -> None:
            self.polls += 1

    connection = Connection()
    monkeypatch.setattr(consumer.select, "select", lambda *args: ([], [], []))
    assert wait_for_pg_notifications(connection, timeout_seconds=1.0) == []
    assert connection.polls == 0

    monkeypatch.setattr(consumer.select, "select", lambda *args: ([connection], [], []))
    assert wait_for_pg_notifications(connection, timeout_seconds=1.0) == [
        (ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload())
    ]
    assert connection.polls == 1
    assert connection.notifies == []
