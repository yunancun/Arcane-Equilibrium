-- ============================================================
-- V075: W-AUDIT-4 retention + compression policy correction
--
-- F-22 originally called for "9 table retention policies". Live schema audit
-- showed that target set is mixed:
--   - 5 Timescale hypertables: trading.risk_verdicts, trading.position_snapshots,
--     trading.signals, trading.order_state_changes, trading.intents
--   - 2 plain tables: learning.decision_features, trading.decision_outcomes
--   - 2 views: learning.scorer_training_features, learning.mlde_edge_training_rows
--
-- TimescaleDB add_retention_policy only applies to hypertables. This migration
-- therefore installs Timescale policies only on the 5 real hypertables and adds
-- a dry-run-default prune function for the 2 plain tables. Views inherit
-- retention through their base tables and must not receive retention policies.
--
-- Do not deploy V075 ahead of the rest of the W-AUDIT-4 migration set unless
-- the operator explicitly accepts the resulting migration version ordering.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: TimescaleDB extension missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'trading'
          AND hypertable_name = 'risk_verdicts'
    ) THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: trading.risk_verdicts is not a hypertable';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'trading'
          AND hypertable_name = 'position_snapshots'
    ) THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: trading.position_snapshots is not a hypertable';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'trading'
          AND hypertable_name = 'signals'
    ) THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: trading.signals is not a hypertable';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'trading'
          AND hypertable_name = 'order_state_changes'
    ) THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: trading.order_state_changes is not a hypertable';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'trading'
          AND hypertable_name = 'intents'
    ) THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: trading.intents is not a hypertable';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'learning'
          AND c.relname = 'scorer_training_features'
          AND c.relkind = 'v'
    ) THEN
        RAISE EXCEPTION
            'V075 Guard A FAIL: learning.scorer_training_features must be a view, not a retention-policy target';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'learning'
          AND c.relname = 'mlde_edge_training_rows'
          AND c.relkind = 'v'
    ) THEN
        RAISE EXCEPTION
            'V075 Guard A FAIL: learning.mlde_edge_training_rows must be a view, not a retention-policy target';
    END IF;

    IF to_regclass('learning.decision_features') IS NULL THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: learning.decision_features missing';
    END IF;

    IF to_regclass('trading.decision_outcomes') IS NULL THEN
        RAISE EXCEPTION 'V075 Guard A FAIL: trading.decision_outcomes missing';
    END IF;

    IF EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'learning'
          AND hypertable_name = 'decision_features'
    ) THEN
        RAISE EXCEPTION
            'V075 Guard A FAIL: learning.decision_features unexpectedly hypertable; use Timescale retention instead of plain prune function';
    END IF;

    IF EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'trading'
          AND hypertable_name = 'decision_outcomes'
    ) THEN
        RAISE EXCEPTION
            'V075 Guard A FAIL: trading.decision_outcomes unexpectedly hypertable; use Timescale retention instead of plain prune function';
    END IF;
END
$$;

-- Hypertable policies.
-- risk_verdicts is the highest-volume table in this set; shrink future chunks,
-- compress after 7d, and retain 30d.
SELECT set_chunk_time_interval('trading.risk_verdicts', INTERVAL '1 day');
ALTER TABLE trading.risk_verdicts SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, engine_mode'
);
SELECT remove_compression_policy('trading.risk_verdicts', if_exists => TRUE);
SELECT add_compression_policy('trading.risk_verdicts', INTERVAL '7 days', if_not_exists => TRUE);
SELECT remove_retention_policy('trading.risk_verdicts', if_exists => TRUE);
SELECT add_retention_policy('trading.risk_verdicts', INTERVAL '30 days', if_not_exists => TRUE);

ALTER TABLE trading.position_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, engine_mode'
);
SELECT remove_compression_policy('trading.position_snapshots', if_exists => TRUE);
SELECT add_compression_policy('trading.position_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
SELECT remove_retention_policy('trading.position_snapshots', if_exists => TRUE);
SELECT add_retention_policy('trading.position_snapshots', INTERVAL '90 days', if_not_exists => TRUE);

-- trading.signals already has DB-RUN-7 2d compression; only shorten retention.
SELECT remove_retention_policy('trading.signals', if_exists => TRUE);
SELECT add_retention_policy('trading.signals', INTERVAL '90 days', if_not_exists => TRUE);

ALTER TABLE trading.order_state_changes SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'engine_mode'
);
SELECT remove_compression_policy('trading.order_state_changes', if_exists => TRUE);
SELECT add_compression_policy('trading.order_state_changes', INTERVAL '14 days', if_not_exists => TRUE);
SELECT remove_retention_policy('trading.order_state_changes', if_exists => TRUE);
SELECT add_retention_policy('trading.order_state_changes', INTERVAL '60 days', if_not_exists => TRUE);

