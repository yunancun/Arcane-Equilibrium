"""Mock-based unit tests for REF-20 R20-P3a-Q2 V041 schema (OOS embargo).

REF-20 R20-P3a-Q2 V041 schema（OOS embargo）的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL file and verify the
structural contract (table bootstrap, ADD COLUMN, CHECK constraint
expression). The Linux operator deploys with real psql + the Guard
A/B + CHECK runtime checks defined in the SQL file. This test layer
is the static compile-time gate (E2 review-ready bundle on Mac dev).

我們在 Mac dev 測試層不對真實資料庫跑 psql；改為靜態 parse migration SQL 檔，
驗證結構契約（table bootstrap、ADD COLUMN、CHECK constraint 表達式）。Linux
operator 部署時跑真 psql + 各 Guard A/B + CHECK 動態檢查。本測試層是靜態
編譯期 gate（Mac dev E2 審查）。

Cross-language consistency / 跨語言一致性:
    The V041 CHECK uses ``GREATEST(7, CEIL(2.0 * half_life_days)::INTEGER)``.
    The Python validator uses ``max(7, math.ceil(2 × half_life_days))``.
    A dedicated test below sweeps representative (half_life, embargo)
    pairs and asserts both layers agree on accept / reject.

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v041_oos_embargo.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §8.1
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
  §4 Wave 5 R20-P3a-Q2
- sql/migrations/REF-20_RESERVATION.md §3 V041
- program_code/exchange_connectors/bybit_connector/control_api_v1/replay/
  embargo_validator.py (Python sibling)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path resolution / 路徑解析
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V041_PATH = _MIGRATIONS_DIR / "V041__replay_oos_embargo_enforcement.sql"


# Make the Python validator importable for the cross-language consistency test.
# 讓 Python validator 可被 import 以做跨語言一致性測試。
_VALIDATOR_PARENT = _SRV_ROOT / "program_code" / "exchange_connectors" / \
    "bybit_connector" / "control_api_v1"
if str(_VALIDATOR_PARENT) not in sys.path:
    sys.path.insert(0, str(_VALIDATOR_PARENT))


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
# V041 SQL structural tests / V041 SQL 結構測試
# ---------------------------------------------------------------------------
def test_v041_bootstraps_replay_experiments_table() -> None:
    """V041 contains CREATE TABLE IF NOT EXISTS replay.experiments.

    V041 含 CREATE TABLE IF NOT EXISTS replay.experiments。
    """
    sql = _strip_sql_comments(_read_sql(V041_PATH))
    assert "CREATE SCHEMA IF NOT EXISTS replay" in sql
    assert "CREATE TABLE IF NOT EXISTS replay.experiments" in sql
    # Required columns for the chk_embargo_days CHECK to function.
    # chk_embargo_days CHECK 所需欄位。
    for col in ("experiment_id", "half_life_days", "embargo_days"):
        assert col in sql, f"V041 missing column: {col}"


def test_v041_adds_columns_idempotently() -> None:
    """V041 uses ADD COLUMN IF NOT EXISTS for half_life_days + embargo_days.

    V041 對 half_life_days + embargo_days 使用 ADD COLUMN IF NOT EXISTS。
    """
    sql = _strip_sql_comments(_read_sql(V041_PATH))
    assert "ADD COLUMN IF NOT EXISTS half_life_days" in sql
    assert "ADD COLUMN IF NOT EXISTS embargo_days" in sql


def test_v041_check_constraint_present() -> None:
    """V041 wraps ADD CONSTRAINT chk_embargo_days in IF NOT EXISTS DO block.

    V041 將 ADD CONSTRAINT chk_embargo_days 包在 IF NOT EXISTS DO block
    保 idempotent。
    """
    sql_raw = _read_sql(V041_PATH)
    sql = _strip_sql_comments(sql_raw)
    # Constraint name + ADD CONSTRAINT verb.
    # 約束名 + ADD CONSTRAINT 語句。
    assert "chk_embargo_days" in sql
    assert "ADD CONSTRAINT chk_embargo_days" in sql
    # Core invariant: GREATEST(7, CEIL(2.0 * half_life_days)::INTEGER)
    # 核心不變量
    assert "GREATEST(7, CEIL(2.0 * half_life_days)::INTEGER)" in sql
    # idempotent guard via pg_constraint lookup
    # idempotent 守門 via pg_constraint
    assert "pg_constraint" in sql
    assert "conname = 'chk_embargo_days'" in sql


def test_v041_guards_present() -> None:
    """V041 includes Guard A (column existence) + Guard B (column type).

    V041 含 Guard A（欄位存在性）+ Guard B（欄位 type）。
    """
    sql_raw = _read_sql(V041_PATH)
    # Guard labels in commented section.
    # Guard 標籤在註解區。
    assert "Guard A:" in sql_raw, "V041 missing Guard A label"
    assert "Guard B:" in sql_raw, "V041 missing Guard B label"
    # Guard A canonical pattern.
    # Guard A 範式。
    assert "information_schema.columns" in sql_raw
    # Guard B canonical pattern: data_type compare on half_life_days + embargo_days.
    # Guard B 範式：對 half_life_days + embargo_days 比 data_type。
    assert "data_type" in sql_raw
    assert "double precision" in sql_raw  # half_life_days expected type
    assert "expected integer" in sql_raw or "'integer'" in sql_raw


def test_v041_bilingual_module_note() -> None:
    """V041 carries CN/EN dual-language header per CLAUDE.md §七.

    V041 依 CLAUDE.md §七 雙語注釋規範。
    """
    sql = _read_sql(V041_PATH)
    # Must have purpose section in both languages.
    # 必有兩語言 purpose 段。
    assert "Purpose / 目的" in sql, "V041 missing bilingual Purpose header"
    # Must reference REF-20 V3 spec.
    # 必引用 REF-20 V3 spec。
    assert (
        "ref20_paper_replay_lab_dev_plan_v3" in sql
        or "REF-20" in sql
    ), "V041 missing V3 spec reference"
    # Bilingual column comments / 雙語欄位 COMMENT。
    assert "COMMENT ON TABLE replay.experiments" in sql
    assert "COMMENT ON COLUMN replay.experiments.half_life_days" in sql
    assert "COMMENT ON COLUMN replay.experiments.embargo_days" in sql


# ---------------------------------------------------------------------------
# Cross-language consistency: V041 CHECK ≡ Python validator
# 跨語言一致性：V041 CHECK 與 Python validator 對齊
# ---------------------------------------------------------------------------
def test_v041_check_aligns_with_python_validator() -> None:
    """V041 ``chk_embargo_days`` agrees with embargo_validator on edge cases.

    V041 ``chk_embargo_days`` 與 embargo_validator 在邊界 case 一致。

    Strategy: import the Python validator and replicate the SQL
    expression in pure Python (PostgreSQL ``GREATEST(7, CEIL(2.0 *
    h)::INTEGER)`` → ``max(7, math.ceil(2.0 * h))``). Sweep
    representative (half_life, embargo) pairs and assert both functions
    agree on accept / reject.
    """
    import math

    # Import Python validator (path injected at module top).
    # Import Python validator（路徑在模組頂部注入）。
    from replay.embargo_validator import (  # type: ignore[import-not-found]
        validate_embargo,
    )

    def _sql_replication(half_life: float, embargo: int) -> bool:
        """Replicate the V041 CHECK in pure Python.
        以 Python 純函式重現 V041 CHECK。
        """
        # NULL handling matches V041 CHECK (NULLs always pass).
        # NULL 處理對齊 V041 CHECK（NULL 永遠通過）。
        if half_life is None or embargo is None:
            return True
        min_required = max(7, math.ceil(2.0 * float(half_life)))
        return embargo >= min_required

    # Edge case sweep / 邊界 case 掃過。
    cases = [
        # (half_life, embargo, expected_ok)
        (3.0, 7, True),   # 7-day floor binding (2 × 3 = 6 < 7)
        (3.0, 6, False),  # below floor
        (5.0, 10, True),  # exact equality (2 × 5 = 10)
        (5.0, 9, False),  # 1-day shy
        (7.5, 15, True),  # exact: 2 × 7.5 = 15
        (7.5, 14, False), # 1-day shy of 15
        (5.6, 12, True),  # ceil(11.2) = 12
        (5.6, 11, False), # ceil(11.2) = 12; 11 fails
        (14.0, 28, True), # default-fallback boundary
        (14.0, 27, False), # below default-fallback minimum
        (0.0, 7, True),   # zero half-life still needs 7-day floor
        (0.0, 6, False),
    ]

    for half_life, embargo, expected_ok in cases:
        py_ok = validate_embargo(half_life, embargo)
        sql_ok = _sql_replication(half_life, embargo)
        assert py_ok == sql_ok == expected_ok, (
            f"Mismatch at (half_life={half_life}, embargo={embargo}): "
            f"py={py_ok} sql={sql_ok} expected={expected_ok}"
        )
