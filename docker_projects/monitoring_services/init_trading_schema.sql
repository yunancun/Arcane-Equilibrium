-- =============================================================================
-- OpenClaw Trading AI - PostgreSQL Schema for Grafana Monitoring
-- Creates tables for: snapshots, observer verdicts, paper trades, AI costs,
--                      system health, learning events
-- =============================================================================

-- 1. Account Snapshots (from Bybit observer cycle)
CREATE TABLE IF NOT EXISTS account_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_equity    NUMERIC(20,8),
    available_balance NUMERIC(20,8),
    used_margin     NUMERIC(20,8),
    unrealized_pnl  NUMERIC(20,8),
    account_type    TEXT DEFAULT 'UNIFIED',
    coin            TEXT DEFAULT 'USDT',
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_ts ON account_snapshots(ts);

-- 2. Position Snapshots
CREATE TABLE IF NOT EXISTS position_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,          -- Buy / Sell
    size            NUMERIC(20,8),
    entry_price     NUMERIC(20,8),
    mark_price      NUMERIC(20,8),
    unrealized_pnl  NUMERIC(20,8),
    leverage        NUMERIC(10,2),
    position_value  NUMERIC(20,8),
    category        TEXT DEFAULT 'linear',  -- spot/linear/inverse/option
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_ts ON position_snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_symbol ON position_snapshots(symbol);

