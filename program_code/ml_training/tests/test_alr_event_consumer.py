from __future__ import annotations

import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from ml_training import alr_event_consumer as consumer
from ml_training import alr_freshness_runtime as freshness
from ml_training.candidate_proof_repository import (
    compute_candidate_proof_repository_receipt_hash,
)
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
    process_candidate_proof_repository_backlog,
    process_health_snapshot,
    process_outcome_feedback_backlog,
    process_retention_backlog,
    run_operational_backlog,
    verify_runtime_source_head,
    wait_for_pg_notifications,
)


_CANDIDATE_PROOF_NO_AUTHORITY = {
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
_CANDIDATE_PROOF_AUTHORITY_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_or_promotion_count": 0,
}


def _notification_payload(**overrides: object) -> str:
    payload: dict[str, object] = {
        "schema_version": "alr_scanner_notification_v1",
        "scan_id": "scan-1783598400000",
        "ts_ms": 1783598400000,
    }
    payload.update(overrides)
    return json.dumps(payload, sort_keys=True)


def _drain_result(**overrides: int) -> dict[str, int]:
    result = {
        "notifications_seen": 0,
        "notifications_received": 0,
        "notifications_consumed": 0,
        "notifications_invalid": 0,
        "rows_seen": 0,
        "persisted": 0,
        "duplicates": 0,
    }
    result.update(overrides)
    return result


def _candidate_proof_result(**overrides: int) -> dict[str, int]:
    result = {
        "candidate_proof_scans": 1,
        "candidate_proof_projection_rows_read": 0,
        "candidate_proof_source_event_rows_read": 0,
        "candidate_proof_projection_edge_rows_read": 0,
        "candidate_proof_source_event_rows_rechecked": 0,
        "candidate_proof_projection_edge_rows_rechecked": 0,
        "candidate_proof_outcome_bridge_rows_scanned": 0,
        "candidate_proof_outcome_bridge_rows_rechecked": 0,
        "candidate_proof_receipts": 0,
        "candidate_proof_pending": 0,
        "candidate_proof_no_fill": 0,
        "candidate_proof_ready_for_reward_validation": 0,
        "candidate_proof_invalid": 0,
        "candidate_proof_schema_required_overflow": 0,
        "candidate_proof_rows_written": 0,
        "candidate_proof_payload_bytes_written": 0,
    }
    result.update(overrides)
    return result


def _pending_candidate_proof_receipt() -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": "candidate_proof_repository_receipt_v1",
        "status": "PENDING_EVIDENCE",
        "projection_identity_status": "RECONSTRUCTED_FROM_HASH_VALIDATED_ROWS",
        "original_ephemeral_projection_hash_attested": False,
        "durability": {
            "source_container": "NO_MATCHING_HASH_VALIDATED_ROW",
            "runtime_or_exchange_attested": False,
            "receipt_persisted": False,
        },
        "no_authority": dict(_CANDIDATE_PROOF_NO_AUTHORITY),
        "authority_counters": dict(_CANDIDATE_PROOF_AUTHORITY_COUNTERS),
    }
    receipt["receipt_hash"] = compute_candidate_proof_repository_receipt_hash(
        receipt
    )
    return receipt


def _valid_candidate_proof_batch() -> dict[str, object]:
    return {
        "schema_version": "candidate_proof_repository_batch_v1",
        "status": "READY",
        "receipts": [_pending_candidate_proof_receipt()],
        "metrics": {
            "candidate_projection_rows_read": 2,
            "source_event_rows_read": 3,
            "projection_edge_rows_read": 3,
            "source_event_rows_rechecked": 3,
            "projection_edge_rows_rechecked": 3,
            "outcome_bridge_rows_scanned": 0,
            "outcome_bridge_rows_rechecked": 0,
            "receipts_built": 1,
            "pending_receipts": 1,
            "no_fill_receipts": 0,
            "ready_for_reward_validation_receipts": 0,
            "invalid_receipts": 0,
            "rows_written": 0,
            "payload_bytes_written": 0,
        },
        "no_authority": dict(_CANDIDATE_PROOF_NO_AUTHORITY),
        "authority_counters": dict(_CANDIDATE_PROOF_AUTHORITY_COUNTERS),
    }


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
    persisted: list[str] = []
    monkeypatch.setattr(freshness, "record_consumer_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        freshness,
        "fetch_persisted_scanner_identity",
        lambda connection, *, scan_id, source_ts: None,
    )
    monkeypatch.setattr(
        freshness,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )
    monkeypatch.setattr(
        freshness,
        "fetch_scanner_snapshot_by_identity",
        lambda connection, *, scan_id, ts_ms: _scanner_row(
            scan_id,
            "2026-07-09T12:00:00Z",
        ),
    )

    def persist(connection: object, cycle: dict[str, object]) -> dict[str, object]:
        persisted.append(str(cycle["source_hash"]))
        return {"status": "PERSISTED"}

    monkeypatch.setattr(freshness, "persist_scanner_cycle", persist)
    notifications = [
        (ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload()),
        (ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload()),
    ]

    connection = _DrainConnection()
    result = drain_notified_backlog(
        connection,
        notifications,
        max_batch=2,
        session_id="00000000-0000-0000-0000-000000000001",
    )

    assert result == {
        "notifications_seen": 2,
        "notifications_received": 2,
        "notifications_consumed": 2,
        "notifications_invalid": 0,
        "rows_seen": 1,
        "persisted": 1,
        "duplicates": 0,
    }
    assert len(persisted) == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_notification_identity_preempts_79k_historical_backlog_same_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeScannerRepository:
        def __init__(self) -> None:
            self.historical_rows = [f"historical-{index}" for index in range(79_000)]
            self.history_fetches = 0

        def fetch_exact(
            self,
            connection: object,
            *,
            scan_id: str,
            ts_ms: int,
        ) -> dict[str, object]:
            del connection, scan_id, ts_ms
            return fresh_row

        def fetch_history(self, *args: object, **kwargs: object) -> list[object]:
            del args, kwargs
            self.history_fetches += 1
            return self.historical_rows[:2]

    repository = FakeScannerRepository()
    persisted_scan_ids: list[str] = []
    fresh_row = _scanner_row("scan-1783598400000", "2026-07-09T12:00:00Z")
    monkeypatch.setattr(freshness, "record_consumer_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        freshness,
        "fetch_persisted_scanner_identity",
        lambda connection, *, scan_id, source_ts: None,
    )
    monkeypatch.setattr(
        freshness,
        "load_restart_state",
        lambda connection: {"processed_source_keys": set(), "watermark": None},
    )
    monkeypatch.setattr(
        freshness,
        "fetch_scanner_snapshot_by_identity",
        repository.fetch_exact,
    )
    monkeypatch.setattr(
        freshness,
        "fetch_historical_lane_rows",
        repository.fetch_history,
    )

    def persist(connection: object, cycle: dict[str, object]) -> dict[str, object]:
        source = cycle["source"]
        assert isinstance(source, dict)
        persisted_scan_ids.append(str(source["scan_id"]))
        return {"status": "PERSISTED"}

    monkeypatch.setattr(freshness, "persist_scanner_cycle", persist)

    result = drain_notified_backlog(
        _DrainConnection(),
        [(ALR_SCANNER_NOTIFY_CHANNEL, _notification_payload())],
        max_batch=2,
        session_id="00000000-0000-0000-0000-000000000001",
    )

    assert persisted_scan_ids[0] == "scan-1783598400000"
    assert result["persisted"] == 1
    assert len(repository.historical_rows) == 79_000
    assert repository.history_fetches == 0


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


