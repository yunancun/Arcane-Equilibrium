-- V030: Persist scanner cycle snapshots for edge attribution.
-- V030：持久化 scanner 掃描週期快照，用於 edge 歸因。

CREATE TABLE IF NOT EXISTS trading.scanner_snapshots (
    ts               TIMESTAMPTZ NOT NULL,
    scan_id          TEXT        NOT NULL,
    active_symbols   TEXT[]      NOT NULL,
    added            TEXT[]      NOT NULL,
    removed          TEXT[]      NOT NULL,
    rejected_count   BIGINT      NOT NULL,
    scan_duration_ms BIGINT      NOT NULL,
    candidates       JSONB       NOT NULL,
    config           JSONB       NOT NULL,
    PRIMARY KEY (scan_id, ts)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('trading.scanner_snapshots', 'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_ts
    ON trading.scanner_snapshots (ts DESC);

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_scan_id
    ON trading.scanner_snapshots (scan_id);

COMMENT ON TABLE trading.scanner_snapshots IS
    'Market scanner cycle snapshots, including edge-aware candidate routing metadata.';
