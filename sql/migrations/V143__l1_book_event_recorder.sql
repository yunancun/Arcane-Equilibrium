-- ============================================================
-- V143: market.l1_events — recorder-v2 full L1 BBO 事件流
--       （L1-BOOK-EVENT-RECORDER，PA 設計 recorder-v2）
--
-- 目的 / Motivation:
--   v1（V142 market.ob_top）是 L1 top-of-book 的 250ms *節流取樣*；且現行
--   parse_orderbook_snapshot 對 orderbook.50 的 delta 把「第一個*變更*檔」誤當
--   top-of-book（campaign-8 14.7% crossed/locked/single-side-zero bad ticks 根因）。
--   recorder-v2 維護有狀態 per-symbol 本地簿（apply snapshot/delta/u==1 reset），
--   解析出真正的 best-bid/best-ask，僅在解析後 BBO 真變化時落盤*每一次*變更——
--   這是 fill-conditional adverse-selection / queue-position 研究所需的完整 BBO
--   事件粒度，與 V142 ob_top（節流取樣）範疇不同。ob_top/trades 不動。
--
--   ⚠️ forward-only：無歷史回填可能（full delta 流先前從未持久化），數據須累積
--      >=10-12 distinct vol/trend regime-days（~2-3 週起）才 research-usable。
--   ⚠️ 本 migration 僅建 schema 表 + hypertable + 壓縮/保留策略。Rust writer 接線、
--      OPENCLAW_RECORD_L1_EVENTS env flag（默認 OFF）、emit 臂全不在本 migration
--      範圍（見 recorder-v2 Rust 改動）。
--
-- 範圍 / Scope (V143):
--   §A market.l1_events CREATE TABLE IF NOT EXISTS + Guard A（9 欄）
--   §B 條件 hypertable（無 TimescaleDB 時跳過，mirror V142/V002）
--   §C 壓縮策略（7 天後壓縮，segmentby symbol，mirror V142/V006）
--   §D 保留策略（21 天，比 ob_top 30d 短，因 full 事件流量級更高）
--      + sync_commit COMMENT
--
-- 編號決策:
--   repo file chain 最高 = V142（V140 缺號、V141 file 尚未 apply 到 prod）。
--   下一個 sqlx file ordinal = V143。sqlx 會在 apply 本 file 前先依序補 apply
--   V141、V142（V142 已 apply 則 no-op）。E1-B 須 ssh trade-core 查 _sqlx_migrations
--   並雙 apply 驗冪等。
--
-- bounded 儲存決策（最 load-bearing）:
--   market.l1_events 是「每一次解析後 BBO 變更」的 full 事件流，*非* full L2.50
--   （full L2.50 = TB/週級，明確拒絕）。三層 bounding：
--   (1) emit-on-change：只有 best_bid|bid_size|best_ask|ask_size 真變化才落盤，
--       deeper-level churn 不產生 row（自然 ~10x 去重）。
--   (2) per-symbol 1s 硬 rate-cap 安全閥（env OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL
--       默認 ~80）：病態 flapping feed 下提供 rows ≤ cap × 37 symbol × 86400 s/day
--       的可證上界。
--   (3) try_send drop-on-full：channel 滿即丟（fail-soft，同 v1）。
--   親算（PA storage_projection）：compressed ~1-2.5 GB/週 realistic，硬上界 ~8.4 GB/週；
--   21d retention 駐留 ~3-7.5 GB realistic，<~26 GB even at hard ceiling（686 GB 卷 < 6%）。
-- ============================================================

-- ==========================================================
-- §A market.l1_events — full L1 BBO 事件流（每一次解析後 BBO 變更）
-- orderbook.50.{symbol} 經有狀態本地簿重建後的 resolved BBO，前向落盤。
-- high volume, loss tolerable。
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.l1_events (
    ts              TIMESTAMPTZ NOT NULL,   -- BBO 變更時戳（delta cts / 撮合引擎時戳，ms）
    symbol          TEXT        NOT NULL,
    best_bid        REAL        NOT NULL,   -- apply 後解析的最高買價
    bid_size        REAL        NOT NULL,   -- best_bid 處量
    best_ask        REAL        NOT NULL,   -- apply 後解析的最低賣價
    ask_size        REAL        NOT NULL,   -- best_ask 處量
    update_id       BIGINT      NOT NULL,   -- Bybit `u`（per-symbol 單調；u==1=reset 標記）
    seq             BIGINT      NOT NULL,   -- Bybit `seq`（cross-sequence，跨檔排序）
    is_snapshot     BOOLEAN     NOT NULL,   -- snapshot/reset frame=true，delta=false
    -- PK = 3-tuple (symbol, ts, update_id)：top-of-book 同毫秒可有多筆 BBO 變更，
    -- (symbol, ts) 2-tuple 會 collide 並 DO NOTHING 靜默丟掉真實變更；update_id 是
    -- per-symbol 天然去重 key。ON CONFLICT DO NOTHING 在多 producer（paper/demo/live
    -- 共用 market_data_tx）下冪等。
    PRIMARY KEY (symbol, ts, update_id)
);

-- TimescaleDB hypertable（條件判斷，無 TimescaleDB 時跳過，mirror V142/V002）
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.l1_events', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- §C 壓縮策略（mirror V142/V006：7 天後壓縮，segmentby symbol）
-- segmentby symbol + delta-encodable ts/update_id + 重複 float 欄 ⇒ columnar ~10x。
-- ==========================================================
ALTER TABLE market.l1_events SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market.l1_events', INTERVAL '7 days', if_not_exists => TRUE);

-- ==========================================================
-- §D 保留策略（21 天，比 ob_top 30d 短：full 事件流量級更高）
-- ==========================================================
SELECT add_retention_policy('market.l1_events', INTERVAL '21 days', if_not_exists => TRUE);

-- ==========================================================
-- sync_commit COMMENT（高頻寫入表，writer 讀此設 session 級 synchronous_commit=off）
-- ==========================================================
COMMENT ON TABLE market.l1_events IS 'sync_commit=off | full L1 BBO event stream — high volume, loss tolerable';

-- ============================================================
-- 驗證 / Verification (double-apply idempotency)
-- ============================================================
-- 重跑本 migration 兩次 → CREATE TABLE IF NOT EXISTS no-op、create_hypertable
-- if_not_exists no-op、add_*_policy if_not_exists no-op，rc=0 冪等。
-- SELECT tablename FROM pg_tables WHERE schemaname = 'market'
--   AND tablename = 'l1_events';  -- 預期 1 行
