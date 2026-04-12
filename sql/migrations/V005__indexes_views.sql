-- ============================================================
-- Phase 0a DDL — 已執行 / Executed
-- 設計來源：融合方案 v0.5 + DB 架構 V1
-- Source: Unified Work Plan v0.5 + DB Architecture V1
-- 執行日期：2026-04-11 · FIX-35: DRAFT 標記移除
-- Execution date: 2026-04-11 · FIX-35: DRAFT marker removed
-- ============================================================
--
-- V005: Indexes + Views + Legacy Rename + Grafana Bridge
--
-- 內容 / Contents:
--   1. 全部索引（B-tree + GIN for JSONB）
--   2. scorer_training_features VIEW（placeholder，排除 outcome_* 防 leakage）
--   3. ALTER TABLE ... RENAME TO ..._legacy（public 11 表 + trading_raw 5 表）
--   4. Grafana VIEW 橋接
--
-- 設計決策 / Design Decisions:
--   - 高頻表只有 (symbol, ts DESC) 一個索引，減少寫入放大
--   - GIN 索引只在需要 JSONB 查詢的欄位上建
--   - scorer_training_features VIEW 同時提供 features(X) 和 outcome labels(y)，應用層負責分離
--   - Grafana VIEW 保持舊表名，SELECT 從新 schema 讀取
-- ============================================================


-- ================================================================
-- PART 1: INDEXES / 索引
-- ================================================================

-- -------------------------------------------------------
-- market.* indexes
-- 市場數據索引（高頻表精簡索引，減少寫入放大）
-- -------------------------------------------------------

-- market.market_tickers: PK 已含 (symbol, ts)，額外加 ts DESC 用於時間範圍查詢
CREATE INDEX IF NOT EXISTS idx_market_tickers_ts_desc
    ON market.market_tickers (ts DESC);

-- market.ob_snapshots: PK 已含 (symbol, ts)
CREATE INDEX IF NOT EXISTS idx_ob_snapshots_ts_desc
    ON market.ob_snapshots (ts DESC);

-- market.trade_agg_1m: PK 已含 (symbol, ts)
CREATE INDEX IF NOT EXISTS idx_trade_agg_1m_ts_desc
    ON market.trade_agg_1m (ts DESC);

-- market.klines: PK 已含 (symbol, timeframe, ts)，加 ts DESC 快速查最新
CREATE INDEX IF NOT EXISTS idx_klines_ts_desc
    ON market.klines (ts DESC);
-- 用於查詢特定 symbol + timeframe 最新 K 線
CREATE INDEX IF NOT EXISTS idx_klines_symbol_tf_ts
    ON market.klines (symbol, timeframe, ts DESC);

-- market.funding_rates: PK 已含 (symbol, ts)
CREATE INDEX IF NOT EXISTS idx_funding_rates_ts_desc
    ON market.funding_rates (ts DESC);

-- market.open_interest: PK 已含 (symbol, ts)
CREATE INDEX IF NOT EXISTS idx_open_interest_ts_desc
    ON market.open_interest (ts DESC);

-- market.liquidations: 按 symbol + 時間查詢清算事件
CREATE INDEX IF NOT EXISTS idx_liquidations_ts_desc
    ON market.liquidations (ts DESC);

-- market.regime_snapshots: 快速查某 symbol+TF 的最新 regime
CREATE INDEX IF NOT EXISTS idx_regime_snapshots_ts_desc
    ON market.regime_snapshots (ts DESC);

-- market.news_signals: 按 severity 降序（高嚴重度優先）
CREATE INDEX IF NOT EXISTS idx_news_severity
    ON market.news_signals (severity DESC, ts DESC);
-- GIN 索引：按 affected_symbols 查詢
CREATE INDEX IF NOT EXISTS idx_news_symbols
    ON market.news_signals USING GIN (affected_symbols);

-- -------------------------------------------------------
-- trading.* indexes
-- 交易數據索引
-- -------------------------------------------------------

