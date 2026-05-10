-- ============================================================
-- V087: panel.oi_delta_panel — W1 W-AUDIT-8a Phase B Tier 2 OI delta panel
--   WS-fed cross-symbol open interest delta panel（5m / 15m / 1h）
--   for AlphaSurface.oi_delta_panel typedef wire
--
-- 動機 / Motivation:
--   W-AUDIT-8a Phase A 已 land 全 Tier struct typedef + Strategy::on_tick(ctx,
--   surface) 接口（HEAD c9fb0b8f / b6ed4975），但 AlphaSurface.oi_delta_panel
--   永遠 None（trait 預留 field 但 caller 不 wire）。bb_breakout 已 declare
--   OiDeltaPanel tag (`mod.rs:295-300`) 但 silent fallback。
--
--   W1 Phase B B-2 把 oi_delta_panel 從 stub typedef 升級為真實 wire panel：
--   Rust panel_aggregator/oi_delta.rs 訂閱既有 WS event stream（tickers.{sym}
--   topic 已 extract open_interest），cold-start backfill 跑 1 次 batch REST
--   /v5/market/open-interest 拉 25 sym × 3 interval (5min/15min/1h) history
--   建 baseline，後續 WS push 即時 oi_abs，aggregator 算 5m/15m/1h delta vs
--   sliding window，60s 一視窗 flush 同時寫 Rust slot (hot path) + PG (audit
--   / ML training data / healthcheck source)。bb_breakout consumer 真實
--   consume `surface.oi_delta_panel`，panel unavailable 時 fail-closed 寫
--   `evaluation_outcome='oi_panel_unavailable'`。
--
--   Spec source:
--     - W1 PA spec v1.1 (WS-first revision)
--       docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md §3
--     - 對齊 trait typedef
--       srv/rust/openclaw_core/src/alpha_surface.rs:159-175 OIDeltaPanel
--     - V086 sister pattern (W6-3c governance reject/close enum)
--       srv/sql/migrations/V086__governance_reject_close_reason_code.sql
--
-- 範圍 / Scope (V087):
--   1. CREATE SCHEMA IF NOT EXISTS panel
--      （sister V085 funding_rates_panel 也建同 schema，先 land 者勝；
--        V087 用 IF NOT EXISTS 雙安全）
--   2. CREATE TABLE IF NOT EXISTS panel.oi_delta_panel
--      （PK: snapshot_ts_ms + symbol；25 row per snapshot；DOUBLE PRECISION
--       delta column 可 NULL — cold-start backfill 不齊或 5m/15m/1h window
--       不足 NaN 時不插）
--   3. TimescaleDB hypertable conversion (idempotent, ext-guarded for
--      non-Timescale env)
--      chunk_time_interval = 1 day（86400000 ms；對齊 W1 spec §3.2）
--   4. Retention policy 14d (idempotent, ext-guarded)
--      paper-only 14d learning window — 不長期保留（saving disk + cold
--      start 重 backfill 即可）
--   5. Hot-path index idx_oi_panel_ts_desc_symbol (snapshot_ts_ms DESC, symbol)
--      for healthcheck `[58]` PG-side freshness query 與 ML trainer
--      JOIN by symbol 兩 pattern
--   6. Guard A/B/C 強制（schema_guard_template.sql 三層）+ idempotency
--
-- 不變式 / Invariants:
--   - panel schema 是 Phase B Tier 2 panel collector family 共用 namespace
--     （V085 funding_rates_panel + V087 oi_delta_panel；後續 W-AUDIT-8c/8d
--     再加 basis / orderflow panel）。各 panel table PK 必為
--     (snapshot_ts_ms, symbol)，便於 cross-panel 同步 GROUP BY 對齊。
--   - oi_abs DOUBLE PRECISION NOT NULL — current OI 絕對值；3 種 delta 欄位
--     全 NULL 表示 cold-start 完全失敗或 1h sliding window 不足，consumer 端
--     必判 NaN 走 fail-closed。
--   - oi_delta_5m_pct / 15m_pct / 1h_pct 單位 percent（不 bps），對齊 trait
--     OIDeltaPanel.oi_delta_5m_pct: Vec<f64> 預期值範圍。
--   - source_tier 預設 'bybit_v5_public'；後續 W-AUDIT-8d 加 hybrid (WS+REST)
--     可寫 'bybit_v5_ws_tickers' / 'bybit_v5_rest_open_interest' 區分來源。
--   - hypertable + retention 經 pg_extension guard 避開 non-Timescale env
--     fail（dev / Mac mock pytest 環境往往無 timescaledb extension）。
--   - 14d retention 是「冷數據自動 drop」：drop_after = INTERVAL '14 days'
--     後 chunk 自動清，不需 cron / manual。Aggregator cold-start 重新跑
--     bybit_rest_client.get_open_interest_batch() 即可重 backfill。
--
-- Idempotency:
--   全 migration 重跑兩次必須 PASS：
--     - CREATE SCHEMA IF NOT EXISTS → 第二次 no-op
--     - CREATE TABLE IF NOT EXISTS → 第二次 no-op (Guard A 已驗 shape)
--     - create_hypertable(if_not_exists => TRUE) → 第二次 no-op
--     - add_retention_policy(if_not_exists => TRUE) → 第二次 no-op
--     - CREATE INDEX IF NOT EXISTS → 第二次 no-op (Guard C 已驗欄位)
--
-- E2 review checklist:
--   1. Guard A 驗 panel.oi_delta_panel 既存 shape 對嗎？(snapshot_ts_ms BIGINT
--      / symbol TEXT / oi_abs DOUBLE PRECISION 等 6 column 全俱在)
--   2. Guard B 驗 oi_delta_5m_pct / 15m_pct / 1h_pct 三 column 型別必為
--      'double precision' (canonical name 小寫，不是 'float8' 別名)
--   3. Guard C 驗 idx_oi_panel_ts_desc_symbol index 含 'snapshot_ts_ms DESC'
--      pattern (per pg_get_indexdef substring match)
--   4. timescaledb pg_extension guard wrap hypertable + retention 兩呼叫
--      （對齊 V002 既有 pattern line 179-185）
--   5. PRIMARY KEY (snapshot_ts_ms, symbol) 順序對嗎？(snapshot_ts_ms 在前
--      因為 hypertable partition column 是 snapshot_ts_ms — TimescaleDB
--      要求 partition column 在 PK 內)
--   6. retention 14d INTERVAL 對齊 paper-only learning window 政策
--      (對比 V002 market.open_interest 的「永久保留」策略 — 此 panel 是
--       衍生短期數據，與 raw OI 區別)
--
-- D+1 IMPL 補丁餘地:
--   本 file 為 sign-off 前 SQL skeleton 預寫；D+1 W1 IMPL 階段預期可能
--   微調：
--     - constraint name 命名（chk_oi_panel_*）若需加 CHECK constraint
--       (per E2 review)
--     - chunk_time_interval 值（當前 86400000 ms = 1d；若 25 sym × 1440
--       row/day = 36000 row/day chunk 過大，需縮短至 6h chunk 提升查詢效率）
--     - source_tier enum 收緊（W-AUDIT-8d hybrid source 上線後）
--     - Linux PG dry-run 驗 hypertable + retention policy 實際 land
--       (per `feedback_v_migration_pg_dry_run` 2026-05-05 V055 5-round 教訓)
-- ============================================================

