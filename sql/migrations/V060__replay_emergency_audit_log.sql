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

DO $$
DECLARE
    v_constraint_defs TEXT;
BEGIN
    SELECT string_agg(pg_get_constraintdef(c.oid), E'\n')
    INTO v_constraint_defs
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'audit'
      AND t.relname = 'replay_emergency_log';

    IF v_constraint_defs IS NULL
       OR position('/api/v1/replay/full-chain/prepare' IN v_constraint_defs) = 0
       OR position('request_count >= 0' IN v_constraint_defs) = 0
       OR position('human' IN v_constraint_defs) = 0
       OR position('agent' IN v_constraint_defs) = 0
       OR position('system' IN v_constraint_defs) = 0
       OR position('octet_length(manifest_hash) = 32' IN v_constraint_defs) = 0 THEN
        RAISE EXCEPTION
            'V060 Guard B: emergency audit log constraints incomplete';
    END IF;

    RAISE NOTICE 'V060 Guard B: route, actor, request-count, and hash constraints verified';
END $$;

CREATE INDEX IF NOT EXISTS idx_replay_emergency_log_ts
    ON audit.replay_emergency_log (ts DESC);

CREATE INDEX IF NOT EXISTS idx_replay_emergency_log_actor_ts
    ON audit.replay_emergency_log (actor_id, ts DESC);

REVOKE UPDATE, DELETE ON audit.replay_emergency_log FROM PUBLIC;

DO $$
DECLARE
    v_public_write_grants INTEGER;
    v_ts_index_exists BOOLEAN;
    v_actor_index_exists BOOLEAN;
BEGIN
    SELECT COUNT(*)
    INTO v_public_write_grants
    FROM information_schema.role_table_grants
    WHERE table_schema = 'audit'
      AND table_name = 'replay_emergency_log'
      AND grantee = 'PUBLIC'
      AND privilege_type IN ('UPDATE', 'DELETE');

    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'audit'
          AND tablename = 'replay_emergency_log'
          AND indexname = 'idx_replay_emergency_log_ts'
    ) INTO v_ts_index_exists;

    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'audit'
          AND tablename = 'replay_emergency_log'
          AND indexname = 'idx_replay_emergency_log_actor_ts'
    ) INTO v_actor_index_exists;

    IF v_public_write_grants <> 0 OR NOT v_ts_index_exists OR NOT v_actor_index_exists THEN
        RAISE EXCEPTION
            'V060 Guard C: public_write_grants=% ts_index=% actor_index=%',
            v_public_write_grants, v_ts_index_exists, v_actor_index_exists;
    END IF;

    RAISE NOTICE 'V060 Guard C: PUBLIC write revoke and indexes verified';
END $$;

COMMENT ON TABLE audit.replay_emergency_log IS
'REF-21 append-only audit authority for /api/v1/replay/full-chain/prepare governed enablement.';
