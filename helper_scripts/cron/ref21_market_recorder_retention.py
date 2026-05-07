#!/usr/bin/env python3
"""REF-21 market recorder retention for replay microstructure tables.

This cron prunes only locally recorded public-market data used by replay:
`market.market_tickers` and `market.ob_snapshots`. It never touches trading,
learning, settings, or replay result schemas.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ref21_market_microstructure_recorder import (  # noqa: E402
    connect_db,
    process_lock,
    read_db_config,
    table_exists,
)


RECORDER_TABLES = ("market.market_tickers", "market.ob_snapshots")
DEFAULT_RETENTION_DAYS = 45
MIN_RETENTION_DAYS = 14
DEFAULT_MAX_DELETE_ROWS = 500_000


def retention_days_from_env(value: str | None = None) -> int:
    raw = value if value is not None else os.environ.get(
        "OPENCLAW_REF21_RECORDER_RETENTION_DAYS",
        str(DEFAULT_RETENTION_DAYS),
    )
    try:
        parsed = int(str(raw))
    except ValueError:
        parsed = DEFAULT_RETENTION_DAYS
    return max(MIN_RETENTION_DAYS, parsed)


def cutoff_for_retention(now: datetime, retention_days: int) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc) - timedelta(days=retention_days)


def _split_table(table: str) -> tuple[str, str]:
    if table not in RECORDER_TABLES:
        raise ValueError(f"table_not_allowed:{table}")
    schema, name = table.split(".", 1)
    return schema, name


def count_prune_candidates(cur: Any, table: str, cutoff: datetime) -> int:
    schema, name = _split_table(table)
    if not table_exists(cur, schema, name):
        return 0
    cur.execute(f"SELECT COUNT(*)::bigint FROM {table} WHERE ts < %s;", (cutoff,))
    row = cur.fetchone() or (0,)
    return int(row[0] or 0)


def prune_table(
    cur: Any,
    table: str,
    cutoff: datetime,
    *,
    max_rows: int,
    apply: bool,
) -> dict[str, Any]:
    schema, name = _split_table(table)
    if not table_exists(cur, schema, name):
        return {
            "table": table,
            "status": "absent",
            "candidate_rows": 0,
            "deleted_rows": 0,
        }
    candidates = count_prune_candidates(cur, table, cutoff)
    if not apply or candidates <= 0:
        return {
            "table": table,
            "status": "dry_run" if not apply else "empty",
            "candidate_rows": candidates,
            "deleted_rows": 0,
        }
    limit = max(1, min(int(max_rows), DEFAULT_MAX_DELETE_ROWS))
    cur.execute(
        f"""
        WITH doomed AS (
            SELECT ctid
            FROM {table}
            WHERE ts < %s
            ORDER BY ts ASC
            LIMIT %s
        )
        DELETE FROM {table}
        WHERE ctid IN (SELECT ctid FROM doomed);
        """,
        (cutoff, limit),
    )
    deleted = int(getattr(cur, "rowcount", 0) or 0)
    return {
        "table": table,
        "status": "applied",
        "candidate_rows": candidates,
        "deleted_rows": deleted,
        "max_rows": limit,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=retention_days_from_env(),
    )
    parser.add_argument(
        "--max-delete-rows",
        type=int,
        default=int(os.environ.get(
            "OPENCLAW_REF21_RECORDER_RETENTION_MAX_ROWS",
            str(DEFAULT_MAX_DELETE_ROWS),
        )),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    retention_days = max(MIN_RETENTION_DAYS, int(args.retention_days))
    max_rows = max(1, min(int(args.max_delete_rows), DEFAULT_MAX_DELETE_ROWS))
    now = datetime.now(tz=timezone.utc)
    cutoff = cutoff_for_retention(now, retention_days)
    summary: dict[str, Any] = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "tables": [],
    }
    with process_lock("ref21_market_recorder_retention.lock"):
        conn = connect_db(read_db_config())
        try:
            with conn.cursor() as cur:
                for table in RECORDER_TABLES:
                    summary["tables"].append(
                        prune_table(
                            cur,
                            table,
                            cutoff,
                            max_rows=max_rows,
                            apply=bool(args.apply),
                        )
                    )
            if args.apply:
                conn.commit()
                data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
                data_dir.mkdir(parents=True, exist_ok=True)
                (data_dir / "ref21_market_recorder_retention_last_run").touch()
            else:
                conn.rollback()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
