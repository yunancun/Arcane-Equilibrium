-- ============================================================
-- V084: W-AUDIT-4b-M3 + P0-MIT-LABEL-CLOSE-TAG-1
--   governance reject 寫 negative label + class weight handling
-- ============================================================
--
-- 動機 / Motivation:
--   2026-05-09 MIT PG 直查：trading.intents 24h 12,681 中只 175 成交（1.38%）。
--   98.6% reject 沒寫 negative label → ML training pool 67 row vs 應有 12,500+。
--
--   根因：governance / cost-gate reject 路徑（step_4_5_dispatch.rs path 1/2/3）
--   只走 record_pre_risk_rejection / push_display_intent / persist_verdict，
--   **不寫** learning.decision_features，導致：
--     1. ML training pool 樣本量缺 170×（67 fill vs 應 12,500+ reject + fill）
--     2. attribution_chain_ok 24h 0.5%（denominator 含全部 intent，numerator
--        只 fill 才有 label_net_edge_bps）
--     3. P0-MIT-LABEL-CLOSE-TAG-1 標記 attribution real root cause = label_close_tag
--        NULL 98.9%
--
--   修復鏈（應用層 + 本 migration）：
--     - Rust step_4_5_dispatch 三 reject path 呼叫
--       intent_processor.emit_decision_feature_intent_rejected
--     - 該 method emit DecisionFeatureMsg with label_close_tag='rejected_governance'
--       + label_net_edge_bps=0.0 + label_filled_at_now=true
--     - decision_feature_writer 改 INSERT 連 label 三欄位寫入（reject 變體）
--     - 本 V084 view 加 sample_weight column 防 70:1 imbalance dominance
--
-- 範圍 / Scope (V084):
--   1. UDF learning.mlde_sample_weight(close_tag TEXT) → DOUBLE PRECISION
--      回傳 1/170 (rejected_governance) | 1.0 (其他, 含 NULL 與 fill row)
--      上界 170 來自 PA spec：reject:fill = 70:1 觀察 + 100x safety margin。
--   2. CREATE OR REPLACE VIEW learning.mlde_edge_training_rows
--      重抄 V034 view + 加 sample_weight 欄位（沿用 UDF 計算）
--      其他 schema / WHERE / 計算邏輯零變動，下游 query 不破。
--   3. Guard A：確認 learning.decision_features 已含 label_close_tag /
--      label_net_edge_bps / label_filled_at（V017 land 後該俱在）。
--   4. Guard B：確認 label_close_tag 型別 = TEXT（writer 寫 'rejected_governance'）。
--   5. Idempotent：CREATE OR REPLACE VIEW + DROP IF EXISTS / CREATE FUNCTION
--      支援重跑，第二次 NOTICE-only。
--
-- 不變式 / Invariants:
--   - V084 落地後既有 mlde_edge_training_rows column / 計算邏輯 / WHERE
--     完全保留，僅追加 sample_weight。
--   - sample_weight 對「無 close tag」row（label_close_tag IS NULL，含
--     未平倉的 entry-emit row + backfill 前的 stuck row）回 1.0 — 與舊
--     行為（unweighted）對齊，向後相容。
--   - 對 'rejected_governance' row 回 1/170 — 70× imbalance 修正成 reject:
--     fill ≈ 1:0.41，weighted 後 reject 不 dominance。
--   - 訓練端 trainer 可 opt-in 用 sample_weight，舊 trainer 不破（column 無
--     參考 = 自動忽略）。
--
-- Spec:
--   - docs/CCAgentWorkSpace/PA/workspace/reports/
--     2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M3
--   - srv/TODO.md v19 §5 invariant 5 + §10 P0-MIT-LABEL-CLOSE-TAG-1
--
-- E2 review checklist：
--   1. Guard A 命中 V017 schema (decision_features 三 label 欄位俱在)？
--   2. UDF mlde_sample_weight IMMUTABLE 對嗎？(yes — 純函數依 close_tag)
--   3. View sample_weight 落點對嗎？(SELECT 結尾 + 回傳 row)
--   4. 既有 attribution_chain_ok 計算未動？(yes — 仍用 label_net_edge_bps IS NOT NULL)
-- ============================================================

