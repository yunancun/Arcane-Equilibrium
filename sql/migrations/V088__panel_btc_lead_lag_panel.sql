-- ============================================================
-- V088: panel.btc_lead_lag_panel — W2 A4-C BTC→Alt Lead-Lag panel skeleton
-- Status: NOT_RUN — Sprint N+1 D+1 deploy after 21:30 UTC sign-off (D+0)
-- Spec:   docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md (v1.2)
-- 預留:   V088 per memory project_2026_05_10_sprint_n1_d0_readiness.md
--         （Sprint N+1 D+0 dispatch 預留，同 wave V086 W6-3c 鄰位）
--
-- 動機 / Motivation:
--   W6 baseline + 4-agent loss audit 雙重確認（2026-05-10）：5 textbook 策略
--   結構性 alpha-deficient（demo 7d gross −26.44 USDT, realized edge `[40]`
--   avg_net 持續 −6 bps）。P0-EDGE-1 不靠 textbook 策略本身能解。
--
--   A4-C BTC→Alt Lead-Lag 是 W-AUDIT-8c 候選 C 的 fast-track 預跑：用 BTCUSDT
--   1m kline + orderbook 算 lead signal（return / volume z / book imbalance over
--   N=120s 主信號 + 60s/300s shadow value 收 R²(N) decay curve evidence）+
--   BTCUSDT 1h kline 算 regime_tag → 7-symbol alt cohort xcorr + expected_dir
--   寫 panel.btc_lead_lag_panel；ma_crossover + grid_trading 在 paper engine mode
--   接 BtcLeadLag 為 CrossAsset tag, on_tick shadow log only 不 trade。
--
--   7d paper engine 收 evidence，gate 三檔（avg_net ≥ +15 bps promote N+2 /
--   +5~+15 extend 14d / <+5 revise）才決定 N+2 demo IMPL 路徑。
--
-- 範圍 / Scope (V088):
--   1. CREATE SCHEMA panel（首個 panel.* 表，schema 不存在則建）
--   2. CREATE TABLE panel.btc_lead_lag_panel（per spec §4.1 schema）：
--        - snapshot_ts_ms BIGINT（1m grain timestamp）
--        - lead_window_secs INT（主信號固定 120）
--        - btc_lead_return_pct REAL（bps，主信號 N=120）
--        - btc_lead_return_pct_60s REAL（bps，N=60 shadow value, decay curve evidence）
--        - btc_lead_return_pct_300s REAL（bps，N=300 shadow value, decay curve evidence）
--        - btc_volume_z REAL（per §3.1.2，主信號 N=120）
--        - btc_book_imbalance REAL（per §3.1.3）
--        - alt_symbols TEXT[]（cohort symbol list, per §2.2）
--        - alt_xcorr REAL[]（per §3.2，主 N=120，與 alt_symbols 同序，NaN 表 sample 不足）
--        - alt_expected_dir SMALLINT[]（−1 / 0 / +1，per §3.3，主 N=120）
--        - regime_tag TEXT（'normal' / 'extreme'，|BTC 1h return| > 200 bps 標 extreme）
--        - source_tier TEXT（固定 'cross_asset_btc_lead_lag'）
--   3. TimescaleDB hypertable（chunk_time_interval = 1 day，BIGINT 時間維度）
--   4. Retention policy 14d（paper-only 期；N+2 promote demo 後升 30d 走新 V###）
--   5. Hot-path index：(snapshot_ts_ms DESC, lead_window_secs) covering
--   6. Guard A/B/C 強制（schema_guard_template.sql 三層）+ 註釋。
--
-- 不變式 / Invariants:
--   - panel schema 為 cross-asset / cross-strategy collector 專用；本 V088 是
--     首個 panel.* 表，schema 缺則自動建（CREATE SCHEMA IF NOT EXISTS）
--   - 1 snapshot = 1 row（per-snapshot vector layout，per spec §4.1 Hypertable
--     設計；對應 W-AUDIT-8a Phase A `BtcLeadLagPanel` struct rust 端 vector layout）
--   - alt_symbols / alt_xcorr / alt_expected_dir 三 array 同長度 + 同序（writer
--     端強制；schema 層 PG array 不能 enforce length-equality cross-column，由
--     application Guard）
--   - 主信號 lead_window_secs=120；60s/300s shadow value 寫 schema column 但不
--     寫 IPC slot（avoid Rust strategy 接觸下游污染 main signal）
--   - regime_tag = 'extreme' 的 row 仍寫入，但 §7.2 evaluate SQL 以
--     `FILTER (WHERE regime_tag = 'normal')` 排除，不計入 7d edge avg
--   - source_tier 固定 'cross_asset_btc_lead_lag'（per spec §4.1，不允許 writer
--     寫其他值；未來新 panel.* 表用獨立 source_tier）
--   - paper-only fence Layer 1 在 Rust step_4_5_dispatch.rs；Layer 2 在 Python
--     writer btc_lead_lag_writer.py（per spec §6）；schema 本身不阻 demo/live
--     寫入（fence 在上層）— V088 純 schema, runtime gate 由 writer + Rust gate 守
--
-- Idempotency:
--   全 migration 重跑兩次必須 PASS：
--     - CREATE SCHEMA IF NOT EXISTS  → 第二次 no-op
--     - CREATE TABLE IF NOT EXISTS   → 第二次 no-op（Guard A 確認 shape）
--     - create_hypertable(..., if_not_exists => TRUE)  → 第二次 no-op
--     - add_retention_policy(..., if_not_exists => TRUE) → 第二次 no-op
--     - CREATE INDEX IF NOT EXISTS   → 第二次 no-op（Guard C 確認 column set）
--     - COMMENT ON                   → 第二次覆蓋 OK（PG 允許）
--
-- E2 review checklist:
--   1. Guard A：panel schema 存在則 panel.btc_lead_lag_panel shape 必含 12 column
--      （per spec §4.1 完整列）；schema 不存在則 CREATE SCHEMA + CREATE TABLE 自然
--      建立，no-op pass
--   2. Guard B：3 新數值 column（btc_lead_return_pct_60s / btc_lead_return_pct_300s
--      / regime_tag）的 data_type 對嗎？(real / real / text)
--   3. Guard C：hot-path index `idx_btc_lead_lag_panel_ts_window` 必含
--      `(snapshot_ts_ms DESC, lead_window_secs)`（per spec §4.1）
--   4. TimescaleDB hypertable 走 BIGINT 時間維度，chunk_time_interval = 86400000
--      ms（= 1 day in ms）— Rust producer 寫 epoch ms 必須對齊 1m grain（writer
--      端 invariant，schema 層只驗 BIGINT 型別）
--   5. Retention policy `INTERVAL '14 days'` 14d paper-only 期；N+2 promote demo
--      後升 30d 走新 V### migration（不在本 V088 scope）
--   6. CREATE SCHEMA panel：首個 panel.* 表，schema 不能預設存在，必 CREATE
--      SCHEMA IF NOT EXISTS（PG 允許 idempotent）
--
-- D+1 IMPL 補丁餘地（per W2 dispatch v3.3 §3.2 W2 fast-track）：
--   本 file 為 D+0 21:30 UTC sign-off 前 SQL skeleton 預寫；D+1 W2 E1-δ
--   (C-IMPL-2) IMPL phase 預期可能微調：
--     - constraint name 命名是否對齊 panel.* 未來 sibling 表的 pattern（V085/V087
--       Phase B Tier 2 panel.* 鄰位若 land 後對齊）
--     - chunk_time_interval 是否需縮短至 1h（per W-AUDIT-8a Phase B 模板 review；
--       1m grain × 60 row/h × 24h = 1440 row/day 不算大，1 day chunk 合適）
--     - Linux PG dry-run 兩次驗 idempotent（Mac mock 不夠 per
--       feedback_v_migration_pg_dry_run）
--     - Bybit V5 orderbook snapshot frequency 對 alt_symbols cohort scope 的影響：
--       7-symbol cohort 1m × 7 = 7 req/min，與 BTC 1m kline 1 req + BTC 1h kline
--       1 req + BTC orderbook 1 req = 10 req/min 合計，well under 120 req/s budget
-- ============================================================

