-- V151: ALR append-only persistence foundation.
--
-- Scope:
-- - Creates only ALR-owned learning.alr_* tables.
-- - Retains canonical scanner-cycle payloads, source identities, immutable
--   ingest/watermark events, and a provenance graph.
-- - Does not create, alter, query, or write trading.scanner_snapshots.
-- - Does not grant trading, proof, serving, promotion, or execution authority.
--
-- Idempotency:
-- - CREATE IF NOT EXISTS permits a second application.
-- - Guard A verifies required columns after creation.
-- - Guard B verifies primary/unique/index contracts needed for conflict-safe
--   source identity and monotonic restart-watermark reconstruction.
-- - Application roles receive SELECT/INSERT only; corrections are new events.

BEGIN;

CREATE SCHEMA IF NOT EXISTS learning;

CREATE TABLE IF NOT EXISTS learning.alr_artifact_nodes (
    artifact_hash TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    canonical_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_artifact_nodes_pk PRIMARY KEY (artifact_hash),
    CONSTRAINT alr_artifact_nodes_hash_check CHECK (artifact_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT alr_artifact_nodes_kind_check CHECK (
        artifact_kind IN ('scanner_cycle', 'ingest_event')
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_source_events (
    source_table TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_scan_id TEXT NOT NULL,
    source_ts TIMESTAMPTZ NOT NULL,
    source_hash TEXT NOT NULL,
    cycle_schema_version TEXT NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_source_events_pk PRIMARY KEY (source_table, source_key),
    CONSTRAINT alr_source_events_scan_identity_uniq UNIQUE (
        source_table, source_scan_id, source_ts
    ),
    CONSTRAINT alr_source_events_table_check CHECK (
        source_table = 'trading.scanner_snapshots'
    ),
    CONSTRAINT alr_source_events_hash_fk FOREIGN KEY (source_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash)
);

CREATE TABLE IF NOT EXISTS learning.alr_ingest_events (
    event_hash TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_key TEXT NOT NULL,
    ingest_event_kind TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_ingest_events_pk PRIMARY KEY (event_hash),
    CONSTRAINT alr_ingest_events_hash_fk FOREIGN KEY (event_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_ingest_events_source_fk FOREIGN KEY (source_table, source_key)
        REFERENCES learning.alr_source_events (source_table, source_key),
    CONSTRAINT alr_ingest_events_kind_check CHECK (
        ingest_event_kind IN ('PERSISTED', 'DUPLICATE')
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_watermark_events (
    event_hash TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_ts TIMESTAMPTZ NOT NULL,
    source_scan_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    watermark_event_kind TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_watermark_events_pk PRIMARY KEY (event_hash),
    CONSTRAINT alr_watermark_events_source_fk FOREIGN KEY (source_table, source_key)
        REFERENCES learning.alr_source_events (source_table, source_key),
    CONSTRAINT alr_watermark_events_hash_fk FOREIGN KEY (source_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_watermark_events_kind_check CHECK (
        watermark_event_kind IN ('ADVANCED', 'RETAINED_LATE')
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_provenance_edges (
    edge_hash TEXT NOT NULL,
    from_artifact_hash TEXT NOT NULL,
    to_artifact_hash TEXT NOT NULL,
    edge_role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_provenance_edges_pk PRIMARY KEY (edge_hash),
    CONSTRAINT alr_provenance_edges_from_fk FOREIGN KEY (from_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_provenance_edges_to_fk FOREIGN KEY (to_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_provenance_edges_role_check CHECK (edge_role = 'ingested_from'),
    CONSTRAINT alr_provenance_edges_not_self_check CHECK (
        from_artifact_hash <> to_artifact_hash
    )
);

CREATE INDEX IF NOT EXISTS idx_alr_source_events_persisted
    ON learning.alr_source_events (persisted_at ASC);

CREATE INDEX IF NOT EXISTS idx_alr_watermark_events_cursor
    ON learning.alr_watermark_events (source_ts DESC, source_scan_id DESC)
    WHERE watermark_event_kind = 'ADVANCED';

CREATE INDEX IF NOT EXISTS idx_alr_provenance_edges_to
    ON learning.alr_provenance_edges (to_artifact_hash, edge_role);

-- Guard A: existing objects must expose every column required by repository SQL.
DO $$
DECLARE
    required_columns TEXT[] := ARRAY[
        'alr_artifact_nodes.artifact_hash',
        'alr_artifact_nodes.artifact_kind',
        'alr_artifact_nodes.canonical_payload',
        'alr_source_events.source_table',
        'alr_source_events.source_key',
        'alr_source_events.source_scan_id',
        'alr_source_events.source_ts',
        'alr_source_events.source_hash',
        'alr_ingest_events.event_hash',
        'alr_ingest_events.ingest_event_kind',
        'alr_watermark_events.event_hash',
        'alr_watermark_events.source_scan_id',
        'alr_watermark_events.watermark_event_kind',
        'alr_provenance_edges.edge_hash',
        'alr_provenance_edges.from_artifact_hash',
        'alr_provenance_edges.to_artifact_hash'
    ];
    item TEXT;
    missing_columns TEXT[] := ARRAY[]::TEXT[];
    v_table_name TEXT;
    v_column_name TEXT;
BEGIN
    FOREACH item IN ARRAY required_columns LOOP
        v_table_name := split_part(item, '.', 1);
        v_column_name := split_part(item, '.', 2);
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns AS columns_info
            WHERE columns_info.table_schema = 'learning'
              AND columns_info.table_name = v_table_name
              AND columns_info.column_name = v_column_name
        ) THEN
            missing_columns := array_append(missing_columns, item);
        END IF;
    END LOOP;
    IF array_length(missing_columns, 1) IS NOT NULL THEN
        RAISE EXCEPTION 'V151 Guard A FAIL: ALR columns missing: %', missing_columns;
    END IF;
END $$;

-- Guard B: idempotency/restart contracts need named constraints and cursor index.
DO $$
DECLARE
    required_constraints TEXT[] := ARRAY[
        'alr_artifact_nodes_pk',
        'alr_source_events_pk',
        'alr_source_events_scan_identity_uniq',
        'alr_ingest_events_pk',
        'alr_watermark_events_pk',
        'alr_provenance_edges_pk'
    ];
    constraint_name TEXT;
BEGIN
    FOREACH constraint_name IN ARRAY required_constraints LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = constraint_name
        ) THEN
            RAISE EXCEPTION 'V151 Guard B FAIL: required constraint missing: %', constraint_name;
        END IF;
    END LOOP;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'learning'
          AND tablename = 'alr_watermark_events'
          AND indexname = 'idx_alr_watermark_events_cursor'
    ) THEN
        RAISE EXCEPTION 'V151 Guard B FAIL: restart watermark index missing.';
    END IF;
END $$;

REVOKE UPDATE, DELETE ON learning.alr_artifact_nodes FROM PUBLIC;
REVOKE UPDATE, DELETE ON learning.alr_source_events FROM PUBLIC;
REVOKE UPDATE, DELETE ON learning.alr_ingest_events FROM PUBLIC;
REVOKE UPDATE, DELETE ON learning.alr_watermark_events FROM PUBLIC;
REVOKE UPDATE, DELETE ON learning.alr_provenance_edges FROM PUBLIC;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA learning TO trading_ai';
        FOREACH table_name IN ARRAY ARRAY[
            'alr_artifact_nodes',
            'alr_source_events',
            'alr_ingest_events',
            'alr_watermark_events',
            'alr_provenance_edges'
        ] LOOP
            EXECUTE format('REVOKE UPDATE, DELETE ON learning.%I FROM trading_ai', table_name);
            EXECUTE format('GRANT SELECT, INSERT ON learning.%I TO trading_ai', table_name);
        END LOOP;
        RAISE NOTICE 'V151: trading_ai receives ALR SELECT/INSERT only.';
    ELSE
        RAISE NOTICE 'V151: trading_ai absent; PUBLIC append-only revokes applied.';
    END IF;
END $$;

COMMENT ON TABLE learning.alr_artifact_nodes IS
    'ALR immutable canonical payload nodes. Evidence-only; not trading/proof/serving authority.';
COMMENT ON TABLE learning.alr_source_events IS
    'ALR immutable identity ledger for read-only Rust scanner snapshots.';
COMMENT ON TABLE learning.alr_ingest_events IS
    'ALR append-only ingest outcome ledger. Corrections are new events, never updates.';
COMMENT ON TABLE learning.alr_watermark_events IS
    'ALR append-only watermark history for restart reconstruction; no mutable cursor row.';
COMMENT ON TABLE learning.alr_provenance_edges IS
    'ALR immutable source-to-ingest provenance graph; no promotion or proof authority.';

COMMIT;
