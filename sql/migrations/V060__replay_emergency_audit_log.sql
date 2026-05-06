-- V060__replay_emergency_audit_log.sql
-- REF-21 emergency audit log for disabled-by-default full-chain prepare.
--
-- Purpose / 目的:
--   Create audit.replay_emergency_log as the authoritative append-only row
--   for governed uses of POST /api/v1/replay/full-chain/prepare. V1.3 only
--   had a DDL sketch and did not create the audit schema, so the first real
--   INSERT would fail.
--
--   建立 audit.replay_emergency_log 作為
--   POST /api/v1/replay/full-chain/prepare governed enablement 的權威
--   append-only row。V1.3 只有 DDL sketch，且未建立 audit schema，第一筆
--   真 INSERT 會直接失敗；本 migration 修正該 gap。

CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS audit.replay_emergency_log (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_id TEXT NOT NULL CHECK (actor_id !~ E'[\\r\\n]'),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'agent', 'system')),
    route TEXT NOT NULL CHECK (route = '/api/v1/replay/full-chain/prepare'),
    enabled_flag BOOLEAN NOT NULL,
    bulk_prod_ip_allowed BOOLEAN NOT NULL DEFAULT false,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    symbols TEXT[] NOT NULL DEFAULT '{}',
    source_tier TEXT NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count >= 0),
    manifest_hash BYTEA CHECK (manifest_hash IS NULL OR octet_length(manifest_hash) = 32),
    reason TEXT NOT NULL CHECK (reason !~ E'[\\r\\n]'),
    payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
);

DO $$
DECLARE
    v_table_exists BOOLEAN;
    v_bulk_col_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'audit'
          AND table_name = 'replay_emergency_log'
    ) INTO v_table_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'audit'
          AND table_name = 'replay_emergency_log'
          AND column_name = 'bulk_prod_ip_allowed'
    ) INTO v_bulk_col_exists;

    IF NOT v_table_exists OR NOT v_bulk_col_exists THEN
        RAISE EXCEPTION
            'V060 Guard A: audit.replay_emergency_log missing table or bulk_prod_ip_allowed column';
    END IF;

    RAISE NOTICE 'V060 Guard A: audit.replay_emergency_log verified';
END $$;

CREATE INDEX IF NOT EXISTS idx_replay_emergency_log_ts
    ON audit.replay_emergency_log (ts DESC);

CREATE INDEX IF NOT EXISTS idx_replay_emergency_log_actor_ts
    ON audit.replay_emergency_log (actor_id, ts DESC);

REVOKE UPDATE, DELETE ON audit.replay_emergency_log FROM PUBLIC;

COMMENT ON TABLE audit.replay_emergency_log IS
'REF-21 append-only audit authority for /api/v1/replay/full-chain/prepare governed enablement.';
