-- ============================================================
-- V077: trading.fills engine_mode archive-label CHECK
--
-- F-29 standardizes the known 2026-04-18 demo archive label without allowing
-- it to become a future runtime mode. Canonical runtime values remain:
-- paper, demo, live, live_demo.
--
-- The archive label is only accepted for rows before 2026-04-19 CEST
-- (2026-04-18 22:00:00Z), matching the audited live distribution.
--
-- Do not deploy V077 ahead of the rest of the W-AUDIT-4 migration set unless
-- the operator explicitly accepts the resulting migration version ordering.
-- ============================================================

DO $$
DECLARE
    v_bad_count BIGINT;
    v_bad_modes TEXT;
    v_constraint_def TEXT;
BEGIN
    IF to_regclass('trading.fills') IS NULL THEN
        RAISE EXCEPTION 'V077 Guard A FAIL: trading.fills missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'trading'
          AND table_name = 'fills'
          AND column_name = 'engine_mode'
          AND data_type = 'text'
          AND is_nullable = 'NO'
    ) THEN
        RAISE EXCEPTION
            'V077 Guard A FAIL: trading.fills.engine_mode missing, nullable, or not TEXT';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'trading'
          AND table_name = 'fills'
          AND column_name = 'ts'
          AND data_type = 'timestamp with time zone'
    ) THEN
        RAISE EXCEPTION
            'V077 Guard A FAIL: trading.fills.ts missing or not TIMESTAMPTZ';
    END IF;

    SELECT COALESCE(SUM(row_count), 0), COALESCE(string_agg(mode_count, ', ' ORDER BY engine_mode), '')
    INTO v_bad_count, v_bad_modes
    FROM (
        SELECT
            engine_mode,
            count(*) AS row_count,
            format('%s=%s', engine_mode, count(*)) AS mode_count
        FROM trading.fills
        WHERE NOT (
            engine_mode IN ('paper', 'demo', 'live', 'live_demo')
            OR (
                engine_mode = 'demo_archive_20260418'
                AND ts < TIMESTAMPTZ '2026-04-18 22:00:00+00'
            )
        )
        GROUP BY engine_mode
    ) invalid_modes;

    IF v_bad_count > 0 THEN
        RAISE EXCEPTION
            'V077 Guard B FAIL: trading.fills has unsupported engine_mode rows: %',
            v_bad_modes;
    END IF;

    SELECT pg_get_constraintdef(oid)
    INTO v_constraint_def
    FROM pg_constraint
    WHERE conrelid = 'trading.fills'::regclass
      AND conname = 'chk_fills_engine_mode_known_values'
      AND contype = 'c';

    IF v_constraint_def IS NOT NULL THEN
        IF v_constraint_def ILIKE '%demo_archive_20260418%'
           AND v_constraint_def ILIKE '%live_demo%'
           AND (
               v_constraint_def ILIKE '%2026-04-18%'
               OR v_constraint_def ILIKE '%2026-04-19%'
           ) THEN
            RAISE NOTICE 'V077: chk_fills_engine_mode_known_values already present; skipping';
        ELSE
            RAISE EXCEPTION
                'V077 Guard C FAIL: chk_fills_engine_mode_known_values exists with unexpected definition: %',
                v_constraint_def;
        END IF;
    ELSE
        ALTER TABLE trading.fills
            ADD CONSTRAINT chk_fills_engine_mode_known_values
            CHECK (
                engine_mode IN ('paper', 'demo', 'live', 'live_demo')
                OR (
                    engine_mode = 'demo_archive_20260418'
                    AND ts < TIMESTAMPTZ '2026-04-18 22:00:00+00'
                )
            )
            NOT VALID;

        ALTER TABLE trading.fills
            VALIDATE CONSTRAINT chk_fills_engine_mode_known_values;

        RAISE NOTICE 'V077: added and validated chk_fills_engine_mode_known_values';
    END IF;
END
$$;
