-- ============================================================
-- manual V140: agent.agent_memory pgvector 軸（embedding 欄 + HNSW）
--
-- 【手動 apply 檔——刻意不在 sql/migrations/】（PA 2026-06-11 spec §3.2 路徑 B）：
--   CREATE EXTENSION vector 通常需要 superuser/db-owner 權限；若以 migration
--   入鏈而權限不足，sqlx fail-stop 會卡死 V141+ 整條鏈。故本檔放
--   helper_scripts/db/ 由 operator 以足夠權限手動 apply（建議經
--   apply_manual_V140_agent_memory_vector.sh，含權限失敗清晰報錯與退出碼）。
--   V140 號保留給本檔（號已預留，不可挪用——migration 號是全局命名空間）。
--
-- 前提：V139（agent.agent_memory）已 apply；pgvector extension 在 PG 安裝目錄
--   available（Linux prod 已驗 0.8.1 available 未 installed）。
--
-- 冪等：CREATE EXTENSION IF NOT EXISTS / ADD COLUMN IF NOT EXISTS /
--   CREATE INDEX IF NOT EXISTS——雙 apply 安全，重跑 no-op。
--
-- 未 apply 時的系統行為：recall 偵測 embedding 欄缺 → 自動降 FTS-only，
--   不 raise（spec §3.2 運行時降級）；本檔永遠是可選增強軸。
--
-- dims=1024（bge-m3 固定維度；嵌入請求體一律不帶 dimensions 欄位——
--   bge-m3 不支持 matryoshka，帶了 HTTP 400，TencentDB README:336）。
--
-- rollback（出問題時，forward-fix 不改本檔）：
--   DROP INDEX IF EXISTS agent.idx_agent_memory_embedding_hnsw;
--   ALTER TABLE agent.agent_memory DROP COLUMN IF EXISTS embedding;
--   管線無 V140 強依賴，FTS-only 繼續運行。
--
-- 維度遷移 runbook（換 embedding 模型且維度改變時，例 1024 → 768；
--   MIT ratify 條件 ③，文字 runbook——列型 vector(1024) 是唯一 schema 鎖點，
--   runtime 側 dims 全為活探測無硬編）：
--   0) 停補嵌軸：OPENCLAW_L2_MEMORY_EMBED_BACKFILL=0（crontab env 行），
--      防遷移中途 backfill 寫舊維度向量。
--   1) DROP INDEX IF EXISTS agent.idx_agent_memory_embedding_hnsw;
--   2) ALTER TABLE agent.agent_memory DROP COLUMN IF EXISTS embedding;
--   3) ALTER TABLE agent.agent_memory ADD COLUMN embedding vector(<新dims>);
--      （drop+重建而非 ALTER TYPE：新舊維度向量不可比，必須全表重嵌，
--        重建列天然全 NULL）
--   4) CREATE INDEX idx_agent_memory_embedding_hnsw
--          ON agent.agent_memory USING hnsw (embedding vector_cosine_ops);
--   5) 重置補嵌游標 + meta（meta 表 DELETE 已 REVOKE，reset 走 UPDATE）：
--      UPDATE agent.agent_memory SET embedding_pending = true;
--      UPDATE agent.agent_memory_embedding_meta
--          SET model = '<新模型>', dims = <新dims>, updated_at = NOW()
--          WHERE meta_id = 1;
--      （略過本步時下輪 backfill 的漂移偵測也會 mark-all + upsert meta 自動
--        收斂；顯式 reset 只是消掉過渡期 [89] 漂移 WARN 窗口）
--   6) 同步代碼側常數與 env：checks_l2_memory.EXPECTED_EMBED_DIMS
--      （1024→新值）+ OPENCLAW_L2_MEMORY_EMBED_MODEL + 本檔 dims 注釋；
--      不同步則 [89] 持續 WARN（tripwire 設計如此）。
--   7) 重開 OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1，驗收 backfill 收斂
--      （日誌 embedded>0 且 embedding_pending 計數歸零）。
-- ============================================================

BEGIN;

-- 前提守門：V139 未 apply 即 RAISE（清晰錯誤訊息供 apply wrapper 分類退出碼）。
DO $$
BEGIN
    IF to_regclass('agent.agent_memory') IS NULL THEN
        RAISE EXCEPTION
            'manual V140 prerequisite FAIL: agent.agent_memory missing — apply V139 first.';
    END IF;
END $$;

-- 權限敏感點：失敗訊息通常為 "permission denied to create extension" /
-- "must be superuser"（apply wrapper 以此分類 exit 3）。
CREATE EXTENSION IF NOT EXISTS vector;

-- Guard B'（type-sensitive ADD COLUMN）：欄已存在但型別非 vector → RAISE。
-- 注意 vector 型在 information_schema.columns 的 data_type='USER-DEFINED'，
-- 必須用 udt_name 反射。
DO $$
DECLARE
    v_udt TEXT;
BEGIN
    SELECT udt_name INTO v_udt
    FROM information_schema.columns
    WHERE table_schema = 'agent' AND table_name = 'agent_memory'
      AND column_name = 'embedding';
    IF v_udt IS NOT NULL AND v_udt <> 'vector' THEN
        RAISE EXCEPTION
            'manual V140 Guard B FAIL: embedding column exists with udt %, expected vector.', v_udt;
    END IF;
END $$;

ALTER TABLE agent.agent_memory ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- HNSW cosine（表小 <10k rows，默認 m/ef_construction 足夠；建索引秒級）。
CREATE INDEX IF NOT EXISTS idx_agent_memory_embedding_hnsw
    ON agent.agent_memory USING hnsw (embedding vector_cosine_ops);

COMMENT ON COLUMN agent.agent_memory.embedding IS
    'bge-m3 1024-dim embedding (Ollama /v1/embeddings, request body WITHOUT dimensions field). NULL until backfill job fills; recall degrades to FTS when NULL/column absent.';

COMMIT;
