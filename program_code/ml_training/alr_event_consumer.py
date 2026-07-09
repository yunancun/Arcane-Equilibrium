"""Event-driven, evidence-only consumer for persisted Rust scanner snapshots."""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import shlex
import signal
import stat
import threading
from contextlib import contextmanager
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml_training.alr_persistence_repository import (
    fetch_unseen_scanner_snapshots,
    load_restart_state,
    persist_scanner_cycle,
)
from ml_training.alr_retention_repository import run_retention_pass
from ml_training.alr_operational_repository import (
    fetch_untrained_scanner_cycles,
    persist_statistical_run,
)
from ml_training.alr_outcome_feedback import build_outcome_feedback
from ml_training.alr_outcome_feedback_repository import (
    fetch_unreviewed_outcome_runs,
    persist_outcome_feedback,
)
from ml_training.alr_scanner_snapshot_adapter import adapt_scanner_snapshot
from ml_training.alr_scanner_statistical_experiment import (
    AlrScannerStatisticalExperimentError,
    build_scanner_statistical_experiment,
)


ALR_SCANNER_NOTIFY_CHANNEL = "alr_scanner_snapshot_v1"
_NOTIFICATION_SCHEMA_VERSION = "alr_scanner_notification_v1"
_NOTIFICATION_FIELDS = {"schema_version", "scan_id", "ts_ms"}
_SINGLE_INSTANCE_LOCK_NAME = "alr_event_consumer_v1"
_LOCAL_DSN_REQUIRED = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "trading_ai",
    "user": "alr_shadow",
}
_DSN_FORBIDDEN_KEYS = {"hostaddr", "service", "servicefile"}
_SOURCE_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_RETENTION_GRACE_SECONDS = 900


class AlrEventConsumerError(ValueError):
    """An ALR notification or consumer control cannot be handled safely."""


def parse_scanner_notification(channel: str, payload: str) -> dict[str, Any]:
    """Validate a source-identity-only notification before it can wake ALR."""
    if channel != ALR_SCANNER_NOTIFY_CHANNEL:
        raise AlrEventConsumerError("notification_channel_invalid")
    try:
        event = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AlrEventConsumerError("notification_json_invalid") from exc
    if not isinstance(event, dict):
        raise AlrEventConsumerError("notification_not_mapping")
    if set(event) != _NOTIFICATION_FIELDS:
        raise AlrEventConsumerError("notification_fields_invalid")
    if event.get("schema_version") != _NOTIFICATION_SCHEMA_VERSION:
        raise AlrEventConsumerError("notification_schema_invalid")
    if not isinstance(event.get("scan_id"), str) or not event["scan_id"].strip():
        raise AlrEventConsumerError("notification_scan_id_invalid")
    ts_ms = event.get("ts_ms")
    if isinstance(ts_ms, bool) or not isinstance(ts_ms, int) or ts_ms < 0:
        raise AlrEventConsumerError("notification_ts_ms_invalid")
    return {
        "schema_version": _NOTIFICATION_SCHEMA_VERSION,
        "scan_id": event["scan_id"],
        "ts_ms": ts_ms,
    }


def acquire_single_instance(connection: Any) -> bool:
    """Try the session-scoped database lock; a busy lock is fail-closed."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s))",
            (_SINGLE_INSTANCE_LOCK_NAME,),
        )
        result = cursor.fetchone()
    connection.commit()
    if result is None:
        raise AlrEventConsumerError("single_instance_lock_result_missing")
    acquired = _row_value(result, 0, "pg_try_advisory_lock")
    if not isinstance(acquired, bool):
        raise AlrEventConsumerError("single_instance_lock_result_invalid")
    return acquired


def release_single_instance(connection: Any) -> None:
    """Release the session lock during graceful shutdown."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_unlock(hashtext(%s))",
            (_SINGLE_INSTANCE_LOCK_NAME,),
        )
    connection.commit()


