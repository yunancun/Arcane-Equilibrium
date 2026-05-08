-- V066__replay_report_artifact_type_cleanup.sql
-- Purpose:
--   Extend replay.report_artifacts.artifact_type with the explicit
--   'replay_report' value used by POST /replay/run/{run_id}/finalize, while
--   keeping the legacy 'pnl_summary' value readable for existing rows.
--   Also adds the missing non-negative byte_size CHECK used by storage quota
--   accounting.
--
-- Migration order:
--   V045 -> V046 -> ... -> V066. This migration requires the V046
--   replay.report_artifacts table and only changes constraints.
--
-- Idempotency:
--   Safe to run more than once. Existing 5-value V046 artifact_type CHECK is
--   replaced only when it lacks 'replay_report'. Existing upgraded CHECKs are
--   preserved.

CREATE SCHEMA IF NOT EXISTS replay;

DO $$
DECLARE
    v_table REGCLASS := to_regclass('replay.report_artifacts');
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY['artifact_type', 'byte_size'];
    v_col TEXT;
    v_type_def TEXT;
BEGIN
    -- Guard A: V046 prerequisite + required columns.
    IF v_table IS NULL THEN
        RAISE EXCEPTION
            'V066 Guard A FAIL: replay.report_artifacts is missing; apply V046 before V066';
    END IF;

    FOREACH v_col IN ARRAY v_required_cols LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'replay'
               AND table_name = 'report_artifacts'
               AND column_name = v_col
        ) THEN
            v_missing_cols := array_append(v_missing_cols, v_col);
        END IF;
    END LOOP;

    IF array_length(v_missing_cols, 1) > 0 THEN
        RAISE EXCEPTION
            'V066 Guard A FAIL: replay.report_artifacts missing required columns: %',
            array_to_string(v_missing_cols, ', ');
    END IF;

    -- Guard B: upgrade artifact_type CHECK from the V046 5-value enum to the
    -- V066 6-value enum. Legacy pnl_summary remains accepted for old rows and
    -- reports; new finalize rows use replay_report.
    SELECT pg_get_constraintdef(c.oid)
      INTO v_type_def
      FROM pg_constraint c
     WHERE c.conrelid = v_table
       AND c.conname = 'chk_replay_report_artifacts_type';

    IF v_type_def IS NULL THEN
        ALTER TABLE replay.report_artifacts
            ADD CONSTRAINT chk_replay_report_artifacts_type
            CHECK (artifact_type IN (
                'canary', 'diagnostic', 'pnl_summary', 'replay_report',
                'fill_log', 'baseline_compare'
            ));
        RAISE NOTICE 'V066: added artifact_type CHECK with replay_report';
    ELSIF position('replay_report' IN v_type_def) = 0 THEN
        ALTER TABLE replay.report_artifacts
            DROP CONSTRAINT chk_replay_report_artifacts_type;
        ALTER TABLE replay.report_artifacts
            ADD CONSTRAINT chk_replay_report_artifacts_type
            CHECK (artifact_type IN (
                'canary', 'diagnostic', 'pnl_summary', 'replay_report',
                'fill_log', 'baseline_compare'
            ));
        RAISE NOTICE 'V066: upgraded artifact_type CHECK with replay_report';
    ELSE
        RAISE NOTICE 'V066: artifact_type CHECK already includes replay_report';
    END IF;

    -- Guard B: byte_size is an accounting input and must never be negative.
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
         WHERE c.conrelid = v_table
           AND c.conname = 'chk_replay_report_artifacts_byte_size_nonnegative'
    ) THEN
        ALTER TABLE replay.report_artifacts
            ADD CONSTRAINT chk_replay_report_artifacts_byte_size_nonnegative
            CHECK (byte_size >= 0);
        RAISE NOTICE 'V066: added byte_size non-negative CHECK';
    ELSE
        RAISE NOTICE 'V066: byte_size non-negative CHECK already present';
    END IF;
END $$;

COMMENT ON CONSTRAINT chk_replay_report_artifacts_type
    ON replay.report_artifacts IS
'Artifact type enum: canary / diagnostic / pnl_summary / replay_report / fill_log / baseline_compare. replay_report is the explicit finalize artifact; pnl_summary remains legacy-readable.';

COMMENT ON CONSTRAINT chk_replay_report_artifacts_byte_size_nonnegative
    ON replay.report_artifacts IS
'Storage accounting guard: artifact byte_size must be non-negative.';

COMMENT ON COLUMN replay.report_artifacts.artifact_type IS
'Enum: canary / diagnostic / pnl_summary / replay_report / fill_log / baseline_compare. CHECK chk_replay_report_artifacts_type enforces.';
