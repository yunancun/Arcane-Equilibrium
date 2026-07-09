"""Run the P2-3 listener contract against an isolated PostgreSQL instance."""

from __future__ import annotations

import json
import os
from typing import Any

from ml_training.alr_event_consumer import (
    ALR_SCANNER_NOTIFY_CHANNEL,
    acquire_single_instance,
    drain_notified_backlog,
    release_single_instance,
    wait_for_pg_notifications,
)


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

        notifications = wait_for_pg_notifications(listener, timeout_seconds=5.0)
        result = drain_notified_backlog(listener, notifications, max_batch=8)
        if result != {
            "notifications_seen": 1,
            "rows_seen": 1,
            "persisted": 1,
            "duplicates": 0,
        }:
            raise AssertionError(f"unexpected_drain_result:{result}")
        duplicate_result = drain_notified_backlog(listener, notifications, max_batch=8)
        if duplicate_result["rows_seen"] != 0 or duplicate_result["persisted"] != 0:
            raise AssertionError(f"duplicate_reprocessed:{duplicate_result}")
        print(
            json.dumps(
                {
                    "schema_version": "alr_event_consumer_isolated_pg_v1",
                    "status": "PASS",
                    "listener_result": result,
                    "duplicate_result": duplicate_result,
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
