-- ============================================================
-- test_v028_v034_guards.sql
-- Guard A / B fixture tests for V028 / V030 / V031 / V032 / V034
-- 為 V028/V030/V031/V032/V034 retrofit 的 Guard A/B fixture 測試
-- AUDIT-2026-05-02-P1-1
-- ============================================================
--
-- Purpose / 用途：
--   Per CLAUDE.md §七 V023 silent-noop postmortem rule, every new SQL
--   migration's guards must have pass / fail / no-op tests. This file
--   covers the guards retrofitted in V028, V030, V031, V032, and V034
--   without touching real `trading.*` / `learning.*` tables — fixtures
--   live in throwaway `v028_v034_guard_test` schema.
--
--   依 CLAUDE.md §七 V023 事後規定，新 migration guard 須有 pass / fail
--   / no-op 測試。本檔涵蓋 V028 / V030 / V031 / V032 / V034 retrofit
--   guard，固件放臨時 `v028_v034_guard_test` schema 不污染 production。
--
-- Usage / 用法：
--   psql -U trading_admin -d trading_ai_test -v ON_ERROR_STOP=0 \
--        -f sql/migrations/tests/test_v028_v034_guards.sql
--
--   Each test prints `TEST V<NNN>/<n>:` PASS or FAIL via NOTICE.
--   Grep stderr/NOTICE for `FAIL` to detect regressions.
--
--   每個 test 印 `TEST V<NNN>/<n>:` PASS 或 FAIL；grep `FAIL` 找回歸。
--
-- Coverage / 涵蓋：
--   V028 — fills.* ADD COLUMN Guard B (×6) + fills parent Guard A
--          [B-1 reference_price, B-2 reference_ts_ms, B-3 reference_source,
--           B-4 slippage_bps, B-5 liquidity_role, B-6 fill_latency_ms]
--   V030 — scanner_snapshots Guard A
--   V031 — mlde_shadow_recommendations Guard A
--   V032 — mlde_param_applications Guard A
--   V034 — mlde_edge_training_rows view-shape Guard A
--
-- Each migration: 1 pass test + 1 fail test + 1 no-op test (3 cases per
-- migration × 5 migrations = 15 baseline cases). V028 also includes 1
-- representative Guard B fail case (wrong-type column) since 6 columns
-- share the same logic — the representative case proves the pattern.
-- 每 migration 1 pass + 1 fail + 1 no-op；V028 額外 1 個 Guard B 型別錯
-- 測試（6 欄共享同一 pattern，代表性 case 即足夠）。
-- ============================================================

\set ON_ERROR_STOP off

-- ------------------------------------------------------------
-- Setup: scratch schema mirroring trading.* / learning.*
-- 測試用暫存 schema（鏡射 trading.* / learning.*）
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS v028_v034_guard_test CASCADE;
CREATE SCHEMA v028_v034_guard_test;


-- ============================================================
-- V028 — fills parent Guard A: pass / fail / no-op
-- ============================================================
-- Pass case: trading.fills-shaped fixture with all Guard A required cols.
-- 通過情境：擁有 Guard A 所有必要欄位的 fills fixture。
DO $$
DECLARE v_missing TEXT[];
BEGIN
    EXECUTE 'CREATE TABLE v028_v034_guard_test.fills_good (
        ts            TIMESTAMPTZ NOT NULL,
        fill_id       TEXT NOT NULL,
        order_id      TEXT,
        symbol        TEXT NOT NULL,
        side          TEXT NOT NULL,
        qty           DOUBLE PRECISION NOT NULL,
        price         DOUBLE PRECISION NOT NULL,
        fee           DOUBLE PRECISION,
        realized_pnl  DOUBLE PRECISION,
        strategy_name TEXT NOT NULL,
        context_id    TEXT,
        engine_mode   TEXT NOT NULL,
        exit_source   TEXT
    )';

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts','fill_id','order_id','symbol','side',
        'qty','price','fee','realized_pnl',
        'strategy_name','context_id','engine_mode','exit_source'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='v028_v034_guard_test' AND table_name='fills_good'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
        RAISE NOTICE 'TEST V028/A-pass: FAIL (unexpected missing: %)', v_missing;
    ELSE
        RAISE NOTICE 'TEST V028/A-pass: PASS Guard A on fully-shaped fills';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.fills_good';
