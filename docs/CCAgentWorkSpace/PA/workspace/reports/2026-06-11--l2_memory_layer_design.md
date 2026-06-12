# L2 結構化記憶層 — 完整技術 Spec（V139/V140 + 蒸餾管線 + 召回接縫 + seed CLI）

- 日期：2026-06-11
- 作者：PA
- 狀態：**E1-READY（design-only，本批 0 feature code by PA）**
- 借鑒源：TencentCloud/TencentDB-Agent-Memory（MIT，`/tmp/repo-eval/TencentDB-Agent-Memory`）
- 基準：local main `296a77b9`（origin/main `c9e160f6`；brief 寫的 `39b7ff73` 在本 repo 不可解析，
  已以 fetch 後的 origin/main 重驗全部編號占用，不構成 blocker）
- 部署目標：全部 flag-OFF inert；新表零 live 寫路徑；cron 安裝後行為中性

---

## 0. 一頁摘要

為 OpenClaw 建「L2 結構化記憶層」：把每日 L2 呼叫帳本（`agent.l2_calls`）與 gate 報告
（V131 drar→postmortem taxonomy）經本地 LLM（Ollama qwen3.5:9b）蒸餾成三類結構化記憶
（`system_trait`/`incident`/`rule`），存入新表 `agent.agent_memory`（V139，FTS+trgm 雙路檢索，
零擴展依賴），pgvector 語義檢索為獨立 V140 緩裝軸（bge-m3 嵌入，缺模型自動 FTS-only）。
dedup 用「召回 top-5 候選 → 單次 LLM batch 裁決 store/skip/update/merge」兩段式
（抄改 TencentDB l1-extraction/l1-dedup prompt）。B3 生產召回注入本批只留 dormant 接縫
（`layer2_engine.py:604` 旁），zero engine diff。seed CLI 把 agent.lessons dead-modes +
`srv/memory/MEMORY.md` 索引條目一次性重放入庫。

成本證成（原則 13）：管線僅 2 次本地 Ollama call/日（cost_usd=0），零雲端調用；
預期收益=L2 session 帶歷史教訓推理（B 工作流 retrieve_lessons 的結構化升級），
失敗模式=記憶庫無用（dormant，零交易影響）。

---

## 1. Grounding 事實清單（全部親查，file:line / runtime）

| # | 事實 | 證據 |
|---|---|---|
| G1 | V139/V140 free | `ls sql/migrations/` + `git ls-tree origin/main`（fetch 後）：head=V138；prod `_sqlx_migrations` head=**137**（V138 prod apply owed，operator-gated） |
| G2 | healthcheck 占用至 [87] | `passive_wait_healthcheck/runner.py:589-590`（canonical 註冊清單）：cursor 區 `[83]-[87]`（L2 P4 五軸）；canary namespace 至 [80]。**下一免費段=[88]** |
| G3 | `agent.l2_calls` 24 欄 schema | Linux PG 反射（24 rows）+ V134 原文；現有 1 row（E2E-1）；append-only REVOKE UPDATE/DELETE |
| G4 | `agent.lessons` 結構+seed | V133 原文（id/created_at/symbol/lesson_type/content/.../source；pg_trgm GIN）；runtime 6 rows 全 `source='dead_mode_seed'`, `lesson_type='dead_mode'`, `symbol='ml_advisory'`，英文主幹 |
| G5 | 擴展狀態 | Linux PG：pg_trgm 1.6 **installed**；timescaledb 2.26.1 installed；vector 0.8.1 **available 未 installed** |
| G6 | Ollama 模型 | trade-core `curl /api/tags`：僅 `qwen3.5:9b-q4_K_M` + `qwen3.5:27b-q4_K_M`；**無 bge-m3**（嵌入模型缺=部署日 FTS-only 是事實預設，非理論降級） |
| G7 | LocalLLMClient 抽象 | `program_code/local_model_tools/local_llm_client.py:59`（ABC：`generate(prompt,*,system,temperature,max_tokens,timeout_s)->LLMResponse` / `is_available`）；工廠 `control_api_v1/app/local_llm_factory.py:392 get_local_llm_client(heavy=False)`→OllamaClient 單例（`ollama_client.py:48-49`：base=`http://127.0.0.1:11434` env `OLLAMA_BASE_URL`，model=`qwen3.5:9b-q4_K_M` env `OLLAMA_MODEL`） |
| G8 | cron import app 模組先例 | `helper_scripts/cron/ml_training_maintenance.py:103 _ensure_repo_imports` + `:429` import `control_api_v1.app.auth` —— cron 進程 import app leaf 模組是 vetted 慣例 |
| G9 | cron 三件套範本 | `helper_scripts/cron/incident_sentinel_cron.sh`（108 行：mkdir lock+secrets grep-parse+heartbeat+fail-soft exit 0）+ `install_incident_sentinel_cron.sh`（119 行：Linux-only+dry-run 預設+APPLY=1 gate+--remove+idempotent guard） |
| G10 | cron 避撞表 | 03:00 pg_dump / 03:17 ml_training_maintenance / 04:00 m11_replay / 04:41 feature_baseline / 06:00 counterfactual_daily / 09:00 key_rotation / */5 incident_sentinel（SCRIPT_INDEX.md:400 + installer 註釋） |
| G11 | postmortem 分類器**零 caller、零持久化** | `learning_engine/signal_postmortem.py`（純函數 `classify_signal_failure`，0 DB 0 wiring；grep 全 repo 僅自身命中）——「postmortem 產物」**不存在現成 DB sink**，本設計改為 distiller 內聯呼叫（§6.2） |
| G12 | drar 表（gate 報告 DB 落點） | V131 `learning.demo_residual_alpha_reports`（report_jsonb JSONB + first/last_seen_ts）——postmortem evidence bundle 的唯一現成持久化源 |
| G13 | B3 注入點 | `layer2_engine.py:604` `_critic.retrieve_lessons(...)`（run_session 開頭、prompt 組裝前）；`:825 persist_lessons`；SYSTEM_PROMPT 拼裝 `:647/:673` |
| G14 | retrieve_lessons 召回範式 | `layer2_critic.py:278-379`：pg_trgm `content %% hint` + `SET LOCAL similarity_threshold=0.1` + recency 兜底 + fail-soft 回 `[]` NEVER raise + `asyncio.to_thread` |
| G15 | seed 源在 repo 內 | `srv/memory/` 存在（MEMORY.md 索引 + feedback_*/project_*/reference_* topic 檔）——**跨平台路徑安全**（非 `~/.claude` Mac 專屬路徑） |
| G16 | TencentDB l1_records schema | `src/core/store/sqlite.ts:557-588`（record_id PK/content/type/priority/scene_name/timestamp 三欄/created·updated/metadata_json + 增量複合索引 `(session_key,updated_time)`） |
| G17 | TencentDB 兩 prompt | `src/core/prompts/l1-extraction.ts:16-102`（單次 call：情境切分+三類抽取+JSON 數組）；`l1-dedup.ts:15-69`（統一候選池 batch 裁決 store/skip/update/merge） |
| G18 | sendDimensions 坑 | TencentDB README:336：bge-m3 不支持 matryoshka，請求帶 `dimensions` 欄→HTTP 400。**我們的 embedding 請求體一律不帶 dimensions** |
| G19 | registry/flag 慣例 | `settings/l2_capability_registry.toml`（TOML SSOT、enabled=false fail-closed、unknown field reject）；env flag 慣例=`OPENCLAW_*` 默認 0 |
| G20 | hypertable 適用性 | db-schema skill §1.1：config/registry 類=regular table。`agent_memory` 是 mutable 小記憶庫（預期 <10k rows）→ **plain table，不做 hypertable**（也避開 compressed-twin/UPDATE 衝突整族問題） |

