"""Static migration tests for V078 lease_transitions BYPASS state."""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V078_PATH = _SRV_ROOT / "sql" / "migrations" / "V078__lease_transitions_bypass_state.sql"


def _read_sql() -> str:
    assert V078_PATH.exists(), f"Migration file missing: {V078_PATH}"
    return V078_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v078_guards_v054_table_and_to_state_column() -> None:
    sql = _normalized_sql()

    assert "to_regclass('learning.lease_transitions')" in sql
    assert "v078 guard a fail: learning.lease_transitions missing" in sql
    assert "table_schema = 'learning'" in sql
    assert "table_name = 'lease_transitions'" in sql
    assert "column_name = 'to_state'" in sql
    assert "data_type = 'text'" in sql
    assert "is_nullable = 'no'" in sql


def test_v078_preserves_nine_sm_states_and_adds_bypass() -> None:
    sql = _normalized_sql()

    for state in (
        "draft",
        "registered",
        "active",
        "bridged",
        "frozen",
        "revoked",
        "expired",
        "rejected",
        "consumed",
        "bypass",
    ):
        assert f"'{state}'" in sql

    assert "v078 guard b fail: learning.lease_transitions has unsupported to_state rows" in sql


def test_v078_replaces_named_check_idempotently() -> None:
    sql = _normalized_sql()

    assert "chk_lease_transitions_to_state" in sql
    assert "pg_get_constraintdef(oid)" in sql
    assert "already accepts bypass" in sql
    assert "lock table learning.lease_transitions in access exclusive mode" in sql
    assert "drop constraint chk_lease_transitions_to_state" in sql
    assert "add constraint chk_lease_transitions_to_state" in sql
    assert "not valid" in sql
    assert "validate constraint chk_lease_transitions_to_state" in sql


def test_v078_does_not_mutate_lease_transition_rows() -> None:
    sql = _normalized_sql()

    for forbidden in (
        "insert into learning.lease_transitions",
        "update learning.lease_transitions",
        "delete from learning.lease_transitions",
        "drop table",
        "create table",
    ):
        assert forbidden not in sql
