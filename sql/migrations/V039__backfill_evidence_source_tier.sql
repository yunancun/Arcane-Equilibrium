-- V039__backfill_evidence_source_tier.sql
-- Purpose / 目的:
--   Step 2 of REF-20 R20-P2a-S6 evidence_source_tier 3-step retrofit. Mass UPDATE
--   sets `evidence_source_tier='real_outcome'` for all rows where the column is
--   currently NULL AND `source` is in the legacy producer allowlist (V3 §4.2).
--   This is the schema-precondition for V040 ALTER NOT NULL + CHECK.
--
-- 步驟 2 / REF-20 R20-P2a-S6 evidence_source_tier 三步回補：對 source 屬於既有
-- producer allowlist 且 evidence_source_tier 仍 NULL 的列批量 UPDATE 為 'real_outcome'。
-- 為 V040 ALTER NOT NULL + CHECK 預備 schema 前提。
--
-- 3-step sequence / 三步序列：
--   V038              ADD COLUMN evidence_source_tier TEXT NULLABLE
--   V039 (this file)  backfill via P0-T7 source classification → 'real_outcome'
--   V040              ALTER COLUMN NOT NULL + ADD CHECK constraint allowlist
--
-- Producer classification source (P0-T7 evidence) / Producer 分類來源（P0-T7 證據）：
--   docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_source_classification.md
--
--   Distinct source values written to learning.mlde_shadow_recommendations
--   (4-day window 2026-04-29 → 2026-05-03, 2,482 rows total):
--     - dream_engine          1,117 rows  (V3 §4.2 allowlist) → real_outcome
--     - ml_shadow             1,185 rows  (V3 §4.2 allowlist) → real_outcome
--     - opportunity_tracker     180 rows  (V3 §4.2 allowlist) → real_outcome
--   0 ambiguous / 0 forbidden / 0 unknown / 0 NULL source.
--
--   27 of the 1,185 ml_shadow rows carry engine_mode='live' (LG-5 promotion-
--   candidate audit rows from `mlde_demo_applier._insert_live_candidate`,
--   applied=false, decision_lease_id=NULL). PM clarification (dispatch §2 #2):
--   these 27 rows also map to evidence_source_tier='real_outcome' because the
--   producer is the demo applier (no replay registry FK; manifest_hash IS NULL).
--   The §4.2 row CHECK (V040 ADD CONSTRAINT replay_evidence_lineage_check) holds
--   for `real_outcome AND replay_experiment_id IS NULL AND manifest_hash IS NULL`.
--
-- Migration order / 遷移順序：V038 → V039 (this) → V040.
-- Idempotency / 幂等性: local psql -f V039 ... × 2 → second run UPDATE 0 rows
-- (the WHERE clause requires evidence_source_tier IS NULL; first run cleared
-- all qualifying rows). The audit INSERT writes a second row on each apply
-- with the actual UPDATE row count (expected 0 on re-run).
-- Guard A: N/A (UPDATE-only; existence already enforced by V031 / V038).
-- Guard B: precheck — V038 must have completed (column exists as text). RAISE
--          if column missing.
-- Guard C: N/A.
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §4.2
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 3 R20-P2a-S6
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V039

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B (V038 precondition) /
-- Guard B（V038 前提條件）
--
-- The column must exist as text. If V038 has not been applied, abort.
-- This also protects against running V039 against an environment where
-- V038 partially applied (column dropped manually).
--
-- 該欄必須以 text 型別存在；V038 尚未 apply 則中止。同時保護 V038 部分 apply
-- 後手動 DROP 欄位的環境。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_actual_type TEXT;
BEGIN
    SELECT data_type INTO v_actual_type
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'evidence_source_tier';

    IF v_actual_type IS NULL THEN
        RAISE EXCEPTION
            'V039 Guard B: learning.mlde_shadow_recommendations.evidence_source_tier '
            'does not exist. V038 must run before V039.';
    END IF;

    IF v_actual_type <> 'text' THEN
        RAISE EXCEPTION
            'V039 Guard B: evidence_source_tier exists as %, expected text. '
            'V038 partial apply / drift detected; resolve before V039.',
            v_actual_type;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B' (governance_audit_log dependency) /
-- Guard B'（governance_audit_log 依賴）
--
-- We log the backfill batch via INSERT INTO learning.governance_audit_log.
-- The audit table is created in V035; if absent, abort.
--
-- 我們透過 INSERT 寫入 learning.governance_audit_log 記錄回填批次；
-- 該表由 V035 建立；若不存在則中止。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) THEN
        RAISE EXCEPTION
            'V039 Guard B'': learning.governance_audit_log does not exist. '
            'V035 must run before V039 (audit row writes depend on it).';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Backfill body / 回填主體