---

## 2. V139 — `agent.agent_memory` 核心表（零擴展依賴）

### 2.1 設計裁決（與 TencentDB 對映 + repo 改造）

| 軸 | TencentDB l1_records | 本設計 | 理由 |
|---|---|---|---|
| 表名/schema | l1_records (SQLite) | `agent.agent_memory` | 拍板表名字面保留；schema 跟 L2 家族（V133/V134 先例） |
| type | persona/episodic/instruction | `mem_type` CHECK `system_trait/incident/rule` | 拍板語義改造；欄名避 `type` 裸保留字（V133 `lesson_type` 先例） |
| 可變性 | upsert+delete | **UPDATE 允許、DELETE REVOKE、merge=軟刪除**（status='superseded'+superseded_by） | dedup 裁決需要改寫；但原則 8 要 lineage 可重建 → 物理刪禁止，supersede 鏈保全史。`agent_memory` 是記憶庫非 ledger（V133 lessons 同類，無 append-only REVOKE；與 V134 ledger 不同類） |
| timestamp 三欄 | timestamp_str/start/end (TEXT) | `event_time_str TEXT` + `event_start/event_end TIMESTAMPTZ` | str 保 LLM 原話；可解析時填 typed 欄供範圍查詢 |
| FTS | FTS5+jieba 分詞 | **tsvector('simple') 生成列+GIN（拍板）+ pg_trgm GIN 雙路**（trgm 已 installed，V133 先例） | 'simple' 對中文連續文本切詞弱；trgm 對 CJK 有效且 repo 已驗證（G14 similarity 0.1 門檻教訓）。召回 SQL 雙路 UNION 取 top-5，仍是「FTS 級」單一降級檔位 |
| 向量 | sqlite-vec 虛擬表 | V140 pgvector 欄（獨立緩裝） | §3 |
| 增量游標 | (session_key,updated_time) 複合 | `(status, updated_at)` 複合 + `embedding_pending` partial | 我們無 session_key 維度；dedup/補嵌走 status+updated_at |

### 2.2 完整 DDL 草稿（E1 直接抄，Guard A/B/C 照 V133/V134 範式）

```sql
-- ============================================================
-- V139: agent.agent_memory + agent.agent_memory_embedding_meta
--       L2 結構化記憶層核心表（零擴展依賴；pgvector 軸在 V140 獨立緩裝）
--
-- 目的：
--   L2 蒸餾管線（memory_distiller）把每日 l2_calls + gate 報告蒸餾成三類
--   結構化記憶（system_trait/incident/rule），供未來 L2 session 召回注入。
--   借鑒 TencentDB-Agent-Memory l1_records（MIT）移植 PG + 交易語義改造。
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
```

### 2.3 V139 注意點

- **不做 hypertable**（G20）：mutable 小表 + 需要 UPDATE，plain table 是 skill §1.1 正解；
  也徹底繞開 TimescaleDB compressed-twin / UPDATE 衝突。
- `content_tsv` 生成列在 Guard B 反射為 `data_type='tsvector'`（PG 生成列在
  information_schema.columns 正常出現，已按此寫 Guard B）。
- supersede CHECK 約束把「active 卻有指向 / superseded 卻無指向」直接擋在 DB 層。
- Linux dry-run（E1 sign-off 前 owed，feedback_v_migration_pg_dry_run）：雙 apply 冪等 +
  Guard A 觸發測試（scratch DB 建漂移表）+ `trading_ai` 無 DELETE 驗證。
- **V138 連帶提醒**：prod sqlx head=137，V139 deploy 時 V138 會一起 apply（V138 已 E4
  GREEN，僅排程事實，operator-gated apply 不在本批）。

---

## 3. V140 — pgvector 軸（獨立檔，緩裝雙路徑）

### 3.1 DDL 草稿

