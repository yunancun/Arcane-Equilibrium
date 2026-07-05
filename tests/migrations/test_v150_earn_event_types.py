"""Mock-based unit tests for CC-3 / OOS-1 V150 earn event_type enum extension.

CC-3 / OOS-1 V150 governance_audit_log event_type enum 的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL file and verify the
structural contract:

1. V150 has Guard A (V035 base table existence check).
2. V150 has Guard B (V113 26-value baseline probe: halt_session_set +
   pg_dump_completed must exist before extending).
3. V150 DROPs + ADDs governance_audit_log_event_type_check with the
   canonical 28-value list including both earn approval event types.
4. V150 idempotency probe checks both NEW enum values via position()
   so re-running the migration is a no-op.
5. V150 wraps DROP+ADD in BEGIN + ACCESS EXCLUSIVE LOCK (E2 retrofit F2),
   with lock -> drop -> add in the correct order.

Linux Operator deploys with real psql + the Guard runtime checks defined
in the SQL file. This test layer is the static compile-time gate (E2
review-ready bundle on Mac dev).

Mac dev 測試層不對真實 PG 跑 psql；改靜態 parse migration SQL 驗結構契約。
Linux operator 部署時跑真 psql + Guard 動態檢查（Linux PG double-apply dry-run）。

Test invocation / 測試呼叫:
    pytest tests/migrations/test_v150_earn_event_types.py -q

References / 參考:
- docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-05--cc3_earn_governance_audit_id_chain_design.md §7
- sql/migrations/V113__governance_audit_log_pg_dump_event_types.sql (template)
"""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V150_PATH = _MIGRATIONS_DIR / "V150__governance_audit_log_earn_event_types.sql"


def _read_sql(path: Path) -> str:
    """Read full SQL file as text. / 讀取完整 SQL 檔為文字。"""
    assert path.exists(), f"Migration file missing: {path}"
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Remove `-- ...` line comments to avoid false-positive on doc text.
    去除 `-- ...` 行註解避免文字描述被 grep 誤命中。
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def test_v150_file_exists() -> None:
    """V150 migration file is present at the expected path.
    V150 migration 檔在預期路徑存在。
    """
    assert V150_PATH.exists(), f"V150 migration missing: {V150_PATH}"


def test_v150_guard_a_v035_base_table_check_present() -> None:
    """V150 contains Guard A: V035 governance_audit_log existence check.
    V150 含 Guard A：V035 governance_audit_log 存在性檢查。

    無 V035 時 V150 擴展無意義；Guard A 早期 RAISE 讓 operator 看清部署順序錯誤。
    """
    sql = _strip_sql_comments(_read_sql(V150_PATH))
    assert "information_schema.tables" in sql
    assert "table_schema = 'learning'" in sql
    assert "table_name = 'governance_audit_log'" in sql
    assert "V150 Guard A" in sql or "RAISE EXCEPTION" in sql


def test_v150_guard_b_v113_baseline_probe_present() -> None:
    """V150 contains Guard B: V113 26-value baseline probe.
    V150 含 Guard B：V113 26-value baseline 探測。

    以 halt_session_set（V098）+ pg_dump_completed（V113）substring 雙探，
    確保 V053/V054/V098/V113 enum 擴展鏈已 apply 才擴到 28-value。
    """
    sql = _strip_sql_comments(_read_sql(V150_PATH))
    assert "pg_get_constraintdef" in sql, (
        "V150 Guard B must probe existing CHECK def via pg_get_constraintdef"
    )
    # halt_session_set (V098) + pg_dump_completed (V113) 皆須被 Guard B 探測。
    assert re.search(
        r"position\s*\(\s*'halt_session_set'\s+IN\s+v_check_def\s*\)",
        sql,
        re.IGNORECASE,
    ), "V150 Guard B must position()-probe halt_session_set (V098 baseline)"
    assert re.search(
        r"position\s*\(\s*'pg_dump_completed'\s+IN\s+v_check_def\s*\)",
        sql,
        re.IGNORECASE,
    ), "V150 Guard B must position()-probe pg_dump_completed (V113 baseline)"
    assert "V150 Guard B" in sql, "V150 Guard B must RAISE with a V150 Guard B tag"