def test_event_loop_prioritizes_exact_then_fresh_and_keeps_history_idle_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    waits = 0
    monkeypatch.setattr(
        consumer,
        "drain_fresh_lane",
        lambda connection, *, session_id, max_batch: calls.append("fresh")
        or _drain_result(),
    )
    monkeypatch.setattr(
        consumer,
        "drain_historical_lane",
        lambda connection, *, session_id, max_batch: calls.append("history")
        or _drain_result(),
    )
    monkeypatch.setattr(
        consumer,
        "drain_notified_backlog",
        lambda connection, notifications, *, max_batch, session_id: calls.append("exact")
        or _drain_result(
            notifications_seen=1,
            notifications_received=1,
            notifications_consumed=1,
            rows_seen=1,
            persisted=1,
        ),
    )

    def wait_for_notifications(
        connection: object,
        *,
        timeout_seconds: float,
        max_batch: int,
    ) -> list[tuple[str, str]]:
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
        session_id="00000000-0000-0000-0000-000000000001",
    )

    assert calls == ["fresh", "fresh", "exact", "fresh"]
    assert result == {
        "drains": 4,
        "notifications_seen": 1,
        "notifications_received": 1,
        "notifications_consumed": 1,
        "notifications_invalid": 0,
        "rows_seen": 1,
        "persisted": 1,
        "duplicates": 0,
    }


def test_event_loop_history_is_fixed_smaller_bound_after_idle_fresh_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []
    waits = 0
    monkeypatch.setattr(
        consumer,
        "drain_fresh_lane",
        lambda connection, *, session_id, max_batch: calls.append(("fresh", max_batch))
        or _drain_result(),
    )
    monkeypatch.setattr(
        consumer,
        "drain_historical_lane",
        lambda connection, *, session_id, max_batch: calls.append(("history", max_batch))
        or _drain_result(),
    )

    def wait(
        connection: object,
        *,
        timeout_seconds: float,
        max_batch: int,
    ) -> list[tuple[str, str]]:
        nonlocal waits
        waits += 1
        return []

    clock = iter([0.0, 61.0])

    result = event_consumer_loop(
        object(),
        max_batch=32,
        should_stop=lambda: waits >= 2,
        wait_for_notifications=wait,
        session_id="00000000-0000-0000-0000-000000000001",
        monotonic_seconds=lambda: next(clock),
    )

    assert calls == [
        ("fresh", 32),
        ("fresh", 32),
        ("history", 8),
    ]
    assert result["drains"] == 3


def test_candidate_board_inotify_source_wakes_on_immutable_create_and_recovers_overflow(
    tmp_path: Path,
) -> None:
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    rearms: list[Path] = []

    def open_watch(directory: Path) -> tuple[int, int, int]:
        assert directory == tmp_path
        return read_fd, 17, -1

    def reopen_watch(directory: Path) -> tuple[int, int, int]:
        rearms.append(directory)
        return read_fd, 23, -1

    source = consumer.open_candidate_board_event_source(
        tmp_path,
        open_watch=open_watch,
        reopen_watch=reopen_watch,
    )
    try:
        assert source.consume_reconciliation_request() is True
        assert source.consume_reconciliation_request() is False

        for mask in (
            consumer._IN_CREATE,
            consumer._IN_MOVED_TO,
            consumer._IN_CLOSE_WRITE,
            consumer._IN_DELETE,
        ):
            name = b"blocked_outcome_review_20260711T120000Z.json\x00"
            padded = name + b"\x00" * ((4 - len(name) % 4) % 4)
            os.write(
                write_fd,
                struct.pack("iIII", 17, mask, 0, len(padded)) + padded,
            )
            source.drain_ready()
            assert source.consume_reconciliation_request() is True

        os.write(
            write_fd,
            struct.pack("iIII", -1, consumer._IN_Q_OVERFLOW, 0, 0),
        )
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
        assert rearms == [tmp_path]

        os.write(
            write_fd,
            struct.pack("iIII", 17, consumer._IN_IGNORED, 0, 0),
        )
        source.drain_ready()
        assert source.consume_reconciliation_request() is False
        assert rearms == [tmp_path]

        os.write(
            write_fd,
            struct.pack("iIII", 23, consumer._IN_IGNORED, 0, 0),
        )
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
        assert rearms == [tmp_path, tmp_path]
    finally:
        source.close()
        with pytest.raises(OSError):
            os.fstat(read_fd)
        os.close(write_fd)


