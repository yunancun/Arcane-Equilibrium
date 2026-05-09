#!/usr/bin/env python3
"""Read-only 7d audit for frozen blocked_symbols cells.

This report deliberately separates two evidence types:
- realized fill PnL for blocked cells that still had fills in the window
- rejected-intent outcome coverage for cells rejected by blocked_symbols

If rejected rows have no decision_outcomes, the script reports lack of
counterfactual power instead of inventing a would-have-traded PnL.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = ROOT / "docs" / "governance_dev" / "strategy_blocked_symbols_freeze.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper_scripts.db.passive_wait_healthcheck.db import _get_conn  # noqa: E402


@dataclass(frozen=True)
class BlockedCell:
    strategy: str
    symbol: str


@dataclass(frozen=True)
class AuditRow:
    strategy: str
    symbol: str
    fills: int
    entries: int
    exits: int
    net_pnl_usdt: float
    gross_pnl_usdt: float
    fees_usdt: float
    rejected_n: int
    rejected_outcome_n: int
    avg_outcome_24h: float | None
    first_seen: str
    last_seen: str

    @property
    def evidence_power(self) -> str:
        if self.rejected_n > 0 and self.rejected_outcome_n == 0:
            return "no_rejected_outcome_labels"
        if self.rejected_outcome_n > 0:
            return "rejected_counterfactual_available"
        if self.fills > 0:
            return "realized_fill_only"
        return "no_7d_sample"


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_cells(registry: dict) -> list[BlockedCell]:
    cells: list[BlockedCell] = []
    for strategy, payload in registry["frozen_cells"].items():
        for symbol in payload["symbols"]:
            cells.append(BlockedCell(strategy=strategy, symbol=symbol))
    return cells


def _values_sql(cells: Iterable[BlockedCell]) -> tuple[str, list[str]]:
    params: list[str] = []
    placeholders: list[str] = []
    for cell in cells:
        placeholders.append("(%s, %s)")
        params.extend([cell.strategy, cell.symbol])
    if not placeholders:
        raise ValueError("at least one blocked cell is required")
    return ", ".join(placeholders), params


def fetch_audit_rows(*, days: int, statement_timeout_ms: int) -> list[AuditRow]:
    registry = load_registry()
    cells = iter_cells(registry)
    values_sql, cell_params = _values_sql(cells)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))

        fill_sql = f"""
WITH cells(strategy_name, symbol) AS (VALUES {values_sql})
SELECT c.strategy_name,
       c.symbol,
       COUNT(f.fill_id)::int AS fills,
       COUNT(f.fill_id) FILTER (WHERE COALESCE(f.exit_source, '') = '')::int AS entries,
       COUNT(f.fill_id) FILTER (WHERE COALESCE(f.exit_source, '') <> '')::int AS exits,
       COALESCE(SUM(COALESCE(f.realized_pnl, 0) - ABS(COALESCE(f.fee, 0))), 0)::float8 AS net_pnl_usdt,
       COALESCE(SUM(COALESCE(f.realized_pnl, 0)), 0)::float8 AS gross_pnl_usdt,
       COALESCE(SUM(ABS(COALESCE(f.fee, 0))), 0)::float8 AS fees_usdt,
       MIN(f.ts)::text AS first_seen,
       MAX(f.ts)::text AS last_seen
FROM cells c
LEFT JOIN trading.fills f
  ON f.strategy_name = c.strategy_name
 AND f.symbol = c.symbol
 AND f.engine_mode IN ('demo', 'live_demo')
 AND f.ts > now() - (%s * interval '1 day')
GROUP BY c.strategy_name, c.symbol
ORDER BY c.strategy_name, c.symbol
"""
        cur.execute(fill_sql, [*cell_params, days])
        fill_rows = {
            (str(r[0]), str(r[1])): {
                "fills": int(r[2] or 0),
                "entries": int(r[3] or 0),
                "exits": int(r[4] or 0),
                "net_pnl_usdt": float(r[5] or 0.0),
                "gross_pnl_usdt": float(r[6] or 0.0),
                "fees_usdt": float(r[7] or 0.0),
                "first_seen": str(r[8] or ""),
                "last_seen": str(r[9] or ""),
            }
            for r in cur.fetchall()
        }

        reject_sql = f"""