BEGIN;

-- ============================================================
-- §1 CREATE SCHEMA panel（idempotent, 對齊 V085/V087 panel.* sibling pattern）
-- per spec §4.1：panel schema 為 cross-asset / cross-strategy collector 專用
-- panel schema 為 W-AUDIT-8a Phase B Tier 2 namespace；V085 (funding_curve) /
-- V087 (oi_delta_panel) / V088 (btc_lead_lag_panel) 三 sibling 都用同樣 idempotent
-- CREATE SCHEMA IF NOT EXISTS（whoever runs first creates；其餘 no-op）
-- ============================================================
CREATE SCHEMA IF NOT EXISTS panel;

-- ============================================================
-- Guard A: panel.btc_lead_lag_panel 若已存在則必含 12 必要欄位
-- Guard A: panel.btc_lead_lag_panel must contain 12 required columns if exists
-- 對齊 spec §4.1 schema 完整列（防 V085/V087 sibling panel.* 預先 land 後 shape drift）
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'panel' AND table_name = 'btc_lead_lag_panel'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'snapshot_ts_ms',
            'lead_window_secs',
            'btc_lead_return_pct',
            'btc_lead_return_pct_60s',
            'btc_lead_return_pct_300s',
            'btc_volume_z',
            'btc_book_imbalance',
            'alt_symbols',
            'alt_xcorr',
            'alt_expected_dir',
            'regime_tag',
            'source_tier'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'panel'
              AND table_name = 'btc_lead_lag_panel'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V088 Guard A FAIL: panel.btc_lead_lag_panel exists but missing required columns: %. '
                'A previous migration likely pre-created this table with a different shape. '
                'Resolve legacy schema (DROP + re-apply, or ALTER ADD missing columns) then re-run V088.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ============================================================