def drain_notified_backlog(
    connection: Any,
    notifications: Iterable[tuple[str, str]],
    *,
    max_batch: int,
) -> dict[str, int]:
    """Validate a notification burst and reconcile one bounded source backlog.

    Notifications are wake-up hints only.  Scanner rows remain the sole source
    of cycle content, so a missed or coalesced notification cannot create a
    synthetic learning input.
    """
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= 256:
        raise AlrEventConsumerError("backlog_batch_limit_invalid")

    notification_count = 0
    for notification in notifications:
        if not isinstance(notification, tuple) or len(notification) != 2:
            raise AlrEventConsumerError("notification_tuple_invalid")
        channel, payload = notification
        parse_scanner_notification(channel, payload)
        notification_count += 1

    try:
        restart_state = load_restart_state(connection)
        processed_source_keys = set(restart_state["processed_source_keys"])
        watermark = restart_state["watermark"]
        rows = fetch_unseen_scanner_snapshots(connection, limit=max_batch)
        persisted = 0
        duplicates = 0
        for row in rows:
            cycle = adapt_scanner_snapshot(
                row,
                processed_source_keys=processed_source_keys,
                watermark=watermark,
            )
            result = persist_scanner_cycle(connection, cycle)
            status = result.get("status")
            if status == "PERSISTED":
                persisted += 1
                processed_source_keys.add(cycle["source"]["source_key"])
                watermark = cycle["next_watermark"]
            elif status == "DUPLICATE":
                duplicates += 1
                processed_source_keys.add(cycle["source"]["source_key"])
            else:
                raise AlrEventConsumerError("persistence_status_invalid")
        # A no-row read also opens a transaction under psycopg2.  End it before
        # waiting again so PostgreSQL can deliver the next LISTEN notification.
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "notifications_seen": notification_count,
        "rows_seen": len(rows),
        "persisted": persisted,
        "duplicates": duplicates,
    }