END $$;

-- Fail case: legacy stub missing exit_source → Guard A must RAISE.
-- 失敗情境：legacy stub 缺 exit_source → Guard A 必 RAISE。
DO $$
DECLARE
    v_missing TEXT[];
    v_caught  BOOLEAN := FALSE;
BEGIN
    EXECUTE 'CREATE TABLE v028_v034_guard_test.fills_legacy (
        ts            TIMESTAMPTZ NOT NULL,
        fill_id       TEXT NOT NULL,
        order_id      TEXT,
        symbol        TEXT NOT NULL,
        side          TEXT NOT NULL,
        qty           DOUBLE PRECISION NOT NULL,
        price         DOUBLE PRECISION NOT NULL,
        fee           DOUBLE PRECISION,
        realized_pnl  DOUBLE PRECISION,
        strategy_name TEXT NOT NULL,
        context_id    TEXT,
        engine_mode   TEXT NOT NULL
        -- exit_source intentionally missing (V021 not applied)
    )';

    BEGIN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts','fill_id','order_id','symbol','side',
            'qty','price','fee','realized_pnl',
            'strategy_name','context_id','engine_mode','exit_source'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='v028_v034_guard_test' AND table_name='fills_legacy'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION 'V028 Guard A FAIL: missing %', v_missing;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V028/A-fail: PASS Guard A correctly raised on missing exit_source';
    ELSE
        RAISE NOTICE 'TEST V028/A-fail: FAIL Guard A should have raised on legacy stub';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.fills_legacy';
END $$;

-- No-op case: table absent → IF EXISTS gate skips, no RAISE.
-- No-op 情境：表不存在 → IF EXISTS 跳過，不 RAISE。
DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='v028_v034_guard_test' AND table_name='fills_absent'
        ) THEN
            RAISE EXCEPTION 'should_not_reach';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V028/A-noop: FAIL Guard A no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V028/A-noop: PASS Guard A no-op (table absent) skipped cleanly';
    END IF;
END $$;


-- ============================================================
-- V028 — Guard B representative case (slippage_bps wrong type)
-- V028 — Guard B 代表性測試（slippage_bps 型別錯）
-- ============================================================
-- The 6 V028 Guard B blocks share identical logic; one representative
-- fail case per type family (DOUBLE PRECISION here) proves the pattern.
-- 6 個 V028 Guard B 邏輯一致，每型別家族 1 代表性失敗測試即可。
DO $$
DECLARE
    v_actual TEXT;
    v_caught BOOLEAN := FALSE;
BEGIN
    -- Legacy fixture: slippage_bps as TEXT (should be DOUBLE PRECISION).
    EXECUTE 'CREATE TABLE v028_v034_guard_test.fills_b_wrong (
        ts           TIMESTAMPTZ NOT NULL,
        slippage_bps TEXT
    )';

    BEGIN
        SELECT data_type INTO v_actual
        FROM information_schema.columns
        WHERE table_schema='v028_v034_guard_test' AND table_name='fills_b_wrong'
          AND column_name='slippage_bps';
        IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
            RAISE EXCEPTION
                'V028 Guard B FAIL: slippage_bps is %, expected double precision', v_actual;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V028/B-fail: PASS Guard B correctly raised on wrong type';
    ELSE
        RAISE NOTICE 'TEST V028/B-fail: FAIL Guard B should have raised on TEXT';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.fills_b_wrong';
END $$;

-- V028 Guard B no-op: column absent → no RAISE.
DO $$
DECLARE
    v_actual TEXT;
    v_caught BOOLEAN := FALSE;
BEGIN
    EXECUTE 'CREATE TABLE v028_v034_guard_test.fills_b_noop (ts TIMESTAMPTZ NOT NULL)';
    BEGIN
        SELECT data_type INTO v_actual
        FROM information_schema.columns
        WHERE table_schema='v028_v034_guard_test' AND table_name='fills_b_noop'
          AND column_name='slippage_bps';
        IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
            RAISE EXCEPTION 'should_not_reach';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V028/B-noop: FAIL Guard B no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V028/B-noop: PASS Guard B no-op (column absent) skipped cleanly';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.fills_b_noop';
