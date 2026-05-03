"""Mock-based unit tests for REF-20 Sprint 1 Track D V049/V050/V051/V052.

REF-20 Sprint 1 Track D V049/V050/V051/V052 的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer;
instead we statically parse each migration SQL file and verify the
structural contract:

  - V049 promotes replay.experiments from V041 4-col stub to V3 §4.1 22 col;
    aligns experiment_id type to UUID; adds 3 hot-path indexes; declares
    intra-row 3-pair window non-overlap CHECK and EXCLUDE GIST.
  - V050 creates replay.simulated_fills with FK to V049 + 5 CHECK
    constraints + UNIQUE(experiment_id, idempotency_key) + 3 hot-path
    indexes (one partial).
  - V051 ADDs replay_experiment_id (uuid) + manifest_hash (bytea) to
    learning.mlde_shadow_recommendations; ADDs paired CHECK
    chk_mlde_shadow_replay_lineage that enforces V3 §4.2 lineage
    invariant + FK to replay.experiments.
  - V052 ALTERs V045/V046 to ADD FK to V049 (forward-only; not editing
    V045/V046 file). V046 ADDs experiment_id column with backfill from
    V045.manifest_id via run_id JOIN. Preflight LEFT JOIN dangling check.

Linux operator deploys with real psql + the Guard A/B/C runtime checks
defined in the SQL files. This test layer is the static compile-time
gate (E2 review-ready bundle on Mac dev).

Mac dev 測試層不對真實 PG 跑 psql；改靜態 parse migration SQL 驗結構契約。
Linux operator 部署時跑真 psql + Guard A/B/C 動態檢查。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v049_v050_v051_v052_track_d.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
  §4.1 + §4.2
- docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
  §2 Track D
- sql/migrations/REF-20_RESERVATION.md §3 V049 / V050 / V051 / V052
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

V049_PATH = _MIGRATIONS_DIR / "V049__replay_experiments.sql"
V050_PATH = _MIGRATIONS_DIR / "V050__replay_simulated_fills.sql"
V051_PATH = _MIGRATIONS_DIR / "V051__mlde_recommendations_replay_columns.sql"
V052_PATH = _MIGRATIONS_DIR / "V052__replay_run_state_artifacts_fk_redirect.sql"
V052_PREFLIGHT_PATH = _MIGRATIONS_DIR / "V052_preflight.sql"


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
# V049 tests / V049 測試
# ---------------------------------------------------------------------------


def test_v049_promotes_replay_experiments_to_22_columns() -> None:
    """V049 declares all 18 new V3 §4.1 columns (4 already in V041 stub).
    V049 宣告 18 新 V3 §4.1 column（V041 stub 已有 4 個）。
    """
    sql = _strip_sql_comments(_read_sql(V049_PATH))
    new_cols = [
        "parent_experiment_id",
        "created_by",
        "runtime_environment",
        "git_sha",
        "engine_binary_sha",
        "strategy_config_sha256",
        "risk_config_sha256",
        "timeframe",
        "data_tier",
        "execution_confidence",
        "calibration_train_window_start",
        "calibration_train_window_end",
        "oos_label_window_start",
        "oos_label_window_end",
        "candidate_window_start",
        "candidate_window_end",
        "oos_embargo_seconds",
        "total_candidates_K",
        "manifest_jsonb",
        "manifest_hash",
        "manifest_signature",
        "signature_key_ref",
        "expires_at",
        "status",
        "output_policy_jsonb",
    ]
    for col in new_cols:
        assert col in sql, f"V049 missing column ADD: {col}"


def test_v049_alters_experiment_id_to_uuid() -> None:
    """V049 ALTERs experiment_id from TEXT to UUID, aligned to V045/V046.
    V049 把 experiment_id 從 TEXT 對齊為 UUID（V045/V046 既已 UUID）。
    """
    sql = _strip_sql_comments(_read_sql(V049_PATH))
    assert "ALTER COLUMN experiment_id TYPE UUID" in sql
    assert "USING experiment_id::uuid" in sql


def test_v049_window_constraints_present() -> None:
    """V049 declares window order CHECK + intra-row pairwise non-overlap.
    V049 宣告 window 順序 CHECK + intra-row 兩兩不重疊。
    """
    sql = _strip_sql_comments(_read_sql(V049_PATH))
    assert "chk_replay_experiments_window_order" in sql
    assert "chk_replay_experiments_window_no_overlap" in sql
    assert "tstzrange(" in sql
    # EXCLUDE GIST defense-in-depth (degraded gracefully if btree_gist absent).
    # EXCLUDE GIST 防禦深度（btree_gist 缺時 graceful degrade）。
    assert "excl_replay_experiments_candidate_window_per_id" in sql
    assert "EXCLUDE USING gist" in sql
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in sql


def test_v049_conditional_engine_sha_check() -> None:
    """V049 enforces engine_binary_sha NOT NULL when runtime=linux_trade_core.
    V049 強制 runtime=linux_trade_core 時 engine_binary_sha NOT NULL。
    """
    sql = _strip_sql_comments(_read_sql(V049_PATH))
    assert "chk_replay_experiments_engine_sha_linux" in sql
    assert "linux_trade_core" in sql
    assert "engine_binary_sha IS NOT NULL" in sql


def test_v049_three_hot_path_indexes() -> None:
    """V049 has 3 hot-path indexes via Guard C pattern.
    V049 有 3 個 hot-path 索引透過 Guard C pattern。
    """
    sql = _strip_sql_comments(_read_sql(V049_PATH))
    indexes = [
        "idx_replay_experiments_status",
        "idx_replay_experiments_created_by_status",
        "idx_replay_experiments_expires_at",
    ]
    for idx in indexes:
        assert idx in sql, f"V049 missing index Guard C: {idx}"


def test_v049_self_fk_parent_experiment() -> None:
    """V049 declares self-FK on parent_experiment_id for lineage.
    V049 宣告 parent_experiment_id 自引 FK（lineage）。
    """
    sql = _strip_sql_comments(_read_sql(V049_PATH))
    assert "fk_replay_experiments_parent" in sql
    assert "REFERENCES replay.experiments(experiment_id)" in sql
    assert "ON DELETE SET NULL" in sql


# ---------------------------------------------------------------------------
# V050 tests / V050 測試
# ---------------------------------------------------------------------------


def test_v050_creates_simulated_fills_with_fk_to_v049() -> None:
    """V050 CREATE TABLE replay.simulated_fills with FK to V049 ON DELETE CASCADE.
    V050 CREATE TABLE replay.simulated_fills 並 FK 至 V049 ON DELETE CASCADE。
    """
    sql = _strip_sql_comments(_read_sql(V050_PATH))
    assert "CREATE TABLE IF NOT EXISTS replay.simulated_fills" in sql
    assert "REFERENCES replay.experiments(experiment_id) ON DELETE CASCADE" in sql


def test_v050_required_columns_complete() -> None:
    """V050 declares all V3 §4.1 17 required columns.
    V050 宣告 V3 §4.1 17 個必要 column。
    """
    sql = _strip_sql_comments(_read_sql(V050_PATH))
    required_cols = [
        "sim_fill_id",
        "experiment_id",
        "intent_id",
        "decision_lease_id",
        "idempotency_key",
        "ts",
        "ts_ms",
        "symbol",
        "strategy_name",
        "side",
        "qty",
        "price",
        "fee",
        "fee_rate",
        "liquidity_role",
        "evidence_source_tier",
        "execution_model_version",
        "ci_low_bps",
        "ci_mid_bps",
        "ci_high_bps",
        "payload",
    ]
    for col in required_cols:
        assert col in sql, f"V050 missing column: {col}"


def test_v050_check_constraints_complete() -> None:
    """V050 declares all 5 CHECK constraints + UNIQUE.
    V050 宣告 5 個 CHECK 約束 + UNIQUE。
    """
    sql = _strip_sql_comments(_read_sql(V050_PATH))
    constraints = [
        "chk_replay_simulated_fills_side",
        "chk_replay_simulated_fills_liquidity_role",
        "chk_replay_simulated_fills_evidence_tier",
        "chk_replay_simulated_fills_qty_price",
        "chk_replay_simulated_fills_ci_order",
        "uq_replay_simulated_fills_idempotency_per_experiment",
    ]
    for c in constraints:
        assert c in sql, f"V050 missing constraint: {c}"


def test_v050_evidence_tier_excludes_real_outcome() -> None:
    """V050 evidence_source_tier CHECK only allows replay-derived 3 values.
    V050 evidence_source_tier CHECK 只允許 replay 衍生 3 值（不含 real_outcome）。
    """
    sql = _strip_sql_comments(_read_sql(V050_PATH))
    # The CHECK enum should contain replay tiers but not 'real_outcome'.
    # 找到 chk_replay_simulated_fills_evidence_tier 的 CHECK 內容。
    m = re.search(
        r"chk_replay_simulated_fills_evidence_tier\s*\n?\s*CHECK\s*\(([^)]+)\)",
        sql,
        re.IGNORECASE,
    )
    assert m is not None, "V050 evidence_tier CHECK not located"
    enum_body = m.group(1)
    assert "calibrated_replay" in enum_body
    assert "synthetic_replay" in enum_body
    assert "counterfactual_replay" in enum_body
    assert "real_outcome" not in enum_body, (
        "V050 must NOT allow real_outcome (reserved for mlde real-fill rows)"
    )


def test_v050_three_hot_path_indexes() -> None:
    """V050 has 3 hot-path indexes including 1 partial.
    V050 有 3 hot-path 索引含 1 個 partial。
    """
    sql = _strip_sql_comments(_read_sql(V050_PATH))
    indexes = [
        "idx_replay_simulated_fills_experiment_ts",
        "idx_replay_simulated_fills_symbol_strategy_ts",
        "idx_replay_simulated_fills_intent_id",
    ]
    for idx in indexes:
        assert idx in sql, f"V050 missing index: {idx}"
    # Partial WHERE clause for intent_id
    assert "WHERE intent_id IS NOT NULL" in sql


# ---------------------------------------------------------------------------
# V051 tests / V051 測試
# ---------------------------------------------------------------------------


def test_v051_adds_two_replay_columns() -> None:
    """V051 ADDs replay_experiment_id (uuid) + manifest_hash (bytea).
    V051 加 replay_experiment_id (uuid) + manifest_hash (bytea) 兩欄。
    """
    sql = _strip_sql_comments(_read_sql(V051_PATH))
    assert "ADD COLUMN IF NOT EXISTS replay_experiment_id UUID" in sql
    assert "ADD COLUMN IF NOT EXISTS manifest_hash" in sql
    assert "BYTEA" in sql


def test_v051_paired_check_v3_42_lineage() -> None:
    """V051 declares paired CHECK chk_mlde_shadow_replay_lineage per V3 §4.2.
    V051 宣告配對 CHECK chk_mlde_shadow_replay_lineage 符合 V3 §4.2 規範。
    """
    sql = _strip_sql_comments(_read_sql(V051_PATH))
    assert "chk_mlde_shadow_replay_lineage" in sql
    # The paired CHECK SQL body should contain both branches per V3 §4.2.
    # 配對 CHECK 兩分支按 V3 §4.2 規範。
    m = re.search(
        r"chk_mlde_shadow_replay_lineage\s*\n?\s*CHECK\s*\((.+?)\);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert m is not None, "V051 chk_mlde_shadow_replay_lineage CHECK body not located"
    check_body = m.group(1)
    # Branch 1: real_outcome → both NULL
    assert "evidence_source_tier = 'real_outcome'" in check_body
    assert "replay_experiment_id IS NULL" in check_body
    assert "manifest_hash IS NULL" in check_body
    # Branch 2: not real_outcome → both NOT NULL
    assert "evidence_source_tier <> 'real_outcome'" in check_body
    assert "replay_experiment_id IS NOT NULL" in check_body
    assert "manifest_hash IS NOT NULL" in check_body


def test_v051_fk_to_v049() -> None:
    """V051 declares FK fk_mlde_shadow_replay_experiment to V049 ON DELETE NO ACTION.
    V051 宣告 FK fk_mlde_shadow_replay_experiment 至 V049 ON DELETE NO ACTION。

    Why NO ACTION (not SET NULL): paired CHECK chk_mlde_shadow_replay_lineage
    forbids {non-real_outcome tier + replay_experiment_id NULL} combo. SET
    NULL would cascade fail the CHECK; NO ACTION blocks the parent DELETE
    explicitly which is the correct semantic for an immutable manifest
    registry.

    為何 NO ACTION（非 SET NULL）：配對 CHECK 禁 {非 real_outcome + NULL}
    組合；SET NULL 觸 CHECK 失敗。NO ACTION 直接擋 parent DELETE，更符合
    manifest registry 不可變的語意。
    """
    sql = _strip_sql_comments(_read_sql(V051_PATH))
    assert "fk_mlde_shadow_replay_experiment" in sql
    assert "REFERENCES replay.experiments(experiment_id)" in sql
    assert "ON DELETE NO ACTION" in sql


def test_v051_guard_a_v049_pk_uuid_check() -> None:
    """V051 Guard A verifies V049 experiment_id is uuid before adding FK.
    V051 Guard A 驗 V049 experiment_id 為 uuid 才加 FK。
    """
    sql = _strip_sql_comments(_read_sql(V051_PATH))
    # Should mention uuid expected and V049 FK target check.
    # 應提及預期 uuid 與 V049 FK 目標檢查。
    assert "expected uuid" in sql or "v_v049_pk_type <> 'uuid'" in sql


# ---------------------------------------------------------------------------
# V052 tests / V052 測試
# ---------------------------------------------------------------------------


def test_v052_adds_v045_fk_without_editing_v045() -> None:
    """V052 ADDs FK on V045.manifest_id forward-only (not editing V045 file).
    V052 forward-only 加 V045.manifest_id FK（不改 V045 file）。
    """
    sql = _strip_sql_comments(_read_sql(V052_PATH))
    assert "fk_replay_run_state_manifest_id" in sql
    assert "ALTER TABLE replay.run_state" in sql
    assert "ON DELETE RESTRICT" in sql


def test_v052_adds_v046_experiment_id_column_and_fk() -> None:
    """V052 ADDs V046.experiment_id column + backfill via run_state JOIN + FK.
    V052 加 V046.experiment_id column + 透過 run_state JOIN backfill + FK。
    """
    sql = _strip_sql_comments(_read_sql(V052_PATH))
    assert "ALTER TABLE replay.report_artifacts" in sql
    assert "ADD COLUMN IF NOT EXISTS experiment_id UUID" in sql
    # backfill via JOIN to run_state.manifest_id
    assert "FROM replay.run_state r" in sql
    assert "WHERE a.run_id = r.run_id" in sql
    # FK to V049
    assert "fk_replay_report_artifacts_experiment_id" in sql
    assert "ON DELETE CASCADE" in sql


def test_v052_preflight_dangling_row_raise() -> None:
    """V052 preflight LEFT JOIN catches V045 dangling rows; raises if >0.
    V052 preflight LEFT JOIN 抓 V045 懸空 row；> 0 RAISE。
    """
    sql = _strip_sql_comments(_read_sql(V052_PATH))
    # The preflight DO block should contain LEFT JOIN, COUNT, RAISE EXCEPTION.
    # preflight DO block 應含 LEFT JOIN、COUNT、RAISE EXCEPTION。
    assert "LEFT JOIN replay.experiments e" in sql
    assert "v_v045_dangling > 0" in sql
    assert "Operator decision required" in sql


def test_v052_does_not_edit_v045_v046_files() -> None:
    """V052 must not change V045/V046 file content (P0 sqlx hash drift avoidance).
    V052 不改 V045/V046 file（避觸 P0 sqlx hash drift incident）。

    We verify by reading V045/V046 files directly and confirming they don't
    contain V052-specific FK declarations.

    我們透過直接讀 V045/V046 file 確認其不含 V052 專屬 FK 宣告以驗證。
    """
    v045_sql = _read_sql(_MIGRATIONS_DIR / "V045__replay_run_state.sql")
    v046_sql = _read_sql(_MIGRATIONS_DIR / "V046__replay_report_artifacts.sql")
    # V045 must not declare fk_replay_run_state_manifest_id (V052 owns it).
    # V046 must not declare fk_replay_report_artifacts_experiment_id (V052 owns it).
    assert "fk_replay_run_state_manifest_id" not in v045_sql, (
        "V045 file edited; this would re-trigger P0 sqlx hash drift incident"
    )
    assert "fk_replay_report_artifacts_experiment_id" not in v046_sql, (
        "V046 file edited; this would re-trigger P0 sqlx hash drift incident"
    )


def test_v052_preflight_helper_sql_present() -> None:
    """V052_preflight.sql is present alongside V052 with 5 read-only probes.
    V052_preflight.sql 與 V052 同 commit，含 5 個 read-only probe。
    """
    sql = _read_sql(V052_PREFLIGHT_PATH)
    # 5 probes per the file's spec.
    # 5 個 probe 按檔案規格。
    assert "Probe 1" in sql
    assert "Probe 2" in sql
    assert "Probe 3" in sql
    assert "Probe 4" in sql
    assert "Probe 5" in sql
    # No DDL in healthcheck (read-only).
    # healthcheck 無 DDL（純讀）。
    sql_no_comments = _strip_sql_comments(sql)
    assert "ALTER TABLE" not in sql_no_comments
    assert "CREATE TABLE" not in sql_no_comments
    assert "DROP TABLE" not in sql_no_comments


# ---------------------------------------------------------------------------
# Cross-file invariants / 跨檔不變量
# ---------------------------------------------------------------------------


def test_dual_language_module_note_in_all_v_files() -> None:
    """All four V### files have bilingual MODULE_NOTE per CLAUDE.md §七.
    所有 4 個 V### file 含中英 MODULE_NOTE，符合 CLAUDE.md §七。
    """
    for path in (V049_PATH, V050_PATH, V051_PATH, V052_PATH):
        sql = _read_sql(path)
        # Each migration starts with Purpose / 目的 dual-language header.
        assert "Purpose / 目的" in sql, f"{path.name} missing bilingual Purpose"
        # Spec source citation present.
        assert "Spec source / 規格來源" in sql, (
            f"{path.name} missing Spec source citation"
        )


def test_no_user_home_path_hardcoded() -> None:
    """No user-home path hardcoded in V049-V052 (CLAUDE.md §七 cross-platform).
    V049-V052 0 個 user-home 路徑硬編碼（CLAUDE.md §七 跨平台）。
    """
    pattern = re.compile(r"/home/ncyu|/Users/[^/]+")
    for path in (V049_PATH, V050_PATH, V051_PATH, V052_PATH, V052_PREFLIGHT_PATH):
        sql = _read_sql(path)
        m = pattern.search(sql)
        assert m is None, (
            f"{path.name} has hardcoded user-home path: {m.group(0)} at "
            f"position {m.start()}"
        )


def test_no_trading_or_live_mutation_in_v_files() -> None:
    """V049-V052 do not INSERT / UPDATE / DELETE trading.* or live_*.
    V049-V052 不 INSERT / UPDATE / DELETE trading.* 或 live_*。

    V052 has UPDATE replay.report_artifacts (backfill); that's allowed.
    V049-V051 are pure DDL.

    V052 有 UPDATE replay.report_artifacts（backfill）允許。
    V049-V051 純 DDL。
    """
    forbidden_pat = re.compile(
        r"\b(INSERT INTO trading|UPDATE trading|DELETE FROM trading|"
        r"INSERT INTO live_|UPDATE live_|DELETE FROM live_)",
        re.IGNORECASE,
    )
    for path in (V049_PATH, V050_PATH, V051_PATH, V052_PATH, V052_PREFLIGHT_PATH):
        sql = _strip_sql_comments(_read_sql(path))
        m = forbidden_pat.search(sql)
        assert m is None, (
            f"{path.name} has forbidden trading/live mutation: {m.group(0)}"
        )


def test_no_hard_boundary_columns_touched() -> None:
    """V049-V052 do not touch hard-boundary columns (max_retries / live_*).
    V049-V052 不觸碰硬邊界 column（max_retries / live_execution_allowed
    / execution_authority / system_mode）。
    """
    forbidden = [
        "max_retries",
        "live_execution_allowed",
        "execution_authority",
        "system_mode",
        "OPENCLAW_ALLOW_MAINNET",
    ]
    for path in (V049_PATH, V050_PATH, V051_PATH, V052_PATH, V052_PREFLIGHT_PATH):
        sql = _strip_sql_comments(_read_sql(path))
        for kw in forbidden:
            assert kw not in sql, (
                f"{path.name} touches hard-boundary keyword: {kw}"
            )
