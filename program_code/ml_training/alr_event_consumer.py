"""Event-driven, evidence-only consumer for persisted Rust scanner snapshots."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import select
import shlex
import signal
import subprocess
import threading
import time
from contextlib import contextmanager, nullcontext
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# S2.4 §2.1 W2a 拆分:inotify board-watch 面(含共用 AlrEventConsumerError)搬入
# alr_candidate_board_events;此處 re-export 保持公開匯入面/monkeypatch 縫不變。
# retention apply 面已「整段」移出本進程(見 alr_retention_runner)——本模組對
# alr_retention_repository 零匯入路徑(無 lazy/條件;由 privilege-split 靜態執法)。
from ml_training.alr_candidate_board_events import (  # noqa: F401 — re-export
    AlrEventConsumerError,
    CandidateBoardEventSource,
    _IN_ACCESS_EVENT,
    _IN_CLOSE_WRITE,
    _IN_CREATE,
    _IN_DELETE,
    _IN_DONT_FOLLOW,
    _IN_IGNORED,
    _IN_MOVED_TO,
    _IN_ONLYDIR,
    _IN_Q_OVERFLOW,
    _add_linux_candidate_board_watch,
    open_candidate_board_event_source,
)
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
    evaluate_compatibility,
    try_build_learning_runtime_manifest,
    try_build_learning_runtime_manifest_v2,
)
from ml_training.aiml_gate_receipt_validator import validate_aiml_artifact
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
# S2.4 §8.3(W2 P1-A):常駐重連韌性 + 在帶叢集身分閘下沉至 governed 葉;
# write-metrics 純投影面同樣下沉(2000 行治理拆分),此處逐名 re-export 保持既有
# 匯入面/monkeypatch 縫不變(``consumer._build_write_metrics`` 等仍可用)。
from ml_training.alr_consumer_resilience import (
    AlrRuntimeIdentityError,  # noqa: F401 — re-export
    ResidentConsumerState,  # noqa: F401 — re-export
    default_jitter,
    run_resident_db_sessions,
    verify_connected_cluster_identity,
)
from ml_training.alr_consumer_write_metrics import (
    build_write_metrics as _build_write_metrics,
    row_value as _row_value,
)
from ml_training.alr_safe_file import (
    AlrSafeFileError,
    CHANGED,
    MODE_INVALID,
    NOT_REGULAR,
    SIZE_INVALID,
    read_bounded_regular_file,
)
# S2.4 §8.1/§8.3(W2b):production 身分前置(application-root 整樹重算 + v2 receipt +
# launch/topology 期望硬比對)下沉至 governed 葉模組;consumer 只消費 typed 結果。
from ml_training.alr_application_identity import (
    AlrApplicationIdentityError,
    EX_CONFIG_EXIT_CODE,
    is_permanent_pre_db_error,
    production_failure_summary,
    run_production_preflight_from_args,
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
# LR1(S2.2A):in-repo pinned source_compatibility receipt(reviewed 期望清單來源)。
_DEFAULT_COMPATIBILITY_RECEIPT_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/"
    "S2.2A-source-compatibility-receipt-v1.json"
)
# S2-WP1(spawn value-guard):in-repo pinned v2 source_compatibility receipt(更強身分——
# 綁 spec+sealed lock 雙檔 + parquet_etl COMPUTE)。production spawn 端據此把 pinned v2
# learning_runtime_digest 帶成 non-None value-guard(env 契約見 main / S2.4 unit)。
_DEFAULT_COMPATIBILITY_RECEIPT_V2_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/"
    "S2.2A-source-compatibility-receipt-v2.json"
)
_CANDIDATE_EVIDENCE_MAX_AGE_SECONDS = 172_800
_CANDIDATE_EVIDENCE_MAX_FILES = 128
_CANDIDATE_EVIDENCE_MAX_BYTES = 64 * 1024 * 1024
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
# 九項 authority 恆為 false 的常量向量(main 成功/value-guard fail-closed 兩路共用,避免漂移)。
_ZERO_AUTHORITY = {
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


# F5:``os.open`` / ``mkdir`` 的失敗只有 ``BlockingIOError`` 被轉成 typed code,其餘
# ``OSError`` 裸奔出 main 的 ``except AlrEventConsumerError`` → exit 1 + 原始 traceback。
# 下列 errno 是永不自癒的部署/組態錯(RuntimeDirectory 權限、路徑被檔案佔住、只讀掛載、
# symlink 攻擊被 O_NOFOLLOW 擋下),必須一次 78 停下等 operator,而不是 300 秒燒三次
# start limit 把單元變成永久 failed。
_RUNTIME_LOCK_PERMANENT_ERRNOS = frozenset({
    errno.EACCES,
    errno.EPERM,
    errno.EROFS,
    errno.ENOTDIR,
    errno.EISDIR,
    errno.ELOOP,
    errno.ENAMETOOLONG,
})


def _runtime_file_lock_open_code(error: OSError) -> str:
    """把 lock 開檔失敗轉成 typed code;permanent 類走 ``_denied_``(→ exit 78)。

    ENOSPC / EMFILE / ENFILE 等資源耗盡刻意**不**列為 permanent(operator 清空間即自癒),
    只做 typed 化,讓失敗以結構化 code 而非裸 traceback 收場。
    """
    name = errno.errorcode.get(error.errno, str(error.errno))
    prefix = (
        "runtime_file_lock_denied_"
        if error.errno in _RUNTIME_LOCK_PERMANENT_ERRNOS
        else "runtime_file_lock_unavailable_"
    )
    return f"{prefix}{name}"


@contextmanager
def runtime_file_lock(lock_path: Path) -> Iterator[None]:
    """Hold a nonblocking local process lock for the consumer lifetime."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - P2 target is Linux only
        raise AlrEventConsumerError("runtime_file_lock_unsupported") from exc

    try:
        lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:  # F5:ENOSPC/EACCES/EPERM/… 不再以 exit 1 裸奔
        raise AlrEventConsumerError(_runtime_file_lock_open_code(exc)) from exc
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


