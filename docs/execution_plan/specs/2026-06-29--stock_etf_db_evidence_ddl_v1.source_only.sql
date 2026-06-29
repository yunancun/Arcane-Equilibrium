-- stock_etf_db_evidence_ddl_v1 SOURCE-ONLY DDL DRAFT.
-- ADR-0048 / AMD-2026-06-29-01 Phase 1 artifact.
--
-- Do not copy into sql/migrations/ or apply to any database before:
--   1. E2/E4 review,
--   2. Linux Postgres dry-run,
--   3. idempotency double-apply proof,
--   4. PM/Operator migration apply authorization.

CREATE SCHEMA IF NOT EXISTS broker;
CREATE SCHEMA IF NOT EXISTS research;
CREATE SCHEMA IF NOT EXISTS audit;

-- Guard A: if a table already exists, it must already carry the contract cols.
DO $$
DECLARE
    rec RECORD;
    v_missing TEXT[];
BEGIN
    FOR rec IN
        SELECT * FROM (VALUES
            ('broker','instruments',ARRAY['asset_lane','broker','symbol','listing_venue','currency','primary_exchange','instrument_kind','instrument_identity_hash']),
            ('broker','instrument_listings',ARRAY['asset_lane','broker','symbol','listing_venue','currency','primary_exchange','instrument_identity_hash']),
            ('broker','market_sessions',ARRAY['asset_lane','broker','listing_venue','session_date','session_status','raw_artifact_hash']),
            ('broker','corporate_actions',ARRAY['asset_lane','broker','symbol','action_id','action_type','raw_artifact_hash']),
            ('broker','fx_rates',ARRAY['asset_lane','broker','base_currency','quote_currency','as_of','fx_rate','raw_artifact_hash']),
            ('broker','account_cash_ledger',ARRAY['asset_lane','broker','environment','account_fingerprint','currency','cash_balance','raw_artifact_hash']),
            ('broker','paper_orders',ARRAY['asset_lane','broker','environment','account_fingerprint','local_order_id','idempotency_key','order_state']),
            ('broker','paper_fills',ARRAY['asset_lane','broker','environment','broker_order_id','execution_id','raw_artifact_hash']),
            ('broker','commissions',ARRAY['asset_lane','broker','environment','broker_order_id','execution_id','commission_report_id']),
            ('research','stock_shadow_signals',ARRAY['asset_lane','strategy_id','signal_id','instrument_identity_hash','universe_version','raw_artifact_hash']),
            ('research','stock_shadow_fills',ARRAY['asset_lane','signal_id','instrument_identity_hash','synthetic_shadow','raw_artifact_hash']),
            ('research','stock_etf_scorecard',ARRAY['asset_lane','strategy_id','universe_version','benchmark_version','as_of_date','scorecard_hash']),
            ('audit','asset_lane_events',ARRAY['event_id','event_time','asset_lane','broker','environment','operation','allowed','denial_reason'])
        ) AS t(schema_name, table_name, required_cols)
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = rec.schema_name AND table_name = rec.table_name
        ) THEN
            SELECT array_agg(c) INTO v_missing
            FROM unnest(rec.required_cols) AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = rec.schema_name
                  AND table_name = rec.table_name
                  AND column_name = c
            );
            IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
                RAISE EXCEPTION
                    'stock_etf_db_evidence_ddl_v1 Guard A: %.% exists but is missing required columns: %',
                    rec.schema_name, rec.table_name, v_missing;
            END IF;
        END IF;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS broker.instruments (
    instrument_id BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    symbol TEXT NOT NULL,
    listing_venue TEXT NOT NULL,
    currency TEXT NOT NULL,
    primary_exchange TEXT NOT NULL,
    instrument_kind TEXT NOT NULL CHECK (instrument_kind IN ('stock','etf','cash')),
    instrument_identity_hash TEXT NOT NULL CHECK (instrument_identity_hash ~ '^[0-9a-f]{64}$'),
    raw_artifact_hash TEXT CHECK (raw_artifact_hash IS NULL OR raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_lane, broker, symbol, listing_venue, currency, primary_exchange)
);

