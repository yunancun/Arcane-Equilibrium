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
--
-- Runtime note: on Timescale columnstore-enabled hypertables, ADD/VALIDATE
-- CHECK may return feature_not_supported. In that case this migration installs
-- a BEFORE INSERT/UPDATE trigger with the same predicate so new writes are
-- still bounded without rewriting existing rows or disabling columnstore.
-- ============================================================

CREATE OR REPLACE FUNCTION trading.enforce_fills_engine_mode_known_values()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NOT (
        NEW.engine_mode IN ('paper', 'demo', 'live', 'live_demo')
        OR (
            NEW.engine_mode = 'demo_archive_20260418'
            AND NEW.ts < TIMESTAMPTZ '2026-04-18 22:00:00+00'
        )
    ) THEN
        RAISE EXCEPTION
            'chk_fills_engine_mode_known_values violation: engine_mode=%, ts=%',
            NEW.engine_mode,
            NEW.ts
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END
$fn$;

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
        BEGIN
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
        EXCEPTION
            WHEN feature_not_supported THEN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_trigger
                    WHERE tgrelid = 'trading.fills'::regclass
                      AND tgname = 'trg_fills_engine_mode_known_values'
                      AND NOT tgisinternal
                ) THEN
                    CREATE TRIGGER trg_fills_engine_mode_known_values
                        BEFORE INSERT OR UPDATE OF engine_mode, ts ON trading.fills
                        FOR EACH ROW
                        EXECUTE FUNCTION trading.enforce_fills_engine_mode_known_values();
                END IF;

                RAISE NOTICE
                    'V077: columnstore hypertable does not support CHECK; installed trigger fallback trg_fills_engine_mode_known_values';
        END;
    END IF;
END
$$;
