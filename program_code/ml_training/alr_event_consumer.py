"""Event-driven, evidence-only consumer for persisted Rust scanner snapshots."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import select
import shlex
import signal
import stat
import struct
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml_training.alr_consumer_repository import (
    fail_consumer_session,
    new_session_id,
    start_consumer_session,
    stop_consumer_session,
)
from ml_training.alr_freshness_runtime import (
    drain_fresh_lane,
    drain_historical_lane,
    drain_notified_identities,
)
from ml_training.alr_retention_repository import run_retention_pass
from ml_training.alr_operational_repository import (
    fetch_recent_candidate_scanner_cycles,
    fetch_recent_candidate_projection_decisions,
    fetch_untrained_scanner_cycles,
    persist_candidate_learning_projection,
    persist_statistical_run,
)
from ml_training.alr_candidate_evidence_adapter import (
    load_candidate_evidence_snapshot,
)
from ml_training.alr_candidate_policy import (
    CandidatePolicyError,
    validate_candidate_policy_configuration,
)
from ml_training.learning_runtime_manifest import (
    evaluate_runtime_digest_pin,
    try_build_learning_runtime_manifest,
)
from ml_training.candidate_proof_repository import (
    BATCH_SCHEMA_VERSION as CANDIDATE_PROOF_BATCH_SCHEMA_VERSION,
    compute_candidate_proof_repository_receipt_hash,
    discover_candidate_proof_receipts,
)
from ml_training.alr_health_repository import (
    collect_health_snapshot,
    persist_health_snapshot,
)
from ml_training.alr_outcome_feedback import build_outcome_feedback
from ml_training.alr_outcome_feedback_repository import (
    fetch_unreviewed_outcome_runs,
    persist_outcome_feedback,
)
from ml_training.alr_scanner_statistical_experiment import (
    AlrScannerStatisticalExperimentError,
    build_candidate_aware_learning_projection,
    build_scanner_statistical_experiment,
)
from ml_training.alr_safe_file import (
    AlrSafeFileError,
    CHANGED,
    MODE_INVALID,
    NOT_REGULAR,
    SIZE_INVALID,
    read_bounded_regular_file,
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
_CANDIDATE_EVIDENCE_MAX_AGE_SECONDS = 172_800
_CANDIDATE_EVIDENCE_MAX_FILES = 128
_CANDIDATE_EVIDENCE_MAX_BYTES = 64 * 1024 * 1024
_IN_ACCESS_EVENT = struct.Struct("iIII")
_IN_CREATE = 0x00000100
_IN_DELETE = 0x00000200
_IN_MOVED_TO = 0x00000080
_IN_CLOSE_WRITE = 0x00000008
_IN_DELETE_SELF = 0x00000400
_IN_MOVE_SELF = 0x00000800
_IN_UNMOUNT = 0x00002000
_IN_Q_OVERFLOW = 0x00004000
_IN_IGNORED = 0x00008000
_IN_ONLYDIR = 0x01000000
_IN_DONT_FOLLOW = 0x02000000
# The immutable publisher links the new board before pruning the old board.
# DELETE is the retry wake when a CREATE reconciliation observes that transient.
_INOTIFY_WAKE_MASK = _IN_CREATE | _IN_DELETE | _IN_MOVED_TO | _IN_CLOSE_WRITE
_INOTIFY_INVALIDATION_MASK = _IN_DELETE_SELF | _IN_MOVE_SELF | _IN_UNMOUNT | _IN_IGNORED
_INOTIFY_WATCH_MASK = _INOTIFY_WAKE_MASK | (
    _IN_DELETE_SELF | _IN_MOVE_SELF | _IN_UNMOUNT
) | _IN_ONLYDIR | _IN_DONT_FOLLOW
_IMMUTABLE_CANDIDATE_BOARD_NAME_RE = re.compile(
    r"^blocked_outcome_review_[0-9]{8}T[0-9]{6}Z\.json$"
)
_ZERO_AUTHORITY_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_promotion_count": 0,
    "latest_pointer_update_count": 0,
}


class AlrEventConsumerError(ValueError):
    """An ALR notification or consumer control cannot be handled safely."""


class CandidateBoardEventSource:
    """Linux inotify wake source; event names never carry learning content."""

    def __init__(
        self,
        directory: Path,
        *,
        event_fd: int,
        watch_descriptor: int,
        directory_fd: int,
        reopen_watch: Any,
    ) -> None:
        self._directory = directory
        self._event_fd = event_fd
        self._watch_descriptor = watch_descriptor
        self._directory_fd = directory_fd
        self._reopen_watch = reopen_watch
        self._reconciliation_required = True
        self._closed = False

    def __enter__(self) -> "CandidateBoardEventSource":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fileno(self) -> int:
        if self._closed:
            raise AlrEventConsumerError("candidate_board_event_source_closed")
        return self._event_fd

    def consume_reconciliation_request(self) -> bool:
        requested = self._reconciliation_required
        self._reconciliation_required = False
        return requested

    def drain_ready(self) -> None:
        """Drain bounded kernel records and reduce every valid event to one wake."""
        if self._closed:
            raise AlrEventConsumerError("candidate_board_event_source_closed")
        try:
            payload = os.read(self._event_fd, 64 * 1024)
        except BlockingIOError:
            return
        except OSError as exc:
            if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
                return
            raise AlrEventConsumerError("candidate_board_event_read_failed") from exc
        if not payload:
            return
        offset = 0
        invalidated = False
        while offset < len(payload):
            if len(payload) - offset < _IN_ACCESS_EVENT.size:
                raise AlrEventConsumerError("candidate_board_event_truncated")
            watch_descriptor, mask, _cookie, name_length = _IN_ACCESS_EVENT.unpack_from(
                payload, offset
            )
            offset += _IN_ACCESS_EVENT.size
            if name_length > 4096 or offset + name_length > len(payload):
                raise AlrEventConsumerError("candidate_board_event_name_invalid")
            raw_name = bytes(payload[offset : offset + name_length])
            offset += name_length
            if watch_descriptor == -1 and mask & _IN_Q_OVERFLOW:
                invalidated = True
                self._reconciliation_required = True
                continue
            if watch_descriptor != self._watch_descriptor:
                continue
            if mask & _INOTIFY_INVALIDATION_MASK:
                invalidated = True
                self._reconciliation_required = True
                continue
            if mask & _INOTIFY_WAKE_MASK:
                name = raw_name.split(b"\x00", 1)[0]
                try:
                    decoded_name = name.decode("ascii")
                except UnicodeDecodeError:
                    continue
                if _IMMUTABLE_CANDIDATE_BOARD_NAME_RE.fullmatch(decoded_name):
                    self._reconciliation_required = True
        if invalidated:
            new_event_fd, new_watch, new_directory_fd = self._reopen_watch(
                self._directory
            )
            old_event_fd = self._event_fd
            old_directory_fd = self._directory_fd
            self._event_fd = new_event_fd
            self._watch_descriptor = new_watch
            self._directory_fd = new_directory_fd
            _close_candidate_board_watch_descriptors(
                old_event_fd if old_event_fd != new_event_fd else -1,
                old_directory_fd
                if old_directory_fd >= 0 and old_directory_fd != new_directory_fd
                else -1,
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_candidate_board_watch_descriptors(
            self._event_fd,
            self._directory_fd,
        )


def _close_candidate_board_watch_descriptors(
    event_fd: int,
    directory_fd: int,
) -> None:
    try:
        if directory_fd >= 0:
            os.close(directory_fd)
    finally:
        if event_fd >= 0:
            os.close(event_fd)


def open_candidate_board_event_source(
    directory: Path,
    *,
    open_watch: Any = None,
    reopen_watch: Any = None,
) -> CandidateBoardEventSource:
    """Open one nonblocking Linux directory watch with startup reconciliation."""
    opener = open_watch or _open_linux_candidate_board_watch
    reopen = reopen_watch or _open_linux_candidate_board_watch
    event_fd, watch_descriptor, directory_fd = opener(Path(directory))
    return CandidateBoardEventSource(
        Path(directory),
        event_fd=event_fd,
        watch_descriptor=watch_descriptor,
        directory_fd=directory_fd,
        reopen_watch=reopen,
    )


def _open_linux_candidate_board_watch(directory: Path) -> tuple[int, int, int]:
    if sys.platform != "linux":
        raise AlrEventConsumerError("candidate_board_inotify_unsupported")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        init = libc.inotify_init1
        init.argtypes = [ctypes.c_int]
        init.restype = ctypes.c_int
    except (AttributeError, OSError) as exc:
        raise AlrEventConsumerError("candidate_board_inotify_unavailable") from exc
    event_fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
    if event_fd < 0:
        error_number = ctypes.get_errno()
        raise AlrEventConsumerError(
            f"candidate_board_inotify_open_failed:{error_number}"
        ) from OSError(error_number, os.strerror(error_number))
    try:
        watch_descriptor, directory_fd = _add_linux_candidate_board_watch(
            libc,
            event_fd,
            directory,
        )
    except Exception:
        os.close(event_fd)
        raise
    return event_fd, watch_descriptor, directory_fd


def _add_linux_candidate_board_watch(
    libc: Any,
    event_fd: int,
    directory: Path,
) -> tuple[int, int]:
    try:
        before = directory.lstat()
    except OSError as exc:
        raise AlrEventConsumerError("candidate_board_directory_unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise AlrEventConsumerError("candidate_board_directory_invalid")
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY
            | os.O_CLOEXEC
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise AlrEventConsumerError("candidate_board_directory_unavailable") from exc
    try:
        opened = os.fstat(directory_fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise AlrEventConsumerError("candidate_board_directory_changed")
        add_watch = libc.inotify_add_watch
        add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        add_watch.restype = ctypes.c_int
        held_directory_path = os.fsencode(f"/proc/self/fd/{directory_fd}/.")
        descriptor = add_watch(
            event_fd,
            held_directory_path,
            _INOTIFY_WATCH_MASK,
        )
        if descriptor < 0:
            error_number = ctypes.get_errno()
            raise AlrEventConsumerError(
                f"candidate_board_inotify_watch_failed:{error_number}"
            ) from OSError(error_number, os.strerror(error_number))
        after = directory.lstat()
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            raise AlrEventConsumerError("candidate_board_directory_changed")
        return descriptor, directory_fd
    except Exception:
        os.close(directory_fd)
        raise


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
    session_id: str,
) -> dict[str, int]:
    """精確消費 notification identity；notification 不可推進 fresh cursor。"""
    return drain_notified_identities(
        connection,
        notifications,
        max_batch=max_batch,
        session_id=session_id,
        parse_notification=parse_scanner_notification,
        notification_error_type=AlrEventConsumerError,
    )


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
    session_id: str,
    source_head: str | None = None,
    candidate_evidence_directory: Path | None = None,
    candidate_policy: Mapping[str, Any] | None = None,
    candidate_board_source: CandidateBoardEventSource | Any | None = None,
    notification_timeout_seconds: float = 5.0,
    history_interval_seconds: float = 60.0,
    monotonic_seconds: Any = time.monotonic,
    fit_quarantined: bool = False,
) -> dict[str, int]:
    """Fresh 優先 listener；idle reconciliation 後才允許小額 history lane。

    LR1：fit_quarantined=True 時，capture(drain)照常，但 fit-triggering 的 candidate
    projection 轉換被 fence(不再由漂移的 training 面產生新學習候選)。
    """
    totals = {
        "drains": 0,
        "notifications_seen": 0,
        "notifications_received": 0,
        "notifications_consumed": 0,
        "notifications_invalid": 0,
        "rows_seen": 0,
        "persisted": 0,
        "duplicates": 0,
    }
    fresh_result = drain_fresh_lane(
        connection,
        session_id=session_id,
        max_batch=max_batch,
    )
    _accumulate(totals, fresh_result)
    last_history_run = monotonic_seconds()
    if candidate_board_source is not None:
        # Opening the watch is itself the startup full-reconciliation request.
        candidate_board_source.consume_reconciliation_request()
    if source_head is not None:
        _process_operational_cycle(
            totals,
            connection=connection,
            source_head=source_head,
            max_batch=max_batch,
            session_id=session_id,
            candidate_evidence_directory=candidate_evidence_directory,
            candidate_policy=candidate_policy,
            fit_quarantined=fit_quarantined,
        )
    while not should_stop():
        wait_kwargs = {
            "timeout_seconds": notification_timeout_seconds,
            "max_batch": max_batch,
        }
        if candidate_board_source is not None:
            wait_kwargs["candidate_board_source"] = candidate_board_source
        notifications = wait_for_notifications(connection, **wait_kwargs)
        if should_stop():
            break
        candidate_board_wake = (
            candidate_board_source.consume_reconciliation_request()
            if candidate_board_source is not None
            else False
        )
        cycle_rows = 0
        if notifications:
            exact_result = drain_notified_backlog(
                connection,
                notifications,
                max_batch=max_batch,
                session_id=session_id,
            )
            _accumulate(totals, exact_result)
            cycle_rows += exact_result["rows_seen"]
        fresh_result = drain_fresh_lane(
            connection,
            session_id=session_id,
            max_batch=max_batch,
        )
        _accumulate(totals, fresh_result)
        cycle_rows += fresh_result["rows_seen"]
        now = monotonic_seconds()
        if (
            not notifications
            and not candidate_board_wake
            and fresh_result["rows_seen"] == 0
            and now - last_history_run >= history_interval_seconds
        ):
            history_result = drain_historical_lane(
                connection,
                session_id=session_id,
                max_batch=min(max_batch, 8),
            )
            _accumulate(totals, history_result)
            cycle_rows += history_result["rows_seen"]
            last_history_run = now
        if source_head is not None:
            if cycle_rows:
                _process_operational_cycle(
                    totals,
                    connection=connection,
                    source_head=source_head,
                    max_batch=max_batch,
                    session_id=session_id,
                    candidate_evidence_directory=candidate_evidence_directory,
                    candidate_policy=candidate_policy,
                    fit_quarantined=fit_quarantined,
                )
            elif candidate_board_wake:
                _process_candidate_reconciliation(
                    totals,
                    connection=connection,
                    source_head=source_head,
                    max_batch=max_batch,
                    session_id=session_id,
                    candidate_evidence_directory=candidate_evidence_directory,
                    candidate_policy=candidate_policy,
                    fit_quarantined=fit_quarantined,
                )
            else:
                _accumulate_health(
                    totals,
                    process_health_snapshot(
                        connection,
                        source_head=source_head,
                        write_metrics=_build_write_metrics(
                            totals,
                            session_id=session_id,
                        ),
                    ),
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
        "feedback_write_attempts": 0,
        "feedback_duplicate_retries": 0,
        "feedback_artifact_rows_written": 0,
        "feedback_provenance_rows_written": 0,
        "feedback_event_rows_written": 0,
        "feedback_total_rows_written": 0,
        "feedback_payload_bytes_written": 0,
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
        metric_fields = {
            "artifact_rows_written",
            "provenance_rows_written",
            "feedback_event_rows_written",
            "total_rows_written",
            "payload_bytes_written",
            "duplicate_retries",
        }
        if any(
            isinstance(persisted.get(field), bool)
            or not isinstance(persisted.get(field), int)
            or persisted[field] < 0
            for field in metric_fields
        ):
            raise AlrEventConsumerError("feedback_write_metrics_invalid")
        if persisted["total_rows_written"] != (
            persisted["artifact_rows_written"]
            + persisted["provenance_rows_written"]
            + persisted["feedback_event_rows_written"]
        ):
            raise AlrEventConsumerError("feedback_write_metric_total_invalid")
        if (
            status == "PERSISTED"
            and persisted["duplicate_retries"] != 0
        ) or (
            status == "DUPLICATE"
            and persisted["duplicate_retries"] != 1
        ):
            raise AlrEventConsumerError(
                "feedback_duplicate_metric_status_mismatch"
            )
        totals["feedback_write_attempts"] += 1
        totals["feedback_duplicate_retries"] += persisted[
            "duplicate_retries"
        ]
        totals["feedback_artifact_rows_written"] += persisted[
            "artifact_rows_written"
        ]
        totals["feedback_provenance_rows_written"] += persisted[
            "provenance_rows_written"
        ]
        totals["feedback_event_rows_written"] += persisted[
            "feedback_event_rows_written"
        ]
        totals["feedback_total_rows_written"] += persisted[
            "total_rows_written"
        ]
        totals["feedback_payload_bytes_written"] += persisted[
            "payload_bytes_written"
        ]
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


def process_candidate_proof_repository_backlog(
    connection: Any,
    *,
    max_batch: int,
) -> dict[str, int]:
    """Reconstruct current proof inputs from immutable rows with zero writes."""
    if (
        isinstance(max_batch, bool)
        or not isinstance(max_batch, int)
        or not 1 <= max_batch <= 256
    ):
        raise AlrEventConsumerError("candidate_proof_batch_limit_invalid")
    batch = discover_candidate_proof_receipts(
        connection,
        limit=min(max_batch, 64),
    )
    if (
        not isinstance(batch, Mapping)
        or batch.get("schema_version") != CANDIDATE_PROOF_BATCH_SCHEMA_VERSION
        or batch.get("status")
        not in {
            "READY",
            "NO_CURRENT_SELECTED_CANDIDATE",
            "SCHEMA_REQUIRED_OVERFLOW",
        }
    ):
        raise AlrEventConsumerError("candidate_proof_batch_invalid")
    metrics = batch.get("metrics")
    required_metrics = {
        "candidate_projection_rows_read",
        "source_event_rows_read",
        "projection_edge_rows_read",
        "source_event_rows_rechecked",
        "projection_edge_rows_rechecked",
        "outcome_bridge_rows_scanned",
        "outcome_bridge_rows_rechecked",
        "receipts_built",
        "pending_receipts",
        "no_fill_receipts",
        "ready_for_reward_validation_receipts",
        "invalid_receipts",
        "rows_written",
        "payload_bytes_written",
    }
    if (
        not isinstance(metrics, Mapping)
        or set(metrics) != required_metrics
        or any(
            isinstance(metrics[key], bool)
            or not isinstance(metrics[key], int)
            or metrics[key] < 0
            for key in required_metrics
        )
    ):
        raise AlrEventConsumerError("candidate_proof_metrics_invalid")
    if metrics["rows_written"] != 0 or metrics["payload_bytes_written"] != 0:
        raise AlrEventConsumerError("candidate_proof_write_claim")
    receipts = batch.get("receipts")
    if not isinstance(receipts, list) or not all(
        isinstance(item, Mapping) for item in receipts
    ):
        raise AlrEventConsumerError("candidate_proof_receipts_invalid")
    receipt_statuses = [item.get("status") for item in receipts]
    allowed_receipt_statuses = {
        "PENDING_EVIDENCE",
        "no_matched_fills",
        "READY_FOR_REWARD_VALIDATION",
        "INVALID",
    }
    if any(status not in allowed_receipt_statuses for status in receipt_statuses):
        raise AlrEventConsumerError("candidate_proof_receipt_status_invalid")
    expected_counts = {
        "receipts_built": len(receipts),
        "pending_receipts": receipt_statuses.count("PENDING_EVIDENCE"),
        "no_fill_receipts": receipt_statuses.count("no_matched_fills"),
        "ready_for_reward_validation_receipts": receipt_statuses.count(
            "READY_FOR_REWARD_VALIDATION"
        ),
        "invalid_receipts": receipt_statuses.count("INVALID"),
    }
    if any(metrics[key] != value for key, value in expected_counts.items()):
        raise AlrEventConsumerError("candidate_proof_receipt_metrics_mismatch")
    if sum(expected_counts[key] for key in expected_counts if key != "receipts_built") != len(
        receipts
    ):
        raise AlrEventConsumerError("candidate_proof_receipt_status_invalid")
    if (
        batch["status"] == "READY" and not receipts
    ) or (
        batch["status"] != "READY" and receipts
    ) or (
        batch["status"] == "SCHEMA_REQUIRED_OVERFLOW"
        and metrics["outcome_bridge_rows_scanned"] <= min(max_batch, 64)
    ):
        raise AlrEventConsumerError("candidate_proof_batch_status_mismatch")
    no_authority = batch.get("no_authority")
    counters = batch.get("authority_counters")
    expected_no_authority = {
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
    expected_counters = {
        "exchange_contact_count": 0,
        "trading_action_count": 0,
        "order_or_probe_count": 0,
        "decision_lease_count": 0,
        "cost_gate_change_count": 0,
        "proof_claim_count": 0,
        "serving_or_promotion_count": 0,
    }
    if (
        no_authority != expected_no_authority
        or counters != expected_counters
    ):
        raise AlrEventConsumerError("candidate_proof_authority_invalid")
    for receipt in receipts:
        durability = receipt.get("durability")
        if (
            receipt.get("schema_version")
            != "candidate_proof_repository_receipt_v1"
            or receipt.get("projection_identity_status")
            != "RECONSTRUCTED_FROM_HASH_VALIDATED_ROWS"
            or receipt.get("original_ephemeral_projection_hash_attested") is not False
            or receipt.get("receipt_hash")
            != compute_candidate_proof_repository_receipt_hash(receipt)
            or receipt.get("no_authority") != expected_no_authority
            or receipt.get("authority_counters") != expected_counters
            or not isinstance(durability, Mapping)
            or durability.get("source_container")
            not in {
                "HASH_VALIDATED_APPEND_ONLY_ROW",
                "NO_MATCHING_HASH_VALIDATED_ROW",
            }
            or durability.get("runtime_or_exchange_attested") is not False
            or durability.get("receipt_persisted") is not False
        ):
            raise AlrEventConsumerError("candidate_proof_receipt_authority_invalid")
    return {
        "candidate_proof_scans": 1,
        "candidate_proof_projection_rows_read": metrics[
            "candidate_projection_rows_read"
        ],
        "candidate_proof_source_event_rows_read": metrics[
            "source_event_rows_read"
        ],
        "candidate_proof_projection_edge_rows_read": metrics[
            "projection_edge_rows_read"
        ],
        "candidate_proof_source_event_rows_rechecked": metrics[
            "source_event_rows_rechecked"
        ],
        "candidate_proof_projection_edge_rows_rechecked": metrics[
            "projection_edge_rows_rechecked"
        ],
        "candidate_proof_outcome_bridge_rows_scanned": metrics[
            "outcome_bridge_rows_scanned"
        ],
        "candidate_proof_outcome_bridge_rows_rechecked": metrics[
            "outcome_bridge_rows_rechecked"
        ],
        "candidate_proof_receipts": metrics["receipts_built"],
        "candidate_proof_pending": metrics["pending_receipts"],
        "candidate_proof_no_fill": metrics["no_fill_receipts"],
        "candidate_proof_ready_for_reward_validation": metrics[
            "ready_for_reward_validation_receipts"
        ],
        "candidate_proof_invalid": metrics["invalid_receipts"],
        "candidate_proof_schema_required_overflow": int(
            batch["status"] == "SCHEMA_REQUIRED_OVERFLOW"
        ),
        "candidate_proof_rows_written": 0,
        "candidate_proof_payload_bytes_written": 0,
    }


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


def process_health_snapshot(
    connection: Any,
    *,
    source_head: str,
    write_metrics: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Persist one local ALR health snapshot after a bounded listener cycle."""
    collect_kwargs = (
        {"write_metrics": write_metrics} if write_metrics is not None else {}
    )
    snapshot = collect_health_snapshot(
        connection,
        source_head=source_head,
        **collect_kwargs,
    )
    counters = snapshot.get("authority_counters")
    required_counters = {
        "run_authority_mismatch_count",
        "feedback_authority_mismatch_count",
        *_ZERO_AUTHORITY_COUNTERS,
    }
    if (
        not isinstance(counters, Mapping)
        or set(counters) != required_counters
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counters.values()
        )
        or any(counters[key] != 0 for key in _ZERO_AUTHORITY_COUNTERS)
    ):
        raise AlrEventConsumerError("health_authority_counters_invalid")
    persisted = persist_health_snapshot(connection, snapshot)
    status = persisted.get("status")
    if status not in {"PERSISTED", "SUPPRESSED_NO_DELTA"}:
        raise AlrEventConsumerError("health_persistence_status_invalid")
    emission_reason = persisted.get("emission_reason")
    if status == "PERSISTED" and emission_reason not in {"STATE_DELTA", "HEARTBEAT"}:
        raise AlrEventConsumerError("health_emission_reason_invalid")
    metrics = {
        "rows_written": persisted.get("rows_written"),
        "payload_bytes_written": persisted.get("payload_bytes_written"),
        "writes_suppressed": persisted.get("writes_suppressed"),
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in metrics.values()
    ):
        raise AlrEventConsumerError("health_write_metrics_invalid")
    return {
        "health_attempts": 1,
        "health_snapshots": int(status == "PERSISTED"),
        "health_state_delta_writes": int(
            status == "PERSISTED" and emission_reason == "STATE_DELTA"
        ),
        "health_heartbeat_writes": int(
            status == "PERSISTED" and emission_reason == "HEARTBEAT"
        ),
        "health_writes_suppressed": metrics["writes_suppressed"],
        "health_rows_written": metrics["rows_written"],
        "health_payload_bytes_written": metrics["payload_bytes_written"],
        "health_authority_mismatches": int(
            counters.get("run_authority_mismatch_count", 0)
        )
        + int(counters.get("feedback_authority_mismatch_count", 0)),
    }


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
    if status not in {
        "PERSISTED",
        "DUPLICATE",
        "SUPPRESSED_EQUIVALENT_DEFER",
        "DUPLICATE_SUPPRESSION",
    }:
        raise AlrEventConsumerError("operational_persistence_status_invalid")
    metric_fields = {
        "decision_writes_suppressed",
        "duplicate_retries",
        "artifact_rows_written",
        "provenance_rows_written",
        "run_rows_written",
        "feedback_rows_written",
        "defer_artifact_rows_written",
        "payload_bytes_written",
        "source_rows_consumed",
    }
    if any(
        isinstance(persisted.get(field), bool)
        or not isinstance(persisted.get(field), int)
        or persisted[field] < 0
        for field in metric_fields
    ):
        raise AlrEventConsumerError("operational_write_metrics_invalid")
    result = _operational_result(status)
    result["training_runs"] = 1 if status == "PERSISTED" else 0
    result["training_duplicates"] = 1 if status == "DUPLICATE" else 0
    result["defer_suppressions"] = int(
        status == "SUPPRESSED_EQUIVALENT_DEFER"
    )
    result["suppression_duplicate_retries"] = int(
        status == "DUPLICATE_SUPPRESSION"
    )
    result["decision_write_attempts"] = 1
    result["decision_writes_suppressed"] = persisted[
        "decision_writes_suppressed"
    ]
    result["decision_duplicate_retries"] = persisted["duplicate_retries"]
    result["operational_artifact_rows_written"] = persisted[
        "artifact_rows_written"
    ]
    result["operational_provenance_rows_written"] = persisted[
        "provenance_rows_written"
    ]
    result["operational_run_rows_written"] = persisted["run_rows_written"]
    result["operational_feedback_rows_written"] = persisted[
        "feedback_rows_written"
    ]
    result["operational_defer_artifact_rows_written"] = persisted[
        "defer_artifact_rows_written"
    ]
    result["operational_payload_bytes_written"] = persisted[
        "payload_bytes_written"
    ]
    result["operational_source_rows_consumed"] = persisted[
        "source_rows_consumed"
    ]
    return result


