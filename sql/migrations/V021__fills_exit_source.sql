-- ============================================================
-- V021: INFRA-PREBUILD-1 Part A — trading.fills.exit_source
-- DUAL-TRACK-EXIT-1 Phase 2 Combine Layer shadow path 前置
-- Combine Layer shadow path prerequisite for Phase 2
-- Created 2026-04-23 per plan INFRA-PREBUILD-1 §A1
-- ============================================================
--
-- Purpose / 用途：
--   為每筆退場 fill 記錄其決策來源（Physical/Hybrid/ML/Disabled），
--   讓 Phase 2 shadow mode 可觀測 ML 是否與 Physical 一致，
--   且 production 階段亦可用來 GROUP BY audit（Physical 佔比、
--   Hybrid 確認率等）。
--
--   Record exit source for each fill so Phase 2 shadow mode can
--   audit ML vs Physical agreement; production can also GROUP BY
--   for Physical share / Hybrid confirm ratio etc.
--
-- Semantics / 語義：
--   Physical  — Track P 純物理層決策（Phase 1a 100% 走此）
--   Hybrid    — 物理 Lock + ML 高信心確認
--   ML        — 純 ML 決策（Phase 1a unreachable，ml_override_high=2.0）
--   Disabled  — ML 失效降級（NaN/Inf/stale）
--
-- Rust ExitSource enum stable dictionary @ combine_layer.rs:57-84
--
-- Write path (Rust) / 寫入路徑：
--   tick_pipeline/on_tick/helpers.rs → emit_close_fill
--   → TradingMsg::Fill { ..., exit_source }
--   → trading_writer.rs::batch_insert_chunked INSERT
--   INSERT 第 16 個欄位（承 V017 的 15 欄）
--
-- Backwards compatibility / 向後相容：
--   - ADD COLUMN IF NOT EXISTS 對現有 rows → NULL
--   - 應用層 SELECT 時 COALESCE(exit_source, 'Physical') 視為
--     歷史 rows 均為 Physical（唯一存在的路徑）
--   - 新 INSERT 無 exit_source 傳入時 column 會是 NULL（非強制
--     NOT NULL，因 LiveDemo/Mainnet sync-fill 可能無 decision 來源）
--
-- Rollback / 回滾：
--   ALTER TABLE trading.fills DROP COLUMN IF EXISTS exit_source;
--   DROP INDEX IF EXISTS trading.idx_fills_exit_source_non_physical;
--
-- TimescaleDB note / TimescaleDB 備註：
--   ADD COLUMN 對 hypertable 是 metadata-only 改動（不 rewrite chunks），
--   大表友善。CHECK constraint 同理（validate 失敗時才 rewrite，
--   這裡用 CHECK IN 對歷史 NULL 不觸發）。

-- ------------------------------------------------------------
-- Schema Guard B (retrofit 2026-04-24, V023 postmortem)
-- ------------------------------------------------------------
-- If trading.fills.exit_source already exists with a non-TEXT type,
-- the ADD COLUMN IF NOT EXISTS below would silently skip and
-- downstream writers would later fail in confusing ways. RAISE now.
--
-- 若 trading.fills.exit_source 已存在但非 TEXT，下方 ADD COLUMN
-- IF NOT EXISTS 會靜默跳過、下游 writer 之後才報難解錯誤。提前 RAISE。
--
-- Template source: sql/migrations/templates/schema_guard_template.sql § Guard B
-- ------------------------------------------------------------
DO $$
DECLARE
    v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading'
      AND table_name   = 'fills'
      AND column_name  = 'exit_source';

    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.exit_source exists as type %, expected text. '
            'Legacy drift detected — resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply.',
            v_actual;
    END IF;
END $$;

-- ------------------------------------------------------------
-- 1. Add column (nullable) / 加欄位（可 NULL）
-- ------------------------------------------------------------
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS exit_source TEXT;

