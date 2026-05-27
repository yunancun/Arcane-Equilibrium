-- ============================================================
-- V101: Track v3 Attribution Column EXTEND — trading.fills only
--
-- 2026-05-26 deprecation note: funding_arb enum/case branches are now
-- historical-only post AMD-2026-05-26-01 (funding_arb V2 retired closed per
-- ADR-0018 status upgrade). Retain enum / case for backfill query support;
-- Track C baseline cohort 收斂為 4 textbook（funding_arb 移除）；trading.fills
-- 歷史 funding_arb row 自然 30d V075 retention drop（不手動 DELETE）。
--
-- 用途:
--   為 ADR-0025 v3 Track-Based Strategy Attribution 在 trading.fills 加
--   single column `track` (strategy_track ENUM 3 值)，標記每筆 fill 屬於
--   哪一條 Track:
--     - direct_exploit : Track A 手寫 Rust 策略，cash flow 優先
--     - asds_factory   : Track B schema-only LLM hypothesis (N+1 ~ N+3)
--     - baseline       : Track C frozen textbook 4 策略（funding_arb retired per
--                        AMD-2026-05-26-01；原 5 → 4），A/B 對照基準
--
--   既有 5 textbook 策略 (grid_trading / bb_breakout / bb_reversion /
--   ma_crossover / funding_arb) 全 row backfill → 'baseline'。Sprint 5+
--   Wave 2 Track A/B writer 上線後，Rust writer 由 V102 trigger 強制
--   顯式填 'direct_exploit' / 'asds_factory'。
--
-- 範圍:
--   - CREATE TYPE strategy_track AS ENUM (3 值) (per V057 ENUM 範式)
--   - ADD COLUMN IF NOT EXISTS track strategy_track NULL on trading.fills
--     (per V094 columnstore-safe nullable ADD COLUMN 範式)
--   - batched UPDATE backfill (LIMIT 10000 + pg_sleep(0.1) + LOOP) 全 row
--     → 'baseline'
--   - Guard A: trading.fills exist + V003/V015/V077/V083/V094 baseline 15
--     column 完整
--   - Guard B: track column 已存在情境下 type/udt/nullable 對齊驗
--     (idempotency safety)
--   - Guard C: strategy_track ENUM 3 值 + column 物理存在 + nullable=YES
--     + 0 NULL row (100% backfill verified)
--
-- Parent specs:
--   docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md
--   docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md
--     §3.1-§3.4 (Track v3 attribution SSOT)
--   docs/CCAgentWorkSpace/PA/workspace/reports/
--     2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_design.md
--   docs/adr/0010-database-migration-guards.md (Guard A/B/C)
--   docs/adr/0011-database-migration-linux-pg-empirical-dry-run.md
--   docs/adr/0025-v3-track-based-strategy-attribution.md
--   docs/adr/0026-v3-direct-exploit-bypass-cpcv.md
--
-- 硬邊界:
--   - trading.fills 是 TimescaleDB columnstore hypertable (per V077 lesson
--     2026-05-09 49ceeb61);本 V101 走 ADD COLUMN nullable + DEFAULT 不設
--     (V102 才設 DEFAULT 'baseline')，避免 columnstore feature_not_supported
--   - 不走 ALTER COLUMN SET NOT NULL (columnstore 不支援);NOT NULL 強制由
--     V102 BEFORE INSERT/UPDATE trigger 處理 (per V077 trigger fallback 範式)
--   - scope 嚴格收緊 trading.fills only (不對 trading.intents/signals/orders/
--     decision_outcomes/risk_verdicts/position_snapshots 同時 ADD COLUMN);
--     其他 11 表 + 2 新表 + 4 view + governance.track_kill_events 屬
--     Sprint 5+ Wave 2 Phase 2 carry-over
--   - 不重新 CREATE learning.hypotheses (V100 已 land 2026-05-23 production)
--   - V101 結尾 0 NULL row 必達成 (RAISE EXCEPTION on FAIL 根原則 6 fail-closed)
--   - production deploy lock window 警告: sqlx migrate transaction 包整體
--     V101;LOOP backfill 預估 wall-clock 17s-3min trading.fills writer block;
--     production deploy 必走 low-IO window (避免與 demo/paper writer race
--     觸發 V101 結尾 RAISE EXCEPTION rollback);詳見 Main DDL Step 2 注釋
-- ============================================================

