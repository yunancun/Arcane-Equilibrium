"""Mock-based unit tests for REF-20 R20-P2b-T2/T3 V045/V046 schema.

REF-20 R20-P2b-T2/T3 V045/V046 schema 的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL files and verify the
structural contract:

1. V045 CREATE TABLE replay.run_state with required columns + status CHECK
   enum + runtime_environment CHECK enum + 2 hot-path indexes
   (actor_id+status, status only).
2. V046 CREATE TABLE replay.report_artifacts with FK to V045 ON DELETE
   CASCADE + artifact_type CHECK enum + 1 hot-path index (run_id+created_at).
3. Both files include Guard A (table existence + required-column probe)
   + Guard C (pg_get_indexdef compare for re-run safety).
4. V046 has explicit V045 prerequisite check (cannot run without V045
   land first).

Linux Operator deploys with real psql + the Guard A / Guard C runtime
checks defined in the SQL files. This test layer is the static
compile-time gate (E2 review-ready bundle on Mac dev).

我們在 Mac dev 測試層不對真實資料庫跑 psql；改為靜態 parse migration SQL 檔，
驗證結構契約。Linux operator 部署時跑真 psql + 各 Guard A/C 動態檢查。本
測試層是靜態編譯期 gate（Mac dev E2 審查）。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v045_v046_replay_run_state_artifacts.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §4.1
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
  §4 Wave 4 R20-P2b-T2 + T3
- docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md §6 v1.1 Option C
- sql/migrations/REF-20_RESERVATION.md §3 V045 / V046
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path resolution / 路徑解析
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V045_PATH = _MIGRATIONS_DIR / "V045__replay_run_state.sql"
V046_PATH = _MIGRATIONS_DIR / "V046__replay_report_artifacts.sql"


# ---------------------------------------------------------------------------
# Helpers / 工具函數
# ---------------------------------------------------------------------------
def _read_sql(path: Path) -> str:
    """Read full SQL file as text. / 讀取完整 SQL 檔為文字。"""
    assert path.exists(), f"Migration file missing: {path}"
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Remove `-- ...` line comments to avoid false-positive on doc text.
    去除 `-- ...` 行註解避免文字描述被 grep 誤命中。
    """
    return "\n".join(
        re.sub(r"--.*$", "", line) for line in sql.splitlines()
    )


# ---------------------------------------------------------------------------
# V045 tests / V045 測試
# ---------------------------------------------------------------------------
def test_v045_creates_replay_run_state_table() -> None:
    """V045 contains CREATE TABLE replay.run_state with required columns.
    V045 含 CREATE TABLE replay.run_state 並有必要欄位。
    """
    sql = _strip_sql_comments(_read_sql(V045_PATH))
    # Schema + table.
    assert "CREATE SCHEMA IF NOT EXISTS replay" in sql
    assert "CREATE TABLE IF NOT EXISTS replay.run_state" in sql
    # Required columns (per V3 §4.1 schema + V045 spec).
    required_cols = [
        "run_id",
        "actor_id",
        "manifest_id",
        "subprocess_pid",
        "status",
        "started_at",
        "completed_at",
        "exit_code",
        "output_path",
        "idempotency_key",
        "cancel_reason",
        "runtime_environment",
        "created_at",
    ]
    for col in required_cols:
        assert col in sql, f"V045 missing column declaration: {col}"


def test_v045_status_check_enum() -> None:
    """V045 ADDs CHECK chk_replay_run_state_status enforcing 5-value enum.
    V045 加 CHECK chk_replay_run_state_status 強制 5 值 enum。
    """
    sql = _strip_sql_comments(_read_sql(V045_PATH))
    assert "chk_replay_run_state_status" in sql
    # Must reference all 5 enum values.
    for status in (
        "starting",
        "running",
        "completed",
        "failed",
        "cancelled",
    ):
        assert f"'{status}'" in sql, f"V045 status enum missing: {status}"


def test_v045_runtime_env_check_enum() -> None:
    """V045 ADDs CHECK chk_replay_run_state_runtime_env enforcing V3 §4.1 enum.
    V045 加 CHECK chk_replay_run_state_runtime_env 強制 V3 §4.1 enum。
    """
    sql = _strip_sql_comments(_read_sql(V045_PATH))
    assert "chk_replay_run_state_runtime_env" in sql
    assert "'linux_trade_core'" in sql
    assert "'mac_dev_smoke_test_only'" in sql


def test_v045_hot_path_indexes_present() -> None:
    """V045 creates 2 hot-path indexes for advisory-lock cap query.
    V045 建 2 個 hot-path 索引供 advisory-lock cap 查詢。
    """
    sql = _strip_sql_comments(_read_sql(V045_PATH))
    # Index 1: actor_id + status composite (per-actor cap).
    assert "idx_replay_run_state_actor_status" in sql
    assert "(actor_id, status)" in sql
    # Index 2: status only (global cap).
    assert "idx_replay_run_state_status_only" in sql


