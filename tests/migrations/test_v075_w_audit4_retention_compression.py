"""Static migration tests for V075 W-AUDIT-4 retention/compression."""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V075_PATH = _SRV_ROOT / "sql" / "migrations" / "V075__w_audit4_retention_compression.sql"


def _read_sql() -> str:
    assert V075_PATH.exists(), f"Migration file missing: {V075_PATH}"
    return V075_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v075_guards_actual_hypertable_plain_table_and_view_shapes() -> None:
    sql = _normalized_sql()

    assert "v075 guard a fail: timescaledb extension missing" in sql
    for hypertable in (
        "risk_verdicts",
        "position_snapshots",
        "signals",
        "order_state_changes",
        "intents",
    ):
        assert f"hypertable_name = '{hypertable}'" in sql
        assert f"trading.{hypertable} is not a hypertable" in sql

    assert "learning.scorer_training_features must be a view" in sql
    assert "learning.mlde_edge_training_rows must be a view" in sql
    assert "c.relkind = 'v'" in sql
    assert "learning.decision_features unexpectedly hypertable" in sql
    assert "trading.decision_outcomes unexpectedly hypertable" in sql


def test_v075_installs_timescale_policy_for_five_real_hypertables_only() -> None:
    sql = _normalized_sql()

    assert "set_chunk_time_interval('trading.risk_verdicts', interval '1 day')" in sql
    assert "add_compression_policy('trading.risk_verdicts', interval '7 days'" in sql
    assert "add_retention_policy('trading.risk_verdicts', interval '30 days'" in sql

    assert "add_compression_policy('trading.position_snapshots', interval '7 days'" in sql
    assert "add_retention_policy('trading.position_snapshots', interval '90 days'" in sql

    assert "add_retention_policy('trading.signals', interval '90 days'" in sql
    assert "add_compression_policy('trading.order_state_changes', interval '14 days'" in sql
    assert "add_retention_policy('trading.order_state_changes', interval '60 days'" in sql
    assert "add_retention_policy('trading.intents', interval '90 days'" in sql

    for table in (
        "trading.risk_verdicts",
        "trading.position_snapshots",
        "trading.signals",
        "trading.order_state_changes",
        "trading.intents",
    ):
        assert f"remove_retention_policy('{table}', if_exists => true)" in sql

    assert "add_retention_policy('learning.scorer_training_features'" not in sql
    assert "add_retention_policy('learning.mlde_edge_training_rows'" not in sql
    assert "add_retention_policy('learning.decision_features'" not in sql
    assert "add_retention_policy('trading.decision_outcomes'" not in sql


def test_v075_plain_table_prune_function_is_dry_run_default_and_bounded() -> None:
    sql = _normalized_sql()

    assert "create or replace function learning.prune_w_audit4_plain_retention" in sql
    assert "p_apply boolean default false" in sql
    assert "p_max_rows integer default null" in sql
    assert "v_max_rows_effective := coalesce(p_max_rows, 100000)" in sql
    assert "if v_max_rows_effective > 100000 then" in sql
    assert "if p_apply then" in sql
    assert "candidate_count bigint" in sql
    assert "deleted_count bigint" in sql


def test_v075_plain_table_prune_function_targets_only_storage_tables() -> None:
    sql = _normalized_sql()

    assert "from learning.decision_features" in sql
    assert "delete from learning.decision_features" in sql
    assert "where ts < v_decision_features_cutoff" in sql
    assert "'learning.decision_features'::text" in sql

    assert "from trading.decision_outcomes" in sql
    assert "delete from trading.decision_outcomes" in sql
    assert "backfilled_ts < v_decision_outcomes_cutoff" in sql
    assert "engine_mode <> 'live'" in sql
    assert "'trading.decision_outcomes'::text" in sql

    assert "delete from learning.scorer_training_features" not in sql
    assert "delete from learning.mlde_edge_training_rows" not in sql


def test_v075_has_plain_retention_safety_floors_and_guard_c() -> None:
    sql = _normalized_sql()

    assert "decision_features retention % days is below 30-day safety floor" in sql
    assert "decision_outcomes retention % days is below 90-day safety floor" in sql
    assert "v075 guard c fail: learning.prune_w_audit4_plain_retention function missing" in sql
    assert "v075: w-audit-4 retention/compression policy source installed" in sql
