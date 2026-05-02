-- V032: MLDE demo autonomous parameter-application audit log.
-- V032：MLDE demo 自主調參審計表。
--
-- Scope:
--   * Demo may auto-apply bounded ML/Dream recommendations.
--   * Live/live_demo must remain governance-gated. This table records live
--     promotion candidates, but an applied live/live_demo row still requires a
--     Decision Lease id.
--
-- Retrofit (AUDIT-2026-05-02-P1-1, 2026-05-02): added Guard A per CLAUDE.md
-- §七 (V023 silent-noop postmortem). 4-day cold audit found V032 missing
-- this guard; if a legacy `learning.mlde_param_applications` stub exists
-- without `requires_governance` / `decision_lease_id` / `prev_snapshot`
-- columns, `CREATE TABLE IF NOT EXISTS` silently no-ops and the live-gate
-- CHECK constraint below cannot bind correctly. Guard A surfaces drift at
-- apply time. The ALTER TABLE ADD CONSTRAINT block at the bottom is
-- already wrapped in its own `IF NOT EXISTS` DO check (constraint, not
-- column), so no Guard B applies — Guard B is for ADD COLUMN IF NOT
-- EXISTS only.
--
-- 回補（AUDIT-2026-05-02-P1-1，2026-05-02）：依 CLAUDE.md §七 補上
-- Guard A。若 legacy stub 缺 requires_governance / decision_lease_id /
-- prev_snapshot 等欄，CREATE TABLE IF NOT EXISTS 靜默 no-op，下方
-- live-gate CHECK constraint 套不上去。底部 ADD CONSTRAINT 已自帶
-- IF NOT EXISTS DO block（constraint 不是 column），不適用 Guard B。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A

CREATE SCHEMA IF NOT EXISTS learning;

-- ------------------------------------------------------------
-- Schema Guard A — verify mlde_param_applications required cols
-- Schema Guard A — 表已存在時驗必要欄位俱在
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name   = 'mlde_param_applications'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'ts', 'engine_mode', 'recommendation_id',
            'application_type', 'target_name',
            'patch', 'prev_snapshot', 'ipc_response',
            'status', 'reason',
            'requires_governance', 'decision_lease_id',
            'created_by', 'payload'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'mlde_param_applications'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: learning.mlde_param_applications exists but missing required columns: %. '
                'Likely a legacy stub is present (perhaps without requires_governance / decision_lease_id). '
                'Resolve (DROP + re-apply V032, or ALTER TABLE ADD missing columns) before continuing — '
                'the live-gate CHECK constraint below depends on these columns.',
                v_missing;
        END IF;
    END IF;
END $$;

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
