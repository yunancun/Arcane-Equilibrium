from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ml_training import alr_event_consumer as consumer
from ml_training import alr_freshness_runtime as freshness
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
    process_health_snapshot,
    process_outcome_feedback_backlog,
    process_retention_backlog,
    run_operational_backlog,
    verify_runtime_source_head,
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

    assert calls == ["feedback", "target", "retention", "health"]
    assert result["feedback_rotations"] == 1
    assert result["training_runs"] == 0
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