-- §2 CREATE TABLE panel.btc_lead_lag_panel
-- per spec §4.1 完整 schema
--
-- PRIMARY KEY 設計：(snapshot_ts_ms, lead_window_secs)
--   - 1 snapshot per 1m grain，主信號 lead_window_secs=120 固定
--   - PK 含 lead_window_secs 是為未來 backward-compat 預留（如未來有獨立 60s/300s
--     主信號 row，可同 snapshot_ts_ms 不撞 PK；目前 writer 只寫 lead_window_secs=120
--     1 row per snapshot, 60s/300s 為 schema column shadow 不是獨立 row）
--   - hypertable partition key 必含於 PK：snapshot_ts_ms 是 partition col，已含
--
-- Hypertable 設計：
--   - chunk_time_interval = 86400000 ms（= 1 day），對齊 BTC 1m grain × 1440 row/day
--     單一 chunk 可承載 ~1 day data
--   - if_not_exists => TRUE 確保 idempotent
--
-- Retention 設計：
--   - INTERVAL '14 days' paper-only 期 retention；N+2 promote demo 後升 30d 新 V###
--   - if_not_exists => TRUE idempotent
-- ============================================================
CREATE TABLE IF NOT EXISTS panel.btc_lead_lag_panel (
    -- 時間維度（hypertable partition key, BIGINT epoch ms 對齊 1m grain）
    snapshot_ts_ms          BIGINT      NOT NULL,
    -- lead window 維度（主信號固定 120, PK 預留 future per-N row）
    lead_window_secs        INT         NOT NULL,

    -- BTC lead signal 主信號（per spec §3.1, N=120 主，60s/300s shadow column）
    btc_lead_return_pct     REAL,            -- bps，主信號 N=120
    btc_lead_return_pct_60s REAL,            -- bps，N=60 shadow（v1.1 condition #3 R²(N) decay curve evidence）
    btc_lead_return_pct_300s REAL,           -- bps，N=300 shadow（v1.1 condition #3 R²(N) decay curve evidence）
    btc_volume_z            REAL,            -- per §3.1.2，rolling 1h baseline shift(1)
    btc_book_imbalance      REAL,            -- per §3.1.3，Bybit V5 orderbook top-10

    -- Alt cohort 維度（per-snapshot vector layout，3 array 同長度 + 同序）
    alt_symbols             TEXT[]      NOT NULL,   -- cohort symbol list，per spec §2.2 e.g. {ETHUSDT,SOLUSDT,...}
    alt_xcorr               REAL[],          -- per §3.2，與 alt_symbols 同序，NaN 表 sample 不足 (consumer no-signal)
    alt_expected_dir        SMALLINT[],      -- −1 / 0 / +1，per §3.3，與 alt_symbols 同序

    -- Regime guard（v1.1 §9 condition #5：|BTC 1h return| > 200 bps 標 extreme，shadow log only 不計入 edge avg）
    regime_tag              TEXT        NOT NULL DEFAULT 'normal',

    -- Source tier（固定 'cross_asset_btc_lead_lag'，writer 端強制）
    source_tier             TEXT        NOT NULL DEFAULT 'cross_asset_btc_lead_lag',

    PRIMARY KEY (snapshot_ts_ms, lead_window_secs)
);