def test_candidate_board_rearm_closes_old_descriptors_and_owns_new_pair(
    tmp_path: Path,
) -> None:
    old_read_fd, old_write_fd = os.pipe()
    new_read_fd, new_write_fd = os.pipe()
    os.set_blocking(old_read_fd, False)
    old_directory_fd = os.open(tmp_path, os.O_RDONLY)
    new_directory_fd = os.open(tmp_path, os.O_RDONLY)

    source = consumer.open_candidate_board_event_source(
        tmp_path,
        open_watch=lambda directory: (old_read_fd, 17, old_directory_fd),
        reopen_watch=lambda directory: (new_read_fd, 23, new_directory_fd),
    )
    try:
        source.consume_reconciliation_request()
        os.write(
            old_write_fd,
            struct.pack("iIII", 17, consumer._IN_IGNORED, 0, 0),
        )
        source.drain_ready()

        with pytest.raises(OSError):
            os.fstat(old_read_fd)
        with pytest.raises(OSError):
            os.fstat(old_directory_fd)
        os.fstat(new_read_fd)
        os.fstat(new_directory_fd)
        assert source.consume_reconciliation_request() is True
    finally:
        source.close()
        os.close(old_write_fd)
        os.close(new_write_fd)

    with pytest.raises(OSError):
        os.fstat(new_read_fd)
    with pytest.raises(OSError):
        os.fstat(new_directory_fd)


def test_empty_pg_wait_uses_rearmed_candidate_board_descriptor(
    tmp_path: Path,
) -> None:
    pg_read_fd, pg_write_fd = os.pipe()
    old_read_fd, old_write_fd = os.pipe()
    new_read_fd, new_write_fd = os.pipe()
    os.set_blocking(old_read_fd, False)
    os.set_blocking(new_read_fd, False)

    class Connection:
        def __init__(self) -> None:
            self.notifies: list[object] = []
            self.polls = 0

        def fileno(self) -> int:
            return pg_read_fd

        def poll(self) -> None:
            self.polls += 1

    source = consumer.open_candidate_board_event_source(
        tmp_path,
        open_watch=lambda directory: (old_read_fd, 17, -1),
        reopen_watch=lambda directory: (new_read_fd, 23, -1),
    )
    connection = Connection()
    try:
        source.consume_reconciliation_request()
        os.write(
            old_write_fd,
            struct.pack("iIII", 17, consumer._IN_IGNORED, 0, 0),
        )
        assert wait_for_pg_notifications(
            connection,
            timeout_seconds=1.0,
            max_batch=8,
            candidate_board_source=source,
        ) == []
        assert source.consume_reconciliation_request() is True

        name = b"blocked_outcome_review_20260711T120001Z.json\x00"
        padded = name + b"\x00" * ((4 - len(name) % 4) % 4)
        os.write(
            new_write_fd,
            struct.pack("iIII", 23, consumer._IN_CREATE, 0, len(padded)) + padded,
        )
        assert wait_for_pg_notifications(
            connection,
            timeout_seconds=1.0,
            max_batch=8,
            candidate_board_source=source,
        ) == []
        assert source.consume_reconciliation_request() is True
        assert connection.polls == 0
    finally:
        source.close()
        os.close(pg_read_fd)
        os.close(pg_write_fd)
        os.close(old_write_fd)
        os.close(new_write_fd)


def test_candidate_board_wake_runs_candidate_only_with_zero_scanner_drain_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    candidate_inputs: list[tuple[str, int, Path | None, object]] = []
    waits = 0

    class BoardWake:
        def __init__(self) -> None:
            self.pending = False

        def consume_reconciliation_request(self) -> bool:
            pending, self.pending = self.pending, False
            return pending

    board_wake = BoardWake()
    monkeypatch.setattr(
        consumer,
        "drain_fresh_lane",
        lambda connection, *, session_id, max_batch: _drain_result(),
    )
    monkeypatch.setattr(
        consumer,
        "_process_operational_cycle",
        lambda *args, **kwargs: calls.append("startup_full"),
    )
    def candidate_only(
        connection: object,
        *,
        source_head: str,
        max_batch: int,
        evidence_directory: Path | None,
        candidate_policy: object,
    ) -> dict[str, int]:
        del connection
        calls.append("candidate_only")
        candidate_inputs.append(
            (source_head, max_batch, evidence_directory, candidate_policy)
        )
        return consumer._operational_result("INSUFFICIENT_SOURCE_CYCLES")

    monkeypatch.setattr(consumer, "run_candidate_aware_backlog", candidate_only)
    monkeypatch.setattr(
        consumer,
        "process_candidate_proof_repository_backlog",
        lambda connection, *, max_batch: calls.append("proof_repository")
        or _candidate_proof_result(),
    )
    monkeypatch.setattr(
        consumer,
        "process_health_snapshot",
        lambda *args, **kwargs: calls.append("health")
        or {
            "health_attempts": 0,
            "health_snapshots": 0,
            "health_state_delta_writes": 0,
            "health_heartbeat_writes": 0,
            "health_writes_suppressed": 0,
            "health_rows_written": 0,
            "health_payload_bytes_written": 0,
            "health_authority_mismatches": 0,
        },
    )
    monkeypatch.setattr(
        consumer,
        "process_outcome_feedback_backlog",
        lambda *args, **kwargs: pytest.fail("board wake must not run feedback"),
    )
    monkeypatch.setattr(
        consumer,
        "process_retention_backlog",
        lambda *args, **kwargs: pytest.fail("board wake must not run retention"),
    )

    def wait(
        connection: object,
        *,
        timeout_seconds: float,
        max_batch: int,
        candidate_board_source: object,
    ) -> list[tuple[str, str]]:
        del connection, timeout_seconds, max_batch
        nonlocal waits
        waits += 1
        assert candidate_board_source is board_wake
        if waits == 1:
            board_wake.pending = True
        return []

    event_consumer_loop(
        object(),
        max_batch=8,
        should_stop=lambda: waits >= 2,
        wait_for_notifications=wait,
        session_id="00000000-0000-0000-0000-000000000001",
        source_head="a" * 40,
        candidate_evidence_directory=Path("/durable/evidence"),
        candidate_policy={"policy_config_hash": "b" * 64},
        candidate_board_source=board_wake,
        monotonic_seconds=iter([0.0, 61.0]).__next__,
    )

    assert calls == [
        "startup_full",
        "candidate_only",
        "proof_repository",
        "health",
    ]

    assert candidate_inputs == [
        (
            "a" * 40,
            8,
            Path("/durable/evidence"),
            {"policy_config_hash": "b" * 64},
        )
    ]


