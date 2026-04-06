-- ============================================================
-- V009 — Phase 4 Pre-Fix 1: ML/News tables + decision_context columns
-- V009 — Phase 4 預修 1：ML/新聞表 + decision_context 新欄位
-- ============================================================
--
-- Phase 4 (Claude Teacher / LinUCB / News / DL-3) DDL prerequisites.
-- Most "8 tables" from the Phase 4 spec already exist in V001-V007:
--   learning.teacher_directives       — V004 (directive_id SERIAL PK)
--   learning.directive_executions     — V004 (FK → teacher_directives)
--   learning.bayesian_posteriors      — V004 (NIG four params, regime PK)
--   learning.cpcv_results             — V004 (4-fold)
--   observability.scorer_predictions  — V004 (hypertable 1d)
--   observability.model_performance   — V004 (hypertable 7d)
--   market.news_signals               — V002 (hypertable 7d)
-- Only `learning.linucb_state` is genuinely new for Phase 4.
--
-- Phase 4 預修任務原指 8 張新表，但其中 7 張在 Phase 0a (V001-V007) 已建。
-- 本次只新增 LinUCB 狀態表 + decision_context_snapshots 5 個欄位
-- （其中 news_severity 已存在於 V003，hours_since_news 對應已存在的
-- hours_since_last_major_news，故僅補 3 個 LinUCB / Teacher 連結欄位）。
--
-- Source / 來源:
--   docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md §DB schema
--   docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md
--   docs/references/2026-04-04--execution_plan_v1.md Phase 4
--
-- Spec vs ask divergences (spec wins) / 規格 vs 任務差異（以規格為準）:
--   - teacher_directives.directive_id is SERIAL/INT (V004), not UUID.
--     → claude_directive_id is INT, not UUID.
--   - news_severity / hours_since_last_major_news already exist in V003.
--     → only 3 new columns added below.
-- ============================================================


-- ============================================================
-- 1. learning.linucb_state — LinUCB contextual bandit state
--    LinUCB 上下文 bandit 狀態（per-arm A 矩陣 / b 向量）
-- Source: v0.5 §1.2 + ml_dl_learning_architecture_v0.4 §LinUCB
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.linucb_state (
    arm_id              TEXT        PRIMARY KEY,        -- e.g. "trending_btcusdt_ma_crossover"
    a_matrix            BYTEA       NOT NULL,           -- 序列化 numpy d×d 矩陣 / serialized numpy d×d
    b_vector            BYTEA       NOT NULL,           -- 序列化 numpy d 向量 / serialized numpy d-vector
    context_dim         INT         NOT NULL,           -- d (context vector dimension)
    n_pulls             BIGINT      NOT NULL DEFAULT 0, -- 該 arm 被選次數 / times this arm was pulled
    cumulative_reward   DOUBLE PRECISION NOT NULL DEFAULT 0,  -- 累積回報 / cumulative reward
    alpha               REAL        NOT NULL DEFAULT 1.0,     -- 探索系數 / exploration coefficient
    last_updated_ts     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes               TEXT
);

COMMENT ON TABLE learning.linucb_state IS
    'LinUCB contextual bandit per-arm state (A matrix, b vector, pulls, reward) | LinUCB 上下文 bandit per-arm 狀態';
COMMENT ON COLUMN learning.linucb_state.arm_id IS
    'Composite arm identifier, e.g. {regime}_{symbol}_{strategy} | 組合 arm 標識';
COMMENT ON COLUMN learning.linucb_state.a_matrix IS
    'Serialized numpy d×d design matrix (A = I + sum x x^T) | 序列化的 d×d 設計矩陣';
COMMENT ON COLUMN learning.linucb_state.b_vector IS
    'Serialized numpy d-vector (b = sum r_i x_i) | 序列化的 d 維獎勵向量';
COMMENT ON COLUMN learning.linucb_state.context_dim IS
    'Context feature vector dimension d | 上下文特徵維度 d';
COMMENT ON COLUMN learning.linucb_state.alpha IS
    'UCB exploration coefficient; higher = more exploration | 探索系數';

CREATE INDEX IF NOT EXISTS idx_linucb_state_updated
    ON learning.linucb_state (last_updated_ts DESC);


-- ============================================================
-- 2. trading.decision_context_snapshots — add Phase 4 linkage columns
--    新增 Phase 4 連結欄位（Teacher / LinUCB）
-- Source: execution_plan_v1 Phase 4 §decision context extension
-- Note: news_severity + hours_since_last_major_news already in V003
-- ============================================================
ALTER TABLE trading.decision_context_snapshots
    ADD COLUMN IF NOT EXISTS claude_directive_id INTEGER DEFAULT NULL;

ALTER TABLE trading.decision_context_snapshots
    ADD COLUMN IF NOT EXISTS linucb_arm_id TEXT DEFAULT NULL;

ALTER TABLE trading.decision_context_snapshots
    ADD COLUMN IF NOT EXISTS linucb_confidence_bound REAL DEFAULT NULL;

COMMENT ON COLUMN trading.decision_context_snapshots.claude_directive_id IS
    'Logical FK -> learning.teacher_directives.directive_id (NULL if no teacher directive influenced this decision) | 對應 Claude Teacher 指令 ID（無則 NULL）';
COMMENT ON COLUMN trading.decision_context_snapshots.linucb_arm_id IS
    'Logical FK -> learning.linucb_state.arm_id (which bandit arm produced this decision) | 對應 LinUCB arm ID';
COMMENT ON COLUMN trading.decision_context_snapshots.linucb_confidence_bound IS
    'LinUCB UCB value at decision time (mean + alpha*sqrt(x^T A^-1 x)) | 決策時的 LinUCB UCB 值';

-- Index to support "find decisions driven by a given directive" lookups
CREATE INDEX IF NOT EXISTS idx_decision_context_claude_directive
    ON trading.decision_context_snapshots (claude_directive_id)
    WHERE claude_directive_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_decision_context_linucb_arm
    ON trading.decision_context_snapshots (linucb_arm_id, ts DESC)
    WHERE linucb_arm_id IS NOT NULL;


-- ============================================================
-- 驗證 / Verification
-- ============================================================
-- SELECT tablename FROM pg_tables WHERE schemaname='learning' AND tablename='linucb_state';
-- 預期 / Expect: 1 row
--
-- SELECT column_name FROM information_schema.columns
--  WHERE table_schema='trading' AND table_name='decision_context_snapshots'
--    AND column_name IN ('claude_directive_id','linucb_arm_id','linucb_confidence_bound',
--                        'news_severity','hours_since_last_major_news')
--  ORDER BY column_name;
-- 預期 / Expect: 5 rows
-- ============================================================
