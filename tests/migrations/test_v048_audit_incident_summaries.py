"""Mock-based unit tests for REF-20 R20-W9-T3 V048 audit_incident_summaries schema.

REF-20 R20-W9-T3 V048 audit_incident_summaries schema 的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL file and verify the
structural contract:

1. V048 CREATE TABLE replay.audit_incident_summaries with required columns
   + UNIQUE(scan_date, severity, event_type).
2. V048 has 1 hot-path index: idx_audit_incident_scan_date_severity.
3. V048 enforces severity CHECK enum (low / medium / high / critical).
4. Both Guard A (table existence + required-column probe) and Guard C
   (pg_get_indexdef compare) are present.

Linux Operator deploys with real psql + the Guard A / Guard C runtime
checks defined in the SQL files. This test layer is the static
compile-time gate (E2 review-ready bundle on Mac dev).

Mac dev 測試層不對真實 PG 跑 psql；改靜態 parse migration SQL 驗結構契約。
Linux operator 部署時跑真 psql + Guard A/C 動態檢查。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v048_audit_incident_summaries.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
  §11 P6 + §12 #14
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
  §4 Wave 9 R20-W9-T3
- sql/migrations/REF-20_RESERVATION.md §3 V048
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

V048_PATH = _MIGRATIONS_DIR / "V048__replay_audit_incident_summaries.sql"


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
# Test 1: V048 schema exists + required columns
# ---------------------------------------------------------------------------


def test_v048_creates_audit_incident_summaries_table() -> None:
    """V048 contains CREATE TABLE replay.audit_incident_summaries with required columns.
    V048 含 CREATE TABLE replay.audit_incident_summaries 並有必要欄位。
    """
    sql = _strip_sql_comments(_read_sql(V048_PATH))
    # Schema + table.
    assert "CREATE SCHEMA IF NOT EXISTS replay" in sql
    assert "CREATE TABLE IF NOT EXISTS replay.audit_incident_summaries" in sql
    # Required columns (per V048 spec).
    required_cols = [
        "summary_id",
        "scan_date",
        "window_days",
        "incident_count",
        "severity",
        "event_type",
        "first_incident_ts",
        "last_incident_ts",
        "sample_payload",
    ]
    for col in required_cols:
        assert col in sql, f"V048 missing column declaration: {col}"


# ---------------------------------------------------------------------------
# Test 2: UNIQUE(scan_date, severity, event_type) constraint enforced
# ---------------------------------------------------------------------------


def test_v048_unique_summary_constraint() -> None:
    """V048 ADDs UNIQUE(scan_date, severity, event_type).
    V048 加 UNIQUE(scan_date, severity, event_type) — 防同日重跑寫重複。
    """
    sql = _strip_sql_comments(_read_sql(V048_PATH))
    assert "uq_audit_incident_scan_severity_event" in sql
    assert "UNIQUE (scan_date, severity, event_type)" in sql


# ---------------------------------------------------------------------------
# Test 3: severity CHECK enum enforces 4 values
# ---------------------------------------------------------------------------


def test_v048_severity_check_enum() -> None:
    """V048 enforces severity ∈ {'low', 'medium', 'high', 'critical'}.
    V048 強制 severity ∈ {'low', 'medium', 'high', 'critical'}。
    """
    sql = _strip_sql_comments(_read_sql(V048_PATH))
    assert "chk_audit_incident_severity" in sql
    # 4-value enum.
    # 4 值 enum。
    for v in ("'low'", "'medium'", "'high'", "'critical'"):
        assert v in sql, f"missing severity enum value {v}"
    assert "severity IN ('low', 'medium', 'high', 'critical')" in sql


# ---------------------------------------------------------------------------
# Test 4: Guard A + Guard C present + hot-path index defined
# ---------------------------------------------------------------------------


def test_v048_guards_and_index_present() -> None:
    """V048 has Guard A + Guard C blocks + hot-path index.
    V048 有 Guard A + Guard C blocks + hot-path index。
    """
    sql_with_comments = _read_sql(V048_PATH)
    sql = _strip_sql_comments(sql_with_comments)

    # Guard A block / Guard A 區塊.
    assert "V048 Guard A" in sql_with_comments
    assert "v_required_cols TEXT[]" in sql
    assert "RAISE EXCEPTION" in sql

    # Guard C block / Guard C 區塊.
    assert "V048 Guard C" in sql_with_comments
    assert "pg_get_indexdef" in sql

    # Hot-path index name + columns.
    # Hot-path index 名稱 + 欄位。
    assert "idx_audit_incident_scan_date_severity" in sql
    assert "(scan_date DESC, severity)" in sql

    # Defensive CHECK on incident_count >= 0 + window_days > 0.
    # 防禦 CHECK incident_count >= 0 + window_days > 0。
    assert "chk_audit_incident_count_nonneg" in sql
    assert "incident_count >= 0" in sql
    assert "chk_audit_incident_window_pos" in sql
    assert "window_days > 0" in sql