def test_candidate_board_event_source_rejects_truncated_kernel_record(
    tmp_path: Path,
) -> None:
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    source = consumer.open_candidate_board_event_source(
        tmp_path,
        open_watch=lambda directory: (read_fd, 7, -1),
        reopen_watch=lambda directory: (read_fd, 7, -1),
    )
    source.consume_reconciliation_request()
    try:
        os.write(write_fd, b"truncated")
        with pytest.raises(AlrEventConsumerError, match="candidate_board_event_truncated"):
            source.drain_ready()
    finally:
        source.close()
        os.close(write_fd)


def test_inotify_watch_binds_held_directory_fd_across_configured_path_aba(
    tmp_path: Path,
) -> None:
    configured = tmp_path / "configured"
    replacement = tmp_path / "replacement"
    held_name = tmp_path / "held-original"
    configured.mkdir()
    replacement.mkdir()
    original_identity = configured.stat().st_dev, configured.stat().st_ino
    replacement_identity = replacement.stat().st_dev, replacement.stat().st_ino
    observed_paths: list[bytes] = []

    class AddWatch:
        argtypes: object = None
        restype: object = None

        def __call__(self, event_fd: int, path: bytes, mask: int) -> int:
            assert event_fd == 41
            assert mask & consumer._IN_ONLYDIR
            assert mask & consumer._IN_DONT_FOLLOW
            observed_paths.append(path)
            decoded = os.fsdecode(path)
            prefix = "/proc/self/fd/"
            assert decoded.startswith(prefix)
            assert decoded.endswith("/.")
            directory_fd = int(decoded[len(prefix) : -2])
            assert (os.fstat(directory_fd).st_dev, os.fstat(directory_fd).st_ino) == (
                original_identity
            )

            configured.rename(held_name)
            replacement.rename(configured)
            try:
                assert (configured.stat().st_dev, configured.stat().st_ino) == (
                    replacement_identity
                )
                assert (os.fstat(directory_fd).st_dev, os.fstat(directory_fd).st_ino) == (
                    original_identity
                )
            finally:
                configured.rename(replacement)
                held_name.rename(configured)
            return 19

    class Libc:
        inotify_add_watch = AddWatch()

    descriptor, directory_fd = consumer._add_linux_candidate_board_watch(
        Libc(),
        41,
        configured,
    )
    try:
        assert descriptor == 19
        assert observed_paths == [os.fsencode(f"/proc/self/fd/{directory_fd}/.")]
        assert (configured.stat().st_dev, configured.stat().st_ino) == (
            original_identity
        )
    finally:
        os.close(directory_fd)


def test_prequeued_pg_notification_still_services_ready_board_fd() -> None:
    read_fd, write_fd = os.pipe()
    drained: list[bool] = []

    class BoardSource:
        def fileno(self) -> int:
            return read_fd

        def drain_ready(self) -> None:
            os.read(read_fd, 1)
            drained.append(True)

    class Connection:
        def __init__(self) -> None:
            self.notifies = [SimpleNamespace(channel="channel", payload="payload")]

    os.write(write_fd, b"w")
    try:
        result = wait_for_pg_notifications(
            Connection(),
            timeout_seconds=1.0,
            max_batch=8,
            candidate_board_source=BoardSource(),
        )
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert result == [("channel", "payload")]
    assert drained == [True]


@pytest.mark.skipif(consumer.sys.platform != "linux", reason="Linux inotify integration")
def test_linux_inotify_real_link_publish_wakes_bounded_source(tmp_path: Path) -> None:
    evidence_directory = tmp_path / "evidence"
    evidence_directory.mkdir()
    producer_path = tmp_path / "producer.json"
    producer_path.write_text("{}\n", encoding="utf-8")
    source = consumer.open_candidate_board_event_source(evidence_directory)
    try:
        assert source.consume_reconciliation_request() is True
        os.link(
            producer_path,
            evidence_directory / "blocked_outcome_review_20260711T120000Z.json",
        )
        ready, _, _ = consumer.select.select([source], [], [], 1.0)
        assert ready == [source]
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
    finally:
        source.close()


def test_missing_candidate_directory_fails_before_db_listener_connect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    active_lock = False

    class Lock:
        def __enter__(self) -> None:
            nonlocal active_lock
            active_lock = True

        def __exit__(self, *args: object) -> None:
            nonlocal active_lock
            active_lock = False

    monkeypatch.setattr(consumer, "verify_runtime_source_head", lambda *args, **kwargs: "a" * 40)
    monkeypatch.setattr(consumer, "read_local_dsn_file", lambda path: "local-dsn")
    monkeypatch.setattr(consumer, "_install_shutdown_handlers", lambda event: {})
    monkeypatch.setattr(consumer, "_restore_shutdown_handlers", lambda previous: None)
    monkeypatch.setattr(consumer, "runtime_file_lock", lambda path: Lock())

    def fail_watch(path: Path) -> object:
        assert active_lock is True
        raise AlrEventConsumerError("candidate_board_directory_unavailable")

    monkeypatch.setattr(consumer, "open_candidate_board_event_source", fail_watch)
    monkeypatch.setattr(
        consumer,
        "_connect_listener",
        lambda dsn: pytest.fail("DB listener must not open without board watch"),
    )

    with pytest.raises(
        AlrEventConsumerError,
        match="candidate_board_directory_unavailable",
    ):
        consumer.run_event_consumer(
            dsn_path=tmp_path / "dsn",
            lock_path=tmp_path / "lock",
            max_batch=8,
            source_head="a" * 40,
            candidate_evidence_directory=tmp_path / "missing",
        )


