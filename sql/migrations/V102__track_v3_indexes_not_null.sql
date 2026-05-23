-- ============================================================
-- V102: Track v3 Indexes + NOT NULL Handling — trading.fills hot-path + fail-closed
--
-- 用途:
--   V101 配對 migration — V101 land 後 trading.fills.track column 存在 +
--   100% backfilled 'baseline';本 V102 工作:
--     1. 加 2 hot-path index 支撐 ADR-0025 v3 4 P&L view query pattern
--     2. ALTER COLUMN ... SET DEFAULT 'baseline' (writer 漏填降級安全網)
--     3. BEFORE INSERT/UPDATE OF track trigger 強制 NOT NULL fail-closed
--        (per V077 columnstore hypertable trigger fallback 範式)
--
--   DEFAULT 'baseline' + trigger NOT NULL 雙保險：
--     - writer 顯式 INSERT track=NULL → trigger RAISE EXCEPTION
--     - writer INSERT 漏 track column 不寫 → DEFAULT 'baseline' 自動填
--       (degrade-to-baseline 行為，非 trigger violation)
--     - 新策略 writer 必須改填 'direct_exploit'/'asds_factory'，
--       否則 baseline 攔截 (writer self-discipline catch by COMMENT semantic)
--
-- 範圍:
--   - CREATE INDEX IF NOT EXISTS idx_fills_track_ts_v102 ON
--     trading.fills (track, ts DESC)
--   - CREATE INDEX IF NOT EXISTS idx_fills_strategy_track_v102 ON
--     trading.fills (strategy_name, track)
--   - ALTER TABLE trading.fills ALTER COLUMN track SET DEFAULT 'baseline'
--     (metadata-only operation;預期 columnstore-safe)
--   - CREATE OR REPLACE FUNCTION trading.enforce_fills_track_not_null()
--   - CREATE TRIGGER trg_fills_track_not_null_v102 BEFORE INSERT OR
--     UPDATE OF track ON trading.fills (FOR EACH ROW;
--     對齊 V077 trg_fills_engine_mode_known_values 範式)
--   - Guard A: V101 prerequisite (column + ENUM + 100% backfill)
--   - Guard B: DEFAULT + trigger 已存在情境下定義對齊驗 (idempotency)
--   - Guard C: 後驗 2 index + DEFAULT + trigger 全 land
--
-- Parent specs:
--   docs/execution_plan/specs/2026-05-23--v102-track-v3-indexes-not-null.md
--   docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md (prereq)
--   docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md §4.1-§4.2
--   docs/CCAgentWorkSpace/PA/workspace/reports/
--     2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_design.md
--   docs/adr/0010-database-migration-guards.md (Guard A/B/C)
--   docs/adr/0011-database-migration-linux-pg-empirical-dry-run.md
--   docs/adr/0025-v3-track-based-strategy-attribution.md
--
-- 硬邊界:
--   - trading.fills 是 TimescaleDB columnstore hypertable (per V077 lesson);
--     本 V102 不走 ALTER COLUMN SET NOT NULL (columnstore feature_not_supported);
--     NOT NULL 強制走 BEFORE INSERT/UPDATE OF track trigger 範式
--   - index 全 CREATE INDEX IF NOT EXISTS 非 CONCURRENTLY (sqlx migrate
--     transaction-wrapped；對齊 V094/V083 既有 fills index land 範式)
--   - V101 必先 apply (Guard A 強制驗 column + ENUM + 0 NULL)
--   - trigger fail-closed 對齊 V077 範式：function 名
--     trading.enforce_fills_track_not_null + trigger 名
--     trg_fills_track_not_null_v102 (V### suffix 命名 anti-collision)
-- ============================================================

-- ============================================================
-- Guard A: V101 prerequisite check (column + ENUM + 0 NULL backfill)
-- Guard A: V101 必先 apply (track column + ENUM + 100% backfill)
-- ============================================================
DO $$
DECLARE
    v_null_count BIGINT;
BEGIN
    -- trading.fills.track column 必存在且 strategy_track ENUM type (V101 land 後)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading' AND table_name = 'fills'
          AND column_name = 'track'
          AND udt_name = 'strategy_track'
    ) THEN
        RAISE EXCEPTION
            'V102 Guard A FAIL: trading.fills.track missing — V101 必先 apply。'
            'Re-check migration order.';
    END IF;

    -- strategy_track ENUM 必存在 (V101 CREATE TYPE 落地後)
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'strategy_track'
    ) THEN
        RAISE EXCEPTION
            'V102 Guard A FAIL: strategy_track ENUM missing — V101 必先 apply。';
    END IF;

    -- V101 backfill 100% verify (0 NULL row)
    SELECT COUNT(*) INTO v_null_count
      FROM trading.fills WHERE track IS NULL;

    IF v_null_count > 0 THEN
        RAISE EXCEPTION
            'V102 Guard A FAIL: trading.fills.track still has % NULL row(s)。'
            'V101 backfill 必先 100%% 完成。',
            v_null_count;
    END IF;

    RAISE NOTICE 'V102 Guard A PASS: V101 prerequisite verified (column + ENUM + 0 NULL)';
