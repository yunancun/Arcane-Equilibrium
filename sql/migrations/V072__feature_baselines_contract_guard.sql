-- V072: feature baseline contract guard
--
-- MODULE_NOTE:
--   W-AUDIT-4 F-16 originally proposed a feature_baselines writer sourced
--   from learning.decision_features over the last 7 days. Source/runtime audit
--   corrected that scope:
--   - observability.feature_baselines is consumed by Rust drift_detector.
--   - drift_detector maps feature_name through feature_collector::FEATURE_NAMES.
--   - feature_collector::FEATURE_NAMES is the 34-dim features.online_latest
--     vector, not the 17-dim edge_predictor/learning.decision_features vector.
--
-- Boundary:
--   This migration is a contract guard only. It does not seed baselines and it
--   does not add a writer. A future writer must derive historical
--   feature_collector-compatible 34-dim distributions before inserting rows.

DO $$
DECLARE
    v_bad_online_latest BIGINT;
    v_bad_active_baselines BIGINT;
BEGIN
    IF to_regclass('features.online_latest') IS NULL THEN
        RAISE EXCEPTION 'V072 Guard A FAIL: features.online_latest missing';
    END IF;

    IF to_regclass('observability.feature_baselines') IS NULL THEN
        RAISE EXCEPTION 'V072 Guard A FAIL: observability.feature_baselines missing';
    END IF;

    SELECT count(*)
    INTO v_bad_online_latest
    FROM features.online_latest
    WHERE feature_vector IS NOT NULL
      AND array_length(feature_vector, 1) <> 34;

    IF v_bad_online_latest <> 0 THEN
        RAISE EXCEPTION
            'V072 Guard A FAIL: features.online_latest has % row(s) with feature_vector dimension != 34',
            v_bad_online_latest;
    END IF;

    WITH allowed_feature_names(feature_name) AS (
        SELECT unnest(ARRAY[
            'sma_20',
            'sma_50',
            'ema_12',
            'ema_26',
            'rsi_14',
            'macd',
            'macd_signal',
            'macd_histogram',
            'bb_upper',
            'bb_middle',
            'bb_lower',
            'bb_bandwidth',
            'bb_percent_b',
            'atr_14',
            'atr_14_percent',
            'atr_5',
            'atr_5_percent',
            'stoch_k',
            'stoch_d',
            'kama',
            'kama_efficiency',
            'adx',
            'plus_di',
            'minus_di',
            'hurst',
            'regime_id',
            'ewma_vol',
            'vol_regime_id',
            'volume_ratio',
            'donchian_upper',
            'donchian_lower',
            'donchian_middle',
            'donchian_width',
            'price'
        ]::TEXT[])
    )
    SELECT count(*)
    INTO v_bad_active_baselines
    FROM observability.feature_baselines b
    LEFT JOIN allowed_feature_names a ON a.feature_name = b.feature_name
    WHERE b.valid_until IS NULL
      AND a.feature_name IS NULL;

    IF v_bad_active_baselines <> 0 THEN
        RAISE EXCEPTION
            'V072 Guard A FAIL: observability.feature_baselines has % active row(s) outside the 34-dim feature_collector contract',
            v_bad_active_baselines;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_feature_baselines_active_symbol_feature
    ON observability.feature_baselines (symbol, feature_name)
    WHERE valid_until IS NULL;

COMMENT ON TABLE observability.feature_baselines IS
    'PSI baseline contract for Rust feature_collector 34-dim features.online_latest vectors. Do not seed from the 17-dim edge_predictor learning.decision_features vector.';

COMMENT ON COLUMN features.online_latest.feature_vector IS
    'Rust feature_collector::FEATURE_NAMES 34-dim vector consumed by drift_detector PSI checks.';