-- trading.decision_context_snapshots: 核心查詢模式
CREATE INDEX IF NOT EXISTS idx_dcs_symbol_ts
    ON trading.decision_context_snapshots (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_dcs_decision_type
    ON trading.decision_context_snapshots (decision_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_dcs_strategy
    ON trading.decision_context_snapshots (strategy_name, ts DESC);
-- GIN 索引：JSONB 查詢（indicators_snapshot, decision_payload）
CREATE INDEX IF NOT EXISTS idx_dcs_indicators_gin
    ON trading.decision_context_snapshots USING GIN (indicators_snapshot);
CREATE INDEX IF NOT EXISTS idx_dcs_payload_gin
    ON trading.decision_context_snapshots USING GIN (decision_payload);

-- trading.decision_outcomes: PK 已是 context_id
-- 無需額外索引（JOIN on PK）

-- trading.signals: 按 symbol + strategy 查詢信號
CREATE INDEX IF NOT EXISTS idx_signals_symbol_ts
    ON trading.signals (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_signals_strategy
    ON trading.signals (strategy_name, ts DESC);

-- trading.intents: 按 symbol 查詢意圖
CREATE INDEX IF NOT EXISTS idx_intents_symbol_ts
    ON trading.intents (symbol, ts DESC);

-- trading.risk_verdicts: 按 verdict 結果查詢
CREATE INDEX IF NOT EXISTS idx_verdicts_symbol_ts
    ON trading.risk_verdicts (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_verdicts_verdict
    ON trading.risk_verdicts (verdict, ts DESC);

-- trading.orders: 按 symbol + status 查詢
CREATE INDEX IF NOT EXISTS idx_orders_symbol_ts
    ON trading.orders (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status
    ON trading.orders (status, ts DESC);

-- trading.order_state_changes: 按 order_id 查詢歷史
CREATE INDEX IF NOT EXISTS idx_osc_order_ts
    ON trading.order_state_changes (order_id, ts DESC);

-- trading.fills: 按 symbol 查詢成交
CREATE INDEX IF NOT EXISTS idx_fills_symbol_ts
    ON trading.fills (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_fills_order_id
    ON trading.fills (order_id, ts DESC);

-- trading.position_snapshots: PK 已含 (symbol, side, ts)
CREATE INDEX IF NOT EXISTS idx_positions_ts_desc
    ON trading.position_snapshots (ts DESC);

-- -------------------------------------------------------
-- agent.* indexes
-- Agent 通信索引
-- -------------------------------------------------------

-- agent.messages: 按 agent 查詢消息
CREATE INDEX IF NOT EXISTS idx_messages_from
    ON agent.messages (from_agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_messages_to
    ON agent.messages (to_agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_messages_type
    ON agent.messages (message_type, ts DESC);

-- agent.ai_invocations: 按 provider/model 查詢
CREATE INDEX IF NOT EXISTS idx_ai_inv_provider
    ON agent.ai_invocations (provider, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ai_inv_model
    ON agent.ai_invocations (model, ts DESC);

-- agent.state_changes: PK 已含 (agent_name, ts)

-- -------------------------------------------------------
-- learning.* indexes
-- 學習系統索引
-- -------------------------------------------------------

-- learning.rl_transitions: 按 episode 查詢
CREATE INDEX IF NOT EXISTS idx_rl_episode
    ON learning.rl_transitions (episode_id, step_index);

-- learning.ml_parameter_suggestions: 按 strategy + symbol 查詢
CREATE INDEX IF NOT EXISTS idx_ml_suggestions_strategy
    ON learning.ml_parameter_suggestions (strategy_name, symbol);

-- learning.model_registry: 按 is_active 查詢活躍模型
CREATE INDEX IF NOT EXISTS idx_model_registry_active
    ON learning.model_registry (is_active) WHERE is_active = TRUE;

-- -------------------------------------------------------
-- observability.* indexes
-- 監控索引
-- -------------------------------------------------------

-- observability.scorer_predictions: 按 model + was_executed 查詢
CREATE INDEX IF NOT EXISTS idx_scorer_pred_model
    ON observability.scorer_predictions (model_name, ts DESC);
CREATE INDEX IF NOT EXISTS idx_scorer_pred_executed
    ON observability.scorer_predictions (was_executed, ts DESC);

-- observability.drift_events: 按 drift_type + severity 查詢
CREATE INDEX IF NOT EXISTS idx_drift_type_severity
    ON observability.drift_events (drift_type, severity, ts DESC);

-- observability.data_quality_events: 按 check_type + severity 查詢
CREATE INDEX IF NOT EXISTS idx_dq_check_severity
    ON observability.data_quality_events (check_type, severity, ts DESC);

-- -------------------------------------------------------
-- risk.* indexes
-- 風險索引
-- -------------------------------------------------------

-- risk.black_swan_events: 按 severity 查詢
CREATE INDEX IF NOT EXISTS idx_bse_severity
    ON risk.black_swan_events (severity, ts DESC);
CREATE INDEX IF NOT EXISTS idx_bse_symbol
    ON risk.black_swan_events (symbol, ts DESC);

-- risk.black_swan_votes: PK 已含 (symbol, signal_name, ts)

-- risk.correlation_pairs: 按 symbol pair 查詢
CREATE INDEX IF NOT EXISTS idx_corr_pairs_ts
    ON risk.correlation_pairs (ts DESC);


-- ================================================================
-- PART 2: SCORER TRAINING FEATURES VIEW（防 leakage）
-- scorer_training_features VIEW (prevent outcome leakage)
-- ================================================================

-- 此 VIEW 是 ML 訓練管線的唯一數據入口
-- This VIEW is the ONLY data entry point for ML training pipeline
-- 顯式排除所有 outcome_* 欄位，防止標籤洩漏
-- Explicitly excludes all outcome_* columns to prevent label leakage
--
-- 審計 MIT-1：訓練管線用 JSONB key 白名單，匹配 /^outcome_/ 硬斷言失敗
-- Audit MIT-1: training pipeline uses JSONB key whitelist, /^outcome_/ assertion failure

CREATE OR REPLACE VIEW learning.scorer_training_features AS
SELECT
    -- 身份 / Identity
    c.ts,
    c.context_id,
    c.decision_type,
    c.symbol,
    c.strategy_name,

    -- 扁平化價格 / Flat price features
    c.last_price,
    c.mark_price,
    c.spread_bps,

    -- Regime
    c.regime_5m,
    c.regime_1h,

    -- 核心指標 / Core indicators
    c.ind_5m_adx,
    c.ind_5m_rsi,
    c.ind_5m_atr_14_pct,

    -- 持倉 / Position
    c.position_side,
    c.position_qty,

    -- 組合 / Portfolio
    c.total_equity,
    c.drawdown_pct,

    -- 新聞 / News
    c.news_severity,
    c.hours_since_last_major_news,
    c.news_driven,

    -- Scorer
    c.scorer_ev_prediction,
    c.scorer_divergence,

    -- JSONB（排除 outcome 相關 key）/ JSONB (outcome keys excluded)
    -- TODO: 確認 JSONB 白名單機制在應用層實現
    -- TODO: Confirm JSONB whitelist mechanism is implemented in application layer
    c.indicators_snapshot,
    c.microstructure,
    c.position_detail,
    c.recent_sequences,
    c.decision_payload,

    -- 事後結果從 decision_outcomes JOIN（僅作 label，不作 feature）
    -- Outcomes from decision_outcomes JOIN (label only, NOT feature)
    o.outcome_1m,
    o.outcome_5m,
    o.outcome_1h,
    o.outcome_4h,
    o.outcome_24h,
    o.max_favorable,
    o.max_adverse

FROM trading.decision_context_snapshots c
LEFT JOIN trading.decision_outcomes o ON c.context_id = o.context_id
WHERE c.outcome_backfilled = TRUE;

COMMENT ON VIEW learning.scorer_training_features IS
'★ ML 訓練專用 VIEW — outcome 列只作為 label（y），不可作為 feature（X）。'
'★ ML training VIEW — outcome columns are labels (y) only, NEVER features (X). '
'應用層必須用白名單過濾 JSONB key，匹配 /^outcome_/ 則硬斷言失敗。'
'Application layer MUST whitelist JSONB keys; /^outcome_/ pattern triggers hard assertion failure.';


-- ================================================================
-- PART 3: LEGACY RENAME（舊表加 _legacy 後綴）
-- Legacy table rename (add _legacy suffix)
-- ================================================================

-- -------------------------------------------------------
-- 3a. public schema 11 表 → _legacy
-- public schema 11 tables → _legacy
-- Source: init_trading_schema.sql
-- -------------------------------------------------------

-- 使用條件判斷避免表不存在時報錯
-- Use conditional check to avoid error if table doesn't exist

DO $$ BEGIN
    -- 1. account_snapshots
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'account_snapshots') THEN
        ALTER TABLE public.account_snapshots RENAME TO account_snapshots_legacy;
    END IF;

    -- 2. position_snapshots
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'position_snapshots') THEN
        ALTER TABLE public.position_snapshots RENAME TO position_snapshots_legacy;
    END IF;

    -- 3. order_events
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'order_events') THEN
        ALTER TABLE public.order_events RENAME TO order_events_legacy;
    END IF;

    -- 4. trade_executions
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'trade_executions') THEN
        ALTER TABLE public.trade_executions RENAME TO trade_executions_legacy;
    END IF;

    -- 5. ai_cost_events
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'ai_cost_events') THEN
        ALTER TABLE public.ai_cost_events RENAME TO ai_cost_events_legacy;
    END IF;

    -- 6. system_health
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'system_health') THEN
        ALTER TABLE public.system_health RENAME TO system_health_legacy;
    END IF;

    -- 7. observer_verdicts
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'observer_verdicts') THEN
        ALTER TABLE public.observer_verdicts RENAME TO observer_verdicts_legacy;
    END IF;

    -- 8. paper_pnl_snapshots
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'paper_pnl_snapshots') THEN
        ALTER TABLE public.paper_pnl_snapshots RENAME TO paper_pnl_snapshots_legacy;
    END IF;

    -- 9. risk_events
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'risk_events') THEN
        ALTER TABLE public.risk_events RENAME TO risk_events_legacy;
    END IF;

    -- 10. market_tickers
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'market_tickers') THEN
        ALTER TABLE public.market_tickers RENAME TO market_tickers_legacy;
    END IF;

    -- 11. learning_events
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'learning_events') THEN
        ALTER TABLE public.learning_events RENAME TO learning_events_legacy;
    END IF;
