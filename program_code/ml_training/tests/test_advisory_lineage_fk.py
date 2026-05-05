"""REF-20 Sprint C2 R7-T7 Part A — FK chain SQL acceptance test。

模組目的：
    對 ``learning.mlde_shadow_recommendations`` + ``replay.experiments``
    跨表 FK lineage 設置 SQL acceptance test，驗 V051 paired CHECK +
    V051 FK ON DELETE NO ACTION + V036 verify_replay_evidence_and_insert
    function 加 V055 fix 後維持的不變式：

      A10-1 paired CHECK：tier=calibrated_replay/synthetic_replay/
            counterfactual_replay → replay_experiment_id NOT NULL +
            manifest_hash NOT NULL（V051 paired CHECK 強制）。
      A10-2 TTL hard check：tier 非 real_outcome → JOIN replay.experiments
            取 expires_at（V049 source-of-truth），驗 row 仍未過期。
            **mlde_shadow_recommendations 表本無 expires_at column**
            （W6 R6-T9 verified），故 hard check 走 JOIN replay.experiments。
      A10-3 FK lineage：tier 非 real_outcome → replay_experiment_id 必
            指向 V049 row（V051 FK ON DELETE NO ACTION 保證 PG 層級）。

    本 test 為 SQL acceptance — 驗 SQL 字串 + caller 端 query 構造正確；
    真實 PG row 0 violation 驗證需 Real PG smoke (OPENCLAW_TEST_LIVE_PG=1
    opt-in)。

參考：
    - sql/migrations/V049__replay_experiments.sql line 305 (expires_at)
    - sql/migrations/V051__mlde_recommendations_replay_columns.sql line
      261-281 (FK + paired CHECK)
    - sql/migrations/V055__verify_replay_evidence_function_full_insert.sql
      (INSERT body 寫 3 column；expires_at 不在 mlde_shadow_recommendations
       — V049 source-of-truth)
    - AI-E advisory §9.4 SQL acceptance spec。

Hard contracts:
    - 純 SQL string 構造 + 真實 PG smoke opt-in。
    - 0 hardcoded path / 0 forbidden import。
    - mlde_shadow_recommendations.expires_at column 不存在 — A10-2 必經
      JOIN replay.experiments.expires_at 而非 row-level 直查（dispatch
      §1.2 注意明寫）。
"""

from __future__ import annotations

import os

import pytest


# ─── A10-1：paired CHECK SQL acceptance ─────────────────────────────────


def _build_a10_1_sql() -> str:
    """V051 paired CHECK acceptance：non-real_outcome tier → 兩 column NOT NULL。

    Per V051 line 278-281：
        CHECK (
          (evidence_source_tier = 'real_outcome' AND
           replay_experiment_id IS NULL AND
           manifest_hash IS NULL)
          OR
          (evidence_source_tier IN (...) AND
           replay_experiment_id IS NOT NULL AND
           manifest_hash IS NOT NULL)
        )

    返回 row count = 0 才合 paired CHECK 不變式。
    """
    return """
        SELECT COUNT(*) FROM learning.mlde_shadow_recommendations
        WHERE evidence_source_tier IN (
            'calibrated_replay', 'synthetic_replay', 'counterfactual_replay'
        )
          AND (replay_experiment_id IS NULL OR manifest_hash IS NULL);
    """


def test_a10_1_sql_string_paired_check_acceptance():
    """A10-1：paired CHECK SQL acceptance 字串可解析 + 結構正確。"""
    sql = _build_a10_1_sql()

    # 必含三 tier IN clause（calibrated/synthetic/counterfactual）
    assert "calibrated_replay" in sql
    assert "synthetic_replay" in sql
    assert "counterfactual_replay" in sql

    # 必驗 replay_experiment_id IS NULL OR manifest_hash IS NULL
    assert "replay_experiment_id IS NULL" in sql
    assert "manifest_hash IS NULL" in sql

    # 必使用 OR clause（兩 column 任一為 NULL 都違反 paired CHECK）
    assert " OR " in sql

    # 不應含 expires_at 直查（dispatch §1.2 注意：表本無此 column）
    # mlde_shadow_recommendations.expires_at 不存在
    assert "mlde_shadow_recommendations.expires_at" not in sql


