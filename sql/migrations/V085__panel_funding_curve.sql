-- ============================================================
-- V085: panel.funding_rates_panel — W-AUDIT-8a Phase B Tier 2.1 funding curve panel
-- Status: NOT_RUN — D+1 deploy after sign-off
-- Spec:   docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md
-- Reservation: V085 per memory project_2026_05_10_sprint_n1_d0_readiness.md
--
-- 動機 / Motivation:
--   Sprint N+1 W1 W-AUDIT-8a Phase B Tier 2 panel collector：把
--   AlphaSurface.funding_curve 從 Phase A stub typedef 升級為真實 wire panel。
--   Producer = Rust panel_aggregator/funding_curve.rs（v1.1 WS-first 設計，
--   訂閱既有 tickers.{sym} broadcast，60s flush 一批寫 PG + slot 雙寫）。
--
--   PG 端責任：audit trail + ML training data + healthcheck [57] freshness 來源。
--   slot 端責任：hot path read（dispatch step_4_5 直接 RwLock::read clone）。
--
-- 範圍 / Scope (V085):
--   1. CREATE SCHEMA IF NOT EXISTS panel  (panel schema 首次引入；後續
--      V087 oi_delta_panel + 未來 W2 V088 BtcLeadLagPanel 等共用)
--   2. CREATE TABLE IF NOT EXISTS panel.funding_rates_panel (5 column,
--      PRIMARY KEY (snapshot_ts_ms, symbol))
--   3. TimescaleDB hypertable conversion (1d chunk on snapshot_ts_ms BIGINT;
--      非 timestamptz 故 chunk_time_interval 用 86400000 ms 整數)
--   4a. integer_now_func helper panel.unix_now_ms() + set_integer_now_func
--       (BIGINT time column hypertable retention policy 硬要求)
--   4b. 14d retention policy BIGINT 1209600000 ms (per spec §2.2)
--   5. Hot-path index idx_funding_panel_ts_desc_symbol (snapshot_ts_ms DESC, symbol)
--   6. COMMENT ON COLUMN 雙語語義文檔
--   7. Guard A/B/C 強制 + idempotency
--
-- 不變式 / Invariants:
--   - 每個 (snapshot_ts_ms, symbol) tuple 唯一 (PK 強制)；25 row per snapshot 對齊
--     trait FundingCurveSnapshot.{symbols,funding_rates_bps,next_funding_ms} Vec
--     index 對齊
--   - source_tier 默認 'bybit_v5_public'；aggregator INSERT 時顯式給
--     'bybit_v5_ws_tickers' 覆蓋（per spec §2.3 line 211）
--   - retention 14d hard cap：panel data 為 ML training + audit 用，不需長期保存；
--     14d 滿足 W-AUDIT-8a Phase B/C/D 評估窗口（per spec §2.2 retention rationale）
--   - hypertable 用 snapshot_ts_ms BIGINT 為 time column（NOT timestamptz）；
--     create_hypertable chunk_time_interval 必須整數 86400000 (= 1d in ms)
--   - schema 對齊 trait FundingCurveSnapshot（critical, per spec §2.2 line 136-140）：
--       funding_rate_bps DOUBLE PRECISION  → Vec<f64>
--       next_funding_ms  BIGINT            → Vec<i64>
--       snapshot_ts_ms   BIGINT            → i64
--       source_tier      TEXT              → String
--
-- Idempotency:
--   全 migration 重跑兩次必須 PASS：
--     - CREATE SCHEMA IF NOT EXISTS                       → 第二次 no-op
--     - CREATE TABLE IF NOT EXISTS                        → 第二次 no-op (Guard A 已先驗 shape)
--     - create_hypertable(... if_not_exists => TRUE)      → 第二次 no-op
--     - CREATE OR REPLACE FUNCTION panel.unix_now_ms()    → 第二次 silent overwrite (定義不變)
--     - set_integer_now_func(replace_if_exists => TRUE)   → 第二次 silent replace (idempotent)
--     - add_retention_policy(... if_not_exists => TRUE)   → 第二次 no-op
--     - CREATE INDEX IF NOT EXISTS                        → 第二次 no-op (Guard C 已先驗 shape)
--
-- E2 review checklist:
--   1. Guard A 對 panel.funding_rates_panel 必要欄位完整性檢查
--      （重跑時若表已存在但 shape drift → RAISE，不 silent skip）
--   2. Guard B 驗 funding_rate_bps / next_funding_ms / snapshot_ts_ms 三 type
--      （aggregator 寫入靠 type 對齊 trait struct）
--   3. Guard C 驗 idx_funding_panel_ts_desc_symbol 含 'snapshot_ts_ms DESC'
--      （hot-path query 依賴）
--   4. timescaledb extension 守 (與 V027 pattern 對齊；無 extension 則 hypertable
--      conversion skip 但 PG 表照常運作；W-AUDIT-8d 需 evidence 監控)
--   5. PRIMARY KEY 順序 (snapshot_ts_ms, symbol)：snapshot_ts_ms 在前是 hypertable
--      time column 的對齊要求
--
-- D+1 IMPL 補丁餘地：
--   本 file 為 sign-off 前 SQL skeleton 預寫；D+1 W1 IMPL 階段預期可能微調：
--     - timescaledb extension 守的 PERFORM 包裝 (對齊 V027 line 54-60 pattern)
--     - retention policy 是否需 set_chunk_time_interval 額外 hint
--     - 若 cohort 25 sym 從 hardcoded 改為 dynamic SymbolRegistry subset
--       (W-AUDIT-8c phase) 是否需 schema constraint 增 cohort version column
-- ============================================================

