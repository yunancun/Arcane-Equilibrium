-- V154: P2-6 two-phase retention for ALR-owned rebuildable cache only.

BEGIN;

ALTER TABLE learning.alr_artifact_nodes
    DROP CONSTRAINT IF EXISTS alr_artifact_nodes_kind_check;

ALTER TABLE learning.alr_artifact_nodes
    ADD CONSTRAINT alr_artifact_nodes_kind_check CHECK (
        artifact_kind IN (
            'scanner_cycle', 'ingest_event', 'learning_target', 'pit_dataset',
            'statistical_experiment', 'candidate_artifact', 'defer_evidence',
            'outcome_bridge', 'outcome_feedback', 'target_rotation',
            'derived_cache'
        )
    );

CREATE TABLE IF NOT EXISTS learning.alr_derived_cache_entries (
    cache_key TEXT NOT NULL,
    cache_artifact_hash TEXT NOT NULL,
    cache_kind TEXT NOT NULL,
    cache_payload JSONB NOT NULL,
    cache_content_hash TEXT NOT NULL,
    owner_scope TEXT NOT NULL,
    rebuildable BOOLEAN NOT NULL,
    cache_state TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    quarantined_at TIMESTAMPTZ NULL,
    CONSTRAINT alr_derived_cache_entries_pk PRIMARY KEY (cache_key),
    CONSTRAINT alr_derived_cache_entries_artifact_uniq UNIQUE (cache_artifact_hash),
    CONSTRAINT alr_derived_cache_entries_artifact_fk FOREIGN KEY (cache_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_derived_cache_entries_content_hash_check CHECK (
        cache_content_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_derived_cache_entries_owner_check CHECK (
        owner_scope = 'ALR_OWNED_REBUILDABLE'
    ),
    CONSTRAINT alr_derived_cache_entries_rebuildable_check CHECK (rebuildable),
    CONSTRAINT alr_derived_cache_entries_state_check CHECK (
        (cache_state = 'ACTIVE' AND quarantined_at IS NULL)
        OR (cache_state = 'QUARANTINED' AND quarantined_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_retention_events (
    event_hash TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    cache_artifact_hash TEXT NOT NULL,
    cache_content_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    reference_graph_hash TEXT NOT NULL,
    canonical_payload JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_retention_events_pk PRIMARY KEY (event_hash),
    CONSTRAINT alr_retention_events_artifact_fk FOREIGN KEY (cache_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_retention_events_content_hash_check CHECK (
        cache_content_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_retention_events_reference_hash_check CHECK (
        reference_graph_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_retention_events_action_check CHECK (
        action IN ('QUARANTINE', 'RESTORE_REFERENCE', 'SWEEP')
    )
);

CREATE INDEX IF NOT EXISTS idx_alr_derived_cache_entries_state
    ON learning.alr_derived_cache_entries (cache_state, created_at ASC);

REVOKE UPDATE, DELETE ON learning.alr_derived_cache_entries FROM PUBLIC;
REVOKE UPDATE, DELETE ON learning.alr_retention_events FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        GRANT USAGE ON SCHEMA learning TO trading_ai;
        REVOKE UPDATE, DELETE ON learning.alr_retention_events FROM trading_ai;
        GRANT SELECT, INSERT ON learning.alr_retention_events TO trading_ai;
    END IF;
END $$;

COMMENT ON TABLE learning.alr_derived_cache_entries IS
    'Only ALR-owned, rebuildable cache payloads. The retention guardian may quarantine or sweep these rows only.';
COMMENT ON TABLE learning.alr_retention_events IS
    'Immutable audit of derived-cache quarantine, reference restore, and sweep actions.';

COMMIT;