END $$;

-- ============================================================
-- Guard B: DEFAULT + trigger 已存在情境下定義對齊驗 (idempotency safety)
-- Guard B: if DEFAULT/trigger already present, verify shape matches expectation
--
-- 首次 apply 時 SELECT 返 NULL → if block skip → PASS。
-- 重跑時若 drift (手工 ALTER 改成其他值) → RAISE EXCEPTION。
-- ============================================================
DO $$
DECLARE
    v_column_default TEXT;
    v_trigger_def TEXT;
BEGIN
    -- DEFAULT 'baseline' 已存在情境驗 (idempotency)
    SELECT column_default INTO v_column_default
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'track';

    IF v_column_default IS NOT NULL THEN
        IF v_column_default NOT ILIKE '%baseline%' THEN
            RAISE EXCEPTION
                'V102 Guard B FAIL: trading.fills.track DEFAULT drift。'
                'Expected ''baseline''::strategy_track, got %。', v_column_default;
        END IF;
    END IF;

    -- trigger 已存在情境驗 (idempotency)
    SELECT pg_get_triggerdef(t.oid)
      INTO v_trigger_def
    FROM pg_trigger t
    WHERE t.tgrelid = 'trading.fills'::regclass
      AND t.tgname = 'trg_fills_track_not_null_v102'
      AND NOT t.tgisinternal;

    IF v_trigger_def IS NOT NULL THEN
        IF v_trigger_def NOT ILIKE '%BEFORE INSERT OR UPDATE OF track%'
           OR v_trigger_def NOT ILIKE '%enforce_fills_track_not_null%' THEN
            RAISE EXCEPTION
                'V102 Guard B FAIL: trg_fills_track_not_null_v102 definition drift。'
                'Expected BEFORE INSERT OR UPDATE OF track + enforce_fills_track_not_null function, got %。',
                v_trigger_def;
        END IF;
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: ALTER COLUMN track SET DEFAULT 'baseline'
-- 主 DDL Step 1: 設 DEFAULT 'baseline' (writer 漏填降級安全網)
--
-- 為什麼設 DEFAULT 而不只靠 trigger:
--   - 雙保險語意:
--     · trigger RAISE 抓「writer 顯式 INSERT track=NULL」(catch early)
--     · DEFAULT 'baseline' 抓「writer INSERT 完全漏 track column」(降級行為)
--   - 對齊 V003 既有 column 範式 (fee REAL DEFAULT 0 / fee_currency TEXT
--     DEFAULT 'USDT' / is_paper BOOLEAN DEFAULT FALSE)
--   - DEFAULT 是 metadata-only operation;不重寫既有 row;
--     預期 columnstore-safe (per PA spec §3.2 Option B)
-- ============================================================
ALTER TABLE trading.fills
    ALTER COLUMN track SET DEFAULT 'baseline'::strategy_track;

-- ============================================================
-- Main DDL Step 2: trigger function + trigger (per V077 範式)
-- 主 DDL Step 2: NOT NULL 強制 trigger (columnstore-safe fail-closed)
--
-- 為什麼用 trigger 不用 ALTER COLUMN SET NOT NULL:
--   - V077 hotfix lesson 2026-05-09 49ceeb61 確認 trading.fills (columnstore
--     hypertable) ALTER COLUMN SET NOT NULL 與 ADD/VALIDATE CHECK 均
--     RAISE feature_not_supported
--   - 對齊 V077 BEFORE INSERT/UPDATE 範式 (trg_fills_engine_mode_known_values)
--   - trigger fail-closed: RAISE EXCEPTION on NULL → migration / runtime
--     writer 漏填 catch early
--   - DROP TRIGGER 可逆 (per spec rollback path)
-- ============================================================
CREATE OR REPLACE FUNCTION trading.enforce_fills_track_not_null()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.track IS NULL THEN
        RAISE EXCEPTION
            'V102 trigger violation: trading.fills.track must not be NULL '
            '(per ADR-0025 v3 Track-based attribution unfair if track unset). '
            'Writer must explicitly set track to direct_exploit/asds_factory/baseline.'
            USING ERRCODE = '23502';  -- not_null_violation SQLSTATE
    END IF;
    RETURN NEW;