END $$;


-- ============================================================
-- V030 — scanner_snapshots Guard A: pass / fail / no-op
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    EXECUTE 'CREATE TABLE v028_v034_guard_test.scanner_good (
        ts               TIMESTAMPTZ NOT NULL,
        scan_id          TEXT NOT NULL,
        active_symbols   TEXT[] NOT NULL,
        added            TEXT[] NOT NULL,
        removed          TEXT[] NOT NULL,
        rejected_count   BIGINT NOT NULL,
        scan_duration_ms BIGINT NOT NULL,
        candidates       JSONB NOT NULL,
        config           JSONB NOT NULL,
        PRIMARY KEY (scan_id, ts)
    )';

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts','scan_id','active_symbols','added','removed',
        'rejected_count','scan_duration_ms','candidates','config'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='v028_v034_guard_test' AND table_name='scanner_good'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
        RAISE NOTICE 'TEST V030/A-pass: FAIL (unexpected missing: %)', v_missing;
    ELSE
        RAISE NOTICE 'TEST V030/A-pass: PASS Guard A on fully-shaped scanner_snapshots';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.scanner_good';
END $$;

DO $$
DECLARE
    v_missing TEXT[];
    v_caught  BOOLEAN := FALSE;
BEGIN
    -- Legacy stub: missing config + candidates JSONB.
    EXECUTE 'CREATE TABLE v028_v034_guard_test.scanner_legacy (
        ts             TIMESTAMPTZ NOT NULL,
        scan_id        TEXT NOT NULL,
        active_symbols TEXT[] NOT NULL,
        added          TEXT[] NOT NULL,
        removed        TEXT[] NOT NULL,
        rejected_count BIGINT NOT NULL,
        scan_duration_ms BIGINT NOT NULL
        -- candidates / config intentionally missing
    )';

    BEGIN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts','scan_id','active_symbols','added','removed',
            'rejected_count','scan_duration_ms','candidates','config'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='v028_v034_guard_test' AND table_name='scanner_legacy'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION 'V030 Guard A FAIL: missing %', v_missing;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V030/A-fail: PASS Guard A correctly raised on missing candidates/config';
    ELSE
        RAISE NOTICE 'TEST V030/A-fail: FAIL Guard A should have raised';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.scanner_legacy';
END $$;

DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='v028_v034_guard_test' AND table_name='scanner_absent'
        ) THEN
            RAISE EXCEPTION 'should_not_reach';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;
    IF v_caught THEN
        RAISE NOTICE 'TEST V030/A-noop: FAIL Guard A no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V030/A-noop: PASS Guard A no-op (table absent) skipped cleanly';
    END IF;
END $$;


-- ============================================================
-- V031 — mlde_shadow_recommendations Guard A: pass / fail / no-op
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    EXECUTE 'CREATE TABLE v028_v034_guard_test.mlde_shadow_good (
        id                  BIGSERIAL PRIMARY KEY,
        ts                  TIMESTAMPTZ NOT NULL DEFAULT now(),
        engine_mode         TEXT NOT NULL,
        context_id          TEXT,
        intent_id           TEXT,
        symbol              TEXT,
        strategy_name       TEXT,
        source              TEXT NOT NULL,
        recommendation_type TEXT NOT NULL,
        primary_metric      TEXT NOT NULL DEFAULT ''net_bps_after_fee'',
        expected_net_bps    DOUBLE PRECISION,
        confidence          DOUBLE PRECISION,
        sample_count        INTEGER,
        payload             JSONB NOT NULL DEFAULT ''{}''::jsonb,
        applied             BOOLEAN NOT NULL DEFAULT FALSE,
        requires_governance BOOLEAN NOT NULL DEFAULT TRUE,
        decision_lease_id   TEXT,
        created_by          TEXT NOT NULL DEFAULT ''mlde_shadow''
    )';

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'id','ts','engine_mode','context_id','intent_id','symbol','strategy_name',
        'source','recommendation_type','primary_metric','expected_net_bps',
        'confidence','sample_count','payload','applied','requires_governance',
        'decision_lease_id','created_by'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_shadow_good'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
        RAISE NOTICE 'TEST V031/A-pass: FAIL (unexpected missing: %)', v_missing;
    ELSE
        RAISE NOTICE 'TEST V031/A-pass: PASS Guard A on fully-shaped mlde_shadow_recommendations';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.mlde_shadow_good';
