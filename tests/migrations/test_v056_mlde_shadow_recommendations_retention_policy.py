"""Mock-based unit tests for REF-20 Sprint D R8 V056 retention policy.

REF-20 Sprint D R8 V056 retention policy migration 的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse the migration SQL file and verify the
structural contract:

1. V056 CREATE OR REPLACE FUNCTION learning.prune_mlde_shadow_recommendations
   with 4-arg signature (replay_retention_days, real_retention_days,
   apply, max_rows).
2. V056 schema preflight enforces V051 paired CHECK + V055 verify function +
   V038/V040 evidence_source_tier NOT NULL + V051 replay_experiment_id col.
3. V056 confirms NOT hypertable (RAISE if hypertable).
4. V056 Guard A: post-create function existence + 4-arg pronargs + identity
   args byte-equal expected pattern.
5. V056 boundary checks: replay_retention_days >= 1, real_retention_days >= 1,
   real_retention_days >= replay_retention_days; max_rows hard cap 100k.
6. V056 idempotency: CREATE OR REPLACE makes re-run safe.

Linux Operator deploys with real psql + the Guard A runtime checks defined
in the SQL files. This test layer is the static compile-time gate (E2
review-ready bundle on Mac dev).

Mac dev 測試層不對真實 PG 跑 psql；改靜態 parse migration SQL 驗結構契約。
Linux operator 部署時跑真 psql + Guard A 動態檢查。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v056_mlde_shadow_recommendations_retention_policy.py -v

References / 參考:
- docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md Sprint D R8 §6.R8 §1.2
- sql/migrations/V055__verify_replay_evidence_function_full_insert.sql
- sql/migrations/V051__mlde_recommendations_replay_columns.sql
- sql/migrations/REF-20_RESERVATION.md §3 V056
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

V056_PATH = _MIGRATIONS_DIR / "V056__mlde_shadow_recommendations_retention_policy.sql"


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
# Test 1: V056 file exists + module note + bilingual comments
# ---------------------------------------------------------------------------

def test_v056_file_exists_and_has_module_note() -> None:
    """V056 file is present and starts with bilingual MODULE_NOTE.
    V056 檔存在且有雙語 MODULE_NOTE。
    """
    sql = _read_sql(V056_PATH)
    # File contains REF-20 Sprint D R8 reference.
    # 檔含 REF-20 Sprint D R8 引用。
    assert "REF-20 Sprint D R8" in sql
    assert "retention policy" in sql.lower()
    # Bilingual: Chinese + English.
    # 雙語：中文 + 英文。
    assert "目的" in sql or "保留期" in sql, "V056 missing Chinese commentary"
    assert "Purpose" in sql or "retention" in sql.lower(), "V056 missing English commentary"


# ---------------------------------------------------------------------------
# Test 2: V056 creates prune_mlde_shadow_recommendations function
# ---------------------------------------------------------------------------

def test_v056_creates_prune_function() -> None:
    """V056 contains CREATE OR REPLACE FUNCTION
    learning.prune_mlde_shadow_recommendations with 4 args.
    V056 含 CREATE OR REPLACE FUNCTION 4-arg signature。
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))
    assert "CREATE OR REPLACE FUNCTION learning.prune_mlde_shadow_recommendations" in sql
    # Required args.
    assert "p_replay_retention_days INTEGER" in sql
    assert "p_real_retention_days INTEGER" in sql
    assert "p_apply BOOLEAN" in sql
    assert "p_max_rows INTEGER" in sql
    # SECURITY INVOKER (mirrors V036 pattern; not DEFINER).
    assert "SECURITY INVOKER" in sql
    # Returns table with tier / candidate_count / deleted_count columns.
    assert "RETURNS TABLE" in sql
    assert "tier TEXT" in sql
    assert "candidate_count BIGINT" in sql
    assert "deleted_count BIGINT" in sql


# ---------------------------------------------------------------------------
# Test 3: V056 schema preflight checks predecessor migrations
# ---------------------------------------------------------------------------

def test_v056_schema_preflight_validates_predecessors() -> None:
    """V056 preflight raises EXCEPTION when V051 paired CHECK / V055 function /
    V038-V040 evidence_source_tier NOT NULL / V051 replay_experiment_id col missing.

    V056 preflight 在 V051 paired CHECK / V055 function / V038-V040 / V051
    column 任一缺時 RAISE EXCEPTION。
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))
    # V051 paired CHECK preflight.
    assert "chk_mlde_shadow_replay_lineage" in sql
    assert "V051 must be applied" in sql
    # V038/V040 evidence_source_tier NOT NULL preflight.
    assert "evidence_source_tier" in sql
    assert "V038-V040 3-step retrofit must complete" in sql
    # V055 verify function preflight.
    assert "verify_replay_evidence_and_insert" in sql
    assert "V055 retrofit must be applied" in sql
    # V051 replay_experiment_id column preflight.
    assert "replay_experiment_id" in sql


# ---------------------------------------------------------------------------
# Test 4: V056 confirms NOT hypertable (defends design assumption)
# ---------------------------------------------------------------------------

def test_v056_confirms_not_hypertable() -> None:
    """V056 RAISE EXCEPTION if mlde_shadow_recommendations IS unexpectedly a
    hypertable (design assumes cron-driven DELETE, not add_retention_policy).

    V056 在表意外是 hypertable 時 RAISE（設計假設 cron-driven DELETE）。
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))
    assert "timescaledb_information.hypertables" in sql
    assert "unexpectedly" in sql or "unexpectedly IS a hypertable" in sql
    assert "add_retention_policy" in sql


# ---------------------------------------------------------------------------
# Test 5: V056 boundary checks for retention days args
# ---------------------------------------------------------------------------