def read_local_dsn_file(
    dsn_path: Path, *, required_identity: Mapping[str, str] | None = None
) -> str:
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
    _validate_local_dsn(dsn, required_identity)
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
    expected_compatibility_receipt: Path | None = None,
    pinned_repo_source_head: str | None = None,
    dsn_required_identity: Mapping[str, str] | None = None,
    topology_guard_file: Path | None = None,
    reconnect_sleep: Callable[[float], Any] | None = None,
    reconnect_jitter: Callable[[], float] | None = None,
    reconnect_state: Any | None = None,
) -> dict[str, int]:
    """LR1 相容性 preflight 後執行常駐 consumer，並持久化真實 lifecycle。

    整倉 HEAD 已降為遙測：docs-only 提交不再停 ingest。只有 capture 面不相容(建置失敗
    等)才 fail-closed 停 capture；training 契約漂移只 quarantine fit(fit_quarantined)。

    W2b(§8.3 production):``pinned_repo_source_head`` 非 None 時,相容性重算以該 pinned
    head 建置(零 Git 呼叫——application root 無 checkout);``dsn_required_identity``
    非 None 時 DSN 綁 production 身分表(aiml_engine_scanner)。兩者皆 None = 舊行為。

    W2 P1-A(§8.3 resident 語義):DB 可用性 transient 失敗**不退出**——關閉失敗連線後,
    以有界指數退避 + jitter(5s..300s)無限重連;host 面資源(檔案鎖、candidate board
    watch)跨重連持有,進度 cursor 全在 DB 側,故不累積 task/row/記憶體。重連時
    ``topology_guard_file`` 非 None 即先載入並自我 digest guard、比對連上的
    user/database/endpoint 與叢集身分列,不符即 permanent typed 失敗(production → 78)。
    """
    compatibility = _preflight_source_compatibility(
        source_head=source_head,
        expected_learning_runtime_digest=expected_learning_runtime_digest,
        repo_root=repo_root,
        expected_compatibility_receipt=expected_compatibility_receipt,
        pinned_repo_source_head=pinned_repo_source_head,
    )
    fit_quarantined = bool(compatibility["fit_quarantined"])
    dsn = (
        read_local_dsn_file(dsn_path)
        if dsn_required_identity is None
        else read_local_dsn_file(dsn_path, required_identity=dsn_required_identity)
    )
    stop_event = threading.Event()
    previous_handlers = _install_shutdown_handlers(stop_event)
    try:
        with runtime_file_lock(lock_path):
            board_source_context = (
                open_candidate_board_event_source(candidate_evidence_directory)
                if candidate_evidence_directory is not None
                else nullcontext(None)
            )
            with board_source_context as board_source:
                outcome = run_resident_db_sessions(
                    open_connection=lambda: _connect_listener(dsn),
                    run_session=lambda connection: _run_single_db_session(
                        connection,
                        max_batch=max_batch,
                        source_head=source_head,
                        stop_event=stop_event,
                        board_source=board_source,
                        candidate_evidence_directory=candidate_evidence_directory,
                        candidate_policy=candidate_policy,
                        fit_quarantined=fit_quarantined,
                        topology_guard_file=topology_guard_file,
                        dsn_required_identity=dsn_required_identity,
                    ),
                    close_connection=_close_db_session,
                    should_stop=stop_event.is_set,
                    # 可中斷等待:退避期間收到 SIGTERM 立即醒來(不拖到 TimeoutStopSec)。
                    sleep=reconnect_sleep or stop_event.wait,
                    jitter=reconnect_jitter or default_jitter,
                    state=reconnect_state,
                )
                # result 為 None = 停機訊號在 DB 中斷期間到達(零 session 完成、非失敗)。
                return outcome["result"] if outcome["result"] is not None else {}
    finally:
        _restore_shutdown_handlers(previous_handlers)


