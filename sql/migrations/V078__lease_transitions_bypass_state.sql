-- ============================================================
-- V078: learning.lease_transitions BYPASS facade state
--
-- P0-NEW-VULN-2 showed that Validation / Exploration lease bypasses could
-- make the writer look idle at runtime even when the facade was active. V078
-- keeps bypass as infrastructure, not a hard gate: it widens the V054
-- to_state CHECK to accept the synthetic facade state "BYPASS" while leaving
-- the nine real SM states unchanged.
-- ============================================================

DO $$
DECLARE
    v_bad_count BIGINT;
    v_bad_states TEXT;
    v_constraint_def TEXT;
BEGIN
    IF to_regclass('learning.lease_transitions') IS NULL THEN
        RAISE EXCEPTION 'V078 Guard A FAIL: learning.lease_transitions missing; V054 must deploy first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'lease_transitions'
          AND column_name = 'to_state'
          AND data_type = 'text'
          AND is_nullable = 'NO'
    ) THEN
        RAISE EXCEPTION 'V078 Guard A FAIL: learning.lease_transitions.to_state missing, nullable, or not TEXT';
    END IF;

    SELECT COALESCE(SUM(row_count), 0), COALESCE(string_agg(state_count, ', ' ORDER BY to_state), '')
    INTO v_bad_count, v_bad_states
    FROM (
        SELECT
            to_state,
            count(*) AS row_count,
            format('%s=%s', to_state, count(*)) AS state_count
        FROM learning.lease_transitions
        WHERE to_state NOT IN (
            'DRAFT', 'REGISTERED', 'ACTIVE', 'BRIDGED',
            'FROZEN', 'REVOKED', 'EXPIRED', 'REJECTED', 'CONSUMED',
            'BYPASS'
        )
        GROUP BY to_state
    ) invalid_states;

    IF v_bad_count > 0 THEN
        RAISE EXCEPTION
            'V078 Guard B FAIL: learning.lease_transitions has unsupported to_state rows: %',
            v_bad_states;
    END IF;

    SELECT pg_get_constraintdef(oid)
    INTO v_constraint_def
    FROM pg_constraint
    WHERE conrelid = 'learning.lease_transitions'::regclass
      AND conname = 'chk_lease_transitions_to_state'
      AND contype = 'c';

    IF v_constraint_def IS NOT NULL AND v_constraint_def ILIKE '%BYPASS%' THEN
        RAISE NOTICE 'V078: chk_lease_transitions_to_state already accepts BYPASS; skipping';
    ELSE
        LOCK TABLE learning.lease_transitions IN ACCESS EXCLUSIVE MODE;

        IF v_constraint_def IS NOT NULL THEN
            ALTER TABLE learning.lease_transitions
                DROP CONSTRAINT chk_lease_transitions_to_state;
        END IF;

        ALTER TABLE learning.lease_transitions
            ADD CONSTRAINT chk_lease_transitions_to_state
            CHECK (to_state IN (
                'DRAFT', 'REGISTERED', 'ACTIVE', 'BRIDGED',
                'FROZEN', 'REVOKED', 'EXPIRED', 'REJECTED', 'CONSUMED',
                'BYPASS'
            ))
            NOT VALID;

        ALTER TABLE learning.lease_transitions
            VALIDATE CONSTRAINT chk_lease_transitions_to_state;

        RAISE NOTICE 'V078: chk_lease_transitions_to_state widened with BYPASS facade state';
    END IF;
END
$$;
