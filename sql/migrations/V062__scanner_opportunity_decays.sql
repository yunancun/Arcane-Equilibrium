-- MAG-022 — scanner advisory decay evidence.
-- scanner ranking decay is advisory evidence only; it is not a close/reduce command.

CREATE TABLE IF NOT EXISTS trading.scanner_opportunity_decays (
    ts                       TIMESTAMPTZ NOT NULL,
    decay_id                 TEXT        NOT NULL,
    scan_id                  TEXT        NOT NULL,
    symbol                   TEXT        NOT NULL,
    strategy                 TEXT,
    authority_mode           TEXT        NOT NULL,
    reason                   TEXT        NOT NULL,
    previous_score           DOUBLE PRECISION,
    current_score            DOUBLE PRECISION,
    previous_rank            INTEGER,
    current_rank             INTEGER,
    has_open_position        BOOLEAN     NOT NULL DEFAULT FALSE,
    position_review_required BOOLEAN     NOT NULL DEFAULT FALSE,
    auto_close_allowed       BOOLEAN     NOT NULL DEFAULT FALSE,
    evidence                 JSONB       NOT NULL DEFAULT '{}'::jsonb,
    payload                  JSONB       NOT NULL,
    PRIMARY KEY (decay_id, ts)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('trading.scanner_opportunity_decays', 'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_scanner_opportunity_decays_ts
    ON trading.scanner_opportunity_decays (ts DESC);

CREATE INDEX IF NOT EXISTS idx_scanner_opportunity_decays_scan_id
    ON trading.scanner_opportunity_decays (scan_id);

CREATE INDEX IF NOT EXISTS idx_scanner_opportunity_decays_symbol_ts
    ON trading.scanner_opportunity_decays (symbol, ts DESC);

COMMENT ON TABLE trading.scanner_opportunity_decays IS
    'Advisory scanner opportunity decay evidence; rows must not be interpreted as close or reduce commands.';

COMMENT ON COLUMN trading.scanner_opportunity_decays.position_review_required IS
    'True means downstream Strategist/PositionReview should review the open position; scanner itself does not close.';

COMMENT ON COLUMN trading.scanner_opportunity_decays.auto_close_allowed IS
    'Must remain false for scanner-only decay evidence.';
