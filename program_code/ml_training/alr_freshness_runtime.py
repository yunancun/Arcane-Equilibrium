"""
MODULE_NOTE
模塊用途：執行 exact notification、contiguous fresh catch-up 與低優先 history lane。
主要函數：drain_notified_identities、drain_fresh_lane、drain_historical_lane。
硬邊界：notification 只提供 identity；fresh cursor 只能逐 raw row 前進。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from ml_training.alr_consumer_repository import (
    FRESH_LANE,
    HISTORICAL_LANE,
    fetch_fresh_lane_rows,
    fetch_fresh_raw_only_holes,
    fetch_historical_lane_rows,
    fetch_latest_alr_watermark,
    fetch_latest_scanner_snapshot,
    load_consumer_state,
    record_consumer_event,
)
from ml_training.alr_persistence_repository import (
    AlrPersistenceConflict,
    fetch_persisted_scanner_identity,
    fetch_scanner_snapshot_by_identity,
    load_restart_state,
    persist_scanner_cycle,
)
from ml_training.alr_scanner_snapshot_adapter import adapt_scanner_snapshot


_EMPTY_RESULT = {
    "notifications_seen": 0,
    "notifications_received": 0,
    "notifications_consumed": 0,
    "notifications_invalid": 0,
    "rows_seen": 0,
    "persisted": 0,
    "duplicates": 0,
}


class AlrFreshnessRuntimeError(ValueError):
    """Fresh/history lane 無法在 append-only 邊界內安全推進。"""


def drain_notified_identities(
    connection: Any,
    notifications: Iterable[tuple[str, str]],
    *,
    max_batch: int,
    session_id: str,
    parse_notification: Callable[[str, str], Mapping[str, Any]],
    notification_error_type: type[Exception],
) -> dict[str, int]:
    """先攝取每個 valid notification 的 exact raw identity，不觸碰 fresh cursor。"""
    _validate_batch(max_batch, maximum=256)
    result = dict(_EMPTY_RESULT)
    identities: dict[tuple[str, int], int] = {}
    for notification in notifications:
        result["notifications_seen"] += 1
        result["notifications_received"] += 1
        if not isinstance(notification, tuple) or len(notification) != 2:
            result["notifications_invalid"] += 1
            _record_notification_event(
                connection,
                session_id=session_id,
                event_kind="NOTIFICATION_RECEIVED",
            )
            _record_notification_event(
                connection,
                session_id=session_id,
                event_kind="NOTIFICATION_INVALID",
                error_code="notification_tuple_invalid",
            )
            continue
        channel, payload = notification
        try:
            event = parse_notification(channel, payload)
        except notification_error_type as exc:
            result["notifications_invalid"] += 1
            _record_notification_event(
                connection,
                session_id=session_id,
                event_kind="NOTIFICATION_RECEIVED",
            )
            _record_notification_event(
                connection,
                session_id=session_id,
                event_kind="NOTIFICATION_INVALID",
                error_code=str(exc),
            )
            continue
        scan_id = str(event["scan_id"])
        ts_ms = int(event["ts_ms"])
        _record_notification_event(
            connection,
            session_id=session_id,
            event_kind="NOTIFICATION_RECEIVED",
            source_scan_id=scan_id,
            notification_ts_ms=ts_ms,
        )
        identity = (scan_id, ts_ms)
        identities[identity] = identities.get(identity, 0) + 1

    rows: list[Mapping[str, Any]] = []
    matched_counts: dict[tuple[str, int], int] = {}
    for scan_id, ts_ms in identities:
        row = fetch_scanner_snapshot_by_identity(
            connection,
            scan_id=scan_id,
            ts_ms=ts_ms,
        )
        if row is not None:
            rows.append(row)
            matched_counts[(scan_id, ts_ms)] = identities[(scan_id, ts_ms)]

    def consumed(row: Mapping[str, Any], cycle: Mapping[str, Any], status: str) -> None:
        source = cycle["source"]
        row_identity = (str(source["scan_id"]), _row_ts_ms(row, source))
        occurrence_count = matched_counts.get(row_identity, 0)
        duplicate_count = (
            occurrence_count
            if status == "ALREADY_PERSISTED"
            else max(occurrence_count - 1, 0)
        )
        for _ in range(duplicate_count):
            _record_notification_event(
                connection,
                session_id=session_id,
                event_kind="NOTIFICATION_DUPLICATE",
                source_scan_id=row_identity[0],
                source_ts=source["ts"],
                source_hash=str(cycle["source_hash"]),
                notification_ts_ms=row_identity[1],
                details={"source_state": status},
            )
        for _ in range(occurrence_count):
            _record_notification_event(
                connection,
                session_id=session_id,
                event_kind="NOTIFICATION_CONSUMED",
                source_scan_id=row_identity[0],
                source_ts=source["ts"],
                source_hash=str(cycle["source_hash"]),
                notification_ts_ms=row_identity[1],
                details={"source_state": status},
            )
            result["notifications_consumed"] += 1

    persisted = _persist_rows(connection, rows=rows, on_row=consumed)
    for key in ("rows_seen", "persisted", "duplicates"):
        result[key] = persisted[key]
    return result


def ensure_fresh_lane_bootstrap(
    connection: Any,
    *,
    session_id: str,
) -> dict[str, Any]:
    """優先沿用 durable cursor；無 ALR source 時只攝取最新 raw anchor。"""
    state = load_consumer_state(connection)
    if state["fresh_cursor"] is not None:
        return state
    cursor = fetch_latest_alr_watermark(connection)
    if cursor is None:
        latest_raw = fetch_latest_scanner_snapshot(connection)
        if latest_raw is None:
            return state
        captured: list[Mapping[str, Any]] = []
        bootstrap_result = _persist_rows(
            connection,
            rows=[latest_raw],
            on_row=lambda row, cycle, status: captured.append(cycle),
        )
        cycle = captured[0]
        cursor = _cycle_cursor(cycle)
        origin = "LATEST_RAW"
    else:
        origin = "LATEST_ALR_WATERMARK"
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="LANE_BOOTSTRAPPED",
        lane=FRESH_LANE,
        source_ts=cursor["source_ts"],
        source_scan_id=cursor["source_scan_id"],
        source_hash=cursor.get("source_hash"),
        details={"origin": origin},
    )
    if origin == "LATEST_RAW":
        _record_lane_success(
            connection,
            session_id=session_id,
            lane=FRESH_LANE,
            cursor=cursor,
            result=bootstrap_result,
        )
    return load_consumer_state(connection)


def drain_fresh_lane(
    connection: Any,
    *,
    session_id: str,
    max_batch: int,
) -> dict[str, int]:
    """從 durable composite frontier 連續 catch up；已攝取 exact row 仍必被走過。"""
    _validate_batch(max_batch, maximum=256)
    state = ensure_fresh_lane_bootstrap(connection, session_id=session_id)
    cursor = state["fresh_cursor"]
    if cursor is None:
        return dict(_EMPTY_RESULT)
    anchor = state["fresh_anchor"]
    if anchor is None:
        raise AlrFreshnessRuntimeError("fresh_anchor_missing")
    repair_rows = fetch_fresh_raw_only_holes(
        connection,
        anchor_cursor=anchor,
        limit=max_batch,
    )
    repair_result = _persist_rows(
        connection,
        rows=repair_rows,
        on_row=lambda row, cycle, status: None,
    )
    rows = fetch_fresh_lane_rows(connection, cursor_state=cursor, limit=max_batch)

    def advance(row: Mapping[str, Any], cycle: Mapping[str, Any], status: str) -> None:
        del row
        source = cycle["source"]
        record_consumer_event(
            connection,
            session_id=session_id,
            event_kind="LANE_CURSOR_ADVANCED",
            lane=FRESH_LANE,
            source_ts=source["ts"],
            source_scan_id=source["scan_id"],
            source_hash=str(cycle["source_hash"]),
            details={
                "persistence_status": (
                    "TRAVERSED" if status == "ALREADY_PERSISTED" else status
                ),
                "source_state": status,
            },
        )

    forward_result = _persist_rows(connection, rows=rows, on_row=advance)
    result = {
        key: repair_result[key] + forward_result[key]
        for key in ("rows_seen", "persisted", "duplicates")
    }
    final_state = load_consumer_state(connection)["fresh_cursor"] or cursor
    if result["rows_seen"] > 0:
        _record_lane_success(
            connection,
            session_id=session_id,
            lane=FRESH_LANE,
            cursor=final_state,
            result=result,
        )
    return {**_EMPTY_RESULT, **result}


def drain_historical_lane(
    connection: Any,
    *,
    session_id: str,
    max_batch: int,
) -> dict[str, int]:
    """只在 fresh idle 後，於固定 bootstrap boundary 前低額回填。"""
    _validate_batch(max_batch, maximum=8)
    state = load_consumer_state(connection)
    boundary = state["fresh_anchor"]
    if boundary is None:
        return dict(_EMPTY_RESULT)
    rows = fetch_historical_lane_rows(
        connection,
        after_cursor=state["historical_cursor"],
        before_cursor=boundary,
        limit=max_batch,
    )

    def advance(row: Mapping[str, Any], cycle: Mapping[str, Any], status: str) -> None:
        del row
        source = cycle["source"]
        event_kind = (
            "LANE_BOOTSTRAPPED"
            if state["historical_cursor"] is None
            and not _historical_cursor_created(connection)
            else "LANE_CURSOR_ADVANCED"
        )
        record_consumer_event(
            connection,
            session_id=session_id,
            event_kind=event_kind,
            lane=HISTORICAL_LANE,
            source_ts=source["ts"],
            source_scan_id=source["scan_id"],
            source_hash=str(cycle["source_hash"]),
            details={
                "persistence_status": (
                    "TRAVERSED" if status == "ALREADY_PERSISTED" else status
                ),
                "source_state": status,
            },
        )

    result = _persist_rows(connection, rows=rows, on_row=advance)
    final_state = load_consumer_state(connection)["historical_cursor"]
    if result["rows_seen"] > 0:
        _record_lane_success(
            connection,
            session_id=session_id,
            lane=HISTORICAL_LANE,
            cursor=final_state,
            result=result,
        )
    return {**_EMPTY_RESULT, **result}


def _persist_rows(
    connection: Any,
    *,
    rows: list[Mapping[str, Any]],
    on_row: Callable[[Mapping[str, Any], Mapping[str, Any], str], None],
) -> dict[str, int]:
    try:
        restart_state = load_restart_state(connection)
        processed_source_keys = set(restart_state["processed_source_keys"])
        watermark = restart_state["watermark"]
        persisted = 0
        duplicates = 0
        for row in rows:
            cycle = adapt_scanner_snapshot(
                row,
                processed_source_keys=processed_source_keys,
                watermark=watermark,
            )
            source = cycle["source"]
            existing = fetch_persisted_scanner_identity(
                connection,
                scan_id=source["scan_id"],
                source_ts=source["ts"],
            )
            if existing is not None:
                if existing["source_hash"] != cycle["source_hash"]:
                    raise AlrPersistenceConflict("source_hash_conflict")
                status = "ALREADY_PERSISTED"
                processed_source_keys.add(cycle["source"]["source_key"])
            else:
                outcome = persist_scanner_cycle(connection, cycle)
                status = outcome.get("status")
                if status == "PERSISTED":
                    persisted += 1
                    processed_source_keys.add(cycle["source"]["source_key"])
                    watermark = cycle["next_watermark"]
                elif status == "DUPLICATE":
                    duplicates += 1
                    processed_source_keys.add(cycle["source"]["source_key"])
                else:
                    raise AlrFreshnessRuntimeError("persistence_status_invalid")
            on_row(row, cycle, status)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {"rows_seen": len(rows), "persisted": persisted, "duplicates": duplicates}


def _record_notification_event(
    connection: Any,
    *,
    session_id: str,
    event_kind: str,
    source_ts: Any = None,
    source_scan_id: str | None = None,
    source_hash: str | None = None,
    notification_ts_ms: int | None = None,
    error_code: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind=event_kind,
        source_ts=source_ts,
        source_scan_id=source_scan_id,
        source_hash=source_hash,
        notification_ts_ms=notification_ts_ms,
        error_code=error_code,
        details=details,
    )


def _record_lane_success(
    connection: Any,
    *,
    session_id: str,
    lane: str,
    cursor: Mapping[str, Any] | None,
    result: Mapping[str, int],
) -> None:
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="LANE_SUCCESS",
        lane=lane,
        source_ts=None if cursor is None else cursor["source_ts"],
        source_scan_id=None if cursor is None else cursor["source_scan_id"],
        source_hash=None if cursor is None else cursor.get("source_hash"),
        details=dict(result),
    )


def _historical_cursor_created(connection: Any) -> bool:
    return load_consumer_state(connection)["historical_cursor"] is not None


def _cycle_cursor(cycle: Mapping[str, Any]) -> dict[str, Any]:
    source = cycle["source"]
    return {
        "source_ts": source["ts"],
        "source_scan_id": source["scan_id"],
        "source_hash": cycle["source_hash"],
    }


def _row_ts_ms(row: Mapping[str, Any], source: Mapping[str, Any]) -> int:
    del source
    value = row.get("ts")
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value)
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlrFreshnessRuntimeError("scanner_identity_timestamp_invalid")
    delta = parsed.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (
        delta.days * 86_400_000
        + delta.seconds * 1_000
        + delta.microseconds // 1_000
    )


def _validate_batch(value: Any, *, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise AlrFreshnessRuntimeError("backlog_batch_limit_invalid")