```sql
-- ============================================================
-- V140: agent.agent_memory pgvector 軸（embedding 欄 + HNSW）
--
-- 前提：pgvector 0.8.1 在 Linux prod 為 available 未 installed（已驗）。
--   CREATE EXTENSION vector 通常需要 superuser/db-owner 權限；本檔進
--   migration 鏈的前提 = Linux dry-run 以 trading_admin 實證 CREATE
--   EXTENSION 成功。失敗 ⇒ 本檔【不得進 sql/migrations/】（sqlx 鏈
--   fail-stop 會卡死 V141+），改走 §3.2 緩裝路徑。
--
-- dims=1024（bge-m3 固定維度；嵌入請求體不帶 dimensions 欄位——
--   bge-m3 不支持 matryoshka，帶了 HTTP 400，TencentDB README:336）。
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- Guard B'（type-sensitive ADD COLUMN）：欄已存在但型別非 vector → RAISE。
DO $$
DECLARE
    v_udt TEXT;
BEGIN
    SELECT udt_name INTO v_udt
    FROM information_schema.columns
    WHERE table_schema = 'agent' AND table_name = 'agent_memory'
      AND column_name = 'embedding';
    IF v_udt IS NOT NULL AND v_udt <> 'vector' THEN
        RAISE EXCEPTION 'V140 Guard B FAIL: embedding column exists with udt %, expected vector.', v_udt;
    END IF;
END $$;

ALTER TABLE agent.agent_memory ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- HNSW cosine（表小，默認 m/ef_construction 足够；建索引秒級）
CREATE INDEX IF NOT EXISTS idx_agent_memory_embedding_hnsw
    ON agent.agent_memory USING hnsw (embedding vector_cosine_ops);

COMMENT ON COLUMN agent.agent_memory.embedding IS
    'bge-m3 1024-dim embedding (Ollama /v1/embeddings, request body WITHOUT dimensions field). NULL until backfill job fills; recall degrades to FTS when NULL/column absent.';

COMMIT;
```

注意：vector 型在 `information_schema.columns` 的 `data_type='USER-DEFINED'`，
Guard 用 `udt_name='vector'`（上面已按此寫）。

### 3.2 緩裝雙路徑（降級路徑，設計完成必備項）

| 分支 | 條件 | 動作 |
|---|---|---|
| 路徑 A（首選） | Linux dry-run：`ssh trade-core 'psql -U trading_admin -d <scratch> -c "CREATE EXTENSION vector;"'` 成功 | V140 進 `sql/migrations/`，正常入鏈 |
| 路徑 B（緩裝） | dry-run 權限不足（needs superuser） | V140 檔改放 `helper_scripts/db/manual_V140_agent_memory_vector.sql`（內容同上），**不進 migration 鏈**；operator 以管理權限手動 apply；V140 號保留給此檔（號已預留不可挪用）；系統 FTS-only 運行 |
| 運行時降級 | embedding 欄不存在（路徑 B 未 apply）/ bge-m3 未 pull | recall vector 級偵測 `UndefinedColumn` / embed client `is_available()=False` → 自動降 FTS 級，不 raise（§6.4） |

rollback：路徑 A 下 V140 出問題 → `DROP INDEX idx_agent_memory_embedding_hnsw; ALTER TABLE agent.agent_memory DROP COLUMN embedding;`（forward-fix migration，不改已 apply 檔——sqlx checksum 鐵則 a19797d）；管線無 V140 依賴，FTS-only 繼續運行。

---

## 4. 模組檔案清單 + 行數預算（全部 <800 行/檔，註釋中文）

新 package：`program_code/learning_engine/memory_distiller/`
（落點理由：蒸餾是學習管線歸 learning_engine；cron 獨立進程經 G8 慣例 import；
與 control_api app 解耦——僅 LLM client 經工廠注入時觸 app leaf 模組）

| 檔 | 預算 | 內容 |
|---|---|---|
| `__init__.py` | ~30 | 導出 public API |
| `prompts.py` | ~280 | 抽取/dedup 兩 system prompt 常數（§5 全文）+ user prompt builder 純函數 |
| `parsing.py` | ~170 | LLM JSON 輸出解析：markdown fence 剝除、數組校驗、欄位白名單、**dedup 段 fail-open-to-store**、extraction 段 fail-to-skip |
| `store.py` | ~260 | `MemoryStore`（conn 注入）：insert_record / supersede_records（UPDATE 限 status/superseded_by/updated_at）/ load_candidates_by_ids / 游標讀取。零模組級連線 |
| `recall.py` | ~230 | 三級降級召回（§6.4）：`recall_top_k(conn, text, k=5)` + B3 接縫 `recall_for_prompt(...)`（§8） |
| `embedding.py` | ~170 | `OllamaEmbeddingClient`（urllib，POST `/v1/embeddings`，**body 不帶 dimensions**；`is_available`/`embed_batch`）+ 漂移偵測 helper |
| `pipeline.py` | ~330 | `run_daily(conn, llm, ...)`：讀源（l2_calls+drar→postmortem 內聯）→ extraction → 召回 → dedup → 執行裁決 → 補嵌（flag-gated）→ 統計 JSON |
| `backfill_embeddings.py` | ~130 | 補嵌 batch（embedding_pending 游標 + meta 漂移→重索引標記） |

cron / CLI / seed（`helper_scripts/`）：

