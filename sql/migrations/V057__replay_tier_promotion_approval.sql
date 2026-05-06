-- V057__replay_tier_promotion_approval.sql
-- REF-21 full-chain replay governance bootstrap.
--
-- Purpose / 目的:
--   Create the first concrete REF-21 promotion-approval schema so MIT can run
--   Linux PG dry-run against a real migration file instead of a design sketch.
--   This migration is deliberately narrow: it adds the tier enum and the
--   signed approval ledger only. The SECURITY DEFINER metrics calculator is
--   not created here until its SQL body is implemented and cross-checked
--   against program_code/learning_engine/dsr_gate.py and pbo_gate.py.
--
--   建立第一個可實跑的 REF-21 promotion approval schema，讓 MIT Linux PG
--   dry-run 有真 migration 對象，而不是對 markdown sketch 乾跑。本遷移
--   只落 tier enum + 簽名 approval ledger；SECURITY DEFINER metrics
--   calculator 等 SQL body 對齊 learning_engine/dsr_gate.py / pbo_gate.py 後
--   另行落地，避免把 stub 函數部署成假安全邊界。

CREATE SCHEMA IF NOT EXISTS replay;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    CREATE TYPE replay.replay_evidence_tier_v057 AS ENUM (
        'synthetic_replay',
        's2_public_replay',
        's2_oos_replay',
        's1_calibrated_replay',
        'verified_replay_advisory',
        'legacy_calibrated_replay_pending_review',
        'legacy_counterfactual_replay_pending_review'
    );
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'V057: replay.replay_evidence_tier_v057 already exists; skipping CREATE TYPE';
END $$;

CREATE TABLE IF NOT EXISTS replay.tier_promotion_approval (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL,
    from_tier replay.replay_evidence_tier_v057 NOT NULL,
    to_tier replay.replay_evidence_tier_v057 NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('requested', 'approved', 'rejected')),
    metrics_hash BYTEA NOT NULL CHECK (octet_length(metrics_hash) = 32),
    manifest_hash BYTEA NOT NULL CHECK (octet_length(manifest_hash) = 32),
    approver_actor_id TEXT NOT NULL CHECK (approver_actor_id !~ E'[\\r\\n]'),
    approver_role TEXT NOT NULL CHECK (approver_role IN ('PM', 'QC', 'MIT')),
    signature_scheme TEXT NOT NULL DEFAULT 'hmac_sha256_v1'
        CHECK (signature_scheme = 'hmac_sha256_v1'),
    signature_payload_sha256 BYTEA NOT NULL
        CHECK (octet_length(signature_payload_sha256) = 32),
    approval_signature BYTEA NOT NULL CHECK (octet_length(approval_signature) = 32),
    mfa_challenge_id TEXT CHECK (mfa_challenge_id IS NULL OR mfa_challenge_id !~ E'[\\r\\n]'),
    signed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (report_id, from_tier, to_tier, approver_role)
);

DO $$
DECLARE
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'approval_id', 'report_id', 'from_tier', 'to_tier', 'state',
        'metrics_hash', 'manifest_hash', 'approver_actor_id', 'approver_role',
        'signature_scheme', 'signature_payload_sha256', 'approval_signature',
        'mfa_challenge_id', 'signed_at', 'payload_jsonb'
    ];
    v_col TEXT;
BEGIN
    FOREACH v_col IN ARRAY v_required_cols LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'replay'
              AND table_name = 'tier_promotion_approval'
              AND column_name = v_col
        ) THEN
            v_missing_cols := array_append(v_missing_cols, v_col);
        END IF;
    END LOOP;

    IF array_length(v_missing_cols, 1) > 0 THEN
        RAISE EXCEPTION
            'V057 Guard A: replay.tier_promotion_approval missing required columns: %',
            array_to_string(v_missing_cols, ', ');
    END IF;

    RAISE NOTICE 'V057 Guard A: replay.tier_promotion_approval column contract verified';
END $$;

DO $$
DECLARE
    v_required_tiers TEXT[] := ARRAY[
        'synthetic_replay',
        's2_public_replay',
        's2_oos_replay',
        's1_calibrated_replay',
        'verified_replay_advisory',
        'legacy_calibrated_replay_pending_review',
        'legacy_counterfactual_replay_pending_review'
    ];
    v_actual_tiers TEXT[];
    v_constraint_defs TEXT;
BEGIN
    SELECT COALESCE(array_agg(e.enumlabel::TEXT ORDER BY e.enumsortorder), ARRAY[]::TEXT[])
    INTO v_actual_tiers
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    JOIN pg_enum e ON e.enumtypid = t.oid
    WHERE n.nspname = 'replay'
      AND t.typname = 'replay_evidence_tier_v057';

    IF NOT v_required_tiers <@ v_actual_tiers THEN
        RAISE EXCEPTION
            'V057 Guard B: replay.replay_evidence_tier_v057 missing required values. actual=%',
            array_to_string(v_actual_tiers, ', ');
    END IF;

    SELECT string_agg(pg_get_constraintdef(c.oid), E'\n')
    INTO v_constraint_defs
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'replay'
      AND t.relname = 'tier_promotion_approval';

    IF v_constraint_defs IS NULL
       OR position('requested' IN v_constraint_defs) = 0
       OR position('approved' IN v_constraint_defs) = 0
       OR position('rejected' IN v_constraint_defs) = 0
       OR position('hmac_sha256_v1' IN v_constraint_defs) = 0
       OR position('octet_length(metrics_hash) = 32' IN v_constraint_defs) = 0
       OR position('octet_length(approval_signature) = 32' IN v_constraint_defs) = 0 THEN
        RAISE EXCEPTION
            'V057 Guard B: tier promotion approval constraints incomplete';
    END IF;

    RAISE NOTICE 'V057 Guard B: tier enum and signature/hash constraints verified';
END $$;

CREATE INDEX IF NOT EXISTS idx_tier_promotion_approval_report
    ON replay.tier_promotion_approval (report_id, signed_at DESC);

REVOKE INSERT, UPDATE, DELETE ON replay.tier_promotion_approval FROM PUBLIC;

DO $$
DECLARE
    v_public_write_grants INTEGER;
    v_index_exists BOOLEAN;
BEGIN
    SELECT COUNT(*)
    INTO v_public_write_grants
    FROM information_schema.role_table_grants
    WHERE table_schema = 'replay'
      AND table_name = 'tier_promotion_approval'
      AND grantee = 'PUBLIC'
      AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE');

    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'replay'
          AND tablename = 'tier_promotion_approval'
          AND indexname = 'idx_tier_promotion_approval_report'
    ) INTO v_index_exists;

    IF v_public_write_grants <> 0 OR NOT v_index_exists THEN
        RAISE EXCEPTION
            'V057 Guard C: public_write_grants=% index_exists=%',
            v_public_write_grants, v_index_exists;
    END IF;

    RAISE NOTICE 'V057 Guard C: PUBLIC write revoke and hot-path index verified';
END $$;

COMMENT ON TABLE replay.tier_promotion_approval IS
'REF-21 signed tier-promotion approval ledger. Signature scheme is fixed to hmac_sha256_v1; metrics calculator is intentionally not stubbed in V057.';

COMMENT ON COLUMN replay.tier_promotion_approval.signature_scheme IS
'Current scheme: hmac_sha256_v1. Ed25519 or other schemes require a new migration and E3/QC/MIT approval.';
