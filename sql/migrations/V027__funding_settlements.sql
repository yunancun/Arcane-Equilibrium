-- ============================================================
-- V027: trading.funding_settlements
-- First-class funding settlement ledger from Bybit execution stream.
-- ============================================================

DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'trading'
          AND table_name   = 'funding_settlements'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts','settlement_id','exec_id','symbol','side','amount',
            'fee_currency','exec_value','exec_price','exec_qty',
            'strategy_name','engine_mode','raw'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'trading'
              AND table_name   = 'funding_settlements'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V027 Guard A FAIL: trading.funding_settlements exists but missing columns: %',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS trading.funding_settlements (
    ts              TIMESTAMPTZ NOT NULL,
    settlement_id   TEXT        NOT NULL,
    exec_id         TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,
    amount          DOUBLE PRECISION NOT NULL DEFAULT 0,
    fee_currency    TEXT        NOT NULL DEFAULT 'USDT',
    exec_value      DOUBLE PRECISION NOT NULL DEFAULT 0,
    exec_price      DOUBLE PRECISION NOT NULL DEFAULT 0,
    exec_qty        DOUBLE PRECISION NOT NULL DEFAULT 0,
    strategy_name   TEXT        NOT NULL,
    engine_mode     TEXT        NOT NULL
        CHECK (engine_mode IN ('paper','demo','live','live_demo')
               OR engine_mode LIKE 'test\_%' ESCAPE '\'),
    raw             JSONB,
    PRIMARY KEY (settlement_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('trading.funding_settlements', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_funding_settlements_engine_mode_ts
    ON trading.funding_settlements (engine_mode, ts DESC);

CREATE INDEX IF NOT EXISTS idx_funding_settlements_symbol_ts
    ON trading.funding_settlements (symbol, ts DESC);

COMMENT ON TABLE trading.funding_settlements IS
    'Bybit funding settlement ledger; separate from trading.fills because funding is not an order fill.';

COMMENT ON COLUMN trading.funding_settlements.amount IS
    'Signed funding settlement amount in fee_currency; positive increases account equity.';