BEGIN;

-- ============================================================
-- §1 CREATE SCHEMA panel (idempotent)
-- panel schema 首次引入；後續 V087 oi_delta_panel + 未來 W2 V088
-- BtcLeadLagPanel 等 cross-asset / cross-section panel 共用此 schema
-- ============================================================
CREATE SCHEMA IF NOT EXISTS panel;

-- ============================================================
-- Guard A: panel.funding_rates_panel 表如已存在必要欄位俱在
-- 對齊 schema_guard_template.sql Guard A pattern
-- 若表不存在 → no-op (下方 CREATE TABLE 自然建立)
-- 若表存在但缺 ≥1 必要欄位 → RAISE EXCEPTION (silent drift 防線)
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'panel'
          AND table_name   = 'funding_rates_panel'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'snapshot_ts_ms', 'symbol', 'funding_rate_bps',
            'next_funding_ms', 'source_tier'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'panel'
              AND table_name   = 'funding_rates_panel'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V085 Guard A FAIL: panel.funding_rates_panel exists but '
                'missing required columns: %. Resolve legacy schema drift '
                '(DROP TABLE + re-apply, or ALTER ADD missing columns) '
                'then re-run V085.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ============================================================
-- §2 CREATE TABLE panel.funding_rates_panel (idempotent)
-- 對齊 trait FundingCurveSnapshot (alpha_surface.rs:127-140)：
--   symbols: Vec<String>          → symbol TEXT
--   funding_rates_bps: Vec<f64>   → funding_rate_bps DOUBLE PRECISION
--   next_funding_ms: Vec<i64>     → next_funding_ms BIGINT
--   snapshot_ts_ms: i64           → snapshot_ts_ms BIGINT
--   source_tier: String           → source_tier TEXT (default 'bybit_v5_public')
-- 25 row per snapshot_ts_ms (cohort 25 sym, 每 sym 一 row)
-- ============================================================
CREATE TABLE IF NOT EXISTS panel.funding_rates_panel (
    snapshot_ts_ms     BIGINT           NOT NULL,
    symbol             TEXT             NOT NULL,
    funding_rate_bps   DOUBLE PRECISION NOT NULL,
    next_funding_ms    BIGINT           NOT NULL,
    source_tier        TEXT             NOT NULL DEFAULT 'bybit_v5_public',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

-- ============================================================
-- Guard B: 三型別敏感欄位驗 data_type
-- aggregator 寫入靠 type 對齊 trait struct field；type drift = silent
-- write fail (sqlx) 或 NaN 寫入污染 ML training data
-- 若 column 不存在 v_actual = NULL → silent skip (CREATE TABLE 已負責建)
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- funding_rate_bps must be 'double precision'
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel'
      AND table_name   = 'funding_rates_panel'
      AND column_name  = 'funding_rate_bps';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V085 Guard B FAIL: panel.funding_rates_panel.funding_rate_bps '
            'is %, expected double precision. Type drift detected.',
            v_actual;
    END IF;

    -- next_funding_ms must be 'bigint'
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel'
      AND table_name   = 'funding_rates_panel'
      AND column_name  = 'next_funding_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'V085 Guard B FAIL: panel.funding_rates_panel.next_funding_ms '
            'is %, expected bigint. Type drift detected.',
            v_actual;
    END IF;

    -- snapshot_ts_ms must be 'bigint' (hypertable time column 對齊)
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel'
      AND table_name   = 'funding_rates_panel'
      AND column_name  = 'snapshot_ts_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'V085 Guard B FAIL: panel.funding_rates_panel.snapshot_ts_ms '
            'is %, expected bigint (hypertable time column 必須整數型). '
            'Type drift detected.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- §3 TimescaleDB hypertable conversion (idempotent)
-- snapshot_ts_ms 是 BIGINT (NOT timestamptz)，create_hypertable 對 integer
-- time column 必須給 integer chunk_time_interval：
--   86400000 ms = 1 day
-- 對齊 V027 funding_settlements pattern：先檢 timescaledb extension 存在
-- 否則 hypertable conversion skip（PG 表仍可運作，只是無 chunk auto-rotate /
-- compression / retention 自動化）
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'panel.funding_rates_panel',
            'snapshot_ts_ms',
            chunk_time_interval => 86400000,
            if_not_exists       => TRUE
        );
    ELSE
        RAISE NOTICE 'V085: timescaledb extension absent; '
                     'panel.funding_rates_panel created as plain table '
                     '(no hypertable / retention auto-rotate)';
    END IF;