BEGIN;

-- ============================================================
-- §1 CREATE SCHEMA IF NOT EXISTS panel
-- panel namespace 是 Phase B Tier 2 panel collector family 共用 namespace
-- (V085 funding_rates_panel + V087 oi_delta_panel)
-- 雙重 IF NOT EXISTS 保護：sister V085 也建同 schema，先 land 者勝
-- ============================================================
CREATE SCHEMA IF NOT EXISTS panel;

-- ============================================================
-- Guard A: panel.oi_delta_panel 表存在時必須含全部必要 column
-- 對齊 W1 spec §3.2 schema 6 column
-- 若表不存在 (首次 run) → no-op，下方 CREATE TABLE 會自然建立
-- 若表存在但 shape drift (legacy mis-applied) → RAISE，operator 手動 resolve
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='panel' AND table_name='oi_delta_panel'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'snapshot_ts_ms',
            'symbol',
            'oi_delta_5m_pct',
            'oi_delta_15m_pct',
            'oi_delta_1h_pct',
            'oi_abs',
            'source_tier'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='panel' AND table_name='oi_delta_panel'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V087 Guard A FAIL: panel.oi_delta_panel exists but missing required columns: %. '
                'Legacy mis-applied schema detected. Resolve manually (DROP TABLE + re-apply V087, '
                'or ALTER TABLE ADD COLUMN missing fields) then re-run.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ============================================================