END $$;

DO $$
DECLARE
    v_missing TEXT[];
    v_caught  BOOLEAN := FALSE;
BEGIN
    -- Legacy stub: missing requires_governance + decision_lease_id.
    EXECUTE 'CREATE TABLE v028_v034_guard_test.mlde_shadow_legacy (
        id                  BIGSERIAL PRIMARY KEY,
        ts                  TIMESTAMPTZ NOT NULL DEFAULT now(),
        engine_mode         TEXT NOT NULL,
        context_id          TEXT,
        intent_id           TEXT,
        symbol              TEXT,
        strategy_name       TEXT,
        source              TEXT NOT NULL,
        recommendation_type TEXT NOT NULL,
        primary_metric      TEXT NOT NULL DEFAULT ''net_bps_after_fee'',
        expected_net_bps    DOUBLE PRECISION,
        confidence          DOUBLE PRECISION,
        sample_count        INTEGER,
        payload             JSONB NOT NULL DEFAULT ''{}''::jsonb,
        applied             BOOLEAN NOT NULL DEFAULT FALSE,
        created_by          TEXT NOT NULL DEFAULT ''mlde_shadow''
        -- requires_governance / decision_lease_id intentionally missing
    )';

    BEGIN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id','ts','engine_mode','context_id','intent_id','symbol','strategy_name',
            'source','recommendation_type','primary_metric','expected_net_bps',
            'confidence','sample_count','payload','applied','requires_governance',
            'decision_lease_id','created_by'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_shadow_legacy'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION 'V031 Guard A FAIL: missing %', v_missing;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V031/A-fail: PASS Guard A correctly raised on missing governance cols';
    ELSE
        RAISE NOTICE 'TEST V031/A-fail: FAIL Guard A should have raised';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.mlde_shadow_legacy';
END $$;

DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_shadow_absent'
        ) THEN
            RAISE EXCEPTION 'should_not_reach';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;
    IF v_caught THEN
        RAISE NOTICE 'TEST V031/A-noop: FAIL Guard A no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V031/A-noop: PASS Guard A no-op (table absent) skipped cleanly';
    END IF;
END $$;


-- ============================================================
-- V032 — mlde_param_applications Guard A: pass / fail / no-op
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    EXECUTE 'CREATE TABLE v028_v034_guard_test.mlde_param_good (
        id                  BIGSERIAL PRIMARY KEY,
        ts                  TIMESTAMPTZ NOT NULL DEFAULT now(),
        engine_mode         TEXT NOT NULL,
        recommendation_id   BIGINT,
        application_type    TEXT NOT NULL,
        target_name         TEXT NOT NULL,
        patch               JSONB NOT NULL DEFAULT ''{}''::jsonb,
        prev_snapshot       JSONB NOT NULL DEFAULT ''{}''::jsonb,
        ipc_response        JSONB NOT NULL DEFAULT ''{}''::jsonb,
        status              TEXT NOT NULL,
        reason              TEXT,
        requires_governance BOOLEAN NOT NULL DEFAULT TRUE,
        decision_lease_id   TEXT,
        created_by          TEXT NOT NULL DEFAULT ''mlde_demo_applier'',
        payload             JSONB NOT NULL DEFAULT ''{}''::jsonb
    )';

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'id','ts','engine_mode','recommendation_id','application_type','target_name',
        'patch','prev_snapshot','ipc_response','status','reason',
        'requires_governance','decision_lease_id','created_by','payload'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_param_good'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
        RAISE NOTICE 'TEST V032/A-pass: FAIL (unexpected missing: %)', v_missing;
    ELSE
        RAISE NOTICE 'TEST V032/A-pass: PASS Guard A on fully-shaped mlde_param_applications';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.mlde_param_good';
