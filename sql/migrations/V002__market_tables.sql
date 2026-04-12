-- ============================================================
-- Phase 0a DDL — 已執行 / Executed
-- 設計來源：融合方案 v0.5 + DB 架構 V1
-- Source: Unified Work Plan v0.5 + DB Architecture V1
-- 執行日期：2026-04-11 · FIX-35: DRAFT 標記移除
-- Execution date: 2026-04-11 · FIX-35: DRAFT marker removed
-- ============================================================
--
-- V002: market.* Tables
-- 市場數據表（含 TimescaleDB hypertable 語句）
-- Market data tables (with TimescaleDB hypertable statements)
--
-- 表清單 / Table List:
--   market.market_tickers     — 5s 行情快照（替代 raw_ticks）/ 5s ticker snapshots
--   market.ob_snapshots       — L5 1m orderbook summary / L5 1-min OB summary
--   market.trade_agg_1m       — 分鐘聚合成交 / 1-min aggregated trades
--   market.klines             — K 線 OHLCV / Candlestick OHLCV
--   market.funding_rates      — 資金費率 / Funding rates
--   market.open_interest      — 未平倉合約 / Open interest
--   market.long_short_ratio   — 多空比 / Long-short ratio
--   market.liquidations       — 清算事件 / Liquidation events
--   market.regime_snapshots   — Regime 快照 / Regime snapshots
--   market.regime_transitions — Regime 轉換 / Regime transitions
--   market.news_signals       — 新聞信號 / News signals
--
-- 設計決策 / Design Decisions:
--   - v0.5 存儲精簡：raw_ticks→market_tickers 5s / orderbook L25→ob L5 1m / raw trades→agg 1m
--   - PK 包含時間列（TimescaleDB 要求）
--   - 使用 REAL 而非 NUMERIC（ML 友好，精度足夠）
-- ============================================================

-- ==========================================================
-- market.market_tickers — 5s 行情快照
-- 5-second ticker snapshots (replaces raw_ticks, 97% storage reduction)
-- 來源：v0.5 §10.3 · ~50 MB/day
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.market_tickers (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    last_price      REAL,
    mark_price      REAL,
    index_price     REAL,
    best_bid        REAL,
    best_ask        REAL,
    bid_size        REAL,
    ask_size        REAL,
    volume_24h      REAL,
    turnover_24h    REAL,
    spread_bps      REAL,       -- (ask - bid) / mid * 10000
    open_interest   REAL,
    PRIMARY KEY (symbol, ts)
);