| 檔 | 預算 | 內容 |
|---|---|---|
| `cron/l2_memory_distill.py` | ~170 | CLI 殼：`_ensure_repo_imports` 仿（G8）+ flag gate（連 DB 前）+ psycopg2 連線（POSTGRES_* env）+ `get_local_llm_client()` 注入 + 游標狀態檔 + exit code |
| `cron/l2_memory_distill_cron.sh` | ~110 | mirror `incident_sentinel_cron.sh`（G9）：lock dir + secrets grep-parse + heartbeat `cron_heartbeat/l2_memory_distill.last_fire` + fail-soft exit 0 |
| `cron/install_l2_memory_distill_cron.sh` | ~120 | mirror installer（G9）：Linux-only / dry-run 預設 / `OPENCLAW_L2_MEMORY_CRON_APPLY=1` / `--remove` / idempotent guard。cron 行：`23 5 * * *`（05:23 UTC，避撞 G10 全表） |
| `memory/seed_agent_memory.py` | ~280 | §9 seed CLI（自帶 INSERT SQL，不 import distiller——與 E1-A 檔案零重疊） |

SQL：`sql/migrations/V139__agent_memory_store.sql`（§2.2）+
`V140__agent_memory_vector.sql`（§3，路徑 A 才入此目錄）。

測試（§13）：`program_code/learning_engine/memory_distiller/tests/`（E1-A）+
`helper_scripts/memory/test_seed_agent_memory.py`、cron 殼測試（E1-B）。

另：`helper_scripts/SCRIPT_INDEX.md` 必須更新（CLAUDE §七）；
`passive_wait_healthcheck/runner.py` 註冊清單註釋加 1 行 reserved 標記（§12）。

---

## 5. 兩段 prompt 草稿（抄改 TencentDB，中文化+交易語義；E1 直接取用）

### 5.1 抽取 prompt（`EXTRACT_MEMORIES_SYSTEM_PROMPT`，改自 l1-extraction.ts:16-102）

```text
你是 OpenClaw 交易系統的「運維情報蒸餾專家」。
你的任務是分析給定的 L2 AI 呼叫記錄與信號失敗報告，從中提取結構化的核心記憶
（僅限 system_trait, incident, rule 三類）。

**輸出語言**：所有自由文本欄位（scene、content）使用繁體中文；技術名詞、代碼
標識、策略名、symbol、JSON 欄位名、枚舉值、ISO 時間戳保持英文。

### 任務一：情境歸納（scene）
為本批材料歸納一個情境名稱（例如「我在覆盤 2026-06-10 的 ml_advisory 診斷呼叫
與 cascade_fade 失敗報告」），30-50 字、單句。

### 任務二：核心記憶提取
【通用提取原則】
1. 寧缺毋濫：過濾一次性操作細節、無結論的中間輸出、純狀態回報；剔除不可靠
   的邊緣信息。每批 0-8 條為宜。
2. 獨立完整：記憶必須「跳出本批材料依然成立」，無上下文也能看懂。主體必須
   明確（哪個策略 / 哪個模組 / 哪類市場狀態）。
3. 歸納合併：強因果關聯的多條材料必須合併為一條完整記憶，不可碎片化。
4. 嚴禁編造：每條記憶必須給出 source_ids（來自材料中的 [id] 標記）；無法
   對應到具體材料的內容不得輸出。

【支持提取的三大類型】（必須嚴格遵守類型規則）
1. 系統特質 (mem_type: "system_trait")
   - 定義：系統、策略、模型、市場結構的穩定屬性與行為模式（如「qwen3.5:9b
     輸出 JSON 偶爾包 markdown fence」「TONUSDT demo 盤口薄、滑點大」）。
   - 句式：「[主體] 在 [條件] 下表現出 [穩定特性]」。
   - priority：80-100（影響風控/資金安全的特質）；50-70（一般行為特性）；
     <50（模糊次要，丟棄）。
2. 事件記憶 (mem_type: "incident")
   - 定義：客觀發生的一次性事件、故障、決定或結果。不含純推測。
   - 句式：「[時間] [主體] 發生 [事件]（起因/經過/結果）」。
   - 時間：盡量從材料 timestamp 推算絕對時間；可確定時在 metadata 填
     activity_start_time / activity_end_time（ISO 8601）。
   - priority：80-100（造成損失/宕機/誤判的事件）；60-70（一般完整事件）；
     <60（瑣碎，丟棄）。
3. 規則記憶 (mem_type: "rule")
   - 定義：應長期遵守的行為規則、檢驗準則、禁令（如「任何短 bias 信號必須
     先做 beta 中性化檢驗」「rolling 窗口含 current bar 必然假 mean-revert」）。
   - 句式：「[條件] 時必須/禁止 [行為]，因為 [理由]」。
   - priority：-1（不可違反的鐵則）；90-100（核心檢驗規則）；70-80（重要
     慣例）；<70（臨時性，丟棄）。

### 不應該提取的內容
- 單次呼叫的中間參數、token 統計、延遲數字
- 與交易/系統運維無關的內容；重複已知的常識
- 純推測（材料中無事實支撐）；AI 自身的客套輸出

### 輸出格式（JSON）
返回且僅返回一個合法 JSON 對象：
{
  "scene": "情境名稱",
  "memories": [
    {
      "content": "完整、獨立的記憶陳述",
      "mem_type": "system_trait|incident|rule",
      "priority": 80,
      "source_ids": ["材料id_1"],
      "event_time_str": "2026-06-10 前後",
      "metadata": {}
    }
  ]
}
無有意義記憶時 memories 為空數組。不要輸出任何 markdown 代碼塊修飾符或解釋文字。
```

User prompt builder（`format_extraction_prompt`）：仿 l1-extraction.ts:115-145 —
頭部聲明 UTC 時區 + 逐條材料 `[id] [source_kind] [ISO ts]: <截斷文本>`。
材料 id 規則：`l2:<l2_reply_id>` / `drar:<report_id>`（parse 回 source_refs）。

### 5.2 dedup prompt（`CONFLICT_DETECTION_SYSTEM_PROMPT`，改自 l1-dedup.ts:15-69）

