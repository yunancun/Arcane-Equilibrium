"""Exercise P2-5 deferred feedback and next-target rotation in isolated PG."""

from __future__ import annotations

import json
import os
from typing import Any

from ml_training.alr_event_consumer import (
    process_outcome_feedback_backlog,
    run_operational_backlog,
)


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
        first = run_operational_backlog(connection, source_head="a" * 40, max_batch=4)
        if first["training_runs"] != 1:
            raise AssertionError(f"first_target_missing:{first}")
        feedback = process_outcome_feedback_backlog(connection, max_batch=4)
        if feedback != {
            "feedback_persisted": 1,
            "feedback_duplicates": 0,
            "feedback_deferred": 1,
            "feedback_rotations": 1,
            "feedback_boundary_blocks": 0,
        }:
            raise AssertionError(f"feedback_rotation_failed:{feedback}")
        second = run_operational_backlog(connection, source_head="a" * 40, max_batch=4)
        if second["training_runs"] != 1:
            raise AssertionError(f"second_target_missing:{second}")
        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM learning.alr_training_runs")
            run_count = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_outcome_feedback_events"
            )
            feedback_count = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_provenance_edges "
                "WHERE edge_role = 'feedback_rotation'"
            )
            rotation_edges = cursor.fetchone()["count"]
            try:
                cursor.execute(
                    "UPDATE learning.alr_outcome_feedback_events "
                    "SET reward_record_count = reward_record_count"
                )
            except Exception:
                connection.rollback()
            else:
                raise AssertionError("shadow_feedback_update_granted")
        print(
            json.dumps(
                {
                    "schema_version": "alr_outcome_feedback_isolated_pg_v1",
                    "status": "PASS",
                    "first_target": first,
                    "feedback": feedback,
                    "second_target": second,
                    "run_count": run_count,
                    "feedback_count": feedback_count,
                    "rotation_edges": rotation_edges,
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