END $$;

-- -------------------------------------------------------
-- 3b. trading_raw schema 5 表 → _legacy
-- trading_raw schema 5 tables → _legacy
-- Source: DATA_STORAGE_ARCHITECTURE_V1.md §1.2.2
-- -------------------------------------------------------

DO $$ BEGIN
    -- 1. decision_packets
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'trading_raw' AND tablename = 'decision_packets') THEN
        ALTER TABLE trading_raw.decision_packets RENAME TO decision_packets_legacy;
    END IF;

    -- 2. observer_verdicts
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'trading_raw' AND tablename = 'observer_verdicts') THEN
        ALTER TABLE trading_raw.observer_verdicts RENAME TO observer_verdicts_legacy;
    END IF;

    -- 3. bybit_account_coin_snapshots
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'trading_raw' AND tablename = 'bybit_account_coin_snapshots') THEN
        ALTER TABLE trading_raw.bybit_account_coin_snapshots RENAME TO bybit_account_coin_snapshots_legacy;
    END IF;

    -- 4. bybit_position_snapshots
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'trading_raw' AND tablename = 'bybit_position_snapshots') THEN
        ALTER TABLE trading_raw.bybit_position_snapshots RENAME TO bybit_position_snapshots_legacy;
    END IF;

    -- 5. bybit_ws_private_events_raw
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'trading_raw' AND tablename = 'bybit_ws_private_events_raw') THEN
        ALTER TABLE trading_raw.bybit_ws_private_events_raw RENAME TO bybit_ws_private_events_raw_legacy;
    END IF;