```text
你是 OpenClaw 交易系統的記憶衝突檢測器。批量比較多條【新記憶】與【統一候選
記憶池】中的已有記憶，逐條決定如何處理。

**輸出語言**：merged_content 使用繁體中文（技術名詞保持英文）；JSON 欄位名、
枚舉值、record_id、ISO 時間戳保持英文。

## 核心規則
- 跨類型合併：不同 mem_type（system_trait/incident/rule）的記憶若語義上描述
  同一事實/事件/規則，可以合併；合併後判斷最佳 merged_type。
- 多對多合併：一條新記憶可同時替換候選池中的多條舊記憶（target_ids 數組）。
- 規則升級：同一規則的更精確版本（加了條件、閾值、理由）→ update。
- 事件聚合：同一事故的前因後果 → merge 為一條完整敘述。

## 動作定義
- "store"：新信息，直接新增。
- "skip"：已有記憶更好，新記憶無增量。
- "update"：同一事實，新記憶更具體/更晚/糾錯，以新記憶為主覆蓋。
- "merge"：信息互補不矛盾，合併成一條更完整記憶。

## 輸出格式
嚴格輸出 JSON 數組，每個元素對應一條新記憶的決策，不輸出任何其他內容：
[
  {
    "record_id": "新記憶的 record_id",
    "action": "store|update|skip|merge",
    "target_ids": ["被取代的候選 record_id"],
    "merged_content": "合併/更新後的記憶內容（merge/update 必填）",
    "merged_type": "system_trait|incident|rule（merge/update 必填）",
    "merged_priority": 85
  }
]
target_ids 只能取自該條新記憶的【關聯候選 ID】列表。store/skip 時 target_ids
省略或為空。合併後信息更完整時 merged_priority 可酌情提升。
```

User prompt builder（`format_batch_dedup_prompt`）：照抄 l1-dedup.ts:94-167 結構
（統一候選池 JSON + 逐條新記憶 + 關聯候選 ID；池空 ⇒ 直接全 store 短路，
**省一次 LLM call**——TencentDB 同款行為）。

---

## 6. 蒸餾管線（pipeline.py）— 調用流程

### 6.1 觸發與游標

- daily cron 05:23 UTC（G10 避撞）。flag `OPENCLAW_L2_MEMORY_PIPELINE`（默認 0）
  在 CLI 殼**連 DB 之前**檢查，off ⇒ log + exit 0（零連線零副作用）。
- 游標：狀態檔 `${OPENCLAW_DATA_DIR}/cron_state/l2_memory_distill_cursor.json`
  （`{"last_success_utc_date": "2026-06-10"}`；mirror sentinel state 檔慣例，
  跨進程獨立不共寫）。處理窗 = (cursor+1 日) .. (昨日)，**上限回看 7 日**
  （防長期停擺後爆量）；成功才推進 cursor，失敗日下輪自動補跑。

### 6.2 輸入源（每個 UTC 日）

1. `agent.l2_calls`：`created_at >= D 00:00 AND < D+1 00:00`，
   `ORDER BY created_at LIMIT 200`（R5 cap）。每 row 取
   `capability_id/trigger/parsed_output/raw_response`（每欄截斷 4KB）。唯讀。
2. `learning.demo_residual_alpha_reports`（V131）：`first_seen_ts` 同窗新 row
   （LIMIT 20）。對每 row 以 `report_jsonb` 作 evidence bundle **內聯呼叫**
   `learning_engine.signal_postmortem.classify_signal_failure()`（G11：純函數
   零 caller，本設計給它第一個消費者；evidence 欄位不足時它自身誠實降
   confidence，不硬湊）→ taxonomy+confidence+strategy_name 文本化為材料塊。
3. 兩源皆空 ⇒ 當日 no-op，推進 cursor。

### 6.3 兩段式 LLM（單日最多 2 次 call，皆本地 Ollama）

```
材料塊[..] ──(1) extraction call (qwen3.5:9b, temperature=0.1,
              max_tokens=2000, timeout_s=180)──> memories[0..8]
每條候選 ──(2) 召回 top-5（§6.4 三級降級）──> 統一候選池
全部候選+池 ──(3) dedup call（同參數；池全空則跳過 call 直接全 store）
            ──> 裁決[..]
(4) 執行：store=INSERT；skip=no-op；
    update/merge=INSERT 新 row（source_refs=新∪舊 並集，metadata 記
    merged_from）+ 舊 target rows UPDATE status='superseded',
    superseded_by=<新 record_id>, updated_at=NOW()。
    單裁決一個事務（部分失敗不污染整批）。
```

parser 行為（§風險 R2 的對偶）：
- **extraction parse fail ⇒ 當日該批 skip + WARN log + cursor 不推進**
  （fail-open-to-store 在此段無對象——沒有解析出的記憶可存；偽造=違反
  「不得 fake AI 產物」硬邊界）。
- **dedup parse fail / 裁決行缺欄 / action 非法 / target_ids 越界 ⇒
  該條（或整批）fail-open-to-store**：直接 INSERT 新記憶、不動舊記憶。
  寧可暫時重複，不可丟失或誤刪——重複會被未來輪次 dedup 收斂。

### 6.4 召回三級降級（recall.py，dedup 與 B3 共用）

```
L1 vector：embedding 欄存在 AND meta 行存在 AND embed client 可用
   → 對候選 content 嵌入一次 → ORDER BY embedding <=> $vec LIMIT 5
   （WHERE status='active' AND embedding IS NOT NULL）
   例外（UndefinedColumn / embed 失敗 / 連線錯）→ 降 L2，不 raise
L2 FTS：tsvector 與 trgm 雙路 UNION（單 SQL）：
   SELECT ... , GREATEST(ts_rank(content_tsv, plainto_tsquery('simple',$q)),
                          similarity(content,$q)) AS score
   FROM agent.agent_memory
   WHERE status='active'
     AND (content_tsv @@ plainto_tsquery('simple',$q) OR content % $q)
   ORDER BY score DESC LIMIT 5
   （事務內 SET LOCAL pg_trgm.similarity_threshold=0.1，G14 教訓）
   例外 → 降 L3
L3 skip：回空 list（dedup 對該候選=池空=直接 store）
```