END $$;

-- ============================================================
-- §4a integer_now_func for BIGINT time column hypertable (idempotent)
-- TimescaleDB 硬條件：BIGINT time column hypertable 加 retention policy
-- 前必先註冊 integer_now_func；否則 add_retention_policy / compression
-- background job 在 fire 時 RAISE（per TimescaleDB issue #6197 +
-- set_integer_now_func 文檔）。
-- 函數簽名：返回 BIGINT，單位對齊 time column (此處 ms epoch)。
-- CREATE OR REPLACE FUNCTION 是 idempotent (定義不變則重跑無副作用)。
-- 使用 IF NOT EXISTS 風格不可行 (PG CREATE FUNCTION 無 IF NOT EXISTS)；
-- OR REPLACE 是標準 idempotent pattern。
-- ============================================================
CREATE OR REPLACE FUNCTION panel.unix_now_ms()
    RETURNS BIGINT
    LANGUAGE SQL
    STABLE
AS $$
    SELECT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
$$;

COMMENT ON FUNCTION panel.unix_now_ms() IS
    'V085 helper: returns now() as BIGINT ms epoch for TimescaleDB '
    'set_integer_now_func on BIGINT time column hypertables in panel schema. '
    'Required before add_retention_policy / compression policy on '
    'panel.funding_rates_panel (snapshot_ts_ms BIGINT).';

-- 註冊 integer_now_func 到 panel.funding_rates_panel hypertable
-- (僅當 timescaledb extension 存在 + 表已成功 hypertable conversion)
-- 用 _timescaledb_catalog.hypertable 直查 (TimescaleDB 2.x 內部 catalog
-- 含 schema_name + table_name 直接 column)；避免 §3 hypertable conversion
-- skip 場景 set_integer_now_func raise
-- ⚠️ idempotency 關鍵：set_integer_now_func 第三 arg replace_if_exists 默認
-- false 會 RAISE 重跑；必須顯式給 true 才能 idempotent (per TimescaleDB
-- function signature 文檔: set_integer_now_func(hypertable REGCLASS,
-- integer_now_func REGPROC, replace_if_exists BOOL = false))
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')
       AND EXISTS (
           SELECT 1 FROM _timescaledb_catalog.hypertable
           WHERE schema_name = 'panel'
             AND table_name  = 'funding_rates_panel'
       )
    THEN
        PERFORM set_integer_now_func(
            'panel.funding_rates_panel'::regclass,
            'panel.unix_now_ms'::regproc,
            replace_if_exists => TRUE
        );
    END IF;
END $$;

-- ============================================================
-- §4b Retention policy 14 days (idempotent)
-- panel data = ML training + audit 用，不需長期保存；14d 滿足 W-AUDIT-8a
-- Phase B/C/D 評估窗口 (per spec §2.2)。
-- 對 BIGINT time column hypertable 必須給 BIGINT drop_after (ms 對齊單位)；
-- 14 days = 14 * 86400 * 1000 = 1209600000 ms
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM add_retention_policy(
            'panel.funding_rates_panel',
            BIGINT '1209600000',  -- 14 days in ms
            if_not_exists => TRUE
        );
    END IF;
END $$;

