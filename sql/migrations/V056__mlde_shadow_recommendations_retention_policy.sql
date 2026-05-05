-- V056__mlde_shadow_recommendations_retention_policy.sql
-- REF-20 Sprint D R8 (maintenance / retention policy)
--
-- 目的 / Purpose:
--   為 `learning.mlde_shadow_recommendations` 上 replay-derived row 加 30 天
--   保留期 + real_outcome row 加 90 天保留期。透過 cron-driven DELETE 函數
--   執行（本表非 hypertable，故不能用 TimescaleDB add_retention_policy）。
--
--   Sprint C R7 已實裝 evidence_source_tier 4-value enum 配 V051 paired
--   CHECK；3 producer (dream_engine / ml_shadow / opportunity_tracker)
--   寫入 calibrated_replay/synthetic_replay/counterfactual_replay 路徑。
--   隨 replay row 累積，無 retention policy 表會無界增長 + ML training
--   surface 被舊 stale row 拉低 signal。MIT §2.4 推薦：replay-derived
--   30-60d / real_outcome 90d 維持 ML training data quality。
--
--   PM 設計選擇 30d (replay) + 90d (real_outcome) 中位值；可由 cron 環境
--   變數 OPENCLAW_MLDE_REPLAY_RETENTION_DAYS / OPENCLAW_MLDE_REAL_RETENTION_DAYS
--   調整（sibling cron `mlde_shadow_recommendations_retention_cron.sh`）。
--
--   Add 30-day retention for replay-derived rows + 90-day retention for
--   real_outcome rows on `learning.mlde_shadow_recommendations`. Implemented
--   via cron-driven DELETE function (table is NOT a hypertable, so cannot
--   use TimescaleDB ``add_retention_policy``).
--
--   Sprint C R7 landed evidence_source_tier 4-value enum + V051 paired CHECK;
--   3 producers (dream_engine / ml_shadow / opportunity_tracker) emit rows
--   via calibrated_replay/synthetic_replay/counterfactual_replay path.
--   Without retention policy the table grows unbounded + ML training surface
--   is diluted by stale replay rows. MIT §2.4 recommends 30-60d for
--   replay-derived / 90d for real_outcome to maintain ML training data
--   quality.
--
--   PM design choice: 30d (replay) + 90d (real_outcome) midpoint values;
--   tunable via env var OPENCLAW_MLDE_REPLAY_RETENTION_DAYS /
--   OPENCLAW_MLDE_REAL_RETENTION_DAYS in sibling cron
--   ``mlde_shadow_recommendations_retention_cron.sh``.
--
-- 何時 apply / When to apply:
--   Sprint D R8 maintenance pass。先 land V056 → 安裝 cron → operator 觀察
--   1 cycle 後啟用 apply mode（dry-run 默認）。
--
-- Migration order / 遷移順序:
--   V038 → V039 → V040 (evidence_source_tier 3-step retrofit)
--   → V051 (replay metadata columns + paired CHECK)
--   → V055 (V036 PR3 retrofit, 3-column INSERT body)
--   → V056 (this; retention policy function only — no schema change)
--
-- Idempotency / 幂等性:
--   `CREATE OR REPLACE FUNCTION` 重跑時覆寫舊 body。
--   Guard A function existence + 4-arg signature check 重跑無 RAISE。
--   `CREATE OR REPLACE FUNCTION` overwrites previous body on re-run.
--   Guard A function existence + 4-arg signature check no-op on re-run.
--
-- Guard A: enforced (V051 paired CHECK existence + V055 verify function
--          existence pre-condition; ensures retention runs against
--          full-metadata table state).
-- Guard B: N/A (no ALTER COLUMN; function-only DDL).
-- Guard C: N/A (no index DDL).
--
-- 規格來源 / Spec source:
--   docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md (Sprint D R8 §6.R8)
--   docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-05--ref20_r6_r7_capability_risk.md §2.4
--   sql/migrations/REF-20_RESERVATION.md §3 V056 row

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema preflight / 預檢
--
-- V056 retention 函數對 V051 paired CHECK 與 V055 verify function 之後的表
-- state 做 DELETE。需要 V051 paired CHECK + V055 verify function 全 land。
-- 非 hypertable 確認：mlde_shadow_recommendations 不在 timescaledb_information.hypertables
-- （V051 設計時刻意未 hypertable_create，因 advisory row 樣本量 << kline；
--  per CLAUDE.md §九 mlde_shadow 不是 hot-path partition target）。
--
-- V056 retention function operates on table state post-V051 paired CHECK +
-- post-V055 verify function. Requires both predecessor migrations applied.
-- Non-hypertable confirmed: mlde_shadow_recommendations is NOT in
-- timescaledb_information.hypertables (V051 design intentionally skipped
-- hypertable_create — advisory row volume << kline; per CLAUDE.md §九
-- mlde_shadow_recommendations is not a hot-path partition target).
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_v051_check_exists BOOLEAN;
    v_v055_function_exists BOOLEAN;
    v_replay_experiment_id_col_exists BOOLEAN;
    v_evidence_tier_col_exists BOOLEAN;
    v_is_hypertable BOOLEAN;