# ─── A10-2：TTL hard check via JOIN replay.experiments ───────────────────


def _build_a10_2_sql() -> str:
    """A10-2：TTL hard check via JOIN replay.experiments.expires_at。

    Per dispatch §1.2 注意：mlde_shadow_recommendations 表本無 expires_at
    column；A10-2 SQL **必經 JOIN** replay.experiments 而非 row-level
    expires_at column 直查。

    返回 row count = 0 才合「non-real_outcome row 必指向 active manifest」
    invariant（V055 V036 verify input + Block B JOIN 雙層守門）。
    """
    return """
        SELECT COUNT(*) FROM learning.mlde_shadow_recommendations msr
        JOIN replay.experiments re ON msr.replay_experiment_id = re.experiment_id
        WHERE msr.evidence_source_tier != 'real_outcome'
          AND (re.expires_at IS NULL OR re.expires_at <= now());
    """


def test_a10_2_sql_string_ttl_via_join():
    """A10-2：TTL hard check SQL 必經 JOIN，不直查 row-level expires_at。"""
    sql = _build_a10_2_sql()

    # 必有 JOIN replay.experiments
    assert "JOIN replay.experiments" in sql

    # 必經 re.expires_at（V049 source-of-truth）
    assert "re.expires_at" in sql

    # 必比較 re.expires_at <= now() OR re.expires_at IS NULL
    assert "now()" in sql
    assert "IS NULL" in sql

    # 不應直查 msr.expires_at（mlde_shadow_recommendations 表本無此 column）
    assert "msr.expires_at" not in sql


# ─── A10-3：FK lineage validation（V051 FK ON DELETE NO ACTION）───────────


def _build_a10_3_sql() -> str:
    """A10-3：FK lineage validation。

    Per V051 line 261-263：
        ADD CONSTRAINT fk_mlde_shadow_replay_experiment
        FOREIGN KEY (replay_experiment_id)
        REFERENCES replay.experiments(experiment_id);

    返回 row count = 0 才合 FK ON DELETE NO ACTION（V051 enforced）。
    LEFT JOIN + experiment_id IS NULL → V049 row 不存在但 FK 指向 = error
    （但 V051 FK 預期阻 PG 層級 INSERT，故 row count 應 = 0）。
    """
    return """
        SELECT COUNT(*) FROM learning.mlde_shadow_recommendations msr
        LEFT JOIN replay.experiments re ON msr.replay_experiment_id = re.experiment_id
        WHERE msr.evidence_source_tier IN (
            'calibrated_replay', 'synthetic_replay', 'counterfactual_replay'
        )
          AND re.experiment_id IS NULL;
    """


def test_a10_3_sql_string_fk_lineage_validation():
    """A10-3：FK lineage SQL 必檢 LEFT JOIN + replay.experiments.experiment_id。"""
    sql = _build_a10_3_sql()

    # 必 LEFT JOIN replay.experiments
    assert "LEFT JOIN replay.experiments" in sql

    # 必驗 re.experiment_id IS NULL（FK orphan detection）
    assert "re.experiment_id IS NULL" in sql

    # 必含三 replay tier
    assert "calibrated_replay" in sql
    assert "synthetic_replay" in sql
    assert "counterfactual_replay" in sql

    # 必透 msr.replay_experiment_id JOIN
    assert "msr.replay_experiment_id" in sql


# ─── Real PG smoke (OPENCLAW_TEST_LIVE_PG=1 opt-in) ─────────────────────


