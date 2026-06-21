#!/usr/bin/env python3
"""Read-only counterfactual audit for cost-gate rejections.

The normal outcome path is:

    decision_context_snapshots -> decision_outcomes

That path is useful when labels are caught up, but it can lag large signal
bursts. This audit measures rejected cost-gate decisions directly from
``learning.decision_features`` and future ``market.klines`` prices, so the
operator can see whether blocked signals later moved in the blocked direction.

No PG writes, no order placement, no risk/config mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper_scripts.lib.pg_connect import connect_report_pg  # noqa: E402


VALID_ENGINE_MODES = {"paper", "demo", "live_demo", "live"}


@dataclass(frozen=True)
class AuditConfig:
    engine_modes: tuple[str, ...]
    lookback_hours: int
    horizon_minutes: int
    limit: int
    friction_bps: float
    strategy: str | None = None
    symbol: str | None = None
    side: int | None = None


def side_to_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"buy", "long", "1"}:
        return 1
    if value in {"sell", "short", "-1"}:
        return -1
    raise ValueError("--side must be Buy/Long/1 or Sell/Short/-1")


def validate_config(cfg: AuditConfig) -> None:
    if not cfg.engine_modes:
        raise ValueError("at least one engine mode is required")
    bad = [m for m in cfg.engine_modes if m not in VALID_ENGINE_MODES]
    if bad:
        raise ValueError(f"invalid engine mode(s): {bad}")
    if cfg.lookback_hours < 1 or cfg.lookback_hours > 24 * 30:
        raise ValueError("--lookback-hours must be in [1, 720]")
    if cfg.horizon_minutes < 1 or cfg.horizon_minutes > 24 * 60:
        raise ValueError("--horizon-minutes must be in [1, 1440]")
    if cfg.limit < 1 or cfg.limit > 500_000:
        raise ValueError("--limit must be in [1, 500000]")
    if cfg.friction_bps < 0 or cfg.friction_bps > 200:
        raise ValueError("--friction-bps must be in [0, 200]")


def build_coverage_sql() -> str:
    return """
WITH rv AS (
    SELECT rv.*
    FROM trading.risk_verdicts rv
    WHERE rv.engine_mode = ANY(%s)
      AND rv.ts >= now() - (%s::int * interval '1 hour')
      AND rv.reason LIKE 'cost_gate%%'
),
features AS (
    SELECT f.*
    FROM learning.decision_features f
    WHERE f.engine_mode = ANY(%s)
      AND f.ts >= now() - (%s::int * interval '1 hour')
      AND f.reject_reason_code LIKE 'cost_gate%%'
)
SELECT
    (SELECT count(*)::bigint FROM rv) AS risk_verdicts,
    (SELECT max(ts) FROM rv) AS latest_risk_verdict_ts,
    (
      SELECT count(*)::bigint
      FROM rv
      JOIN trading.intents i
        ON i.intent_id = rv.intent_id
       AND i.engine_mode = rv.engine_mode
    ) AS risk_verdicts_joined_intents,
    (SELECT count(*)::bigint FROM features) AS decision_features,
    (
      SELECT count(*)::bigint
      FROM features f
      JOIN trading.decision_context_snapshots d
        ON d.context_id = f.context_id
    ) AS features_joined_contexts,
    (
      SELECT count(*)::bigint
      FROM features f
      JOIN trading.decision_outcomes o
        ON o.context_id = f.context_id
    ) AS features_joined_outcomes,
    (
      SELECT count(*)::bigint
      FROM trading.decision_context_snapshots d
      WHERE d.outcome_backfilled = false
        AND d.ts < now() - interval '25 hours'
    ) AS decision_context_old_pending
"""


def build_counterfactual_sql(cfg: AuditConfig) -> tuple[str, list[Any]]:
    validate_config(cfg)
    where = [
        "f.engine_mode = ANY(%s)",
        "f.ts >= now() - (%s::int * interval '1 hour')",
        "f.ts < now() - (%s::int * interval '1 minute')",
        "f.reject_reason_code LIKE 'cost_gate%%'",
    ]
    params: list[Any] = [list(cfg.engine_modes), cfg.lookback_hours, cfg.horizon_minutes]
    if cfg.strategy:
        where.append("f.strategy_name = %s")
        params.append(cfg.strategy)
    if cfg.symbol:
        where.append("f.symbol = %s")
        params.append(cfg.symbol)
    if cfg.side is not None:
        where.append("f.side = %s")
        params.append(cfg.side)
    params.extend([cfg.limit, cfg.horizon_minutes, cfg.friction_bps, cfg.friction_bps])

    sql = f"""