-- ------------------------------------------------------------
-- 2. CHECK constraint / 值域約束
--    允許 NULL（歷史 rows + 非退場 fill 如開倉）
--    Allow NULL for historical rows and non-exit fills (e.g. opens)
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fills_exit_source_enum'
    ) THEN
        ALTER TABLE trading.fills
            ADD CONSTRAINT fills_exit_source_enum
            CHECK (exit_source IS NULL
                OR exit_source IN ('Physical', 'Hybrid', 'ML', 'Disabled'));
    END IF;
END $$;

-- ------------------------------------------------------------
-- 3. Partial index for non-Physical audit
--    Phase 2 shadow 時 Hybrid/ML/Disabled 是關注對象
--    預期佔比 < 20%，partial index 節省空間
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fills_exit_source_non_physical
    ON trading.fills (ts DESC, exit_source)
    WHERE exit_source IS NOT NULL AND exit_source != 'Physical';

COMMENT ON COLUMN trading.fills.exit_source IS
    'INFRA-PREBUILD-1 (2026-04-23): ExitSource tag from combine_layer. '
    'Values: Physical|Hybrid|ML|Disabled. NULL = historical row or non-exit fill. '
    'Phase 1a 100% Physical; Phase 2 shadow mode writes Hybrid/ML (unreachable '
    'pre-Track-L via ml_override_high=2.0 sentinel).';

COMMENT ON INDEX trading.idx_fills_exit_source_non_physical IS
    'INFRA-PREBUILD-1 (2026-04-23): Partial index on non-Physical exits for '
    'Phase 2 shadow audit. Expected < 20% rows match; saves disk vs full index.';

-- ============================================================
-- 4. learning.decision_shadow_exits — Combine Layer shadow audit
-- ============================================================
--
-- 用途 / Purpose:
--   Phase 2 shadow mode 觀察 Combine Layer 決策（ExitSource）vs
--   單獨 Track P 決策之差異。每筆 exit fill 可選寫一列觀察，
--   記錄 Track P 原本會怎麼決、ML inference 提供什麼 score、
--   Combine 最終選了哪個 ExitSource、分歧原因等。
--
--   Not to be confused with `decision_shadow_fills` (entry-time
--   ε-greedy exploration, paper-only, V017). This table is
--   exit-time Combine Layer shadow — engine_mode allows demo too.
--
-- Semantics / 語義區分：
--   decision_shadow_fills (V017)  — entry 時 ε-greedy 合成 fill
--   decision_shadow_exits (V021)  — exit 時 Combine Layer 一致性觀察
--
-- Writer: rust/openclaw_engine/src/database/shadow_exit_writer.rs
--   (Phase 2 才啟用；shadow_enabled=true 時每個 close fire 一次)
--
-- Label isolation / label 隔離:
--   純觀測，永不入 `learning.decision_features` label 回填。
--   Pure observation; never enters training label backfill.
-- ============================================================

-- ------------------------------------------------------------
-- Schema Guard A (retrofit 2026-04-24, V023 postmortem)
-- ------------------------------------------------------------
-- If learning.decision_shadow_exits already exists from a prior
-- attempt, verify all required columns are present before the
-- CREATE TABLE IF NOT EXISTS silently no-ops.
--
-- 若 learning.decision_shadow_exits 已存在（前次嘗試殘留），
-- 驗所有必要欄位都在；避免 CREATE TABLE IF NOT EXISTS 靜默跳過。
--
-- Template source: sql/migrations/templates/schema_guard_template.sql § Guard A
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name   = 'decision_shadow_exits'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'context_id', 'ts', 'engine_mode',
            'strategy_name', 'symbol', 'side',
            'physical_action', 'exit_source',
            'disagreed'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'decision_shadow_exits'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: learning.decision_shadow_exits exists but missing required columns: %. '
                'Resolve legacy schema (DROP + re-apply V021) before continuing.',
                v_missing;
        END IF;
    END IF;
END $$;