@pytest.mark.skipif(
    os.environ.get("OPENCLAW_TEST_LIVE_PG") != "1",
    reason="real PG smoke opt-in via OPENCLAW_TEST_LIVE_PG=1",
)
def test_a10_real_pg_smoke_all_three_invariants_zero_violation():
    """Real PG smoke：A10-1/A10-2/A10-3 全 SQL 對 live PG 跑 → 0 violation。"""
    import psycopg2  # type: ignore

    dsn = os.environ.get(
        "OPENCLAW_TEST_PG_DSN",
        "dbname=trading_ai user=postgres host=127.0.0.1",
    )

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # A10-1 paired CHECK
            cur.execute(_build_a10_1_sql())
            row = cur.fetchone()
            paired_check_violations = int(row[0]) if row else -1
            assert paired_check_violations == 0, (
                f"A10-1 violation: {paired_check_violations} non-real_outcome row "
                f"with NULL replay_experiment_id or manifest_hash"
            )

            # A10-2 TTL hard check
            cur.execute(_build_a10_2_sql())
            row = cur.fetchone()
            ttl_violations = int(row[0]) if row else -1
            assert ttl_violations == 0, (
                f"A10-2 violation: {ttl_violations} non-real_outcome row "
                f"pointing at expired/NULL replay.experiments.expires_at"
            )

            # A10-3 FK lineage
            cur.execute(_build_a10_3_sql())
            row = cur.fetchone()
            fk_violations = int(row[0]) if row else -1
            assert fk_violations == 0, (
                f"A10-3 violation: {fk_violations} non-real_outcome row "
                f"FK orphan (replay_experiment_id 不指向 V049 row)"
            )


# ─── Schema doc cross-check：mlde_shadow_recommendations 確實無 expires_at 列 ──


@pytest.mark.skipif(
    os.environ.get("OPENCLAW_TEST_LIVE_PG") != "1",
    reason="real PG smoke opt-in via OPENCLAW_TEST_LIVE_PG=1",
)
def test_real_pg_smoke_mlde_shadow_recommendations_no_expires_at_column():
    """Real PG smoke：交叉驗 W6 R6-T9 的「expires_at column 不存在」事實。"""
    import psycopg2  # type: ignore

    dsn = os.environ.get(
        "OPENCLAW_TEST_PG_DSN",
        "dbname=trading_ai user=postgres host=127.0.0.1",
    )

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'learning'
                   AND table_name = 'mlde_shadow_recommendations'
                   AND column_name = 'expires_at';
                """
            )
            rows = cur.fetchall() or []
            # mlde_shadow_recommendations.expires_at column 不存在（W6 verified）
            # → A10-2 必經 JOIN 取 V049 expires_at
            assert len(rows) == 0, (
                "mlde_shadow_recommendations.expires_at column 意外存在；"
                "若已 land 需更新 A10-2 SQL 走 row-level 直查。"
                "預期：表本無 expires_at column（V055 fix 確認）"
            )


# ─── A10 contract documentation：V051 paired CHECK semantic 要求 ─────────


def test_a10_contract_documentation_consistency():
    """文檔級對齊：A10-1/A10-2/A10-3 SQL 與 V051 paired CHECK 同結構。

    V051 paired CHECK constraint chk_mlde_shadow_replay_lineage 的 SQL
    semantic：
      (real_outcome AND replay_experiment_id IS NULL AND manifest_hash IS NULL)
      OR
      (non-real_outcome AND replay_experiment_id IS NOT NULL AND manifest_hash IS NOT NULL)

    A10-1 acceptance SQL 必驗 inverse condition（non-real_outcome AND NULL
    fields）→ 0 row。
    """
    sql_a1 = _build_a10_1_sql()
    sql_a2 = _build_a10_2_sql()
    sql_a3 = _build_a10_3_sql()

    # 三 SQL 都必涵蓋三 replay tier
    for sql, label in [(sql_a1, "A10-1"), (sql_a3, "A10-3")]:
        assert "calibrated_replay" in sql, f"{label} 缺 calibrated_replay"
        assert "synthetic_replay" in sql, f"{label} 缺 synthetic_replay"
        assert "counterfactual_replay" in sql, f"{label} 缺 counterfactual_replay"

    # A10-2 用 != 'real_outcome' pattern（涵蓋三 replay tier 與其他 future tier）
    assert "!= 'real_outcome'" in sql_a2, "A10-2 應用 !=  pattern 涵蓋所有 replay tier"

    # 三 SQL 都應期望 row count = 0（acceptance SQL 不變式）
    assert "COUNT(*)" in sql_a1
    assert "COUNT(*)" in sql_a2
    assert "COUNT(*)" in sql_a3
