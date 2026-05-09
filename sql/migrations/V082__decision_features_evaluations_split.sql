-- ============================================================
-- V082: W-AUDIT-4b-M1 — decision_features evaluation 拆表
--
-- 動機 / Motivation:
--   2026-05-09 PG 直查：learning.decision_features 24h 31,183 行中
--   ~99.32% 是 orphan candidate evaluation（無對應 trading.intents emit）。
--   Root cause: rust/openclaw_engine/src/intent_processor/mod.rs
--     :evaluate_predictor_gate 在 cost_gate / Reject 之前頂端就 emit
--     一條 decision_features row，無論該 intent 是否真實 emit。
--
--   修復：拆 evaluation 路徑到新表 learning.decision_features_evaluations
--   （保 38k/24h evaluation log 行為，作 producer 偵錯 / gate 行為觀測），
--   保留 learning.decision_features 為 production training 表（intent-only emit）。
--
-- 範圍 / Scope:
--   1. 新表 learning.decision_features_evaluations（candidate evaluation log）
--   2. PK = evaluation_id BIGSERIAL（單 context_id 可被 evaluate 多次）
--   3. 加 evaluation_outcome TEXT 記 PredictorAction 結果
--   4. 加 evidence_source_tier TEXT NOT NULL CHECK ∈
--      ('evaluation_log', 'shadow_synthetic')
--      per CLAUDE.md §九「Non-training surfaces」標準
--   5. 加 entry_context_id TEXT NULL（為 W-AUDIT-4b-M2 trigger 鋪路）
--   6. 不遷移舊 38k row（accepted as historic noise；新 producer 從新表開始）
--   7. 既有 learning.decision_features 不動（Phase 2 producer 改造後 30d
--      自然衰減）
--
-- 不變式 / Invariants:
--   - evaluation_id 單調遞增 BIGSERIAL（無 dedup 語義）
--   - evaluation_outcome ∈ ('accept', 'reject', 'reject_add', 'shadow_fill',
--                           'fallback_use_legacy', 'fallback_fail_closed',
--                           'use_legacy_no_predictor')
--   - evidence_source_tier ∉ {'real_outcome', 'calibrated_replay',
--                              'synthetic_replay', 'counterfactual_replay'}
--     避免與 V050 replay.simulated_fills 共享 tier 字串污染下游 ML SELECT
--
-- ML training 安全性 / ML Training Safety:
--   下游 SELECT learning.decision_features* 必過濾：
--     learning.decision_features：production training（intent-only，
--       與 trading.intents 1:1 對齊）— 可訓練
--     learning.decision_features_evaluations：candidate evaluation log
--       — 不可作 ML training data（pool 已被 reject path 污染）
--   SELECT FROM learning.decision_features_evaluations 必含
--     WHERE evidence_source_tier IN ('shadow_synthetic')
--   或不在 ML SELECT 範圍內（producer-debug only）。
--
-- 對應產品 / Product impact:
--   attribution_chain_ok 0.5% → 25-40%（denominator 縮 99% / decision_features
--   intent-only emit 後與 attribution_chain 一比一對齊）。
--
-- Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
--       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
--       TODO.md v19 §5 invariant 5+19 (P1-INSERT-PATH ticket family)
-- ============================================================

-- ============================================================
-- Guard A: learning schema must exist (cheap fail-fast)
-- Guard A: learning schema 必須已存在
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'learning'
    ) THEN
        RAISE EXCEPTION 'V082 Guard A FAIL: learning schema missing';
    END IF;
END $$;

-- ============================================================
-- Guard A2: legacy learning.decision_features must exist with required columns
-- (確認 producer fan-out 改造前的對齊基準)
-- Guard A2：legacy learning.decision_features 必須存在且具必要欄位
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='decision_features'
    ) THEN
        RAISE EXCEPTION
            'V082 Guard A2 FAIL: learning.decision_features missing — '
            'V017 must have applied first. Re-check migration order.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'context_id', 'ts', 'engine_mode', 'strategy_name', 'symbol',
        'side', 'feature_schema_version', 'feature_schema_hash',
        'feature_definition_hash', 'features_jsonb'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='decision_features'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V082 Guard A2 FAIL: learning.decision_features missing required columns: %. '
            'Resolve V017 schema drift before applying V082.',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- Guard A3: 新表 learning.decision_features_evaluations 若已存在
-- 必須 schema 一致（防 future re-run drift）
-- Guard A3: if learning.decision_features_evaluations exists, schema must align
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning'
          AND table_name='decision_features_evaluations'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'evaluation_id', 'context_id', 'ts', 'engine_mode',
            'strategy_name', 'symbol', 'side',
            'feature_schema_version', 'feature_schema_hash',
            'feature_definition_hash', 'features_jsonb',
            'evaluation_outcome', 'evidence_source_tier',
            'entry_context_id'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning'
              AND table_name='decision_features_evaluations'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION
                'V082 Guard A3 FAIL: learning.decision_features_evaluations '
                'exists but missing required columns: %. '
                'Drop legacy table or ALTER ADD missing columns then re-apply V082.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ============================================================
