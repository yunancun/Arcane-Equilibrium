-- V153: P2-5 append-only ProofPacket/RewardLedger feedback and target rotation.
-- Scope is limited to learning.alr_* objects. It neither reads nor changes
-- scanner source data and grants no proof, promotion, serving, trading, or
-- exchange authority.

BEGIN;

ALTER TABLE learning.alr_artifact_nodes
    DROP CONSTRAINT IF EXISTS alr_artifact_nodes_kind_check;

ALTER TABLE learning.alr_artifact_nodes
    ADD CONSTRAINT alr_artifact_nodes_kind_check CHECK (
        artifact_kind IN (
            'scanner_cycle', 'ingest_event', 'learning_target', 'pit_dataset',
            'statistical_experiment', 'candidate_artifact', 'defer_evidence',
            'outcome_bridge', 'outcome_feedback', 'target_rotation'
        )
    );

ALTER TABLE learning.alr_provenance_edges
    DROP CONSTRAINT IF EXISTS alr_provenance_edges_role_check;

ALTER TABLE learning.alr_provenance_edges
    ADD CONSTRAINT alr_provenance_edges_role_check CHECK (
        edge_role IN (
            'ingested_from', 'training_input', 'target_dataset',
            'dataset_experiment', 'experiment_candidate',
            'candidate_defer_evidence', 'candidate_outcome_bridge',
            'bridge_feedback', 'feedback_rotation'
        )
    );

CREATE TABLE IF NOT EXISTS learning.alr_outcome_feedback_events (
    feedback_artifact_hash TEXT NOT NULL,
    run_hash TEXT NOT NULL,
    candidate_artifact_hash TEXT NOT NULL,
    bridge_artifact_hash TEXT NOT NULL,
    rotation_artifact_hash TEXT NOT NULL,
    feedback_status TEXT NOT NULL,
    bridge_outcome TEXT NOT NULL,
    proof_packet_present BOOLEAN NOT NULL,
    reward_record_count INTEGER NOT NULL,
    rotate_next_target BOOLEAN NOT NULL,
    global_stop BOOLEAN NOT NULL,
    no_authority JSONB NOT NULL,
    authority_counters JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_outcome_feedback_events_pk PRIMARY KEY (feedback_artifact_hash),
    CONSTRAINT alr_outcome_feedback_events_run_uniq UNIQUE (run_hash),
    CONSTRAINT alr_outcome_feedback_events_feedback_fk FOREIGN KEY (feedback_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_outcome_feedback_events_run_fk FOREIGN KEY (run_hash)
        REFERENCES learning.alr_training_runs (run_hash),
    CONSTRAINT alr_outcome_feedback_events_candidate_fk FOREIGN KEY (candidate_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_outcome_feedback_events_bridge_fk FOREIGN KEY (bridge_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_outcome_feedback_events_rotation_fk FOREIGN KEY (rotation_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash),
    CONSTRAINT alr_outcome_feedback_events_status_check CHECK (
        feedback_status IN ('DEFER_EVIDENCE', 'EVIDENCE_OBSERVED_NO_PROMOTION', 'BLOCKED_BOUNDARY')
    ),
    CONSTRAINT alr_outcome_feedback_events_outcome_check CHECK (
        bridge_outcome IN ('DEFER_EVIDENCE', 'ADVANCED', 'BLOCKED_BOUNDARY')
    ),
    CONSTRAINT alr_outcome_feedback_events_rotation_check CHECK (
        (feedback_status = 'DEFER_EVIDENCE' AND rotate_next_target AND NOT global_stop)
        OR (feedback_status = 'EVIDENCE_OBSERVED_NO_PROMOTION' AND NOT rotate_next_target AND NOT global_stop)
        OR (feedback_status = 'BLOCKED_BOUNDARY' AND NOT rotate_next_target AND global_stop)
    ),
    CONSTRAINT alr_outcome_feedback_events_reward_count_check CHECK (reward_record_count >= 0),
    CONSTRAINT alr_outcome_feedback_events_no_authority_check CHECK (
        no_authority = '{"exchange_authority": false, "trading_authority": false, "order_or_probe_authority": false, "decision_lease_authority": false, "cost_gate_authority": false, "proof_authority": false, "serving_authority": false, "promotion_authority": false, "latest_authority": false}'::jsonb
    ),
    CONSTRAINT alr_outcome_feedback_events_authority_counters_check CHECK (
        authority_counters = '{"exchange_contact_count": 0, "trading_action_count": 0, "order_or_probe_count": 0, "decision_lease_count": 0, "cost_gate_change_count": 0, "proof_claim_count": 0, "serving_or_promotion_count": 0}'::jsonb
    )
);

CREATE INDEX IF NOT EXISTS idx_alr_outcome_feedback_events_recorded_at
    ON learning.alr_outcome_feedback_events (recorded_at ASC);

REVOKE UPDATE, DELETE ON learning.alr_outcome_feedback_events FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        GRANT USAGE ON SCHEMA learning TO trading_ai;
        REVOKE UPDATE, DELETE ON learning.alr_outcome_feedback_events FROM trading_ai;
        GRANT SELECT, INSERT ON learning.alr_outcome_feedback_events TO trading_ai;
    END IF;
END $$;

COMMENT ON TABLE learning.alr_outcome_feedback_events IS
    'P2-5 append-only outcome feedback. DEFER rotates targets; no proof, serving, promotion, or trading authority.';

COMMIT;