-- §2 CREATE TABLE IF NOT EXISTS panel.oi_delta_panel
-- per W1 spec §3.2
-- 對齊 trait OIDeltaPanel typedef (alpha_surface.rs:159-175):
--   - snapshot_ts_ms (BIGINT) → OIDeltaPanel.snapshot_ts_ms: i64
--   - symbol (TEXT, 25 row per snapshot) → OIDeltaPanel.symbols: Vec<String>
--   - oi_abs (DOUBLE PRECISION NOT NULL) → OIDeltaPanel.oi_abs: Vec<f64>
--   - oi_delta_5m_pct / 15m_pct / 1h_pct (DOUBLE PRECISION nullable)
--       → OIDeltaPanel.oi_delta_*_pct: Vec<f64>
--       nullable 因為 cold-start backfill 不齊或 5m/15m/1h sliding window
--       不足時，aggregator 寫 NULL（而非 NaN，方便 SQL filter）
--   - source_tier (TEXT) → OIDeltaPanel.source_tier: String
--
-- PK 順序 (snapshot_ts_ms, symbol)：
--   - snapshot_ts_ms 必在前（TimescaleDB hypertable partition column 必在 PK 內）
--   - 25 row per snapshot_ts_ms (一 sym 一 row)；Rust IPC slot pull 時
--     GROUP BY 最新 snapshot_ts_ms 構造 Vec 並對齊 symbols[i]
-- ============================================================
CREATE TABLE IF NOT EXISTS panel.oi_delta_panel (
    snapshot_ts_ms      BIGINT           NOT NULL,
    symbol              TEXT             NOT NULL,
    oi_delta_5m_pct     DOUBLE PRECISION,
    oi_delta_15m_pct    DOUBLE PRECISION,
    oi_delta_1h_pct     DOUBLE PRECISION,
    oi_abs              DOUBLE PRECISION NOT NULL,
    source_tier         TEXT             NOT NULL DEFAULT 'bybit_v5_public',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

-- ============================================================
-- Guard B: oi_delta_5m_pct / 15m_pct / 1h_pct 必為 'double precision'
-- (idempotent: 若 column 不存在 v_actual = NULL 會 silent skip RAISE)
--
-- 為什麼必驗：consumer 端 Rust f64 直 cast；若 NUMERIC / REAL 會 round-trip
-- 精度損失或 type mismatch panic
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='panel' AND table_name='oi_delta_panel'
      AND column_name='oi_delta_5m_pct';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V087 Guard B FAIL: panel.oi_delta_panel.oi_delta_5m_pct '
            'is %, expected double precision. Type drift detected.',
            v_actual;
    END IF;

    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='panel' AND table_name='oi_delta_panel'
      AND column_name='oi_delta_15m_pct';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V087 Guard B FAIL: panel.oi_delta_panel.oi_delta_15m_pct '
            'is %, expected double precision. Type drift detected.',
            v_actual;
    END IF;

    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='panel' AND table_name='oi_delta_panel'
      AND column_name='oi_delta_1h_pct';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V087 Guard B FAIL: panel.oi_delta_panel.oi_delta_1h_pct '
            'is %, expected double precision. Type drift detected.',
            v_actual;
    END IF;

    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='panel' AND table_name='oi_delta_panel'
      AND column_name='oi_abs';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'V087 Guard B FAIL: panel.oi_delta_panel.oi_abs '
            'is %, expected double precision. Type drift detected.',
            v_actual;
    END IF;

    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='panel' AND table_name='oi_delta_panel'
      AND column_name='snapshot_ts_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'V087 Guard B FAIL: panel.oi_delta_panel.snapshot_ts_ms '
            'is %, expected bigint. Type drift detected.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- §3 TimescaleDB hypertable conversion + 14d retention policy
-- (idempotent: pg_extension guard avoid 非 Timescale 環境 fail)
-- chunk_time_interval = 86400000 ms = 1 day
--   per W1 spec §3.2 (對齊 V085 funding_rates_panel chunk size)
-- if_not_exists => TRUE 第二次跑 no-op
--
-- 對齊 V002 既有 pattern line 179-185：用 pg_extension guard 開發環境
-- (Mac mock pytest 通常無 timescaledb extension) friendly，
-- production Linux PG 必有 extension → 進 IF block 跑 hypertable + retention
--
-- 14d retention：paper-only learning window，cold data 自動 drop chunks
-- （aggregator cold-start 重新跑 REST batch 拉 history 即可重 backfill）
-- ============================================================
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable(
        'panel.oi_delta_panel',
        'snapshot_ts_ms',
        chunk_time_interval => 86400000,
        if_not_exists => TRUE
    );

    PERFORM add_retention_policy(
        'panel.oi_delta_panel',
        INTERVAL '14 days',
        if_not_exists => TRUE
    );
END IF;
END $$;

-- ============================================================
-- §4 Hot-path index: 最新 N 秒 snapshot lookup + per-symbol 查詢
-- per W1 spec §3.2
-- (snapshot_ts_ms DESC, symbol) 對齊 healthcheck [58] 與 ML trainer JOIN
-- 兩 query pattern：
--   - healthcheck [58]: SELECT MAX(snapshot_ts_ms) FROM panel.oi_delta_panel
--     (DESC index 直接 leftmost lookup, O(1))
--   - ML trainer: SELECT * FROM panel.oi_delta_panel
--     WHERE snapshot_ts_ms > $1 AND symbol = $2 ORDER BY snapshot_ts_ms DESC
--     (DESC index range scan + symbol secondary filter)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_oi_panel_ts_desc_symbol
    ON panel.oi_delta_panel (snapshot_ts_ms DESC, symbol);

-- ============================================================
-- Guard C: idx_oi_panel_ts_desc_symbol 必含 'snapshot_ts_ms DESC' pattern
-- (idempotent: 若 index 不存在 v_actual = NULL 會 silent skip RAISE)
--
-- 為什麼必驗：legacy mis-applied 可能漏 DESC 或欄位順序顛倒，導致 healthcheck
-- query plan 退化為 full scan
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='panel' AND c.relname='idx_oi_panel_ts_desc_symbol';

    IF v_actual IS NOT NULL AND position('snapshot_ts_ms DESC' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V087 Guard C FAIL: idx_oi_panel_ts_desc_symbol exists but column '
            'list mismatch. Expected to contain "snapshot_ts_ms DESC", actual: %. '
            'DROP INDEX + re-apply V087 to repair.',
            v_actual;
    END IF;

    IF v_actual IS NOT NULL AND position('symbol' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V087 Guard C FAIL: idx_oi_panel_ts_desc_symbol exists but missing '
            'symbol column. Actual: %.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- §5 COMMENT 註解 (idempotent: COMMENT ON 可重跑)
-- ============================================================
COMMENT ON TABLE panel.oi_delta_panel IS
    'W-AUDIT-8a Phase B Tier 2.3 OI delta panel — WS-fed cross-symbol open '
    'interest delta (5m / 15m / 1h). Producer = Rust panel_aggregator/'
    'oi_delta.rs（訂閱既有 WS tickers.{sym} broadcast + cold-start REST batch '
    'backfill）。Consumer = bb_breakout via AlphaSurface.oi_delta_panel slot. '
    '14d retention; cold data auto-drop. PK (snapshot_ts_ms, symbol) 25 row/snapshot.';

COMMENT ON COLUMN panel.oi_delta_panel.snapshot_ts_ms IS
    'Aggregator flush timestamp (ms since epoch). 60s flush window per spec §3.3. '
    '對應 OIDeltaPanel.snapshot_ts_ms: i64.';

COMMENT ON COLUMN panel.oi_delta_panel.oi_abs IS
    'Current open interest absolute value (合約張數). Latest WS broadcast snapshot. '
    'NOT NULL — aggregator 必有 latest oi_abs 才 flush 該 sym (per spec §3.3 buffer 邏輯).';

COMMENT ON COLUMN panel.oi_delta_panel.oi_delta_5m_pct IS
    '5m OI delta percent: (current_oi_abs - oi_baseline_5m_ago) / oi_baseline_5m_ago × 100. '
    'NULL = 5m sliding window 不足或 cold-start backfill 失敗，consumer fail-closed.';

COMMENT ON COLUMN panel.oi_delta_panel.oi_delta_15m_pct IS
    '15m OI delta percent. NULL semantics 同 5m_pct.';

COMMENT ON COLUMN panel.oi_delta_panel.oi_delta_1h_pct IS
    '1h OI delta percent. NULL semantics 同 5m_pct (1h sliding window 通常需 cold-start backfill 完成才齊).';

COMMENT ON COLUMN panel.oi_delta_panel.source_tier IS
    'Provenance tier. Default bybit_v5_public; W-AUDIT-8d hybrid 上線後可寫 '
    'bybit_v5_ws_tickers / bybit_v5_rest_open_interest 區分來源.';

COMMIT;

-- ============================================================
-- §6 Final NOTICE (in transaction-end NOTICE for operator runbook)
-- 注意: COMMIT 之後的 RAISE NOTICE 需在獨立 DO block (PG 限制)
-- ============================================================
DO $$ BEGIN
    RAISE NOTICE 'V087 land complete:';
    RAISE NOTICE '  - panel.oi_delta_panel TimescaleDB hypertable (1d chunk, 14d retention)';
    RAISE NOTICE '  - 6 column: snapshot_ts_ms / symbol / oi_delta_{5m,15m,1h}_pct / oi_abs / source_tier';
    RAISE NOTICE '  - PK (snapshot_ts_ms, symbol); 25 row per snapshot expected';
    RAISE NOTICE '  - Hot-path index idx_oi_panel_ts_desc_symbol (snapshot_ts_ms DESC, symbol)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps (D+1 W1 IMPL):';
    RAISE NOTICE '  - Rust panel_aggregator/oi_delta.rs (WS subscribe + 60s flush + cold-start REST backfill)';
    RAISE NOTICE '  - openclaw_engine/src/ipc_server/slots.rs OIDeltaPanelSlot late-injection';
    RAISE NOTICE '  - step_4_5_dispatch wire (slot read → AlphaSurface.oi_delta_panel borrow)';
    RAISE NOTICE '  - bb_breakout on_tick consume `surface.oi_delta_panel` 真實 wire (B-4 E1-γ)';
    RAISE NOTICE '  - healthcheck [58] PG-side oi_panel freshness (30s WARN / 300s FAIL)';
END $$;