def run_candidate_aware_backlog(
    connection: Any,
    *,
    source_head: str,
    max_batch: int,
    evidence_directory: Path | None = None,
    candidate_policy: Mapping[str, Any] | None = None,
    prior_decisions: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    """Persist one candidate-aware decision node without a V152 training run."""
    if not isinstance(source_head, str) or not _SOURCE_HEAD_RE.fullmatch(source_head):
        raise AlrEventConsumerError("operational_source_head_invalid")
    if (
        isinstance(max_batch, bool)
        or not isinstance(max_batch, int)
        or not 1 <= max_batch <= 256
    ):
        raise AlrEventConsumerError("operational_batch_limit_invalid")
    if max_batch < 3:
        return _operational_result("INSUFFICIENT_SOURCE_CYCLES")
    cycles = fetch_untrained_scanner_cycles(connection, limit=min(max_batch, 64))
    if len(cycles) < 3 and evidence_directory is not None:
        cycles = fetch_recent_candidate_scanner_cycles(
            connection,
            limit=min(max_batch, 64),
        )
    if len(cycles) < 3:
        return _operational_result("INSUFFICIENT_SOURCE_CYCLES")

    evaluated_at = _candidate_evaluation_time(cycles)
    evaluated_datetime = datetime.fromisoformat(
        evaluated_at.replace("Z", "+00:00")
    )
    runtime_policy = dict(candidate_policy or {})
    runtime_policy["decision_ts_s"] = int(evaluated_datetime.timestamp())
    runtime_policy["as_of_utc_date"] = evaluated_datetime.date().isoformat()
    if evidence_directory is None:
        evidence_snapshot = _unconfigured_evidence_snapshot(evaluated_at)
    else:
        evidence_snapshot = load_candidate_evidence_snapshot(
            evidence_directory,
            evaluated_at=evaluated_at,
            max_age_seconds=_CANDIDATE_EVIDENCE_MAX_AGE_SECONDS,
            max_files=_CANDIDATE_EVIDENCE_MAX_FILES,
            max_bytes=_CANDIDATE_EVIDENCE_MAX_BYTES,
        )
    history = (
        list(prior_decisions)
        if prior_decisions is not None
        else fetch_recent_candidate_projection_decisions(connection, limit=64)
    )
    projection = build_candidate_aware_learning_projection(
        source_head=source_head,
        cycles=cycles,
        evidence_snapshot=evidence_snapshot,
        prior_decisions=history,
        policy=runtime_policy,
    )
    persisted = persist_candidate_learning_projection(connection, projection)
    status = persisted.get("status")
    if status not in {"PERSISTED", "DUPLICATE", "SUPPRESSED_UNCHANGED"}:
        raise AlrEventConsumerError("candidate_projection_persistence_status_invalid")
    metric_fields = {
        "artifact_rows_written",
        "provenance_rows_written",
        "payload_bytes_written",
        "source_rows_consumed",
        "training_run_rows_written",
    }
    if any(
        isinstance(persisted.get(field), bool)
        or not isinstance(persisted.get(field), int)
        or persisted[field] < 0
        for field in metric_fields
    ):
        raise AlrEventConsumerError("candidate_projection_write_metrics_invalid")
    if (
        persisted["training_run_rows_written"] != 0
        or persisted.get("model_training_performed") is not False
    ):
        raise AlrEventConsumerError("candidate_projection_training_claim_invalid")

    result = _operational_result(status)
    result["decision_write_attempts"] = 1
    result["decision_writes_suppressed"] = int(
        status == "SUPPRESSED_UNCHANGED"
    )
    result["decision_duplicate_retries"] = int(status == "DUPLICATE")
    result["operational_artifact_rows_written"] = persisted[
        "artifact_rows_written"
    ]
    result["operational_provenance_rows_written"] = persisted[
        "provenance_rows_written"
    ]
    result["operational_run_rows_written"] = 0
    result["operational_feedback_rows_written"] = 0
    result["operational_defer_artifact_rows_written"] = 0
    result["operational_payload_bytes_written"] = persisted[
        "payload_bytes_written"
    ]
    result["operational_source_rows_consumed"] = persisted[
        "source_rows_consumed"
    ]
    return result


def read_local_dsn_file(dsn_path: Path) -> str:
    """Read a private local-PG DSN without falling back to ambient credentials."""
    try:
        raw = read_bounded_regular_file(
            dsn_path,
            max_bytes=16_384,
            require_nonempty=True,
            require_private_mode=True,
        )
        dsn = raw.decode("utf-8").strip()
    except AlrSafeFileError as exc:
        reason = {
            NOT_REGULAR: "dsn_file_not_regular",
            MODE_INVALID: "dsn_file_permissions_invalid",
            SIZE_INVALID: "dsn_file_blank",
            CHANGED: "dsn_file_changed_during_read",
        }.get(exc.code, "dsn_file_unavailable")
        raise AlrEventConsumerError(reason) from exc
    except UnicodeError as exc:
        raise AlrEventConsumerError("dsn_file_unreadable") from exc
    if not dsn:
        raise AlrEventConsumerError("dsn_file_blank")
    _validate_local_dsn(dsn)
    return dsn


def read_candidate_policy_file(policy_path: Path) -> dict[str, Any]:
    """Read an explicit private candidate policy without permissive fallbacks."""
    try:
        raw = read_bounded_regular_file(
            policy_path,
            max_bytes=65_536,
            require_nonempty=True,
            require_private_mode=True,
        ).decode("utf-8")
    except AlrSafeFileError as exc:
        reason = {
            NOT_REGULAR: "candidate_policy_not_regular",
            MODE_INVALID: "candidate_policy_mode_invalid",
            SIZE_INVALID: "candidate_policy_size_invalid",
            CHANGED: "candidate_policy_changed_during_read",
        }.get(exc.code, "candidate_policy_unavailable")
        raise AlrEventConsumerError(reason) from exc
    except UnicodeError as exc:
        raise AlrEventConsumerError("candidate_policy_unavailable") from exc

    def reject_constant(value: str) -> None:
        raise ValueError(f"non_finite:{value}")

    try:
        payload = json.loads(raw, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AlrEventConsumerError("candidate_policy_json_invalid") from exc
    if not isinstance(payload, dict):
        raise AlrEventConsumerError("candidate_policy_json_invalid")
    try:
        return validate_candidate_policy_configuration(payload)
    except CandidatePolicyError as exc:
        raise AlrEventConsumerError("candidate_policy_semantics_invalid") from exc


def wait_for_pg_notifications(
    connection: Any,
    *,
    timeout_seconds: float,
    max_batch: int,
    candidate_board_source: CandidateBoardEventSource | None = None,
) -> list[tuple[str, str]]:
    """先 bounded drain client queue；socket poll 新事件後仍保留超額 remainder。"""
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
        or timeout_seconds > 60
    ):
        raise AlrEventConsumerError("notification_wait_timeout_invalid")
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= 256:
        raise AlrEventConsumerError("notification_batch_limit_invalid")
    if connection.notifies:
        if candidate_board_source is not None:
            board_ready, _, _ = select.select([candidate_board_source], [], [], 0)
            if board_ready:
                candidate_board_source.drain_ready()
    else:
        waitables = [connection]
        if candidate_board_source is not None:
            waitables.append(candidate_board_source)
        ready, _, _ = select.select(waitables, [], [], timeout_seconds)
        if not ready:
            return []
        if candidate_board_source is not None and candidate_board_source in ready:
            candidate_board_source.drain_ready()
        if connection in ready:
            connection.poll()
    notifications = list(connection.notifies[:max_batch])
    del connection.notifies[: len(notifications)]
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
    source_head: str,
    repo_root: Path | None = None,
    candidate_evidence_directory: Path | None = None,
    candidate_policy: Mapping[str, Any] | None = None,
    expected_learning_runtime_digest: str | None = None,
) -> dict[str, int]:
    """LR1 相容性 preflight 後執行 shadow consumer，並持久化真實 lifecycle。

    整倉 HEAD 已降為遙測：docs-only 提交不再停 ingest。只有 capture 面不相容(建置失敗
    等)才 fail-closed 停 capture；training 契約漂移只 quarantine fit(fit_quarantined)。
    """
    compatibility = _preflight_source_compatibility(
        source_head=source_head,
        expected_learning_runtime_digest=expected_learning_runtime_digest,
        repo_root=repo_root,
    )
    fit_quarantined = bool(compatibility["fit_quarantined"])
    dsn = read_local_dsn_file(dsn_path)
    stop_event = threading.Event()
    previous_handlers = _install_shutdown_handlers(stop_event)
    connection: Any | None = None
    db_lock_acquired = False
    session_id: str | None = None
    session_started = False
    try:
        with runtime_file_lock(lock_path):
            board_source_context = (
                open_candidate_board_event_source(candidate_evidence_directory)
                if candidate_evidence_directory is not None
                else nullcontext(None)
            )
            with board_source_context as board_source:
                connection = _connect_listener(dsn)
                db_lock_acquired = acquire_single_instance(connection)
                if not db_lock_acquired:
                    raise AlrEventConsumerError("single_instance_lock_busy")
                session_id = new_session_id()
                start_consumer_session(connection, session_id=session_id)
                session_started = True
                try:
                    result = event_consumer_loop(
                        connection,
                        max_batch=max_batch,
                        should_stop=stop_event.is_set,
                        wait_for_notifications=wait_for_pg_notifications,
                        session_id=session_id,
                        source_head=source_head,
                        candidate_evidence_directory=candidate_evidence_directory,
                        candidate_policy=candidate_policy,
                        candidate_board_source=board_source,
                        fit_quarantined=fit_quarantined,
                    )
                    stop_consumer_session(connection, session_id=session_id)
                    session_started = False
                    return result
                except Exception as exc:
                    connection.rollback()
                    if session_started:
                        try:
                            fail_consumer_session(
                                connection,
                                session_id=session_id,
                                error_code=type(exc).__name__,
                            )
                            session_started = False
                        except Exception:
                            connection.rollback()
                    raise
    finally:
        if connection is not None:
            if db_lock_acquired:
                release_single_instance(connection)
            connection.close()
        _restore_shutdown_handlers(previous_handlers)


