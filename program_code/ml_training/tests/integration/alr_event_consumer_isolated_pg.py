"""Run the P2-3 listener contract against an isolated PostgreSQL instance."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from ml_training.alr_event_consumer import (
    ALR_SCANNER_NOTIFY_CHANNEL,
    acquire_single_instance,
    drain_notified_backlog,
    release_single_instance,
    wait_for_pg_notifications,
)
from ml_training.alr_freshness_runtime import (
    drain_fresh_lane,
    ensure_fresh_lane_bootstrap,
)
from ml_training.alr_health_repository import collect_health_snapshot


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _connect(dsn: str, *, autocommit: bool) -> Any:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore

    connection = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    connection.autocommit = autocommit
    return connection


def main() -> int:
    shadow_dsn = _required_env("ALR_ISOLATED_SHADOW_DSN")
    admin_dsn = _required_env("ALR_ISOLATED_ADMIN_DSN")
    listener = _connect(shadow_dsn, autocommit=False)
    contender = _connect(shadow_dsn, autocommit=False)
    notifier = _connect(admin_dsn, autocommit=True)
    lock_acquired = False
    try:
        with notifier.cursor() as cursor:
            cursor.execute(
                "INSERT INTO trading.scanner_snapshots "
                "(ts, scan_id, active_symbols, added, removed, rejected_count, "
                "scan_duration_ms, candidates, config) "
                "SELECT TIMESTAMPTZ '2020-01-01T00:00:00Z' + "
                "(ordinal * INTERVAL '1 second'), 'historical-' || ordinal, "
                "ARRAY['BTCUSDT'], ARRAY['BTCUSDT'], ARRAY[]::text[], 0, 1, "
                "'[{\"symbol\":\"BTCUSDT\"}]'::jsonb, '{}'::jsonb "
                "FROM generate_series(1, 79000) AS ordinal "
                "ON CONFLICT (scan_id, ts) DO NOTHING"
            )
            cursor.execute(
                "INSERT INTO trading.scanner_snapshots "
                "(ts, scan_id, active_symbols, added, removed, rejected_count, "
                "scan_duration_ms, candidates, config) VALUES ("
                "TIMESTAMPTZ 'epoch' + (1783598400000::bigint * INTERVAL '1 millisecond'), "
                "'isolated-scan-1', ARRAY['BTCUSDT'], ARRAY['BTCUSDT'], "
                "ARRAY[]::text[], 0, 1, '[{\"symbol\":\"BTCUSDT\"}]'::jsonb, '{}'::jsonb) "
                "ON CONFLICT (scan_id, ts) DO NOTHING"
            )
        with listener.cursor() as cursor:
            cursor.execute(f"LISTEN {ALR_SCANNER_NOTIFY_CHANNEL}")
        listener.commit()
        lock_acquired = acquire_single_instance(listener)
        if not lock_acquired or acquire_single_instance(contender):
            raise AssertionError("single_instance_lock_contract_failed")

        payload = json.dumps(
            {
                "schema_version": "alr_scanner_notification_v1",
                "scan_id": "isolated-scan-1",
                "ts_ms": 1783598400000,
            },
            sort_keys=True,
        )
        with notifier.cursor() as cursor:
            cursor.execute("SELECT pg_notify(%s, %s)", (ALR_SCANNER_NOTIFY_CHANNEL, payload))

        notifications = wait_for_pg_notifications(
            listener,
            timeout_seconds=5.0,
            max_batch=8,
        )
        session_id = "00000000-0000-0000-0000-000000000001"
        result = drain_notified_backlog(
            listener,
            notifications,
            max_batch=8,
            session_id=session_id,
        )
        if result != {
            "notifications_seen": 1,
            "notifications_received": 1,
            "notifications_consumed": 1,
            "notifications_invalid": 0,
            "rows_seen": 1,
            "persisted": 1,
            "duplicates": 0,
        }:
            raise AssertionError(f"unexpected_drain_result:{result}")
        with listener.cursor() as cursor:
            cursor.execute(
                "SELECT source_ts, source_scan_id, source_hash "
                "FROM learning.alr_source_events WHERE source_scan_id = %s",
                ("isolated-scan-1",),
            )
            exact_source = cursor.fetchone()
        listener.commit()
        lineage_rejections = 0
        for source_ts, scan_id, source_hash in (
            (exact_source["source_ts"], "phantom-scan", "f" * 64),
            (exact_source["source_ts"], exact_source["source_scan_id"], "e" * 64),
        ):
            try:
                with notifier.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO learning.alr_consumer_events "
                        "(event_id, session_id, event_kind, lane, source_ts, "
                        "source_scan_id, source_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            str(uuid.uuid4()),
                            session_id,
                            "LANE_CURSOR_ADVANCED",
                            "FRESH",
                            source_ts,
                            scan_id,
                            source_hash,
                        ),
                    )
            except Exception:
                lineage_rejections += 1
        if lineage_rejections != 2:
            raise AssertionError(f"lineage_fk_rejections_invalid:{lineage_rejections}")
        with listener.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM learning.alr_ingest_events")
            ingest_events_before_duplicate = cursor.fetchone()["count"]
        listener.commit()
        duplicate_result = drain_notified_backlog(
            listener,
            notifications,
            max_batch=8,
            session_id=session_id,
        )
        if (
            duplicate_result["rows_seen"] != 1
            or duplicate_result["persisted"] != 0
            or duplicate_result["duplicates"] != 0
        ):
            raise AssertionError(f"duplicate_reprocessed:{duplicate_result}")
        with listener.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM learning.alr_ingest_events")
            ingest_events_after_duplicate = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_source_events "
                "WHERE source_scan_id LIKE 'historical-%'"
            )
            historical_ingested = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT event_kind, count(*) AS count "
                "FROM learning.alr_consumer_events "
                "WHERE event_kind LIKE 'NOTIFICATION_%' GROUP BY event_kind"
            )
            notification_counts = {
                row["event_kind"]: row["count"] for row in cursor.fetchall()
            }
        listener.commit()
        if ingest_events_after_duplicate != ingest_events_before_duplicate:
            raise AssertionError(
                "duplicate_notification_appended_ingest_event:"
                f"{ingest_events_before_duplicate}->{ingest_events_after_duplicate}"
            )
        if historical_ingested != 0:
            raise AssertionError(f"fresh_starved_by_history:{historical_ingested}")
        if notification_counts != {
            "NOTIFICATION_RECEIVED": 2,
            "NOTIFICATION_CONSUMED": 2,
            "NOTIFICATION_DUPLICATE": 1,
        }:
            raise AssertionError(f"notification_counts_invalid:{notification_counts}")
        ensure_fresh_lane_bootstrap(listener, session_id=session_id)
        with notifier.cursor() as cursor:
            cursor.execute(
                "INSERT INTO trading.scanner_snapshots "
                "(ts, scan_id, active_symbols, added, removed, rejected_count, "
                "scan_duration_ms, candidates, config) VALUES ("
                "TIMESTAMPTZ 'epoch' + (1783598520000::bigint * INTERVAL '1 millisecond'), "
                "'isolated-scan-2', ARRAY['BTCUSDT'], ARRAY[]::text[], "
                "ARRAY[]::text[], 0, 1, '[{\"symbol\":\"BTCUSDT\"}]'::jsonb, '{}'::jsonb) "
                "ON CONFLICT (scan_id, ts) DO NOTHING"
            )
        fresh_two_payload = json.dumps(
            {
                "schema_version": "alr_scanner_notification_v1",
                "scan_id": "isolated-scan-2",
                "ts_ms": 1783598520000,
            },
            sort_keys=True,
        )
        drain_notified_backlog(
            listener,
            [(ALR_SCANNER_NOTIFY_CHANNEL, fresh_two_payload)],
            max_batch=8,
            session_id=session_id,
        )
        drain_fresh_lane(listener, session_id=session_id, max_batch=8)
        with notifier.cursor() as cursor:
            cursor.execute(
                "INSERT INTO trading.scanner_snapshots "
                "(ts, scan_id, active_symbols, added, removed, rejected_count, "
                "scan_duration_ms, candidates, config) VALUES ("
                "TIMESTAMPTZ 'epoch' + (1783598460000::bigint * INTERVAL '1 millisecond'), "
                "'isolated-scan-gap', ARRAY['BTCUSDT'], ARRAY[]::text[], "
                "ARRAY[]::text[], 0, 1, '[{\"symbol\":\"BTCUSDT\"}]'::jsonb, '{}'::jsonb) "
                "ON CONFLICT (scan_id, ts) DO NOTHING"
            )
        before_repair = collect_health_snapshot(listener, source_head="a" * 40)
        listener.commit()
        cursor_before_repair = before_repair["ingestion"]["fresh_cursor_ts"]
        repair_result = drain_fresh_lane(listener, session_id=session_id, max_batch=8)
        after_repair = collect_health_snapshot(listener, source_head="a" * 40)
        listener.commit()
        if before_repair["ingestion"]["fresh_raw_only_count"] != 1:
            raise AssertionError(f"old_hole_not_detected:{before_repair['ingestion']}")
        if after_repair["ingestion"]["fresh_raw_only_count"] != 0:
            raise AssertionError(f"old_hole_not_repaired:{after_repair['ingestion']}")
        if after_repair["ingestion"]["fresh_cursor_ts"] != cursor_before_repair:
            raise AssertionError("old_hole_repair_rewound_or_advanced_cursor")
        with listener.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_source_events "
                "WHERE source_scan_id LIKE 'historical-%'"
            )
            history_after_fresh_repair = cursor.fetchone()["count"]
        listener.commit()
        if history_after_fresh_repair != 0:
            raise AssertionError(f"history_entered_fresh_repair:{history_after_fresh_repair}")
        print(
            json.dumps(
                {
                    "schema_version": "alr_event_consumer_isolated_pg_v1",
                    "status": "PASS",
                    "listener_result": result,
                    "duplicate_result": duplicate_result,
                    "historical_backlog_rows": 79000,
                    "historical_ingested_during_exact_drain": historical_ingested,
                    "notification_counts": notification_counts,
                    "ingest_events_before_duplicate": ingest_events_before_duplicate,
                    "ingest_events_after_duplicate": ingest_events_after_duplicate,
                    "lineage_fk_rejections": lineage_rejections,
                    "old_hole_before_repair": before_repair["ingestion"],
                    "old_hole_after_repair": after_repair["ingestion"],
                    "old_hole_repair_result": repair_result,
                    "history_after_fresh_repair": history_after_fresh_repair,
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
    finally:
        if lock_acquired:
            release_single_instance(listener)
        listener.close()
        contender.close()
        notifier.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
