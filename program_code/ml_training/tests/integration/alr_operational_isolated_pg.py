"""Run the P2-4 statistical challenger path against disposable PostgreSQL."""

from __future__ import annotations

import json
import os
from typing import Any

from ml_training.alr_event_consumer import run_operational_backlog


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
    shadow = _connect(_required_env("ALR_ISOLATED_SHADOW_DSN"))
    try:
        result = run_operational_backlog(
            shadow,
            source_head="a" * 40,
            max_batch=8,
        )
        expected = {
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
            "operational_provenance_rows_written": 8,
            "operational_run_rows_written": 1,
            "operational_feedback_rows_written": 0,
            "operational_defer_artifact_rows_written": 1,
            "operational_source_rows_consumed": 4,
        }
        if (
            set(result) != set(expected) | {
                "operational_payload_bytes_written"
            }
            or any(result.get(key) != value for key, value in expected.items())
            or not isinstance(
                result.get("operational_payload_bytes_written"),
                int,
            )
            or result["operational_payload_bytes_written"] <= 0
        ):
            raise AssertionError(f"unexpected_first_result:{result}")
        shadow.commit()

        duplicate = run_operational_backlog(
            shadow,
            source_head="a" * 40,
            max_batch=8,
        )
        if duplicate["training_runs"] != 0 or duplicate["training_duplicates"] != 0:
            raise AssertionError(f"untrained_source_reprocessed:{duplicate}")

        with shadow.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM learning.alr_training_runs")
            run_count = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_provenance_edges "
                "WHERE edge_role = 'training_input'"
            )
            training_input_count = cursor.fetchone()["count"]
            for table in (
                "alr_artifact_nodes",
                "alr_provenance_edges",
                "alr_training_runs",
            ):
                try:
                    cursor.execute(f"UPDATE learning.{table} SET created_at = created_at")
                except Exception:
                    shadow.rollback()
                else:
                    raise AssertionError(f"shadow_update_granted:{table}")
        print(
            json.dumps(
                {
                    "schema_version": "alr_operational_isolated_pg_v1",
                    "status": "PASS",
                    "training_result": result,
                    "run_count": run_count,
                    "training_input_count": training_input_count,
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
        shadow.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