def verify_runtime_source_head(
    source_head: str,
    *,
    repo_root: Path | None = None,
) -> str:
    """在任何 DB 讀寫前 fail-closed 比對 pinned head 與 checkout HEAD。"""
    if not isinstance(source_head, str) or not _SOURCE_HEAD_RE.fullmatch(source_head):
        raise AlrEventConsumerError("source_head_required")
    root = repo_root or Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AlrEventConsumerError("source_head_verification_unavailable") from exc
    actual = completed.stdout.strip()
    if completed.returncode != 0 or not _SOURCE_HEAD_RE.fullmatch(actual):
        raise AlrEventConsumerError("source_head_verification_unavailable")
    if actual != source_head:
        raise AlrEventConsumerError("source_head_mismatch")
    return actual


def _telemetry_source_head_match(
    source_head: str | None,
    *,
    repo_root: Path | None = None,
) -> str:
    """LR1 降級：整倉 HEAD 比對只留遙測；mismatch/unavailable 不再停 capture。"""
    if not isinstance(source_head, str) or not _SOURCE_HEAD_RE.fullmatch(source_head):
        return "unpinned"
    try:
        verify_runtime_source_head(source_head, repo_root=repo_root)
    except AlrEventConsumerError as exc:
        return str(exc)
    return "match"


