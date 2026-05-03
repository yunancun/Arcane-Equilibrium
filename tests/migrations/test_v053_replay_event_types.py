"""Mock-based unit tests for REF-20 Sprint 1 Track C V053 enum extension.

REF-20 Sprint 1 Track C V053 governance_audit_log event_type enum 的 mock
單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL file and verify the
structural contract:

1. V053 has Guard A (V035 base table existence check).
2. V053 DROPs + ADDs governance_audit_log_event_type_check with the
   canonical 14-value list including all 8 Sprint 1 replay event types.
3. V053 idempotency probe checks all 8 NEW enum values via position()
   so re-running the migration is a no-op.
4. V053 emits NOTICE messages for both the skip and add branches.

Linux Operator deploys with real psql + the Guard A runtime checks
defined in the SQL file. This test layer is the static compile-time
gate (E2 review-ready bundle on Mac dev).

Mac dev 測試層不對真實 PG 跑 psql；改靜態 parse migration SQL 驗結構契約。
Linux operator 部署時跑真 psql + Guard A 動態檢查。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v053_replay_event_types.py -v

References / 參考:
- docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md §"Track C"
- sql/migrations/REF-20_RESERVATION.md §3 V053 row + §6 v1.9 revision
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V053_PATH = _MIGRATIONS_DIR / "V053__governance_audit_log_replay_event_types.sql"


def _read_sql(path: Path) -> str:
    """Read full SQL file as text. / 讀取完整 SQL 檔為文字。"""
    assert path.exists(), f"Migration file missing: {path}"
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Remove `-- ...` line comments to avoid false-positive on doc text.
    去除 `-- ...` 行註解避免文字描述被 grep 誤命中。
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def test_v053_file_exists() -> None:
    """V053 migration file is present at the expected path.
    V053 migration 檔在預期路徑存在。
    """
    assert V053_PATH.exists(), f"V053 migration missing: {V053_PATH}"


def test_v053_guard_a_v035_base_table_check_present() -> None:
    """V053 contains Guard A: V035 governance_audit_log existence check.
    V053 含 Guard A：V035 governance_audit_log 存在性檢查。

    Without V035, V053's CHECK extension is meaningless; Guard A RAISEs
    EXCEPTION early so operator gets a clear deploy-order error.
    無 V035 時 V053 擴展無意義；Guard A 早期 RAISE 讓 operator 看清部署
    順序錯誤。
    """
    sql = _strip_sql_comments(_read_sql(V053_PATH))
    # Guard A presence: information_schema.tables probe + RAISE EXCEPTION.
    # Guard A 存在：information_schema.tables 探測 + RAISE EXCEPTION。
    assert "information_schema.tables" in sql
    assert "table_schema = 'learning'" in sql
    assert "table_name = 'governance_audit_log'" in sql
    assert "V053 Guard A" in sql or "RAISE EXCEPTION" in sql


def test_v053_drops_and_adds_event_type_check_canonical_list() -> None:
    """V053 DROPs existing event_type CHECK and ADDs canonical 14-value list.
    V053 DROP 既有 event_type CHECK 並 ADD canonical 14 值 list。
    """
    sql = _strip_sql_comments(_read_sql(V053_PATH))
    assert "ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS" in sql
    # canonical 14 enum values must all appear in the ADD CONSTRAINT body.
    # canonical 14 個 enum 值必皆出現於 ADD CONSTRAINT body。
    expected_values = [
        # V035 base 5 values.
        "'review_live_candidate'",
        "'lease_grant'",
        "'lease_auto_revoke'",
        "'bulk_re_evaluation'",
        "'audit_write_failed'",
        # V044 P6-S15.
        "'replay_handoff_request'",
        # V053 NEW (8 Sprint 1 Track A/C).
        "'replay_run_started'",
        "'replay_run_cancelled'",
        "'replay_manifest_verify_attempted'",
        "'replay_signature_test_key_blocked'",
        "'replay_pid_identity_mismatch'",
        "'replay_idor_admin_bypass'",
        "'replay_artifact_path_traversal_blocked'",
        "'replay_argv_mismatch_blocked'",
    ]
    for value in expected_values:
        assert value in sql, f"V053 missing enum value: {value}"


def test_v053_idempotency_probe_all_8_new_values() -> None:
    """V053 idempotency probe: position-check all 8 NEW enum values.
    V053 幂等探測：position-check 全部 8 個 NEW 值。

    Re-running the migration on an already-extended DB must be a no-op.
    The DO $$ block uses position() probes for each Sprint 1 NEW enum
    to detect prior application.
    重跑 migration 必為 no-op。DO $$ 用 position() 對 Sprint 1 NEW 8 enum
    偵測先前已應用。
    """
    sql = _strip_sql_comments(_read_sql(V053_PATH))
    # Idempotency check tokens: each NEW value must be position()'d in the
    # existing-CHECK probe. We accept any of the 8 values appearing inside
    # a `position(... IN v_check_def)` call.
    # 幂等檢查 token：每個 NEW 值必出現於 position() probe 內。
    new_values = [
        "replay_signature_test_key_blocked",
        "replay_pid_identity_mismatch",
        "replay_idor_admin_bypass",
        "replay_artifact_path_traversal_blocked",
        "replay_argv_mismatch_blocked",
        "replay_run_started",
        "replay_run_cancelled",
        "replay_manifest_verify_attempted",
    ]
    for value in new_values:
        # Find position("<value>" IN v_check_def) pattern (case-insensitive
        # whitespace-tolerant).
        # 找 position("<value>" IN v_check_def) pattern（容白空，case-insensitive）。
        assert re.search(
            rf"position\s*\(\s*'{re.escape(value)}'\s+IN\s+v_check_def\s*\)",
            sql,
            re.IGNORECASE,
        ), f"V053 missing idempotency position()-check for: {value}"


def test_v053_raise_notice_on_skip_and_add_branches() -> None:
    """V053 emits NOTICE on both 'already extended' and 'newly added' paths.
    V053 在「已擴」和「新加」兩分支均 emit NOTICE。
    """
    sql = _strip_sql_comments(_read_sql(V053_PATH))
    # The two NOTICE patterns: 'already extended' (skip) and '14-value' (add).
    # 兩 NOTICE pattern：「已擴」（skip）和「14-value」（add）。
    assert re.search(r"RAISE\s+NOTICE\s+'V053:\s*governance_audit_log\s+event_type", sql, re.IGNORECASE)
    assert re.search(r"RAISE\s+NOTICE\s+'V053:\s*added\s+event_type\s+CHECK", sql, re.IGNORECASE)


def test_v053_constraint_comment_describes_14_value_list() -> None:
    """V053 attaches a COMMENT ON CONSTRAINT describing the 14-value canonical list.
    V053 加 COMMENT ON CONSTRAINT 描述 14 值 canonical list。

    Improves DBA discoverability when inspecting via psql \\d+.
    透過 psql \\d+ 檢查時提升 DBA 發現性。
    """
    sql = _read_sql(V053_PATH)  # comment NOT stripped — we want the COMMENT body
    assert "COMMENT ON CONSTRAINT" in sql
    assert "governance_audit_log_event_type_check" in sql
    assert "14 值 canonical" in sql or "14-value canonical" in sql


def test_v053_e2_retrofit_f2_lock_table_access_exclusive_present() -> None:
    """E2 retrofit F2: V053 wraps DROP+ADD in BEGIN + ACCESS EXCLUSIVE LOCK.
    E2 retrofit F2：V053 用 BEGIN + ACCESS EXCLUSIVE LOCK 包裹 DROP+ADD。

    The original V053 IMPL emitted DROP+ADD outside any explicit
    transaction; concurrent INSERT could write any event_type during
    the gap (E3 P1-3 already flagged the V044 same-pattern bug). E2
    retrofit F2 wraps the pair in ``BEGIN; ... LOCK TABLE ... IN ACCESS
    EXCLUSIVE MODE; ... COMMIT;`` so concurrent writers block until
    the new CHECK commits — no "constraint absent" window.
    原 V053 IMPL 在無顯式 transaction 下 DROP+ADD；concurrent INSERT
    在 gap 內可寫任意 event_type（E3 P1-3 已 flag V044 同 pattern bug）。
    E2 retrofit F2 用 ``BEGIN; ... LOCK TABLE ... IN ACCESS EXCLUSIVE
    MODE; ... COMMIT;`` 包裹，concurrent writer 阻塞至新 CHECK commit
    — 無「無 constraint」窗口。
    """
    sql = _read_sql(V053_PATH)
    # E2 retrofit F2 contract: BEGIN + LOCK TABLE + COMMIT must wrap DROP+ADD.
    # E2 retrofit F2 契約：BEGIN + LOCK TABLE + COMMIT 包裹 DROP+ADD。
    assert "BEGIN;" in sql, "V053 must contain explicit BEGIN; for race-free DROP+ADD"
    assert "LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE" in sql, (
        "V053 must take ACCESS EXCLUSIVE on learning.governance_audit_log "
        "before DROP+ADD pair (E2 retrofit F2)"
    )
    assert "COMMIT;" in sql, "V053 must close BEGIN with explicit COMMIT;"
    # Lock + DROP + ADD must be in correct order (lock BEFORE the pair).
    # Lock + DROP + ADD 必為正確順序（lock 在對之前）。
    lock_pos = sql.find("LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE")
    drop_pos = sql.find("DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check")
    add_pos = sql.find("ADD CONSTRAINT governance_audit_log_event_type_check")
    assert lock_pos > 0
    assert drop_pos > 0
    assert add_pos > 0
    assert lock_pos < drop_pos, (
        f"LOCK TABLE must precede DROP CONSTRAINT; "
        f"got lock={lock_pos} drop={drop_pos}"
    )
    assert lock_pos < add_pos, (
        f"LOCK TABLE must precede ADD CONSTRAINT; "
        f"got lock={lock_pos} add={add_pos}"
    )
