-- V034: Expose scanner market-judgment context to MLDE.
-- V034：將 scanner 趨勢/fitness context 暴露給 MLDE。
--
-- Scope:
--   * Recreate learning.mlde_edge_training_rows with the same V031 column
--     order, appending scanner context columns at the end for PostgreSQL
--     CREATE OR REPLACE VIEW compatibility.
--   * No execution gate, no live mutation, no trading-path side effect.
--
-- Hard boundary:
--   ML/Dream outputs remain advisory. These fields are learning/explainability
--   features only and must not bypass GovernanceHub or Decision Lease.

CREATE SCHEMA IF NOT EXISTS learning;

CREATE OR REPLACE FUNCTION learning.mlde_try_float8(value TEXT, fallback DOUBLE PRECISION DEFAULT NULL)
RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF value IS NULL OR btrim(value) = '' THEN
        RETURN fallback;
    END IF;
    RETURN value::double precision;
EXCEPTION WHEN others THEN
    RETURN fallback;
END
$$;

CREATE OR REPLACE VIEW learning.mlde_edge_training_rows AS
WITH intent_base AS (
    SELECT
        i.ts,
        floor(extract(epoch FROM i.ts) * 1000.0)::bigint AS ts_ms,
        i.engine_mode,
        i.intent_id,
        i.signal_id,
        i.context_id,
        i.symbol,
        i.side,
        i.qty,
        i.price,
        i.order_type,
        i.strategy_name AS intent_strategy_name,
        i.details AS intent_details,
        i.details->'scanner' AS scanner_json,
        df.strategy_name AS feature_strategy_name,
        df.side AS feature_side,
        df.features_jsonb,
        df.label_net_edge_bps,
        df.label_close_tag,
        df.label_split_flag,
        df.label_filled_at,
        sig.context_id AS signal_context_id,
        sig.strategy_name AS signal_strategy_name,
        dcs.regime_5m,
        dcs.ind_5m_adx,
        dcs.ind_5m_rsi,
        dcs.ind_5m_atr_14_pct,
        dcs.spread_bps,
        dcs.indicators_snapshot,
        dcs.decision_payload
    FROM trading.intents i
    LEFT JOIN learning.decision_features df
      ON df.context_id = i.context_id
    LEFT JOIN LATERAL (
        SELECT s.context_id, s.strategy_name
        FROM trading.signals s
        WHERE s.signal_id = i.signal_id
        ORDER BY s.ts DESC
        LIMIT 1
    ) sig ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            d.context_id,
            d.regime_5m,
            d.ind_5m_adx,
            d.ind_5m_rsi,
            d.ind_5m_atr_14_pct,
            d.spread_bps,
            d.indicators_snapshot,
            d.decision_payload
        FROM trading.decision_context_snapshots d
        WHERE d.context_id = i.context_id
        ORDER BY d.ts DESC
        LIMIT 1
    ) dcs ON TRUE
    WHERE i.engine_mode IN ('demo', 'live_demo', 'live')
      AND COALESCE(i.details->>'source', '') <> 'command'
),
normalized AS (
    SELECT
        b.*,
        COALESCE(
            NULLIF(b.intent_strategy_name, ''),
            NULLIF(b.feature_strategy_name, ''),
            NULLIF(b.signal_strategy_name, ''),
            NULLIF(b.scanner_json->>'best_strategy', '')
        ) AS raw_strategy_name,
        lower(COALESCE(b.scanner_json->>'route_mode', 'unknown')) AS scanner_route_mode,
        lower(COALESCE(b.scanner_json->>'edge_status', 'unknown')) AS scanner_edge_status,
        NULLIF(b.scanner_json->>'scan_id', '') AS scanner_scan_id,
        NULLIF(b.scanner_json->>'best_strategy', '') AS scanner_best_strategy,
        learning.mlde_try_float8(b.scanner_json->>'edge_bps') AS scanner_edge_bps,
        learning.mlde_try_float8(b.scanner_json->>'edge_n') AS scanner_edge_n,
        learning.mlde_try_float8(b.scanner_json->>'final_score') AS scanner_final_score,
        learning.mlde_try_float8(b.scanner_json->>'raw_score') AS scanner_raw_score,
        NULLIF(b.scanner_json->>'market_regime', '') AS scanner_market_regime,
        NULLIF(b.scanner_json->>'trend_phase', '') AS scanner_trend_phase,
        learning.mlde_try_float8(b.scanner_json->>'trend_score') AS scanner_trend_score,
        learning.mlde_try_float8(b.scanner_json->>'range_score') AS scanner_range_score,
        learning.mlde_try_float8(b.scanner_json->>'shock_score') AS scanner_shock_score,
        learning.mlde_try_float8(b.scanner_json->>'close_alignment') AS scanner_close_alignment,
        learning.mlde_try_float8(b.scanner_json->>'range_position') AS scanner_range_position,
        learning.mlde_try_float8(b.scanner_json->>'crowding_score') AS scanner_crowding_score,
        learning.mlde_try_float8(b.scanner_json->>'reversal_risk_score') AS scanner_reversal_risk_score,
        learning.mlde_try_float8(b.scanner_json->>'directional_efficiency') AS scanner_directional_efficiency,
        learning.mlde_try_float8(b.scanner_json->>'dir_pct') AS scanner_dir_pct,
        learning.mlde_try_float8(b.scanner_json->>'signed_dir_pct') AS scanner_signed_dir_pct,
        learning.mlde_try_float8(b.scanner_json->>'range_pct') AS scanner_range_pct,
        learning.mlde_try_float8(b.scanner_json->>'fr_bps') AS scanner_fr_bps,
        learning.mlde_try_float8(b.scanner_json->>'f_ma') AS scanner_f_ma,
        learning.mlde_try_float8(b.scanner_json->>'f_grid') AS scanner_f_grid,
        learning.mlde_try_float8(b.scanner_json->>'f_bbrv') AS scanner_f_bbrv,
        learning.mlde_try_float8(b.scanner_json->>'f_bkout') AS scanner_f_bkout,
        learning.mlde_try_float8(b.scanner_json->>'f_funding_arb') AS scanner_f_funding_arb,
        CASE
            WHEN b.symbol IN ('BTCUSDT', 'BTCUSD') THEN 'btc'
            WHEN b.symbol IN ('ETHUSDT', 'ETHUSD') THEN 'eth'
            WHEN b.symbol LIKE 'SOL%' THEN 'sol'
            WHEN b.symbol LIKE 'XRP%' THEN 'xrp'
            WHEN b.symbol LIKE 'DOGE%' THEN 'doge'
            ELSE 'alt'
        END AS symbol_bucket
    FROM intent_base b
),
strategy_regime AS (
    SELECT
        n.*,
        CASE lower(COALESCE(n.raw_strategy_name, ''))
            WHEN 'bollinger_reversion' THEN 'bb_reversion'
            WHEN 'bb_reversion' THEN 'bb_reversion'
            WHEN 'bb_breakout' THEN 'bb_breakout'
            WHEN 'ma_crossover' THEN 'ma_crossover'
            WHEN 'grid_trading' THEN 'grid_trading'
            WHEN 'funding_arb' THEN 'funding_arb'
            ELSE lower(COALESCE(n.raw_strategy_name, 'unknown'))
        END AS strategy_name_norm,
        CASE
            WHEN lower(COALESCE(n.regime_5m, '')) LIKE '%trend%' THEN 'trending'
            WHEN lower(COALESCE(n.regime_5m, '')) LIKE '%mean%'
              OR lower(COALESCE(n.regime_5m, '')) LIKE '%range%'
              OR lower(COALESCE(n.regime_5m, '')) LIKE '%anti%' THEN 'mean_reverting'
            WHEN lower(COALESCE(n.raw_strategy_name, '')) IN ('grid_trading', 'bb_reversion', 'bollinger_reversion') THEN 'mean_reverting'
            WHEN lower(COALESCE(n.raw_strategy_name, '')) IN ('ma_crossover', 'bb_breakout') THEN 'trending'
            ELSE 'random_walk'
        END AS regime_norm
    FROM normalized n
)
SELECT
    sr.ts,
    sr.ts_ms,
    sr.engine_mode,
    sr.intent_id,
    sr.signal_id,
    sr.context_id,
    sr.symbol,
    sr.symbol_bucket,
    sr.side,
    COALESCE(sr.feature_side, CASE WHEN lower(sr.side) = 'sell' THEN -1 ELSE 1 END) AS side_num,
    sr.qty,
    sr.price,
    sr.order_type,
    sr.strategy_name_norm AS strategy_name,
    sr.regime_norm AS regime,
    sr.scanner_scan_id,
    sr.scanner_best_strategy,
    sr.scanner_route_mode,
    sr.scanner_edge_status,
    sr.scanner_edge_bps,
    sr.scanner_edge_n,
    sr.scanner_final_score,
    sr.scanner_raw_score,
    sr.label_net_edge_bps AS net_bps_after_fee,
    sr.label_close_tag,
    sr.label_split_flag,
    sr.label_filled_at,
    sr.features_jsonb,
    jsonb_build_array(
        LEAST(GREATEST(COALESCE(sr.ind_5m_atr_14_pct::double precision, 0.5), 0.0), 1.0),
        LEAST(GREATEST(COALESCE(sr.ind_5m_rsi::double precision, 50.0) / 100.0, 0.0), 1.0),
        LEAST(GREATEST(COALESCE(learning.mlde_try_float8(sr.features_jsonb->>'bb_width_pct'), 0.5), 0.0), 5.0),
        LEAST(GREATEST(COALESCE(learning.mlde_try_float8(sr.features_jsonb->>'hurst_h'), 0.5), 0.0), 1.0),
        LEAST(GREATEST(COALESCE(sr.ind_5m_adx::double precision, 25.0), 0.0), 100.0) / 100.0,
        LEAST(GREATEST(COALESCE(learning.mlde_try_float8(sr.features_jsonb->>'volume_ratio'), 1.0), 0.0), 5.0),
        sin(2.0 * pi() * ((sr.ts_ms % 86400000)::double precision / 86400000.0)),
        cos(2.0 * pi() * ((sr.ts_ms % 86400000)::double precision / 86400000.0))
    ) AS context_features,
    CASE
        WHEN sr.strategy_name_norm IN ('ma_crossover', 'bb_breakout', 'bb_reversion', 'grid_trading', 'funding_arb')
        THEN sr.regime_norm || '__' || sr.strategy_name_norm
        ELSE NULL
    END AS linucb_arm_id,
    concat_ws(
        '__',
        sr.strategy_name_norm,
        sr.symbol_bucket,
        sr.regime_norm,
        COALESCE(NULLIF(sr.scanner_route_mode, ''), 'unknown'),
        COALESCE(NULLIF(sr.scanner_edge_status, ''), 'unknown')
    ) AS mlde_arm_id,
    (sr.signal_id IS NOT NULL AND sr.signal_id <> ''
        AND sr.context_id IS NOT NULL AND sr.context_id <> ''
        AND sr.signal_context_id IS NOT NULL
        AND sr.signal_context_id = sr.context_id
        AND sr.label_net_edge_bps IS NOT NULL) AS attribution_chain_ok,
    CASE
        WHEN sr.ts >= TIMESTAMPTZ '2026-04-29 10:27:53+00' THEN 'post_attribution_maker_repair'
        WHEN sr.ts >= TIMESTAMPTZ '2026-04-22 21:00:00+00' THEN 'post_atr_v2_clean'
        ELSE 'legacy_pre_clean'
    END AS data_window,
    jsonb_build_object(
        'view_version', 'mlde_v2_scanner_context',
        'primary_reward', 'net_bps_after_fee',
        'attribution_chain', jsonb_build_object(
            'has_signal_id', sr.signal_id IS NOT NULL AND sr.signal_id <> '',
            'has_context_id', sr.context_id IS NOT NULL AND sr.context_id <> '',
            'signal_context_match', sr.signal_context_id = sr.context_id,
            'has_post_fee_reward', sr.label_net_edge_bps IS NOT NULL
        ),
        'scanner', COALESCE(sr.scanner_json, '{}'::jsonb)
    ) AS metadata,
    sr.scanner_market_regime,
    sr.scanner_trend_phase,
    sr.scanner_trend_score,
    sr.scanner_range_score,
    sr.scanner_shock_score,
    sr.scanner_close_alignment,
    sr.scanner_range_position,
    sr.scanner_crowding_score,
    sr.scanner_reversal_risk_score,
    sr.scanner_directional_efficiency,
    sr.scanner_dir_pct,
    sr.scanner_signed_dir_pct,
    sr.scanner_range_pct,
    sr.scanner_fr_bps,
    sr.scanner_f_ma,
    sr.scanner_f_grid,
    sr.scanner_f_bbrv,
    sr.scanner_f_bkout,
    sr.scanner_f_funding_arb
FROM strategy_regime sr;

COMMENT ON VIEW learning.mlde_edge_training_rows IS
    'ML/Dream edge-unblock training view. Valid rows require attribution_chain_ok=true and net_bps_after_fee; V034 appends scanner trend/fitness context for advisory learning.';
