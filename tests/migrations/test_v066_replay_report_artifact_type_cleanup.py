"""Static migration tests for V066 replay_report artifact type cleanup."""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V066_PATH = (
    _SRV_ROOT
    / "sql"
    / "migrations"
    / "V066__replay_report_artifact_type_cleanup.sql"
)


def _read_sql() -> str:
    assert V066_PATH.exists(), f"Migration file missing: {V066_PATH}"
    return V066_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def test_v066_requires_v046_report_artifacts_table() -> None:
    sql = _strip_sql_comments(_read_sql())
    assert "to_regclass('replay.report_artifacts')" in sql
    assert "V066 Guard A FAIL" in sql
    assert "information_schema.columns" in sql
    for column in ("artifact_type", "byte_size"):
        assert f"'{column}'" in sql


def test_v066_extends_artifact_type_check_with_replay_report() -> None:
    sql = _strip_sql_comments(_read_sql())
    assert "chk_replay_report_artifacts_type" in sql
    assert "DROP CONSTRAINT chk_replay_report_artifacts_type" in sql
    assert "position('replay_report' IN v_type_def) = 0" in sql
    for artifact_type in (
        "canary",
        "diagnostic",
        "pnl_summary",
        "replay_report",
        "fill_log",
        "baseline_compare",
    ):
        assert f"'{artifact_type}'" in sql


def test_v066_adds_byte_size_nonnegative_check() -> None:
    sql = _strip_sql_comments(_read_sql())
    assert "chk_replay_report_artifacts_byte_size_nonnegative" in sql
    assert "CHECK (byte_size >= 0)" in sql


def test_v066_documents_legacy_pnl_summary_compatibility() -> None:
    sql = _read_sql()
    assert "legacy 'pnl_summary'" in sql
    assert "replay_report is the explicit finalize artifact" in sql
