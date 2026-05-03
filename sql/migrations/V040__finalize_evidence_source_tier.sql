-- V040__finalize_evidence_source_tier.sql
-- Purpose / 目的:
--   Step 3 of REF-20 R20-P2a-S6 evidence_source_tier 3-step retrofit. After V038
--   (ADD nullable) + V039 (backfill 'real_outcome' for known producers), this
--   migration locks the column with NOT NULL + CHECK enum constraint per V3
--   §4.2 allowlist. From V040 onwards every INSERT must supply a valid tier.
--
-- 步驟 3 / REF-20 R20-P2a-S6 evidence_source_tier 三步回補：在 V038（加 nullable）+ V039
--（'real_outcome' 回填）之後，本步驟以 NOT NULL + CHECK enum 鎖死該欄位（V3 §4.2 allowlist）。
-- 自 V040 起每筆 INSERT 都必須給定合法 tier。
--
-- 3-step sequence / 三步序列：
--   V038              ADD COLUMN evidence_source_tier TEXT NULLABLE
--   V039              backfill via P0-T7 source classification → 'real_outcome'
--   V040 (this file)  ALTER COLUMN NOT NULL + ADD CHECK constraint allowlist
--
-- WARNING / 操作前注意事項:
--   ❗ Operator MUST verify V039 backfill landed cleanly before V040.
--      The healthcheck `sql/migrations/V040_healthcheck.sql` returns 0 NULL
--      rows when V039 finished successfully. If any row still has
--      evidence_source_tier IS NULL, the V040 ALTER ... SET NOT NULL below
--      WILL FAIL atomically (no partial change).
--   ❗ 部署前必先驗 V039 回填乾淨：跑 sql/migrations/V040_healthcheck.sql 期望 0 NULL row；
--      若仍有 NULL row，本檔的 ALTER ... SET NOT NULL 會 atomic 失敗。
--
--   Recovery if NULL rows present after V039 / V039 後仍有 NULL row 的恢復步驟:
--     a) Identify the offending source values:
--          SELECT source, COUNT(*) FROM learning.mlde_shadow_recommendations
--           WHERE evidence_source_tier IS NULL GROUP BY 1;
--     b) PM classifies new source(s) per V3 §4.2 ambiguous-rows protocol.
--     c) Re-run V039 (idempotent UPDATE 0 row) or write a one-off
--        V039.5 backfill for the new source.
--     d) Re-run V040.
--   恢復步驟 / Recovery: 找出剩餘 NULL row 的 source → PM 分類 → 補回填 → 重跑 V040。
--
-- Migration order / 遷移順序：V038 → V039 → V040 (this).
-- Idempotency / 幂等性: local psql -f V040 ... × 2 → second run no-op
--   (Guard B detects column already NOT NULL; CHECK constraint already exists
--    via IF NOT EXISTS conditional CREATE).
-- Guard A: N/A (existence guaranteed by V031).
-- Guard B: enforced (column type + NOT NULL state + CHECK existence).
-- Guard C: N/A (no index changes).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §3 G3 + §4.2
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 3 R20-P2a-S6
--   V3 §12 acceptance #5 evidence_tier_completeness (0 NULL row post-V040)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V040
-- Healthcheck companion / 健康檢查同伴:
--   sql/migrations/V040_healthcheck.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B (V038 + V039 precondition) /
-- Guard B（V038 + V039 前提條件）
--
-- 1. evidence_source_tier column must exist as text (V038 land).
-- 2. No NULL rows allowed (V039 backfill complete; otherwise SET NOT NULL fails).
--    We RAISE here for a friendlier error message instead of letting ALTER fail.
--
-- 1. evidence_source_tier 必以 text 型存在（V038 已 land）。
-- 2. 不可有 NULL 列（V039 回填完成；否則 SET NOT NULL 失敗）；本處 RAISE 提供
--    比 ALTER 失敗更易讀的錯訊。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_actual_type TEXT;
    v_is_nullable TEXT;
    v_null_count BIGINT;