def test_busy_runtime_lock_never_opens_candidate_board_watch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class BusyLock:
        def __enter__(self) -> None:
            raise AlrEventConsumerError("runtime_file_lock_busy")

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(consumer, "verify_runtime_source_head", lambda *args, **kwargs: "a" * 40)
    monkeypatch.setattr(consumer, "read_local_dsn_file", lambda path: "local-dsn")
    monkeypatch.setattr(consumer, "_install_shutdown_handlers", lambda event: {})
    monkeypatch.setattr(consumer, "_restore_shutdown_handlers", lambda previous: None)
    monkeypatch.setattr(consumer, "runtime_file_lock", lambda path: BusyLock())
    monkeypatch.setattr(
        consumer,
        "open_candidate_board_event_source",
        lambda path: pytest.fail("busy lock must prevent a second watcher"),
    )

    with pytest.raises(AlrEventConsumerError, match="runtime_file_lock_busy"):
        consumer.run_event_consumer(
            dsn_path=tmp_path / "dsn",
            lock_path=tmp_path / "lock",
            max_batch=8,
            source_head="a" * 40,
            candidate_evidence_directory=tmp_path / "evidence",
        )


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
        lambda connection, result: {
            "status": "PERSISTED",
            "decision_writes_suppressed": 0,
            "duplicate_retries": 0,
            "artifact_rows_written": 5,
            "provenance_rows_written": 7,
            "run_rows_written": 1,
            "feedback_rows_written": 0,
            "defer_artifact_rows_written": 1,
            "payload_bytes_written": 1024,
            "source_rows_consumed": 3,
        },
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
        "defer_suppressions": 0,
        "suppression_duplicate_retries": 0,
        "decision_write_attempts": 1,
        "decision_writes_suppressed": 0,
        "decision_duplicate_retries": 0,
        "operational_artifact_rows_written": 5,
        "operational_provenance_rows_written": 7,
        "operational_run_rows_written": 1,
        "operational_feedback_rows_written": 0,
        "operational_defer_artifact_rows_written": 1,
        "operational_payload_bytes_written": 1024,
        "operational_source_rows_consumed": 3,
    }


def test_operational_backlog_reports_equivalent_defer_suppression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        lambda connection, *, limit: cycles,
    )
    monkeypatch.setattr(
        consumer,
        "build_scanner_statistical_experiment",
        lambda **kwargs: {"research_only": True},
    )
    monkeypatch.setattr(
        consumer,
        "persist_statistical_run",
        lambda connection, result: {
            "status": "SUPPRESSED_EQUIVALENT_DEFER",
            "decision_writes_suppressed": 1,
            "duplicate_retries": 0,
            "artifact_rows_written": 1,
            "provenance_rows_written": 3,
            "run_rows_written": 0,
            "feedback_rows_written": 0,
            "defer_artifact_rows_written": 0,
            "payload_bytes_written": 256,
            "source_rows_consumed": 3,
        },
    )

    result = run_operational_backlog(
        object(),
        source_head="a" * 40,
        max_batch=32,
    )

    assert result == {
        "training_runs": 0,
        "training_duplicates": 0,
        "training_deferred": 0,
        "training_insufficient_source_cycles": 0,
        "defer_suppressions": 1,
        "suppression_duplicate_retries": 0,
        "decision_write_attempts": 1,
        "decision_writes_suppressed": 1,
        "decision_duplicate_retries": 0,
        "operational_artifact_rows_written": 1,
        "operational_provenance_rows_written": 3,
        "operational_run_rows_written": 0,
        "operational_feedback_rows_written": 0,
        "operational_defer_artifact_rows_written": 0,
        "operational_payload_bytes_written": 256,
        "operational_source_rows_consumed": 3,
    }


def test_operational_backlog_reports_duplicate_suppression_without_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        lambda connection, *, limit: cycles,
    )
    monkeypatch.setattr(
        consumer,
        "build_scanner_statistical_experiment",
        lambda **kwargs: {"research_only": True},
    )
    monkeypatch.setattr(
        consumer,
        "persist_statistical_run",
        lambda connection, result: {
            "status": "DUPLICATE_SUPPRESSION",
            "decision_writes_suppressed": 1,
            "duplicate_retries": 1,
            "artifact_rows_written": 0,
            "provenance_rows_written": 0,
            "run_rows_written": 0,
            "feedback_rows_written": 0,
            "defer_artifact_rows_written": 0,
            "payload_bytes_written": 0,
            "source_rows_consumed": 0,
        },
    )

    result = run_operational_backlog(
        object(),
        source_head="a" * 40,
        max_batch=32,
    )

    assert result["decision_write_attempts"] == 1
    assert result["decision_writes_suppressed"] == 1
    assert result["decision_duplicate_retries"] == 1
    assert result["suppression_duplicate_retries"] == 1
    assert result["operational_artifact_rows_written"] == 0
    assert result["operational_run_rows_written"] == 0


def test_write_metric_builder_reports_explicit_nonzero_ratios() -> None:
    metrics = consumer._build_write_metrics(
        {
            "health_attempts": 4,
            "health_snapshots": 1,
            "health_state_delta_writes": 1,
            "health_heartbeat_writes": 0,
            "health_writes_suppressed": 3,
            "decision_write_attempts": 5,
            "decision_writes_suppressed": 2,
            "decision_duplicate_retries": 1,
        },
        session_id="00000000-0000-0000-0000-000000000001",
    )

    assert metrics["health"]["suppression_ratio"] == 0.75
    assert metrics["decision"]["suppression_ratio"] == 0.4
    assert metrics["feedback"]["persisted_ratio"] == 0.0
    assert metrics["feedback"]["duplicate_retry_ratio"] == 0.0


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
            "artifact_rows_written": 3,
            "provenance_rows_written": 3,
            "feedback_event_rows_written": 1,
            "total_rows_written": 7,
            "payload_bytes_written": 256,
            "duplicate_retries": 0,
        },
    )

    result = process_outcome_feedback_backlog(object(), max_batch=8)

    assert result == {
        "feedback_persisted": 1,
        "feedback_duplicates": 0,
        "feedback_deferred": 1,
        "feedback_rotations": 1,
        "feedback_boundary_blocks": 0,
        "feedback_write_attempts": 1,
        "feedback_duplicate_retries": 0,
        "feedback_artifact_rows_written": 3,
        "feedback_provenance_rows_written": 3,
        "feedback_event_rows_written": 1,
        "feedback_total_rows_written": 7,
        "feedback_payload_bytes_written": 256,
    }


