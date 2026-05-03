-- V038__add_evidence_source_tier.sql
-- Purpose / 目的:
--   Step 1 of REF-20 R20-P2a-S6 evidence_source_tier 3-step retrofit. Add nullable
--   `evidence_source_tier TEXT` column to learning.mlde_shadow_recommendations.
--   No producer write impact; column NULL on insert; backfill happens in V039;
--   NOT NULL + CHECK enforced in V040.
--
-- 步驟 1 / REF-20 R20-P2a-S6 evidence_source_tier 三步回補：對
-- learning.mlde_shadow_recommendations 加上 nullable `evidence_source_tier TEXT`
-- 欄位。本步無 producer 寫入影響（INSERT 時為 NULL）；V039 回填；V040 鎖 NOT NULL + CHECK。
--
-- 3-step sequence / 三步序列：
--   V038 (this file)  ADD COLUMN evidence_source_tier TEXT NULLABLE — no production write impact
--   V039              backfill via P0-T7 source classification table → 'real_outcome'
--   V040              ALTER COLUMN NOT NULL + ADD CHECK constraint allowlist
--
-- Migration order / 遷移順序：V035 → V036 → V037 → V038 (this) → V039 → V040.
-- Idempotency / 幂等性: local psql -f V038 ... × 2 → second run no-op (Guard B
-- detects column exists with expected type 'text' and skips RAISE).
-- Guard A: N/A (table existence already enforced by V031 Guard A; this migration
--          only ALTERs; if table missing the ADD COLUMN would fail naturally).
-- Guard B: enforced (column existence + canonical type 'text' verification).
-- Guard C: N/A (no index changes).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §3 G3 + §4.2
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 3 R20-P2a-S6
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard B
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V038
-- Producer classification source / Producer 分類來源:
--   docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_source_classification.md
--   (3 source / 0 ambiguous / 0 forbidden — all → real_outcome at V039 backfill)

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B (column type drift detection) /
-- Guard B（欄位型別漂移偵測）
--
-- If `evidence_source_tier` already exists with a non-text type (legacy partial
-- apply), RAISE so operator resolves drift before re-running. If absent, no-op
-- and let the ALTER TABLE below add it.
--
-- 若 `evidence_source_tier` 已存在但型別非 text（部分 apply 殘留），RAISE 讓 operator
-- 先解決漂移再重跑。不存在則 no-op，下方 ALTER 會自然加上。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_actual_type TEXT;
    v_expected_type TEXT := 'text';
BEGIN
    SELECT data_type INTO v_actual_type
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'evidence_source_tier';

    IF v_actual_type IS NOT NULL AND v_actual_type <> v_expected_type THEN
        RAISE EXCEPTION
            'V038 Guard B: learning.mlde_shadow_recommendations.evidence_source_tier '
            'exists as %, expected %. Column type drift detected. '
            'Resolve manually (ALTER COLUMN TYPE) or DROP COLUMN + re-apply V038.',
            v_actual_type, v_expected_type;
    END IF;

    IF v_actual_type IS NOT NULL THEN
        RAISE NOTICE 'V038 Guard B: evidence_source_tier already exists as text; ADD COLUMN will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD COLUMN (nullable) / 加欄位（可為 NULL）
--
-- Stay nullable for now. V039 backfills NULL → 'real_outcome' for the 3 known
-- producers; V040 enforces NOT NULL + CHECK. Splitting these steps avoids
-- write traffic blocking during a long ALTER on a hypertable / large table.
--
-- 暫保持 nullable。V039 回填 NULL → 'real_outcome'（3 個已知 producer），V040 加 NOT
-- NULL + CHECK。分步避免 hypertable / 大表 ALTER 過程中阻塞寫入流量。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE learning.mlde_shadow_recommendations
    ADD COLUMN IF NOT EXISTS evidence_source_tier TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Bilingual column comment / 中英欄位註解
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON COLUMN learning.mlde_shadow_recommendations.evidence_source_tier IS
'Replay evidence tier per REF-20 V3 §4.2. Allowlist enforced in V040: '
'real_outcome / calibrated_replay / synthetic_replay / counterfactual_replay. '
'NULLABLE in V038 (this), backfilled by V039 to ''real_outcome'' for 3 legacy '
'producers (dream_engine / ml_shadow / opportunity_tracker), NOT NULL + CHECK '
'enforced by V040. / REF-20 V3 §4.2 重放證據層級；V040 鎖 enum 白名單；'
'V038 階段 NULLABLE，V039 對 3 個歷史 producer 回填 ''real_outcome''，V040 鎖 NOT NULL + CHECK。';
