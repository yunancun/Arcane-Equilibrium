#!/usr/bin/env python3
"""Scheduled decision_outcomes backfill for live-lane cohorts.

This helper mirrors the fixed Rust outcome_backfiller SQL shape, but makes the
live/live_demo lane runnable from cron when the API scheduler is stale or down.
It updates labels only; it does not submit orders, mutate live authorization,
or change strategy/risk configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from typing import Iterable


VALID_ENGINE_MODES = {"paper", "demo", "live", "live_demo"}
DEFAULT_ENGINE_MODES = "live,live_demo"


BACKFILL_SQL = """
WITH pending AS (
    SELECT
        s.context_id,
        s.ts,
        s.symbol,
        s.last_price,
        s.engine_mode
    FROM trading.decision_context_snapshots s
    LEFT JOIN trading.decision_outcomes o ON o.context_id = s.context_id
    WHERE s.engine_mode = ANY(%(engine_modes)s::text[])
      AND s.last_price IS NOT NULL
      AND s.last_price > 0
      AND s.ts < NOW() - INTERVAL '25 hours'
      AND (
            s.outcome_backfilled = FALSE
         OR o.context_id IS NULL
         OR o.engine_mode IS DISTINCT FROM s.engine_mode
         OR (
                %(repair_existing)s
            AND (
                   o.backfilled_ts IS NULL
                OR o.outcome_1m IS NULL
                OR o.outcome_5m IS NULL
                OR o.outcome_1h IS NULL
                OR o.outcome_4h IS NULL
                OR o.outcome_24h IS NULL
                OR o.max_favorable IS NULL
                OR o.max_adverse IS NULL
            )
         )
      )
    ORDER BY s.ts ASC
    LIMIT %(batch_size)s
),
outcomes AS (
    SELECT
        p.context_id,
        p.last_price,
        p.engine_mode,
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1m'
           AND k.ts >= p.ts + INTERVAL '1 minute'
         ORDER BY k.ts ASC LIMIT 1) AS price_1m,
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '5m'
           AND k.ts >= p.ts + INTERVAL '5 minutes'
         ORDER BY k.ts ASC LIMIT 1) AS price_5m,
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1h'
           AND k.ts >= p.ts + INTERVAL '1 hour'
         ORDER BY k.ts ASC LIMIT 1) AS price_1h,
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '4h'
           AND k.ts >= p.ts + INTERVAL '4 hours'
         ORDER BY k.ts ASC LIMIT 1) AS price_4h,
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '4h'
           AND k.ts >= p.ts + INTERVAL '24 hours'
         ORDER BY k.ts ASC LIMIT 1) AS price_24h,
        (SELECT MAX(k.high) FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1m'
           AND k.ts > p.ts AND k.ts <= p.ts + INTERVAL '24 hours') AS max_high_24h,
        (SELECT MIN(k.low) FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1m'
           AND k.ts > p.ts AND k.ts <= p.ts + INTERVAL '24 hours') AS min_low_24h
    FROM pending p
),
upserted AS (
    INSERT INTO trading.decision_outcomes
        (context_id, outcome_1m, outcome_5m, outcome_1h, outcome_4h, outcome_24h,
         max_favorable, max_adverse, backfilled_ts, engine_mode)
    SELECT
        o.context_id,
        (o.price_1m  - o.last_price) / o.last_price,
        (o.price_5m  - o.last_price) / o.last_price,
        (o.price_1h  - o.last_price) / o.last_price,
        (o.price_4h  - o.last_price) / o.last_price,
        (o.price_24h - o.last_price) / o.last_price,
        (o.max_high_24h - o.last_price) / o.last_price,
        (o.min_low_24h  - o.last_price) / o.last_price,
        NOW(),
        o.engine_mode
    FROM outcomes o
    ON CONFLICT (context_id) DO UPDATE SET
        outcome_1m = EXCLUDED.outcome_1m,
        outcome_5m = EXCLUDED.outcome_5m,
        outcome_1h = EXCLUDED.outcome_1h,
        outcome_4h = EXCLUDED.outcome_4h,
        outcome_24h = EXCLUDED.outcome_24h,
        max_favorable = EXCLUDED.max_favorable,
        max_adverse = EXCLUDED.max_adverse,
        backfilled_ts = EXCLUDED.backfilled_ts,
        engine_mode = EXCLUDED.engine_mode
    RETURNING
        context_id,
        (
            outcome_1m IS NOT NULL
         OR outcome_5m IS NOT NULL
         OR outcome_1h IS NOT NULL
         OR outcome_4h IS NOT NULL
         OR outcome_24h IS NOT NULL
         OR max_favorable IS NOT NULL
         OR max_adverse IS NOT NULL
        ) AS has_any_outcome
),
marked AS (
    UPDATE trading.decision_context_snapshots s
    SET outcome_backfilled = TRUE
    WHERE s.context_id IN (SELECT context_id FROM upserted)
    RETURNING s.context_id
)
SELECT
    (SELECT count(*) FROM upserted)::int AS upserted_rows,
    (SELECT count(*) FROM upserted WHERE has_any_outcome)::int AS rows_with_any_outcome,
    (SELECT count(*) FROM marked)::int AS marked_rows
