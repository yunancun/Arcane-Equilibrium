-- ============================================================
-- V115: panel.basis_panel — P2-BASIS-PANEL-INFRA perp-index basis point-in-time panel
--   WS-fed perp-vs-index basis (期現價差) snapshot panel；A1 funding_short_v2
--   Stage 0R 前置（offline replay 用歷史 basis 序列，不靠 in-memory cache）。
--
-- 動機 / Motivation:
--   A1 funding_short_v2 candidate entry gate `basis_pct < 0.3%`（spec line 45）。
--   A1/A2 Stage 0R runner spec v2 標記 `basis_panel_infra_missing` → A1 BLOCKED
--   draft_only。本表提供 point-in-time basis 持久化層，解鎖 A1 Stage 0R replay。
--
--   basis = (perp_last_price / index_price - 1) * 100（signed，單位 %）。
--   producer = Rust panel_aggregator/basis.rs（mirror funding_curve.rs；訂閱既有
--   WS tickers.{sym} broadcast 取 last_price + index_price，60s flush 一批寫 PG）。
--   index_price 只在 snapshot frame 帶（~1/8 frame）→ aggregator latest-value cache
--   跨 frame 保留 last-known index（對齊 funding_curve sparse cache 範式）。
--
--   PG 端責任：A1 Stage 0R as-of LATERAL lookup 來源（offline replay）+ ML training
--   data + healthcheck freshness 來源。
--   ⚠️ 本 panel **無 IPC slot**（per spec §6.4 #5）：A1 strategy live path 已用
--   in-memory index_prices cache 即時算 basis；basis_panel 純為 offline replay 服務。
--
-- 範圍 / Scope (V115):
--   1. CREATE SCHEMA IF NOT EXISTS panel
--      （sister V085 funding_rates_panel / V087 oi_delta_panel / V088 btc_lead_lag
--        已建同 schema；先 land 者勝，雙重 IF NOT EXISTS 保護）
--   2. CREATE TABLE IF NOT EXISTS panel.basis_panel (6 column,
--      PRIMARY KEY (snapshot_ts_ms, symbol))
--   3. TimescaleDB hypertable conversion (1d chunk on snapshot_ts_ms BIGINT;
--      非 timestamptz 故 chunk_time_interval 用 86400000 ms 整數)
--   4a. integer_now_func panel.unix_now_ms() + set_integer_now_func
--       (BIGINT time column hypertable retention policy 硬要求；V085 已建，
--        本 file 自含完整 dependency 以支援單獨 dry-run / 部分先跑)
--   4b. 14d retention policy BIGINT 1209600000 ms
--       （對齊 sister panel V085/V087/V088 統一 14d；basis 是衍生短期數據，
--         前向累積，不需長期保存）
--   5. Hot-path index idx_basis_panel_ts_desc_symbol (snapshot_ts_ms DESC, symbol)
--      （Stage 0R as-of LATERAL 用 ts DESC + symbol）
--      + sister secondary index basis_panel_snapshot_ts_ms_idx（per spec §3.1）
--   6. COMMENT 語義文檔
--   7. Guard A/B/C 強制 + idempotency
--
-- 設計決策（per spec §3.1）:
--   - **不存 mark_price**：basis 用 last vs index（spec §2.1）；mark 在 WS stream
--     不可得（parser 不解析）且非 basis 定義輸入 → 不引入死 column（避 market_tickers
--     index_price/mark_price 壞死同類陷阱 spec §1.4）。
--   - **NOT NULL on basis_pct + index_price + perp_last_price**：fail-closed 在
--     writer 端 = index≤0 不寫 row（非寫 NULL row）。比 oi_delta 寫 NULL 更嚴
--     （oi_delta 是 window 不足；basis 是 input 缺失 = 該 snapshot 無有效 basis，
--      不該入庫污染 replay as-of lookup；NULL row 會被 as-of LIMIT 1 撈到誤判）。
--   - **無 engine_mode column**：basis 是 market-data（market truth，非 per-engine
--     fills），三引擎共讀同一 basis snapshot；對齊 sister panel 0 engine_mode column。
--   - **無 compression policy**：對齊 sister V085/V087/V088（皆只掛 14d retention，
--     無 add_compression_policy）；surgical，per spec §3.1「相同則複製，無則不加」。
--
-- basis 公式 replay parity（E2 必查）:
--   panel 存 **signed** basis_pct = (last/index-1)*100；
--   strategy live (funding_short_v2/mod.rs:155-157) compute_basis_pct 回
--   ((perp_price/ip)-1.0).abs()*100.0（**已取 abs**）。
--   → panel 存 signed（保方向資訊）；consumer/Stage 0R runner 取 ABS(basis_pct)
--     比 gate（spec §2.2 + §5.1 runner `ABS(bp.basis_pct) < 0.3`）。
--   → 分子必 = last_price（**非 mark_price**）否則 Stage 0R 與 live 不可比。
--
-- 不變式 / Invariants:
--   - 每個 (snapshot_ts_ms, symbol) tuple 唯一 (PK 強制)；cohort N row per snapshot
--     （收過 ≥1 index snapshot 的 sym；index 缺失者該 snapshot 不寫 row）
--   - source_tier 預設 'bybit_v5_ws_tickers'（basis 全 WS 衍生，無 REST 路徑；
--     對齊 funding_curve aggregator INSERT 顯式值）
--   - hypertable 用 snapshot_ts_ms BIGINT 為 time column（NOT timestamptz）；
--     create_hypertable chunk_time_interval 必整數 86400000 (= 1d in ms)
--   - retention 14d hard cap：panel data = ML training + Stage 0R replay + audit；
--     14d 滿足評估窗口（對齊 sister；basis 只前向累積，spec §5.3）
--
-- index≤0 不寫 row 是 writer 層邏輯，**非 schema CHECK constraint**（per spec §2.2
--   + §3.1）：
--   - schema 用 NOT NULL on index_price 表達「row 必有有效 index」的契約底線
--     （NOT NULL 已阻止 index=NULL row 入庫）。
--   - 但「index>0」門檻是 writer 端 fail-closed 判斷（aggregator flush 跳過 index≤0
--     的 sym，根本不發 INSERT）；不加 CHECK (index_price > 0) constraint 的理由：
--       (a) 對齊 sister panel（V085/V087 皆無 value-range CHECK，靠 writer 邏輯）；
--       (b) index_price=0 在資料層不該出現（writer 已 skip），加 CHECK 是冗餘防線；
--       (c) 若 future debug 需診斷壞 row，CHECK 會讓 INSERT 直接 abort 整批 flush
--           （ON CONFLICT batch 內一條違反 → 全 batch fail），反不利；
--           writer skip + NOT NULL 已是足夠 fail-closed。
--   - MIT 裁決：schema **不需** index_price>0 CHECK；NOT NULL 是正確契約層級。
--     E1 writer 端必確保 index≤0 / 缺失 → skip（不發 INSERT、不寫 0、不寫 NULL）。
--
-- Idempotency:
--   全 migration 重跑兩次必須 PASS（per memory feedback_v_migration_pg_dry_run
--   double-apply mandatory；first-apply PASS ≠ re-apply 安全）：
--     - CREATE SCHEMA IF NOT EXISTS                       → 第二次 no-op
--     - CREATE TABLE IF NOT EXISTS                        → 第二次 no-op (Guard A 已驗 shape)
--     - create_hypertable(... if_not_exists => TRUE)      → 第二次 no-op
--     - CREATE OR REPLACE FUNCTION panel.unix_now_ms()    → 第二次 silent overwrite
--     - set_integer_now_func(replace_if_exists => TRUE)   → 第二次 silent replace
--     - add_retention_policy(... if_not_exists => TRUE)   → 第二次 no-op
--     - CREATE INDEX IF NOT EXISTS                        → 第二次 no-op (Guard C 已驗 shape)
--
-- E2 review checklist:
--   1. Guard A 對 panel.basis_panel 必要 6 欄完整性（重跑 shape drift → RAISE）
--   2. Guard B 驗 perp_last_price / index_price / basis_pct DOUBLE PRECISION
--      + snapshot_ts_ms BIGINT（writer 寫入靠 type 對齊）
--   3. Guard C 驗 idx_basis_panel_ts_desc_symbol 含 'snapshot_ts_ms DESC'
--   4. timescaledb extension guard（無 ext → plain table，hypertable/retention skip）
--   5. PRIMARY KEY (snapshot_ts_ms, symbol) 順序（snapshot_ts_ms 在前 = hypertable
--      partition column 對齊要求）
--   6. basis 公式 parity（grep funding_short_v2/mod.rs:155 對照）+ 分子 = last_price
--
-- Spec source:
--   docs/execution_plan/specs/2026-05-29--basis-panel-infra-spec.md §3.1 / §3.2
--   sister: V085 funding_rates_panel / V087 oi_delta_panel / V088 btc_lead_lag_panel
--   strategy parity: rust/openclaw_engine/src/strategies/funding_short_v2/mod.rs:155
--   migration latest: V114 → V115（FREE）
-- ============================================================