-- ============================================================
-- Main DDL Step 0: CREATE TYPE strategy_track ENUM (per V057 範式)
-- 主 DDL Step 0: 建立 Track 分類 ENUM 型別
--
-- 為什麼用 ENUM 不用 TEXT + CHECK：
--   - ENUM 比 TEXT+CHECK 節省 storage (4 byte vs variable);
--   - 後續 view / index / query 比較 enum 較快;
--   - 違反值 enum 由 PG type system 強制 fail-closed (DBA 層級不變式)。
--
-- 注意：CREATE TYPE 在 sqlx migrate transaction 內必走 EXCEPTION duplicate_object
-- 否則 second apply 會 RAISE non-idempotent 錯誤。
-- ============================================================
DO $$ BEGIN
    CREATE TYPE strategy_track AS ENUM (
        'direct_exploit',
        'asds_factory',
        'baseline'
    );
    RAISE NOTICE 'V101: strategy_track ENUM created (3 values: direct_exploit / asds_factory / baseline)';
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'V101: strategy_track ENUM already exists; skipping CREATE TYPE';
END $$;

-- ============================================================
-- Guard A: trading.fills 必存在且 baseline 15 column 完整
-- Guard A: trading.fills must exist with V003/V015/V077/V083/V094 baseline columns
--
-- baseline 15 column = V003 base (ts/fill_id/order_id/symbol/side/qty/
-- price/fee/strategy_name/context_id/details) + V015 (engine_mode) +
-- V077 不加 column (CHECK constraint + trigger fallback only) +
-- V083 (entry_context_id) + V033 (exit_reason) +
-- V094 (close_maker_attempt + close_maker_fallback_reason 2 columns;
-- 注:Guard A unnest 只列 close_maker_attempt 作 representative,
-- close_maker_fallback_reason 與其同源同步 land 不另列)
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'trading' AND table_name = 'fills'
    ) THEN
        RAISE EXCEPTION
            'V101 Guard A FAIL: trading.fills missing — '
            'V003 trading_agent_tables.sql 必先 apply。Re-check migration order.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts', 'fill_id', 'order_id', 'symbol', 'side', 'qty', 'price',
        'fee', 'strategy_name', 'context_id', 'engine_mode',
        'entry_context_id', 'exit_reason', 'close_maker_attempt',
        'details'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading' AND table_name = 'fills'
          AND column_name = c
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V101 Guard A FAIL: trading.fills missing baseline columns: %. '
            'Resolve V003/V015/V077/V083/V094 schema drift before V101.', v_missing;
    END IF;
    RAISE NOTICE 'V101 Guard A PASS: trading.fills + 15 baseline column verified';
END $$;

-- ============================================================
-- Guard B: track column 已存在情境下 type/udt/nullable 對齊驗 (idempotency)
-- Guard B: if track column already exists, verify type/udt/nullable match
--
-- 首次 apply 時 SELECT 返 NULL → if block skip → PASS。
-- 重跑時若 type drift (例如手工 ALTER 改成 TEXT) → RAISE EXCEPTION。
-- ============================================================
DO $$
DECLARE
    v_data_type TEXT;
    v_udt_name TEXT;
    v_is_nullable TEXT;
BEGIN
    SELECT data_type, udt_name, is_nullable
      INTO v_data_type, v_udt_name, v_is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'track';

    IF v_data_type IS NOT NULL THEN
        IF v_data_type IS DISTINCT FROM 'USER-DEFINED'
           OR v_udt_name IS DISTINCT FROM 'strategy_track'
           OR v_is_nullable IS DISTINCT FROM 'YES' THEN
            RAISE EXCEPTION
                'V101 Guard B FAIL: trading.fills.track type drift. '
                'Expected strategy_track ENUM NULL, got type=%, udt=%, nullable=%. '
                'Resolve schema state before V101 re-apply.',
                v_data_type, v_udt_name, v_is_nullable;
        END IF;
        RAISE NOTICE 'V101 Guard B PASS: track column already exists with expected type (idempotent re-apply)';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: ADD COLUMN track strategy_track NULL on trading.fills
-- 主 DDL Step 1: 加 track 欄位 (nullable;V102 由 trigger 強制 NOT NULL)
--
-- 走 nullable ADD COLUMN：
--   - columnstore hypertable 安全 (per V094 close_maker_audit 同表
--     `ADD COLUMN ... BOOLEAN NOT NULL DEFAULT FALSE` 已驗 PASS 範式);
--   - V102 才走 ALTER COLUMN SET DEFAULT 'baseline' + trigger 強制 NOT NULL;
--   - 本步驟不嘗試 ALTER COLUMN ... SET NOT NULL (columnstore
--     feature_not_supported per V077 lesson)。
-- ============================================================
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

