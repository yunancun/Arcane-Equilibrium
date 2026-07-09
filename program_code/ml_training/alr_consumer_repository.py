"""
MODULE_NOTE
模塊用途：持久化 ALR consumer lifecycle 與 fresh/history lane 的 append-only 狀態。
主要函數：record_consumer_event、load_consumer_state、fetch_fresh_lane_rows。
硬邊界：scanner 僅可 SELECT；consumer 狀態僅可 INSERT 到 learning.alr_*。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


FRESH_LANE = "FRESH"
HISTORICAL_LANE = "HISTORICAL"
_LANES = {FRESH_LANE, HISTORICAL_LANE}
_EVENT_KINDS = {
    "SESSION_STARTED",
    "SESSION_STOPPED",
    "SESSION_FAILED",
    "UNCLEAN_RECOVERY",
    "NOTIFICATION_RECEIVED",
    "NOTIFICATION_CONSUMED",
    "NOTIFICATION_DUPLICATE",
    "NOTIFICATION_INVALID",
    "LANE_BOOTSTRAPPED",
    "LANE_CURSOR_ADVANCED",
    "LANE_SUCCESS",
}
_CURSOR_EVENT_KINDS = {"LANE_BOOTSTRAPPED", "LANE_CURSOR_ADVANCED"}
_SCANNER_SELECT = (
    "SELECT scanner.ts, scanner.scan_id, scanner.active_symbols, scanner.added, "
    "scanner.removed, scanner.rejected_count, scanner.scan_duration_ms, "
    "scanner.candidates, scanner.config FROM trading.scanner_snapshots AS scanner "
)
_SOURCE_TABLE = "trading.scanner_snapshots"


class AlrConsumerRepositoryError(ValueError):
    """Consumer 狀態無法安全表示或持久化。"""


def new_session_id() -> str:
    """建立不含主機或 credential 資訊的 opaque session identity。"""
    return str(uuid.uuid4())


def record_consumer_event(
    connection: Any,
    *,
    session_id: str,
    event_kind: str,
    lane: str | None = None,
    source_ts: Any = None,
    source_scan_id: str | None = None,
    source_hash: str | None = None,
    notification_ts_ms: int | None = None,
    error_code: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """追加一筆 typed consumer event；任何修正都必須是新事件。"""
    normalized_session_id = _uuid_text(session_id, "consumer_session_id_invalid")
    if event_kind not in _EVENT_KINDS:
        raise AlrConsumerRepositoryError("consumer_event_kind_invalid")
    if lane is not None and lane not in _LANES:
        raise AlrConsumerRepositoryError("consumer_lane_invalid")
    if event_kind in _CURSOR_EVENT_KINDS:
        if (
            lane is None
            or source_ts is None
            or not _text(source_scan_id)
            or source_hash is None
        ):
            raise AlrConsumerRepositoryError("consumer_cursor_identity_invalid")
        _validate_cursor_lineage(
            connection,
            source_ts=source_ts,
            source_scan_id=str(source_scan_id),
            source_hash=source_hash,
        )
        current = _fetch_lane_cursor(connection, lane, latest=True)
        if event_kind == "LANE_BOOTSTRAPPED" and current is not None:
            raise AlrConsumerRepositoryError("consumer_lane_already_bootstrapped")
        if event_kind == "LANE_CURSOR_ADVANCED" and current is not None:
            if _identity_key(source_ts, str(source_scan_id)) <= _identity_key(
                current["source_ts"],
                current["source_scan_id"],
            ):
                raise AlrConsumerRepositoryError("consumer_cursor_non_monotonic")
    if notification_ts_ms is not None and (
        isinstance(notification_ts_ms, bool)
        or not isinstance(notification_ts_ms, int)
        or notification_ts_ms < 0
    ):
        raise AlrConsumerRepositoryError("consumer_notification_ts_ms_invalid")
    if source_hash is not None and (
        not isinstance(source_hash, str)
        or len(source_hash) != 64
        or any(character not in "0123456789abcdef" for character in source_hash)
    ):
        raise AlrConsumerRepositoryError("consumer_source_hash_invalid")
    if error_code is not None and (not isinstance(error_code, str) or not error_code):
        raise AlrConsumerRepositoryError("consumer_error_code_invalid")
    payload = dict(details or {})
    event_id = str(uuid.uuid4())
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO learning.alr_consumer_events "
                "(event_id, session_id, event_kind, lane, source_ts, source_scan_id, "
                "source_hash, notification_ts_ms, error_code, details) "
                "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    event_id,
                    normalized_session_id,
                    event_kind,
                    lane,
                    source_ts,
                    source_scan_id,
                    source_hash,
                    notification_ts_ms,
                    error_code,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {"event_id": event_id, "event_kind": event_kind}


def find_unclosed_session(connection: Any) -> str | None:
    """找出最後一個沒有 STOPPED/FAILED 結尾的 session。"""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT started.session_id FROM learning.alr_consumer_events AS started "
            "WHERE started.event_kind = 'SESSION_STARTED' AND NOT EXISTS ("
            "SELECT 1 FROM learning.alr_consumer_events AS terminal "
            "WHERE terminal.session_id = started.session_id "
            "AND terminal.event_kind IN ("
            "'SESSION_STOPPED', 'SESSION_FAILED', 'UNCLEAN_RECOVERY')) "
            "ORDER BY started.recorded_at DESC, started.event_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
    return None if row is None else str(_row_value(row, 0, "session_id"))


def start_consumer_session(connection: Any, *, session_id: str) -> str | None:
    """記錄 start，並把先前未閉合 session 明確標成 unclean recovery。"""
    previous = find_unclosed_session(connection)
    if previous is not None:
        record_consumer_event(
            connection,
            session_id=previous,
            event_kind="UNCLEAN_RECOVERY",
            details={"recovered_by_session_id": session_id},
        )
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="SESSION_STARTED",
    )
    return previous


def stop_consumer_session(connection: Any, *, session_id: str) -> None:
    """記錄 graceful stop。"""
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="SESSION_STOPPED",
    )


def fail_consumer_session(
    connection: Any,
    *,
    session_id: str,
    error_code: str,
) -> None:
    """只記錄 sanitized failure class，不持久化 exception/DSN 內容。"""
    record_consumer_event(
        connection,
        session_id=session_id,
        event_kind="SESSION_FAILED",
        error_code=error_code,
    )


def load_consumer_state(connection: Any) -> dict[str, Any]:
    """從 immutable events 重建 fresh/history cursor 與固定 history boundary。"""
    return {
        "fresh_cursor": _fetch_lane_cursor(connection, FRESH_LANE, latest=True),
        "fresh_anchor": _fetch_fresh_anchor(connection),
        "historical_cursor": _fetch_lane_cursor(
            connection,
            HISTORICAL_LANE,
            latest=True,
        ),
    }


def fetch_latest_alr_watermark(connection: Any) -> dict[str, Any] | None:
    """讀取 V156 首次 bootstrap 可沿用的最新 legacy ALR watermark。"""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_ts, source_scan_id, source_hash "
            "FROM learning.alr_watermark_events "
            "WHERE source_table = 'trading.scanner_snapshots' "
            "AND watermark_event_kind = 'ADVANCED' "
            "ORDER BY source_ts DESC, source_scan_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
    return None if row is None else _cursor_from_row(row)


def fetch_latest_scanner_snapshot(connection: Any) -> dict[str, Any] | None:
    """無既有 ALR source 時只取最新 raw identity 作 fresh bootstrap。"""
    with connection.cursor() as cursor:
        cursor.execute(
            _SCANNER_SELECT + "ORDER BY scanner.ts DESC, scanner.scan_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
    return _scanner_row(row)


def fetch_fresh_lane_rows(
    connection: Any,
    *,
    cursor_state: Mapping[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """依 composite cursor 連續讀 raw；刻意包含已由 exact notification 攝取的 row。"""
    source_ts, source_scan_id = _cursor_identity(cursor_state)
    _bounded_limit(limit, maximum=256)
    with connection.cursor() as cursor:
        cursor.execute(
            _SCANNER_SELECT
            + "WHERE (scanner.ts, scanner.scan_id) > (%s::timestamptz, %s) "
            "ORDER BY scanner.ts ASC, scanner.scan_id ASC LIMIT %s",
            (source_ts, source_scan_id, limit),
        )
        rows = cursor.fetchall()
    return _scanner_rows(rows)


def fetch_fresh_raw_only_holes(
    connection: Any,
    *,
    anchor_cursor: Mapping[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """從 immutable fresh anchor 後找 raw-only 洞，recent identity 優先修復。"""
    anchor_ts, anchor_scan_id = _cursor_identity(anchor_cursor)
    _bounded_limit(limit, maximum=256)
    with connection.cursor() as cursor:
        cursor.execute(
            _SCANNER_SELECT
            + "WHERE (scanner.ts, scanner.scan_id) > (%s::timestamptz, %s) "
            "AND NOT EXISTS (SELECT 1 FROM learning.alr_source_events AS alr "
            "WHERE alr.source_table = %s AND alr.source_ts = scanner.ts "
            "AND alr.source_scan_id = scanner.scan_id) "
            "ORDER BY scanner.ts DESC, scanner.scan_id DESC LIMIT %s",
            (anchor_ts, anchor_scan_id, _SOURCE_TABLE, limit),
        )
        rows = cursor.fetchall()
    return _scanner_rows(rows)


def fetch_historical_lane_rows(
    connection: Any,
    *,
    after_cursor: Mapping[str, Any] | None,
    before_cursor: Mapping[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """在 immutable bootstrap boundary 前依獨立 cursor 低優先回填。"""
    before_ts, before_scan_id = _cursor_identity(before_cursor)
    _bounded_limit(limit, maximum=8)
    params: tuple[Any, ...]
    if after_cursor is None:
        predicate = "WHERE (scanner.ts, scanner.scan_id) < (%s::timestamptz, %s) "
        params = (before_ts, before_scan_id, limit)
    else:
        after_ts, after_scan_id = _cursor_identity(after_cursor)
        predicate = (
            "WHERE (scanner.ts, scanner.scan_id) > (%s::timestamptz, %s) "
            "AND (scanner.ts, scanner.scan_id) < (%s::timestamptz, %s) "
        )
        params = (after_ts, after_scan_id, before_ts, before_scan_id, limit)
    with connection.cursor() as cursor:
        cursor.execute(
            _SCANNER_SELECT
            + predicate
            + "ORDER BY scanner.ts ASC, scanner.scan_id ASC LIMIT %s",
            params,
        )
        rows = cursor.fetchall()
    return _scanner_rows(rows)


def _fetch_lane_cursor(connection: Any, lane: str, *, latest: bool) -> dict[str, Any] | None:
    direction = "DESC" if latest else "ASC"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_ts, source_scan_id, source_hash "
            "FROM learning.alr_consumer_events WHERE lane = %s "
            "AND event_kind IN ('LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED') "
            "AND source_ts IS NOT NULL AND source_scan_id IS NOT NULL "
            f"ORDER BY source_ts {direction}, source_scan_id {direction}, "
            f"event_id {direction} LIMIT 1",
            (lane,),
        )
        row = cursor.fetchone()
    return None if row is None else _cursor_from_row(row)


def _validate_cursor_lineage(
    connection: Any,
    *,
    source_ts: Any,
    source_scan_id: str,
    source_hash: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_hash FROM learning.alr_source_events "
            "WHERE source_table = %s AND source_ts = %s AND source_scan_id = %s",
            (_SOURCE_TABLE, source_ts, source_scan_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise AlrConsumerRepositoryError("consumer_cursor_source_missing")
    if str(_row_value(row, 0, "source_hash")) != source_hash:
        raise AlrConsumerRepositoryError("consumer_cursor_source_hash_mismatch")


def _fetch_fresh_anchor(connection: Any) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_ts, source_scan_id, source_hash "
            "FROM learning.alr_consumer_events WHERE lane = %s "
            "AND event_kind = 'LANE_BOOTSTRAPPED' AND source_ts IS NOT NULL "
            "ORDER BY source_ts ASC, source_scan_id ASC, event_id ASC LIMIT 1",
            (FRESH_LANE,),
        )
        row = cursor.fetchone()
    return None if row is None else _cursor_from_row(row)


def _cursor_from_row(row: Any) -> dict[str, Any]:
    return {
        "source_ts": _row_value(row, 0, "source_ts"),
        "source_scan_id": str(_row_value(row, 1, "source_scan_id")),
        "source_hash": _row_value(row, 2, "source_hash"),
    }


def _cursor_identity(value: Mapping[str, Any]) -> tuple[Any, str]:
    if not isinstance(value, Mapping) or value.get("source_ts") is None:
        raise AlrConsumerRepositoryError("consumer_cursor_invalid")
    scan_id = _text(value.get("source_scan_id"))
    if not scan_id:
        raise AlrConsumerRepositoryError("consumer_cursor_invalid")
    return value["source_ts"], scan_id


def _identity_key(source_ts: Any, source_scan_id: str) -> tuple[datetime, str]:
    if isinstance(source_ts, datetime):
        parsed = source_ts
    elif isinstance(source_ts, str) and source_ts:
        candidate = source_ts[:-1] + "+00:00" if source_ts.endswith("Z") else source_ts
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise AlrConsumerRepositoryError("consumer_cursor_timestamp_invalid") from exc
    else:
        raise AlrConsumerRepositoryError("consumer_cursor_timestamp_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlrConsumerRepositoryError("consumer_cursor_timestamp_invalid")
    return parsed.astimezone(timezone.utc), source_scan_id


def _scanner_row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if not isinstance(row, Mapping):
        raise AlrConsumerRepositoryError("consumer_scanner_row_invalid")
    return dict(row)


def _scanner_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise AlrConsumerRepositoryError("consumer_scanner_rows_invalid")
    if not all(isinstance(row, Mapping) for row in rows):
        raise AlrConsumerRepositoryError("consumer_scanner_row_invalid")
    return [dict(row) for row in rows]


def _bounded_limit(value: Any, *, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise AlrConsumerRepositoryError("consumer_fetch_limit_invalid")


def _uuid_text(value: Any, reason: str) -> str:
    if not isinstance(value, str):
        raise AlrConsumerRepositoryError(reason)
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise AlrConsumerRepositoryError(reason) from exc


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]