BEGIN;

-- ============================================================
-- §1 CREATE SCHEMA IF NOT EXISTS panel (idempotent)
-- panel namespace 是 Phase B Tier 2 panel collector family 共用 namespace
-- (V085 funding_rates_panel / V087 oi_delta_panel / V088 btc_lead_lag_panel)
-- 雙重 IF NOT EXISTS 保護：sister 也建同 schema，先 land 者勝
-- ============================================================
CREATE SCHEMA IF NOT EXISTS panel;

-- ============================================================
-- Guard A: panel.basis_panel 表如已存在必要 6 欄俱在
-- 對齊 schema_guard_template.sql + V085/V087 Guard A pattern
-- 若表不存在 → no-op（下方 CREATE TABLE 自然建立）
-- 若表存在但缺 ≥1 必要欄位 → RAISE EXCEPTION（silent drift 防線）
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'panel'
          AND table_name   = 'basis_panel'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'snapshot_ts_ms', 'symbol', 'perp_last_price',
            'index_price', 'basis_pct', 'source_tier'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'panel'
              AND table_name   = 'basis_panel'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V115 Guard A FAIL: panel.basis_panel exists but missing required '
                'columns: %. Resolve legacy schema drift (DROP TABLE + re-apply, '
                'or ALTER ADD missing columns) then re-run V115.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ============================================================