WITH cells(strategy_name, symbol) AS (VALUES {values_sql})
SELECT c.strategy_name,
       c.symbol,
       COUNT(rv.verdict_id)::int AS rejected_n,
       COUNT(o.context_id)::int AS rejected_outcome_n,
       AVG(o.outcome_24h)::float8 AS avg_outcome_24h
FROM cells c
LEFT JOIN trading.risk_verdicts rv
  ON rv.symbol = c.symbol
 AND rv.engine_mode IN ('demo', 'live_demo')
 AND rv.ts > now() - (%s * interval '1 day')
 AND rv.reason = c.symbol || ' blocked by per_strategy.' || c.strategy_name || '.blocked_symbols'
LEFT JOIN trading.decision_outcomes o
  ON o.context_id = rv.context_id
GROUP BY c.strategy_name, c.symbol
ORDER BY c.strategy_name, c.symbol
"""
        cur.execute(reject_sql, [*cell_params, days])
        reject_rows = {
            (str(r[0]), str(r[1])): {
                "rejected_n": int(r[2] or 0),
                "rejected_outcome_n": int(r[3] or 0),
                "avg_outcome_24h": float(r[4]) if r[4] is not None else None,
            }
            for r in cur.fetchall()
        }
    finally:
        conn.close()

    rows: list[AuditRow] = []
    for cell in sorted(cells, key=lambda c: (c.strategy, c.symbol)):
        fill = fill_rows.get((cell.strategy, cell.symbol), {})
        reject = reject_rows.get((cell.strategy, cell.symbol), {})
        rows.append(
            AuditRow(
                strategy=cell.strategy,
                symbol=cell.symbol,
                fills=int(fill.get("fills", 0)),
                entries=int(fill.get("entries", 0)),
                exits=int(fill.get("exits", 0)),
                net_pnl_usdt=float(fill.get("net_pnl_usdt", 0.0)),
                gross_pnl_usdt=float(fill.get("gross_pnl_usdt", 0.0)),
                fees_usdt=float(fill.get("fees_usdt", 0.0)),
                rejected_n=int(reject.get("rejected_n", 0)),
                rejected_outcome_n=int(reject.get("rejected_outcome_n", 0)),
                avg_outcome_24h=reject.get("avg_outcome_24h"),
                first_seen=str(fill.get("first_seen", "")),
                last_seen=str(fill.get("last_seen", "")),
            )
        )
    return rows


def render_markdown(rows: list[AuditRow], *, days: int) -> str:
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# P2-AUDIT-VERIFY-5 Blocked Symbols Freeze",
        "",
        f"- Generated: `{generated}`",
        f"- Window: last `{days}` days, `engine_mode IN ('demo','live_demo')`",
        "- Boundary: read-only DB SELECT; no config change, DB write, rebuild, restart, or live auth mutation.",
        "- Interpretation: fill PnL is observed realized data. Rejected rows only become true counterfactual evidence when `trading.decision_outcomes` labels exist.",
        "",
        "| strategy | symbol | fills | entries | exits | net_pnl_usdt | rejected_n | rejected_outcome_n | avg_outcome_24h | evidence_power |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        avg_outcome = "n/a" if row.avg_outcome_24h is None else f"{row.avg_outcome_24h:.6f}"
        lines.append(
            "| "
            f"{row.strategy} | {row.symbol} | {row.fills} | {row.entries} | "
            f"{row.exits} | {row.net_pnl_usdt:.4f} | {row.rejected_n} | "
            f"{row.rejected_outcome_n} | {avg_outcome} | {row.evidence_power} |"
        )

    no_outcome = sum(1 for row in rows if row.rejected_n > 0 and row.rejected_outcome_n == 0)
    sampled = sum(1 for row in rows if row.fills > 0)
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Frozen cells audited: `{len(rows)}`",
            f"- Cells with observed fills in window: `{sampled}`",
            f"- Cells with blocked rejections but zero outcome labels: `{no_outcome}`",
            "- Conclusion: keep the blocklist frozen. New blocked cells need an RFC plus outcome-backed counterfactual/DSR-PBO evidence before source config mutation.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--statement-timeout-ms", type=int, default=5000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = fetch_audit_rows(
        days=args.days,
        statement_timeout_ms=args.statement_timeout_ms,
    )
    markdown = render_markdown(rows, days=args.days)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
