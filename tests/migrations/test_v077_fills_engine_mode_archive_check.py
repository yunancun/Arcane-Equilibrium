"""Static migration tests for V077 fills engine_mode archive CHECK."""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V077_PATH = _SRV_ROOT / "sql" / "migrations" / "V077__fills_engine_mode_archive_check.sql"


def _read_sql() -> str:
    assert V077_PATH.exists(), f"Migration file missing: {V077_PATH}"
    return V077_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v077_guards_fills_table_and_required_columns() -> None:
    sql = _normalized_sql()

    assert "to_regclass('trading.fills')" in sql
    assert "v077 guard a fail: trading.fills missing" in sql
    assert "table_schema = 'trading'" in sql
    assert "table_name = 'fills'" in sql
    assert "column_name = 'engine_mode'" in sql
    assert "data_type = 'text'" in sql
    assert "is_nullable = 'no'" in sql
    assert "column_name = 'ts'" in sql
    assert "data_type = 'timestamp with time zone'" in sql


def test_v077_accepts_only_canonical_modes_plus_bounded_archive_label() -> None:
    sql = _normalized_sql()

    for mode in ("paper", "demo", "live", "live_demo"):
        assert f"'{mode}'" in sql

    assert "engine_mode = 'demo_archive_20260418'" in sql
    assert "ts < timestamptz '2026-04-18 22:00:00+00'" in sql
    assert "v077 guard b fail: trading.fills has unsupported engine_mode rows" in sql


def test_v077_adds_idempotent_named_check_constraint() -> None:
    sql = _normalized_sql()

    assert "chk_fills_engine_mode_known_values" in sql
    assert "pg_get_constraintdef(oid)" in sql
    assert "add constraint chk_fills_engine_mode_known_values" in sql
    assert "not valid" in sql
    assert "validate constraint chk_fills_engine_mode_known_values" in sql
    assert "v077 guard c fail" in sql
    assert "v077: added and validated chk_fills_engine_mode_known_values" in sql


def test_v077_does_not_rewrite_existing_fill_rows() -> None:
    sql = _normalized_sql()

    for forbidden in (
        "insert into",
        "update ",
        "delete from",
        "drop table",
        "drop constraint",
        "create table",
    ):
        assert forbidden not in sql