def test_v056_boundary_checks_present() -> None:
    """V056 enforces:
    - p_replay_retention_days >= 1 day (prevents misconfigured cron clearing same-day)
    - p_real_retention_days >= 1 day
    - p_real_retention_days >= p_replay_retention_days (real is ground truth)
    - p_max_rows capped at 100000 per cycle (avoid long lock)

    V056 邊界檢查：
    - p_replay_retention_days >= 1（防誤配清當日樣本）
    - p_real_retention_days >= 1
    - p_real_retention_days >= p_replay_retention_days（real 是 ground truth）
    - p_max_rows 上限 100k（防長鎖）
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))

    # Boundary: replay >= 1.
    assert "p_replay_retention_days < 1" in sql
    # Boundary: real >= 1.
    assert "p_real_retention_days < 1" in sql
    # Boundary: real >= replay.
    assert (
        "p_real_retention_days < p_replay_retention_days" in sql
        or "p_real_retention_days <= p_replay_retention_days" in sql
    )
    # Hard cap on max_rows.
    assert "100000" in sql
    assert "v_max_rows_effective" in sql


# ---------------------------------------------------------------------------
# Test 6: V056 Guard A post-create function verification
# ---------------------------------------------------------------------------

def test_v056_guard_a_post_create_verification() -> None:
    """V056 Guard A: post-create function existence + 4-arg pronargs +
    identity_arguments byte-equal expected pattern.

    V056 Guard A：創建後驗證 function 存在 / pronargs=4 / identity_args 對齊。
    """
    sql_with_comments = _read_sql(V056_PATH)
    sql = _strip_sql_comments(sql_with_comments)

    # Guard A block named.
    assert "V056 Guard A" in sql_with_comments

    # Function existence post-create probe.
    assert "v_function_exists" in sql
    assert "prune_mlde_shadow_recommendations" in sql

    # pronargs == 4 enforce.
    assert "v_function_pronargs" in sql
    assert "pronargs <> 4" in sql or "pronargs = 4" in sql

    # identity_arguments check.
    assert "pg_get_function_identity_arguments" in sql
    assert "v_function_identity_args" in sql

    # Each of the 4 expected arg names verified.
    assert "p_replay_retention_days integer" in sql
    assert "p_real_retention_days integer" in sql
    assert "p_apply boolean" in sql
    assert "p_max_rows integer" in sql


# ---------------------------------------------------------------------------
# Test 7: V056 dry-run vs apply mode logic separation
# ---------------------------------------------------------------------------

def test_v056_dry_run_vs_apply_mode() -> None:
    """V056 splits dry-run (count only) and apply (DELETE) paths cleanly.
    V056 dry-run（只計數）與 apply（DELETE）路徑分離。
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))

    # IF p_apply branch.
    assert "IF p_apply THEN" in sql

    # Both replay-derived AND real_outcome DELETE paths in apply branch.
    # 兩 tier 的 DELETE path 都在 apply 分支。
    assert "DELETE FROM learning.mlde_shadow_recommendations" in sql
    # The DELETE filters on the 3 replay tiers.
    assert "calibrated_replay" in sql
    assert "synthetic_replay" in sql
    assert "counterfactual_replay" in sql
    # Real outcome separate cutoff.
    assert "real_outcome" in sql

    # Returns table separate replay_derived + real_outcome rows.
    assert "'replay_derived'::TEXT" in sql
    assert "'real_outcome'::TEXT" in sql


# ---------------------------------------------------------------------------
# Test 8: V056 idempotency via CREATE OR REPLACE
# ---------------------------------------------------------------------------

def test_v056_idempotent_via_create_or_replace() -> None:
    """V056 uses CREATE OR REPLACE FUNCTION for idempotent re-run.
    V056 用 CREATE OR REPLACE FUNCTION 確保 idempotent 重跑。
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))
    assert "CREATE OR REPLACE FUNCTION" in sql
    # Single function definition (no duplicate CREATE FUNCTION pattern).
    # 單一 function 定義（無重複 CREATE FUNCTION pattern）。
    assert sql.count("CREATE OR REPLACE FUNCTION learning.prune_mlde_shadow_recommendations") == 1


# ---------------------------------------------------------------------------
# Test 9: V056 LIMIT clause caps DELETE batch size
# ---------------------------------------------------------------------------

def test_v056_delete_uses_limit() -> None:
    """V056 DELETE uses LIMIT v_max_rows_effective (avoid long lock).
    V056 DELETE 用 LIMIT v_max_rows_effective（防長鎖）。
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))
    assert "LIMIT v_max_rows_effective" in sql


# ---------------------------------------------------------------------------
# Test 10: V056 COMMENT ON FUNCTION
# ---------------------------------------------------------------------------

def test_v056_comment_on_function_present() -> None:
    """V056 attaches COMMENT ON FUNCTION for psql \\df+ visibility.
    V056 加 COMMENT ON FUNCTION 供 psql \\df+ 顯示。
    """
    sql = _strip_sql_comments(_read_sql(V056_PATH))
    assert "COMMENT ON FUNCTION learning.prune_mlde_shadow_recommendations" in sql
    assert "V056 retention policy function" in sql or "Sprint D R8" in sql


# ---------------------------------------------------------------------------
# Test 11: V056 mentions sibling cron script
# ---------------------------------------------------------------------------

def test_v056_documents_sibling_cron() -> None:
    """V056 documents sibling cron script path.
    V056 文件 sibling cron script 路徑。
    """
    sql = _read_sql(V056_PATH)
    assert "mlde_shadow_recommendations_retention_cron.sh" in sql
    assert "helper_scripts/cron" in sql or "helper_scripts/db" in sql