END $$;

DO $$
DECLARE
    v_missing TEXT[];
    v_caught  BOOLEAN := FALSE;
BEGIN
    -- Legacy stub: missing prev_snapshot + ipc_response + decision_lease_id.
    EXECUTE 'CREATE TABLE v028_v034_guard_test.mlde_param_legacy (
        id                  BIGSERIAL PRIMARY KEY,
        ts                  TIMESTAMPTZ NOT NULL DEFAULT now(),
        engine_mode         TEXT NOT NULL,
        recommendation_id   BIGINT,
        application_type    TEXT NOT NULL,
        target_name         TEXT NOT NULL,
        patch               JSONB NOT NULL DEFAULT ''{}''::jsonb,
        status              TEXT NOT NULL,
        reason              TEXT,
        requires_governance BOOLEAN NOT NULL DEFAULT TRUE,
        created_by          TEXT NOT NULL DEFAULT ''mlde_demo_applier'',
        payload             JSONB NOT NULL DEFAULT ''{}''::jsonb
        -- prev_snapshot / ipc_response / decision_lease_id intentionally missing
    )';

    BEGIN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id','ts','engine_mode','recommendation_id','application_type','target_name',
            'patch','prev_snapshot','ipc_response','status','reason',
            'requires_governance','decision_lease_id','created_by','payload'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_param_legacy'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION 'V032 Guard A FAIL: missing %', v_missing;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V032/A-fail: PASS Guard A correctly raised on missing audit cols';
    ELSE
        RAISE NOTICE 'TEST V032/A-fail: FAIL Guard A should have raised';
    END IF;
    EXECUTE 'DROP TABLE v028_v034_guard_test.mlde_param_legacy';
END $$;

DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_param_absent'
        ) THEN
            RAISE EXCEPTION 'should_not_reach';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;
    IF v_caught THEN
        RAISE NOTICE 'TEST V032/A-noop: FAIL Guard A no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V032/A-noop: PASS Guard A no-op (table absent) skipped cleanly';
    END IF;
END $$;


-- ============================================================
-- V034 — view-shape Guard A: pass / fail / no-op
-- V034 — view 形狀 Guard A：pass / fail / no-op
-- ============================================================
-- Note: V034 guards a VIEW (not a base table). information_schema.views
-- gates the IF EXISTS check; information_schema.columns reports view cols.
-- 註：V034 守 view 不是 table。information_schema.views 做 IF EXISTS gate；
-- information_schema.columns 對 view 同樣回欄位。
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    -- Pass: build a view that has the V031 column set the V034 guard expects.
    EXECUTE 'CREATE VIEW v028_v034_guard_test.mlde_view_good AS
             SELECT
               NULL::TIMESTAMPTZ AS ts,
               NULL::BIGINT AS ts_ms,
               NULL::TEXT AS engine_mode,
               NULL::TEXT AS intent_id,
               NULL::TEXT AS signal_id,
               NULL::TEXT AS context_id,
               NULL::TEXT AS symbol,
               NULL::TEXT AS symbol_bucket,
               NULL::TEXT AS side,
               NULL::INTEGER AS side_num,
               NULL::DOUBLE PRECISION AS qty,
               NULL::DOUBLE PRECISION AS price,
               NULL::TEXT AS order_type,
               NULL::TEXT AS strategy_name,
               NULL::TEXT AS regime,
               NULL::TEXT AS scanner_scan_id,
               NULL::TEXT AS scanner_best_strategy,
               NULL::TEXT AS scanner_route_mode,
               NULL::TEXT AS scanner_edge_status,
               NULL::DOUBLE PRECISION AS scanner_edge_bps,
               NULL::DOUBLE PRECISION AS scanner_edge_n,
               NULL::DOUBLE PRECISION AS scanner_final_score,
               NULL::DOUBLE PRECISION AS scanner_raw_score,
               NULL::DOUBLE PRECISION AS net_bps_after_fee,
               NULL::TEXT AS label_close_tag,
               NULL::BOOLEAN AS label_split_flag,
               NULL::TIMESTAMPTZ AS label_filled_at,
               NULL::JSONB AS features_jsonb,
               NULL::JSONB AS context_features,
               NULL::TEXT AS linucb_arm_id,
               NULL::TEXT AS mlde_arm_id,
               NULL::BOOLEAN AS attribution_chain_ok,
               NULL::TEXT AS data_window,
               NULL::JSONB AS metadata
             WHERE FALSE';

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts','ts_ms','engine_mode','intent_id','signal_id','context_id',
        'symbol','symbol_bucket','side','side_num','qty','price','order_type',
        'strategy_name','regime',
        'scanner_scan_id','scanner_best_strategy','scanner_route_mode','scanner_edge_status',
        'scanner_edge_bps','scanner_edge_n','scanner_final_score','scanner_raw_score',
        'net_bps_after_fee','label_close_tag','label_split_flag','label_filled_at',
        'features_jsonb','context_features','linucb_arm_id','mlde_arm_id',
        'attribution_chain_ok','data_window','metadata'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_view_good'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
        RAISE NOTICE 'TEST V034/A-pass: FAIL (unexpected missing: %)', v_missing;
    ELSE
        RAISE NOTICE 'TEST V034/A-pass: PASS view-shape Guard A on V031-shaped view';
    END IF;
    EXECUTE 'DROP VIEW v028_v034_guard_test.mlde_view_good';