"""


@dataclass
class BackfillResult:
    engine_modes: list[str]
    batch_size: int
    repair_existing: bool
    dry_run: bool
    upserted_rows: int
    rows_with_any_outcome: int
    marked_rows: int
    elapsed_ms: int


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _resolve_engine_modes(values: list[str] | None) -> list[str]:
    raw: list[str] = []
    if values:
        for value in values:
            raw.extend(_csv(value))
    else:
        raw = _csv(os.environ.get("OPENCLAW_OUTCOME_BACKFILL_ENGINE_MODES", DEFAULT_ENGINE_MODES))
    modes = []
    for mode in raw:
        if mode not in VALID_ENGINE_MODES:
            raise ValueError(f"invalid engine_mode: {mode}")
        if mode not in modes:
            modes.append(mode)
    return modes


def _resolve_dsn(cli_dsn: str | None) -> str | None:
    return cli_dsn or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")


def run_backfill(
    *,
    dsn: str,
    engine_modes: list[str],
    batch_size: int,
    repair_existing: bool,
    dry_run: bool,
) -> BackfillResult:
    try:
        import psycopg2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("psycopg2 is required for outcome_backfiller_live") from exc

    started = time.monotonic()
    conn = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                BACKFILL_SQL,
                {
                    "engine_modes": engine_modes,
                    "batch_size": int(batch_size),
                    "repair_existing": bool(repair_existing),
                },
            )
            row = cur.fetchone() or (0, 0, 0)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return BackfillResult(
            engine_modes=engine_modes,
            batch_size=batch_size,
            repair_existing=repair_existing,
            dry_run=dry_run,
            upserted_rows=int(row[0] or 0),
            rows_with_any_outcome=int(row[1] or 0),
            marked_rows=int(row[2] or 0),
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill live-lane decision_outcomes")
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("OPENCLAW_OUTCOME_BACKFILL_BATCH_SIZE", "2000")),
    )
    parser.add_argument(
        "--repair-existing",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("OPENCLAW_OUTCOME_BACKFILL_REPAIR_EXISTING", "1").lower()
        not in {"0", "false", "no", "off"},
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = _resolve_dsn(args.dsn)
    if not dsn:
        print(json.dumps({"status": "error", "error": "no_database_url"}), file=sys.stderr)
        return 2
    try:
        result = run_backfill(
            dsn=dsn,
            engine_modes=_resolve_engine_modes(args.engine_modes),
            batch_size=max(1, int(args.batch_size)),
            repair_existing=bool(args.repair_existing),
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"status": "ok", **asdict(result)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