def _preflight_source_compatibility(
    *,
    source_head: str | None,
    expected_learning_runtime_digest: str | None,
    repo_root: Path | None,
) -> dict[str, Any]:
    """LR1 preflight：以 learning_runtime_digest 判定 capture/fit 相容。

    只有 capture 不相容(清單建置失敗等)才 raise 停 ingest；training 契約相對 reviewed
    pin 漂移只把 fit_quarantined 設為 True。整倉 HEAD 僅作為遙測記錄。
    """
    root = repo_root or Path(__file__).resolve().parents[2]
    manifest, build_errors = try_build_learning_runtime_manifest(root)
    compatibility = evaluate_runtime_digest_pin(
        expected_learning_runtime_digest, manifest
    )
    if compatibility["capture_status"] != "COMPATIBLE":
        reasons = compatibility["capture_stop_reasons"] or build_errors or ["unknown"]
        raise AlrEventConsumerError("capture_surface_incompatible:" + ",".join(reasons))
    return {
        "repo_source_head": manifest["repo_source_head"] if manifest else None,
        "learning_runtime_digest": manifest["self_digest"] if manifest else None,
        "expected_learning_runtime_digest": expected_learning_runtime_digest,
        "source_head_match": _telemetry_source_head_match(source_head, repo_root=root),
        "fit_quarantined": compatibility["fit_status"] != "COMPATIBLE",
        "capture_status": compatibility["capture_status"],
        "fit_status": compatibility["fit_status"],
    }


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
    parser.add_argument(
        "--expected-learning-runtime-digest",
        default=os.environ.get("ALR_EXPECTED_LEARNING_RUNTIME_DIGEST"),
    )
    parser.add_argument(
        "--candidate-evidence-dir",
        type=Path,
        default=os.environ.get("ALR_CANDIDATE_EVIDENCE_DIR"),
    )
    parser.add_argument(
        "--candidate-policy-file",
        type=Path,
        default=os.environ.get("ALR_CANDIDATE_POLICY_FILE"),
    )
    arguments = parser.parse_args(argv)
    candidate_policy: Mapping[str, Any] | None = None
    candidate_policy_status: dict[str, Any] = {
        "status": "NOT_CONFIGURED_FAIL_CLOSED",
        "policy_config_hash": None,
        "reason": "candidate_policy_not_configured",
    }
    if arguments.candidate_policy_file is not None:
        try:
            candidate_policy = read_candidate_policy_file(
                arguments.candidate_policy_file
            )
            candidate_policy_status = {
                "status": "READY",
                "policy_config_hash": candidate_policy["policy_config_hash"],
                "reason": None,
            }
        except AlrEventConsumerError as exc:
            # 初次 apply 必須先過外部 provision preflight；運行後 policy 漂移則
            # listener 繼續 ingest，並讓 candidate projection durable 地記 REPAIR_DATA。
            candidate_policy_status = {
                "status": "UNAVAILABLE_FAIL_CLOSED",
                "policy_config_hash": None,
                "reason": str(exc),
            }
    result = run_event_consumer(
        dsn_path=arguments.dsn_file,
        lock_path=arguments.lock_file,
        max_batch=arguments.max_batch,
        source_head=arguments.source_head,
        candidate_evidence_directory=arguments.candidate_evidence_dir,
        candidate_policy=candidate_policy,
        expected_learning_runtime_digest=arguments.expected_learning_runtime_digest,
    )
    print(
        json.dumps(
            {
                "schema_version": "alr_event_consumer_result_v2",
                "result": result,
                "candidate_policy": candidate_policy_status,
                "authority": {
                    "exchange_authority": False,
                    "trading_authority": False,
                    "order_or_probe_authority": False,
                    "decision_lease_authority": False,
                    "cost_gate_authority": False,
                    "proof_authority": False,
                    "serving_authority": False,
                    "promotion_authority": False,
                    "latest_authority": False,
                },
                "authority_counters": dict(_ZERO_AUTHORITY_COUNTERS),
            },
            sort_keys=True,
        )
    )
    return 0


