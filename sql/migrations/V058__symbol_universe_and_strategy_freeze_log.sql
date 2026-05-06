-- V058__symbol_universe_and_strategy_freeze_log.sql
-- REF-21 freeze/OOS bootstrap: symbol universe snapshots + immutable freeze log.
--
-- Purpose / 目的:
--   Give REF-21 replay a historical symbol-universe source and an immutable
--   governance freeze log. This closes the V1.3 gap where strategy_freeze_date
--   was described as derived from governance.strategy_freeze_log but the
--   governance schema/table did not exist.
--
--   為 REF-21 replay 提供歷史 symbol universe 來源與不可變 freeze log。
--   修正 V1.3 寫 strategy_freeze_date 來自 governance.strategy_freeze_log，
--   但實際 DB schema/table 為 0 的 gap。

CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS governance.strategy_freeze_log (
    freeze_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    freeze_tag TEXT NOT NULL UNIQUE CHECK (freeze_tag ~ '^freeze/[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
    freeze_date DATE NOT NULL,
    strategy_git_sha TEXT NOT NULL CHECK (strategy_git_sha ~ '^[0-9a-f]{7,64}$'),
    strategy_config_hash BYTEA NOT NULL CHECK (octet_length(strategy_config_hash) = 32),
    scanner_config_hash BYTEA NOT NULL CHECK (octet_length(scanner_config_hash) = 32),
    risk_config_hash BYTEA NOT NULL CHECK (octet_length(risk_config_hash) = 32),
    created_by TEXT NOT NULL CHECK (created_by !~ E'[\\r\\n]'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS market.symbol_universe_snapshots (
    ts TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL CHECK (exchange = 'bybit'),
    category TEXT NOT NULL CHECK (category IN ('linear', 'spot', 'inverse')),
    symbol TEXT NOT NULL CHECK (symbol ~ '^[A-Z0-9_.]{1,32}$'),
    status TEXT NOT NULL,
    base_coin TEXT,
    quote_coin TEXT,
    contract_type TEXT,
    tick_size NUMERIC,
    qty_step NUMERIC,
    min_notional NUMERIC,
    listed_at TIMESTAMPTZ,
    delisted_at TIMESTAMPTZ,
    is_delisted_at_asof BOOLEAN NOT NULL DEFAULT false,
    source_uri TEXT NOT NULL,
    payload_hash BYTEA NOT NULL CHECK (octet_length(payload_hash) = 32),
    payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (ts, exchange, category, symbol)
);

DO $$
DECLARE
    v_freeze_exists BOOLEAN;
    v_universe_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'governance'
          AND table_name = 'strategy_freeze_log'
    ) INTO v_freeze_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'market'
          AND table_name = 'symbol_universe_snapshots'
    ) INTO v_universe_exists;

    IF NOT v_freeze_exists OR NOT v_universe_exists THEN
        RAISE EXCEPTION
            'V058 Guard A: expected governance.strategy_freeze_log and market.symbol_universe_snapshots to exist';
    END IF;

    RAISE NOTICE 'V058 Guard A: freeze log and symbol universe snapshot tables verified';
END $$;

CREATE INDEX IF NOT EXISTS idx_symbol_universe_snapshots_symbol_ts
    ON market.symbol_universe_snapshots (exchange, category, symbol, ts DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_freeze_log_date
    ON governance.strategy_freeze_log (freeze_date DESC);

REVOKE UPDATE, DELETE ON governance.strategy_freeze_log FROM PUBLIC;
REVOKE UPDATE, DELETE ON market.symbol_universe_snapshots FROM PUBLIC;

COMMENT ON TABLE governance.strategy_freeze_log IS
'Immutable REF-21 strategy freeze log. strategy_freeze_date must be derived from this table or CI freeze tag, not operator-entered request JSON.';

COMMENT ON TABLE market.symbol_universe_snapshots IS
'REF-21 historical Bybit symbol universe snapshots for replay. Scanner replay must select from this table instead of current survivors.';
