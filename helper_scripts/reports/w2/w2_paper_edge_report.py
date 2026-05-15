#!/usr/bin/env python3
"""W2 legacy paper edge / Stage 0R diagnostic report CLI 整合層。

MODULE_NOTE:
    本模組是 W2 A4-C BTC→Alt Lead-Lag spec v1.2 §7.1 report 的 CLI 入口。
    AMD-2026-05-15-01 後，輸出降級為 Stage 0R diagnostic/read-only packet，
    只能表達 `eligible_for_demo_canary=true/false`，不得稱 Stage 1 PASS 或
    promotion。只負責 argparse、read-only PG query、metrics→render 編排與
    報告輸出；統計公式、渲染、smoke fixture 分別在 sibling modules。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

try:
    from .w2_paper_edge_metrics import (
        DEFAULT_COHORT,
        DEFAULT_WINDOW_DAYS,
        compute_per_symbol_metrics,
        compute_pooled_metrics,
    )
    from .w2_paper_edge_render import render_markdown
    from .w2_paper_edge_smoke import run_smoke_test
except ImportError:
    from w2_paper_edge_metrics import (  # type: ignore
        DEFAULT_COHORT,
        DEFAULT_WINDOW_DAYS,
        compute_per_symbol_metrics,
        compute_pooled_metrics,
    )
    from w2_paper_edge_render import render_markdown  # type: ignore
    from w2_paper_edge_smoke import run_smoke_test  # type: ignore


def _repo_root() -> Path:
    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get("OPENCLAW_SRV_ROOT")
    if base:
        return Path(base)
    return Path(__file__).resolve().parents[3]


def _get_conn():
    import psycopg2  # type: ignore

    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


def _read_counterfactual_sql() -> str:
    sql_path = _repo_root() / "sql" / "queries" / "w2_btc_alt_lead_lag_counterfactual.sql"
    if not sql_path.exists():
        raise FileNotFoundError(
            f"counterfactual SQL not found at {sql_path}; "
            "expected sql/queries/w2_btc_alt_lead_lag_counterfactual.sql"
        )
    return sql_path.read_text(encoding="utf-8")


def _parse_cohort(arg: Optional[str]) -> tuple[str, ...]:
    if not arg:
        return DEFAULT_COHORT
    return tuple(s.strip().upper() for s in arg.split(",") if s.strip())


def fetch_rows_from_pg(
    conn,
    window_days: int,
    cohort: Sequence[str],
) -> list[dict]:
    sql_text = _read_counterfactual_sql()
    with conn.cursor() as cur:
        cur.execute(
            sql_text,
            {
                "window_days": window_days,
                "cohort_symbols": list(cohort),
            },
        )
        col_names = [d[0] for d in cur.description]
        return [dict(zip(col_names, row)) for row in cur.fetchall()]


def build_report_markdown(rows: list[dict], window_days: int, cohort: Sequence[str]) -> str:
    pooled = compute_pooled_metrics(rows, primary_window_secs=120)
    per_symbol = compute_per_symbol_metrics(rows, primary_window_secs=120)
    return render_markdown(
        pooled=pooled,
        per_symbol=per_symbol,
        window_days=window_days,
        cohort=cohort,
        timestamp=datetime.now(timezone.utc),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="W2 A4-C BTC→Alt Lead-Lag — Stage 0R diagnostic report generator"
    )
    parser.add_argument(
        "--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
        help=f"diagnostic/replay evidence window (default {DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--cohort", type=str, default=None,
        help="comma-separated cohort symbols (default 7-symbol cohort per spec §2.2)",
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="output markdown path (default docs/CCAgentWorkSpace/PA/workspace/reports/<today>--w2_paper_edge_report.md)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print to stdout only, do not write file",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="run smoke test (3 mock case, no PG), exit 0 PASS / 1 FAIL",
    )
    args = parser.parse_args()

    if args.smoke_test:
        return run_smoke_test()

    cohort = _parse_cohort(args.cohort)
    window_days = max(1, args.window_days)

    try:
        conn = _get_conn()
    except Exception as e:  # noqa: BLE001
        print(f"[FATAL] DB connect failed: {e}", file=sys.stderr)
        return 2

    try:
        rows = fetch_rows_from_pg(conn, window_days, cohort)
    finally:
        conn.close()

    print(f"[INFO] fetched {len(rows)} counterfactual rows over {window_days}d "
          f"for {len(cohort)} cohort symbols", file=sys.stderr)

    md = build_report_markdown(rows, window_days, cohort)
    if args.dry_run:
        print(md)
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = (
        Path(args.out)
        if args.out
        else _repo_root() / "docs" / "CCAgentWorkSpace" / "PA" / "workspace"
            / "reports" / f"{today}--w2_paper_edge_report.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
