"""Static migration tests for V095 market.liquidations item identity.

Mac dev tests do not apply production SQL. These assertions pin the migration
shape so the Linux PostgreSQL dry-run can be done later under operator control.
Mac dev 測試不套用 production SQL；本檔只靜態驗證 migration contract。
"""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V095_PATH = _SRV_ROOT / "sql" / "migrations" / "V095__market_liquidations_identity.sql"


def _read_sql() -> str:
    """Read raw V095 SQL / 讀取 V095 SQL 原文。"""
    assert V095_PATH.exists(), f"Migration file missing: {V095_PATH}"
    return V095_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Strip -- comments for stable static assertions / 去除 SQL 行注釋。"""
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    """Normalize SQL text for grep-like checks / 規範化 SQL 文字。"""
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v095_targets_market_liquidations_identity() -> None:
    """V095 must correct the exact market.liquidations identity surface."""
    sql = _normalized_sql()

    assert "alter table market.liquidations" in sql
    assert "primary key (symbol, ts, side, qty, price)" in sql
    assert "array['symbol', 'ts', 'side']" in sql
    assert "array['symbol', 'ts', 'side', 'qty', 'price']" in sql


def test_v095_drops_only_exact_old_primary_key_shape() -> None:
    """Old PK may be dropped only after exact column-shape reflection."""
    sql = _normalized_sql()

    assert "drop constraint" in sql
    assert "v_pk_cols = array['symbol', 'ts', 'side']" in sql
    assert "v_pk_cols = array['symbol', 'ts', 'side', 'qty', 'price']" in sql
    assert "refusing to drop unexpected primary key" in sql


def test_v095_adds_side_check_not_valid() -> None:
    """Side CHECK must be Buy/Sell and NOT VALID."""
    sql = _normalized_sql()

    assert "chk_market_liquidations_side_v095" in sql
    assert "check (side in ('buy', 'sell')) not valid" in sql


def test_v095_has_guard_a_b_c_and_reflection_checks() -> None:
    """Guard A/B/C must catch table, type, PK, and CHECK drift."""
    raw = _read_sql().lower()
    sql = _normalized_sql()

    for guard in ("guard a", "guard b", "guard c"):
        assert guard in raw, f"missing {guard}"

    assert "v095 guard a fail" in sql
    assert "v095 guard b fail" in sql
    assert "v095 guard c fail" in sql
    assert "information_schema.columns" in sql
    assert "pg_get_constraintdef" in sql
    assert "pg_constraint" in sql


def test_v095_is_idempotent_on_repeat() -> None:
    """Repeat runs should skip existing new PK and CHECK."""
    sql = _normalized_sql()

    assert "already has item-level primary key; skipping" in sql
    assert "already present; skipping" in sql
    assert "not exists" in sql


def test_v095_no_destructive_table_or_data_rewrite() -> None:
    """V095 must not drop tables, truncate, or rewrite existing rows."""
    sql = _normalized_sql()

    for forbidden in (
        "drop table",
        "truncate",
        "delete from market.liquidations",
        "update market.liquidations",
        "insert into market.liquidations",
        "alter column",
        "drop column",
    ):
        assert forbidden not in sql, f"forbidden destructive op: {forbidden}"
