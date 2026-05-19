-- ============================================================
-- V097: LG-5 attribution healthcheck join indexes
--
-- Context:
--   [42b]/[42c] passive_wait_healthcheck needs a fast, exact proof that a
--   settled learning.decision_features row still has an intent -> signal
--   attribution chain:
--
--       decision_features.context_id
--         -> trading.intents.context_id + signal_id
--         -> trading.signals.signal_id + context_id
--
--   V005/V015 only indexed trading.intents by symbol / engine_mode+ts and
--   trading.signals by symbol / strategy. On production trade-core the
--   healthcheck query timed out when it tried to prove attribution by
--   context_id, even though the underlying label scan was fast. This migration
--   adds the missing narrow indexes instead of weakening the healthcheck.
--
-- 中文:
--   [42b]/[42c] 需要快速驗證已結算 decision_features row 的歸因鏈：
--   context_id 找 intent，再由 signal_id + context_id 找 signal。既有索引只
--   覆蓋 symbol / engine_mode+ts / strategy，沒有 context_id 熱路徑，導致
--   trade-core 真實 timeout。本 migration 補索引，不放寬哨兵。
--
-- Invariants:
--   - Additive only: no table/column mutation, no data rewrite.
--   - Partial indexes exclude NULL context_id rows; those rows cannot satisfy
--     attribution_chain_ok anyway.
--   - Idempotent through CREATE INDEX IF NOT EXISTS.
-- ============================================================

BEGIN;

-- ============================================================
-- Guard A: required tables/columns exist before adding hot-path indexes.
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    SELECT array_agg(req.label ORDER BY req.label) INTO v_missing
    FROM (
        VALUES
            ('learning.decision_features.context_id', 'learning', 'decision_features', 'context_id'),
            ('learning.decision_features.ts', 'learning', 'decision_features', 'ts'),
            ('learning.decision_features.engine_mode', 'learning', 'decision_features', 'engine_mode'),
            ('learning.decision_features.strategy_name', 'learning', 'decision_features', 'strategy_name'),
            ('learning.decision_features.label_net_edge_bps', 'learning', 'decision_features', 'label_net_edge_bps'),
            ('trading.intents.context_id', 'trading', 'intents', 'context_id'),
            ('trading.intents.signal_id', 'trading', 'intents', 'signal_id'),
            ('trading.intents.ts', 'trading', 'intents', 'ts'),
            ('trading.intents.engine_mode', 'trading', 'intents', 'engine_mode'),
            ('trading.intents.details', 'trading', 'intents', 'details'),
            ('trading.signals.signal_id', 'trading', 'signals', 'signal_id'),
            ('trading.signals.context_id', 'trading', 'signals', 'context_id'),
            ('trading.signals.ts', 'trading', 'signals', 'ts')
    ) AS req(label, schema_name, table_name, column_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.columns c
        WHERE c.table_schema = req.schema_name
          AND c.table_name = req.table_name
          AND c.column_name = req.column_name
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V097 Guard A FAIL: missing required attribution healthcheck column(s): %',
            v_missing;
    END IF;
END $$;

-- [42b]/[42c] lateral lookup:
--   learning.decision_features.context_id -> latest matching trading.intents row.
CREATE INDEX IF NOT EXISTS idx_intents_context_mode_ts
    ON trading.intents (context_id, engine_mode, ts DESC)
    WHERE context_id IS NOT NULL;

-- [42b]/[42c] attribution proof:
--   trading.intents.signal_id + context_id -> trading.signals.
CREATE INDEX IF NOT EXISTS idx_signals_signal_context_ts
    ON trading.signals (signal_id, context_id, ts DESC)
    WHERE context_id IS NOT NULL;

COMMENT ON INDEX idx_intents_context_mode_ts IS
    'V097: accelerates LG-5 [42b]/[42c] attribution healthcheck context_id -> intent lookup.';
COMMENT ON INDEX idx_signals_signal_context_ts IS
    'V097: accelerates LG-5 [42b]/[42c] attribution healthcheck signal_id + context_id proof.';

COMMIT;
