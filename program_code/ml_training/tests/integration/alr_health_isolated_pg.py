"""Persist one P2-7 health snapshot with the real isolated shadow role."""

from __future__ import annotations

import json
import os
from typing import Any

from ml_training.alr_event_consumer import process_health_snapshot


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
    try:
        result = process_health_snapshot(connection, source_head="a" * 40)
        expected = {
            "health_attempts": 1,
            "health_snapshots": 1,
            "health_state_delta_writes": 1,
            "health_heartbeat_writes": 0,
            "health_writes_suppressed": 0,
            "health_rows_written": 2,
            "health_authority_mismatches": 0,
        }
        if (
            set(result) != set(expected) | {"health_payload_bytes_written"}
            or any(result.get(key) != value for key, value in expected.items())
            or not isinstance(result.get("health_payload_bytes_written"), int)
            or result["health_payload_bytes_written"] <= 0
        ):
            raise AssertionError(f"health_result_invalid:{result}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM learning.alr_health_events")
            health_event_count = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_artifact_nodes "
                "WHERE artifact_kind = 'health_snapshot'"
            )
            artifact_count = cursor.fetchone()["count"]
            try:
                cursor.execute("UPDATE learning.alr_health_events SET source_head = source_head")
            except Exception:
                connection.rollback()
            else:
                raise AssertionError("shadow_health_update_granted")
        print(
            json.dumps(
                {
                    "schema_version": "alr_health_isolated_pg_v1",
                    "status": "PASS",
                    "health_result": result,
                    "health_event_count": health_event_count,
                    "health_snapshot_artifact_count": artifact_count,
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