-- 3. Order Events
CREATE TABLE IF NOT EXISTS order_events (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    order_id        TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    order_type      TEXT NOT NULL,
    qty             NUMERIC(20,8),
    price           NUMERIC(20,8),
    status          TEXT NOT NULL,          -- New/Filled/Cancelled/PartiallyFilled/Rejected
    filled_qty      NUMERIC(20,8) DEFAULT 0,
    avg_price       NUMERIC(20,8),
    fee             NUMERIC(20,8) DEFAULT 0,
    category        TEXT DEFAULT 'linear',
    is_paper        BOOLEAN DEFAULT FALSE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_order_events_ts ON order_events(ts);
CREATE INDEX IF NOT EXISTS idx_order_events_symbol ON order_events(symbol);

-- 4. Trade Executions (fills)
CREATE TABLE IF NOT EXISTS trade_executions (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exec_id         TEXT,
    order_id        TEXT,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    exec_type       TEXT,                   -- Trade/Funding/Settlement
    exec_qty        NUMERIC(20,8),
    exec_price      NUMERIC(20,8),
    fee             NUMERIC(20,8) DEFAULT 0,
    fee_currency    TEXT DEFAULT 'USDT',
    realized_pnl    NUMERIC(20,8) DEFAULT 0,
    is_paper        BOOLEAN DEFAULT FALSE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_trade_executions_ts ON trade_executions(ts);
CREATE INDEX IF NOT EXISTS idx_trade_executions_symbol ON trade_executions(symbol);

-- 5. AI Cost Events (from H5 / Layer 2 cost tracking)
CREATE TABLE IF NOT EXISTS ai_cost_events (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider        TEXT NOT NULL,          -- anthropic/openai/perplexity/local
    model           TEXT NOT NULL,
    tier            TEXT,                   -- L0/L1/L2
    purpose         TEXT,                   -- triage/analysis/search/routing
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        NUMERIC(10,6) DEFAULT 0,
    latency_ms      INTEGER DEFAULT 0,
    success         BOOLEAN DEFAULT TRUE,
    context         JSONB
);
CREATE INDEX IF NOT EXISTS idx_ai_cost_events_ts ON ai_cost_events(ts);

-- 6. System Health Snapshots
CREATE TABLE IF NOT EXISTS system_health (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    component       TEXT NOT NULL,          -- rest_api/websocket/database/observer/paper_engine
    status          TEXT NOT NULL,          -- healthy/degraded/down
    latency_ms      NUMERIC(10,2),
    detail          TEXT,
    metrics         JSONB
);
CREATE INDEX IF NOT EXISTS idx_system_health_ts ON system_health(ts);

-- 7. Observer Verdicts (decision packets)
CREATE TABLE IF NOT EXISTS observer_verdicts (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verdict         TEXT NOT NULL,          -- pass/fail/skip/degraded
    packet_version  TEXT,
    h0_pass         BOOLEAN,
    thought_gate    TEXT,                   -- call/no_call
    ai_tier         TEXT,                   -- none/L0/L1/L2
    risk_flags      JSONB,
    summary         TEXT
);
CREATE INDEX IF NOT EXISTS idx_observer_verdicts_ts ON observer_verdicts(ts);

-- 8. Paper Trading PnL (periodic snapshots)
CREATE TABLE IF NOT EXISTS paper_pnl_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id      TEXT,
    realized_pnl    NUMERIC(20,8) DEFAULT 0,
    unrealized_pnl  NUMERIC(20,8) DEFAULT 0,
    total_fees      NUMERIC(20,8) DEFAULT 0,
    ai_cost         NUMERIC(10,6) DEFAULT 0,
    net_pnl         NUMERIC(20,8) DEFAULT 0,
    open_positions  INTEGER DEFAULT 0,
    total_trades    INTEGER DEFAULT 0,
    win_rate        NUMERIC(5,2),
    sharpe_ratio    NUMERIC(10,4)
);
CREATE INDEX IF NOT EXISTS idx_paper_pnl_ts ON paper_pnl_snapshots(ts);

-- 9. Risk Framework Events
CREATE TABLE IF NOT EXISTS risk_events (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type      TEXT NOT NULL,          -- hard_stop/soft_stop/circuit_breaker/exposure_limit/kill_switch
    symbol          TEXT,
    severity        TEXT NOT NULL,          -- info/warning/critical
    layer           TEXT,                   -- P0/P1/P2
    detail          TEXT,
    metrics         JSONB
);
CREATE INDEX IF NOT EXISTS idx_risk_events_ts ON risk_events(ts);

-- 10. Market Data Snapshots (ticker prices for reference)
CREATE TABLE IF NOT EXISTS market_tickers (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol          TEXT NOT NULL,
    last_price      NUMERIC(20,8),
    bid_price       NUMERIC(20,8),
    ask_price       NUMERIC(20,8),
    volume_24h      NUMERIC(30,8),
    turnover_24h    NUMERIC(30,8),
    funding_rate    NUMERIC(20,10),
    open_interest   NUMERIC(30,8)
);
CREATE INDEX IF NOT EXISTS idx_market_tickers_ts ON market_tickers(ts);
CREATE INDEX IF NOT EXISTS idx_market_tickers_symbol ON market_tickers(symbol);

-- 11. Learning Events (observations, lessons, hypotheses)
CREATE TABLE IF NOT EXISTS learning_events (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type      TEXT NOT NULL,          -- observation/lesson/hypothesis/experiment
    title           TEXT,
    detail          TEXT,
    status          TEXT DEFAULT 'pending', -- pending/approved/rejected/completed
    confidence      NUMERIC(3,2),
    tags            TEXT[],
    metadata        JSONB
);
CREATE INDEX IF NOT EXISTS idx_learning_events_ts ON learning_events(ts);

-- Insert seed data for immediate dashboard visibility
INSERT INTO system_health (component, status, latency_ms, detail) VALUES
    ('rest_api', 'healthy', 45.2, 'FastAPI control API responsive'),
    ('websocket', 'healthy', 12.1, 'Bybit WS v2 connected'),
    ('database', 'healthy', 3.5, 'PostgreSQL 16 operational'),
    ('observer', 'healthy', 120.5, 'Observer cycle running'),
    ('paper_engine', 'healthy', 8.3, 'Paper trading engine idle');

INSERT INTO observer_verdicts (verdict, h0_pass, thought_gate, ai_tier, summary) VALUES
    ('pass', true, 'no_call', 'none', 'H0 pass, no AI needed - legal idle state');

INSERT INTO ai_cost_events (provider, model, tier, purpose, input_tokens, output_tokens, cost_usd, latency_ms) VALUES
    ('anthropic', 'claude-3-haiku', 'L1', 'triage', 500, 100, 0.000325, 450);

INSERT INTO paper_pnl_snapshots (session_id, realized_pnl, unrealized_pnl, total_fees, ai_cost, net_pnl, open_positions, total_trades) VALUES
    ('seed_session', 0, 0, 0, 0, 0, 0, 0);

INSERT INTO account_snapshots (total_equity, available_balance, used_margin, unrealized_pnl) VALUES
    (0, 0, 0, 0);