CREATE TABLE IF NOT EXISTS broker.instrument_listings (
    listing_id BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    symbol TEXT NOT NULL,
    listing_venue TEXT NOT NULL,
    currency TEXT NOT NULL,
    primary_exchange TEXT NOT NULL,
    instrument_identity_hash TEXT NOT NULL CHECK (instrument_identity_hash ~ '^[0-9a-f]{64}$'),
    listing_status TEXT NOT NULL DEFAULT 'active' CHECK (listing_status IN ('active','inactive','blocked','unknown')),
    raw_artifact_hash TEXT CHECK (raw_artifact_hash IS NULL OR raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, symbol, listing_venue, currency, primary_exchange)
);

CREATE TABLE IF NOT EXISTS broker.market_sessions (
    session_id BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    listing_venue TEXT NOT NULL,
    session_date DATE NOT NULL,
    session_status TEXT NOT NULL CHECK (session_status IN ('open','closed','holiday','partial','unknown')),
    open_time TIMESTAMPTZ,
    close_time TIMESTAMPTZ,
    timezone TEXT NOT NULL,
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, listing_venue, session_date)
);

CREATE TABLE IF NOT EXISTS broker.corporate_actions (
    corporate_action_pk BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    symbol TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    effective_date DATE NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, symbol, action_id)
);

CREATE TABLE IF NOT EXISTS broker.fx_rates (
    fx_rate_id BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    fx_rate NUMERIC NOT NULL CHECK (fx_rate > 0),
    source TEXT NOT NULL,
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, base_currency, quote_currency, as_of)
);

CREATE TABLE IF NOT EXISTS broker.account_cash_ledger (
    ledger_id BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    environment TEXT NOT NULL CHECK (environment IN ('readonly','paper','shadow')),
    account_fingerprint TEXT NOT NULL,
    currency TEXT NOT NULL,
    cash_balance NUMERIC NOT NULL,
    settled_cash NUMERIC,
    buying_power_paper_value NUMERIC,
    fx_rate_source TEXT,
    fx_rate_as_of TIMESTAMPTZ,
    paper_equity NUMERIC,
    source_time TIMESTAMPTZ NOT NULL,
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, environment, account_fingerprint, currency, source_time)
);

CREATE TABLE IF NOT EXISTS broker.paper_orders (
    paper_order_pk BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    environment TEXT NOT NULL DEFAULT 'paper' CHECK (environment = 'paper'),
    account_fingerprint TEXT NOT NULL,
    local_order_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    broker_order_id TEXT,
    symbol TEXT NOT NULL,
    instrument_identity_hash TEXT NOT NULL CHECK (instrument_identity_hash ~ '^[0-9a-f]{64}$'),
    side TEXT NOT NULL CHECK (side IN ('buy','sell')),
    order_type TEXT NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    limit_price NUMERIC,
    order_state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    raw_artifact_hash TEXT CHECK (raw_artifact_hash IS NULL OR raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, environment, account_fingerprint, local_order_id),
    UNIQUE (asset_lane, broker, environment, account_fingerprint, idempotency_key)
);

CREATE TABLE IF NOT EXISTS broker.paper_fills (
    paper_fill_pk BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    environment TEXT NOT NULL DEFAULT 'paper' CHECK (environment = 'paper'),
    broker_order_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    instrument_identity_hash TEXT NOT NULL CHECK (instrument_identity_hash ~ '^[0-9a-f]{64}$'),
    fill_time TIMESTAMPTZ NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    fill_price NUMERIC NOT NULL CHECK (fill_price > 0),
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, environment, broker_order_id, execution_id)
);

CREATE TABLE IF NOT EXISTS broker.commissions (
    commission_pk BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    broker TEXT NOT NULL DEFAULT 'ibkr' CHECK (broker = 'ibkr'),
    environment TEXT NOT NULL DEFAULT 'paper' CHECK (environment = 'paper'),
    broker_order_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    commission_report_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    commission_amount NUMERIC NOT NULL,
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, broker, environment, broker_order_id, execution_id, commission_report_id)
);