-- ============================================================
-- Guard C: hot-path index idx_funding_panel_ts_desc_symbol 欄位組合驗證
-- 對齊 schema_guard_template.sql Guard C pattern
-- 索引存在但欄位組合錯 → RAISE
-- 索引不存在 → no-op (下方 CREATE INDEX 自然建立)
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'panel'
      AND c.relname = 'idx_funding_panel_ts_desc_symbol';

    IF v_actual IS NOT NULL AND position('snapshot_ts_ms DESC' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V085 Guard C FAIL: idx_funding_panel_ts_desc_symbol exists but '
            'column list mismatch. Expected to contain snapshot_ts_ms DESC, '
            'actual: %. DROP INDEX + re-apply migration to repair.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- §5 Hot-path index (idempotent)
-- Hot-path query: 最新 N 秒 snapshot lookup
--   SELECT ... FROM panel.funding_rates_panel
--   WHERE snapshot_ts_ms >= $cutoff_ms
--   ORDER BY snapshot_ts_ms DESC, symbol
-- aggregator flush 後 dispatch step_4_5 雖直接讀 slot（不查 PG），但 healthcheck
-- [57] freshness query + ML trainer 批拉 panel snapshot 都需此 index
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_funding_panel_ts_desc_symbol
    ON panel.funding_rates_panel (snapshot_ts_ms DESC, symbol);

-- ============================================================
-- §6 COMMENT 雙語語義文檔 (idempotent: COMMENT ON 可重跑)
-- ============================================================
COMMENT ON SCHEMA panel IS
    'W-AUDIT-8a Phase B Tier 2 cross-asset / cross-section panel schema. '
    '專供 panel collector aggregator 寫入；retention 14d；ML training '
    '+ audit + healthcheck freshness source.';

COMMENT ON TABLE panel.funding_rates_panel IS
    'W-AUDIT-8a Phase B B-1 funding curve panel. 25 row per snapshot_ts_ms '
    '對齊 cohort 25 sym (active strategy union)；source = Bybit V5 '
    'tickers WS broadcast aggregator (60s flush)；retention 14d；對齊 '
    'trait FundingCurveSnapshot (openclaw_core/src/alpha_surface.rs:127-140).';

COMMENT ON COLUMN panel.funding_rates_panel.snapshot_ts_ms IS
    'Aggregator flush 時戳 (ms epoch)。hypertable time column；同一 snapshot '
    '所有 25 sym row 共享同值。';

COMMENT ON COLUMN panel.funding_rates_panel.symbol IS
    'Cohort symbol (e.g. BTCUSDT)。對齊 SymbolRegistry strict subset；W1 IMPL '
    'hardcoded 25 sym snapshot；W-AUDIT-8c 後改 dynamic discovery。';

COMMENT ON COLUMN panel.funding_rates_panel.funding_rate_bps IS
    '當前 funding rate，單位 basis points (bps)。WS tickers fundingRate × 10000。'
    '對齊 trait FundingCurveSnapshot.funding_rates_bps Vec<f64>。';

COMMENT ON COLUMN panel.funding_rates_panel.next_funding_ms IS
    '下次 funding 結算時間戳 (ms epoch)。WS tickers nextFundingTime。'
    '對齊 trait FundingCurveSnapshot.next_funding_ms Vec<i64>。';

COMMENT ON COLUMN panel.funding_rates_panel.source_tier IS
    'Source tier 標記（aggregator 寫 ''bybit_v5_ws_tickers'' 覆蓋 default '
    '''bybit_v5_public''）；對齊 V050 simulated_fills.evidence_source_tier '
    '命名語義；對齊 trait FundingCurveSnapshot.source_tier String。';

COMMIT;

-- ============================================================
-- §7 Final NOTICE (transaction-end NOTICE for operator runbook)
-- 注意：COMMIT 之後的 RAISE NOTICE 需在獨立 DO block (PG 限制)
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE 'V085 land complete:';
    RAISE NOTICE '  - panel schema created (first introduction)';
    RAISE NOTICE '  - panel.funding_rates_panel table 5 column';
    RAISE NOTICE '    PRIMARY KEY (snapshot_ts_ms, symbol)';
    RAISE NOTICE '  - TimescaleDB hypertable (1d chunk on snapshot_ts_ms BIGINT)';
    RAISE NOTICE '  - panel.unix_now_ms() integer_now_func registered';
    RAISE NOTICE '  - 14d retention policy (BIGINT 1209600000 ms)';
    RAISE NOTICE '  - idx_funding_panel_ts_desc_symbol (snapshot_ts_ms DESC, symbol)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps (D+1 W1 IMPL):';
    RAISE NOTICE '  - Linux PG dry-run V085 (跑兩次驗 idempotent + 無 RAISE)';
    RAISE NOTICE '  - E1-α IMPL Rust panel_aggregator/funding_curve.rs WS subscriber';
    RAISE NOTICE '  - E2 verify Guard A/B/C 完整性 + Linux PG dry-run report';
    RAISE NOTICE '  - E4 regression: 確認既有 5 策略未被 panel schema 引入破壞';
    RAISE NOTICE '  - PM commit + deploy after sign-off';
END $$;
