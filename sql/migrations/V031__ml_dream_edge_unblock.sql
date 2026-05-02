-- V031: ML/Dream edge-unblock data contract.
-- V031：ML/Dream edge 修復啟用資料契約。
--
-- Scope:
--   * learning.mlde_edge_training_rows is a read-only view that turns the
--     current attribution chain into training rows.
--   * learning.mlde_shadow_recommendations stores advisory/shadow outputs
--     from LinUCB/ML/Dream/Opportunity producers. It is not an execution table.
--
-- Hard boundary:
--   ML/Dream output is advisory by default. Live/live_demo rows may be logged,
--   but an applied live/live_demo row must carry a Decision Lease id.
--
-- Retrofit (AUDIT-2026-05-02-P1-1, 2026-05-02): added Guard A per CLAUDE.md
-- §七 (V023 silent-noop postmortem). 4-day cold audit found V031 missing
-- this guard; if a legacy `learning.mlde_shadow_recommendations` stub
-- exists without `requires_governance` / `decision_lease_id` / `payload`
-- columns, `CREATE TABLE IF NOT EXISTS` silently no-ops and the live-gate
-- CHECK constraint below fails to bind correctly. Guard A surfaces drift
-- at apply time.
--
-- Round 3 retrofit (AUDIT-2026-05-02-P1-1 round 3, 2026-05-02): Round 1/2
-- self-disclaimer "CREATE OR REPLACE VIEW for mlde_edge_training_rows is
-- idempotent and needs no guard" was wrong. Postgres `CREATE OR REPLACE
-- VIEW` cannot DROP columns; only APPEND. After V034 lands (V034 adds 18
-- scanner_market_* cols making the view 52 wide), re-applying V031's
-- 34-col CREATE OR REPLACE VIEW raises `cannot drop columns from view`.
-- E4 round 2 caught this on the production DB (V034-applied state).
-- Fix: view-shape guard mirroring V034's pattern; the view body is moved
-- inside a DO/EXECUTE block so it can be conditionally skipped. If the
-- view exists and already contains all V031 baseline cols, the view has
-- been extended by a later migration (V034+) and we MUST skip the
-- CREATE OR REPLACE to avoid the column-drop error. If the view is
-- missing baseline cols, that is unexpected drift and we RAISE. If the
-- view does not exist (fresh install), we create it via EXECUTE.
--
-- 回補（AUDIT-2026-05-02-P1-1，2026-05-02）：依 CLAUDE.md §七 補上
-- Guard A。若 legacy `learning.mlde_shadow_recommendations` stub 缺
-- requires_governance / decision_lease_id / payload 等欄，CREATE TABLE
-- IF NOT EXISTS 會靜默 no-op，下方 live-gate CHECK constraint 套不上去。
--
-- 第三輪回補（AUDIT-2026-05-02-P1-1 round 3，2026-05-02）：Round 1/2
-- 自報「mlde_edge_training_rows 的 CREATE OR REPLACE VIEW 不需 guard」
-- 推論錯誤。Postgres CREATE OR REPLACE VIEW 規格上禁止 DROP columns，
-- 只能 APPEND。V034 為 view 加 18 個 scanner_market_* 欄成 52 欄；
-- V031 第二次跑（或 fresh-from-V034 state 跑）會撞 `cannot drop columns
-- from view`。E4 round 2 在 production DB（V034-applied state）抓到。
-- 修法：仿 V034 view-shape guard，將 view body 包進 DO/EXECUTE block
-- 使其可條件 skip。若 view 已存在且包含 V031 baseline 全部 col，代表
-- 已被後續 migration（V034+）擴展，必須 SKIP CREATE OR REPLACE 以避免
-- column-drop error。若 view 缺 baseline col 為非預期 drift → RAISE。
-- 若 view 不存在（fresh install）→ EXECUTE 建 view。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A
--   (view-shape variant adapted from V034 round-2 retrofit)

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

-- ------------------------------------------------------------
-- Schema Guard A (view-shape variant) — V031 view conditional create
-- Schema Guard A（view shape 變體）— V031 view 條件建立
-- ------------------------------------------------------------
-- Three paths:
--   1. View absent (fresh install) → EXECUTE the CREATE OR REPLACE VIEW
--      below to land V031 baseline shape.
--   2. View exists and contains all V031 baseline cols → SKIP recreation
--      (view has been extended by V034+; CREATE OR REPLACE would attempt
--      to drop the appended cols and fail with `cannot drop columns from
--      view`). Emit NOTICE so re-runs are visibly idempotent.
--   3. View exists but missing V031 baseline cols → unexpected drift,
--      RAISE EXCEPTION (mirrors Guard A semantics on tables).
--
-- 三條路徑：
--   1. View 不存在（fresh install）→ EXECUTE 下方 CREATE OR REPLACE VIEW
--      建立 V031 baseline 形狀。
--   2. View 存在且包含 V031 baseline 全部 col → SKIP（view 已被 V034+
--      擴展；CREATE OR REPLACE 會嘗試 drop 已 append 的 col 並撞
--      `cannot drop columns from view`）。發 NOTICE 讓 re-run 可見地
--      idempotent。
--   3. View 存在但缺 V031 baseline col → 非預期 drift → RAISE
--      EXCEPTION（仿 Guard A 對 table 的語意）。
DO $migration$
DECLARE
    v_view_schema  CONSTANT TEXT := 'learning';
    v_view_name    CONSTANT TEXT := 'mlde_edge_training_rows';
    -- V031 outer-SELECT alias list (verbatim from the SELECT below, in
    -- declaration order). 34 columns. V034 appends 18 scanner_market_*
    -- cols on top of these; the same baseline list appears in V034's
    -- view-shape guard.
    -- V031 outer SELECT alias 列表（依下方 SELECT 順序逐字抄出），共 34 欄。
    -- V034 在此基礎上 append 18 個 scanner_market_* 欄；V034 的 view-shape
    -- guard 也用同一份 baseline。
    v_v031_cols    CONSTANT TEXT[] := ARRAY[
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
    ];
    v_existing     TEXT[];
    v_missing      TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.views
        WHERE table_schema = v_view_schema
          AND table_name   = v_view_name
    ) THEN
        SELECT array_agg(column_name) INTO v_existing
        FROM information_schema.columns
        WHERE table_schema = v_view_schema
          AND table_name   = v_view_name;

        SELECT array_agg(c) INTO v_missing
        FROM unnest(v_v031_cols) AS c
        WHERE c <> ALL(COALESCE(v_existing, ARRAY[]::TEXT[]));

        IF v_missing IS NULL OR array_length(v_missing, 1) IS NULL THEN
            -- Path 2: V031 baseline cols all present → view extended by
            -- V034+. Must skip CREATE OR REPLACE (would drop appended cols).
            -- 路徑 2：V031 baseline 全在 → view 已被 V034+ 擴展。
            -- 必須 skip CREATE OR REPLACE（否則會 drop 已 append 的 col）。
            RAISE NOTICE
                'V031 view-shape guard: %.% already contains all V031 baseline cols '
                '(likely extended by V034+); skipping CREATE OR REPLACE VIEW to avoid '
                '`cannot drop columns from view` error. View body is unchanged.',
                v_view_schema, v_view_name;
            RETURN;
        ELSE
            -- Path 3: drift → RAISE
            -- 路徑 3：drift → RAISE
            RAISE EXCEPTION
                'schema_guard V031 (view): %.% exists but missing V031 baseline cols: %. '
                'Manual remediation required (DROP VIEW then re-apply V031..V034 in order, '
                'or restore the missing cols).',
                v_view_schema, v_view_name, v_missing;
        END IF;
    END IF;

    -- Path 1: view absent → fresh install, create via EXECUTE.
    -- 路徑 1：view 不存在 → fresh install，用 EXECUTE 建立。
    -- View body verbatim from V031 baseline (no business-logic change).
    -- View body 直接抄自 V031 baseline（業務邏輯不變）。
    EXECUTE $view$
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
                'view_version', 'mlde_v1',
                'primary_reward', 'net_bps_after_fee',
                'attribution_chain', jsonb_build_object(
                    'has_signal_id', sr.signal_id IS NOT NULL AND sr.signal_id <> '',
                    'has_context_id', sr.context_id IS NOT NULL AND sr.context_id <> '',
                    'signal_context_match', sr.signal_context_id = sr.context_id,
                    'has_post_fee_reward', sr.label_net_edge_bps IS NOT NULL
                ),
                'scanner', COALESCE(sr.scanner_json, '{}'::jsonb)
            ) AS metadata
        FROM strategy_regime sr
    $view$;

    EXECUTE $cmt$
        COMMENT ON VIEW learning.mlde_edge_training_rows IS
            'ML/Dream edge-unblock training view. Valid training rows require attribution_chain_ok=true and net_bps_after_fee as primary reward.'
    $cmt$;
END
$migration$;

-- ------------------------------------------------------------
-- Schema Guard A — verify mlde_shadow_recommendations required cols
-- Schema Guard A — 表已存在時驗必要欄位俱在
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name   = 'mlde_shadow_recommendations'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'ts', 'engine_mode',
            'context_id', 'intent_id', 'symbol', 'strategy_name',
            'source', 'recommendation_type', 'primary_metric',
            'expected_net_bps', 'confidence', 'sample_count',
            'payload', 'applied', 'requires_governance',
            'decision_lease_id', 'created_by'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'mlde_shadow_recommendations'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: learning.mlde_shadow_recommendations exists but missing required columns: %. '
                'Likely a legacy stub is present (perhaps without requires_governance / decision_lease_id). '
                'Resolve (DROP + re-apply V031, or ALTER TABLE ADD missing columns) before continuing — '
                'the live-gate CHECK constraint below depends on these columns.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.mlde_shadow_recommendations (
    id                    BIGSERIAL PRIMARY KEY,
    ts                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    engine_mode           TEXT        NOT NULL CHECK (
        engine_mode IN ('paper', 'demo', 'live_demo', 'live')
        OR engine_mode LIKE 'test\_%' ESCAPE '\'
    ),
    context_id            TEXT,
    intent_id             TEXT,
    symbol                TEXT,
    strategy_name         TEXT,
    source                TEXT        NOT NULL CHECK (
        source IN ('linucb', 'ml_shadow', 'dream_engine', 'opportunity_tracker')
    ),
    recommendation_type   TEXT        NOT NULL CHECK (
        recommendation_type IN (
            'rank', 'veto', 'parameter_proposal', 'experiment_plan',
            'regret_summary', 'dream_insight'
        )
    ),
    primary_metric        TEXT        NOT NULL DEFAULT 'net_bps_after_fee',
    expected_net_bps      DOUBLE PRECISION,
    confidence            DOUBLE PRECISION CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    sample_count          INTEGER CHECK (sample_count IS NULL OR sample_count >= 0),
    payload               JSONB       NOT NULL DEFAULT '{}'::jsonb,
    applied               BOOLEAN     NOT NULL DEFAULT FALSE,
    requires_governance   BOOLEAN     NOT NULL DEFAULT TRUE,
    decision_lease_id     TEXT,
    created_by            TEXT        NOT NULL DEFAULT 'mlde_shadow'
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'mlde_shadow_live_applied_requires_lease'
    ) THEN
        ALTER TABLE learning.mlde_shadow_recommendations
            ADD CONSTRAINT mlde_shadow_live_applied_requires_lease
            CHECK (
                NOT (
                    engine_mode IN ('live', 'live_demo')
                    AND applied
                    AND COALESCE(decision_lease_id, '') = ''
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_mlde_shadow_recommendations_ts
    ON learning.mlde_shadow_recommendations (ts DESC);

CREATE INDEX IF NOT EXISTS idx_mlde_shadow_recommendations_mode_source_ts
    ON learning.mlde_shadow_recommendations (engine_mode, source, ts DESC);

CREATE INDEX IF NOT EXISTS idx_mlde_shadow_recommendations_payload_gin
    ON learning.mlde_shadow_recommendations USING GIN (payload);

COMMENT ON TABLE learning.mlde_shadow_recommendations IS
    'Advisory ML/Dream/LinUCB/Opportunity outputs. Not an execution queue; live applied rows require Decision Lease id.';
COMMENT ON COLUMN learning.mlde_shadow_recommendations.applied IS
    'FALSE by default. Any future live/live_demo applied row must carry decision_lease_id.';