-- §2 CREATE TABLE IF NOT EXISTS panel.basis_panel (idempotent)
-- per spec §3.1
--   snapshot_ts_ms  BIGINT            → flush 時戳 (ms epoch)；hypertable time col
--   symbol          TEXT              → cohort sym（N row per snapshot）
--   perp_last_price DOUBLE PRECISION  → basis 分子（last_price，非 mark_price）
--   index_price     DOUBLE PRECISION  → basis 分母（>0 才寫 row；writer fail-closed）
--   basis_pct       DOUBLE PRECISION  → (last/index-1)*100 SIGNED（consumer 取 abs）
--   source_tier     TEXT              → 'bybit_v5_ws_tickers'（全 WS 衍生）
-- NOT NULL on perp_last_price / index_price / basis_pct：fail-closed 在 writer 端
--   = index≤0 不寫 row（非寫 NULL row）；NOT NULL 是「row 必有有效 basis」契約底線
-- 不存 mark_price（spec §3.1 設計決策：不引入死 column）
-- 無 engine_mode column（market 共享平面；對齊 sister panel）
-- ============================================================
CREATE TABLE IF NOT EXISTS panel.basis_panel (
    snapshot_ts_ms   BIGINT            NOT NULL,
    symbol           TEXT              NOT NULL,
    perp_last_price  DOUBLE PRECISION  NOT NULL,
    index_price      DOUBLE PRECISION  NOT NULL,
    basis_pct        DOUBLE PRECISION  NOT NULL,
    source_tier      TEXT              NOT NULL DEFAULT 'bybit_v5_ws_tickers',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

-- ============================================================
-- Guard B: type 敏感欄位驗 data_type
-- writer 寫入靠 type 對齊（sqlx）；type drift = silent write fail 或精度損失
-- 若 column 不存在 v_actual = NULL → silent skip（CREATE TABLE 已負責建）
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- perp_last_price must be 'double precision'
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel' AND table_name = 'basis_panel'
      AND column_name = 'perp_last_price';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V115 Guard B FAIL: panel.basis_panel.perp_last_price is %, '
            'expected double precision. Type drift detected.', v_actual;
    END IF;

    -- index_price must be 'double precision'
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel' AND table_name = 'basis_panel'
      AND column_name = 'index_price';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V115 Guard B FAIL: panel.basis_panel.index_price is %, '
            'expected double precision. Type drift detected.', v_actual;
    END IF;

    -- basis_pct must be 'double precision'
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel' AND table_name = 'basis_panel'
      AND column_name = 'basis_pct';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V115 Guard B FAIL: panel.basis_panel.basis_pct is %, '
            'expected double precision. Type drift detected.', v_actual;
    END IF;

    -- snapshot_ts_ms must be 'bigint' (hypertable time column 對齊)
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel' AND table_name = 'basis_panel'
      AND column_name = 'snapshot_ts_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'V115 Guard B FAIL: panel.basis_panel.snapshot_ts_ms is %, '
            'expected bigint (hypertable time column 必須整數型). '
            'Type drift detected.', v_actual;
    END IF;
END $$;

-- ============================================================
-- §3 TimescaleDB hypertable conversion (idempotent)
-- snapshot_ts_ms 是 BIGINT (NOT timestamptz)，create_hypertable 對 integer
-- time column 必須給 integer chunk_time_interval：86400000 ms = 1 day
-- 對齊 V085/V087 pattern：先檢 timescaledb extension 存在，否則 hypertable
-- conversion skip（PG 表仍可運作，只是無 chunk auto-rotate / retention 自動化）
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'panel.basis_panel',
            'snapshot_ts_ms',
            chunk_time_interval => 86400000,
            if_not_exists       => TRUE
        );
    ELSE
        RAISE NOTICE 'V115: timescaledb extension absent; '
                     'panel.basis_panel created as plain table '
                     '(no hypertable / retention auto-rotate)';
    END IF;
