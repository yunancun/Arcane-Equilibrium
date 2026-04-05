-- V007: ExperimentLedger hypothesis tracking table (Phase 1 debt, Phase 2a implementation)
-- V007：ExperimentLedger 假設追蹤表（Phase 1 延後債務，Phase 2a 實現）
--
-- Migrates from JSON file (settings/experiment_ledger_snapshot.json) to PG.
-- 3 new fields added (F7 audit): source_type, metadata JSONB, trigger_condition.

CREATE TABLE IF NOT EXISTS learning.experiment_ledger (
    hypothesis_id       TEXT        PRIMARY KEY,
    description         TEXT        NOT NULL,
    strategy_name       TEXT        NOT NULL,
    regime              TEXT        NOT NULL DEFAULT 'all',
    proposed_by         TEXT        NOT NULL,
    proposed_at_ms      BIGINT      NOT NULL,
    expires_at_ms       BIGINT      NOT NULL,
    status              TEXT        NOT NULL DEFAULT 'PENDING',
    min_observations    INT         NOT NULL DEFAULT 20,
    supporting_count    INT         NOT NULL DEFAULT 0,
    refuting_count      INT         NOT NULL DEFAULT 0,
    concluded_at_ms     BIGINT,
    claim_id            TEXT,
    notes               TEXT        DEFAULT '',
    -- Phase 2a new fields (F7 audit requirement)
    source_type         TEXT        DEFAULT 'rule_based',
    metadata            JSONB       DEFAULT '{}',
    trigger_condition   TEXT        DEFAULT '',
    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experiment_ledger_status
    ON learning.experiment_ledger (status);
CREATE INDEX IF NOT EXISTS idx_experiment_ledger_strategy
    ON learning.experiment_ledger (strategy_name);
