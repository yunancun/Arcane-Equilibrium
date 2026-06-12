-- ============================================================
-- V139: agent.agent_memory + agent.agent_memory_embedding_meta
--       L2 結構化記憶層核心表（零擴展依賴；pgvector 軸在 V140 獨立緩裝）
--
-- 目的：
--   L2 蒸餾管線（memory_distiller）把每日 l2_calls + gate 報告蒸餾成三類
--   結構化記憶（system_trait/incident/rule），供未來 L2 session 召回注入。
--   借鑒 TencentCloud/TencentDB-Agent-Memory l1_records（MIT License）
--   移植 PG + 交易語義改造（PA spec 2026-06-11--l2_memory_layer_design.md §2）。
--   注意：該上游專案服務的外部開源助手恰好也叫「OpenClaw」，與本 repo 的
--   OpenClaw 控制面家族同名純屬巧合，無任何代碼或協議關聯。
--
-- 範圍 / 硬邊界：
--   - additive only；不改任何既有表、不碰 order / promotion / lease / live。
--   - 純學習記憶層（root principle 7），非交易真相層，不授權任何 live 行為。
--   - 寫入唯一入口 = memory_distiller.store（INSERT + 受限 UPDATE）+ seed CLI；
--     UPDATE 僅限 status/superseded_by/updated_at/embedding/embedding_pending
--     （application discipline，content 不可變——merge 產物是新 row）。
--   - DELETE 永久 REVOKE：記憶不物理刪，merge/update 走 status='superseded'
--     + superseded_by 鏈（原則 8 可重建）。
--
-- 為什麼 idempotent / double-apply safe：
--   依 feedback_v_migration_pg_dry_run.md，first-apply PASS ≠ re-apply 安全。
--   全部物件用 IF NOT EXISTS；Guard A 在表已存在時反射必要欄位，缺欄即 RAISE，
--   避免「表存在但 schema 漂移」被靜默放過。Linux PG 實證 dry-run owed
--   （E4 雙 apply 冪等驗），本檔先確保 SQL 本身安全且可重入。
--
-- Guard：
--   Guard A：既有表缺必要欄 → RAISE。
--   Guard B：型別敏感欄反射（smallint/jsonb/timestamptz/tsvector/boolean）。
--   Guard C：FTS GIN + trgm GIN + 游標索引存在性。
-- ============================================================

BEGIN;

-- pg_trgm：召回 FTS 級的中文兜底軸（Linux prod 已 installed 1.6；冪等保險）。
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS agent;

-- Guard A：表已存在時反射必要欄位，缺欄即 RAISE。
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'agent' AND table_name = 'agent_memory'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'record_id','content','mem_type','priority','scene','source_refs',
            'event_time_str','event_start','event_end',
            'created_at','updated_at','status','superseded_by',
            'embedding_pending','metadata','content_tsv'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'agent' AND table_name = 'agent_memory'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V139 Guard A FAIL: agent.agent_memory exists but missing columns: %.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS agent.agent_memory (
    record_id         TEXT        PRIMARY KEY,          -- "mem:<uuid12>" / "mem:seed:<sha12>"
    content           TEXT        NOT NULL,             -- 完整獨立的記憶陳述（不可變）
    mem_type          TEXT        NOT NULL,             -- 三類交易語義
    priority          SMALLINT    NOT NULL DEFAULT 50,  -- -1=鐵則；0-100
    scene             TEXT        NOT NULL DEFAULT '',  -- 情境名（蒸餾批次語境）
    source_refs       JSONB       NOT NULL DEFAULT '[]'::jsonb,
                      -- [{"kind":"l2_call","id":"l2r:..."},{"kind":"drar","id":123},
                      --  {"kind":"lesson","id":4},{"kind":"memory_topic","path":"memory/x.md"}]
    event_time_str    TEXT        NOT NULL DEFAULT '',  -- LLM 原話時間描述
    event_start       TIMESTAMPTZ,                      -- 可解析時填
    event_end         TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status            TEXT        NOT NULL DEFAULT 'active',
    superseded_by     TEXT,                             -- merge/update 時指向接替 record_id
    embedding_pending BOOLEAN     NOT NULL DEFAULT true, -- V140 補嵌游標（V140 未裝時恆 true 無害）
    metadata          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- FTS 生成列：'simple' config（拍板）。中文短語召回由 trgm 軸補。
    content_tsv       tsvector    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    CONSTRAINT chk_agent_memory_mem_type CHECK (
        mem_type IN ('system_trait','incident','rule')
    ),
    CONSTRAINT chk_agent_memory_priority CHECK (priority BETWEEN -1 AND 100),
    CONSTRAINT chk_agent_memory_status CHECK (status IN ('active','superseded')),
    -- superseded 必有指向；active 必無指向（狀態機一致性）
    CONSTRAINT chk_agent_memory_supersede_link CHECK (
        (status = 'active' AND superseded_by IS NULL)
        OR (status = 'superseded' AND superseded_by IS NOT NULL)
    )
);

-- FTS GIN（拍板軸）
CREATE INDEX IF NOT EXISTS idx_agent_memory_tsv
    ON agent.agent_memory USING gin (content_tsv);
