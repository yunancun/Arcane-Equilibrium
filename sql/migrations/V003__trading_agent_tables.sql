-- ============================================================
-- Phase 0a DDL — 已執行 / Executed
-- 設計來源：融合方案 v0.5 + DB 架構 V1
-- Source: Unified Work Plan v0.5 + DB Architecture V1
-- 執行日期：2026-04-11 · FIX-35: DRAFT 標記移除
-- Execution date: 2026-04-11 · FIX-35: DRAFT marker removed
-- ============================================================
--
-- V003: trading.* + agent.* Tables
-- 交易決策表 + Agent 通信表
-- Trading/decision tables + Agent communication tables
--
-- 表清單 / Table List:
--   trading.decision_context_snapshots — 決策上下文快照（核心表）/ Decision context (core)
--   trading.decision_outcomes          — 事後結果（分離表避免 UPDATE 壓縮 chunk）/ Outcomes
--   trading.signals                    — 信號記錄 / Signal log
--   trading.intents                    — 交易意圖 / Trade intents
--   trading.risk_verdicts              — 風控裁定 / Risk verdicts
--   trading.orders                     — 訂單（事件溯源）/ Orders (event sourced)
--   trading.order_state_changes        — 訂單狀態變化 / Order state changes
--   trading.fills                      — 成交記錄 / Fill records
--   trading.position_snapshots         — 持倉快照 / Position snapshots
--   agent.messages                     — Agent 間消息 / Inter-agent messages
--   agent.ai_invocations               — AI 調用記錄 / AI invocation log
--   agent.state_changes                — Agent 狀態轉換 / Agent state transitions
--
-- 設計決策 / Design Decisions:
--   - decision_context_snapshots 用混合方案（15 扁平 + JSONB），審計 PA-2 修正
--   - decision_outcomes 分離為普通表，避免 UPDATE 壓縮 chunk（DBA §10.5）
--   - Hypertable 不支持 FK，邏輯 FK 文檔化 + 應用層 CHECK
-- ============================================================

