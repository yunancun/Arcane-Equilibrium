"""Static migration tests for V076 Guard A retrofit."""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V076_PATH = _SRV_ROOT / "sql" / "migrations" / "V076__guard_v062_v063_v065.sql"


def _read_sql() -> str:
    assert V076_PATH.exists(), f"Migration file missing: {V076_PATH}"
    return V076_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v076_migration_is_read_only_guard() -> None:
    sql = _normalized_sql()

    for forbidden in (
        "alter table",
        "create table",
        "create index",
        "drop table",
        "drop index",
        "insert into",
        "update ",
        "delete from",
    ):
        assert forbidden not in sql

    assert "do $$" in sql
    assert "raise notice 'v076 guard a pass: v062/v063/v065 prerequisites verified'" in sql


def test_v076_guards_v062_scanner_opportunity_decays() -> None:
    sql = _normalized_sql()

    assert "to_regclass('trading.scanner_opportunity_decays')" in sql
    assert "v076 guard a fail: v062 trading.scanner_opportunity_decays missing" in sql
    for column in (
        "ts",
        "decay_id",
        "scan_id",
        "symbol",
        "authority_mode",
        "reason",
        "has_open_position",
        "position_review_required",
        "auto_close_allowed",
        "evidence",
        "payload",
    ):
        assert f"'{column}'" in sql

    assert "data_type = 'boolean'" in sql
    assert "column_default ilike '%false%'" in sql
    assert "to_regclass('trading.idx_scanner_opportunity_decays_ts')" in sql
    assert "to_regclass('trading.idx_scanner_opportunity_decays_scan_id')" in sql
    assert "to_regclass('trading.idx_scanner_opportunity_decays_symbol_ts')" in sql


def test_v076_guards_v063_market_tickers_funding_rate() -> None:
    sql = _normalized_sql()

    assert "to_regclass('market.market_tickers')" in sql
    assert "v076 guard a fail: v002 market.market_tickers missing before v063" in sql
    assert "column_name = 'funding_rate'" in sql
    assert "data_type = 'real'" in sql
    assert "v076 guard a fail: v063 market.market_tickers.funding_rate missing or not real" in sql


def test_v076_guards_v065_openclaw_ledger_tables_and_columns() -> None:
    sql = _normalized_sql()

    for table in (
        "openclaw.proposals",
        "openclaw.approval_decisions",
        "openclaw.channel_events",
    ):
        assert f"to_regclass('{table}')" in sql

    for column in (
        "proposal_id",
        "source",
        "channel",
        "request_id",
        "proposal_type",
        "risk_class",
        "status",
        "evidence_refs",
        "required_approval_class",
        "operator_action_required",
        "side_effect_route",
        "payload",
        "created_at_ms",
        "approval_id",
        "decision",
        "actor",
        "auth_result",
        "delegated_route",
        "channel_event_id",
        "ts_ms",
        "direction",
        "auth_profile",
        "event_type",
        "payload_summary",
    ):
        assert f"'{column}'" in sql

    assert "v076 guard a fail: v065 openclaw.proposals missing required columns" in sql
    assert (
        "v076 guard a fail: v065 openclaw.approval_decisions missing required columns"
        in sql
    )
    assert "v076 guard a fail: v065 openclaw.channel_events missing required columns" in sql


def test_v076_guards_v065_openclaw_safety_constraints_and_indexes() -> None:
    sql = _normalized_sql()

    assert "pg_get_constraintdef(oid) ilike '%evidence_refs%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%jsonb_array_length%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%> 0%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%side_effect_route%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%/api/v1/governance/%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%live-auth%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%risk-config%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%deploy%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%restart%'" in sql
    assert "pg_get_constraintdef(oid) ilike '%delegated_route%'" in sql

    assert "to_regclass('openclaw.idx_openclaw_proposals_status_created')" in sql
    assert "to_regclass('openclaw.idx_openclaw_approval_decisions_proposal')" in sql
    assert "to_regclass('openclaw.idx_openclaw_channel_events_ts')" in sql
