-- V155: P2-7 immutable ALR health/state snapshots.

BEGIN;

ALTER TABLE learning.alr_artifact_nodes
    DROP CONSTRAINT IF EXISTS alr_artifact_nodes_kind_check;

ALTER TABLE learning.alr_artifact_nodes
    ADD CONSTRAINT alr_artifact_nodes_kind_check CHECK (
        artifact_kind IN (
            'scanner_cycle', 'ingest_event', 'learning_target', 'pit_dataset',
            'statistical_experiment', 'candidate_artifact', 'defer_evidence',
            'outcome_bridge', 'outcome_feedback', 'target_rotation',
            'derived_cache', 'health_snapshot'
        )
    );

CREATE TABLE IF NOT EXISTS learning.alr_health_events (
    snapshot_hash TEXT NOT NULL,
    source_head TEXT NOT NULL,
    canonical_payload JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_health_events_pk PRIMARY KEY (snapshot_hash),
    CONSTRAINT alr_health_events_snapshot_fk FOREIGN KEY (snapshot_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_health_events_source_head_check CHECK (
        source_head ~ '^[0-9a-f]{40}$'
    )
);

CREATE INDEX IF NOT EXISTS idx_alr_health_events_recorded_at
    ON learning.alr_health_events (recorded_at DESC);

REVOKE UPDATE, DELETE ON learning.alr_health_events FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        GRANT USAGE ON SCHEMA learning TO trading_ai;
        REVOKE UPDATE, DELETE ON learning.alr_health_events FROM trading_ai;
        GRANT SELECT, INSERT ON learning.alr_health_events TO trading_ai;
    END IF;
END $$;

COMMENT ON TABLE learning.alr_health_events IS
    'Immutable ALR listener health snapshots: watermark, backlog, evidence gaps, retention, recovery, and authority counters.';

COMMIT;
