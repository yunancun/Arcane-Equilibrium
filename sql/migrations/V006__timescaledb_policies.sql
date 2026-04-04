-- ============================================================
-- Phase 0b — TimescaleDB Compression + Retention Policies
-- Phase 0b — TimescaleDB 壓縮 + 保留策略
-- Executed: 2026-04-04
-- ============================================================
--
-- Compression: auto-compress old chunks to save storage.
-- Retention: auto-drop chunks older than threshold.
-- sync_commit: per-table hint (applied at session level by writers).
--
-- Design rationale / 設計理由:
--   Market high-volume: compress 7d, retain 90d (cold archive on NAS)
--   Klines: compress 14d, retain 365d (backtesting needs)
--   Trading: compress 14d, retain 180-365d (learning pipeline)
--   Obs/Risk: retain 90d (lightweight, regenerable)
-- ============================================================

-- ==================== Compression Policies ====================
-- 壓縮策略

-- Market tables: compress after 7 days / 市場表：7 天後壓縮
ALTER TABLE market.market_tickers SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market.market_tickers', INTERVAL '7 days', if_not_exists => TRUE);

ALTER TABLE market.ob_snapshots SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market.ob_snapshots', INTERVAL '7 days', if_not_exists => TRUE);

ALTER TABLE market.trade_agg_1m SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market.trade_agg_1m', INTERVAL '7 days', if_not_exists => TRUE);

ALTER TABLE market.klines SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol, timeframe');
SELECT add_compression_policy('market.klines', INTERVAL '14 days', if_not_exists => TRUE);

ALTER TABLE market.liquidations SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market.liquidations', INTERVAL '7 days', if_not_exists => TRUE);

-- Trading tables: compress after 14 days / 交易表：14 天後壓縮
ALTER TABLE trading.signals SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('trading.signals', INTERVAL '14 days', if_not_exists => TRUE);

ALTER TABLE trading.intents SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('trading.intents', INTERVAL '14 days', if_not_exists => TRUE);

ALTER TABLE trading.fills SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('trading.fills', INTERVAL '14 days', if_not_exists => TRUE);

ALTER TABLE trading.orders SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('trading.orders', INTERVAL '14 days', if_not_exists => TRUE);

-- ==================== Retention Policies ====================
-- 保留策略（超過閾值的 chunks 自動刪除）

-- Market high-volume: 90 days / 市場高頻：90 天
SELECT add_retention_policy('market.market_tickers', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('market.ob_snapshots', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('market.trade_agg_1m', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('market.liquidations', INTERVAL '90 days', if_not_exists => TRUE);

-- Klines: 1 year (backtesting) / K 線：1 年（回測需要）
SELECT add_retention_policy('market.klines', INTERVAL '365 days', if_not_exists => TRUE);

-- Funding/OI/LS: 180 days / 資金費率/未平倉/多空比：180 天
SELECT add_retention_policy('market.funding_rates', INTERVAL '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('market.open_interest', INTERVAL '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('market.long_short_ratio', INTERVAL '180 days', if_not_exists => TRUE);

-- Trading signals/intents: 180 days / 交易信號/意圖：180 天
SELECT add_retention_policy('trading.signals', INTERVAL '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('trading.intents', INTERVAL '180 days', if_not_exists => TRUE);

-- Trading fills/orders: 1 year (audit + learning) / 交易成交/訂單：1 年
SELECT add_retention_policy('trading.fills', INTERVAL '365 days', if_not_exists => TRUE);
SELECT add_retention_policy('trading.orders', INTERVAL '365 days', if_not_exists => TRUE);

-- Observability: 90 days / 可觀測性：90 天
SELECT add_retention_policy('observability.data_quality_events', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('observability.drift_events', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('observability.scorer_predictions', INTERVAL '90 days', if_not_exists => TRUE);

-- ==================== sync_commit Tiering ====================
-- 同步提交分層（高頻寫入表用 off，關鍵交易表用 on）

-- Database default: synchronous / 數據庫默認：同步
ALTER DATABASE trading_ai SET synchronous_commit = 'on';

-- Table-level hints via COMMENT (application code reads this for session-level setting)
-- 表級提示通過 COMMENT（應用代碼讀取此設置用於 session 級別）
COMMENT ON TABLE market.market_tickers IS 'sync_commit=off | 5s ticker snapshots — high volume, loss tolerable';
COMMENT ON TABLE market.ob_snapshots IS 'sync_commit=off | L5 1-min OB summary — high volume, loss tolerable';
COMMENT ON TABLE market.trade_agg_1m IS 'sync_commit=off | 1-min agg trades — high volume, loss tolerable';
COMMENT ON TABLE trading.signals IS 'sync_commit=off | trading signals — reproducible from indicators';
COMMENT ON TABLE trading.fills IS 'sync_commit=on | fills — critical trading data, must not lose';
COMMENT ON TABLE trading.orders IS 'sync_commit=on | orders — critical trading data, must not lose';