def _run_single_db_session(
    connection: Any,
    *,
    max_batch: int,
    source_head: str,
    stop_event: threading.Event,
    board_source: Any,
    candidate_evidence_directory: Path | None,
    candidate_policy: Mapping[str, Any] | None,
    fit_quarantined: bool,
    topology_guard_file: Path | None = None,
    dsn_required_identity: Mapping[str, str] | None = None,
) -> dict[str, int]:
    """一次 DB session 的完整生命週期(身分閘 → 單例 → session → 事件迴圈)。"""
    if topology_guard_file is not None:
        verify_connected_cluster_identity(
            connection,
            topology_guard_file=topology_guard_file,
            dsn_identity=dsn_required_identity,
        )
    if not acquire_single_instance(connection):
        raise AlrEventConsumerError("single_instance_lock_busy")
    session_id = new_session_id()
    start_consumer_session(connection, session_id=session_id)
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
    except Exception as exc:
        _fail_session_best_effort(
            connection, session_id=session_id, error_code=type(exc).__name__
        )
        raise
    stop_consumer_session(connection, session_id=session_id)
    return result


def _fail_session_best_effort(
    connection: Any, *, session_id: str, error_code: str
) -> None:
    """失敗路徑的 durable 記帳:盡力 rollback + fail_consumer_session。

    連線已死(DB 停機)時記帳必然失敗——此處一律吞掉次生例外,讓**原始**失敗原因
    上拋,否則 transient 分類會被 rollback 的 InterfaceError 掩蓋成永久崩潰。
    """
    try:
        connection.rollback()
        fail_consumer_session(
            connection, session_id=session_id, error_code=error_code
        )
    except Exception:  # noqa: BLE001 — 見 docstring:絕不掩蓋原始失敗
        try:
            connection.rollback()
        except Exception:  # noqa: BLE001
            pass


def _close_db_session(connection: Any) -> None:
    """關閉一次 session 的連線;先盡力釋放 advisory 單例(死連線不得阻斷重連)。"""
    try:
        release_single_instance(connection)
    except Exception:  # noqa: BLE001
        pass
    try:
        connection.close()
    except Exception:  # noqa: BLE001
        pass


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