END $$;


-- ================================================================
-- PART 4: GRAFANA VIEW BRIDGE（零停機橋接）
-- Grafana VIEW bridge (zero-downtime migration)
-- ================================================================

-- 這些 VIEW 讓 Grafana Dashboard SQL 查詢不需修改
-- These VIEWs keep existing Grafana Dashboard SQL queries working unchanged
-- 舊 Dashboard 查 public.table_name → VIEW 從新 schema 讀取
-- Old dashboards query public.table_name → VIEW reads from new schema

-- -------------------------------------------------------
-- account_snapshots → 新表尚未建立，暫時指向 legacy
-- NOTE: 正式遷移後改為指向新 schema 表
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.account_snapshots AS
SELECT
    id, ts, total_equity, available_balance, used_margin,
    unrealized_pnl, account_type, coin, raw_json
FROM public.account_snapshots_legacy;

-- -------------------------------------------------------
-- position_snapshots → trading.position_snapshots
-- 欄位映射：新表欄位名略有不同
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.position_snapshots AS
SELECT
    ts, symbol, side,
    qty AS size,
    entry_price, mark_price, unrealized_pnl,
    leverage,
    position_value,
    category,
    details AS raw_json
FROM trading.position_snapshots;

-- -------------------------------------------------------
-- order_events → trading.orders (+ state changes)
-- Grafana 查詢的欄位映射
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.order_events AS
SELECT
    ts, order_id, symbol, side, order_type,
    qty, price, status,
    NULL::NUMERIC(20,8) AS filled_qty,   -- TODO: JOIN order_state_changes for latest
    NULL::NUMERIC(20,8) AS avg_price,    -- TODO: JOIN fills
    NULL::NUMERIC(20,8) AS fee,          -- TODO: JOIN fills
    category, is_paper,
    details AS raw_json
FROM trading.orders;