BEGIN
    -- V051 paired CHECK existence (3-tuple constraint).
    -- V051 paired CHECK 存在性檢查（3-tuple 約束）。
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_mlde_shadow_replay_lineage'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) INTO v_v051_check_exists;

    IF NOT v_v051_check_exists THEN
        RAISE EXCEPTION
            'V056 preflight: chk_mlde_shadow_replay_lineage paired CHECK absent. '
            'V051 must be applied before V056 retention policy.';
    END IF;

    -- V038/V040 evidence_source_tier column NOT NULL post-finalize.
    -- V038/V040 evidence_source_tier column finalize 後 NOT NULL。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND column_name = 'evidence_source_tier'
          AND is_nullable = 'NO'
    ) INTO v_evidence_tier_col_exists;

    IF NOT v_evidence_tier_col_exists THEN
        RAISE EXCEPTION
            'V056 preflight: evidence_source_tier column missing or nullable. '
            'V038-V040 3-step retrofit must complete before V056.';
    END IF;

    -- V051 replay_experiment_id column existence.
    -- V051 replay_experiment_id column 存在性。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND column_name = 'replay_experiment_id'
    ) INTO v_replay_experiment_id_col_exists;

    IF NOT v_replay_experiment_id_col_exists THEN
        RAISE EXCEPTION
            'V056 preflight: replay_experiment_id column missing. '
            'V051 must be applied before V056.';
    END IF;

    -- V055 verify_replay_evidence_and_insert function existence.
    -- V055 verify function 存在性（V055 retrofit 後 INSERT body 寫 3 column）。
    SELECT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning'
          AND p.proname = 'verify_replay_evidence_and_insert'
    ) INTO v_v055_function_exists;

    IF NOT v_v055_function_exists THEN
        RAISE EXCEPTION
            'V056 preflight: learning.verify_replay_evidence_and_insert '
            'function missing. V055 retrofit must be applied before V056.';
    END IF;

    -- Confirm NOT hypertable (per CLAUDE.md §九 design choice).
    -- 確認非 hypertable（CLAUDE.md §九 設計選擇）。
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'learning'
          AND hypertable_name = 'mlde_shadow_recommendations'
    ) INTO v_is_hypertable;

    IF v_is_hypertable THEN
        RAISE EXCEPTION
            'V056 preflight: learning.mlde_shadow_recommendations unexpectedly '
            'IS a hypertable. V056 design assumes cron-driven DELETE; '
            'retention should switch to TimescaleDB add_retention_policy.';
    END IF;

    RAISE NOTICE 'V056 preflight: V051 + V055 prerequisites verified; non-hypertable confirmed; continuing to retention function creation.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- V056 retention function / V056 保留期函數
--
-- Cron-driven DELETE（per row tier）；caller 用 SECURITY INVOKER role 跑：
--   SELECT learning.prune_mlde_shadow_recommendations(30, 90, false, NULL);
--      → dry-run 統計 row count，不 DELETE
--   SELECT learning.prune_mlde_shadow_recommendations(30, 90, true, NULL);
--      → apply 模式真 DELETE
--
-- Cron-driven DELETE (per row tier); caller invokes with SECURITY INVOKER:
--   SELECT learning.prune_mlde_shadow_recommendations(30, 90, false, NULL);
--      → dry-run mode: count rows, NO DELETE
--   SELECT learning.prune_mlde_shadow_recommendations(30, 90, true, NULL);
--      → apply mode: real DELETE
--
-- Args:
--   p_replay_retention_days  INTEGER  — replay-derived 保留天數（建議 30）
--   p_real_retention_days    INTEGER  — real_outcome 保留天數（建議 90）
--   p_apply                  BOOLEAN  — true=DELETE / false=count only
--   p_max_rows               INTEGER  — DELETE 上限（防 long lock；NULL=無限）
--
-- Returns: TABLE(tier TEXT, candidate_count BIGINT, deleted_count BIGINT)
--
-- Idempotency: dry-run 兩次回相同 candidate_count（sub-second drift 可接受）；
--               apply 後第二次跑 candidate_count 應減為 0（除新 row 落地）。
--
-- 邊界守則:
-- - 保留期下限 = 1 day（防 misconfigured cron 把當天樣本全清）；
--   p_replay_retention_days < 1 → RAISE EXCEPTION
--   p_real_retention_days < 1 → RAISE EXCEPTION
-- - real_outcome 保留期 ≥ replay 保留期（real 是 ground truth，不可比 replay 短）
-- - p_max_rows 上限：每 cycle DELETE 不超過 100k row（avoid 鎖表）
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION learning.prune_mlde_shadow_recommendations(
    p_replay_retention_days INTEGER DEFAULT 30,
    p_real_retention_days INTEGER DEFAULT 90,
    p_apply BOOLEAN DEFAULT false,
    p_max_rows INTEGER DEFAULT NULL
)
RETURNS TABLE(tier TEXT, candidate_count BIGINT, deleted_count BIGINT)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_replay_cutoff TIMESTAMPTZ;
    v_real_cutoff TIMESTAMPTZ;
    v_replay_candidates BIGINT;
    v_real_candidates BIGINT;
    v_replay_deleted BIGINT := 0;
    v_real_deleted BIGINT := 0;
    v_max_rows_effective INTEGER;
