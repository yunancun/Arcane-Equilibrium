-- ============================================================
-- V134: agent.l2_calls + agent.l2_consequential_marks
--       L2 Advisory Mesh — D3 Provenance & Audit 地基（Phase 1）
--
-- 目的：
--   L2（Layer 2 AI 推理）每次模型呼叫的「完整 prompt/response 取證帳本」。
--   現況 D3 中心缺口（PA 設計 §0 已 file:line 核實）：layer2_engine 把
--   system_prompt 餵給模型卻從不持久化完整 prompt/response，唯一落庫的是
--   lesson insight（agent.lessons）。本表補上 reconstructable 取證帳本
--   （root principle 8：每個決策可重建可解釋）。
--
--   agent.l2_calls          —— 單次 L2 呼叫的完整（已消毒）取證帳本。
--   agent.l2_consequential_marks —— later-discovered「成為 consequential」事件
--                               side-table（append-only，多次/多原因/多 lane 標記）。
--
-- 範圍 / 硬邊界：
--   - additive only；不改任何既有表、不碰 order / promotion / lease / live。
--   - 純 audit/provenance，非交易真相層，不授權任何 live 行為。
--   - 純 append-only：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT；
--     全表零 column-level UPDATE grant（operator-LOCKED Option (c)）。
--     consequential_at_creation 為 INSERT-set-once 不可變欄位，永不 UPDATE，
--     故不需任何 UPDATE grant；「事後發現 consequential」走 marks 表 INSERT。
--   - 為何零 column-level UPDATE grant 是 load-bearing：column-level GRANT
--     UPDATE(col) 會被 TimescaleDB 傳播到 _compressed_hypertable_NN twin，
--     其欄位為 compressed-segment 格式 → grant abort（V114:208-216 已驗
--     42703 undefined_column）。零 column-grant 故本表將來可自由開壓縮，
--     無 V114 twin 陷阱。P1 本身不開壓縮、不寫 retention（§A.4.4 post-P1）。
--   - 寫入唯一入口 = L2CallLedgerWriter（INSERT-only）；read 路徑唯讀 SELECT。
--   - sha256 在「已消毒」文本上計算（prompt_sha256 / response_sha256）；
--     消毒在 writer INSERT 之前跑（§B 寫入路徑無窗口），不是事後清洗。
--
-- 為什麼 idempotent / double-apply safe：
--   依 feedback_v_migration_pg_dry_run.md，first-apply PASS ≠ re-apply 安全。
--   全部物件用 IF NOT EXISTS；Guard A 在表已存在時反射必要欄位，缺欄即 RAISE，
--   避免「表存在但 schema 漂移」被靜默放過。REVOKE 區塊用 DO 包住，dev sandbox
--   無 trading_ai role 時 NOTICE 不報錯。Linux PG 實證 dry-run owed
--   （operator-gated；E4 雙 apply 冪等驗），本檔先確保 SQL 本身安全且可重入。
--
-- Guard：
--   Guard A：既有表缺必要欄 → RAISE（兩表各一）。
--   Guard B：型別敏感欄位反射（jsonb / numeric / timestamptz / boolean / text）。
--   Guard C：lineage + forensic 索引存在性。
--
-- Precedent（file:line）：
--   - REVOKE 區塊 = V099:298-307（autonomy_level_switch_audit append-only）。
--   - hypertable + 複合 PK = V064:163,180-184（decision_state_changes）。
--   - side-table event-sourced = V054:225,240（learning.lease_transitions）。
--   - sha256 CHECK 風格 = V064:62-64（payload_hash regex）/ V132 bare-hex 風格。
--   - columnstore 陷阱（本表不觸及，僅作對照）= V077 / V101:170-181。
-- ============================================================

BEGIN;

-- agent schema 在 V001/V064/V133 已建；此處再保險一次（IF NOT EXISTS 冪等）。
CREATE SCHEMA IF NOT EXISTS agent;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A（ledger）：表已存在時反射 24 必要欄位，缺欄即 RAISE（防 schema 漂移）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'agent' AND table_name = 'l2_calls'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'l2_reply_id',
            'session_id',
            'capability_id',
            'trigger',
            'created_at',
            'model',
            'model_version',
            'contract_ver',
            'schema_ver',
            'system_prompt',
            'input_context',
            'raw_response',
            'parsed_output',
            'guard_verdict',
            'fact_inf_assm',
            'input_tokens',
            'output_tokens',
            'cost_usd',
            'latency_ms',
            'prompt_sha256',
            'response_sha256',
            'redactor_version',
            'error_code',
            'consequential_at_creation'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'agent' AND table_name = 'l2_calls'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V134 Guard A FAIL: agent.l2_calls exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Main DDL：agent.l2_calls（24-column 取證帳本）
