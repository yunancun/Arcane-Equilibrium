"""Mock-based unit tests for REF-20 R20-P6-S14 V044 handoff idempotency schema.

REF-20 R20-P6-S14 V044 handoff idempotency schema 的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL file and verify the
structural contract:

1. V044 CREATE TABLE replay.handoff_requests with required columns
   + UNIQUE(actor_id, idempotency_key) + UNIQUE(trace_id).
2. V044 has 2 hot-path indexes: idx_handoff_actor_ts (cooldown) +
   idx_handoff_recent (footer).
3. V044 extends V035 governance_audit_log event_type CHECK enum with
   'replay_handoff_request' (audit_emit dependency).
4. Both Guard A (table existence + required-column probe) and Guard C
   (pg_get_indexdef compare) are present.

Linux Operator deploys with real psql + the Guard A / Guard C runtime
checks defined in the SQL files. This test layer is the static
compile-time gate (E2 review-ready bundle on Mac dev).

Mac dev 測試層不對真實 PG 跑 psql；改靜態 parse migration SQL 驗結構契約。
Linux operator 部署時跑真 psql + Guard A/C 動態檢查。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v044_handoff_idempotency.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
  §11 P6 + §12 #20
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
  §4 Wave 8 R20-P6-S14
- sql/migrations/REF-20_RESERVATION.md §3 V044
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

V044_PATH = _MIGRATIONS_DIR / "V044__replay_handoff_idempotency_unique.sql"


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
# Test 1: V044 schema exists / V044 schema 存在
# ---------------------------------------------------------------------------


def test_v044_creates_handoff_requests_table() -> None:
    """V044 contains CREATE TABLE replay.handoff_requests with required columns.
    V044 含 CREATE TABLE replay.handoff_requests 並有必要欄位。
    """
    sql = _strip_sql_comments(_read_sql(V044_PATH))
    # Schema + table.
    assert "CREATE SCHEMA IF NOT EXISTS replay" in sql
    assert "CREATE TABLE IF NOT EXISTS replay.handoff_requests" in sql
    # Required columns (per V044 spec).
    required_cols = [
        "handoff_id",
        "actor_id",
        "experiment_id",
        "manifest_id",
        "idempotency_key",
        "typed_phrase_hash",
        "operator_notes",
        "result",
        "trace_id",
        "cached",
        "reject_reason",
        "ts",
    ]
    for col in required_cols:
        assert col in sql, f"V044 missing column declaration: {col}"


# ---------------------------------------------------------------------------
# Test 2: UNIQUE(actor_id, idempotency_key) constraint enforced
# ---------------------------------------------------------------------------


def test_v044_unique_actor_idempotency_constraint() -> None:
    """V044 ADDs UNIQUE(actor_id, idempotency_key) — V3 §12 #20 binding.
    V044 加 UNIQUE(actor_id, idempotency_key) — V3 §12 #20 綁定。
    """
    sql = _strip_sql_comments(_read_sql(V044_PATH))
    assert "uq_handoff_actor_idempotency" in sql
    # UNIQUE + (actor_id, idempotency_key) appears in the same expression.
    assert "UNIQUE (actor_id, idempotency_key)" in sql

    # Also UNIQUE(trace_id) for forensic correlation.
    assert "uq_handoff_trace_id" in sql
    assert "UNIQUE (trace_id)" in sql


# ---------------------------------------------------------------------------
# Test 3: FK NOT enforced (decoupled per V045 pattern)
# ---------------------------------------------------------------------------


def test_v044_no_fk_to_replay_experiments() -> None:
    """V044 does NOT enforce FK on experiment_id / manifest_id — decoupled
    per V045 fixture-vs-migration ordering rationale.
    V044 不對 experiment_id / manifest_id 強制 FK — 與 V045 同樣理由
    （fixture vs migration land 順序）。

    The replay.experiments table lives in P2b runner SQL fixture (NOT a
    migration); enforcing FK here would block V044 deploy until fixture
    lands. V045 / V043 follow same decoupling pattern.
    replay.experiments 由 P2b runner SQL fixture 部署（非 migration）；
    本檔強制 FK 會阻擋 V044 deploy。V043 / V045 同此 decoupling。
    """
    sql = _strip_sql_comments(_read_sql(V044_PATH))
    # Should NOT contain REFERENCES to replay.experiments (decoupled).
    # 不應對 replay.experiments 強制 REFERENCES。
    assert "REFERENCES replay.experiments" not in sql, (
        "V044 must not enforce FK to replay.experiments per V045 pattern"
    )


# ---------------------------------------------------------------------------
# Test 4: Append-only audit pattern (no GRANT UPDATE / DELETE)
# ---------------------------------------------------------------------------


def test_v044_v035_event_type_extension_append_only() -> None:
    """V044 extends V035 event_type CHECK enum WITHOUT mutating GRANT.
    V044 擴 V035 event_type CHECK enum 但不動 GRANT。

    P6-S15 audit emit policy: append-only (INSERT only, no UPDATE/DELETE).
    V044 only:
      1. Adds 'replay_handoff_request' to event_type CHECK enum.
      2. Does NOT issue GRANT INSERT / GRANT UPDATE / GRANT DELETE
         (those grants are owned by V035 / governance migrations).
    P6-S15 audit emit 政策：append-only；V044 只擴 enum，不動 GRANT。
    """
    sql = _strip_sql_comments(_read_sql(V044_PATH))
    # event_type CHECK extension referenced.
    # event_type CHECK 擴充被 reference。
    assert "replay_handoff_request" in sql, (
        "V044 must extend V035 event_type CHECK with replay_handoff_request"
    )
    # 6-value list is canonical post-V044.
    # V044 後 canonical 為 6 值 list。
    for value in (
        "review_live_candidate",
        "lease_grant",
        "lease_auto_revoke",
        "bulk_re_evaluation",
        "audit_write_failed",
        "replay_handoff_request",
    ):
        assert f"'{value}'" in sql, f"V044 event_type list missing: {value}"

    # No GRANT UPDATE / GRANT DELETE on governance_audit_log.
    # governance_audit_log 不能被 GRANT UPDATE / DELETE。
    assert "GRANT UPDATE" not in sql.upper(), (
        "V044 must not GRANT UPDATE on governance_audit_log (append-only)"
    )
    assert "GRANT DELETE" not in sql.upper(), (
        "V044 must not GRANT DELETE on governance_audit_log (append-only)"
    )


# ---------------------------------------------------------------------------
# Bonus: Hot-path indexes / 熱路徑索引（覆蓋 cooldown + footer 查詢）
# ---------------------------------------------------------------------------


def test_v044_hot_path_indexes_present() -> None:
    """V044 creates 2 hot-path indexes for cooldown + footer queries.
    V044 建 2 個 hot-path 索引覆蓋 cooldown + footer 查詢。
    """
    sql = _strip_sql_comments(_read_sql(V044_PATH))
    # Index 1: actor_id + ts DESC (cooldown).
    assert "idx_handoff_actor_ts" in sql
    assert "(actor_id, ts DESC)" in sql
    # Index 2: ts DESC (recent footer).
    assert "idx_handoff_recent" in sql


# ---------------------------------------------------------------------------
# Bonus: Guards present (Guard A + Guard C)
# ---------------------------------------------------------------------------


def test_v044_guards_present() -> None:
    """V044 has Guard A (table+columns) + Guard C (index pg_get_indexdef).
    V044 含 Guard A（table+欄）+ Guard C（index pg_get_indexdef）。
    """
    sql = _read_sql(V044_PATH)  # keep comments (Guard label in comment line)
    # Guard A label
    assert "Guard A:" in sql
    # information_schema query is the canonical Guard A pattern.
    assert "information_schema.tables" in sql
    # Guard C label + pg_get_indexdef
    assert "Guard C:" in sql
    assert "pg_get_indexdef" in sql


# ---------------------------------------------------------------------------
# Bonus: result + reject_reason CHECK enums
# ---------------------------------------------------------------------------


def test_v044_result_check_enum() -> None:
    """V044 ADDs CHECK chk_handoff_result enforcing 3-value enum.
    V044 加 CHECK chk_handoff_result 強制 3 值 enum。
    """
    sql = _strip_sql_comments(_read_sql(V044_PATH))
    assert "chk_handoff_result" in sql
    for status in ("success", "failed", "rejected"):
        assert f"'{status}'" in sql, f"V044 result enum missing: {status}"


def test_v044_reject_reason_allowlist() -> None:
    """V044 ADDs CHECK chk_handoff_reject_reason allowlisting 5 values + NULL.
    V044 加 CHECK chk_handoff_reject_reason 白名單 5 值 + NULL。
    """
    sql = _strip_sql_comments(_read_sql(V044_PATH))
    assert "chk_handoff_reject_reason" in sql
    for reason in (
        "phrase_format_invalid",
        "phrase_mismatch",
        "cooldown_in_progress",
        "experiment_not_found",
        "manifest_signature_failed",
    ):
        assert f"'{reason}'" in sql, f"V044 reject_reason missing: {reason}"