-- TimescaleDB hypertable（條件判斷，無 TimescaleDB 時跳過）
-- Conditional hypertable creation (skipped if TimescaleDB not installed)
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.market_tickers', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.ob_snapshots — L5 1m orderbook summary
-- 每分鐘 orderbook L5 匯總（替代 L25 每秒，減 99.7%）
-- Source: v0.5 §10.3 · ~6 MB/day
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.ob_snapshots (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    imbalance_ratio REAL,       -- bid_depth / (bid + ask)
    weighted_mid    REAL,       -- 加權中間價 / weighted mid price
    spread_bps      REAL,
    bid_depth_5     REAL,       -- sum of top 5 bid sizes
    ask_depth_5     REAL,       -- sum of top 5 ask sizes
    depth_ratio     REAL,       -- bid_depth_5 / ask_depth_5
    PRIMARY KEY (symbol, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.ob_snapshots', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.trade_agg_1m — 分鐘聚合成交
-- 1-minute aggregated public trades (replaces raw trade tape, 99.7% reduction)
-- Source: v0.5 §10.3 · ~5 MB/day
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.trade_agg_1m (
    ts              TIMESTAMPTZ NOT NULL,   -- 分鐘開始時間 / minute start
    symbol          TEXT        NOT NULL,
    buy_volume      REAL,
    sell_volume     REAL,
    buy_count       INT,
    sell_count      INT,
    large_buy_count INT,        -- 大單計數（> threshold）/ large order count
    large_sell_count INT,
    vwap            REAL,       -- 成交量加權均價 / volume-weighted avg price
    max_single_qty  REAL,       -- 分鐘內最大單筆 / max single trade qty
    PRIMARY KEY (symbol, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.trade_agg_1m', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.klines — K 線 OHLCV（所有時間框架）
-- Candlestick OHLCV (all timeframes)
-- Source: DB-1 · 永久保留 / permanent retention · ~14 MB/day
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.klines (
    ts              TIMESTAMPTZ NOT NULL,   -- bar open time
    open_ts_ms      BIGINT,                 -- 精確開盤毫秒 / exact open ms
    close_ts_ms     BIGINT,                 -- 精確收盤毫秒 / exact close ms
    symbol          TEXT        NOT NULL,
    timeframe       TEXT        NOT NULL,   -- 1m/5m/15m/30m/1h/4h/1d
    open            REAL        NOT NULL,
    high            REAL        NOT NULL,
    low             REAL        NOT NULL,
    close           REAL        NOT NULL,
    volume          REAL,
    turnover        REAL,
    tick_count      INT,
    PRIMARY KEY (symbol, timeframe, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.klines', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.funding_rates — 資金費率（永久保留）
-- Funding rates (permanent retention)
-- Source: DB-1 · REST 定時 15m / REST polling every 15m
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.funding_rates (
    ts              TIMESTAMPTZ NOT NULL,   -- funding timestamp
    symbol          TEXT        NOT NULL,
    funding_rate    REAL        NOT NULL,
    funding_rate_daily REAL,                -- annualized / 365 or daily
    PRIMARY KEY (symbol, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.funding_rates', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.open_interest — 未平倉合約（永久保留）
-- Open interest (permanent retention)
-- Source: DB-1 · REST 定時 5m / REST polling every 5m
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.open_interest (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    open_interest   REAL        NOT NULL,
    oi_value        REAL,                   -- OI in USDT
    PRIMARY KEY (symbol, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.open_interest', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.long_short_ratio — 多空比（永久保留）
-- Long-short ratio (permanent retention)
-- Source: DB-1 · REST 定時 15m
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.long_short_ratio (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    buy_ratio       REAL,       -- 多頭比例 / long ratio
    sell_ratio      REAL,       -- 空頭比例 / short ratio
    ratio           REAL,       -- buy_ratio / sell_ratio
    PRIMARY KEY (symbol, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.long_short_ratio', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.liquidations — 清算事件（保留 1 年）
-- Liquidation events (1 year retention)
-- Source: DB-1 · WS 訂閱 liquidation.{symbol}
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.liquidations (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,   -- Buy/Sell（被清算方向）
    qty             REAL        NOT NULL,
    price           REAL        NOT NULL,
    PRIMARY KEY (symbol, ts, side)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.liquidations', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.regime_snapshots — Regime 快照（永久保留）
-- Market regime snapshots (permanent retention)
-- Source: DB-1 · market_regime.py
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.regime_snapshots (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    timeframe       TEXT        NOT NULL,   -- 5m/15m/1h/4h
    regime          TEXT        NOT NULL,   -- TRENDING_UP/DOWN/RANGING/SQUEEZE/HIGH_VOL/LOW_VOL/BREAKOUT/REVERSAL
    confidence      REAL,                   -- 0.0 ~ 1.0
    details         JSONB,                  -- 額外指標 / additional metrics
    PRIMARY KEY (symbol, timeframe, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.regime_snapshots', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.regime_transitions — Regime 轉換記錄（永久保留）
-- Market regime transition log (permanent retention)
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.regime_transitions (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    timeframe       TEXT        NOT NULL,
    from_regime     TEXT        NOT NULL,
    to_regime       TEXT        NOT NULL,
    trigger_reason  TEXT,                   -- 觸發原因 / trigger reason
    details         JSONB,
    PRIMARY KEY (symbol, timeframe, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.regime_transitions', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- market.news_signals — 新聞信號（永久保留，年均 <100MB）
-- News signals (permanent retention, <100MB/year)
-- Source: 融合方案 v0.5 §三 · 7d chunk（日均 <20 行）
-- ==========================================================
CREATE TABLE IF NOT EXISTS market.news_signals (
    signal_id       BIGSERIAL,
    ts              TIMESTAMPTZ NOT NULL,
    receive_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          TEXT        NOT NULL,   -- RSS/API/scraper name
    source_url      TEXT,
    severity        REAL        NOT NULL CHECK (severity BETWEEN 0 AND 1),
    severity_source TEXT,                   -- 產出 severity 的 AI 模型 / AI model that produced severity
    category        TEXT        NOT NULL,   -- macro/exchange/regulatory/listing/hack/...
    affected_symbols TEXT[]     NOT NULL DEFAULT '{}',
    is_market_wide  BOOLEAN     DEFAULT FALSE,
    sentiment       REAL        CHECK (sentiment BETWEEN -1 AND 1),
    confidence      REAL        CHECK (confidence BETWEEN 0 AND 1),
    summary         TEXT        NOT NULL,
    raw_content     TEXT,
    ai_model_used   TEXT,
    processing_cost_usd NUMERIC(10,6) DEFAULT 0,
    attributed_trade_count INTEGER DEFAULT 0,
    PRIMARY KEY (signal_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('market.news_signals', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ============================================================
-- 驗證 / Verification
-- ============================================================
-- SELECT tablename FROM pg_tables WHERE schemaname = 'market' ORDER BY tablename;
-- 預期 11 tables:
--   funding_rates, klines, liquidations, long_short_ratio,
--   market_tickers, news_signals, ob_snapshots, open_interest,
--   regime_snapshots, regime_transitions, trade_agg_1m