### 6.5 成本與證成（原則 13）

每日 ≤2 次 qwen3.5:9b 本地推理（cost_usd=0.0，LLMResponse 合約 G7），
零雲端 token。9b 單 call 估 30-120s，05:23 槽位無鄰接 cron。
管線寫入唯一目標=agent.agent_memory（學習平面）。

---

## 7. embedding 軸（deferred；同 flag 家族）

- `OllamaEmbeddingClient`（memory_distiller/embedding.py，新獨立小類——
  **不擴 LocalLLMClient ABC**：embed 非 generate 語義，動穩定抽象影響全部
  既有 provider；仿其風格自帶 is_available/embed_batch/get_model_info）。
  - `POST {OLLAMA_BASE_URL:-http://127.0.0.1:11434}/v1/embeddings`
    body=`{"model": "bge-m3", "input": [<texts>]}` — **絕不帶 dimensions
    欄位**（G18 matryoshka 400 坑）。
  - 模型名 env `OPENCLAW_L2_MEMORY_EMBED_MODEL`（默認 `bge-m3`）。
  - 缺模型（HTTP 404 / error body）⇒ `is_available()=False` ⇒ 全系統
    FTS-only（G6：現機未 pull bge-m3，**部署即此態**；pull 後自動升級）。
- 寫入時 embedding 可空：insert 一律 `embedding_pending=true`，不在寫路徑嵌入
  （寫路徑不依賴 embed 服務可用性）。
- 補嵌 job（backfill_embeddings.py）：daily pipeline 尾端執行，
  flag `OPENCLAW_L2_MEMORY_EMBED_BACKFILL`（默認 0）另控：
  1. 漂移偵測：meta 行 (provider,model,dims) vs 當前 config 不符 ⇒
     `UPDATE agent_memory SET embedding=NULL, embedding_pending=true`（全表）
     + UPDATE meta 行 ⇒ 標記重索引（任務拍板語義）。meta 行不存在 ⇒ INSERT。
  2. 批處理：`WHERE embedding_pending AND status='active' ORDER BY updated_at
     LIMIT 256`，embed_batch 後逐行 `UPDATE SET embedding=$v,
     embedding_pending=false`。
  3. V140 未 apply（無 embedding 欄）⇒ 啟動時探測欄存在性，缺 ⇒ no-op log。

---

## 8. B3 召回注入 = 本批只留 dormant 接縫（zero engine diff）

- **本批交付**：`recall.py` 內接口 + 單元測試。**不改 `layer2_engine.py` 任何
  一行**（高風險檔，等影子期批次）。
- 接口（釘死簽名，未來批次 E1 直接接）：

```python
@dataclass
class RecallBundle:
    stable_block: str    # rule + system_trait；priority DESC、record_id 次序穩定
                         # → 拼進 system prompt 尾（跨 session 字面穩定，KV cache 友好）
    recent_block: str    # incident；recency DESC → 拼進 user message 頭
    record_ids: list[str]
    total_chars: int
    degraded_level: str  # "vector" | "fts" | "skip"

async def recall_for_prompt(
    symbol: str, context_hint: str, *,
    char_budget: int = 2000,       # stable 70% / recent 30%，超限按序截斷整條
    timeout_s: float = 5.0,        # asyncio.wait_for 包裹；逾時回空 bundle（fail-open）
) -> RecallBundle: ...
```

- 注入點（spec for future batch）：`layer2_engine.py:604` retrieve_lessons 同位置，
  flag `OPENCLAW_L2_MEMORY_RECALL` ∈ {`0`,`shadow`,`1`}（默認 `0`）：
  - `0`：不呼叫（本批部署後狀態）。
  - `shadow`（影子期）：計算 bundle，**不注入 prompt**；engine 把
    `{"memory_recall_shadow": {record_ids, total_chars, degraded_level}}` 併入
    record_l2_call 的 `input_context`（l2_calls 既有 engine 寫路徑天然落庫，
    零新表零 schema 改動）→ 事後 SQL 可審「本應注入什麼」。
  - `1`：stable_block 拼 system prompt 尾、recent_block 拼 user message 頭。
  - 任何例外/逾時 ⇒ 空 bundle ⇒ 行為等同 flag=0（fail-open，召回永不阻斷 session）。

---

## 9. seed CLI（`helper_scripts/memory/seed_agent_memory.py`）

一次性重放兩源入庫（mirror `helper_scripts/m4/seed_dead_mode_lessons.py` 慣例）：

| 源 | 映射 | 條數 |
|---|---|---|
| A：`agent.lessons` WHERE `lesson_type='dead_mode'`（G4：6 rows） | mem_type=`rule`，priority=90，content=lesson content 原文，source_refs=`[{"kind":"lesson","id":<id>}]`，scene=`seed:dead_mode` | 6 |
| B：`srv/memory/MEMORY.md` 索引條目（repo 內，G15 跨平台安全） | 逐行 parse `- [title](topic.md) — summary`：`feedback_*` → `rule`(priority 80)；`project_*` → `incident`(priority 70)；**排除 `reference_*` 與「External tool authority」節**；content=`title — summary`（索引行即現成人寫蒸餾，CLI 零 LLM 依賴、確定性），source_refs=`[{"kind":"memory_topic","path":"memory/<file>"}]` | ~55 |

- 敏感過濾雙層：①來源白名單（僅 feedback_/project_ 前綴）；②regex 安全網掃
  content（`(api[_-]?key|secret|password|token|Bearer )`，命中即 skip+列報告）。