BEGIN
    -- 邊界檢查 / Boundary checks.
    IF p_replay_retention_days < 1 THEN
        RAISE EXCEPTION
            'V056 prune_mlde_shadow_recommendations: p_replay_retention_days=% must be >= 1 day '
            '(prevents misconfigured cron clearing same-day samples).',
            p_replay_retention_days;
    END IF;

    IF p_real_retention_days < 1 THEN
        RAISE EXCEPTION
            'V056 prune_mlde_shadow_recommendations: p_real_retention_days=% must be >= 1 day.',
            p_real_retention_days;
    END IF;

    IF p_real_retention_days < p_replay_retention_days THEN
        RAISE EXCEPTION
            'V056 prune_mlde_shadow_recommendations: p_real_retention_days=% must be >= '
            'p_replay_retention_days=% (real_outcome is ground truth; cannot retain less '
            'than replay-derived).',
            p_real_retention_days, p_replay_retention_days;
    END IF;

    -- Cap p_max_rows at 100k per cycle (avoid long lock).
    -- 每 cycle 上限 100k（防長鎖）。
    v_max_rows_effective := COALESCE(p_max_rows, 100000);
    IF v_max_rows_effective > 100000 THEN
        v_max_rows_effective := 100000;
    END IF;

    v_replay_cutoff := now() - make_interval(days => p_replay_retention_days);
    v_real_cutoff := now() - make_interval(days => p_real_retention_days);

    -- ── replay-derived row count ──
    -- 計算 replay-derived row 候選（calibrated/synthetic/counterfactual_replay
    -- 三 tier）：created_at < replay_cutoff 即過期。
    -- Count replay-derived candidates (3 replay tiers): created_at <
    -- replay_cutoff = expired.
    --
    -- NOTE: created_at NOT NULL by default `now()` per V051 schema; safe to
    -- compare directly. Use `ts` instead? `ts` is event-time (default now())
    -- semantically equivalent; we pick `ts` matching V055 INSERT body.
    -- 注意：V051 schema 無 `created_at` column；用 `ts`（V055 INSERT 寫的
    -- 是 ts default now()），語意 = event 時戳。
    SELECT COUNT(*)::BIGINT
      INTO v_replay_candidates
      FROM learning.mlde_shadow_recommendations
     WHERE evidence_source_tier IN ('calibrated_replay', 'synthetic_replay', 'counterfactual_replay')
       AND ts < v_replay_cutoff;

    -- ── real_outcome row count ──
    -- 計算 real_outcome 候選：ts < real_cutoff 即過期。
    -- Count real_outcome candidates: ts < real_cutoff = expired.
    SELECT COUNT(*)::BIGINT
      INTO v_real_candidates
      FROM learning.mlde_shadow_recommendations
     WHERE evidence_source_tier = 'real_outcome'
       AND ts < v_real_cutoff;

    -- ── apply mode：真 DELETE ──
    IF p_apply THEN
        -- DELETE replay-derived expired rows (cap at v_max_rows_effective).
        -- 刪 replay-derived 過期 row（上限 v_max_rows_effective）。
        WITH del_replay AS (
            DELETE FROM learning.mlde_shadow_recommendations
             WHERE id IN (
                SELECT id FROM learning.mlde_shadow_recommendations
                 WHERE evidence_source_tier IN ('calibrated_replay', 'synthetic_replay', 'counterfactual_replay')
                   AND ts < v_replay_cutoff
                 ORDER BY ts ASC
                 LIMIT v_max_rows_effective
             )
            RETURNING 1
        )
        SELECT COUNT(*)::BIGINT INTO v_replay_deleted FROM del_replay;

        -- DELETE real_outcome expired rows (cap at v_max_rows_effective).
        -- 刪 real_outcome 過期 row（上限 v_max_rows_effective）。
        WITH del_real AS (
            DELETE FROM learning.mlde_shadow_recommendations
             WHERE id IN (
                SELECT id FROM learning.mlde_shadow_recommendations
                 WHERE evidence_source_tier = 'real_outcome'
                   AND ts < v_real_cutoff
                 ORDER BY ts ASC
                 LIMIT v_max_rows_effective
             )
            RETURNING 1
        )
        SELECT COUNT(*)::BIGINT INTO v_real_deleted FROM del_real;

        RAISE NOTICE
            'V056 prune_mlde_shadow_recommendations APPLY: replay deleted=% / candidates=%; real deleted=% / candidates=%; replay_cutoff=%; real_cutoff=%.',
            v_replay_deleted, v_replay_candidates,
            v_real_deleted, v_real_candidates,
            v_replay_cutoff, v_real_cutoff;
    ELSE
        -- dry-run mode：only return counts.
        -- dry-run 模式：只回 count。
        RAISE NOTICE
            'V056 prune_mlde_shadow_recommendations DRY-RUN: replay candidates=%; real candidates=%; replay_cutoff=%; real_cutoff=%.',
            v_replay_candidates, v_real_candidates,
            v_replay_cutoff, v_real_cutoff;
    END IF;

    -- Return per-tier summary table (caller consumes via SELECT).
    -- 回 per-tier summary table（caller 用 SELECT 消費）。
    RETURN QUERY
    SELECT 'replay_derived'::TEXT AS tier_label,
           v_replay_candidates AS candidate_count,
           v_replay_deleted AS deleted_count
    UNION ALL
    SELECT 'real_outcome'::TEXT AS tier_label,
           v_real_candidates AS candidate_count,
           v_real_deleted AS deleted_count;