-- Guard A：確認 learning.decision_features 表已存在且含 label 三欄位
-- learning.decision_features 已存在但 schema drift 時 RAISE
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='learning' AND table_name='decision_features') THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY['label_close_tag','label_net_edge_bps','label_filled_at']) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='decision_features'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION
                'V084 schema_guard A: learning.decision_features missing label columns: %. '
                'V017 must land first (label_close_tag/label_net_edge_bps/label_filled_at). '
                'Re-apply V017 then re-run V084.',
                v_missing;
        END IF;
    ELSE
        RAISE EXCEPTION
            'V084 schema_guard A: learning.decision_features does not exist. '
            'V017 must land first.';
    END IF;
END $$;

-- Guard B：確認 label_close_tag / label_net_edge_bps / label_filled_at 型別正確
DO $$
DECLARE v_type TEXT;
BEGIN
    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='decision_features'
      AND column_name='label_close_tag';
    IF v_type IS DISTINCT FROM 'text' THEN
        RAISE EXCEPTION
            'V084 schema_guard B: label_close_tag type drift; expected text, got %. '
            'V017 schema must align before V084 land.',
            v_type;
    END IF;

    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='decision_features'
      AND column_name='label_net_edge_bps';
    IF v_type NOT IN ('double precision', 'real', 'numeric') THEN
        RAISE EXCEPTION
            'V084 schema_guard B: label_net_edge_bps type drift; expected float, got %.',
            v_type;
    END IF;

    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='decision_features'
      AND column_name='label_filled_at';
    IF v_type NOT LIKE 'timestamp%' THEN
        RAISE EXCEPTION
            'V084 schema_guard B: label_filled_at type drift; expected timestamp, got %.',
            v_type;
    END IF;
END $$;

-- ============================================================
-- UDF: learning.mlde_sample_weight(close_tag TEXT) → DOUBLE PRECISION
--   回傳 sample_weight 給 ML 訓練端 opt-in 使用。
--   - 'rejected_governance' → 1/170 ≈ 0.005882（PA 70:1 + 安全餘量）
--   - 其他 (NULL / 'orphan_close:%' / 'adopted_close:%' / 'shadow_fill:%' /
--     'abandoned:no_close_fill' / 一般 fill row) → 1.0（unweighted 行為）
--
-- IMMUTABLE：純函數依輸入 → 可 PG plan cache + index expression 用。
-- LANGUAGE sql：simpler form; PG can inline。
-- ============================================================
CREATE OR REPLACE FUNCTION learning.mlde_sample_weight(close_tag TEXT)
RETURNS DOUBLE PRECISION
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN close_tag = 'rejected_governance' THEN (1.0::double precision / 170.0)
        ELSE 1.0::double precision
    END;
$$;

COMMENT ON FUNCTION learning.mlde_sample_weight(TEXT) IS
    'W-AUDIT-4b-M3 sample_weight: rejected_governance row 加權 1/170 防 70:1 dominance；其他 row 1.0 保 unweighted 兼容。';

-- ============================================================
-- View: learning.mlde_edge_training_rows
--   重抄 V034 全部邏輯 + 結尾追加 sample_weight 欄位。
--   其他 schema / WHERE / 計算 / attribution_chain_ok 完全保留。
-- ============================================================
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
        'view_version', 'mlde_v3_class_weight',
        'primary_reward', 'net_bps_after_fee',
        'attribution_chain', jsonb_build_object(
            'has_signal_id', sr.signal_id IS NOT NULL AND sr.signal_id <> '',
            'has_context_id', sr.context_id IS NOT NULL AND sr.context_id <> '',
            'signal_context_match', sr.signal_context_id = sr.context_id,
            'has_post_fee_reward', sr.label_net_edge_bps IS NOT NULL
        ),
        'scanner', COALESCE(sr.scanner_json, '{}'::jsonb),
        'sample_weight', jsonb_build_object(
            'rejected_governance', 1.0/170.0,
            'default', 1.0,
            'rationale', 'W-AUDIT-4b-M3 negative-label class weight; reject:fill 70:1 + 100x safety margin'
        )
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
    sr.scanner_f_funding_arb,
    -- W-AUDIT-4b-M3：sample_weight 給 ML training opt-in 使用
    -- rejected_governance row → 1/170；其他 row → 1.0（unweighted 兼容）
    learning.mlde_sample_weight(sr.label_close_tag) AS sample_weight
FROM strategy_regime sr;

COMMENT ON VIEW learning.mlde_edge_training_rows IS
    'ML/Dream edge-unblock training view. Valid rows require attribution_chain_ok=true and net_bps_after_fee; V034 appends scanner trend/fitness context for advisory learning; V084 adds sample_weight for class weight handling (rejected_governance=1/170, default=1.0).';
