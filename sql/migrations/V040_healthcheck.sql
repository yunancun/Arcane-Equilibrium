-- V040_healthcheck.sql
-- Purpose / 目的:
--   Pre-deploy healthcheck for V040 ALTER NOT NULL + CHECK on
--   learning.mlde_shadow_recommendations.evidence_source_tier. Run after V039
--   backfill and before V040 to catch any leftover NULL rows that would cause
--   V040 to fail atomically.
--
--   This script is READ-ONLY (3 SELECTs); operator-friendly for routine
--   inspection and post-deploy verification.
--
-- V040 對 evidence_source_tier 加 NOT NULL + CHECK 的部署前健康檢查。V039 回填後、
-- V040 land 前執行；找出任何剩餘 NULL row 以避免 V040 atomic 失敗。
-- 本腳本純讀（3 條 SELECT），適合日常巡檢與部署後驗證。
--
-- Usage / 用法:
--   psql -U trading_admin -d trading_ai -f sql/migrations/V040_healthcheck.sql
--
--   ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai \
--     -f /opt/openclaw/srv/sql/migrations/V040_healthcheck.sql"
--
-- Expected output (post-V039, pre-V040) / 預期輸出（V039 後、V040 前）:
--   - null_check.null_row_count  = 0       ← V040 ready to run
--   - tier_distribution rows     = 1 (real_outcome ≈ 2,482 in 4-day window)
--   - constraint_state.is_nullable = YES, has_check = false
--
-- Expected output (post-V040) / 預期輸出（V040 後）:
--   - null_check.null_row_count  = 0
--   - tier_distribution rows     = ≥1 (will grow as new producers
--                                      emit calibrated_replay / synthetic_replay /
--                                      counterfactual_replay rows post-P2 runner)
--   - constraint_state.is_nullable = NO, has_check = true
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §3 G3 + §4.2
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 3
--   V3 §12 acceptance #5 evidence_tier_completeness (0 NULL row post-V040)

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 1: NULL row count / NULL 列計數
-- Goal: zero before V040 runs / 目標：V040 run 前必為 0
-- ─────────────────────────────────────────────────────────────────────────────
\echo '=== V040 Probe 1: NULL evidence_source_tier row count ==='
\echo '=== V040 探針 1：NULL evidence_source_tier 列數 ==='
SELECT 'null_check' AS probe,
       COUNT(*)    AS null_row_count
  FROM learning.mlde_shadow_recommendations
 WHERE evidence_source_tier IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 2: tier value distribution / tier 值分佈
-- Goal: post-V039 sanity check; post-V040 monitoring baseline.
-- 目標：V039 後合理性檢查；V040 後監控基線。
--
-- Pre-V040 expected (assuming V039 land): all rows = 'real_outcome' (3 producers
-- backfilled). NULL rows surfaced in Probe 1 above; if Probe 1 shows >0,
-- this query will additionally show evidence_source_tier IS NULL bucket.
--
-- V040 前預期（假設 V039 已 land）：全部 = 'real_outcome'（3 個 producer 回填）。
-- 探針 1 的 NULL 列在此處會額外顯示為一個 bucket。
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '=== V040 Probe 2: evidence_source_tier value distribution ==='
\echo '=== V040 探針 2：evidence_source_tier 值分佈 ==='
SELECT COALESCE(evidence_source_tier, '<NULL>') AS evidence_source_tier,
       COUNT(*)                                  AS row_count,
       ROUND(100.0 * COUNT(*) /
             NULLIF((SELECT COUNT(*) FROM learning.mlde_shadow_recommendations), 0),
             2) AS pct_of_total
  FROM learning.mlde_shadow_recommendations
 GROUP BY 1
 ORDER BY 2 DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 3: Constraint state / 約束狀態
-- Goal: confirm NOT NULL + CHECK landed (post-V040) or absent (pre-V040).
-- 目標：確認 V040 之後 NOT NULL + CHECK 都已 land；之前都沒有。
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '=== V040 Probe 3: column NOT NULL + CHECK constraint state ==='
\echo '=== V040 探針 3：欄位 NOT NULL + CHECK 約束狀態 ==='
SELECT 'constraint_state' AS probe,
       (SELECT is_nullable
          FROM information_schema.columns
         WHERE table_schema = 'learning'
           AND table_name = 'mlde_shadow_recommendations'
           AND column_name = 'evidence_source_tier') AS is_nullable,
       EXISTS (
           SELECT 1 FROM pg_constraint
            WHERE conname = 'chk_evidence_source_tier'
              AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
       )                                              AS has_check_constraint,
       (SELECT pg_get_constraintdef(c.oid)
          FROM pg_constraint c
         WHERE conname = 'chk_evidence_source_tier'
           AND conrelid = 'learning.mlde_shadow_recommendations'::regclass) AS check_definition;