-- Guard B: ts column must be timestamptz (hypertable partition column).
-- Guard B：ts 欄位必須是 timestamptz（hypertable 分區欄）。
DO $$
DECLARE
    v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name   = 'decision_shadow_exits'
      AND column_name  = 'ts';

    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION
            'schema_guard B: learning.decision_shadow_exits.ts is %, expected timestamp with time zone. '
            'TimescaleDB hypertable partition column type must match; resolve manually.',
            v_actual;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.decision_shadow_exits (
    shadow_exit_id        BIGSERIAL,
    context_id            TEXT            NOT NULL,   -- FK → decision_features.context_id
    ts                    TIMESTAMPTZ     NOT NULL,   -- close fill 時間
    engine_mode           TEXT            NOT NULL
        CHECK (engine_mode IN ('paper', 'demo', 'live', 'live_demo')),
    strategy_name         TEXT            NOT NULL,
    symbol                TEXT            NOT NULL,
    side                  SMALLINT        NOT NULL,

    -- Track P 物理層決策 / Physical decision
    physical_action       TEXT            NOT NULL
        CHECK (physical_action IN ('Lock', 'Hold')),
    physical_reason       TEXT,                       -- e.g. 'phys_lock_gate4_giveback'

    -- ML inference (shadow_enabled=false 時全 NULL)
    ml_model_id           TEXT,                       -- NULL = no ML / ML disabled
    ml_score              DOUBLE PRECISION,
    ml_age_secs           BIGINT,
    ml_confidence         DOUBLE PRECISION,

    -- Combine Layer 最終決定 / Combine Layer final decision
    exit_source           TEXT            NOT NULL
        CHECK (exit_source IN ('Physical', 'Hybrid', 'ML', 'Disabled')),
    disagreed             BOOLEAN         NOT NULL DEFAULT FALSE,
    disagreement_reason   TEXT,

    -- Combine config snapshot（降級時 debug 用）
    ml_confirm_threshold  DOUBLE PRECISION,
    ml_override_high      DOUBLE PRECISION,
    ml_veto_low           DOUBLE PRECISION,

    -- Composite PK required by TimescaleDB create_hypertable: any unique index
    -- must include the partition column (ts). shadow_exit_id BIGSERIAL still
    -- guarantees global uniqueness on its own; (shadow_exit_id, ts) satisfies
    -- the hypertable constraint without weakening identity.
    -- TimescaleDB 要求：hypertable 上任何 unique index 必須含 partition 欄；
    -- BIGSERIAL 本身全局唯一，複合 PK 加上 ts 兩者一致不衝突。
    PRIMARY KEY (shadow_exit_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('learning.decision_shadow_exits', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_shadow_exits_strategy_ts
    ON learning.decision_shadow_exits (strategy_name, engine_mode, ts DESC);

CREATE INDEX IF NOT EXISTS idx_shadow_exits_disagreed
    ON learning.decision_shadow_exits (engine_mode, ts DESC)
    WHERE disagreed = TRUE;

CREATE INDEX IF NOT EXISTS idx_shadow_exits_context_id
    ON learning.decision_shadow_exits (context_id);

COMMENT ON TABLE learning.decision_shadow_exits IS
    'INFRA-PREBUILD-1 (2026-04-23): Combine Layer exit-time shadow observations. '
    'Phase 2 shadow mode fires one row per close fill when shadow_enabled=true. '
    'Pure observation — never enters label backfill. Distinguish from '
    'decision_shadow_fills (V017, entry-time ε-greedy, paper-only).';

COMMENT ON COLUMN learning.decision_shadow_exits.ml_model_id IS
    'NULL = Combine Layer got None MLInference (Phase 1a default). '
    'Non-NULL = Phase 2 shadow mode active with mock or real ONNX inference.';

COMMENT ON COLUMN learning.decision_shadow_exits.disagreed IS
    'TRUE when Combine output != what Physical-only would have produced. '
    'Key audit metric for Phase 2 shadow agreement ratio target ≥60%.';