def test_candidate_proof_repository_backlog_maps_only_read_only_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_limits: list[int] = []

    def discover(connection: object, *, limit: int) -> dict[str, object]:
        del connection
        observed_limits.append(limit)
        return {
            "schema_version": "candidate_proof_repository_batch_v1",
            "status": "READY",
            "receipts": [_pending_candidate_proof_receipt()],
            "metrics": {
                "candidate_projection_rows_read": 1,
                "source_event_rows_read": 3,
                "projection_edge_rows_read": 3,
                "source_event_rows_rechecked": 3,
                "projection_edge_rows_rechecked": 3,
                "outcome_bridge_rows_scanned": 0,
                "outcome_bridge_rows_rechecked": 0,
                "receipts_built": 1,
                "pending_receipts": 1,
                "no_fill_receipts": 0,
                "ready_for_reward_validation_receipts": 0,
                "invalid_receipts": 0,
                "rows_written": 0,
                "payload_bytes_written": 0,
            },
            "no_authority": dict(_CANDIDATE_PROOF_NO_AUTHORITY),
            "authority_counters": dict(_CANDIDATE_PROOF_AUTHORITY_COUNTERS),
        }

    monkeypatch.setattr(consumer, "discover_candidate_proof_receipts", discover)

    result = process_candidate_proof_repository_backlog(object(), max_batch=8)

    assert result == _candidate_proof_result(
        candidate_proof_projection_rows_read=1,
        candidate_proof_source_event_rows_read=3,
        candidate_proof_projection_edge_rows_read=3,
        candidate_proof_source_event_rows_rechecked=3,
        candidate_proof_projection_edge_rows_rechecked=3,
        candidate_proof_receipts=1,
        candidate_proof_pending=1,
    )
    assert observed_limits == [8]


def test_candidate_proof_repository_backlog_rejects_any_write_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = {
        "schema_version": "candidate_proof_repository_batch_v1",
        "status": "READY",
        "receipts": [],
        "metrics": {
            "candidate_projection_rows_read": 0,
            "source_event_rows_read": 0,
            "projection_edge_rows_read": 0,
            "source_event_rows_rechecked": 0,
            "projection_edge_rows_rechecked": 0,
            "outcome_bridge_rows_scanned": 0,
            "outcome_bridge_rows_rechecked": 0,
            "receipts_built": 0,
            "pending_receipts": 0,
            "no_fill_receipts": 0,
            "ready_for_reward_validation_receipts": 0,
            "invalid_receipts": 0,
            "rows_written": 1,
            "payload_bytes_written": 0,
        },
        "no_authority": dict(_CANDIDATE_PROOF_NO_AUTHORITY),
        "authority_counters": dict(_CANDIDATE_PROOF_AUTHORITY_COUNTERS),
    }
    monkeypatch.setattr(
        consumer,
        "discover_candidate_proof_receipts",
        lambda connection, *, limit: batch,
    )

    with pytest.raises(AlrEventConsumerError, match="candidate_proof_write_claim"):
        process_candidate_proof_repository_backlog(object(), max_batch=8)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("unknown_status", "receipt_status"),
        ("truncated_authority", "authority"),
        ("receipt_authority", "receipt_authority"),
        ("ready_without_receipt", "batch_status"),
        ("no_current_with_receipt", "batch_status"),
    ),
)
def test_candidate_proof_backlog_rejects_contract_or_authority_drift(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    reason: str,
) -> None:
    batch = _valid_candidate_proof_batch()
    receipts = batch["receipts"]
    metrics = batch["metrics"]
    assert isinstance(receipts, list) and isinstance(metrics, dict)
    if mutation == "unknown_status":
        receipts[0]["status"] = "UNREVIEWED_POSITIVE"
        metrics["pending_receipts"] = 0
    elif mutation == "truncated_authority":
        batch["no_authority"] = {"proof_authority": False}
    elif mutation == "receipt_authority":
        receipts[0]["no_authority"]["proof_authority"] = True
    elif mutation == "ready_without_receipt":
        batch["receipts"] = []
        metrics["receipts_built"] = 0
        metrics["pending_receipts"] = 0
    else:
        batch["status"] = "NO_CURRENT_SELECTED_CANDIDATE"
    monkeypatch.setattr(
        consumer,
        "discover_candidate_proof_receipts",
        lambda connection, *, limit: batch,
    )

    with pytest.raises(AlrEventConsumerError, match=reason):
        process_candidate_proof_repository_backlog(object(), max_batch=8)