--   PK = (l2_reply_id, created_at)：TimescaleDB hypertable 要求 partition key
--   入唯一約束（V064:163 / V054:240 範式）。l2_reply_id 由 uuid12 構造全域唯一。
--   consequential_at_creation：IMMUTABLE，INSERT-set-once（從 registry 預設），
--   永不 UPDATE；retention class（§Q6 post-P1）。事後發現走 marks side-table。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent.l2_calls (
    l2_reply_id        TEXT        NOT NULL,   -- "l2r:<uuid12>" 全域 lineage handle
    session_id         TEXT,                   -- Layer2Session.session_id（群組多呼叫 session）
    capability_id      TEXT        NOT NULL,
    trigger            TEXT        NOT NULL,    -- "event|schedule|manual|threshold" + spec
    created_at         TIMESTAMPTZ NOT NULL,   -- hypertable partition key
    model              TEXT        NOT NULL,
    model_version      TEXT,
    contract_ver       TEXT        NOT NULL,   -- PromptContract 版本（§E.1）
    schema_ver         TEXT        NOT NULL,   -- output-schema 版本（§E.1）
    system_prompt      TEXT        NOT NULL,   -- FULL 已送出的確定性 prompt（已消毒，§B）
    input_context      JSONB       NOT NULL,   -- FULL 結構化輸入 + offered tool defs（已消毒）
    raw_response       TEXT        NOT NULL,   -- FULL 原始模型輸出，pre-parse（已消毒）
    parsed_output      JSONB,                  -- schema 驗證後輸出（guard reject 時 NULL）
    guard_verdict      TEXT,                   -- out-of-bound guard 結果：pass|clamp|reject
    fact_inf_assm      JSONB,                  -- {facts:[],inferences:[],assumptions:[]}
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cost_usd           NUMERIC,
    latency_ms         INTEGER,
    prompt_sha256      TEXT,                   -- sha256 over SANITIZED stored system_prompt
    response_sha256    TEXT,                   -- sha256 over SANITIZED stored raw_response
    redactor_version   TEXT,                   -- 跑了哪個 sanitize-redactor 版本（§B）
    error_code         TEXT,                   -- 失敗時分類 error code（§B；絕不存 str(e)）
    consequential_at_creation BOOLEAN NOT NULL DEFAULT false,  -- IMMUTABLE：INSERT-set-once
    PRIMARY KEY (l2_reply_id, created_at),
    -- 內容完整性：bare sha256 hex（V132 風格；非 V064 sha256:-prefixed）。nullable-tolerant。
    CONSTRAINT chk_l2_calls_prompt_sha256 CHECK (
        prompt_sha256 IS NULL OR prompt_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_l2_calls_response_sha256 CHECK (
        response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'
    ),
    -- guard_verdict 詞彙與 gate-seam（V135）verdict enum 對齊。
    CONSTRAINT chk_l2_calls_guard_verdict CHECK (
        guard_verdict IS NULL OR guard_verdict IN ('pass', 'clamp', 'reject')
    )
);

-- hypertable on created_at（7-day chunks；timestamptz → interval 形，V064:180-184）。
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('agent.l2_calls', 'created_at',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
    RAISE NOTICE 'V134: agent.l2_calls hypertable (created_at, 7-day chunks) ready';
ELSE
    RAISE NOTICE 'V134: timescaledb absent; agent.l2_calls stays plain table';
END IF;
END $$;

-- Forensic 熱路徑索引（§D.4 fault-localization queries）。
CREATE INDEX IF NOT EXISTS idx_l2_calls_session
    ON agent.l2_calls (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_l2_calls_capability
    ON agent.l2_calls (capability_id, created_at DESC);
-- 註：PK (l2_reply_id, created_at) 已服務主 WHERE l2_reply_id = ? 查找（§D.4 step 2）。
-- 註：retention partial index（§Q6 post-P1）刻意不在 V134 建——避免假裝 retention
--     policy 已存在；retention migration 落地時才連同 drop 邏輯一起建。

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B（ledger）：型別敏感欄位反射，型別漂移即 RAISE（V101:143-167 範式）。
--   JSONB 欄被誤建成 text 會讓 writer 壞掉；numeric/timestamptz/boolean 同理。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_bad TEXT[];
BEGIN
    SELECT array_agg(column_name || ':' || data_type) INTO v_bad
    FROM information_schema.columns
    WHERE table_schema = 'agent' AND table_name = 'l2_calls'
      AND (
        (column_name = 'system_prompt' AND data_type <> 'text')
        OR (column_name = 'raw_response' AND data_type <> 'text')
        OR (column_name = 'input_context' AND data_type <> 'jsonb')
        OR (column_name = 'parsed_output' AND data_type <> 'jsonb')
        OR (column_name = 'fact_inf_assm' AND data_type <> 'jsonb')
        OR (column_name = 'cost_usd' AND data_type <> 'numeric')
        OR (column_name = 'created_at' AND data_type <> 'timestamp with time zone')
        OR (column_name = 'consequential_at_creation' AND data_type <> 'boolean')
      );

    IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
        RAISE EXCEPTION 'V134 Guard B FAIL: agent.l2_calls type drift: %.', v_bad;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C（ledger）：lineage + forensic 索引存在性。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'agent' AND tablename = 'l2_calls'
          AND indexname = 'idx_l2_calls_session'
    ) THEN
        RAISE EXCEPTION 'V134 Guard C FAIL: idx_l2_calls_session missing.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'agent' AND tablename = 'l2_calls'
          AND indexname = 'idx_l2_calls_capability'
    ) THEN
        RAISE EXCEPTION 'V134 Guard C FAIL: idx_l2_calls_capability missing.';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Append-only（ledger）：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT。
--   零 column-level UPDATE grant（operator-LOCKED Option (c)）。
--   DO 包住 trading_ai 分支，dev sandbox 無此 role 時 NOTICE 不報錯。
--   範式 = V099:298-307。
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE UPDATE, DELETE ON agent.l2_calls FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON agent.l2_calls FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT ON agent.l2_calls TO trading_ai';
        RAISE NOTICE 'V134: agent.l2_calls — trading_ai = INSERT/SELECT only; UPDATE/DELETE revoked';
    ELSE
        RAISE NOTICE 'V134: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;

COMMENT ON TABLE agent.l2_calls IS
    'L2 Advisory Mesh D3 forensic ledger. One row per L2 model call: FULL sanitized system_prompt/input_context/raw_response + contract/schema ver + tokens/cost/latency + sha256 over sanitized text. Pure append-only (REVOKE UPDATE/DELETE, zero column-level UPDATE grant). Audit/provenance only, not trading authority.';
COMMENT ON COLUMN agent.l2_calls.consequential_at_creation IS
    'IMMUTABLE. Set once at INSERT from the capability registry default; NEVER UPDATEd (no UPDATE grant exists). Later-discovered consequence is an append-only row in agent.l2_consequential_marks, not a flip here.';
COMMENT ON COLUMN agent.l2_calls.prompt_sha256 IS
    'sha256 (bare hex) over the SANITIZED stored system_prompt, not the original. Hash-after-sanitize is the load-bearing ordering invariant (PA design point E2-2).';

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A（marks side-table）：表已存在時反射必要欄位，缺欄即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'agent' AND table_name = 'l2_consequential_marks'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'mark_id',
            'l2_reply_id',
            'marked_at',
            'reason',
            'lane',
            'marked_by',
            'details'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'agent' AND table_name = 'l2_consequential_marks'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V134 Guard A FAIL: agent.l2_consequential_marks exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Main DDL：agent.l2_consequential_marks（append-only event side-table）
--   「成為 consequential」是事後發現屬性：同一 l2_reply_id 可被多次/多原因/
--   多 lane/多 actor 標記，每筆帶 when/why/which-lane/by-whom，比單一 boolean
--   flip 更豐富且保持 ledger 純淨。event-sourced 範式 = V054 lease_transitions。
--   訂正錯誤標記 = 新增補償 mark row（reason='retracted:<mark_id>'），永不 UPDATE。
--   PK = (mark_id, marked_at)：hypertable 要求 partition key 入唯一約束。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent.l2_consequential_marks (
    mark_id      BIGSERIAL,
    l2_reply_id  TEXT        NOT NULL,            -- joins agent.l2_calls.l2_reply_id（logical FK）
    marked_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason       TEXT        NOT NULL,            -- 為何成為 consequential（free text / code）
    lane         TEXT,                            -- 進入哪個 retention-worthy lane（NULL=未指定）
    marked_by    TEXT,                            -- 哪個 applier/role/actor 記錄此 mark
    details      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (mark_id, marked_at)
);

-- hypertable on marked_at（7-day chunks）。
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('agent.l2_consequential_marks', 'marked_at',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
    RAISE NOTICE 'V134: agent.l2_consequential_marks hypertable (marked_at, 7-day chunks) ready';
ELSE
    RAISE NOTICE 'V134: timescaledb absent; agent.l2_consequential_marks stays plain table';
END IF;
END $$;

-- retention anti-join + 「show me why this reply is consequential」forensic query。
CREATE INDEX IF NOT EXISTS idx_l2_marks_reply
    ON agent.l2_consequential_marks (l2_reply_id, marked_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C（marks）：forensic 索引存在性。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'agent' AND tablename = 'l2_consequential_marks'
          AND indexname = 'idx_l2_marks_reply'
    ) THEN
        RAISE EXCEPTION 'V134 Guard C FAIL: idx_l2_marks_reply missing.';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Append-only（marks）：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT
--   + USAGE on BIGSERIAL sequence。零 column-level UPDATE grant。
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE UPDATE, DELETE ON agent.l2_consequential_marks FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON agent.l2_consequential_marks FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT ON agent.l2_consequential_marks TO trading_ai';
        EXECUTE 'GRANT USAGE ON SEQUENCE agent.l2_consequential_marks_mark_id_seq TO trading_ai';
        RAISE NOTICE 'V134: agent.l2_consequential_marks — trading_ai = INSERT/SELECT only; UPDATE/DELETE revoked';
    ELSE
        RAISE NOTICE 'V134: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;

COMMENT ON TABLE agent.l2_consequential_marks IS
    'Append-only side-table recording later-discovered "became consequential" events for an agent.l2_calls reply (when/why/which-lane/by-whom). Multi-mark per l2_reply_id. Corrections are new compensating rows, never UPDATEs. event-sourced pattern (cf. learning.lease_transitions V054:225).';

COMMIT;