COMMENT ON COLUMN trading.fills.track IS
    'Strategy track attribution dimension per ADR-0025 v3。'
    '3 值 enum: direct_exploit (Track A hand-coded Rust);'
    'asds_factory (Track B schema-only LLM hypothesis);'
    'baseline (Track C frozen textbook 5 strategy A/B reference)。'
    '既有 5 textbook 策略 全 backfill baseline;'
    'Sprint 5+ Track A/B 上線後新 fill 由 writer 顯式填 direct_exploit/asds_factory。'
    'V101 此 column nullable (legacy columnstore-safe);'
    'V102 NOT NULL handling 走 BEFORE INSERT trigger 強制 fail-closed (per columnstore feature_not_supported)。';

-- ============================================================
-- Main DDL Step 1.5 [NEW per PA-DRIFT-8 lesson 2026-05-23]:
-- Strategy B sentinel populate — legacy pre-V083 close fill entry_context_id NULL fix
--
-- PA-DRIFT-8 RCA (per MIT audit 2026-05-23):
--   PG/TimescaleDB UPDATE row 觸發 row-level constraint re-validation EVEN
--   if updated column 與 constraint 無關 (PG documented behavior;NOT VALID
--   chunk constraint 不阻 historical scan 但不阻 UPDATE 觸發 re-validation)。
--   53 pre-V083 close fills 違反 V083 chk_fills_close_has_entry_context_id_v083
--   (exit_reason IS NOT NULL AND entry_context_id IS NULL);均在
--   2026-04-30 ~ 2026-05-09 V083 install 之前 ipc_close_symbol /
--   fast_track_reduce_half / phys_lock_gate4_giveback / orphan_frozen
--   緊急路徑漏 set_entry_context_id (W-AUDIT-4b M2 接通之前 era)。
--
-- 修法 (Strategy B sentinel populate per MIT verdict):
--   sentinel format = 'legacy_pre_v083_unknown_' || fill_id
--   - 顯式標明 legacy unknown (per 根原則 10 分離 fact/inference;不假裝真實 entry)
--   - 保留 fill_id suffix audit trace (per 根原則 8 可重建可解釋)
--   - ML training 自然 filter `entry_context_id NOT LIKE 'legacy_%'` 防污染
--   - 滿足 V083 constraint (entry_context_id IS NOT NULL)
--   - 後續 Step 2 LOOP backfill UPDATE track 不觸發 V083 re-validation
--
-- 未來 V### spec SOP (per MIT recommendation):
--   對 fills 等含 forward-only NOT VALID CHECK constraint 的表做 backfill
--   UPDATE 前必先跑 violator detection SQL + sentinel populate (ADR-0010
--   Guard D pre-UPDATE forward-only constraint violator scan;待 Sprint 5+
--   Wave 2 governance amend)。
-- ============================================================
DO $$
DECLARE
    v_sentinel_count INT;
BEGIN
    UPDATE trading.fills
       SET entry_context_id = 'legacy_pre_v083_unknown_' || fill_id
     WHERE exit_reason IS NOT NULL
       AND entry_context_id IS NULL;
    GET DIAGNOSTICS v_sentinel_count = ROW_COUNT;
    RAISE NOTICE 'V101 Step 1.5: sentinel-populated % legacy close fill(s) '
                 '(pre-V083 entry_context_id NULL);per PA-DRIFT-8 MIT audit '
                 '2026-05-23 verdict Strategy B', v_sentinel_count;
END $$;

-- ============================================================
-- Main DDL Step 2: Backfill batched UPDATE → 'baseline'
-- 主 DDL Step 2: 分批回填 track='baseline'
--
-- batch sizing rationale:
--   - LIMIT 10000 + pg_sleep(0.1) = ~6k row/sec sustained
--   - 估 trading.fills row volume ~100k-1M (live 8 個月 demo+paper 累計);
--     wall clock ~17s-3min
--   - FOR UPDATE SKIP LOCKED 避免與 writer 寫入新 row 互鎖
--
-- 為什麼必走 single-shot atomic backfill (sqlx migrate transaction 包整體):
--   - V094 land 2026-05-15 不含 backfill (No data rewrite, no backfill, no
--     runtime enablement per V094 header line 14-15);本 LOOP+pg_sleep 範式
--     非直接 mirror V094，而是 V101 自行 ENUM nullable column EXTEND 場景
--     需要 100% backfill 才能在 V102 上 NOT NULL trigger
--   - sqlx migrate 將整段 V101 包入 BEGIN/COMMIT;LOOP 內 SELECT 全程
--     transaction-isolated;writer 新寫入 row 在 COMMIT 前不可見;
--     COMMIT 後 V102 trigger 立即接管 (writer 新 row 顯式填 trigger 強制)
--   - production deploy 必須 low-IO window 執行;預估 wall-clock ~17s-3min
--     trading.fills writer block (per fill_id, ts composite PK row lock)
-- ============================================================
DO $$
DECLARE
    v_updated INT;
    v_total INT := 0;