def test_event_loop_processes_feedback_before_next_target_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    captured_write_metrics: list[dict[str, object]] = []
    captured_target_config: list[tuple[Path | None, dict[str, object] | None]] = []
    monkeypatch.setattr(
        consumer,
        "drain_fresh_lane",
        lambda connection, *, session_id, max_batch: _drain_result(),
    )
    monkeypatch.setattr(
        consumer,
        "drain_historical_lane",
        lambda connection, *, session_id, max_batch: _drain_result(),
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
            "feedback_write_attempts": 1,
            "feedback_duplicate_retries": 0,
            "feedback_artifact_rows_written": 3,
            "feedback_provenance_rows_written": 3,
            "feedback_event_rows_written": 1,
            "feedback_total_rows_written": 7,
            "feedback_payload_bytes_written": 256,
        },
    )
    def target(
        connection: object,
        *,
        source_head: str,
        max_batch: int,
        evidence_directory: Path | None,
        candidate_policy: dict[str, object] | None,
    ) -> dict[str, int]:
        del connection, source_head, max_batch
        calls.append("target")
        captured_target_config.append((evidence_directory, candidate_policy))
        return {
            "training_runs": 0,
            "training_duplicates": 0,
            "training_deferred": 0,
            "training_insufficient_source_cycles": 0,
            "defer_suppressions": 0,
            "suppression_duplicate_retries": 0,
            "decision_write_attempts": 1,
            "decision_writes_suppressed": 0,
            "decision_duplicate_retries": 0,
            "operational_artifact_rows_written": 1,
            "operational_provenance_rows_written": 3,
            "operational_run_rows_written": 0,
            "operational_feedback_rows_written": 0,
            "operational_defer_artifact_rows_written": 0,
            "operational_payload_bytes_written": 512,
            "operational_source_rows_consumed": 3,
        }

    monkeypatch.setattr(consumer, "run_candidate_aware_backlog", target)
    monkeypatch.setattr(
        consumer,
        "process_candidate_proof_repository_backlog",
        lambda connection, *, max_batch: calls.append("proof_repository")
        or _candidate_proof_result(
            candidate_proof_projection_rows_read=1,
            candidate_proof_source_event_rows_read=3,
            candidate_proof_projection_edge_rows_read=3,
            candidate_proof_receipts=1,
            candidate_proof_pending=1,
        ),
    )
    monkeypatch.setattr(
        consumer,
        "process_retention_backlog",
        lambda connection, *, max_batch: calls.append("retention")
        or {
            "retention_scanned": 0,
            "retention_quarantined": 0,
            "retention_restored": 0,
            "retention_swept": 0,
            "retention_retained": 0,
            "retention_skipped": 0,
        },
    )
    def health(
        connection: object,
        *,
        source_head: str,
        write_metrics: dict[str, object],
    ) -> dict[str, int]:
        del connection, source_head
        calls.append("health")
        captured_write_metrics.append(write_metrics)
        return {
            "health_attempts": 1,
            "health_snapshots": 1,
            "health_state_delta_writes": 1,
            "health_heartbeat_writes": 0,
            "health_writes_suppressed": 0,
            "health_rows_written": 2,
            "health_payload_bytes_written": 512,
            "health_authority_mismatches": 0,
        }

    monkeypatch.setattr(consumer, "process_health_snapshot", health)

    result = event_consumer_loop(
        object(),
        max_batch=8,
        should_stop=lambda: True,
        wait_for_notifications=lambda *args, **kwargs: [],
        session_id="00000000-0000-0000-0000-000000000001",
        source_head="a" * 40,
        candidate_evidence_directory=Path("/durable/evidence"),
        candidate_policy={"policy_hash": "b" * 64},
    )

    assert calls == [
        "feedback",
        "target",
        "proof_repository",
        "retention",
        "health",
    ]
    assert result["feedback_rotations"] == 1
    assert result["training_runs"] == 0
    assert result["candidate_proof_pending"] == 1
    assert result["candidate_proof_rows_written"] == 0
    assert captured_target_config == [
        (Path("/durable/evidence"), {"policy_hash": "b" * 64})
    ]
    assert captured_write_metrics == [
        {
            "schema_version": "alr_write_metrics_v1",
            "scope": {
                "kind": "consumer_session_cumulative",
                "session_id": "00000000-0000-0000-0000-000000000001",
                "through_completed_health_attempt": 0,
            },
            "health": {
                "attempts": 0,
                "emitted": 0,
                "state_delta_writes": 0,
                "heartbeat_writes": 0,
                "writes_suppressed": 0,
                "rows_written": 0,
                "payload_bytes_written": 0,
                "suppression_ratio": 0.0,
            },
            "decision": {
                "attempts": 1,
                "writes_suppressed": 0,
                "duplicate_retries": 0,
                "artifact_rows_written": 4,
                "provenance_rows_written": 6,
                "run_rows_written": 0,
                "feedback_rows_written": 1,
                "defer_artifact_rows_written": 0,
                "payload_bytes_written": 768,
                "source_rows_consumed": 3,
                "suppression_ratio": 0.0,
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
    ]


def test_idle_health_heartbeat_does_not_trigger_another_training_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_calls = 0
    proof_repository_calls = 0
    health_calls = 0
    waits = 0

    monkeypatch.setattr(
        consumer,
        "drain_fresh_lane",
        lambda connection, *, session_id, max_batch: _drain_result(),
    )
    monkeypatch.setattr(
        consumer,
        "process_outcome_feedback_backlog",
        lambda connection, *, max_batch: {
            "feedback_persisted": 0,
            "feedback_duplicates": 0,
            "feedback_deferred": 0,
            "feedback_rotations": 0,
            "feedback_boundary_blocks": 0,
            "feedback_write_attempts": 0,
            "feedback_duplicate_retries": 0,
            "feedback_artifact_rows_written": 0,
            "feedback_provenance_rows_written": 0,
            "feedback_event_rows_written": 0,
            "feedback_total_rows_written": 0,
            "feedback_payload_bytes_written": 0,
        },
    )

    def target(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal target_calls
        target_calls += 1
        return {
            "training_runs": 0,
            "training_duplicates": 0,
            "training_deferred": 0,
            "training_insufficient_source_cycles": 1,
            "defer_suppressions": 0,
            "suppression_duplicate_retries": 0,
            "decision_write_attempts": 0,
            "decision_writes_suppressed": 0,
            "decision_duplicate_retries": 0,
            "operational_artifact_rows_written": 0,
            "operational_provenance_rows_written": 0,
            "operational_run_rows_written": 0,
            "operational_feedback_rows_written": 0,
            "operational_defer_artifact_rows_written": 0,
            "operational_payload_bytes_written": 0,
            "operational_source_rows_consumed": 0,
        }

    def health(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal health_calls
        health_calls += 1
        return {
            "health_attempts": 1,
            "health_snapshots": 0,
            "health_state_delta_writes": 0,
            "health_heartbeat_writes": 0,
            "health_writes_suppressed": 1,
            "health_rows_written": 0,
            "health_payload_bytes_written": 0,
            "health_authority_mismatches": 0,
        }

    monkeypatch.setattr(consumer, "run_candidate_aware_backlog", target)

    def proof_repository(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal proof_repository_calls
        proof_repository_calls += 1
        return _candidate_proof_result()

    monkeypatch.setattr(
        consumer,
        "process_candidate_proof_repository_backlog",
        proof_repository,
    )
    monkeypatch.setattr(
        consumer,
        "process_retention_backlog",
        lambda connection, *, max_batch: {
            "retention_scanned": 0,
            "retention_quarantined": 0,
            "retention_restored": 0,
            "retention_swept": 0,
            "retention_retained": 0,
            "retention_skipped": 0,
        },
    )
    monkeypatch.setattr(consumer, "process_health_snapshot", health)

    def wait(*args: object, **kwargs: object) -> list[tuple[str, str]]:
        nonlocal waits
        waits += 1
        return []

    event_consumer_loop(
        object(),
        max_batch=8,
        should_stop=lambda: waits >= 2,
        wait_for_notifications=wait,
        session_id="00000000-0000-0000-0000-000000000001",
        source_head="a" * 40,
    )

    assert target_calls == 1
    assert proof_repository_calls == 1
    assert health_calls == 2


def test_retention_backlog_reports_only_derived_cache_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        consumer,
        "run_retention_pass",
        lambda connection, *, now, grace_seconds, limit: {
            "scanned": 2,
            "quarantined": 1,
            "restored": 0,
            "swept": 1,
            "retained": 0,
            "skipped": 0,
        },
    )

    result = process_retention_backlog(object(), max_batch=8)

    assert result == {
        "retention_scanned": 2,
        "retention_quarantined": 1,
        "retention_restored": 0,
        "retention_swept": 1,
        "retention_retained": 0,
        "retention_skipped": 0,
    }


def test_health_snapshot_is_collected_and_persisted_without_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {
        "snapshot_hash": "a" * 64,
        "authority_counters": {
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
        },
        "no_authority": {"trading_authority": False},
    }
    monkeypatch.setattr(
        consumer,
        "collect_health_snapshot",
        lambda connection, *, source_head: snapshot,
    )
    monkeypatch.setattr(
        consumer,
        "persist_health_snapshot",
        lambda connection, value: {
            "status": "PERSISTED",
            "snapshot_hash": "a" * 64,
            "emission_reason": "STATE_DELTA",
            "semantic_state_changed": True,
            "heartbeat_due": False,
            "rows_written": 2,
            "payload_bytes_written": 512,
            "writes_suppressed": 0,
        },
    )

    result = process_health_snapshot(object(), source_head="b" * 40)

    assert result == {
        "health_attempts": 1,
        "health_snapshots": 1,
        "health_state_delta_writes": 1,
        "health_heartbeat_writes": 0,
        "health_writes_suppressed": 0,
        "health_rows_written": 2,
        "health_payload_bytes_written": 512,
        "health_authority_mismatches": 0,
    }


def test_health_snapshot_reports_semantic_no_delta_suppression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {
        "snapshot_hash": "a" * 64,
        "authority_counters": {
            "run_authority_mismatch_count": 0,
            "feedback_authority_mismatch_count": 0,
            **consumer._ZERO_AUTHORITY_COUNTERS,
        },
    }
    monkeypatch.setattr(
        consumer,
        "collect_health_snapshot",
        lambda connection, *, source_head: snapshot,
    )
    monkeypatch.setattr(
        consumer,
        "persist_health_snapshot",
        lambda connection, value: {
            "status": "SUPPRESSED_NO_DELTA",
            "snapshot_hash": "a" * 64,
            "semantic_state_changed": False,
            "heartbeat_due": False,
            "rows_written": 0,
            "payload_bytes_written": 0,
            "writes_suppressed": 1,
        },
    )

    result = process_health_snapshot(object(), source_head="b" * 40)

    assert result == {
        "health_attempts": 1,
        "health_snapshots": 0,
        "health_state_delta_writes": 0,
        "health_heartbeat_writes": 0,
        "health_writes_suppressed": 1,
        "health_rows_written": 0,
        "health_payload_bytes_written": 0,
        "health_authority_mismatches": 0,
    }


def test_health_snapshot_rejects_nonzero_direct_authority_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counters = {
        "run_authority_mismatch_count": 0,
        "feedback_authority_mismatch_count": 0,
        **consumer._ZERO_AUTHORITY_COUNTERS,
    }
    counters["order_or_probe_count"] = 1
    monkeypatch.setattr(
        consumer,
        "collect_health_snapshot",
        lambda connection, *, source_head: {
            "snapshot_hash": "a" * 64,
            "authority_counters": counters,
        },
    )

    with pytest.raises(AlrEventConsumerError, match="health_authority_counters_invalid"):
        process_health_snapshot(object(), source_head="b" * 40)


def test_dsn_file_must_be_private_and_explicitly_local(tmp_path: Path) -> None:
    dsn_file = tmp_path / "alr-shadow.dsn"
    dsn_file.write_text(
        "host=127.0.0.1 port=5432 dbname=trading_ai user=alr_shadow pass" "word=not-a-real-secret\n",
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


def test_runtime_source_head_must_match_checkout_before_database_use(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    head = "a" * 40
    monkeypatch.setattr(
        consumer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=f"{head}\n",
        ),
    )

    assert verify_runtime_source_head(head, repo_root=tmp_path) == head
    with pytest.raises(AlrEventConsumerError, match="source_head_mismatch"):
        verify_runtime_source_head("b" * 40, repo_root=tmp_path)

    source = Path(consumer.__file__).read_text(encoding="utf-8")
    assert "ALR_RECONCILE_AFTER" not in source
    assert "reconcile_after" not in source


def test_main_emits_exact_zero_authority_counter_vector(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(consumer, "run_event_consumer", lambda **kwargs: _drain_result())

    assert consumer.main(
        [
            "--dsn-file",
            "/tmp/alr-shadow.dsn",
            "--lock-file",
            "/tmp/alr-shadow.lock",
            "--source-head",
            "a" * 40,
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["authority_counters"] == {
        "exchange_contact_count": 0,
        "trading_action_count": 0,
        "order_or_probe_count": 0,
        "decision_lease_count": 0,
        "cost_gate_change_count": 0,
        "proof_claim_count": 0,
        "serving_promotion_count": 0,
        "latest_pointer_update_count": 0,
    }


def test_listen_wait_boundedly_drains_prepopulated_queue_without_dropping_remainder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        def __init__(self) -> None:
            self.notifies = [
                SimpleNamespace(
                    channel=ALR_SCANNER_NOTIFY_CHANNEL,
                    payload=_notification_payload(scan_id=f"scan-{index}"),
                )
                for index in range(3)
            ]
            self.polls = 0

        def poll(self) -> None:
            self.polls += 1

    connection = Connection()
    monkeypatch.setattr(consumer.select, "select", lambda *args: ([], [], []))
    first = wait_for_pg_notifications(connection, timeout_seconds=1.0, max_batch=2)

    assert len(first) == 2
    assert len(connection.notifies) == 1
    assert connection.polls == 0
    second = wait_for_pg_notifications(connection, timeout_seconds=1.0, max_batch=2)
    assert len(second) == 1
    assert connection.notifies == []
