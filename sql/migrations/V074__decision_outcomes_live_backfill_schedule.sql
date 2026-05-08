-- V074: decision_outcomes live-lane backfill schedule support
--
-- MODULE_NOTE:
--   Source-only support for W-AUDIT-4 V074. The runtime action is handled by
--   helper_scripts/db/outcome_backfiller_live.py plus its cron wrapper; this
--   migration only pins the schema contract and adds a narrow pending-scan
--   index for the live/live_demo backfill lane.
--
-- Boundary:
--   - No data backfill is performed here.
--   - No cron is installed here.
--   - No trading authority or live API state is changed.

DO $$
DECLARE
    required_cols TEXT[] := ARRAY[
        'context_id', 'outcome_1m', 'outcome_5m', 'outcome_1h',
        'outcome_4h', 'outcome_24h', 'max_favorable', 'max_adverse',
        'backfilled_ts', 'engine_mode'
    ];
    col TEXT;
BEGIN
    IF to_regclass('trading.decision_context_snapshots') IS NULL THEN
        RAISE EXCEPTION 'V074 Guard A FAIL: trading.decision_context_snapshots missing';
    END IF;
    IF to_regclass('trading.decision_outcomes') IS NULL THEN
        RAISE EXCEPTION 'V074 Guard A FAIL: trading.decision_outcomes missing';
    END IF;
    IF to_regclass('market.klines') IS NULL THEN
        RAISE EXCEPTION 'V074 Guard A FAIL: market.klines missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'trading'
          AND table_name = 'decision_context_snapshots'
          AND column_name = 'engine_mode'
    ) THEN
        RAISE EXCEPTION 'V074 Guard A FAIL: decision_context_snapshots.engine_mode missing';
    END IF;

    FOREACH col IN ARRAY required_cols LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'trading'
              AND table_name = 'decision_outcomes'
              AND column_name = col
        ) THEN
            RAISE EXCEPTION 'V074 Guard A FAIL: decision_outcomes.% missing', col;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'market'
          AND table_name = 'klines'
          AND column_name IN ('symbol', 'timeframe', 'ts', 'close', 'high', 'low')
        GROUP BY table_schema, table_name
        HAVING count(*) = 6
    ) THEN
        RAISE EXCEPTION 'V074 Guard A FAIL: market.klines OHLC contract incomplete';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_dcs_outcome_backfill_engine_pending
    ON trading.decision_context_snapshots (engine_mode, ts ASC)
    WHERE outcome_backfilled = FALSE
      AND last_price IS NOT NULL
      AND last_price > 0;

COMMENT ON INDEX trading.idx_dcs_outcome_backfill_engine_pending IS
    'V074: supports live/live_demo decision_outcomes scheduled backfill scans; source-only schedule support, no data backfill in migration.';