BEGIN
    LOOP
        UPDATE trading.fills
           SET track = 'baseline'
         WHERE (fill_id, ts) IN (
             SELECT fill_id, ts
               FROM trading.fills
              WHERE track IS NULL
              LIMIT 10000
              FOR UPDATE SKIP LOCKED
         );
        GET DIAGNOSTICS v_updated = ROW_COUNT;
        v_total := v_total + v_updated;
        EXIT WHEN v_updated = 0;
        PERFORM pg_sleep(0.1);  -- 100ms breath; avoid lock contention
    END LOOP;
    RAISE NOTICE 'V101 backfill: % rows updated to track=baseline', v_total;
END $$;

-- ============================================================
-- Main DDL Step 3: V101 結尾 verify 0 NULL row (per fail-closed 根原則 6)
-- 主 DDL Step 3: 收尾驗證 backfill 100%
--
-- race scenario 釐清:
--   - sqlx migrate 將整段 V101 包入 BEGIN/COMMIT;本 SELECT 全程在
--     transaction-isolated snapshot 內;V101 COMMIT 前外部 writer
--     新 INSERT 的 row 在本 SELECT 不可見;
--   - V101 COMMIT 後 V102 trigger 立即上線 (V### sequence intact);
--     若 V102 land 前有 writer race 寫 NULL row 進去，下一輪 V102 Guard A
--     reflection 會 catch (RAISE EXCEPTION on v_null_count > 0);
--   - V102 trigger 上線後 writer 漏填即 trigger violation (NOT NULL
--     fail-closed 永久接管)。
-- ============================================================
DO $$
DECLARE
    v_null_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_null_count
      FROM trading.fills
     WHERE track IS NULL;

    IF v_null_count > 0 THEN
        RAISE EXCEPTION
            'V101 backfill incomplete: % rows still have track=NULL. '
            'sqlx migrate transaction isolation 內 SELECT 看不到外部 writer 新 row;'
            'V101 COMMIT 後 V102 trigger 立即 catch NULL writer。'
            'Re-run backfill DO block or investigate transaction isolation anomaly.',
            v_null_count;
    END IF;
    RAISE NOTICE 'V101: trading.fills.track 100%% backfilled (0 NULL row)';
END $$;

-- ============================================================
-- Guard C: 後驗 strategy_track ENUM + track column + 0 NULL backfill
-- Guard C: post-DDL verify ENUM + column + 100% backfill
-- ============================================================
DO $$
DECLARE
    v_enum_count INT;
    v_null_count BIGINT;
BEGIN
    -- strategy_track ENUM 必 3 值齊全
    SELECT COUNT(*) INTO v_enum_count
    FROM pg_enum
    WHERE enumtypid = 'strategy_track'::regtype;

    IF v_enum_count <> 3 THEN
        RAISE EXCEPTION
            'V101 Guard C FAIL: strategy_track ENUM 應有 3 值, 實際 %. '
            'Expected 3 values: direct_exploit, asds_factory, baseline.', v_enum_count;
    END IF;

    -- track column 必物理存在 + strategy_track ENUM + nullable
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading' AND table_name = 'fills'
          AND column_name = 'track'
          AND udt_name = 'strategy_track'
          AND is_nullable = 'YES'
    ) THEN
        RAISE EXCEPTION
            'V101 Guard C FAIL: trading.fills.track column missing or type drift.';
    END IF;

    -- backfill 100% (0 NULL)
    SELECT COUNT(*) INTO v_null_count
    FROM trading.fills WHERE track IS NULL;

    IF v_null_count > 0 THEN
        RAISE EXCEPTION
            'V101 Guard C FAIL: % rows still have track=NULL after backfill. '
            'Backfill DO block 失敗或 writer race。', v_null_count;
    END IF;
    RAISE NOTICE 'V101 Guard C PASS: 3 enum + track column + 0 NULL row verified';
END $$;
