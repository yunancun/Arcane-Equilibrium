-- V067__replay_run_state_subprocess_started_at_ms.sql
-- REF-20 P2-REPLAY-1 — harden replay finalize against replay_runner PID reuse.
--
-- Adds a nullable process-start timestamp captured immediately after
-- replay_runner spawn. Finalize can then verify both current cmdline and
-- process create_time before deciding that a stored PID is still the same
-- runner.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'replay'
           AND table_name = 'run_state'
    ) THEN
        RAISE EXCEPTION
            'V067 Guard A: replay.run_state not found; V045 must deploy before V067';
    END IF;
END $$;

ALTER TABLE replay.run_state
    ADD COLUMN IF NOT EXISTS subprocess_started_at_ms BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'chk_replay_run_state_subprocess_started_at_ms_positive'
           AND conrelid = 'replay.run_state'::regclass
    ) THEN
        ALTER TABLE replay.run_state
            ADD CONSTRAINT chk_replay_run_state_subprocess_started_at_ms_positive
            CHECK (
                subprocess_started_at_ms IS NULL
                OR subprocess_started_at_ms > 0
            );
    END IF;
END $$;

COMMENT ON COLUMN replay.run_state.subprocess_started_at_ms IS
'Process create_time in milliseconds for subprocess_pid, captured after '
'replay_runner spawn. Used by finalize to reject replay_runner PID reuse when '
'cmdline alone is ambiguous.';