END $$;

-- ============================================================
-- §4a integer_now_func for BIGINT time column hypertable (idempotent)
-- TimescaleDB 硬條件：BIGINT time column hypertable 加 retention policy 前必先
-- 註冊 integer_now_func；否則 add_retention_policy background job fire 時 RAISE
-- (per TimescaleDB issue #6197 + set_integer_now_func 文檔)。
-- panel.unix_now_ms() V085 已建；CREATE OR REPLACE 是 idempotent（定義不變則
-- 重跑無副作用）；本 file 自含完整 dependency 以支援單獨 dry-run。
-- ============================================================
CREATE OR REPLACE FUNCTION panel.unix_now_ms()
    RETURNS BIGINT
    LANGUAGE SQL
    STABLE
AS $$
    SELECT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
$$;

-- 註冊 integer_now_func 到 panel.basis_panel hypertable
-- replace_if_exists => TRUE 是 idempotent 必需（默認 false 重跑會 RAISE）
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')
       AND EXISTS (
           SELECT 1 FROM _timescaledb_catalog.hypertable
           WHERE schema_name = 'panel'
             AND table_name  = 'basis_panel'
       )
    THEN
        PERFORM set_integer_now_func(
            'panel.basis_panel'::regclass,
            'panel.unix_now_ms'::regproc,
            replace_if_exists => TRUE
        );
    END IF;
END $$;

-- ============================================================
-- §4b Retention policy 14 days (idempotent)
-- 對齊 sister panel V085/V087/V088 統一 14d；basis 是衍生短期數據，前向累積，
-- 不需長期保存。對 BIGINT time column hypertable 必給 BIGINT drop_after
-- (ms 對齊單位)；14 days = 14 * 86400 * 1000 = 1209600000 ms。
-- ❌ 用 INTERVAL '14 days' 在 BIGINT time column 上會 RAISE
--    (per TimescaleDB issue #2877)；必用 BIGINT。
-- 無 compression policy：對齊 sister（皆只掛 retention，無 add_compression_policy）。
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM add_retention_policy(
            'panel.basis_panel',
            BIGINT '1209600000',  -- 14 days in ms
            if_not_exists => TRUE
        );
    END IF;
END $$;

-- ============================================================
-- Guard C: hot-path index idx_basis_panel_ts_desc_symbol 欄位組合驗證
-- 對齊 schema_guard_template.sql + V085/V087 Guard C pattern
-- 索引存在但欄位組合錯 → RAISE；索引不存在 → no-op
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'panel'
      AND c.relname = 'idx_basis_panel_ts_desc_symbol';

    IF v_actual IS NOT NULL AND position('snapshot_ts_ms DESC' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V115 Guard C FAIL: idx_basis_panel_ts_desc_symbol exists but '
            'column list mismatch. Expected to contain snapshot_ts_ms DESC, '
            'actual: %. DROP INDEX + re-apply migration to repair.', v_actual;
    END IF;

    IF v_actual IS NOT NULL AND position('symbol' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V115 Guard C FAIL: idx_basis_panel_ts_desc_symbol exists but '
            'missing symbol column. Actual: %.', v_actual;
    END IF;
END $$;

-- ============================================================
-- §5 Hot-path index (idempotent)
-- Hot-path query 1: Stage 0R as-of LATERAL（per spec §5.1 A1 runner）
--   SELECT basis_pct FROM panel.basis_panel b
--   WHERE b.symbol = $1 AND b.snapshot_ts_ms <= $2
--   ORDER BY b.snapshot_ts_ms DESC LIMIT 1
--   → (snapshot_ts_ms DESC, symbol) 複合索引覆蓋 as-of range scan + symbol filter
-- Hot-path query 2: healthcheck freshness
--   SELECT MAX(snapshot_ts_ms) FROM panel.basis_panel
--   → DESC index leftmost lookup
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_basis_panel_ts_desc_symbol
    ON panel.basis_panel (snapshot_ts_ms DESC, symbol);

-- sister secondary index（per spec §3.1 line 103-104；snapshot_ts_ms DESC only
-- 供純 MAX(snapshot_ts_ms) freshness query 的更窄 leftmost index）
CREATE INDEX IF NOT EXISTS basis_panel_snapshot_ts_ms_idx
    ON panel.basis_panel (snapshot_ts_ms DESC);

-- ============================================================
-- §6 COMMENT 語義文檔 (idempotent: COMMENT ON 可重跑)
-- ============================================================
COMMENT ON TABLE panel.basis_panel IS
    'P2-BASIS-PANEL-INFRA perp-index basis (期現價差) point-in-time panel. '
    'basis_pct = (perp_last_price/index_price - 1)*100 SIGNED；單位 %. '
    'Producer = Rust panel_aggregator/basis.rs（WS tickers.{sym} broadcast '
    'last_price + index_price，60s flush，latest-value cache 跨 frame 保 index）. '
    'Consumer = A1 funding_short_v2 Stage 0R offline replay（as-of LATERAL，取 '
    'ABS(basis_pct) < 0.3 gate）. 無 IPC slot（strategy live 用 in-memory cache）. '
    '14d retention; cold data auto-drop. 前向累積（market_tickers 歷史壞死不可 '
    'backfill，spec §1.4）. PK (snapshot_ts_ms, symbol).';

COMMENT ON COLUMN panel.basis_panel.snapshot_ts_ms IS
    'Aggregator flush 時戳 (ms epoch)。hypertable time column；同一 snapshot 所有 '
    'cohort sym row 共享同值。60s flush cadence（對齊 sister panel）。';

COMMENT ON COLUMN panel.basis_panel.symbol IS
    'Cohort symbol (e.g. BTCUSDT)。對齊 funding_curve/oi_delta 既有 cohort（≥ A1 '
    'BTC/ETH ∪ baseline 採樣 cohort，spec §4.4）；index 缺失的 sym 該 snapshot 不寫 row。';

COMMENT ON COLUMN panel.basis_panel.perp_last_price IS
    'basis 分子 = perp last_price（**非 mark_price**）。對齊 strategy live path '
    'ctx.price=last_price（funding_short_v2/mod.rs:155-157）保 Stage 0R replay parity。';

COMMENT ON COLUMN panel.basis_panel.index_price IS
    'basis 分母 = Bybit V5 tickers indexPrice（現貨指數）。NOT NULL + writer 端 '
    'index>0 才寫 row（fail-closed）；index≤0/缺失 → 不發 INSERT（不寫 0/NULL row，'
    '避污染 Stage 0R as-of lookup）。WS index_price 只在 snapshot frame 帶，'
    'aggregator latest-value cache 跨 frame 保 last-known。';

COMMENT ON COLUMN panel.basis_panel.basis_pct IS
    '(perp_last_price/index_price - 1)*100 **SIGNED**（保留方向資訊供 future 研究）。'
    'consumer/Stage 0R runner 取 ABS(basis_pct) 比 A1 entry gate (< 0.3%)。逐位對齊 '
    'funding_short_v2/mod.rs:157 公式（strategy 端取 abs；panel 存 signed）。';

COMMENT ON COLUMN panel.basis_panel.source_tier IS
    'Provenance tier。預設 ''bybit_v5_ws_tickers''（basis 全 WS tickers 衍生，'
    '無 REST 路徑）；對齊 sister panel source_tier 命名語義。';

COMMIT;

-- ============================================================
-- §7 Final NOTICE (transaction-end NOTICE for operator runbook)
-- 注意：COMMIT 之後的 RAISE NOTICE 需在獨立 DO block (PG 限制)
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE 'V115 land complete:';
    RAISE NOTICE '  - panel.basis_panel table 6 column';
    RAISE NOTICE '    PRIMARY KEY (snapshot_ts_ms, symbol)';
    RAISE NOTICE '    columns: snapshot_ts_ms / symbol / perp_last_price /';
    RAISE NOTICE '             index_price / basis_pct (SIGNED) / source_tier';
    RAISE NOTICE '    (無 mark_price / 無 engine_mode — market 共享平面)';
    RAISE NOTICE '  - TimescaleDB hypertable (1d chunk on snapshot_ts_ms BIGINT)';
    RAISE NOTICE '  - panel.unix_now_ms() integer_now_func registered';
    RAISE NOTICE '  - 14d retention policy (BIGINT 1209600000 ms; 無 compression)';
    RAISE NOTICE '  - idx_basis_panel_ts_desc_symbol (snapshot_ts_ms DESC, symbol)';
    RAISE NOTICE '  - basis_panel_snapshot_ts_ms_idx (snapshot_ts_ms DESC)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps (E1 IMPL B-2/B-3/B-4):';
    RAISE NOTICE '  - Rust panel_aggregator/basis.rs (WS subscribe + 60s flush + latest cache)';
    RAISE NOTICE '  - basis 公式 = (last/index-1)*100 SIGNED (parity funding_short_v2:157)';
    RAISE NOTICE '  - index<=0/缺失 -> skip (不寫 0/NULL row; writer fail-closed)';
    RAISE NOTICE '  - A1 a1_funding_short_metrics.py as-of LATERAL -> panel.basis_panel';
    RAISE NOTICE '  - healthcheck basis_panel freshness (60s flush cadence)';
END $$;
