-- V032: MLDE demo autonomous parameter-application audit log.
-- V032：MLDE demo 自主調參審計表。
--
-- Scope:
--   * Demo may auto-apply bounded ML/Dream recommendations.
--   * Live/live_demo must remain governance-gated. This table records live
--     promotion candidates, but an applied live/live_demo row still requires a
--     Decision Lease id.

CREATE SCHEMA IF NOT EXISTS learning;

CREATE TABLE IF NOT EXISTS learning.mlde_param_applications (
    id                  BIGSERIAL PRIMARY KEY,
    ts                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    engine_mode          TEXT        NOT NULL CHECK (
        engine_mode IN ('paper', 'demo', 'live_demo', 'live')
        OR engine_mode LIKE 'test\_%' ESCAPE '\'
    ),
    recommendation_id   BIGINT REFERENCES learning.mlde_shadow_recommendations(id) ON DELETE SET NULL,
    application_type    TEXT        NOT NULL CHECK (
        application_type IN ('strategy_params', 'risk_config', 'live_promotion_candidate')
    ),
    target_name         TEXT        NOT NULL,
    patch               JSONB       NOT NULL DEFAULT '{}'::jsonb,
    prev_snapshot       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    ipc_response        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT        NOT NULL CHECK (
        status IN ('applied', 'skipped', 'failed', 'candidate', 'dry_run')
    ),
    reason              TEXT,
    requires_governance BOOLEAN     NOT NULL DEFAULT TRUE,
    decision_lease_id   TEXT,
    created_by          TEXT        NOT NULL DEFAULT 'mlde_demo_applier',
    payload             JSONB       NOT NULL DEFAULT '{}'::jsonb
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'mlde_param_live_applied_requires_lease'
    ) THEN
        ALTER TABLE learning.mlde_param_applications
            ADD CONSTRAINT mlde_param_live_applied_requires_lease
            CHECK (
                NOT (
                    engine_mode IN ('live', 'live_demo')
                    AND status = 'applied'
                    AND COALESCE(decision_lease_id, '') = ''
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_mlde_param_applications_ts
    ON learning.mlde_param_applications (ts DESC);

CREATE INDEX IF NOT EXISTS idx_mlde_param_applications_engine_status_ts
    ON learning.mlde_param_applications (engine_mode, status, ts DESC);

CREATE INDEX IF NOT EXISTS idx_mlde_param_applications_recommendation
    ON learning.mlde_param_applications (recommendation_id);

CREATE INDEX IF NOT EXISTS idx_mlde_param_applications_payload_gin
    ON learning.mlde_param_applications USING GIN (payload);

COMMENT ON TABLE learning.mlde_param_applications IS
    'Audit trail for MLDE demo autonomous parameter applications and live promotion candidates.';
COMMENT ON COLUMN learning.mlde_param_applications.requires_governance IS
    'FALSE only for bounded demo applications. Any live/live_demo application requires Decision Lease.';