-- 主 DDL：建立 learning.decision_features_evaluations
-- Main DDL: create learning.decision_features_evaluations
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.decision_features_evaluations (
    evaluation_id           BIGSERIAL    PRIMARY KEY,
    -- candidate intent 的 context_id（與 V017 decision_features 對齊欄位語意）
    -- 注意：同一 context_id 可被 evaluate 多次（無 dedup），與舊表不同
    context_id              TEXT         NOT NULL,
    ts                      TIMESTAMPTZ  NOT NULL,
    engine_mode             TEXT         NOT NULL,
    strategy_name           TEXT         NOT NULL,
    symbol                  TEXT         NOT NULL,
    side                    SMALLINT     NOT NULL,           -- +1 long / -1 short
    feature_schema_version  TEXT         NOT NULL,
    feature_schema_hash     TEXT         NOT NULL,
    feature_definition_hash TEXT         NOT NULL,
    features_jsonb          JSONB        NOT NULL,
    -- evaluate_predictor_gate 的 PredictorAction 結果（producer-debug 用）
    -- evaluation_outcome：predictor gate 評估結果記錄
    evaluation_outcome      TEXT         NOT NULL,
    -- evidence_source_tier：CLAUDE.md §九 Non-training surfaces 標準
    -- 'evaluation_log'：常規 candidate evaluation（reject / pass-through）
    -- 'shadow_synthetic'：ε-greedy ShadowFill 觀測（pair with shadow_fills）
    evidence_source_tier    TEXT         NOT NULL,
    -- entry_context_id：M2 trigger 鋪路欄位
    -- 當前 M1 producer 寫 NULL；M2 attribution chain trigger 需此欄位
    -- 將 evaluation log 與後續實際 entry intent 串聯
    entry_context_id        TEXT,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- evaluation_outcome 白名單 CHECK
-- 條件式加 CHECK 約束，重跑不報錯
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_decision_features_evaluations_outcome'
          AND conrelid = 'learning.decision_features_evaluations'::regclass
    ) THEN
        ALTER TABLE learning.decision_features_evaluations
            ADD CONSTRAINT chk_decision_features_evaluations_outcome
            CHECK (evaluation_outcome IN (
                'accept',                       -- PredictorAction::SkipLegacyGate (predictor accept)
                'reject',                       -- PredictorAction::Reject (predictor q10/cost reject)
                'reject_add',                   -- PredictorGateOutcome::RejectAdd
                'shadow_fill',                  -- PredictorGateOutcome::ShadowFill (ε-greedy)
                'fallback_use_legacy',          -- Fallback policy: shrinkage
                'fallback_fail_closed',         -- Fallback policy: fail-closed
                'use_legacy_no_predictor'       -- predictor disabled / no store / no features
            ));
        RAISE NOTICE 'V082: added CHECK chk_decision_features_evaluations_outcome (7-value allowlist)';
    ELSE
        RAISE NOTICE 'V082: chk_decision_features_evaluations_outcome already present; skipping';
    END IF;

    -- evidence_source_tier 白名單 CHECK
    -- 與 V050 replay.simulated_fills 的 tier 字串故意不重疊（避免下游 SELECT 污染）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_decision_features_evaluations_evidence_tier'
          AND conrelid = 'learning.decision_features_evaluations'::regclass
    ) THEN
        ALTER TABLE learning.decision_features_evaluations
            ADD CONSTRAINT chk_decision_features_evaluations_evidence_tier
            CHECK (evidence_source_tier IN (
                'evaluation_log',       -- 一般 candidate evaluation
                'shadow_synthetic'      -- ε-greedy shadow_fill 觀測
            ));
        RAISE NOTICE 'V082: added CHECK chk_decision_features_evaluations_evidence_tier (2-value allowlist)';
    ELSE
        RAISE NOTICE 'V082: chk_decision_features_evaluations_evidence_tier already present; skipping';
    END IF;

    -- side enum CHECK（與 V017 decision_features 對齊）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_decision_features_evaluations_side'
          AND conrelid = 'learning.decision_features_evaluations'::regclass
    ) THEN
        ALTER TABLE learning.decision_features_evaluations
            ADD CONSTRAINT chk_decision_features_evaluations_side
            CHECK (side IN (-1, 1));
        RAISE NOTICE 'V082: added CHECK chk_decision_features_evaluations_side (long/short)';
    ELSE
        RAISE NOTICE 'V082: chk_decision_features_evaluations_side already present; skipping';
    END IF;
END $$;