-- ============================================================
-- §3 TimescaleDB hypertable conversion
-- 條件判斷：無 TimescaleDB extension 時跳過（保留 plain table fallback）
-- chunk_time_interval = 86400000 ms（= 1 day）
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'panel.btc_lead_lag_panel',
            'snapshot_ts_ms',
            chunk_time_interval => 86400000,   -- 1 day in milliseconds
            if_not_exists => TRUE
        );
        RAISE NOTICE 'V088: hypertable panel.btc_lead_lag_panel created (1 day chunk_time_interval ms)';
    ELSE
        RAISE NOTICE 'V088: TimescaleDB extension not present; panel.btc_lead_lag_panel kept as plain table';
    END IF;
END $$;

-- ============================================================
-- §4 Retention policy: 14d paper-only window
-- per spec §4.1：paper-only 期 retention 14d；N+2 promote demo 後升 30d 走新 V###
-- 條件判斷：無 TimescaleDB 時跳過（plain table 無 retention，operator 手動 truncate）
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM add_retention_policy(
            'panel.btc_lead_lag_panel',
            INTERVAL '14 days',
            if_not_exists => TRUE
        );
        RAISE NOTICE 'V088: retention policy 14d set on panel.btc_lead_lag_panel (paper-only window)';
    END IF;
END $$;

-- ============================================================
-- Guard B: 3 新數值 column 必為對應 type
-- Guard B: 3 new value columns must have correct data_type
-- 對齊 spec §4.1 type 約定（real / real / text）
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- btc_lead_return_pct_60s 必為 real
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel'
      AND table_name = 'btc_lead_lag_panel'
      AND column_name = 'btc_lead_return_pct_60s';
    IF v_actual IS NOT NULL AND v_actual <> 'real' THEN
        RAISE EXCEPTION
            'V088 Guard B FAIL: panel.btc_lead_lag_panel.btc_lead_return_pct_60s '
            'is %, expected real. Type drift detected.',
            v_actual;
    END IF;

    -- btc_lead_return_pct_300s 必為 real
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel'
      AND table_name = 'btc_lead_lag_panel'
      AND column_name = 'btc_lead_return_pct_300s';
    IF v_actual IS NOT NULL AND v_actual <> 'real' THEN
        RAISE EXCEPTION
            'V088 Guard B FAIL: panel.btc_lead_lag_panel.btc_lead_return_pct_300s '
            'is %, expected real. Type drift detected.',
            v_actual;
    END IF;

    -- regime_tag 必為 text
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'panel'
      AND table_name = 'btc_lead_lag_panel'
      AND column_name = 'regime_tag';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V088 Guard B FAIL: panel.btc_lead_lag_panel.regime_tag '
            'is %, expected text. Type drift detected.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- §5 Hot-path index：(snapshot_ts_ms DESC, lead_window_secs)
