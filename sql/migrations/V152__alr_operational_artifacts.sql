-- V152: P2-4 append-only operational ALR artifacts and statistical run ledger.
--
-- Scope is restricted to learning.alr_* tables.  Scanner snapshots remain
-- read-only inputs; this migration grants no trading, proof, serving,
-- promotion, lease, Cost Gate, or exchange authority.

BEGIN;

ALTER TABLE learning.alr_artifact_nodes
    DROP CONSTRAINT IF EXISTS alr_artifact_nodes_kind_check;

ALTER TABLE learning.alr_artifact_nodes
    ADD CONSTRAINT alr_artifact_nodes_kind_check CHECK (
        artifact_kind IN (
            'scanner_cycle',
            'ingest_event',
            'learning_target',
            'pit_dataset',
            'statistical_experiment',
            'candidate_artifact',
            'defer_evidence'
        )
    );

ALTER TABLE learning.alr_provenance_edges
    DROP CONSTRAINT IF EXISTS alr_provenance_edges_role_check;

ALTER TABLE learning.alr_provenance_edges
    ADD CONSTRAINT alr_provenance_edges_role_check CHECK (
        edge_role IN (
            'ingested_from',
            'training_input',
            'target_dataset',
            'dataset_experiment',
            'experiment_candidate',
            'candidate_defer_evidence'
        )
    );

CREATE TABLE IF NOT EXISTS learning.alr_training_runs (
    run_hash TEXT NOT NULL,
    source_set_hash TEXT NOT NULL,
    run_kind TEXT NOT NULL,
    run_status TEXT NOT NULL,
    source_head TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    target_artifact_hash TEXT NOT NULL,
    pit_dataset_artifact_hash TEXT NOT NULL,
    experiment_artifact_hash TEXT NOT NULL,
    candidate_artifact_hash TEXT NOT NULL,
    defer_artifact_hash TEXT NOT NULL,
    no_authority JSONB NOT NULL,
    authority_counters JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_training_runs_pk PRIMARY KEY (run_hash),
    CONSTRAINT alr_training_runs_source_set_kind_uniq UNIQUE (source_set_hash, run_kind),
    CONSTRAINT alr_training_runs_hash_check CHECK (run_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT alr_training_runs_source_set_hash_check CHECK (
        source_set_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_training_runs_source_head_check CHECK (
        source_head ~ '^[0-9a-f]{40}$'
    ),
    CONSTRAINT alr_training_runs_kind_check CHECK (
        run_kind = 'scanner_novelty_statistical_baseline'
    ),
    CONSTRAINT alr_training_runs_status_check CHECK (run_status = 'DEFER_EVIDENCE'),
    CONSTRAINT alr_training_runs_source_count_check CHECK (source_count >= 3),
    CONSTRAINT alr_training_runs_target_fk FOREIGN KEY (target_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_training_runs_pit_fk FOREIGN KEY (pit_dataset_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_training_runs_experiment_fk FOREIGN KEY (experiment_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_training_runs_candidate_fk FOREIGN KEY (candidate_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_training_runs_defer_fk FOREIGN KEY (defer_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_training_runs_no_authority_check CHECK (
        no_authority = '{"exchange_authority": false, "trading_authority": false, "order_or_probe_authority": false, "decision_lease_authority": false, "cost_gate_authority": false, "proof_authority": false, "serving_authority": false, "promotion_authority": false, "latest_authority": false}'::jsonb
    ),
    CONSTRAINT alr_training_runs_authority_counters_check CHECK (
        authority_counters = '{"exchange_contact_count": 0, "trading_action_count": 0, "order_or_probe_count": 0, "decision_lease_count": 0, "cost_gate_change_count": 0, "proof_claim_count": 0, "serving_or_promotion_count": 0}'::jsonb
    )
);

CREATE INDEX IF NOT EXISTS idx_alr_training_runs_created_at
    ON learning.alr_training_runs (created_at ASC);

CREATE INDEX IF NOT EXISTS idx_alr_provenance_edges_training_input
    ON learning.alr_provenance_edges (from_artifact_hash)
    WHERE edge_role = 'training_input';

DO $$
DECLARE
    required_constraints TEXT[] := ARRAY[
        'alr_artifact_nodes_kind_check',
        'alr_provenance_edges_role_check',
        'alr_training_runs_pk',
        'alr_training_runs_source_set_kind_uniq'
    ];
    constraint_name TEXT;
BEGIN
    FOREACH constraint_name IN ARRAY required_constraints LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = constraint_name) THEN
            RAISE EXCEPTION 'V152 guard failed: required constraint missing: %', constraint_name;
        END IF;
    END LOOP;
END $$;

REVOKE UPDATE, DELETE ON learning.alr_training_runs FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        GRANT USAGE ON SCHEMA learning TO trading_ai;
        REVOKE UPDATE, DELETE ON learning.alr_training_runs FROM trading_ai;
        GRANT SELECT, INSERT ON learning.alr_training_runs TO trading_ai;
    END IF;
END $$;

COMMENT ON TABLE learning.alr_training_runs IS
    'P2-4 immutable scanner statistical run ledger. DEFER_EVIDENCE only; never trading, proof, serving, or promotion authority.';

COMMIT;
