-- ============================================================
-- V073: edge_estimate_snapshots cycle-writer contract guard
--
-- W-AUDIT-4 F-edge-cycle wires a recurring writer around the existing
-- REF-21 V059 edge snapshot table. The writer source lives in
-- helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh and reuses
-- helper_scripts/db/ref21_backfill_v058_v059.py with instruments/freeze-log
-- disabled so it only writes V059 snapshots.
--
-- This migration is a read-only contract guard. It verifies the V059 table
-- shape needed by the cycle writer and replay readers; it does not schedule
-- cron, apply rows, or mutate runtime state.
-- ============================================================

DO $$
DECLARE
    v_missing TEXT[];
    v_col TEXT;
BEGIN
    IF to_regclass('learning.edge_estimate_snapshots') IS NULL THEN
        RAISE EXCEPTION 'V073 Guard A FAIL: learning.edge_estimate_snapshots missing; V059 must run before V073';
    END IF;

    v_missing := ARRAY[]::TEXT[];
    FOREACH v_col IN ARRAY ARRAY[
        'asof_ts',
        'source_tier',
        'config_hash',
        'strategy_hash',
        'scanner_config_hash',
        'symbol',
        'strategy',
        'regime_key',
        'cell_key',
        'estimate_payload_hash',
        'estimate_payload_jsonb',
        'is_deprecated_at_asof',
        'deprecated_reason',
        'retention_until'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name = 'edge_estimate_snapshots'
              AND column_name = v_col
        ) THEN
            v_missing := array_append(v_missing, v_col);
        END IF;
    END LOOP;

    IF cardinality(v_missing) > 0 THEN
        RAISE EXCEPTION
            'V073 Guard A FAIL: learning.edge_estimate_snapshots missing required columns: %',
            array_to_string(v_missing, ', ');
    END IF;
END
$$;

DO $$
DECLARE
    v_pk_exists BOOLEAN;
    v_retention_check_exists BOOLEAN;
    v_symbol_index_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = 'learning.edge_estimate_snapshots'::regclass
          AND c.contype = 'p'
          AND pg_get_constraintdef(c.oid) LIKE '%asof_ts%'
          AND pg_get_constraintdef(c.oid) LIKE '%strategy_hash%'
          AND pg_get_constraintdef(c.oid) LIKE '%scanner_config_hash%'
          AND pg_get_constraintdef(c.oid) LIKE '%symbol%'
          AND pg_get_constraintdef(c.oid) LIKE '%strategy%'
          AND pg_get_constraintdef(c.oid) LIKE '%regime_key%'
          AND pg_get_constraintdef(c.oid) LIKE '%cell_key%'
    ) INTO v_pk_exists;

    SELECT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = 'learning.edge_estimate_snapshots'::regclass
          AND c.contype = 'c'
          AND pg_get_constraintdef(c.oid) LIKE '%retention_until%'
          AND pg_get_constraintdef(c.oid) LIKE '%75 days%'
    ) INTO v_retention_check_exists;

    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'learning'
          AND tablename = 'edge_estimate_snapshots'
          AND indexname = 'idx_edge_estimate_snapshots_symbol_strategy_asof'
    ) INTO v_symbol_index_exists;

    IF NOT v_pk_exists OR NOT v_retention_check_exists OR NOT v_symbol_index_exists THEN
        RAISE EXCEPTION
            'V073 Guard B FAIL: edge snapshot contract incomplete pk=% retention_check=% symbol_index=%',
            v_pk_exists, v_retention_check_exists, v_symbol_index_exists;
    END IF;

    RAISE NOTICE 'V073 Guard PASS: V059 edge_estimate_snapshots contract supports cycle writer';
END
$$;
