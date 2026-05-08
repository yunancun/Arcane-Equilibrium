"""Static migration tests for V073 edge snapshot cycle writer contract."""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V073_PATH = (
    _SRV_ROOT
    / "sql"
    / "migrations"
    / "V073__edge_estimate_snapshots_cycle_writer_contract.sql"
)


def _read_sql() -> str:
    assert V073_PATH.exists(), f"Migration file missing: {V073_PATH}"
    return V073_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v073_guards_v059_table_columns() -> None:
    sql = _normalized_sql()

    assert "to_regclass('learning.edge_estimate_snapshots')" in sql
    assert "v073 guard a fail: learning.edge_estimate_snapshots missing" in sql
    for column in (
        "asof_ts",
        "source_tier",
        "config_hash",
        "strategy_hash",
        "scanner_config_hash",
        "symbol",
        "strategy",
        "regime_key",
        "cell_key",
        "estimate_payload_hash",
        "estimate_payload_jsonb",
        "is_deprecated_at_asof",
        "deprecated_reason",
        "retention_until",
    ):
        assert f"'{column}'" in sql


def test_v073_guards_primary_key_retention_and_symbol_index() -> None:
    sql = _normalized_sql()

    assert "pg_get_constraintdef(c.oid) like '%asof_ts%'" in sql
    assert "pg_get_constraintdef(c.oid) like '%strategy_hash%'" in sql
    assert "pg_get_constraintdef(c.oid) like '%scanner_config_hash%'" in sql
    assert "pg_get_constraintdef(c.oid) like '%cell_key%'" in sql
    assert "pg_get_constraintdef(c.oid) like '%retention_until%'" in sql
    assert "pg_get_constraintdef(c.oid) like '%75 days%'" in sql
    assert "idx_edge_estimate_snapshots_symbol_strategy_asof" in sql
    assert "v073 guard b fail: edge snapshot contract incomplete" in sql
    assert "v073 guard pass: v059 edge_estimate_snapshots contract supports cycle writer" in sql


def test_v073_migration_is_contract_guard_not_scheduler() -> None:
    sql = _normalized_sql()

    for forbidden in (
        "insert into",
        "update ",
        "delete from",
        "create table",
        "alter table",
        "add_job",
        "cron.schedule",
    ):
        assert forbidden not in sql