@contextmanager
def runtime_file_lock(lock_path: Path) -> Iterator[None]:
    """Hold a nonblocking local process lock for the consumer lifetime."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - P2 target is Linux only
        raise AlrEventConsumerError("runtime_file_lock_unsupported") from exc

    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        lock_path,
        os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlrEventConsumerError("runtime_file_lock_busy") from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def event_consumer_loop(
    connection: Any,
    *,
    max_batch: int,
    should_stop: Any,
    wait_for_notifications: Any,
    source_head: str | None = None,
) -> dict[str, int]:
    """Reconcile once, then drain only validated PostgreSQL LISTEN wakes."""
    totals = {
        "drains": 0,
        "notifications_seen": 0,
        "rows_seen": 0,
        "persisted": 0,
        "duplicates": 0,
    }

    _accumulate(totals, drain_notified_backlog(connection, [], max_batch=max_batch))
    if source_head is not None:
        _accumulate_feedback(
            totals,
            process_outcome_feedback_backlog(connection, max_batch=max_batch),
        )
        _accumulate_operational(
            totals,
            run_operational_backlog(
                connection,
                source_head=source_head,
                max_batch=max_batch,
            ),
        )
        _accumulate_retention(
            totals,
            process_retention_backlog(connection, max_batch=max_batch),
        )
    while not should_stop():
        notifications = wait_for_notifications(connection, timeout_seconds=1.0)
        if should_stop():
            break
        if not notifications:
            continue
        _accumulate(
            totals,
            drain_notified_backlog(connection, notifications, max_batch=max_batch),
        )
        if source_head is not None:
            _accumulate_feedback(
                totals,
                process_outcome_feedback_backlog(connection, max_batch=max_batch),
            )
            _accumulate_operational(
                totals,
                run_operational_backlog(
                    connection,
                    source_head=source_head,
                    max_batch=max_batch,
                ),
            )
            _accumulate_retention(
                totals,
                process_retention_backlog(connection, max_batch=max_batch),
            )
    return totals


def process_outcome_feedback_backlog(connection: Any, *, max_batch: int) -> dict[str, int]:
    """Persist bounded P2-5 outcome feedback; deferred evidence rotates targets.

    There is no approved runtime proof/reward producer in the current service
    boundary.  The empty input is intentionally bridged to `DEFER_EVIDENCE`,
    rather than being synthesized into profit, proof, or promotion evidence.
    A future producer may supply artifacts through the same pure builder only
    after its own explicit authority review.
    """
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= 256:
        raise AlrEventConsumerError("feedback_batch_limit_invalid")
    rows = fetch_unreviewed_outcome_runs(connection, limit=min(max_batch, 64))
    totals = {
        "feedback_persisted": 0,
        "feedback_duplicates": 0,
        "feedback_deferred": 0,
        "feedback_rotations": 0,
        "feedback_boundary_blocks": 0,
    }
    for row in rows:
        if not isinstance(row, Mapping):
            raise AlrEventConsumerError("feedback_row_invalid")
        feedback = build_outcome_feedback(
            run={
                "run_hash": row.get("run_hash"),
                "candidate_artifact_hash": row.get("candidate_artifact_hash"),
            },
            candidate_artifact=row.get("candidate_artifact"),
        )
        persisted = persist_outcome_feedback(connection, feedback)
        status = persisted.get("status")
        if status == "PERSISTED":
            totals["feedback_persisted"] += 1
        elif status == "DUPLICATE":
            totals["feedback_duplicates"] += 1
        else:
            raise AlrEventConsumerError("feedback_persistence_status_invalid")
        feedback_status = persisted.get("feedback_status")
        if feedback_status == "DEFER_EVIDENCE":
            totals["feedback_deferred"] += 1
            if persisted.get("rotate_next_target") is True:
                totals["feedback_rotations"] += 1
        elif feedback_status == "BLOCKED_BOUNDARY":
            totals["feedback_boundary_blocks"] += 1
        elif feedback_status != "EVIDENCE_OBSERVED_NO_PROMOTION":
            raise AlrEventConsumerError("feedback_status_invalid")
    return totals


def process_retention_backlog(connection: Any, *, max_batch: int) -> dict[str, int]:
    """Run one bounded two-phase pass over ALR-owned derived cache only."""
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= 256:
        raise AlrEventConsumerError("retention_batch_limit_invalid")
    result = run_retention_pass(
        connection,
        now=datetime.now(timezone.utc),
        grace_seconds=_RETENTION_GRACE_SECONDS,
        limit=min(max_batch, 64),
    )
    required = {"scanned", "quarantined", "restored", "swept", "retained", "skipped"}
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("retention_result_invalid")
    return {f"retention_{key}": result[key] for key in required}


def run_operational_backlog(
    connection: Any,
    *,
    source_head: str,
    max_batch: int,
) -> dict[str, int]:
    """Build one bounded P2-4 research challenger from ALR-ledger source rows.

    The scanner notification does not carry learning content.  This function
    reads immutable ALR source artifacts after a scanner drain, runs only the
    pure recurrence/novelty statistical experiment, and persists a challenger
    whose after-cost verdict remains ``DEFER_EVIDENCE``.
    """
    if not isinstance(source_head, str) or not _SOURCE_HEAD_RE.fullmatch(source_head):
        raise AlrEventConsumerError("operational_source_head_invalid")
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= 256:
        raise AlrEventConsumerError("operational_batch_limit_invalid")
    if max_batch < 3:
        return _operational_result("INSUFFICIENT_SOURCE_CYCLES")
    cycles = fetch_untrained_scanner_cycles(connection, limit=min(max_batch, 64))
    if len(cycles) < 3:
        return _operational_result("INSUFFICIENT_SOURCE_CYCLES")
    try:
        experiment = build_scanner_statistical_experiment(
            source_head=source_head,
            cycles=cycles,
        )
    except AlrScannerStatisticalExperimentError:
        # A malformed or insufficient evidence set cannot claim an edge and
        # does not terminate the listener. P2-5 persists granular defer rows.
        return _operational_result("DEFER_EVIDENCE")
    persisted = persist_statistical_run(connection, experiment)
    status = persisted.get("status")
    if status not in {"PERSISTED", "DUPLICATE"}:
        raise AlrEventConsumerError("operational_persistence_status_invalid")
    result = _operational_result(status)
    result["training_runs"] = 1 if status == "PERSISTED" else 0
    result["training_duplicates"] = 1 if status == "DUPLICATE" else 0
    return result


def read_local_dsn_file(dsn_path: Path) -> str:
    """Read a private local-PG DSN without falling back to ambient credentials."""
    try:
        metadata = dsn_path.lstat()
    except OSError as exc:
        raise AlrEventConsumerError("dsn_file_unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise AlrEventConsumerError("dsn_file_not_regular")
    if metadata.st_mode & 0o077:
        raise AlrEventConsumerError("dsn_file_permissions_invalid")
    try:
        dsn = dsn_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AlrEventConsumerError("dsn_file_unreadable") from exc
    if not dsn:
        raise AlrEventConsumerError("dsn_file_blank")
    _validate_local_dsn(dsn)
    return dsn


def wait_for_pg_notifications(
    connection: Any,
    *,
    timeout_seconds: float,
) -> list[tuple[str, str]]:
    """Wait for a PostgreSQL socket event; an idle timeout never drains work."""
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
        or timeout_seconds > 60
    ):
        raise AlrEventConsumerError("notification_wait_timeout_invalid")
    ready, _, _ = select.select([connection], [], [], timeout_seconds)
    if not ready:
        return []
    connection.poll()
    notifications = list(connection.notifies)
    connection.notifies.clear()
    pairs: list[tuple[str, str]] = []
    for notification in notifications:
        channel = getattr(notification, "channel", None)
        payload = getattr(notification, "payload", None)
        if not isinstance(channel, str) or not isinstance(payload, str):
            raise AlrEventConsumerError("notification_transport_invalid")
        pairs.append((channel, payload))
    return pairs


def run_event_consumer(
    *,
    dsn_path: Path,
    lock_path: Path,
    max_batch: int,
    source_head: str | None = None,
) -> dict[str, int]:
    """Run the Linux shadow consumer until SIGTERM/SIGINT requests shutdown."""
    dsn = read_local_dsn_file(dsn_path)
    stop_event = threading.Event()
    previous_handlers = _install_shutdown_handlers(stop_event)
    connection: Any | None = None
    db_lock_acquired = False
    try:
        with runtime_file_lock(lock_path):
            connection = _connect_listener(dsn)
            db_lock_acquired = acquire_single_instance(connection)
            if not db_lock_acquired:
                raise AlrEventConsumerError("single_instance_lock_busy")
            return event_consumer_loop(
                connection,
                max_batch=max_batch,
                should_stop=stop_event.is_set,
                wait_for_notifications=wait_for_pg_notifications,
                source_head=source_head,
            )
    finally:
        if connection is not None:
            if db_lock_acquired:
                release_single_instance(connection)
            connection.close()
        _restore_shutdown_handlers(previous_handlers)


def _connect_listener(dsn: str) -> Any:
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import RealDictCursor  # type: ignore
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise AlrEventConsumerError("psycopg2_unavailable") from exc
    connection = psycopg2.connect(
        dsn,
        connect_timeout=5,
        cursor_factory=RealDictCursor,
    )
    connection.autocommit = False
    with connection.cursor() as cursor:
        cursor.execute(f"LISTEN {ALR_SCANNER_NOTIFY_CHANNEL}")
    connection.commit()
    return connection


def _install_shutdown_handlers(stop_event: threading.Event) -> dict[int, Any]:
    def request_stop(signum: int, frame: Any) -> None:
        del signum, frame
        stop_event.set()

    previous: dict[int, Any] = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, request_stop)
    return previous


def _restore_shutdown_handlers(previous: Mapping[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _validate_local_dsn(dsn: str) -> None:
    try:
        parts = shlex.split(dsn)
    except ValueError as exc:
        raise AlrEventConsumerError("dsn_invalid") from exc
    parsed: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise AlrEventConsumerError("dsn_invalid")
        key, value = part.split("=", 1)
        if not key or not value or key in parsed:
            raise AlrEventConsumerError("dsn_invalid")
        parsed[key] = value
    if _DSN_FORBIDDEN_KEYS.intersection(parsed):
        raise AlrEventConsumerError("dsn_not_local_trading_ai")
    if any(parsed.get(key) != value for key, value in _LOCAL_DSN_REQUIRED.items()):
        raise AlrEventConsumerError("dsn_not_local_trading_ai")


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for the gated user-level scanner-shadow service."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-file", required=True, type=Path)
    parser.add_argument("--lock-file", required=True, type=Path)
    parser.add_argument("--max-batch", type=int, default=32)
    parser.add_argument("--source-head", default=os.environ.get("ALR_SOURCE_HEAD"))
    arguments = parser.parse_args(argv)
    result = run_event_consumer(
        dsn_path=arguments.dsn_file,
        lock_path=arguments.lock_file,
        max_batch=arguments.max_batch,
        source_head=arguments.source_head,
    )
    print(
        json.dumps(
            {
                "schema_version": "alr_event_consumer_result_v1",
                "result": result,
                "authority": {
                    "exchange_authority": False,
                    "trading_authority": False,
                    "proof_authority": False,
                    "serving_authority": False,
                    "promotion_authority": False,
                },
            },
            sort_keys=True,
        )
    )
    return 0


def _accumulate(totals: dict[str, int], result: Mapping[str, int]) -> None:
    required = {"notifications_seen", "rows_seen", "persisted", "duplicates"}
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("backlog_result_invalid")
    totals["drains"] += 1
    for key in required:
        totals[key] += result[key]


def _operational_result(status: str) -> dict[str, int]:
    if status not in {"PERSISTED", "DUPLICATE", "DEFER_EVIDENCE", "INSUFFICIENT_SOURCE_CYCLES"}:
        raise AlrEventConsumerError("operational_status_invalid")
    return {
        "training_runs": 0,
        "training_duplicates": 0,
        "training_deferred": 1 if status == "DEFER_EVIDENCE" else 0,
        "training_insufficient_source_cycles": 1
        if status == "INSUFFICIENT_SOURCE_CYCLES"
        else 0,
    }


def _accumulate_operational(totals: dict[str, int], result: Mapping[str, int]) -> None:
    required = {
        "training_runs",
        "training_duplicates",
        "training_deferred",
        "training_insufficient_source_cycles",
    }
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("operational_result_invalid")
    for key in required:
        totals[key] = totals.get(key, 0) + result[key]


def _accumulate_feedback(totals: dict[str, int], result: Mapping[str, int]) -> None:
    required = {
        "feedback_persisted",
        "feedback_duplicates",
        "feedback_deferred",
        "feedback_rotations",
        "feedback_boundary_blocks",
    }
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("feedback_result_invalid")
    for key in required:
        totals[key] = totals.get(key, 0) + result[key]


def _accumulate_retention(totals: dict[str, int], result: Mapping[str, int]) -> None:
    required = {
        "retention_scanned",
        "retention_quarantined",
        "retention_restored",
        "retention_swept",
        "retention_retained",
        "retention_skipped",
    }
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("retention_result_invalid")
    for key in required:
        totals[key] = totals.get(key, 0) + result[key]


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


if __name__ == "__main__":  # pragma: no cover - exercised by the user unit
    raise SystemExit(main())