-- per spec §4.1：「索引：(snapshot_ts_ms DESC, lead_window_secs) covering」
--
-- 用途：
--   1. Rust IPC slot BtcLeadLagPanelSlot 啟動 latest() 查詢 (DESC + LIMIT 1)
--   2. §7.2 counterfactual SQL evaluate WHERE snapshot_ts_ms >= NOW() - 7d
--   3. paper edge report D+12 30-min bucket rolling decay curve
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_btc_lead_lag_panel_ts_window
    ON panel.btc_lead_lag_panel (snapshot_ts_ms DESC, lead_window_secs);

-- ============================================================
-- Guard C: hot-path index 必含 (snapshot_ts_ms DESC, lead_window_secs)
-- Guard C: hot-path index must contain expected column set
-- per CLAUDE.md §七 SQL migration Guard C 強制
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'panel'
      AND c.relname = 'idx_btc_lead_lag_panel_ts_window';

    IF v_actual IS NOT NULL AND position('snapshot_ts_ms DESC' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V088 Guard C FAIL: idx_btc_lead_lag_panel_ts_window exists but missing '
            '"snapshot_ts_ms DESC". Actual: %. '
            'DROP INDEX + re-apply V088 to repair.',
            v_actual;
    END IF;

    IF v_actual IS NOT NULL AND position('lead_window_secs' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V088 Guard C FAIL: idx_btc_lead_lag_panel_ts_window exists but missing '
            '"lead_window_secs". Actual: %. '
            'DROP INDEX + re-apply V088 to repair.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- §6 COMMENT 與註解（idempotent: COMMENT ON 可重跑覆蓋）
-- ============================================================
COMMENT ON SCHEMA panel IS
    'Cross-asset / cross-strategy panel collector namespace (W-AUDIT-8a Phase B Tier 2). '
    'First table V088 panel.btc_lead_lag_panel (W2 A4-C BTC→Alt Lead-Lag, paper-only).';

COMMENT ON TABLE panel.btc_lead_lag_panel IS
    'W2 A4-C BTC→Alt Lead-Lag panel — BTCUSDT 1m kline + orderbook 算 lead signal '
    '+ 7-symbol alt cohort xcorr/expected_dir (paper-only, retention 14d). '
    'Spec: docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md (v1.2). '
    'Per-snapshot vector layout (1 snapshot per 1m grain, alt_* arrays 同序). '
    '主信號 lead_window_secs=120; 60s/300s shadow value 寫 column 但不寫 IPC slot.';

COMMENT ON COLUMN panel.btc_lead_lag_panel.snapshot_ts_ms IS
    'Snapshot timestamp epoch ms (1m grain，writer 端對齊 1m bucket). '
    'Hypertable partition key (chunk_time_interval = 1 day in ms).';

COMMENT ON COLUMN panel.btc_lead_lag_panel.lead_window_secs IS
    'Lead window seconds. 主信號固定 120 (per spec §3.1 v1.1 N 鎖定 + Easley/De Prado/'
    'O''Hara 2021 + Makarov-Schoar JFE 2020 BTC→alt informational lead 半衰期 30-180s).';

COMMENT ON COLUMN panel.btc_lead_lag_panel.btc_lead_return_pct IS
    'BTC lead return bps over N=120s (主信號). per spec §3.1.1: '
    '(close_btc[t] - close_btc[t-N]) / close_btc[t-N] * 10000. '
    'Strict shift(N) lookahead-free (禁含 current bar, per §3.2 + §7.3 + MIT C-3 grep verify).';

COMMENT ON COLUMN panel.btc_lead_lag_panel.btc_lead_return_pct_60s IS
    'BTC lead return bps over N=60s (shadow value, R²(N) decay curve evidence per v1.1 condition #3). '
    'D+12 paper edge report 必含 N=60/120/300 三檔 R² decay curve (per spec §7.1 metric 4).';

COMMENT ON COLUMN panel.btc_lead_lag_panel.btc_lead_return_pct_300s IS
    'BTC lead return bps over N=300s (shadow value, R²(N) decay curve evidence per v1.1 condition #3). '
    'D+12 paper edge report 必含 N=60/120/300 三檔 R² decay curve (per spec §7.1 metric 4).';

COMMENT ON COLUMN panel.btc_lead_lag_panel.btc_volume_z IS
    'BTC volume z-score over N=120s (rolling 1h baseline shift(1)). per spec §3.1.2.';

COMMENT ON COLUMN panel.btc_lead_lag_panel.btc_book_imbalance IS
    'BTC orderbook top-10 imbalance: (bid_size - ask_size) / (bid_size + ask_size). '
    'per spec §3.1.3, Bybit V5 /v5/market/orderbook 1m grain snapshot.';

COMMENT ON COLUMN panel.btc_lead_lag_panel.alt_symbols IS
    'Cohort alt symbol list (per spec §2.2 7-symbol cohort: ETHUSDT/SOLUSDT/XRPUSDT/'
    'DOGEUSDT/ADAUSDT/AVAXUSDT/DOTUSDT). Order matters — alt_xcorr + alt_expected_dir '
    '同序對齊；writer 端強制 array length consistency.';

COMMENT ON COLUMN panel.btc_lead_lag_panel.alt_xcorr IS
    'Pearson cross-correlation per alt symbol vs BTC lead return (rolling 1h, min 30 sample). '
    'per spec §3.2. NaN 表 sample 不足 (consumer 視 NaN 為 no-signal). 與 alt_symbols 同序.';

COMMENT ON COLUMN panel.btc_lead_lag_panel.alt_expected_dir IS
    'Predicted direction per alt symbol (−1 SHORT / 0 no-signal / +1 LONG). per spec §3.3. '
    '主信號 N=120, threshold_X=10 bps, threshold_Y=0.40 (PA spec 預設, QC + MIT D+1 不再可改). '
    '與 alt_symbols + alt_xcorr 同序.';

COMMENT ON COLUMN panel.btc_lead_lag_panel.regime_tag IS
    'BTC regime tag: ''normal'' or ''extreme'' (|BTCUSDT 1h return| > 200 bps → extreme, '
    'per spec §9 v1.1 condition #5). Extreme row 仍寫入但 §7.2 evaluate SQL 以 '
    'FILTER (WHERE regime_tag = ''normal'') 排除, 不計入 7d edge avg.';

COMMENT ON COLUMN panel.btc_lead_lag_panel.source_tier IS
    'Source tier (固定 ''cross_asset_btc_lead_lag''). per spec §4.1. '
    '未來其他 panel.* 表用獨立 source_tier (不重用本值).';

COMMIT;

-- ============================================================
-- §7 Final NOTICE (in transaction-end NOTICE for operator runbook)
-- COMMIT 之後的 RAISE NOTICE 需在獨立 DO block (PG 限制)
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE 'V088 land complete:';
    RAISE NOTICE '  - CREATE SCHEMA panel (W-AUDIT-8a Phase B namespace, 首個 panel.* 表)';
    RAISE NOTICE '  - CREATE TABLE panel.btc_lead_lag_panel (12 column, per-snapshot vector layout)';
    RAISE NOTICE '  - TimescaleDB hypertable (chunk_time_interval = 1 day in ms)';
    RAISE NOTICE '  - Retention policy 14 days (paper-only window; N+2 promote demo 升 30d 新 V###)';
    RAISE NOTICE '  - Hot-path index idx_btc_lead_lag_panel_ts_window (snapshot_ts_ms DESC, lead_window_secs)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps (D+1 W2 IMPL phase):';
    RAISE NOTICE '  - W2 E1-δ (C-IMPL-2): IMPL btc_lead_lag_writer.py + Rust BtcLeadLagPanelSlot + step_4_5_dispatch surface field assignment + paper-only engine_mode gate';
    RAISE NOTICE '  - W2 E1-ε (C-IMPL-3): IMPL ma_crossover/grid_trading declared_alpha_sources += CrossAsset + on_tick shadow log only (paper engine only)';
    RAISE NOTICE '  - W2 E1-ζ (C-IMPL-4): D+5 paper engine deploy 後跑 7d, D+12 paper edge report land (含 §7.1 mandatory metric 6 條 + dual-layer σ acceptance + PSR(0) skew/kurt formula + +15 bps gate power verification)';
END $$;