- 冪等錨：`record_id = "mem:seed:" + sha256(content)[:12]`，
  INSERT `ON CONFLICT (record_id) DO NOTHING`（重跑零重複）。
- 默認 `--dry-run`（列印將寫入清單）；`--write` + `--dsn`（或 POSTGRES_* env）
  才真寫。自帶 INSERT SQL（不 import memory_distiller —— E1-A/E1-B 檔案零重疊）。
- 驗收（G4 pg_trgm 三重對齊教訓）：seed 後必須跑一條真 recall SQL
  （§6.4 L2 級）以中文+英文 hint 各驗一次命中非空，不能只驗 INSERT 成功。

---

## 10. Flag 表（全默認 OFF；env 慣例 G19）

| Flag | 默認 | 控制 | 檢查位置 |
|---|---|---|---|
| `OPENCLAW_L2_MEMORY_PIPELINE` | `0` | daily 蒸餾管線總開關 | CLI 殼連 DB 前；off=exit 0 |
| `OPENCLAW_L2_MEMORY_EMBED_BACKFILL` | `0` | 補嵌 job | pipeline 尾端 |
| `OPENCLAW_L2_MEMORY_RECALL` | `0` | B3 注入（`0/shadow/1`）| 本批僅 spec（§8），不接線 |
| `OPENCLAW_L2_MEMORY_CRON_APPLY` | `0` | installer 寫 crontab gate | install script |
| `OPENCLAW_L2_MEMORY_EMBED_MODEL` | `bge-m3` | 嵌入模型名 | embedding.py |

cron 安裝後 flag-OFF ⇒ 每日 05:23 啟動即 exit 0（一行 log + heartbeat），inert。
rollback 全鏈：`install_l2_memory_distill_cron.sh --remove`（+APPLY=1）⇒ 回到
本批前狀態；表為 inert 資料可留；V139 不需回滾（additive、零 caller 強依賴）。

---

## 11. cron / installer（mirror G9 三件套）

- wrapper `l2_memory_distill_cron.sh`：lock dir
  `${DATA}/locks/l2_memory_distill_cron.lock.d`、secrets grep-parse（POSTGRES_*，
  與 incident_sentinel_cron.sh 同款不裸 source）、log
  `${DATA}/logs/l2_memory_distill_cron.log`、heartbeat
  `${DATA}/cron_heartbeat/l2_memory_distill.last_fire`、fail-soft exit 0
  （cron mail spam 防護；失敗已寫 log，下輪補跑——§6.1 游標保證不丟日）。
- installer：Linux-only guard / dry-run 預設 / `--remove` / idempotent refuse /
  cron 行 `23 5 * * * OPENCLAW_BASE_DIR=... l2_memory_distill_cron.sh`。
- `SCRIPT_INDEX.md` 新增三行（wrapper/installer/seed CLI）。

---

## 12. healthcheck 號預留

- canonical 註冊處 = `passive_wait_healthcheck/runner.py`（G2）。
- **預留 [88][89]**：[88] `l2_memory_pipeline_freshness`（cursor 滯後 >3 日且
  flag=1 ⇒ WARN；表可達性）；[89] `l2_memory_embedding_drift`（meta vs config
  不符且 backfill flag=1 ⇒ WARN）。
- 本批**不實作** check 本體（dormant 系統無 runtime 可監測，假 check=噪音）；
  E1-B 僅在 runner.py 註冊清單註釋（:589-590 區）加一行
  `[88][89] reserved: L2 memory layer (2026-06-11 PA spec)`——號占用以該註釋為
  全局命名空間正本（V137/[82] 撞號教訓：migration/healthcheck 號是 git 看不見
  的全局命名空間，先佔註釋防並行撞號）。

---

## 13. 測試計劃

### 13.1 單元（Mac 可跑；**全部 autouse `_no_real_db`**，承 0ce45a09 prod 污染教訓）

| 模組 | 重點 case |
|---|---|
| parsing | 合法 JSON / markdown fence 包裹 / 非法 JSON / 欄位缺失 / mem_type 非法 / priority 越界（clamp 到 [-1,100]）/ **dedup fail-open-to-store 斷言** / extraction fail-to-skip 斷言 / target_ids 越界（不在關聯候選列表 ⇒ 該條降 store） |
| prompts | builder 純函數快照：材料 id 格式 `l2:`/`drar:`、截斷、池空短路訊息 |
| store | FakeConn：insert 冪等（ON CONFLICT）/ supersede 只 UPDATE 三欄+updated_at / **斷言 SQL 文本 0 出現 DELETE** |
| recall | vector 級拋 UndefinedColumn ⇒ 落 FTS；FTS 拋例外 ⇒ 落 skip 回 []；不冒泡；RecallBundle 預算截斷與 stable/recent 分塊 |
| embedding | mock urllib：請求 body **斷言無 dimensions key**；404 ⇒ is_available False；400 matryoshka 文案 ⇒ False；批次切分 |
| pipeline | FakeLLM 注入：四裁決執行路徑 / 兩源皆空 no-op / cursor 推進與失敗不推進 / 單裁決事務隔離 / cap LIMIT 生效 |
| backfill | meta 漂移 ⇒ 全表標記重索引；欄缺 ⇒ no-op；批次游標 |
| seed CLI | dry-run 零寫 / regex 敏感攔截 / MEMORY.md parse / reference_* 排除 / 冪等錨 |
| cron 殼 | flag=0 ⇒ exit 0 且 **0 DB 連線**（FakeConn 計數）；flag=1 注入 fake pipeline |

### 13.2 scratch-DB E2E（Linux，`ssh trade-core`，scratch database）

1. V139 雙 apply 冪等（Guard A/B/C 全過）+ 故意建漂移表斷言 Guard A RAISE。
2. V140 權限 dry-run：trading_admin `CREATE EXTENSION vector` ⇒ 決定路徑 A/B
   （**設計凍結後第一個 Linux 動作**，結果寫回 deploy 計劃）。成功則雙 apply。