END
$fn$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'trading.fills'::regclass
          AND tgname = 'trg_fills_track_not_null_v102'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_fills_track_not_null_v102
            BEFORE INSERT OR UPDATE OF track ON trading.fills
            FOR EACH ROW
            EXECUTE FUNCTION trading.enforce_fills_track_not_null();
        RAISE NOTICE
            'V102: trg_fills_track_not_null_v102 installed '
            '(NOT NULL enforced via trigger; columnstore-safe)';
    ELSE
        RAISE NOTICE 'V102: trg_fills_track_not_null_v102 already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 3: 2 hot-path indexes (per ADR-0025 v3 4 P&L view query pattern)
-- 主 DDL Step 3: 2 hot-path index 對映 4 P&L view 查詢模式
--
-- Index 1 (track, ts DESC):
--   per-track time-series P&L attribution 主索引
--   query: WHERE track = 'direct_exploit' AND ts > now() - INTERVAL '7d'
--          ORDER BY ts DESC
--
-- Index 2 (strategy_name, track):
--   cross-track audit query (Track A/B/C 對映 strategy 一致性 verify)
--   query: WHERE strategy_name='grid_trading' GROUP BY track
--
-- 為什麼非 CONCURRENTLY:
--   - sqlx migrate 將 V102 包入 BEGIN/COMMIT；CREATE INDEX CONCURRENTLY
--     在 transaction 內 RAISE
--   - 對齊 V094 + V083 + V028 既有 trading.fills index 範式 (全 IF NOT EXISTS)
--   - 2 index 數量少；非 huge table index build cost;
--     預期 wall clock ~30s-2min per index on production data volume
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_fills_track_ts_v102
    ON trading.fills (track, ts DESC);

CREATE INDEX IF NOT EXISTS idx_fills_strategy_track_v102
    ON trading.fills (strategy_name, track);

COMMENT ON INDEX trading.idx_fills_track_ts_v102 IS
    'V102 hot-path index for per-track time-series P&L attribution '
    '(per ADR-0025 v3 4 P&L view query pattern: '
    'WHERE track = X ORDER BY ts DESC).';

COMMENT ON INDEX trading.idx_fills_strategy_track_v102 IS
    'V102 hot-path index for cross-track audit '
    '(Track A/B/C 對映 strategy 一致性 verify per ADR-0025 v3 X-AC5).';

-- ============================================================
-- Guard C: 後驗 2 index + DEFAULT + trigger 全 land
-- Guard C: post-DDL verify 2 index + DEFAULT + trigger all in place
-- ============================================================
DO $$
DECLARE
    v_idx1 TEXT;
    v_idx2 TEXT;
    v_column_default TEXT;
    v_trigger_count INT;
BEGIN
    -- Index 1 land + def 對齊
    SELECT pg_get_indexdef(c.oid) INTO v_idx1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'trading'
      AND c.relname = 'idx_fills_track_ts_v102';

    IF v_idx1 IS NULL THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_track_ts_v102 missing after DDL。';
    END IF;
    IF position('track' IN v_idx1) = 0 OR position('ts' IN v_idx1) = 0 THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_track_ts_v102 definition drift。Actual: %。', v_idx1;
    END IF;

    -- Index 2 land + def 對齊
    SELECT pg_get_indexdef(c.oid) INTO v_idx2
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'trading'
      AND c.relname = 'idx_fills_strategy_track_v102';

    IF v_idx2 IS NULL THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_strategy_track_v102 missing after DDL。';
    END IF;
    IF position('strategy_name' IN v_idx2) = 0 OR position('track' IN v_idx2) = 0 THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_strategy_track_v102 definition drift。Actual: %。', v_idx2;
    END IF;

    -- DEFAULT 'baseline' 已生效
    SELECT column_default INTO v_column_default
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'track';

    IF v_column_default IS NULL OR v_column_default NOT ILIKE '%baseline%' THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: trading.fills.track DEFAULT not set to baseline。Actual: %。',
            v_column_default;
    END IF;

    -- trigger 物理存在
    SELECT COUNT(*) INTO v_trigger_count
    FROM pg_trigger
    WHERE tgrelid = 'trading.fills'::regclass
      AND tgname = 'trg_fills_track_not_null_v102'
      AND NOT tgisinternal;

    IF v_trigger_count <> 1 THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: trg_fills_track_not_null_v102 trigger count = %, expected 1。',
            v_trigger_count;
    END IF;

    RAISE NOTICE 'V102 Guard C PASS: 2 index + DEFAULT + trigger all verified';
END $$;
