-- ============================================================
-- V133: agent.lessons
--       L2 Reflexion 教訓索引庫（indexed lesson store）
--
-- 目的：
--   B 工作流（Reflexion critic + lesson store）需要一張可被
--   pg_trgm 相似度檢索的教訓表。L2 session 結束時把 insight 落為
--   lesson row（persist_lessons）；下一次 session 開頭依 symbol +
--   context_hint 以 trigram 相似度撈回最相關的數條（retrieve_lessons），
--   讓 agent 帶著過往教訓推理。
--
-- 範圍 / 硬邊界：
--   - additive only；不改任何既有表、不碰 order / promotion / lease。
--   - 此表純為 L2 自學記憶，非交易真相層，不授權任何 live 行為。
--   - outcome_net_bps 為 forward-stub：trading.decision_outcomes.outcome_* 目前
--     100% NULL（已知 bug），故本欄位現階段永遠寫 NULL，待歸因管線修復後回填。
--     任何讀取端不得假設此欄非空。
--   - 寫入唯一入口為 persist_lessons 的單條 INSERT；read 路徑唯讀。
--
-- 為什麼 idempotent / double-apply safe：
--   依 feedback_v_migration_pg_dry_run.md，first-apply PASS ≠ re-apply 安全。
--   全部物件用 IF NOT EXISTS；Guard A 在表已存在時反射必要欄位，缺欄即 RAISE，
--   避免「表存在但 schema 漂移」被靜默放過。Linux PG 實證 dry-run 仍 owed
--   （operator-gated），本檔先確保 SQL 本身安全且可重入。
--
-- Guard：
--   Guard A：既有表缺必要欄 → RAISE。
--   Guard B：核心欄位型別反射。
--   Guard C：trigram GIN 索引與檢索 btree 索引存在性。
-- ============================================================

BEGIN;

-- pg_trgm：retrieve_lessons 用 content % $hint 與 similarity() 做相似度檢索。
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- agent schema 在 V064 已建；此處再保險一次（IF NOT EXISTS 冪等）。
CREATE SCHEMA IF NOT EXISTS agent;

-- Guard A：表已存在時，反射必要欄位，缺欄即 RAISE（防 schema 漂移）。
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'agent'
          AND table_name = 'lessons'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id',
            'created_at',
            'symbol',
            'lesson_type',
            'content',
            'session_trigger',
            'context_id',
            'outcome_net_bps',
            'session_cost_usd',
            'source'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'agent'
              AND table_name = 'lessons'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V133 Guard A FAIL: agent.lessons exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS agent.lessons (
    id               BIGSERIAL   PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol           TEXT        NOT NULL,
    lesson_type      TEXT        NOT NULL,
    content          TEXT        NOT NULL,
    session_trigger  TEXT,
    context_id       TEXT,
    outcome_net_bps  REAL,
    session_cost_usd REAL,
    source           TEXT        NOT NULL DEFAULT 'l2_session'
);

-- 檢索熱路徑：retrieve_lessons 以 symbol(+lesson_type) 過濾後 recency 兜底排序。
CREATE INDEX IF NOT EXISTS idx_agent_lessons_symbol_type_created
    ON agent.lessons (symbol, lesson_type, created_at DESC);

-- trigram 相似度索引：支撐 content % $hint 與 similarity(content,$hint) 排序。
CREATE INDEX IF NOT EXISTS idx_agent_lessons_content_trgm
    ON agent.lessons USING gin (content gin_trgm_ops);

COMMENT ON TABLE agent.lessons IS
    'L2 Reflexion indexed lesson store. persist_lessons writes one row per session insight; retrieve_lessons reads via pg_trgm similarity with recency fallback. Learning memory only, not trading authority.';

COMMENT ON COLUMN agent.lessons.outcome_net_bps IS
    'Forward-stub. trading.decision_outcomes.outcome_* currently 100% NULL (known bug); always NULL until attribution pipeline is fixed. Readers must not assume non-null.';

-- Guard B：核心欄位型別反射。
DO $$
DECLARE
    v_bad TEXT[];
BEGIN
    SELECT array_agg(column_name || ':' || data_type) INTO v_bad
    FROM information_schema.columns
    WHERE table_schema = 'agent'
      AND table_name = 'lessons'
      AND (
        (column_name = 'symbol' AND data_type <> 'text')
        OR (column_name = 'lesson_type' AND data_type <> 'text')
        OR (column_name = 'content' AND data_type <> 'text')
        OR (column_name = 'outcome_net_bps' AND data_type <> 'real')
        OR (column_name = 'session_cost_usd' AND data_type <> 'real')
        OR (column_name = 'source' AND data_type <> 'text')
      );

    IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
        RAISE EXCEPTION
            'V133 Guard B FAIL: agent.lessons type drift: %.',
            v_bad;
    END IF;
END $$;

-- Guard C：檢索所需索引存在性（trigram GIN + symbol/type/created btree）。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'agent'
          AND tablename = 'lessons'
          AND indexname = 'idx_agent_lessons_content_trgm'
    ) THEN
        RAISE EXCEPTION
            'V133 Guard C FAIL: content trigram GIN index missing.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'agent'
          AND tablename = 'lessons'
          AND indexname = 'idx_agent_lessons_symbol_type_created'
    ) THEN
        RAISE EXCEPTION
            'V133 Guard C FAIL: symbol/type/created btree index missing.';
    END IF;
END $$;

COMMIT;
