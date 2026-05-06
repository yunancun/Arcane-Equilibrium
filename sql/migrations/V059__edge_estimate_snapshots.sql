-- V059__edge_estimate_snapshots.sql
-- REF-21 edge estimate snapshot ledger.
--
-- Purpose / 目的:
--   Persist immutable edge estimate snapshots keyed by as-of timestamp,
--   strategy/config hash, symbol, strategy, regime, and cell. REF-21 replay
--   promotion must read historical edge snapshots instead of current mutable
--   estimates.
--
--   持久化 immutable edge estimate snapshot，鍵包含 asof_ts、策略/配置 hash、
--   symbol、strategy、regime、cell。REF-21 replay promotion 必須讀歷史快照，
--   不得讀當前可變 edge estimate。

CREATE SCHEMA IF NOT EXISTS learning;

CREATE TABLE IF NOT EXISTS learning.edge_estimate_snapshots (
    asof_ts TIMESTAMPTZ NOT NULL,
    source_tier TEXT NOT NULL,
    config_hash BYTEA NOT NULL CHECK (octet_length(config_hash) = 32),
    strategy_hash BYTEA NOT NULL CHECK (octet_length(strategy_hash) = 32),
    scanner_config_hash BYTEA NOT NULL CHECK (octet_length(scanner_config_hash) = 32),
    symbol TEXT NOT NULL CHECK (symbol ~ '^[A-Z0-9_.]{1,32}$'),
    strategy TEXT NOT NULL CHECK (strategy ~ '^[A-Za-z0-9_.]{1,64}$'),
    regime_key TEXT NOT NULL,
    cell_key TEXT NOT NULL,
    estimate_payload_hash BYTEA NOT NULL CHECK (octet_length(estimate_payload_hash) = 32),
    estimate_payload_jsonb JSONB NOT NULL,
    is_deprecated_at_asof BOOLEAN NOT NULL DEFAULT false,
    deprecated_reason TEXT CHECK (deprecated_reason IS NULL OR deprecated_reason !~ E'[\\r\\n]'),
    retention_until TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        asof_ts, strategy_hash, scanner_config_hash,
        symbol, strategy, regime_key, cell_key
    ),
    CONSTRAINT chk_edge_estimate_retention_min_75d
        CHECK (retention_until >= asof_ts + INTERVAL '75 days')
);

DO $$
DECLARE
    v_table_exists BOOLEAN;
    v_deprecated_col_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name = 'edge_estimate_snapshots'
    ) INTO v_table_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'edge_estimate_snapshots'
          AND column_name = 'is_deprecated_at_asof'
    ) INTO v_deprecated_col_exists;

    IF NOT v_table_exists OR NOT v_deprecated_col_exists THEN
        RAISE EXCEPTION
            'V059 Guard A: learning.edge_estimate_snapshots missing table or deprecated-strategy column';
    END IF;

    RAISE NOTICE 'V059 Guard A: edge estimate snapshot table verified';
END $$;

CREATE INDEX IF NOT EXISTS idx_edge_estimate_snapshots_symbol_strategy_asof
    ON learning.edge_estimate_snapshots (symbol, strategy, asof_ts DESC);

CREATE INDEX IF NOT EXISTS idx_edge_estimate_snapshots_deprecated
    ON learning.edge_estimate_snapshots (is_deprecated_at_asof, asof_ts DESC)
    WHERE is_deprecated_at_asof = true;

REVOKE UPDATE, DELETE ON learning.edge_estimate_snapshots FROM PUBLIC;

COMMENT ON TABLE learning.edge_estimate_snapshots IS
'REF-21 immutable historical edge estimate snapshots. Retention must be at least 75 days.';

COMMENT ON COLUMN learning.edge_estimate_snapshots.is_deprecated_at_asof IS
'True when the strategy/symbol was deprecated at this as-of timestamp; replay calibration must exclude these rows unless QC explicitly approves.';