-- trgm GIN（中文兜底軸，V133 idx_agent_lessons_content_trgm 先例）
CREATE INDEX IF NOT EXISTS idx_agent_memory_content_trgm
    ON agent.agent_memory USING gin (content gin_trgm_ops);
-- 增量游標（dedup 候選掃描 / 觀測查詢只看 active）
CREATE INDEX IF NOT EXISTS idx_agent_memory_status_updated
    ON agent.agent_memory (status, updated_at DESC);
-- 召回過濾主軸（mem_type 分塊 + priority 排序）
CREATE INDEX IF NOT EXISTS idx_agent_memory_type_status_priority
    ON agent.agent_memory (mem_type, status, priority DESC);
-- 補嵌 job 游標（partial：只索引待嵌 active 行）
CREATE INDEX IF NOT EXISTS idx_agent_memory_embed_pending
    ON agent.agent_memory (updated_at)
    WHERE embedding_pending AND status = 'active';

-- Guard B：型別敏感欄反射。
-- 註：content_tsv 為 pg_catalog 內建型 tsvector，information_schema.columns
--     的 data_type 直接反射為 'tsvector'（USER-DEFINED 僅見於 extension 型如 vector）。
DO $$
DECLARE
    v_bad TEXT[];
BEGIN
    SELECT array_agg(column_name || ':' || data_type) INTO v_bad
    FROM information_schema.columns
    WHERE table_schema = 'agent' AND table_name = 'agent_memory'
      AND (
        (column_name = 'priority' AND data_type <> 'smallint')
        OR (column_name = 'source_refs' AND data_type <> 'jsonb')
        OR (column_name = 'metadata' AND data_type <> 'jsonb')
        OR (column_name = 'created_at' AND data_type <> 'timestamp with time zone')
        OR (column_name = 'event_start' AND data_type <> 'timestamp with time zone')
        OR (column_name = 'embedding_pending' AND data_type <> 'boolean')
        OR (column_name = 'content_tsv' AND data_type <> 'tsvector')
      );
    IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
        RAISE EXCEPTION 'V139 Guard B FAIL: agent.agent_memory type drift: %.', v_bad;
    END IF;
END $$;

-- Guard C：三條檢索索引 + 游標索引存在性。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='agent'
        AND tablename='agent_memory' AND indexname='idx_agent_memory_tsv') THEN
        RAISE EXCEPTION 'V139 Guard C FAIL: idx_agent_memory_tsv missing.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='agent'
        AND tablename='agent_memory' AND indexname='idx_agent_memory_content_trgm') THEN
        RAISE EXCEPTION 'V139 Guard C FAIL: idx_agent_memory_content_trgm missing.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='agent'
        AND tablename='agent_memory' AND indexname='idx_agent_memory_status_updated') THEN
        RAISE EXCEPTION 'V139 Guard C FAIL: idx_agent_memory_status_updated missing.';
    END IF;
END $$;

-- DELETE 永久封禁（UPDATE 保留給 supersede/補嵌；content 不可變屬 application discipline）。
REVOKE DELETE ON agent.agent_memory FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE DELETE ON agent.agent_memory FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON agent.agent_memory TO trading_ai';
        RAISE NOTICE 'V139: agent.agent_memory — trading_ai = SELECT/INSERT/UPDATE; DELETE revoked';
    ELSE
        RAISE NOTICE 'V139: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;

COMMENT ON TABLE agent.agent_memory IS
    'L2 structured memory store (system_trait/incident/rule). Distilled daily from l2_calls + gate reports by memory_distiller. Merge/update = supersede chain (status+superseded_by), never physical DELETE. Learning memory only, not trading authority.';
COMMENT ON COLUMN agent.agent_memory.content IS
    'Immutable. Dedup merge/update writes a NEW row and marks old rows superseded; content is never rewritten in place (lineage, root principle 8).';

-- ── embedding meta（單行表：provider/model/dims 漂移偵測）──
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'agent' AND table_name = 'agent_memory_embedding_meta'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY['meta_id','provider','model','dims','updated_at']) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'agent'
              AND table_name = 'agent_memory_embedding_meta' AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V139 Guard A FAIL: embedding_meta exists but missing columns: %.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS agent.agent_memory_embedding_meta (
    meta_id    SMALLINT    PRIMARY KEY DEFAULT 1,
    provider   TEXT        NOT NULL,             -- 'ollama'
    model      TEXT        NOT NULL,             -- 'bge-m3'
    dims       INTEGER     NOT NULL,             -- 1024
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_embedding_meta_singleton CHECK (meta_id = 1)
);

REVOKE DELETE ON agent.agent_memory_embedding_meta FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE DELETE ON agent.agent_memory_embedding_meta FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON agent.agent_memory_embedding_meta TO trading_ai';
    END IF;
END $$;

COMMENT ON TABLE agent.agent_memory_embedding_meta IS
    'Singleton row recording which embedding provider/model/dims produced agent_memory.embedding. Backfill job compares against current config; mismatch => mark all rows embedding_pending=true + NULL embedding (re-index), then update this row.';

COMMIT;