-- ==========================================================
-- trading.decision_context_snapshots — 決策上下文快照（★ 架構核心）
-- Decision context snapshot (CORE TABLE)
-- 混合方案：~15 核心查詢欄位扁平化 + JSONB 放其餘（審計 PA-2）
-- Hybrid: ~15 flat columns for WHERE/JOIN/GROUP BY + JSONB for the rest
-- Source: v0.5 §1.4 · hypertable 1d chunks
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.decision_context_snapshots (
    -- 身份 / Identity
    ts                  TIMESTAMPTZ NOT NULL,
    ts_ms               BIGINT,
    context_id          TEXT        NOT NULL,  -- UUID，邏輯主鍵 / logical PK
    decision_type       TEXT        NOT NULL,  -- signal_generated/intent_created/risk_review/order_submitted/fill_occurred/position_closed
    symbol              TEXT        NOT NULL,
    strategy_name       TEXT,

    -- 即時價格（扁平化，高頻查詢）/ Real-time price (flat, frequent queries)
    last_price          REAL,
    mark_price          REAL,
    spread_bps          REAL,

    -- Regime（扁平化，GROUP BY 常用）/ Regime (flat, frequent GROUP BY)
    regime_5m           TEXT,
    regime_1h           TEXT,

    -- 核心指標（扁平化，WHERE 條件常用）/ Core indicators (flat, frequent WHERE)
    ind_5m_adx          REAL,
    ind_5m_rsi          REAL,
    ind_5m_atr_14_pct   REAL,

    -- 持倉狀態（扁平化）/ Position state (flat)
    position_side       TEXT,       -- Long/Short/None
    position_qty        REAL,

    -- 組合級（扁平化）/ Portfolio level (flat)
    total_equity        REAL,
    drawdown_pct        REAL,

    -- 新聞特徵（v0.5 §1.3 新增）/ News features (v0.5 §1.3)
    news_severity       REAL,                   -- 近 24h 最高新聞嚴重度 / max news severity in 24h
    hours_since_last_major_news REAL,           -- 距上次重大新聞小時數 / hours since last major news
    news_driven         BOOLEAN,                -- 歸因標籤 / attribution label

    -- Scorer 特徵（v0.5 §1.3 新增）/ Scorer features (v0.5 §1.3)
    scorer_ev_prediction REAL,                  -- Scorer 預測值 / scorer EV prediction
    scorer_divergence    REAL,                  -- 多 Scorer 分歧度 / multi-scorer divergence

    -- JSONB 區（特徵增減不需 ALTER TABLE）/ JSONB section (schema-flexible)
    indicators_snapshot JSONB,     -- 全 TF 所有指標 / all TF indicators
    microstructure      JSONB,     -- orderbook + funding + OI
    position_detail     JSONB,     -- 完整持倉狀態 / full position state
    recent_sequences    JSONB,     -- REAL[60] 序列 / recent price sequences
    decision_payload    JSONB,     -- 決策本身 / decision payload

    -- 事後結果標記（actual 值在 decision_outcomes 表）
    -- Outcome flag (actual values in decision_outcomes table)
    outcome_backfilled  BOOLEAN    DEFAULT FALSE,

    PRIMARY KEY (context_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.decision_context_snapshots', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- trading.decision_outcomes — 事後結果（分離表）
-- Decision outcomes (separated table to avoid UPDATE on compressed chunks)
-- Source: v0.5 §10.5 (DBA 建議) · 普通表 / regular table
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.decision_outcomes (
    context_id      TEXT        PRIMARY KEY,
    -- 5 個回報窗口（v0.5 §10.2 條件 #1：保留 24h）
    -- 5 return windows (v0.5 §10.2 condition #1: keep 24h)
    outcome_1m      REAL,
    outcome_5m      REAL,
    outcome_1h      REAL,
    outcome_4h      REAL,
    outcome_24h     REAL,       -- ★ 趨勢策略持倉 12-72h，必須保留
    -- 極端值 / Extremes
    max_favorable   REAL,       -- 24h 內最大有利移動 / max favorable excursion
    max_adverse     REAL,       -- 24h 內最大不利移動 / max adverse excursion
    -- 回填時間戳 / Backfill timestamp
    backfilled_ts   TIMESTAMPTZ
    -- 邏輯 FK: context_id → trading.decision_context_snapshots.context_id
    -- Logical FK: context_id → trading.decision_context_snapshots.context_id
);

-- ==========================================================
-- trading.signals — 信號記錄
-- Signal log
-- Source: DB-1 · 含 context_id 邏輯 FK
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.signals (
    ts              TIMESTAMPTZ NOT NULL,
    signal_id       TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    strategy_name   TEXT        NOT NULL,
    timeframe       TEXT,
    signal_type     TEXT        NOT NULL,   -- LONG/SHORT/CLOSE/HOLD
    strength        REAL,                   -- 信號強度 / signal strength 0~1
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    details         JSONB,                  -- 策略特定參數 / strategy-specific params
    PRIMARY KEY (signal_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.signals', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- trading.intents — 交易意圖
-- Trade intents (pre-risk-review)
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.intents (
    ts              TIMESTAMPTZ NOT NULL,
    intent_id       TEXT        NOT NULL,
    signal_id       TEXT,                   -- 邏輯 FK → signals
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,   -- Buy/Sell
    qty             REAL,
    price           REAL,
    order_type      TEXT,                   -- Market/Limit
    strategy_name   TEXT,
    details         JSONB,
    PRIMARY KEY (intent_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.intents', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- trading.risk_verdicts — 風控裁定
-- Guardian risk verdicts
-- Source: DB-1 · 含完整裁定理由
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.risk_verdicts (
    ts              TIMESTAMPTZ NOT NULL,
    verdict_id      TEXT        NOT NULL,
    intent_id       TEXT,                   -- 邏輯 FK → intents
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    symbol          TEXT        NOT NULL,
    verdict         TEXT        NOT NULL,   -- APPROVED/REJECTED/MODIFIED
    risk_level      TEXT,                   -- P0/P1/P2
    checks_passed   TEXT[],                 -- 通過的檢查項 / passed checks
    checks_failed   TEXT[],                 -- 失敗的檢查項 / failed checks
    reason          TEXT,
    details         JSONB,
    PRIMARY KEY (verdict_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.risk_verdicts', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- trading.orders — 訂單（事件溯源設計）
-- Orders (event-sourced design)
-- Source: DB-1 · Live 階段 sync_commit=on
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.orders (
    ts              TIMESTAMPTZ NOT NULL,
    order_id        TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,   -- Buy/Sell
    order_type      TEXT        NOT NULL,   -- Market/Limit/StopMarket/StopLimit
    qty             REAL        NOT NULL,
    price           REAL,
    stop_price      REAL,
    time_in_force   TEXT,                   -- GTC/IOC/FOK
    intent_id       TEXT,                   -- 邏輯 FK → intents
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    strategy_name   TEXT,
    category        TEXT        DEFAULT 'linear',  -- spot/linear/inverse
    is_paper        BOOLEAN     DEFAULT FALSE,
    status          TEXT        NOT NULL,   -- Created/Submitted/Working/Filled/PartiallyFilled/Cancelled/Rejected
    details         JSONB,
    PRIMARY KEY (order_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.orders', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- trading.order_state_changes — 訂單狀態變化（事件溯源）
-- Order state changes (event sourcing)
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.order_state_changes (
    ts              TIMESTAMPTZ NOT NULL,
    order_id        TEXT        NOT NULL,   -- 邏輯 FK → orders
    from_status     TEXT,
    to_status       TEXT        NOT NULL,
    reason          TEXT,
    filled_qty      REAL,
    avg_price       REAL,
    details         JSONB,
    PRIMARY KEY (order_id, ts, to_status)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.order_state_changes', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- trading.fills — 成交記錄
-- Fill / execution records
-- Source: DB-1 · Live 階段 sync_commit=on
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.fills (
    ts              TIMESTAMPTZ NOT NULL,
    fill_id         TEXT        NOT NULL,
    order_id        TEXT        NOT NULL,   -- 邏輯 FK → orders
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,
    qty             REAL        NOT NULL,
    price           REAL        NOT NULL,
    fee             REAL        DEFAULT 0,
    fee_currency    TEXT        DEFAULT 'USDT',
    realized_pnl    REAL        DEFAULT 0,
    is_paper        BOOLEAN     DEFAULT FALSE,
    strategy_name   TEXT,
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    details         JSONB,
    PRIMARY KEY (fill_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.fills', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- trading.position_snapshots — 持倉快照
-- Position snapshots
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS trading.position_snapshots (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,   -- Long/Short
    qty             REAL,
    entry_price     REAL,
    mark_price      REAL,
    unrealized_pnl  REAL,
    leverage        REAL,
    position_value  REAL,
    category        TEXT        DEFAULT 'linear',
    is_paper        BOOLEAN     DEFAULT FALSE,
    details         JSONB,
    PRIMARY KEY (symbol, side, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.position_snapshots', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- agent.messages — Agent 間消息
-- Inter-agent messages (currently all lost in memory)
-- Source: DB-1 · MessageBus 持久化
-- ==========================================================
CREATE TABLE IF NOT EXISTS agent.messages (
    ts              TIMESTAMPTZ NOT NULL,
    message_id      TEXT        NOT NULL,
    from_agent      TEXT        NOT NULL,   -- Scout/Strategist/Guardian/Analyst/Executor/Conductor
    to_agent        TEXT        NOT NULL,
    message_type    TEXT        NOT NULL,   -- INTEL_OBJECT/EVENT_ALERT/TRADE_INTENT/RISK_VERDICT/...
    priority        TEXT,                   -- LOW/NORMAL/HIGH/CRITICAL
    payload         JSONB       NOT NULL,
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    PRIMARY KEY (message_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('agent.messages', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- agent.ai_invocations — AI 調用記錄
-- AI invocation log (prompt hash + cost + context)
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS agent.ai_invocations (
    ts              TIMESTAMPTZ NOT NULL,
    invocation_id   TEXT        NOT NULL,
    provider        TEXT        NOT NULL,   -- anthropic/openai/perplexity/local/ollama
    model           TEXT        NOT NULL,
    tier            TEXT,                   -- L0/L1/L2
    purpose         TEXT,                   -- triage/analysis/search/routing/teacher
    prompt_hash     TEXT,                   -- 去重用 / for deduplication
    input_tokens    INT         DEFAULT 0,
    output_tokens   INT         DEFAULT 0,
    cost_usd        NUMERIC(10,6) DEFAULT 0,
    latency_ms      INT         DEFAULT 0,
    success         BOOLEAN     DEFAULT TRUE,
    response_summary TEXT,
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    details         JSONB,
    PRIMARY KEY (invocation_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('agent.ai_invocations', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- agent.state_changes — Agent 狀態轉換日誌
-- Agent state transition log
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS agent.state_changes (
    ts              TIMESTAMPTZ NOT NULL,
    agent_name      TEXT        NOT NULL,   -- Scout/Strategist/Guardian/Analyst/Executor/Conductor
    from_state      TEXT,
    to_state        TEXT        NOT NULL,
    trigger_event   TEXT,                   -- 觸發事件 / trigger event
    details         JSONB,
    PRIMARY KEY (agent_name, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('agent.state_changes', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ============================================================
-- 驗證 / Verification
-- ============================================================
-- SELECT tablename FROM pg_tables WHERE schemaname = 'trading' ORDER BY tablename;
-- 預期 9 tables:
--   decision_context_snapshots, decision_outcomes, fills, intents,
--   order_state_changes, orders, position_snapshots, risk_verdicts, signals
--
-- SELECT tablename FROM pg_tables WHERE schemaname = 'agent' ORDER BY tablename;
-- 預期 3 tables:
--   ai_invocations, messages, state_changes