--
-- WHERE clause filters:
--   1. evidence_source_tier IS NULL   — preserves any non-NULL row already
--                                       written by future producers (defense
--                                       against running V039 after V040 +
--                                       new producers).
--   2. source IN (3 allowlist)        — defensive duplication of the V031
--                                       schema CHECK; even if CHECK is
--                                       relaxed in future, this UPDATE
--                                       only touches known-classified rows.
--
-- Wrapped in a transaction explicitly so the UPDATE row count is captured
-- atomically alongside the audit log INSERT.
--
-- WHERE 過濾器：
--   1. evidence_source_tier IS NULL   — 保護未來 producer 寫入的非 NULL 列。
--   2. source IN (3 個 allowlist)     — V031 schema CHECK 的防禦性重複；
--                                       未來 CHECK 放寬時，本 UPDATE 仍只
--                                       動已分類的列。
--
-- 用 DO block 包裝以原子捕捉 UPDATE row count 並寫入審計列。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_updated_count BIGINT;
    v_env TEXT := current_setting('replay.migration_env', true);
    v_audit_payload JSONB;
BEGIN
    -- Default env tag to 'unknown' if migration runner doesn't set it.
    -- 若遷移執行器未設置，env 標記預設 'unknown'。
    IF v_env IS NULL OR v_env = '' THEN
        v_env := 'unknown';
    END IF;

    -- Mass UPDATE / 批量回填
    WITH updated AS (
        UPDATE learning.mlde_shadow_recommendations
           SET evidence_source_tier = 'real_outcome'
         WHERE evidence_source_tier IS NULL
           AND source IN ('dream_engine', 'ml_shadow', 'opportunity_tracker')
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_updated_count FROM updated;

    -- Build audit payload / 構造審計 payload
    v_audit_payload := jsonb_build_object(
        'migration_id', 'V039',
        'task_id', 'R20-P2a-S6',
        'step', 'backfill_evidence_source_tier',
        'rows_updated', v_updated_count,
        'allowlist', jsonb_build_array('dream_engine', 'ml_shadow', 'opportunity_tracker'),
        'classification', 'real_outcome',
        'env', v_env,
        'preflight_report',
        'docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_source_classification.md',
        'preflight_distinct_sources', 3,
        'preflight_ambiguous', 0,
        'preflight_forbidden', 0,
        'note',
        '27 ml_shadow engine_mode=live rows are LG-5 promotion-candidate audit '
        'rows (applied=false, decision_lease_id=NULL); per PM dispatch §2 #2 '
        'they map to real_outcome (no replay registry FK; manifest_hash NULL).'
    );

    -- Audit row / 審計列
    INSERT INTO learning.governance_audit_log (
        ts,
        event_type,
        candidate_id,
        decision_lease_id,
        verdict_decision,
        verdict_reason,
        rule_failures,
        decided_by,
        payload
    ) VALUES (
        now(),
        'bulk_re_evaluation',
        NULL,
        NULL,
        NULL,
        'evidence_source_tier_backfill',
        ARRAY[]::TEXT[],
        'migration:V039',
        v_audit_payload
    );

    RAISE NOTICE 'V039: backfilled % rows (evidence_source_tier=real_outcome) for sources [dream_engine, ml_shadow, opportunity_tracker]; env=%',
        v_updated_count, v_env;
END $$;