-- ============================================================
-- 索引 / Indexes
-- ============================================================

-- ============================================================
-- Guard C: production-critical hot-path index
-- (strategy_name + engine_mode + ts DESC) — gate behavior debug query
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='learning'
      AND c.relname='idx_decision_features_evaluations_strategy_mode_ts';
    -- 預期 substring 須含「strategy_name」「engine_mode」「ts DESC」
    -- (PostgreSQL pg_get_indexdef 順序與 CREATE INDEX 順序一致)
    IF v_actual IS NOT NULL
       AND (position('strategy_name' IN v_actual) = 0
            OR position('engine_mode' IN v_actual) = 0
            OR position('ts DESC' IN v_actual) = 0) THEN
        RAISE EXCEPTION
            'V082 Guard C FAIL: idx_decision_features_evaluations_strategy_mode_ts '
            'exists but column list mismatch. Actual: %. '
            'Expected to contain (strategy_name, engine_mode, ts DESC). '
            'DROP INDEX + re-apply V082.',
            v_actual;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_decision_features_evaluations_strategy_mode_ts
    ON learning.decision_features_evaluations (strategy_name, engine_mode, ts DESC);

-- ts DESC 掃描索引（最近 N 筆 evaluation 行為觀測）
CREATE INDEX IF NOT EXISTS idx_decision_features_evaluations_ts
    ON learning.decision_features_evaluations (ts DESC);

-- context_id 索引（debug 用：找到該 context_id 的所有 evaluation 歷史）
CREATE INDEX IF NOT EXISTS idx_decision_features_evaluations_context_id
    ON learning.decision_features_evaluations (context_id);

-- evaluation_outcome 過濾索引（gate behavior heatmap）
CREATE INDEX IF NOT EXISTS idx_decision_features_evaluations_outcome_ts
    ON learning.decision_features_evaluations (evaluation_outcome, ts DESC);

-- ============================================================
-- Comments
-- ============================================================
COMMENT ON TABLE learning.decision_features_evaluations IS
    'W-AUDIT-4b-M1 candidate evaluation log split (V082). '
    '每次 evaluate_predictor_gate 評估的 feature snapshot；'
    '無論 PredictorAction outcome 如何都寫入。'
    '不可作 ML training（pool 含 reject path 污染）— '
    '見 CLAUDE.md §九 Non-training surfaces 標準。'
    'ML training 仍用 learning.decision_features（V017，intent-only emit）。';
COMMENT ON COLUMN learning.decision_features_evaluations.evaluation_outcome IS
    'PredictorAction outcome enum (V082 §CHECK)：accept/reject/reject_add/'
    'shadow_fill/fallback_use_legacy/fallback_fail_closed/use_legacy_no_predictor';
COMMENT ON COLUMN learning.decision_features_evaluations.evidence_source_tier IS
    'CLAUDE.md §九 Non-training surfaces 標準。'
    'evaluation_log = 常規 candidate evaluation；'
    'shadow_synthetic = ε-greedy ShadowFill 觀測（pair with decision_shadow_fills）。'
    '故意與 V050 replay.simulated_fills 的 tier 字串不重疊。';
COMMENT ON COLUMN learning.decision_features_evaluations.entry_context_id IS
    'M2 trigger 鋪路欄位（W-AUDIT-4b-M2 將回填）。'
    '當前 M1 producer 寫 NULL；M2 attribution chain trigger 從 trading.fills completed 後 '
    '反向 update 此欄位，建立 evaluation → entry → fill 完整鏈路。';
COMMENT ON COLUMN learning.decision_features_evaluations.context_id IS
    'Candidate intent 的 context_id；與 V017 learning.decision_features.context_id 同語意。'
    '注意：同一 context_id 可有多 evaluation（無 dedup），與舊表 PK=context_id 不同。';

-- ============================================================
-- Verification / 驗證查詢（操作者手動執行）
-- ============================================================
-- 表存在 / Table exists:
--   SELECT to_regclass('learning.decision_features_evaluations');
--   Expected: non-null
--
-- Column 列表 / Column list:
--   SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_schema='learning'
--     AND table_name='decision_features_evaluations'
--   ORDER BY ordinal_position;
--   Expected: 16 rows (evaluation_id ... created_at)
--
-- CHECK 約束 / CHECK constraints:
--   SELECT conname, pg_get_constraintdef(oid)
--   FROM pg_constraint
--   WHERE conrelid='learning.decision_features_evaluations'::regclass
--     AND contype='c';
--   Expected: 3 rows (outcome / evidence_tier / side)
--
-- 索引 / Indexes:
--   SELECT indexname, indexdef
--   FROM pg_indexes
--   WHERE schemaname='learning'
--     AND tablename='decision_features_evaluations';
--   Expected: 5 rows (PK + 4 user indexes)
--
-- ============================================================