END;
$$;

COMMENT ON FUNCTION learning.prune_mlde_shadow_recommendations(INTEGER, INTEGER, BOOLEAN, INTEGER) IS
'V056 retention policy function — cron-driven DELETE for replay-derived (30d default) + real_outcome (90d default) rows. Per CLAUDE.md REF-20 Sprint D R8 maintenance pass; sibling cron at helper_scripts/db/mlde_shadow_recommendations_retention_cron.sh.';

-- Guard A post-create verification: function exists with 4-arg signature.
-- Guard A 創建後驗證：function 存在且 4-arg signature。
DO $$
DECLARE
    v_function_exists BOOLEAN;
    v_function_pronargs INTEGER;
    v_function_identity_args TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning'
          AND p.proname = 'prune_mlde_shadow_recommendations'
    ) INTO v_function_exists;

    IF NOT v_function_exists THEN
        RAISE EXCEPTION
            'V056 Guard A: prune_mlde_shadow_recommendations function not created.';
    END IF;

    SELECT p.pronargs INTO v_function_pronargs
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'learning'
      AND p.proname = 'prune_mlde_shadow_recommendations';

    IF v_function_pronargs <> 4 THEN
        RAISE EXCEPTION
            'V056 Guard A: prune_mlde_shadow_recommendations pronargs=%, expected 4.',
            v_function_pronargs;
    END IF;

    SELECT pg_get_function_identity_arguments(p.oid) INTO v_function_identity_args
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'learning'
      AND p.proname = 'prune_mlde_shadow_recommendations';

    -- Expected (PG 16): "p_replay_retention_days integer, p_real_retention_days integer, p_apply boolean, p_max_rows integer"
    -- 預期（PG 16 含 arg names）。
    IF v_function_identity_args NOT LIKE '%p_replay_retention_days integer%'
       OR v_function_identity_args NOT LIKE '%p_real_retention_days integer%'
       OR v_function_identity_args NOT LIKE '%p_apply boolean%'
       OR v_function_identity_args NOT LIKE '%p_max_rows integer%' THEN
        RAISE EXCEPTION
            'V056 Guard A: prune_mlde_shadow_recommendations identity_arguments=% '
            '(expected 4 args: p_replay_retention_days/p_real_retention_days/p_apply/p_max_rows).',
            v_function_identity_args;
    END IF;

    RAISE NOTICE 'V056 Guard A passed: function exists, pronargs=4, identity_args=%.', v_function_identity_args;
END $$;