def _load_expected_compatibility_manifest(
    repo_root: Path,
    receipt_path: Path | None,
    expected_learning_runtime_digest: str | None,
) -> dict[str, Any] | None:
    """讀取 in-repo pinned source_compatibility receipt,取其 reviewed 期望清單。

    fail-closed:receipt 缺失/不可解析/schema 驗證失敗/(若提供 operator pin 而)
    learning_runtime_digest 不符,一律回 None → 由 evaluate_compatibility 判為
    INDETERMINATE(停 capture)。
    """
    path = receipt_path or (repo_root / _DEFAULT_COMPATIBILITY_RECEIPT_REL)
    try:
        receipt = json.loads(Path(path).read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(receipt, dict):
        return None
    if receipt.get("schema_version") != "source_compatibility_receipt_v1":
        return None
    # 中央驗證器已對 receipt 做內層反偽造重算;驗證失敗一律 fail-closed。
    if validate_aiml_artifact(receipt):
        return None
    if expected_learning_runtime_digest is not None and (
        receipt.get("learning_runtime_digest") != expected_learning_runtime_digest
    ):
        return None
    manifest = receipt.get("learning_runtime_manifest")
    return manifest if isinstance(manifest, dict) else None


def resolve_pinned_learning_runtime_digest(
    repo_root: Path | None = None,
    *,
    receipt_path: Path | None = None,
) -> str | None:
    """S2-WP1 spawn value-guard:讀取 committed v2 source_compatibility receipt 的 pinned
    ``learning_runtime_digest``,並以當前 checkout 重算 v2 manifest 證明可重現(HEAD-independent)。

    fail-closed:receipt 缺失/非 v2/中央驗證失敗/v2 重算失敗或不符 → 一律回 None,由 spawn
    端(main)據此拒啟(不進 run_event_consumer)。此為「production spawn 把 pinned v2 digest
    帶成 non-None value-guard」的來源函數;systemd unit(S2.4 安裝)以 env 供 operator pin。

    SOURCE-TRUTH 註記:此處呼叫的 ``validate_aiml_artifact(receipt)`` 只證 receipt 內部自洽 +
    結構(offline-structure),「不」證 receipt 與真 repo 相符。真正把 pinned 身分綁到「當前
    checkout 真檔」的,是本函數的 ``try_build_learning_runtime_manifest_v2`` recompute 步驟
    (逐檔重算 learning-code/lock/feature 後與 pin 比對);它與 sealed-build CI job 的
    ``verify_lock_closure(lock_path=)`` 共同構成 build-identity receipt 的 source-truth 綁定。
    """
    root = repo_root or Path(__file__).resolve().parents[2]
    path = receipt_path or (root / _DEFAULT_COMPATIBILITY_RECEIPT_V2_REL)
    try:
        receipt = json.loads(Path(path).read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(receipt, dict):
        return None
    if receipt.get("schema_version") != "source_compatibility_receipt_v2":
        return None
    # 中央驗證器對 v2 receipt 做內層反偽造重算 + dependency_lock 形狀驗;失敗一律 fail-closed。
    if validate_aiml_artifact(receipt):
        return None
    pinned = receipt.get("learning_runtime_digest")
    # 以當前 checkout 重算 v2 身分(HEAD-independent,注入 dummy head 免 git 依賴)並比對 pin。
    manifest, _errors = try_build_learning_runtime_manifest_v2(root, repo_source_head="0" * 40)
    if manifest is None or manifest.get("self_digest") != pinned:
        return None
    return pinned


def _preflight_source_compatibility(
    *,
    source_head: str | None,
    expected_learning_runtime_digest: str | None,
    repo_root: Path | None,
    expected_compatibility_receipt: Path | None = None,
    pinned_repo_source_head: str | None = None,
) -> dict[str, Any]:
    """LR1 preflight：唯一權威判定器 evaluate_compatibility(expected, actual)。

    expected 清單取自 in-repo pinned source_compatibility receipt;actual 由當前 checkout
    建置。capture 面不相容/不可判定 → fail-closed 停 ingest;training 面漂移 → 只
    quarantine fit 而 capture 續跑。整倉 HEAD 僅作遙測。

    W2b(§8.3):pinned_repo_source_head 非 None(production)時,建置注入 pinned head、
    HEAD 遙測不呼叫 Git(application root 是不可變 bundle,非 checkout)。
    """
    root = repo_root or Path(__file__).resolve().parents[2]
    actual, build_errors = try_build_learning_runtime_manifest(
        root, repo_source_head=pinned_repo_source_head
    )
    expected = _load_expected_compatibility_manifest(
        root, expected_compatibility_receipt, expected_learning_runtime_digest
    )
    compatibility = evaluate_compatibility(expected, actual)
    if compatibility["capture_status"] != "COMPATIBLE":
        reasons = (
            compatibility["capture_stop_reasons"]
            or build_errors
            or (["expected_compatibility_manifest_unavailable"] if expected is None else [])
            or ["unknown"]
        )
        raise AlrEventConsumerError("capture_surface_incompatible:" + ",".join(reasons))
    return {
        "repo_source_head": actual["repo_source_head"] if actual else None,
        "learning_runtime_digest": actual["self_digest"] if actual else None,
        "expected_learning_runtime_digest": expected_learning_runtime_digest,
        "source_head_match": (
            "pinned_application_root"
            if pinned_repo_source_head is not None
            else _telemetry_source_head_match(source_head, repo_root=root)
        ),
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


def _validate_local_dsn(
    dsn: str, required: Mapping[str, str] | None = None
) -> None:
    # W2b(§8.3):production 模式以 aiml_engine_scanner 身分表覆蓋;預設維持 legacy
    # user-level shadow lane 的 alr_shadow(dev/test 路徑不變)。
    required = _LOCAL_DSN_REQUIRED if required is None else required
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
    if any(parsed.get(key) != value for key, value in required.items()):
        raise AlrEventConsumerError("dsn_not_local_trading_ai")


def _emit_result(
    result: dict[str, int] | None,
    *,
    candidate_policy_status: dict[str, Any],
    source_value_guard: dict[str, Any] | None,
    production_identity: dict[str, Any] | None,
) -> None:
    """v2 結果 JSON 的唯一出口(main 全部出口共用;九 authority 恆 false)。"""
    print(
        json.dumps(
            {
                "schema_version": "alr_event_consumer_result_v2",
                "result": result,
                "candidate_policy": candidate_policy_status,
                "source_value_guard": source_value_guard,
                "production_identity": production_identity,
                "authority": dict(_ZERO_AUTHORITY),
                "authority_counters": dict(_ZERO_AUTHORITY_COUNTERS),
            },
            sort_keys=True,
        )
    )


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
        "--expected-compatibility-receipt",
        type=Path,
        default=os.environ.get("ALR_EXPECTED_COMPATIBILITY_RECEIPT"),
    )
    # S2-WP1 spawn value-guard(選用;S2.4 systemd unit 設此 env 啟用):operator pin 的 v2
    # learning_runtime_digest。非 None 即啟用 value-guard——在任何 DB 前證 committed v2 身分
    # 完整、可由當前 checkout 重算、且與此 pin 相符,任一不符即 fail-closed 拒啟。
    parser.add_argument(
        "--expected-learning-runtime-digest-v2",
        default=os.environ.get("ALR_EXPECTED_LEARNING_RUNTIME_DIGEST_V2"),
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
    # S2.4 §8.3(W2b)production ABI:--application-root 出現即進 production 模式(唯一根;
    # 期望缺失/不符絕不回退,permanent 失敗 exit 78——語義詳 alr_application_identity)。
    parser.add_argument("--application-root", type=Path, default=None)
    parser.add_argument(
        "--expected-compatibility-receipt-v2",
        type=Path,
        default=os.environ.get("ALR_EXPECTED_COMPATIBILITY_RECEIPT_V2"),
    )
    parser.add_argument(
        "--expected-application-bundle-digest",
        default=os.environ.get("ALR_APPLICATION_BUNDLE_DIGEST"),
    )
    parser.add_argument(
        "--expected-launch-bundle-digest",
        default=os.environ.get("ALR_LAUNCH_BUNDLE_DIGEST"),
    )
    parser.add_argument(
        "--topology-guard-file",
        type=Path,
        default=os.environ.get("ALR_TOPOLOGY_GUARD_FILE"),
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
    # S2.4 §8.3(W2b)production 前置:--application-root 出現即整樹重算 application bundle
    # digest 並硬比對全部期望;任何 permanent 身分/組態失敗輸出結構化 JSON 後 exit 78,
    # 「絕不」回退 ambient/Git/module-relative 來源。preflight 通過後,v2 value-guard 由
    # preflight 的 root-scoped 驗證承接(legacy resolver 走 module-relative 根,production 禁用)。
    production_identity: dict[str, Any] | None = None
    if arguments.application_root is not None:
        try:
            production_identity = run_production_preflight_from_args(arguments)
        except AlrApplicationIdentityError as exc:
            _emit_result(
                None,
                candidate_policy_status=candidate_policy_status,
                source_value_guard=None,
                production_identity=production_failure_summary(exc.code),
            )
            return EX_CONFIG_EXIT_CODE
    # S2-WP1 spawn value-guard:若 operator 供了 v2 pin,先在任何 DB 前 fail-closed 核驗
    # committed v2 身分(完整 + 可由 checkout 重算 + 與 pin 相符);任一不符即拒啟,不進 consumer。
    # resolve_pinned_learning_runtime_digest 的 recompute-from-checkout 是此 guard 的 source-truth
    # 依據(其內部 validate_aiml_artifact 只證結構自洽,非真檔相符——見該函數 docstring)。任何非
    # 預期例外一律轉為 FAIL_CLOSED_ERROR:仍 fail-closed,但輸出結構化 JSON、不外洩 raw traceback。
    v2_pin = arguments.expected_learning_runtime_digest_v2
    source_value_guard: dict[str, Any] = {
        "schema_version": "source_value_guard_v1",
        "status": "DISABLED",
        "learning_runtime_digest_v2": None,
    }
    if production_identity is not None:
        source_value_guard = production_identity["source_value_guard"]
    elif v2_pin is not None:
        try:
            resolved = resolve_pinned_learning_runtime_digest()
        except Exception:  # noqa: BLE001 — 拒啟優先於任何錯誤外洩(fail-closed)
            source_value_guard = {
                "schema_version": "source_value_guard_v1",
                "status": "FAIL_CLOSED_ERROR",
                "learning_runtime_digest_v2": None,
            }
        else:
            if resolved is None:
                source_value_guard = {
                    "schema_version": "source_value_guard_v1",
                    "status": "FAIL_CLOSED_UNRESOLVED",
                    "learning_runtime_digest_v2": None,
                }
            elif resolved != v2_pin:
                source_value_guard = {
                    "schema_version": "source_value_guard_v1",
                    "status": "FAIL_CLOSED_PIN_MISMATCH",
                    "learning_runtime_digest_v2": resolved,
                }
            else:
                source_value_guard = {
                    "schema_version": "source_value_guard_v1",
                    "status": "PASS",
                    "learning_runtime_digest_v2": resolved,
                }
        if source_value_guard["status"] != "PASS":
            _emit_result(
                None,
                candidate_policy_status=candidate_policy_status,
                source_value_guard=source_value_guard,
                production_identity=None,
            )
            return 1
    run_kwargs: dict[str, Any] = {
        "dsn_path": arguments.dsn_file,
        "lock_path": arguments.lock_file,
        "max_batch": arguments.max_batch,
        "source_head": arguments.source_head,
        "candidate_evidence_directory": arguments.candidate_evidence_dir,
        "candidate_policy": candidate_policy,
        "expected_learning_runtime_digest": arguments.expected_learning_runtime_digest,
        "expected_compatibility_receipt": arguments.expected_compatibility_receipt,
    }
    production_summary: dict[str, Any] | None = None
    if production_identity is not None:
        # production:唯一根 = application root;pinned head 重算(零 Git);DSN 綁
        # aiml_engine_scanner;v1 receipt 為 root-scoped 路徑(preflight 已驗 containment)。
        run_kwargs.update(production_identity["run_kwargs"])
        production_summary = production_identity["summary"]
    try:
        result = run_event_consumer(**run_kwargs)
    except AlrEventConsumerError as exc:
        # §8.3:production 的 permanent pre-DB config/identity 失敗 → exit 78
        # (unit RestartPreventExitStatus=78);其餘與 dev/test 路徑一致向上拋。
        if production_identity is not None and is_permanent_pre_db_error(exc):
            _emit_result(
                None,
                candidate_policy_status=candidate_policy_status,
                source_value_guard=source_value_guard,
                production_identity=production_failure_summary(str(exc)),
            )
            return EX_CONFIG_EXIT_CODE
        raise
    _emit_result(
        result,
        candidate_policy_status=candidate_policy_status,
        source_value_guard=source_value_guard,
        production_identity=production_summary,
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
    feedback/proof/health 等非 fit 工作照常。

    S2.4 §2.1(W2a):retention pass 已「整段」移出 engine-scanner 進程(獨立入口
    ``alr_retention_runner``);本 orchestration 不再含任何 retention 步驟。
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
    """Board wake path: candidate reconciliation plus health, never feedback.

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


if __name__ == "__main__":  # pragma: no cover - exercised by the user unit
    raise SystemExit(main())
