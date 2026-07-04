-- ============================================================
-- V142: market.trades + market.ob_top — sub-second 前向錄製
--       （SUBSECOND-TICK-ORDERBOOK-RECORDER，PA 設計 §2）
--
-- 目的 / Motivation:
--   引擎已訂閱並 parse publicTrade.{symbol}（逐筆成交）與 orderbook.50.{symbol}
--   （L2 depth），但現行只把它們聚合成 1m（market.trade_agg_1m / market.ob_snapshots）
--   後丟棄逐筆與 sub-minute 粒度。campaign-3/4 證實 cascade 半衰期 0.3-22s、
--   vol-spillover、liquidity-provision 等 microstructure / Hawkes / maker-spread
--   研究恰恰需要被聚合丟棄的 sub-second 粒度。本表前向落盤這兩條既有資料流。
--
--   ⚠️ forward-only：無歷史回填可能，數據須累積數週才 research-usable。
--   ⚠️ 本 migration 僅建 schema 表 + hypertable + 壓縮/保留策略。Rust writer 接線、
--      OPENCLAW_RECORD_TICKS env flag、emit 臂全不在本 migration 範圍（見 E1-A Rust 改動）。
--
-- SOURCE: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-16--PA--subsecond-tick-orderbook-recorder-design.md §2
--
-- 範圍 / Scope (V142):
--   §A market.trades CREATE TABLE IF NOT EXISTS（per-trade tape，5 欄）
--   §B market.ob_top CREATE TABLE IF NOT EXISTS（L1 top-of-book sampled，6 欄）
--   §C 條件 hypertable（無 TimescaleDB 時跳過，mirror V002）
--   §D 壓縮 + 保留策略 + sync_commit COMMENT（mirror V006）
--   ⚠️ 誠實更正（2026-07-04 P2-11 ①）：本檔 body 從未含 Guard A DO-block（header
--   原聲稱有）。兩表的必要欄 Guard A 反射由 V148__recorder_promotions_guard_retrofit
--   補齊；本 header 修正屬 governance 措辭訂正，checksum 漂移由
--   bin/repair_migration_checksum 處理（不手改 _sqlx_migrations）。
--
-- 編號決策:
--   prod _sqlx_migrations 最高 = 139；本 repo file chain 最高 = V141（V140 缺號、
--   V141 file 尚未 apply 到 prod）。下一個 sqlx file ordinal = V142（sqlx 會在
--   apply 本 file 前先補 apply V141）。E1-B 已 ssh trade-core 查 _sqlx_migrations 證實。
--
-- bounded 儲存決策（最 load-bearing）:
--   market.ob_top 是 L1 top-of-book *取樣*（默認 250ms gate / 有意義變化才 emit），
--   *非* full L2.50。full L2.50 全 rate × 153 symbol = TB/週級，明確拒絕。
--   L1 sampled = 補回現行 ObAggregator（每分鐘只留最後一筆）丟棄的 sub-minute
--   spread/queue 動態，足夠做 maker-spread / queue 研究，又把寫入量壓到 ~100x 更小。
--   親算（PA §2.3）：兩表 compressed ~15-25 GB/月，retention 30-45d raw 後 drop，
--   穩態駐留 < 40 GB（686 GB 卷下 < 6%）。
-- ============================================================

-- ==========================================================
-- §A market.trades — per-trade tape（逐筆成交）
-- publicTrade.{symbol} 每筆成交，前向落盤。high volume, loss tolerable。
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.trades (
    ts              TIMESTAMPTZ NOT NULL,   -- 成交毫秒時戳（PriceEvent.ts_ms）
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,   -- Buy/Sell（trade_side / taker 方向）
    price           REAL        NOT NULL,   -- last_price
    qty             REAL        NOT NULL,   -- trade_qty
    -- PK = 5-tuple，鏡像 market.liquidations 去重慣例：同毫秒同價多筆成交合法，
    -- 5-tuple 才不誤併真實 tape；ON CONFLICT DO NOTHING 冪等去重。
    PRIMARY KEY (symbol, ts, side, price, qty)
);

-- TimescaleDB hypertable（條件判斷，無 TimescaleDB 時跳過，mirror V002）
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.trades', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- §B market.ob_top — L1 top-of-book sampled（取樣）
-- orderbook.50.{symbol} 的最優買賣一檔，取樣節流後落盤。BOUNDED：非 full L2.50。
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.ob_top (
    ts              TIMESTAMPTZ NOT NULL,   -- 取樣時戳
    symbol          TEXT        NOT NULL,
    best_bid        REAL        NOT NULL,   -- bids5[0].0
    bid_size        REAL        NOT NULL,   -- bids5[0].1
    best_ask        REAL        NOT NULL,   -- asks5[0].0
    ask_size        REAL        NOT NULL,   -- asks5[0].1
    -- PK = (symbol, ts)：取樣節流保證同 symbol 相鄰 ts 間隔 ≥ ~250ms，
    -- 2-tuple 足以去重；ON CONFLICT DO NOTHING 冪等。
    PRIMARY KEY (symbol, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.ob_top', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- §C 壓縮策略（mirror V006：7 天後壓縮，segmentby symbol）
-- ==========================================================
ALTER TABLE market.trades SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market.trades', INTERVAL '7 days', if_not_exists => TRUE);

ALTER TABLE market.ob_top SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market.ob_top', INTERVAL '7 days', if_not_exists => TRUE);

-- ==========================================================
-- §D 保留策略（量級高，比 1m 表 90d 短：trades 45d / ob_top 30d）
-- ==========================================================
SELECT add_retention_policy('market.trades', INTERVAL '45 days', if_not_exists => TRUE);
SELECT add_retention_policy('market.ob_top', INTERVAL '30 days', if_not_exists => TRUE);

-- ==========================================================
-- sync_commit COMMENT（高頻寫入表，writer 讀此設 session 級 synchronous_commit=off）
-- ==========================================================
COMMENT ON TABLE market.trades IS 'sync_commit=off | per-trade tape — high volume, loss tolerable';
COMMENT ON TABLE market.ob_top IS 'sync_commit=off | L1 top-of-book sampled — high volume, loss tolerable';

-- ============================================================
-- 驗證 / Verification (double-apply idempotency)
-- ============================================================
-- 重跑本 migration 兩次 → CREATE TABLE IF NOT EXISTS no-op、create_hypertable
-- if_not_exists no-op、add_*_policy if_not_exists no-op，rc=0 冪等。
-- SELECT tablename FROM pg_tables WHERE schemaname = 'market'
--   AND tablename IN ('trades','ob_top') ORDER BY tablename;  -- 預期 2 行