CREATE TABLE IF NOT EXISTS research.stock_shadow_signals (
    signal_pk BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    strategy_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    instrument_identity_hash TEXT NOT NULL CHECK (instrument_identity_hash ~ '^[0-9a-f]{64}$'),
    universe_version TEXT NOT NULL,
    benchmark_version TEXT NOT NULL,
    signal_time TIMESTAMPTZ NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy','sell','hold')),
    intended_notional NUMERIC CHECK (intended_notional IS NULL OR intended_notional >= 0),
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, strategy_id, signal_id)
);

CREATE TABLE IF NOT EXISTS research.stock_shadow_fills (
    shadow_fill_pk BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    signal_id TEXT NOT NULL,
    instrument_identity_hash TEXT NOT NULL CHECK (instrument_identity_hash ~ '^[0-9a-f]{64}$'),
    synthetic_shadow BOOLEAN NOT NULL DEFAULT TRUE CHECK (synthetic_shadow = TRUE),
    fill_time TIMESTAMPTZ NOT NULL,
    conservative_fill_price NUMERIC,
    spread_bps NUMERIC,
    slippage_bps NUMERIC,
    cost_components_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    rejection_reason TEXT,
    raw_artifact_hash TEXT NOT NULL CHECK (raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (asset_lane, signal_id, instrument_identity_hash, fill_time)
);

CREATE TABLE IF NOT EXISTS research.stock_etf_scorecard (
    scorecard_pk BIGSERIAL PRIMARY KEY,
    asset_lane TEXT NOT NULL DEFAULT 'stock_etf_cash' CHECK (asset_lane = 'stock_etf_cash'),
    strategy_id TEXT NOT NULL,
    universe_version TEXT NOT NULL,
    benchmark_version TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    scorecard_hash TEXT NOT NULL CHECK (scorecard_hash ~ '^[0-9a-f]{64}$'),
    metrics_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_lane, strategy_id, universe_version, benchmark_version, as_of_date)
);

CREATE TABLE IF NOT EXISTS audit.asset_lane_events (
    event_pk BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_time TIMESTAMPTZ NOT NULL,
    asset_lane TEXT NOT NULL CHECK (asset_lane IN ('crypto_perp','stock_etf_cash','cfd_margin_reserved')),
    broker TEXT NOT NULL CHECK (broker IN ('bybit','ibkr')),
    environment TEXT NOT NULL CHECK (environment IN ('readonly','paper','shadow','live_reserved_denied')),
    operation TEXT NOT NULL,
    order_local_id TEXT,
    broker_order_id TEXT,
    execution_id TEXT,
    commission_report_id TEXT,
    previous_state TEXT,
    next_state TEXT,
    allowed BOOLEAN NOT NULL,
    denial_reason TEXT,
    raw_artifact_hash TEXT CHECK (raw_artifact_hash IS NULL OR raw_artifact_hash ~ '^[0-9a-f]{64}$'),
    redacted_summary_hash TEXT CHECK (redacted_summary_hash IS NULL OR redacted_summary_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_stock_etf_instruments_symbol
    ON broker.instruments (symbol, listing_venue, currency);
CREATE INDEX IF NOT EXISTS idx_stock_etf_paper_orders_account_state
    ON broker.paper_orders (account_fingerprint, order_state, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_etf_paper_fills_order
    ON broker.paper_fills (broker_order_id, fill_time DESC);
CREATE INDEX IF NOT EXISTS idx_stock_etf_shadow_signals_strategy_time
    ON research.stock_shadow_signals (strategy_id, signal_time DESC);
CREATE INDEX IF NOT EXISTS idx_stock_etf_scorecard_asof
    ON research.stock_etf_scorecard (as_of_date DESC, strategy_id);
CREATE INDEX IF NOT EXISTS idx_asset_lane_events_lane_time
    ON audit.asset_lane_events (asset_lane, broker, environment, event_time DESC);

COMMENT ON TABLE broker.paper_orders IS
    'ADR-0048 source-only IBKR paper order facts. environment is constrained to paper; live is denied.';
COMMENT ON TABLE research.stock_shadow_fills IS
    'ADR-0048 synthetic stock/ETF shadow fills, separate from broker paper fills.';
COMMENT ON TABLE audit.asset_lane_events IS
    'Append-only asset lane audit event contract for stock_etf_cash and future lane-scoped denials.';
