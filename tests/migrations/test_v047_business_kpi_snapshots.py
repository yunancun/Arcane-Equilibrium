"""Mock-based unit tests for REF-20 R20-W9-T2 V047 business_kpi_snapshots schema.

REF-20 R20-W9-T2 V047 business_kpi_snapshots schema 的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL file and verify the
structural contract:

1. V047 CREATE TABLE replay.business_kpi_snapshots with required columns
   + UNIQUE(snapshot_date, window_type, kpi_name).
2. V047 has 1 hot-path index: idx_kpi_snapshot_date_window.
3. V047 enforces window_type CHECK enum (7d / 14d only).
4. Both Guard A (table existence + required-column probe) and Guard C
   (pg_get_indexdef compare) are present.

Linux Operator deploys with real psql + the Guard A / Guard C runtime
checks defined in the SQL files. This test layer is the static
compile-time gate (E2 review-ready bundle on Mac dev).

Mac dev 測試層不對真實 PG 跑 psql；改靜態 parse migration SQL 驗結構契約。
Linux operator 部署時跑真 psql + Guard A/C 動態檢查。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v047_business_kpi_snapshots.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
  §11 P6 + §12 #14
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
  §4 Wave 9 R20-W9-T2
- sql/migrations/REF-20_RESERVATION.md §3 V047
"""

from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Path resolution / 路徑解析
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V047_PATH = _MIGRATIONS_DIR / "V047__replay_business_kpi_snapshots.sql"


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
# Test 1: V047 schema exists + required columns
# ---------------------------------------------------------------------------


def test_v047_creates_business_kpi_snapshots_table() -> None:
    """V047 contains CREATE TABLE replay.business_kpi_snapshots with required columns.
    V047 含 CREATE TABLE replay.business_kpi_snapshots 並有必要欄位。
    """
    sql = _strip_sql_comments(_read_sql(V047_PATH))
    # Schema + table.
    assert "CREATE SCHEMA IF NOT EXISTS replay" in sql
    assert "CREATE TABLE IF NOT EXISTS replay.business_kpi_snapshots" in sql
    # Required columns (per V047 spec).
    required_cols = [
        "snapshot_id",
        "snapshot_date",
        "window_type",
        "kpi_name",
        "kpi_value",
        "sample_size",
        "created_at",
    ]
    for col in required_cols:
        assert col in sql, f"V047 missing column declaration: {col}"


# ---------------------------------------------------------------------------
# Test 2: UNIQUE(snapshot_date, window_type, kpi_name) constraint enforced
# ---------------------------------------------------------------------------


def test_v047_unique_snapshot_constraint() -> None:
    """V047 ADDs UNIQUE(snapshot_date, window_type, kpi_name).
    V047 加 UNIQUE(snapshot_date, window_type, kpi_name) — 防同日重跑寫重複。
    """
    sql = _strip_sql_comments(_read_sql(V047_PATH))
    assert "uq_kpi_snapshot_date_window_name" in sql
    assert "UNIQUE (snapshot_date, window_type, kpi_name)" in sql


# ---------------------------------------------------------------------------
# Test 3: window_type CHECK enum enforces 7d / 14d only
# ---------------------------------------------------------------------------


def test_v047_window_type_check_enum() -> None:
    """V047 enforces window_type ∈ {'7d', '14d'}.
    V047 強制 window_type ∈ {'7d', '14d'}。
    """
    sql = _strip_sql_comments(_read_sql(V047_PATH))
    assert "chk_kpi_window_type" in sql
    # Both enum values appear in CHECK constraint.
    # 兩個 enum 值在 CHECK constraint 中。
    assert "'7d'" in sql
    assert "'14d'" in sql
    assert "window_type IN ('7d', '14d')" in sql


# ---------------------------------------------------------------------------
# Test 4: Guard A + Guard C present + hot-path index defined
# ---------------------------------------------------------------------------


def test_v047_guards_and_index_present() -> None:
    """V047 has Guard A + Guard C blocks + hot-path index.
    V047 有 Guard A + Guard C blocks + hot-path index。
    """
    sql_with_comments = _read_sql(V047_PATH)
    sql = _strip_sql_comments(sql_with_comments)

    # Guard A block / Guard A 區塊.
    assert "V047 Guard A" in sql_with_comments
    assert "v_required_cols TEXT[]" in sql
    assert "RAISE EXCEPTION" in sql

    # Guard C block / Guard C 區塊.
    assert "V047 Guard C" in sql_with_comments
    assert "pg_get_indexdef" in sql

    # Hot-path index name + columns.
    # Hot-path index 名稱 + 欄位。
    assert "idx_kpi_snapshot_date_window" in sql
    assert (
        "CREATE INDEX idx_kpi_snapshot_date_window\n"
        "            ON replay.business_kpi_snapshots (snapshot_date DESC, window_type)"
        in sql
        or "(snapshot_date DESC, window_type)" in sql
    )