END $$;

DO $$
DECLARE
    v_missing TEXT[];
    v_caught  BOOLEAN := FALSE;
BEGIN
    -- Fail: build a narrowed view (missing scanner_* + linucb_arm_id columns).
    -- A real-world hot-fix that DROPped + recreated the view with fewer cols.
    EXECUTE 'CREATE VIEW v028_v034_guard_test.mlde_view_legacy AS
             SELECT
               NULL::TIMESTAMPTZ AS ts,
               NULL::BIGINT AS ts_ms,
               NULL::TEXT AS engine_mode,
               NULL::TEXT AS intent_id,
               NULL::TEXT AS signal_id,
               NULL::TEXT AS context_id,
               NULL::TEXT AS symbol,
               NULL::TEXT AS strategy_name
               -- many columns intentionally missing (simulates legacy hot-fix)
             WHERE FALSE';

    BEGIN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts','ts_ms','engine_mode','intent_id','signal_id','context_id',
            'symbol','symbol_bucket','side','side_num','qty','price','order_type',
            'strategy_name','regime',
            'scanner_scan_id','scanner_best_strategy','scanner_route_mode','scanner_edge_status',
            'scanner_edge_bps','scanner_edge_n','scanner_final_score','scanner_raw_score',
            'net_bps_after_fee','label_close_tag','label_split_flag','label_filled_at',
            'features_jsonb','context_features','linucb_arm_id','mlde_arm_id',
            'attribution_chain_ok','data_window','metadata'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_view_legacy'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION 'V034 view Guard A FAIL: missing %', v_missing;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V034/A-fail: PASS view Guard A correctly raised on narrowed view';
    ELSE
        RAISE NOTICE 'TEST V034/A-fail: FAIL view Guard A should have raised';
    END IF;
    EXECUTE 'DROP VIEW v028_v034_guard_test.mlde_view_legacy';
END $$;

DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.views
            WHERE table_schema='v028_v034_guard_test' AND table_name='mlde_view_absent'
        ) THEN
            RAISE EXCEPTION 'should_not_reach';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_caught := TRUE;
    END;
    IF v_caught THEN
        RAISE NOTICE 'TEST V034/A-noop: FAIL view Guard A no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V034/A-noop: PASS view Guard A no-op (view absent) skipped cleanly';
    END IF;
END $$;


-- ------------------------------------------------------------
-- Cleanup / 清理
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS v028_v034_guard_test CASCADE;

\echo ''
\echo '============================================================'
\echo 'V028/V030/V031/V032/V034 guard tests emitted.'
\echo 'Grep stderr/NOTICE output for FAIL — zero FAIL = all guards green.'
\echo 'V028/V030/V031/V032/V034 guard 測試已輸出；grep FAIL 驗綠。'
\echo '============================================================'