WITH base AS (
    SELECT f.ts, f.context_id, f.engine_mode, f.strategy_name, f.symbol,
           f.side, f.reject_reason_code
    FROM learning.decision_features f
    WHERE {' AND '.join(where)}
    ORDER BY f.ts DESC
    LIMIT %s
),
priced AS (
    SELECT b.*,
           COALESCE(d.last_price::float8, k0.close::float8) AS entry_px,
           kh.close::float8 AS future_px,
           (d.context_id IS NOT NULL) AS has_context
    FROM base b
    LEFT JOIN trading.decision_context_snapshots d
      ON d.context_id = b.context_id
    LEFT JOIN LATERAL (
        SELECT k.close
        FROM market.klines k
        WHERE k.symbol = b.symbol
          AND k.timeframe = '1m'
          AND k.ts <= b.ts
        ORDER BY k.ts DESC
        LIMIT 1
    ) k0 ON TRUE
    LEFT JOIN LATERAL (
        SELECT k.close
        FROM market.klines k
        WHERE k.symbol = b.symbol
          AND k.timeframe = '1m'
          AND k.ts >= b.ts + (%s::int * interval '1 minute')
        ORDER BY k.ts ASC
        LIMIT 1
    ) kh ON TRUE
),
scored AS (
    SELECT *,
           ((future_px - entry_px) / NULLIF(entry_px, 0)) * 10000.0 * side
             AS directional_gross_bps
    FROM priced
    WHERE entry_px > 0
      AND future_px > 0
)
SELECT
    strategy_name,
    symbol,
    CASE WHEN side = 1 THEN 'Buy' ELSE 'Sell' END AS side,
    reject_reason_code,
    count(*)::bigint AS n,
    count(*) FILTER (WHERE has_context)::bigint AS joined_contexts,
    min(ts) AS min_ts,
    max(ts) AS max_ts,
    round(avg(directional_gross_bps)::numeric, 4) AS avg_gross_bps,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY directional_gross_bps)::numeric, 4)
      AS p50_gross_bps,
    round(percentile_cont(0.9) WITHIN GROUP (ORDER BY directional_gross_bps)::numeric, 4)
      AS p90_gross_bps,
    round(avg(directional_gross_bps - %s)::numeric, 4) AS avg_net_bps,
    round((avg((directional_gross_bps > 0)::int) * 100)::numeric, 2)
      AS gross_positive_pct,
    round((avg((directional_gross_bps > %s)::int) * 100)::numeric, 2)
      AS net_positive_pct
FROM scored
GROUP BY strategy_name, symbol, side, reject_reason_code
ORDER BY n DESC, strategy_name, symbol, side
"""
    return sql, params


def fetch_coverage(conn: Any, cfg: AuditConfig) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            build_coverage_sql(),
            [list(cfg.engine_modes), cfg.lookback_hours, list(cfg.engine_modes), cfg.lookback_hours],
        )
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
    return dict(zip(cols, row)) if row else {}


def fetch_counterfactual_rows(conn: Any, cfg: AuditConfig) -> list[dict[str, Any]]:
    sql, params = build_counterfactual_sql(cfg)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(
    cfg: AuditConfig,
    coverage: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Cost Gate Reject Counterfactual Audit",
        "",
        f"- Generated: `{generated}`",
        f"- Engine modes: `{','.join(cfg.engine_modes)}`",
        f"- Lookback: `{cfg.lookback_hours}` hours",
        f"- Horizon: `{cfg.horizon_minutes}` minutes",
        f"- Friction: `{cfg.friction_bps:.2f}` bps",
        f"- Limit: `{cfg.limit}` latest rejected feature rows before grouping",
        "- Boundary: read-only PG SELECT; no order, config, risk, auth, or runtime mutation.",
        "- Interpretation: kline counterfactual uses future market close, not actual queue fill.",
        "",
        "## Coverage",
        "",
        "| metric | value |",
        "|---|---:|",
    ]
    for key in [
        "risk_verdicts",
        "latest_risk_verdict_ts",
        "risk_verdicts_joined_intents",
        "decision_features",
        "features_joined_contexts",
        "features_joined_outcomes",
        "decision_context_old_pending",
    ]:
        lines.append(f"| {key} | {_fmt(coverage.get(key))} |")

    lines.extend(
        [
            "",
            "## Counterfactual",
            "",
            "| strategy | symbol | side | reason | n | ctx | avg_gross | p50 | p90 | avg_net | gross+% | net+% | max_ts |",
            "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            f"{row['strategy_name']} | {row['symbol']} | {row['side']} | "
            f"{row['reject_reason_code']} | {row['n']} | {row['joined_contexts']} | "
            f"{_fmt(row['avg_gross_bps'])} | {_fmt(row['p50_gross_bps'])} | "
            f"{_fmt(row['p90_gross_bps'])} | {_fmt(row['avg_net_bps'])} | "
            f"{_fmt(row['gross_positive_pct'])} | {_fmt(row['net_positive_pct'])} | "
            f"{_fmt(row['max_ts'])} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-mode", action="append", default=["demo", "live_demo"])
    parser.add_argument("--lookback-hours", type=int, default=168)
    parser.add_argument("--horizon-minutes", type=int, default=60)
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--friction-bps", type=float, default=4.0)
    parser.add_argument("--strategy")
    parser.add_argument("--symbol")
    parser.add_argument("--side")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = AuditConfig(
        engine_modes=tuple(args.engine_mode),
        lookback_hours=args.lookback_hours,
        horizon_minutes=args.horizon_minutes,
        limit=args.limit,
        friction_bps=args.friction_bps,
        strategy=args.strategy,
        symbol=args.symbol,
        side=side_to_int(args.side),
    )
    validate_config(cfg)
    conn = connect_report_pg(
        "cost_gate_reject_counterfactual",
        statement_timeout_ms_default=180_000,
    )
    try:
        # connect_report_pg sets statement_timeout with a normal SET, which
        # opens a psycopg2 transaction. End that setup transaction before
        # switching the session into read-only autocommit mode.
        conn.rollback()
        conn.set_session(readonly=True, autocommit=True)
        coverage = fetch_coverage(conn, cfg)
        rows = fetch_counterfactual_rows(conn, cfg)
    finally:
        conn.close()
    report = render_markdown(cfg, coverage, rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