3. seed CLI `--write` 入 scratch ⇒ 真 recall SQL 中/英 hint 各一次命中非空。
4. pipeline FakeLLM + 真 scratch DB：插 2 條假 l2_calls ⇒ run_daily ⇒ 斷言
   agent_memory 真 row + supersede 鏈正確 + cursor 檔推進。
5. （可選，operator-gated）真 Ollama 一次 extraction call 煙測（qwen3.5:9b
   真 JSON 輸出過 parser）。

### 13.3 mutation 點（E2 對抗錨）

①壞 dedup JSON ⇒ 全 store（fail-open）；②meta 漂移 ⇒ 重索引標記；③flag=0 ⇒
cron 零連線；④merge ⇒ 舊 row superseded 非 DELETE、content 未變；⑤無 V140 ⇒
vector 級降級不 raise；⑥extraction 壞 JSON ⇒ 0 row 入庫 + cursor 不推進。

---

## 14. E1 派工切分（2 線並行，檔案零重疊）

| 線 | 範圍 | 檔 |
|---|---|---|
| **E1-A**（主體，~1,600 行碼+測試） | V139/V140 SQL + `memory_distiller/` 全 package + 單元測試 | `sql/migrations/V139*.sql`（V140 待 §13.2-2 裁決路徑後入位）+ `program_code/learning_engine/memory_distiller/**` |
| **E1-B**（外圍，~900 行） | cron 三件套 + seed CLI + SCRIPT_INDEX.md + runner.py 1 行 reserved 註釋 + 各自測試 | `helper_scripts/cron/l2_memory_distill*` + `helper_scripts/memory/seed_agent_memory.py` + `helper_scripts/SCRIPT_INDEX.md` + `passive_wait_healthcheck/runner.py`（僅註釋行） |

- 互不依賴：seed CLI 自帶 SQL（§9）；cron 殼呼叫 `pipeline.run_daily` 以
  string import + try/except ImportError ⇒ 「module 未落地」log+exit 0
  （兩線真並行、合流後自然接通；E1-B 測試 mock import）。
- 兩線共同必讀：本 spec §2/§5/§6 + V133/V134 原文 + incident_sentinel 三件套。
- 順序約束：V139 Linux dry-run（§13.2-1/2）在 E1-A sign-off 前 owed；
  V138 prod apply 是既有 owed（operator-gated），與本批解耦。

## E2 重點審查 3 點

1. **supersede 紀律**：全部 UPDATE 語句只動 `status/superseded_by/updated_at/
   embedding/embedding_pending`；`content` 0 處被 UPDATE；`DELETE FROM
   agent.agent_memory` 0 出現（grep 可證）。
2. **fail-open 邊界正確性**：fail-open-to-store 僅存在於 dedup 段；extraction
   parse fail 必須是 skip+log（grep parser 兩段的 except 路徑）——反向寫法
   = 偽造記憶 = 觸「不得 fake AI 產物」硬邊界。
3. **flag gate 在連線之前 + 降級不冒泡**：cron 殼 flag 檢查先於任何 psycopg2
   connect；recall 三級降級的兩個 except 都不得 re-raise；embedding 請求 body
   無 `dimensions` key。

---

## 15. 風險表

| # | 風險 | 等級 | 緩解/降級 |
|---|---|---|---|
| R1 | V140 CREATE EXTENSION 權限不足卡死 sqlx 鏈 | 高 | §3.2 雙路徑；dry-run 先行裁決，失敗檔不入 migrations/ |
| R2 | qwen3.5:9b 中文 JSON 輸出不穩 | 中 | fence 剝除+白名單校驗+兩段差異化 fail 策略（§6.3）+游標補跑 |
| R3 | 'simple' tsvector 中文召回弱 | 中 | trgm 雙路 UNION（G14 已驗 0.1 門檻）+ V140 vector 級長期解 |
| R4 | LLM 幻覺記憶入庫污染 | 中 | source_ids 強制（prompt+parser 雙層，缺=丟棄）；priority<50/<60/<70 分類型丟棄線；supersede 可修正；dormant 期零生產影響 |
| R5 | l2_calls 增長後輸入爆量 | 低 | LIMIT 200 row + 每欄 4KB 截斷 + 回看上限 7 日 |
| R6 | 漂移誤觸發全表重索引 | 低 | 單行 meta 表+嚴格三元組比對；表小重嵌成本分鐘級 |
| R7 | cron import app leaf 模組拉起重依賴 | 低 | G8 先例；E1 驗 import 鏈不觸 FastAPI app 本體；LLM client 經參數注入可換 |
| R8 | seed 洩漏敏感內容 | 低 | 白名單+regex 雙層（§9）+ dry-run 默認人工過目 |

## CC 豁免聲明（16 根原則映射）

本批不觸 execution authority：①新表 `agent.agent_memory` 屬學習平面（原則 7），
零 live config/order/lease 寫路徑，管線對 `l2_calls`/`drar` 唯讀（原則 2）；
②記憶是 AI 產物的存檔與召回上下文，永不成為命令——B3 注入本批不接線，未來
也僅改變 prompt 上下文，決策仍經既有 Lease 鏈（原則 3）；③全 flag 默認 OFF、
fail-open 只向「不注入/不阻斷」方向（原則 6 收縮性成立：worst case=今日
baseline）；④LLM 全本地 Ollama cost=0、bge-m3 缺=FTS-only 仍可運行（原則
13/14）；⑤supersede 鏈+source_refs 保全史可重建（原則 8）。硬邊界指紋
（live_execution_allowed/max_retries/authorization.json 等）0 觸碰。

---
PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-11--l2_memory_layer_design.md
