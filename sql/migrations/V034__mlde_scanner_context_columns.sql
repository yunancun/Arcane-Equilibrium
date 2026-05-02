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
--
-- Retrofit (AUDIT-2026-05-02-P1-1, 2026-05-02): added a view-shape guard
-- per CLAUDE.md §七 (V023 silent-noop postmortem). 4-day cold audit
-- flagged that `CREATE OR REPLACE VIEW` is restricted by Postgres in a
-- specific way: it can only **append** columns at the end and must
-- preserve the existing column order/types/names of every leading
-- column. If V031's view is somehow missing one of its original columns
-- (e.g. a manual hot-fix DROPped + recreated the view with a narrower
-- shape), V034's CREATE OR REPLACE would fail with a confusing
-- "cannot change name of view column" or "cannot drop columns from
-- view" error mid-migration. The guard below verifies V031's expected
-- column set is present on the existing view (if any), and RAISES
-- early with a clear message. If the view does not exist, CREATE OR
-- REPLACE below creates it fresh — V031 may not have been applied,
-- but that is the parallel "fresh DB" case (V031 → V034 in the same
-- run still works because V031's CREATE OR REPLACE VIEW lands first).
--
-- Why no Guard A on a base table: this migration touches only a view
-- (no CREATE TABLE) and a stable IMMUTABLE function (CREATE OR REPLACE
-- FUNCTION is atomic by design). The only drift risk is the view shape.
--
-- 回補（AUDIT-2026-05-02-P1-1，2026-05-02）：依 CLAUDE.md §七 補上 view
-- shape guard。Postgres `CREATE OR REPLACE VIEW` 的限制：只能在末尾
-- **追加**欄位、leading 欄位的 name/type/order 必須維持不變。若 V031
-- view 被手動 hot-fix 縮窄，V034 的 CREATE OR REPLACE 會在 migration
-- 中途報「cannot change name of view column」/「cannot drop columns
-- from view」。下方 guard 提前驗 V031 視為依賴的欄位集俱在於現存 view
-- （若有）；不存在則直接 CREATE 全新 view（V031 → V034 同次跑也 OK，
-- V031 的 CREATE OR REPLACE VIEW 會先 land）。本 migration 不觸表
-- （無 CREATE TABLE）、IMMUTABLE function 用 CREATE OR REPLACE 原子
-- 替換不需 guard，唯一漂移風險即 view shape。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A
--   （adapted for view; information_schema.columns also reports view cols）

CREATE SCHEMA IF NOT EXISTS learning;

-- ------------------------------------------------------------
-- Schema Guard A (view-shape variant) — verify V031 view columns when present
-- Schema Guard A（view shape 變體）— 視圖已存在時驗 V031 欄位俱在
-- ------------------------------------------------------------
-- information_schema.columns reports columns for views as well as tables;
-- table_type can be inspected via information_schema.tables.table_type IN
-- ('BASE TABLE','VIEW'). Here we only care that the column set is intact.
--
-- information_schema.columns 對 view 也有欄位記錄；這裡只關心欄位集合
-- 完整即可。
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.views
        WHERE table_schema = 'learning'
          AND table_name   = 'mlde_edge_training_rows'
    ) THEN
        -- V031 column set (the leading columns V034 must preserve in order).
        -- V031 欄位集合（V034 必須照原順序保留的 leading columns）。
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts', 'ts_ms', 'engine_mode',
            'intent_id', 'signal_id', 'context_id',
            'symbol', 'symbol_bucket', 'side', 'side_num',
            'qty', 'price', 'order_type',
            'strategy_name', 'regime',
            'scanner_scan_id', 'scanner_best_strategy',
            'scanner_route_mode', 'scanner_edge_status',
            'scanner_edge_bps', 'scanner_edge_n',
            'scanner_final_score', 'scanner_raw_score',
            'net_bps_after_fee', 'label_close_tag',
            'label_split_flag', 'label_filled_at',
            'features_jsonb', 'context_features',
            'linucb_arm_id', 'mlde_arm_id',
            'attribution_chain_ok', 'data_window', 'metadata'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'mlde_edge_training_rows'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A (view): learning.mlde_edge_training_rows exists but missing V031 columns: %. '
                'CREATE OR REPLACE VIEW below would fail because Postgres only allows appending columns. '
                'Resolve via DROP VIEW IF EXISTS + re-apply V031 then V034, or restore the missing columns.',
                v_missing;
        END IF;
    END IF;
END $$;

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