def _process_operational_cycle(
    totals: dict[str, int],
    *,
    connection: Any,
    source_head: str,
    max_batch: int,
    session_id: str,
    candidate_evidence_directory: Path | None = None,
    candidate_policy: Mapping[str, Any] | None = None,
    fit_quarantined: bool = False,
) -> None:
    """Fresh/history drain 後依既有順序執行 bounded research-only 工作。

    LR1：fit_quarantined 時 fence 掉 fit-triggering 的 candidate projection 轉換，
    feedback/proof/retention/health 等非 fit 工作照常。
    """
    _accumulate_feedback(
        totals,
        process_outcome_feedback_backlog(connection, max_batch=max_batch),
    )
    if not fit_quarantined:
        _accumulate_operational(
            totals,
            run_candidate_aware_backlog(
                connection,
                source_head=source_head,
                max_batch=max_batch,
                evidence_directory=candidate_evidence_directory,
                candidate_policy=candidate_policy,
            ),
        )
    _accumulate_candidate_proof_repository(
        totals,
        process_candidate_proof_repository_backlog(
            connection,
            max_batch=max_batch,
        ),
    )
    _accumulate_retention(
        totals,
        process_retention_backlog(connection, max_batch=max_batch),
    )
    _accumulate_health(
        totals,
        process_health_snapshot(
            connection,
            source_head=source_head,
            write_metrics=_build_write_metrics(
                totals,
                session_id=session_id,
            ),
        ),
    )