def test_v150_drops_and_adds_event_type_check_canonical_28_value_list() -> None:
    """V150 DROPs existing event_type CHECK and ADDs canonical 28-value list.
    V150 DROP 既有 event_type CHECK 並 ADD canonical 28 值 list。
    """
    sql = _strip_sql_comments(_read_sql(V150_PATH))
    assert "ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS" in sql
    assert "ADD CONSTRAINT governance_audit_log_event_type_check" in sql
    # canonical 28 enum values must all appear in the ADD CONSTRAINT body.
    # canonical 28 個 enum 值必皆出現於 ADD CONSTRAINT body。
    expected_values = [
        # V113 26-value canonical (V053 14 + V054 7 + V098 3 + V113 2).
        "'review_live_candidate'",
        "'lease_grant'",
        "'lease_auto_revoke'",
        "'bulk_re_evaluation'",
        "'audit_write_failed'",
        "'replay_handoff_request'",
        "'replay_run_started'",
        "'replay_run_cancelled'",
        "'replay_manifest_verify_attempted'",
        "'replay_signature_test_key_blocked'",
        "'replay_pid_identity_mismatch'",
        "'replay_idor_admin_bypass'",
        "'replay_artifact_path_traversal_blocked'",
        "'replay_argv_mismatch_blocked'",
        "'lease_acquire_request'",
        "'lease_acquire_success'",
        "'lease_acquire_fail'",
        "'lease_release_consumed'",
        "'lease_release_failed'",
        "'lease_release_cancelled'",
        "'lease_sm_transition'",
        "'halt_session_set'",
        "'halt_session_auto_cleared'",
        "'halt_session_manual_cleared'",
        "'pg_dump_completed'",
        "'pg_dump_failed'",
        # V150 NEW (CC-3 / OOS-1).
        "'earn_stake_approval'",
        "'earn_redeem_approval'",
    ]
    for value in expected_values:
        assert value in sql, f"V150 missing enum value: {value}"


def test_v150_idempotency_probe_both_new_earn_values() -> None:
    """V150 idempotency probe: position-check both NEW earn enum values.
    V150 幂等探測：position-check 兩個 NEW earn 值。

    重跑 migration 必為 no-op。DO $$ 用 position() 對 earn_stake_approval /
    earn_redeem_approval 偵測先前已應用。
    """
    sql = _strip_sql_comments(_read_sql(V150_PATH))
    for value in ["earn_stake_approval", "earn_redeem_approval"]:
        assert re.search(
            rf"position\s*\(\s*'{re.escape(value)}'\s+IN\s+v_check_def\s*\)",
            sql,
            re.IGNORECASE,
        ), f"V150 missing idempotency position()-check for: {value}"


def test_v150_raise_notice_on_skip_and_add_branches() -> None:
    """V150 emits NOTICE on both 'already present' (skip) and 'added' paths.
    V150 在「已擴」（skip）和「新加」兩分支均 emit NOTICE。
    """
    sql = _strip_sql_comments(_read_sql(V150_PATH))
    assert re.search(
        r"RAISE\s+NOTICE\s+'V150:.*skipping", sql, re.IGNORECASE
    ), "V150 must RAISE NOTICE on the idempotent skip branch"
    assert re.search(
        r"RAISE\s+NOTICE\s+'V150:\s*added\s+2\s+earn", sql, re.IGNORECASE
    ), "V150 must RAISE NOTICE on the add branch"


def test_v150_constraint_comment_describes_28_value_list() -> None:
    """V150 attaches a COMMENT ON CONSTRAINT describing the 28-value list.
    V150 加 COMMENT ON CONSTRAINT 描述 28 值 canonical list。
    """
    sql = _read_sql(V150_PATH)  # comment NOT stripped — we want the COMMENT body
    assert "COMMENT ON CONSTRAINT" in sql
    assert "governance_audit_log_event_type_check" in sql
    assert "28-value" in sql or "28 值" in sql


def test_v150_e2_retrofit_f2_lock_table_access_exclusive_present() -> None:
    """E2 retrofit F2: V150 wraps DROP+ADD in BEGIN + ACCESS EXCLUSIVE LOCK.
    E2 retrofit F2：V150 用 BEGIN + ACCESS EXCLUSIVE LOCK 包裹 DROP+ADD。

    concurrent INSERT 在 DROP+ADD gap 內可寫任意 event_type；ACCESS EXCLUSIVE
    lock 令 concurrent writer 阻塞至新 CHECK commit — 無「無 constraint」窗口。
    """
    sql = _read_sql(V150_PATH)
    assert "BEGIN;" in sql, "V150 must contain explicit BEGIN; for race-free DROP+ADD"
    assert "LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE" in sql, (
        "V150 must take ACCESS EXCLUSIVE on learning.governance_audit_log "
        "before DROP+ADD pair (E2 retrofit F2)"
    )
    assert "COMMIT;" in sql, "V150 must close BEGIN with explicit COMMIT;"
    # Lock + DROP + ADD must be in correct order (lock BEFORE the pair).
    # Lock + DROP + ADD 必為正確順序（lock 在對之前）。
    lock_pos = sql.find("LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE")
    drop_pos = sql.find("DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check")
    add_pos = sql.find("ADD CONSTRAINT governance_audit_log_event_type_check")
    assert lock_pos > 0
    assert drop_pos > 0
    assert add_pos > 0
    assert lock_pos < drop_pos, (
        f"LOCK TABLE must precede DROP CONSTRAINT; got lock={lock_pos} drop={drop_pos}"
    )
    assert lock_pos < add_pos, (
        f"LOCK TABLE must precede ADD CONSTRAINT; got lock={lock_pos} add={add_pos}"
    )
