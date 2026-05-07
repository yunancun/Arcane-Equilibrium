"""Static migration tests for MAG-032 V064 Agent Spine decision store."""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V064_PATH = _SRV_ROOT / "sql" / "migrations" / "V064__agent_spine_decision_store.sql"


def _read_sql() -> str:
    assert V064_PATH.exists(), f"Migration file missing: {V064_PATH}"
    return V064_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def test_v064_creates_agent_spine_store_tables() -> None:
    sql = _strip_sql_comments(_read_sql())
    for table in (
        "agent.decision_objects",
        "agent.decision_edges",
        "agent.decision_state_changes",
        "agent.execution_idempotency_keys",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_v064_object_and_edge_contracts_cover_signal_to_plan_chain() -> None:
    sql = _strip_sql_comments(_read_sql())
    for object_type in (
        "strategy_signal",
        "strategist_decision",
        "guardian_verdict",
        "execution_plan",
        "execution_report",
    ):
        assert f"'{object_type}'" in sql
    for edge_type in ("signal_for", "reviewed_by", "planned_by", "executed_by"):
        assert f"'{edge_type}'" in sql
    for column in ("signal_id", "decision_id", "verdict_id", "verdict_version", "order_plan_id"):
        assert column in sql


def test_v064_idempotency_and_chain_indexes_present() -> None:
    sql = _strip_sql_comments(_read_sql())
    for index in (
        "uq_agent_decision_objects_type_idempotency",
        "uq_agent_decision_objects_strategy_signal",
        "uq_agent_decision_objects_strategist_decision",
        "uq_agent_decision_objects_guardian_verdict",
        "uq_agent_decision_objects_execution_plan",
        "uq_agent_execution_keys_plan_mode",
        "uq_agent_execution_keys_decision_plan_mode",
        "idx_agent_decision_edges_from",
        "idx_agent_decision_edges_to",
    ):
        assert index in sql
    assert "ON CONFLICT" not in sql


def test_v064_state_changes_are_timescale_optional_and_guarded() -> None:
    sql_with_comments = _read_sql()
    sql = _strip_sql_comments(sql_with_comments)
    assert "create_hypertable('agent.decision_state_changes', 'ts'" in sql
    assert "IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')" in sql
    assert "V064 Guard A" in sql_with_comments
    assert "information_schema.columns" in sql
    assert "RAISE EXCEPTION 'V064 Guard A FAIL" in sql