def test_v045_guards_present() -> None:
    """V045 has Guard A (table+columns) + Guard C (index pg_get_indexdef).
    V045 含 Guard A（table+欄）+ Guard C（index pg_get_indexdef）。
    """
    sql = _read_sql(V045_PATH)  # keep comments (Guard label in comment line)
    # Guard A label
    assert "Guard A:" in sql
    # information_schema query is the canonical Guard A pattern.
    assert "information_schema.tables" in sql
    # Guard C label + pg_get_indexdef
    assert "Guard C:" in sql
    assert "pg_get_indexdef" in sql


# ---------------------------------------------------------------------------
# V046 tests / V046 測試
# ---------------------------------------------------------------------------
def test_v046_creates_replay_report_artifacts_table() -> None:
    """V046 creates replay.report_artifacts with required columns.
    V046 建 replay.report_artifacts 含必要欄位。
    """
    sql = _strip_sql_comments(_read_sql(V046_PATH))
    assert "CREATE TABLE IF NOT EXISTS replay.report_artifacts" in sql
    required_cols = [
        "artifact_id",
        "run_id",
        "artifact_type",
        "artifact_path",
        "byte_size",
        "is_mock",
        "created_at",
        "expires_at",
    ]
    for col in required_cols:
        assert col in sql, f"V046 missing column declaration: {col}"


def test_v046_fk_cascade_to_v045() -> None:
    """V046 has FK run_id REFERENCES replay.run_state(run_id) ON DELETE CASCADE.
    V046 有 FK run_id REFERENCES replay.run_state(run_id) ON DELETE CASCADE。
    """
    sql = _strip_sql_comments(_read_sql(V046_PATH))
    assert "REFERENCES replay.run_state(run_id)" in sql
    assert "ON DELETE CASCADE" in sql


def test_v046_artifact_type_check_enum() -> None:
    """V046 enforces artifact_type CHECK enum (5 values).
    V046 強制 artifact_type CHECK enum（5 值）。
    """
    sql = _strip_sql_comments(_read_sql(V046_PATH))
    assert "chk_replay_report_artifacts_type" in sql
    for atype in (
        "canary",
        "diagnostic",
        "pnl_summary",
        "fill_log",
        "baseline_compare",
    ):
        assert f"'{atype}'" in sql, f"V046 artifact_type enum missing: {atype}"


def test_v046_hot_path_index_present() -> None:
    """V046 creates idx_replay_report_artifacts_run (run_id + created_at).
    V046 建 idx_replay_report_artifacts_run（run_id + created_at）。
    """
    sql = _strip_sql_comments(_read_sql(V046_PATH))
    assert "idx_replay_report_artifacts_run" in sql
    assert "(run_id, created_at)" in sql


def test_v046_v045_prerequisite_check() -> None:
    """V046 RAISE EXCEPTION if replay.run_state (V045) absent at deploy time.
    V046 在部署時若 replay.run_state（V045）缺則 RAISE EXCEPTION。
    """
    sql = _read_sql(V046_PATH)
    # Look for the explicit prerequisite check pattern.
    # 找顯式前置檢查 pattern。
    assert "V045 must run before V046" in sql or "run_state does not exist" in sql
    assert "RAISE EXCEPTION" in sql


def test_v046_guards_present() -> None:
    """V046 has Guard A (table+columns + V045 prereq) + Guard C (index pg_get_indexdef).
    V046 含 Guard A（table+欄+V045 前置）+ Guard C（index pg_get_indexdef）。
    """
    sql = _read_sql(V046_PATH)
    assert "Guard A:" in sql
    assert "information_schema.tables" in sql
    assert "Guard C:" in sql
    assert "pg_get_indexdef" in sql


# ---------------------------------------------------------------------------
# Cross-file invariants / 跨檔不變量
# ---------------------------------------------------------------------------
def test_both_files_have_bilingual_module_notes() -> None:
    """Both V045 + V046 have CN/EN dual-language headers per CLAUDE.md §七.
    V045 + V046 都依 CLAUDE.md §七 雙語注釋規範。
    """
    for path in (V045_PATH, V046_PATH):
        sql = _read_sql(path)
        # Must have purpose section in both languages.
        # 必有兩語言的 purpose 段。
        assert "Purpose / 目的" in sql, (
            f"{path.name} missing bilingual Purpose header"
        )
        # Must reference REF-20 V3 spec.
        # 必引用 REF-20 V3 spec。
        assert (
            "ref20_paper_replay_lab_dev_plan_v3" in sql
            or "REF-20" in sql
        ), f"{path.name} missing V3 spec reference"


def test_files_are_idempotent_safe() -> None:
    """Both files use IF NOT EXISTS / IF NOT EXISTS conditional CREATE/INDEX.
    兩檔都用 IF NOT EXISTS / 條件式 CREATE/INDEX，保證 idempotent。
    """
    for path in (V045_PATH, V046_PATH):
        sql = _read_sql(path)
        # CREATE TABLE IF NOT EXISTS pattern.
        assert "CREATE TABLE IF NOT EXISTS" in sql
        # CREATE INDEX is wrapped in DO $$ ... IF index def NULL ... END pattern
        # for idempotent runs. Just check that pg_get_indexdef compare exists.
        # CREATE INDEX 在 DO $$ ... IF NULL ... END 條件式內保 idempotent。
        # 確認 pg_get_indexdef compare 存在。
        assert "pg_get_indexdef" in sql
