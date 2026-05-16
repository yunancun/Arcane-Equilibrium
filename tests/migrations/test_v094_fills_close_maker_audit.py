"""Static migration tests for V094 close-maker fill audit columns.

Mac dev tests do not apply production SQL. These tests verify the shipped
migration contract statically; Linux PostgreSQL dry-run remains a separate
operator-controlled gate.
Mac dev 測試不套用 production SQL；本檔只靜態驗證 migration contract。
Linux PostgreSQL dry-run 仍是獨立的 operator-controlled gate。
"""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V094_PATH = _SRV_ROOT / "sql" / "migrations" / "V094__fills_close_maker_audit.sql"


def _read_sql() -> str:
    """Read raw V094 SQL / 讀取 V094 SQL 原文。"""
    assert V094_PATH.exists(), f"Migration file missing: {V094_PATH}"
    return V094_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Strip -- comments for stable static assertions / 去除 SQL 行注釋。"""
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    """Normalize SQL text for grep-like checks / 規範化 SQL 文字。"""
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v094_adds_two_hot_columns() -> None:
    """V094 adds exactly the two hot audit columns / 增加兩個 hot audit 欄位。"""
    sql = _normalized_sql()

    assert (
        "alter table trading.fills add column if not exists "
        "close_maker_attempt boolean not null default false"
    ) in sql
    assert (
        "alter table trading.fills add column if not exists "
        "close_maker_fallback_reason text null"
    ) in sql


def test_v094_fallback_reason_check_enum_has_ten_values_not_valid() -> None:
    """Fallback CHECK must be the final 10-value V094 enum / CHECK enum 為 10 值。"""
    sql = _normalized_sql()

    assert "chk_fills_close_maker_fallback_reason_v094" in sql
    assert "add constraint chk_fills_close_maker_fallback_reason_v094" in sql
    assert "not valid" in sql

    for value in (
        "timeout_taker",
        "postonly_reject",
        "cancel_grace_expired",
        "ack_lost",
        "rate_limit_pause_global",
        "rate_limit_backoff_per_symbol",
        "fast_escalate_safety_upgrade",
        "not_attempted_safety_path",
        "engine_shutdown_safety",
        "fallback_to_taker_mandatory",
    ):
        assert f"'{value}'" in sql, f"missing V094 enum value: {value}"


def test_v094_partial_index_targets_attempted_close_maker_fills() -> None:
    """Partial index must serve close_maker_attempt=true scans."""
    sql = _normalized_sql()

    assert "create index if not exists idx_fills_close_maker_attempt_v094" in sql
    assert "on trading.fills (engine_mode, ts desc)" in sql
    assert "where close_maker_attempt = true" in sql


def test_v094_has_guard_a_b_c_and_runtime_reflection_checks() -> None:
    """Guard A/B/C must catch drift and verify index/constraint shape."""
    raw = _read_sql().lower()
    sql = _normalized_sql()

    for guard in ("guard a", "guard b", "guard c"):
        assert guard in raw, f"missing {guard}"

    assert "v094 guard a fail" in sql
    assert "v094 guard b fail" in sql
    assert "v094 guard c fail" in sql
    assert "information_schema.columns" in sql
    assert "pg_get_constraintdef" in sql
    assert "pg_get_indexdef" in sql


def test_v094_is_append_only_no_fill_rewrite() -> None:
    """V094 must not rewrite trading.fills rows / V094 不改寫既有 fill rows。"""
    sql = _normalized_sql()

    for forbidden in (
        "insert into trading.fills",
        "update trading.fills",
        "delete from trading.fills",
        "drop table",
        "drop column",
        "truncate",
    ):
        assert forbidden not in sql, f"forbidden destructive op: {forbidden}"
