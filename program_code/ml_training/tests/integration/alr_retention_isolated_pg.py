"""Verify P2-6 quarantine -> grace recheck -> sweep in disposable PostgreSQL."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from ml_training.alr_retention_repository import run_retention_pass


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _connect(dsn: str) -> Any:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore

    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def main() -> int:
    connection = _connect(_required_env("ALR_ISOLATED_SHADOW_DSN"))
    now = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    try:
        quarantine = run_retention_pass(
            connection,
            now=now,
            grace_seconds=60,
            limit=4,
        )
        if quarantine != {
            "scanned": 1,
            "quarantined": 1,
            "restored": 0,
            "swept": 0,
            "retained": 0,
            "skipped": 0,
        }:
            raise AssertionError(f"quarantine_failed:{quarantine}")
        sweep = run_retention_pass(
            connection,
            now=now + timedelta(seconds=61),
            grace_seconds=60,
            limit=4,
        )
        if sweep["swept"] != 1:
            raise AssertionError(f"sweep_failed:{sweep}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM learning.alr_derived_cache_entries")
            cache_count = cursor.fetchone()["count"]
            cursor.execute("SELECT count(*) AS count FROM learning.alr_retention_events")
            event_count = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_artifact_nodes "
                "WHERE artifact_kind = 'derived_cache'"
            )
            artifact_count = cursor.fetchone()["count"]
            try:
                cursor.execute("DELETE FROM learning.alr_training_runs")
            except Exception:
                connection.rollback()
            else:
                raise AssertionError("shadow_non_cache_delete_granted")
        print(
            json.dumps(
                {
                    "schema_version": "alr_retention_isolated_pg_v1",
                    "status": "PASS",
                    "quarantine": quarantine,
                    "sweep": sweep,
                    "cache_count": cache_count,
                    "retention_event_count": event_count,
                    "derived_cache_artifact_count": artifact_count,
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
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