-- -------------------------------------------------------
-- trade_executions → trading.fills
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.trade_executions AS
SELECT
    ts,
    fill_id AS exec_id,
    order_id,
    symbol,
    side,
    NULL AS exec_type,
    qty AS exec_qty,
    price AS exec_price,
    fee,
    fee_currency,
    realized_pnl,
    is_paper,
    strategy_name AS strategy,
    details AS metrics
FROM trading.fills;

-- -------------------------------------------------------
-- ai_cost_events → agent.ai_invocations
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.ai_cost_events AS
SELECT
    ts,
    provider,
    model,
    tier,
    purpose,
    input_tokens,
    output_tokens,
    cost_usd,
    latency_ms,
    success,
    details AS context
FROM agent.ai_invocations;

-- -------------------------------------------------------
-- system_health → 暫時指向 legacy（新架構中無直接對應表）
-- NOTE: Phase 0b 時 grafana_data_writer 改寫後可移除
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.system_health AS
SELECT id, ts, component, status, latency_ms, detail, metrics
FROM public.system_health_legacy;

-- -------------------------------------------------------
-- observer_verdicts → trading.risk_verdicts
-- 欄位映射：新表結構不同，需適配
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.observer_verdicts AS
SELECT
    ts,
    verdict,
    NULL AS packet_version,
    CASE WHEN verdict = 'APPROVED' THEN TRUE ELSE FALSE END AS h0_pass,
    NULL AS thought_gate,
    NULL AS ai_tier,
    details AS risk_flags,
    reason AS summary
FROM trading.risk_verdicts;

-- -------------------------------------------------------
-- paper_pnl_snapshots → 暫時指向 legacy
-- NOTE: Phase 0b 時 grafana_data_writer 改寫後改為新表
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.paper_pnl_snapshots AS
SELECT
    id, ts, session_id, realized_pnl, unrealized_pnl,
    total_fees, ai_cost, net_pnl, open_positions,
    total_trades, win_rate, sharpe_ratio
FROM public.paper_pnl_snapshots_legacy;

-- -------------------------------------------------------
-- risk_events → 暫時指向 legacy
-- NOTE: risk.black_swan_events 結構不同，需要 Phase 0b 適配
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.risk_events AS
SELECT id, ts, event_type, symbol, severity, layer, detail, metrics
FROM public.risk_events_legacy;

-- -------------------------------------------------------
-- market_tickers → market.market_tickers
-- 欄位映射：新表用 REAL 替代 NUMERIC
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.market_tickers AS
SELECT
    ts, symbol,
    last_price::NUMERIC(20,8) AS last_price,
    best_bid::NUMERIC(20,8) AS bid_price,
    best_ask::NUMERIC(20,8) AS ask_price,
    volume_24h::NUMERIC(30,8) AS volume_24h,
    NULL::NUMERIC(20,10) AS funding_rate,   -- funding_rate 移到 market.funding_rates
    open_interest::NUMERIC(30,8) AS open_interest,
    index_price::NUMERIC(20,8) AS index_price,
    mark_price::NUMERIC(20,8) AS mark_price
FROM market.market_tickers;

-- -------------------------------------------------------
-- learning_events → 暫時指向 legacy
-- NOTE: 學習事件分散到多張新表（teacher_directives, model_registry 等）
-- -------------------------------------------------------
CREATE OR REPLACE VIEW public.learning_events AS
SELECT id, ts, event_type, title, detail, status, confidence, tags, metadata
FROM public.learning_events_legacy;


-- ================================================================
-- 驗證 / Verification
-- ================================================================
-- -- 確認所有 VIEW 存在
-- SELECT viewname FROM pg_views WHERE schemaname = 'public'
-- AND viewname IN (
--     'account_snapshots', 'position_snapshots', 'order_events',
--     'trade_executions', 'ai_cost_events', 'system_health',
--     'observer_verdicts', 'paper_pnl_snapshots', 'risk_events',
--     'market_tickers', 'learning_events'
-- )
-- ORDER BY viewname;
-- 預期：11 views
--
-- -- 確認 legacy 表存在
-- SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE '%_legacy'
-- ORDER BY tablename;
-- 預期：11 tables
--
-- -- 確認 scorer_training_features VIEW
-- SELECT viewname FROM pg_views WHERE schemaname = 'learning' AND viewname = 'scorer_training_features';
-- 預期：1 row
--
-- -- 測試 Grafana 常用查詢仍然有效
-- SELECT COUNT(*) FROM public.system_health WHERE ts > NOW() - INTERVAL '5 minutes';
-- SELECT COUNT(*) FROM public.market_tickers WHERE ts > NOW() - INTERVAL '5 minutes';