-- trading.intents already has 14d compression; only shorten retention.
SELECT remove_retention_policy('trading.intents', if_exists => TRUE);
SELECT add_retention_policy('trading.intents', INTERVAL '90 days', if_not_exists => TRUE);

-- Plain-table retention helper. Dry-run is the default; callers must pass
-- p_apply=true to delete. This intentionally excludes the two views.
CREATE OR REPLACE FUNCTION learning.prune_w_audit4_plain_retention(
    p_decision_features_retention_days INTEGER DEFAULT 90,
    p_decision_outcomes_retention_days INTEGER DEFAULT 180,
    p_apply BOOLEAN DEFAULT false,
    p_max_rows INTEGER DEFAULT NULL
)
RETURNS TABLE(
    target_table TEXT,
    retention_days INTEGER,
    cutoff_ts TIMESTAMPTZ,
    candidate_count BIGINT,
    deleted_count BIGINT
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_decision_features_cutoff TIMESTAMPTZ;
    v_decision_outcomes_cutoff TIMESTAMPTZ;
    v_decision_features_candidates BIGINT;
    v_decision_outcomes_candidates BIGINT;
    v_decision_features_deleted BIGINT := 0;
    v_decision_outcomes_deleted BIGINT := 0;
    v_max_rows_effective INTEGER;
BEGIN
    IF p_decision_features_retention_days < 30 THEN
        RAISE EXCEPTION
            'V075 prune_w_audit4_plain_retention: decision_features retention % days is below 30-day safety floor',
            p_decision_features_retention_days;
    END IF;

    IF p_decision_outcomes_retention_days < 90 THEN
        RAISE EXCEPTION
            'V075 prune_w_audit4_plain_retention: decision_outcomes retention % days is below 90-day safety floor',
            p_decision_outcomes_retention_days;
    END IF;

    v_max_rows_effective := COALESCE(p_max_rows, 100000);
    IF v_max_rows_effective < 1 THEN
        RAISE EXCEPTION
            'V075 prune_w_audit4_plain_retention: p_max_rows must be positive when provided';
    END IF;

    IF v_max_rows_effective > 100000 THEN
        v_max_rows_effective := 100000;
    END IF;

    v_decision_features_cutoff := now() - make_interval(days => p_decision_features_retention_days);
    v_decision_outcomes_cutoff := now() - make_interval(days => p_decision_outcomes_retention_days);

    SELECT count(*)
    INTO v_decision_features_candidates
    FROM learning.decision_features
    WHERE ts < v_decision_features_cutoff;

    SELECT count(*)
    INTO v_decision_outcomes_candidates
    FROM trading.decision_outcomes
    WHERE backfilled_ts IS NOT NULL
      AND backfilled_ts < v_decision_outcomes_cutoff
      AND engine_mode <> 'live';

    IF p_apply THEN
        WITH doomed AS (
            SELECT context_id
            FROM learning.decision_features
            WHERE ts < v_decision_features_cutoff
            ORDER BY ts ASC
            LIMIT v_max_rows_effective
        )
        DELETE FROM learning.decision_features d
        USING doomed
        WHERE d.context_id = doomed.context_id;

        GET DIAGNOSTICS v_decision_features_deleted = ROW_COUNT;

        WITH doomed AS (
            SELECT context_id
            FROM trading.decision_outcomes
            WHERE backfilled_ts IS NOT NULL
              AND backfilled_ts < v_decision_outcomes_cutoff
              AND engine_mode <> 'live'
            ORDER BY backfilled_ts ASC
            LIMIT v_max_rows_effective
        )
        DELETE FROM trading.decision_outcomes d
        USING doomed
        WHERE d.context_id = doomed.context_id;

        GET DIAGNOSTICS v_decision_outcomes_deleted = ROW_COUNT;
    END IF;

    RETURN QUERY SELECT
        'learning.decision_features'::TEXT,
        p_decision_features_retention_days,
        v_decision_features_cutoff,
        v_decision_features_candidates,
        v_decision_features_deleted;

    RETURN QUERY SELECT
        'trading.decision_outcomes'::TEXT,
        p_decision_outcomes_retention_days,
        v_decision_outcomes_cutoff,
        v_decision_outcomes_candidates,
        v_decision_outcomes_deleted;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning'
          AND p.proname = 'prune_w_audit4_plain_retention'
          AND p.pronargs = 4
    ) THEN
        RAISE EXCEPTION 'V075 Guard C FAIL: learning.prune_w_audit4_plain_retention function missing';
    END IF;

    RAISE NOTICE 'V075: W-AUDIT-4 retention/compression policy source installed';
END
$$;