BEGIN
    SELECT data_type, is_nullable INTO v_actual_type, v_is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'evidence_source_tier';

    IF v_actual_type IS NULL THEN
        RAISE EXCEPTION
            'V040 Guard B: learning.mlde_shadow_recommendations.evidence_source_tier '
            'does not exist. V038 must run before V040.';
    END IF;

    IF v_actual_type <> 'text' THEN
        RAISE EXCEPTION
            'V040 Guard B: evidence_source_tier exists as %, expected text. '
            'V038 partial apply / drift detected.',
            v_actual_type;
    END IF;

    -- If column is already NOT NULL (V040 already applied), skip the count
    -- check entirely — the second run is a guaranteed no-op.
    -- 若欄位已 NOT NULL（V040 已 apply），跳過 NULL 計數檢查（保證 no-op）。
    IF v_is_nullable = 'YES' THEN
        SELECT COUNT(*) INTO v_null_count
        FROM learning.mlde_shadow_recommendations
        WHERE evidence_source_tier IS NULL;

        IF v_null_count > 0 THEN
            RAISE EXCEPTION
                'V040 Guard B: % rows have NULL evidence_source_tier. '
                'V039 backfill must complete before V040. '
                'Run sql/migrations/V040_healthcheck.sql for diagnostics. '
                'Recovery: classify new source(s) per V3 §4.2 → re-run V039 → re-run V040.',
                v_null_count;
        END IF;
    ELSE
        RAISE NOTICE 'V040 Guard B: column already NOT NULL; ALTER below will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER COLUMN SET NOT NULL / 鎖 NOT NULL
--
-- Guard B above guarantees 0 NULL rows; this ALTER is now safe.
-- Idempotent: ALTER COLUMN ... SET NOT NULL on an already-NOT-NULL column
-- is a Postgres no-op.
--
-- 上方 Guard B 保證 0 NULL row，本步安全。
-- 幂等：對已 NOT NULL 欄位再 SET NOT NULL 是 Postgres no-op。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE learning.mlde_shadow_recommendations
    ALTER COLUMN evidence_source_tier SET NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD CONSTRAINT (CHECK enum allowlist) / 加 CHECK enum 白名單
--
-- V3 §4.2 specifies 4 allowed tier values. We add the constraint conditionally
-- so re-runs don't error. Constraint name documented for downstream
-- introspection / repair scripts.
--
-- V3 §4.2 規定 4 個允許值。條件式加約束，重跑不報錯。約束名供下游檢視 / 修復腳本使用。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_evidence_source_tier'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) THEN
        ALTER TABLE learning.mlde_shadow_recommendations
            ADD CONSTRAINT chk_evidence_source_tier
            CHECK (
                evidence_source_tier IN (
                    'real_outcome',
                    'calibrated_replay',
                    'synthetic_replay',
                    'counterfactual_replay'
                )
            );
        RAISE NOTICE 'V040: added CHECK constraint chk_evidence_source_tier (4-value allowlist)';
    ELSE
        RAISE NOTICE 'V040: chk_evidence_source_tier already present; skipping ADD CONSTRAINT';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B'' (post-apply verification) /
-- Guard B''（apply 後驗證）
--
-- Confirm both NOT NULL and CHECK landed. Defense in depth — if a future
-- migration drops the constraint accidentally, re-running V040 RAISES.
--
-- 確認 NOT NULL 與 CHECK 都已 land。防禦深度——若未來 migration 意外 drop 約束，
-- 重跑 V040 會 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_is_nullable TEXT;
    v_check_exists BOOLEAN;
BEGIN
    SELECT is_nullable INTO v_is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'evidence_source_tier';

    IF v_is_nullable <> 'NO' THEN
        RAISE EXCEPTION
            'V040 Guard B'': SET NOT NULL did not take effect (is_nullable=%). '
            'Investigate — possible permission issue or extension interference.',
            v_is_nullable;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_evidence_source_tier'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) INTO v_check_exists;

    IF NOT v_check_exists THEN
        RAISE EXCEPTION
            'V040 Guard B'': chk_evidence_source_tier constraint missing after ADD CONSTRAINT block. '
            'Cannot enforce V3 §4.2 allowlist; abort.';
    END IF;

    RAISE NOTICE 'V040 Guard B'': NOT NULL + CHECK both verified';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Refresh column comment to reflect V040 finalization /
-- 更新欄位註解反映 V040 最終態
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON COLUMN learning.mlde_shadow_recommendations.evidence_source_tier IS
'Replay evidence tier per REF-20 V3 §4.2. NOT NULL + CHECK enforced. '
'Allowlist: real_outcome / calibrated_replay / synthetic_replay / counterfactual_replay. '
'V040 finalized 2026-05-03 (Wave 3 R20-P2a-S6). / '
'REF-20 V3 §4.2 重放證據層級；V040 鎖 NOT NULL + CHECK；'
'白名單：real_outcome / calibrated_replay / synthetic_replay / counterfactual_replay。';