def _process_candidate_reconciliation(
    totals: dict[str, int],
    *,
    connection: Any,
    source_head: str,
    max_batch: int,
    session_id: str,
    candidate_evidence_directory: Path | None = None,
    candidate_policy: Mapping[str, Any] | None = None,
    fit_quarantined: bool = False,
) -> None:
    """Board wake path: candidate reconciliation plus health, never feedback/retention.

    LR1：fit_quarantined 時 fence 掉 fit-triggering 的 candidate projection，只保留
    proof-repository 唯讀映射與 health 心跳。
    """
    if not fit_quarantined:
        _accumulate_operational(
            totals,
            run_candidate_aware_backlog(
                connection,
                source_head=source_head,
                max_batch=max_batch,
                evidence_directory=candidate_evidence_directory,
                candidate_policy=candidate_policy,
            ),
        )
    _accumulate_candidate_proof_repository(
        totals,
        process_candidate_proof_repository_backlog(
            connection,
            max_batch=max_batch,
        ),
    )
    _accumulate_health(
        totals,
        process_health_snapshot(
            connection,
            source_head=source_head,
            write_metrics=_build_write_metrics(totals, session_id=session_id),
        ),
    )


def _accumulate(totals: dict[str, int], result: Mapping[str, int]) -> None:
    required = {
        "notifications_seen",
        "notifications_received",
        "notifications_consumed",
        "notifications_invalid",
        "rows_seen",
        "persisted",
        "duplicates",
    }
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("backlog_result_invalid")
    totals["drains"] += 1
    for key in required:
        totals[key] += result[key]


