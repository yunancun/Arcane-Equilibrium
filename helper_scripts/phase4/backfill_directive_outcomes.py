#!/usr/bin/env python3
"""Backfill directive_executions outcome_* columns from existing result JSONB.

回填 directive_executions 的 outcome_* 欄位（從既存 result JSONB 抽取）。

MODULE_NOTE (EN):
    Phase 4 sub-task 4-03 helper. The 4-02 DirectiveApplier nested outcome
    detail inside the `result` JSONB column before V012 added first-class
    columns. This script extracts known outcome keys from `result` JSONB and
    UPDATEs the corresponding columns where they are still NULL.

    Idempotent: rows whose outcome columns are already populated are skipped.
    Rows with no outcome data in JSONB are left for the Rust OutcomeTracker
    sweep to compute from trading.fills.

MODULE_NOTE (中):
    Phase 4 子任務 4-03 輔助腳本。4-02 DirectiveApplier 在 V012 一級欄位
    存在前，把 outcome 細節塞進 `result` JSONB。本腳本從 JSONB 抽取已知
    outcome key 並 UPDATE 仍為 NULL 的對應欄位。

    冪等：outcome 欄位已填的 row 跳過。JSONB 內無 outcome 的 row 留給 Rust
    OutcomeTracker 從 trading.fills 計算。

Usage / 用法:
    DSN=postgresql://redacted@127.0.0.1/trading_ai \\
        python3 helper_scripts/phase4/backfill_directive_outcomes.py
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _try_import_psycopg2():
    """Lazy psycopg2 import. None on failure. / 延遲 psycopg2 匯入；失敗回 None。"""
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json  # noqa: F401  (validate import)

        return psycopg2
    except ImportError:
        return None


def extract_outcome_from_jsonb(result_jsonb: Optional[dict]) -> dict:
    """Extract known outcome keys from a result JSONB blob.

    從 result JSONB 抽取已知的 outcome key。

    Returns a dict with up to 5 keys:
        outcome_pnl_1h, outcome_pnl_4h, outcome_pnl_24h, outcome_pnl_7d, outcome_sharpe_24h
    Missing keys are omitted (caller can spread into UPDATE).
    """
    if not isinstance(result_jsonb, dict):
        return {}
    out: dict[str, float] = {}

    # Direct keys at top level (4-02 stored a flat outcome dict here).
    # 頂層直接 key（4-02 存的是扁平 outcome dict）。
    for db_col, json_keys in (
        ("outcome_pnl_1h", ("pnl_1h", "outcome_pnl_1h")),
        ("outcome_pnl_4h", ("pnl_4h", "outcome_pnl_4h")),
        ("outcome_pnl_24h", ("pnl_24h", "outcome_pnl_24h")),
        ("outcome_pnl_7d", ("pnl_7d", "outcome_pnl_7d")),
        ("outcome_sharpe_24h", ("sharpe_24h", "outcome_sharpe_24h")),
    ):
        for k in json_keys:
            if k in result_jsonb:
                v = result_jsonb[k]
                if isinstance(v, (int, float)):
                    out[db_col] = float(v)
                    break

    # Nested under "outcome": {...} (alternative shape).
    # 巢狀 "outcome": {...} 結構（替代）。
    nested = result_jsonb.get("outcome")
    if isinstance(nested, dict):
        for db_col, json_keys in (
            ("outcome_pnl_1h", ("pnl_1h",)),
            ("outcome_pnl_4h", ("pnl_4h",)),
            ("outcome_pnl_24h", ("pnl_24h",)),
            ("outcome_pnl_7d", ("pnl_7d",)),
            ("outcome_sharpe_24h", ("sharpe_24h",)),
        ):
            if db_col not in out:
                for k in json_keys:
                    if k in nested and isinstance(nested[k], (int, float)):
                        out[db_col] = float(nested[k])
                        break
    return out


def backfill(dsn: Optional[str] = None, dry_run: bool = False) -> int:
    """Walk pending directive_executions and backfill outcome columns from JSONB.

    Returns the number of rows updated. Fail-soft: returns 0 on any error.

    Args:
        dsn: PostgreSQL DSN. If None, reads from env DSN.
        dry_run: If True, do not commit; just log what would be updated.

    走過 pending directive_executions 並從 JSONB 回填 outcome 欄位。
    返回更新的 row 數。fail-soft：任何錯誤回 0。
    """
    if dsn is None:
        dsn = os.environ.get("DSN") or os.environ.get("OPENCLAW_DATABASE_URL")
    if not dsn:
        logger.warning("backfill: DSN not provided, nothing to do")
        return 0

    psycopg2 = _try_import_psycopg2()
    if psycopg2 is None:
        logger.warning("backfill: psycopg2 unavailable, skipping")
        return 0

    try:
        conn = psycopg2.connect(dsn)
    except Exception as e:
        logger.warning("backfill: connect failed: %s", e)
        return 0

    updated = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT execution_id, result
                FROM learning.directive_executions
                WHERE outcome_computed_at IS NULL
                  AND result IS NOT NULL
                ORDER BY ts ASC
                LIMIT 1000
                """
            )
            rows = cur.fetchall()
            for execution_id, result_jsonb in rows:
                outcome = extract_outcome_from_jsonb(result_jsonb)
                if not outcome:
                    continue
                if dry_run:
                    logger.info(
                        "would update execution_id=%s with %s", execution_id, outcome
                    )
                    updated += 1
                    continue

                # Build dynamic UPDATE — column names are static (no SQL injection).
                # 動態 UPDATE — column 名是靜態的（無 SQL 注入風險）。
                set_clauses = []
                values: list[Any] = []
                for col, val in outcome.items():
                    set_clauses.append(f"{col} = %s")
                    values.append(val)
                # Stamp computed_at so the row is no longer "pending".
                # Stamp computed_at 使該 row 不再 pending。
                set_clauses.append("outcome_computed_at = NOW()")
                values.append(execution_id)
                sql = (
                    "UPDATE learning.directive_executions SET "
                    + ", ".join(set_clauses)
                    + " WHERE execution_id = %s"
                )
                try:
                    cur.execute(sql, values)
                    updated += 1
                except Exception as e:
                    logger.warning(
                        "backfill: update execution_id=%s failed: %s", execution_id, e
                    )
                    conn.rollback()
                    continue
        if not dry_run:
            conn.commit()
    except Exception as e:
        logger.warning("backfill: query failed: %s", e)
    finally:
        conn.close()
    logger.info("backfill: updated %d rows (dry_run=%s)", updated, dry_run)
    return updated


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Backfill directive_executions outcome columns")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN (overrides env)")
    args = parser.parse_args(argv)

    n = backfill(dsn=args.dsn, dry_run=args.dry_run)
    print(f"backfill_directive_outcomes: updated {n} rows (dry_run={args.dry_run})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
