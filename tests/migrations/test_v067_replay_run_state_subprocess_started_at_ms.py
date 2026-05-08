from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[2]
_MIGRATION = _REPO_ROOT / "sql" / "migrations" / "V067__replay_run_state_subprocess_started_at_ms.sql"


def _normalized_sql() -> str:
    sql = _MIGRATION.read_text(encoding="utf-8")
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", sql.lower())


def test_v067_migration_file_exists() -> None:
    assert _MIGRATION.exists()


def test_v067_guards_v045_run_state_presence() -> None:
    sql = _normalized_sql()

    assert "table_schema = 'replay'" in sql
    assert "table_name = 'run_state'" in sql
    assert "v067 guard a: replay.run_state not found" in sql


def test_v067_adds_nullable_subprocess_started_at_ms_column() -> None:
    sql = _normalized_sql()

    assert (
        "alter table replay.run_state add column if not exists "
        "subprocess_started_at_ms bigint"
    ) in sql
    assert "subprocess_started_at_ms bigint not null" not in sql


def test_v067_adds_positive_check_and_comment() -> None:
    sql = _normalized_sql()

    assert "chk_replay_run_state_subprocess_started_at_ms_positive" in sql
    assert "subprocess_started_at_ms is null or subprocess_started_at_ms > 0" in sql
    assert "comment on column replay.run_state.subprocess_started_at_ms" in sql
    assert "pid reuse" in sql