def _operational_result(status: str) -> dict[str, int]:
    if status not in {
        "PERSISTED",
        "DUPLICATE",
        "SUPPRESSED_EQUIVALENT_DEFER",
        "DUPLICATE_SUPPRESSION",
        "SUPPRESSED_UNCHANGED",
        "DEFER_EVIDENCE",
        "INSUFFICIENT_SOURCE_CYCLES",
    }:
        raise AlrEventConsumerError("operational_status_invalid")
    return {
        "training_runs": 0,
        "training_duplicates": 0,
        "training_deferred": 1 if status == "DEFER_EVIDENCE" else 0,
        "training_insufficient_source_cycles": 1
        if status == "INSUFFICIENT_SOURCE_CYCLES"
        else 0,
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


def _candidate_evaluation_time(cycles: list[dict[str, Any]]) -> str:
    """Bind each decision clock to the newest immutable source cycle."""
    source_ts = cycles[-1].get("source_ts")
    if isinstance(source_ts, datetime):
        if source_ts.tzinfo is None:
            raise AlrEventConsumerError("candidate_source_time_invalid")
        return source_ts.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    if not isinstance(source_ts, str) or not source_ts.endswith("Z"):
        raise AlrEventConsumerError("candidate_source_time_invalid")
    try:
        parsed = datetime.fromisoformat(source_ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlrEventConsumerError("candidate_source_time_invalid") from exc
    if parsed.tzinfo is None:
        raise AlrEventConsumerError("candidate_source_time_invalid")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unconfigured_evidence_snapshot(evaluated_at: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "schema_version": "alr_candidate_evidence_snapshot_v2",
        "source_status": "EVIDENCE_DIRECTORY_NOT_CONFIGURED",
        "evaluated_at": evaluated_at,
        "candidate_universe_complete": False,
        "candidate_rows": [],
        "selection_allowed": False,
        "latest_alias_used": False,
    }
    encoded = json.dumps(
        snapshot,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    snapshot["snapshot_hash"] = hashlib.sha256(encoded).hexdigest()
    return snapshot


def _accumulate_operational(totals: dict[str, int], result: Mapping[str, int]) -> None:
    required = {
        "training_runs",
        "training_duplicates",
        "training_deferred",
        "training_insufficient_source_cycles",
        "defer_suppressions",
        "suppression_duplicate_retries",
        "decision_write_attempts",
        "decision_writes_suppressed",
        "decision_duplicate_retries",
        "operational_artifact_rows_written",
        "operational_provenance_rows_written",
        "operational_run_rows_written",
        "operational_feedback_rows_written",
        "operational_defer_artifact_rows_written",
        "operational_payload_bytes_written",
        "operational_source_rows_consumed",
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
        "feedback_write_attempts",
        "feedback_duplicate_retries",
        "feedback_artifact_rows_written",
        "feedback_provenance_rows_written",
        "feedback_event_rows_written",
        "feedback_total_rows_written",
        "feedback_payload_bytes_written",
    }
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("feedback_result_invalid")
    for key in required:
        totals[key] = totals.get(key, 0) + result[key]


def _accumulate_candidate_proof_repository(
    totals: dict[str, int],
    result: Mapping[str, int],
) -> None:
    required = {
        "candidate_proof_scans",
        "candidate_proof_projection_rows_read",
        "candidate_proof_source_event_rows_read",
        "candidate_proof_projection_edge_rows_read",
        "candidate_proof_source_event_rows_rechecked",
        "candidate_proof_projection_edge_rows_rechecked",
        "candidate_proof_outcome_bridge_rows_scanned",
        "candidate_proof_outcome_bridge_rows_rechecked",
        "candidate_proof_receipts",
        "candidate_proof_pending",
        "candidate_proof_no_fill",
        "candidate_proof_ready_for_reward_validation",
        "candidate_proof_invalid",
        "candidate_proof_schema_required_overflow",
        "candidate_proof_rows_written",
        "candidate_proof_payload_bytes_written",
    }
    if set(result) != required or any(
        isinstance(result[key], bool)
        or not isinstance(result[key], int)
        or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("candidate_proof_result_invalid")
    if (
        result["candidate_proof_rows_written"] != 0
        or result["candidate_proof_payload_bytes_written"] != 0
    ):
        raise AlrEventConsumerError("candidate_proof_write_claim")
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


def _accumulate_health(totals: dict[str, int], result: Mapping[str, int]) -> None:
    required = {
        "health_attempts",
        "health_snapshots",
        "health_state_delta_writes",
        "health_heartbeat_writes",
        "health_writes_suppressed",
        "health_rows_written",
        "health_payload_bytes_written",
        "health_authority_mismatches",
    }
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("health_result_invalid")
    for key in required:
        totals[key] = totals.get(key, 0) + result[key]


def _build_write_metrics(
    totals: Mapping[str, int],
    *,
    session_id: str,
) -> dict[str, Any]:
    def counter(key: str) -> int:
        value = totals.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AlrEventConsumerError("write_metric_counter_invalid")
        return value

    def ratio(numerator: int, denominator: int) -> float:
        if numerator > denominator:
            raise AlrEventConsumerError("write_metric_ratio_invalid")
        return numerator / denominator if denominator else 0.0

    health_attempts = counter("health_attempts")
    health_emitted = counter("health_snapshots")
    health_suppressed = counter("health_writes_suppressed")
    decision_attempts = counter("decision_write_attempts")
    decision_suppressed = counter("decision_writes_suppressed")
    feedback_attempts = counter("feedback_write_attempts")
    feedback_persisted = counter("feedback_persisted")
    feedback_duplicate_retries = counter("feedback_duplicate_retries")
    feedback_artifact_rows = counter("feedback_artifact_rows_written")
    feedback_provenance_rows = counter(
        "feedback_provenance_rows_written"
    )
    feedback_event_rows = counter("feedback_event_rows_written")
    feedback_total_rows = counter("feedback_total_rows_written")
    feedback_payload_bytes = counter("feedback_payload_bytes_written")
    if feedback_persisted + feedback_duplicate_retries != feedback_attempts:
        raise AlrEventConsumerError("feedback_write_metric_attempt_invalid")
    if feedback_total_rows != (
        feedback_artifact_rows
        + feedback_provenance_rows
        + feedback_event_rows
    ):
        raise AlrEventConsumerError("feedback_write_metric_total_invalid")
    return {
        "schema_version": "alr_write_metrics_v1",
        "scope": {
            "kind": "consumer_session_cumulative",
            "session_id": session_id,
            "through_completed_health_attempt": health_attempts,
        },
        "health": {
            "attempts": health_attempts,
            "emitted": health_emitted,
            "state_delta_writes": counter("health_state_delta_writes"),
            "heartbeat_writes": counter("health_heartbeat_writes"),
            "writes_suppressed": health_suppressed,
            "rows_written": counter("health_rows_written"),
            "payload_bytes_written": counter(
                "health_payload_bytes_written"
            ),
            "suppression_ratio": ratio(
                health_suppressed,
                health_attempts,
            ),
        },
        "decision": {
            "attempts": decision_attempts,
            "writes_suppressed": decision_suppressed,
            "duplicate_retries": counter("decision_duplicate_retries"),
            "artifact_rows_written": counter(
                "operational_artifact_rows_written"
            )
            + feedback_artifact_rows,
            "provenance_rows_written": counter(
                "operational_provenance_rows_written"
            )
            + feedback_provenance_rows,
            "run_rows_written": counter("operational_run_rows_written"),
            "feedback_rows_written": feedback_event_rows
            + counter("operational_feedback_rows_written"),
            "defer_artifact_rows_written": counter(
                "operational_defer_artifact_rows_written"
            ),
            "payload_bytes_written": counter(
                "operational_payload_bytes_written"
            )
            + feedback_payload_bytes,
            "source_rows_consumed": counter(
                "operational_source_rows_consumed"
            ),
            "suppression_ratio": ratio(
                decision_suppressed,
                decision_attempts,
            ),
        },
        "feedback": {
            "attempts": feedback_attempts,
            "persisted": feedback_persisted,
            "duplicate_retries": feedback_duplicate_retries,
            "persisted_ratio": ratio(
                feedback_persisted,
                feedback_attempts,
            ),
            "duplicate_retry_ratio": ratio(
                feedback_duplicate_retries,
                feedback_attempts,
            ),
            "artifact_rows_written": feedback_artifact_rows,
            "provenance_rows_written": feedback_provenance_rows,
            "event_rows_written": feedback_event_rows,
            "total_rows_written": feedback_total_rows,
            "payload_bytes_written": feedback_payload_bytes,
        },
    }


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


if __name__ == "__main__":  # pragma: no cover - exercised by the user unit
    raise SystemExit(main())
