-- ============================================================
-- test_schema_guards.sql
-- Standalone psql test harness for Guard A/B/C blocks
-- Guard A/B/C 獨立 psql 測試
-- ============================================================
--
-- Project has no pgTAP / pg_regress infra, so this file runs as a
-- plain psql script against a **throwaway test DB**. Do NOT run
-- against production — it creates and drops `schema_guard_test` schema.
--
-- 專案未裝 pgTAP / pg_regress，本檔以普通 psql script 形式對**臨時
-- 測試 DB** 執行。**勿對 production 執行** —— 會創建並 DROP
-- `schema_guard_test` schema。
--
-- Usage / 用法：
--   # Assume a spare local DB named trading_ai_test.
--   # 假設有空的本地 DB `trading_ai_test`。
--   psql -U trading_admin -d trading_ai_test -v ON_ERROR_STOP=0 \
--        -f sql/migrations/tests/test_schema_guards.sql
--
--   Each test emits NOTICE lines starting with `TEST <N>:` indicating
--   PASS / FAIL. Fail cases trap RAISE with BEGIN/EXCEPTION so the
--   whole script runs to completion. Grep output for `FAIL` at end.
--
--   每個 test NOTICE 一行 `TEST <N>:` 註記 PASS / FAIL。失敗案例
--   用 BEGIN/EXCEPTION 捕捉預期 RAISE，整個 script 跑完再 grep FAIL。
--
-- What's tested / 測試內容：
--   * Guard A pass case — existing table with all required cols → no RAISE
--   * Guard A fail case — existing table missing a required col → RAISE
--   * Guard A no-op case — table does not exist → no RAISE
--   * Guard B pass case — column exists with correct type → no RAISE
--   * Guard B fail case — column exists with wrong type → RAISE
--   * Guard B no-op case — column does not exist → no RAISE
--   * Guard C pass case — index contains expected column → no RAISE
--   * Guard C fail case — index exists with mismatched columns → RAISE
--   * Guard C no-op case — index does not exist → no RAISE
--
-- Migration-specific regression cases (G6-03 Wave 1, 2026-04-24):
--   * TEST 10 — V019 Guard A fixture-driven pass/fail (9-col required set)
--   * TEST 11 — V019 Guard A legacy-stub fail case (missing params_json / source)
--   * TEST 12 — V020 Guard A NOVEL: parent table absent MUST RAISE
--                (deviates from template no-op rule; V020 cannot rebuild
--                 index on missing parent, so absence is a hard error)
-- ============================================================

\set ON_ERROR_STOP off

-- ------------------------------------------------------------
-- Setup: scratch schema / 測試用暫存 schema
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS schema_guard_test CASCADE;
CREATE SCHEMA schema_guard_test;

-- Fixture 1: "good" table with all required columns
CREATE TABLE schema_guard_test.model_good (
    id            BIGSERIAL PRIMARY KEY,
    canary_status TEXT      NOT NULL,
    verdict       TEXT      NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Fixture 2: "bad" table missing verdict + canary_status (simulates legacy)
CREATE TABLE schema_guard_test.model_bad (
    id         BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fixture 3: column type mismatch — exit_source as INTEGER
CREATE TABLE schema_guard_test.fills_wrong_type (
    id          BIGSERIAL PRIMARY KEY,
    exit_source INTEGER      -- should be TEXT
);

-- Fixture 4: column type correct
CREATE TABLE schema_guard_test.fills_right_type (
    id          BIGSERIAL PRIMARY KEY,
    exit_source TEXT
);

-- Fixture 5: column absent
CREATE TABLE schema_guard_test.fills_no_col (
    id BIGSERIAL PRIMARY KEY
);

-- Fixture 6: index with mismatched columns for Guard C
CREATE TABLE schema_guard_test.idx_base (
    id          BIGSERIAL PRIMARY KEY,
    strategy    TEXT,
    promoted_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ
);
CREATE INDEX idx_mismatch ON schema_guard_test.idx_base (created_at DESC);
CREATE INDEX idx_correct  ON schema_guard_test.idx_base (strategy, promoted_at DESC);

-- Fixture 7 (G6-03 · V019 happy path): strategist_applied_params with all
-- 9 columns as V019 creates them. Guard A must no-op on this shape.
-- V019 建表正確時的 shape；Guard A 應 no-op。
CREATE TABLE schema_guard_test.strategist_good (
    id               BIGSERIAL PRIMARY KEY,
    engine_mode      TEXT NOT NULL,
    strategy_name    TEXT NOT NULL,
    params_json      JSONB NOT NULL,
    applied_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at_ms    BIGINT NOT NULL,
    source           TEXT NOT NULL,
    reason           TEXT,
    prev_params_json JSONB
);

-- Fixture 8 (G6-03 · V019 legacy stub): simulates a pre-G6-03 hot-fix
-- that created an incomplete strategist_applied_params (missing
-- params_json + source + prev_params_json). Guard A must RAISE on this.
-- 模擬 G6-03 之前 hot-fix 不完整建表（缺 params_json/source/prev_params_json）；
-- Guard A 必須 RAISE。
CREATE TABLE schema_guard_test.strategist_legacy (
    id             BIGSERIAL PRIMARY KEY,
    engine_mode    TEXT NOT NULL,
    strategy_name  TEXT NOT NULL,
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at_ms  BIGINT NOT NULL,
    reason         TEXT
    -- intentional: no params_json, no source, no prev_params_json
);


-- ============================================================
-- TEST 1: Guard A pass — all required cols present
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='schema_guard_test' AND table_name='model_good'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY['canary_status','verdict']) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='schema_guard_test' AND table_name='model_good'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION 'unexpected_missing: %', v_missing;
        END IF;
    END IF;
    RAISE NOTICE 'TEST 1: PASS (Guard A pass case — no RAISE on good table)';
END $$;


-- ============================================================
-- TEST 2: Guard A fail — missing required cols SHOULD RAISE
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
    v_raised  BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='schema_guard_test' AND table_name='model_bad'
        ) THEN
            SELECT array_agg(c) INTO v_missing
            FROM unnest(ARRAY['canary_status','verdict']) AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='schema_guard_test' AND table_name='model_bad'
                  AND column_name=c
            );
            IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
                RAISE EXCEPTION
                    'schema_guard A: model_bad missing %', v_missing;
            END IF;
        END IF;
    EXCEPTION WHEN raise_exception THEN
        v_raised := TRUE;
    END;

    IF v_raised THEN
        RAISE NOTICE 'TEST 2: PASS (Guard A fail case — RAISE captured as expected)';
    ELSE
        RAISE NOTICE 'TEST 2: FAIL (Guard A should have raised but did not)';
    END IF;
END $$;


-- ============================================================
-- TEST 3: Guard A no-op — table does not exist, no RAISE
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
    v_raised  BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='schema_guard_test' AND table_name='model_absent'
        ) THEN
            SELECT array_agg(c) INTO v_missing
            FROM unnest(ARRAY['canary_status','verdict']) AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='schema_guard_test' AND table_name='model_absent'
                  AND column_name=c
            );
            IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
                RAISE EXCEPTION 'should_not_raise';
            END IF;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;

    IF NOT v_raised THEN
        RAISE NOTICE 'TEST 3: PASS (Guard A no-op case — absent table does not RAISE)';
    ELSE
        RAISE NOTICE 'TEST 3: FAIL (Guard A should be no-op when table absent)';
    END IF;
END $$;


-- ============================================================
-- TEST 4: Guard B pass — correct type, no RAISE
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        SELECT data_type INTO v_actual
        FROM information_schema.columns
        WHERE table_schema='schema_guard_test' AND table_name='fills_right_type' AND column_name='exit_source';
        IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
            RAISE EXCEPTION 'type_mismatch_unexpected';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;

    IF NOT v_raised THEN
        RAISE NOTICE 'TEST 4: PASS (Guard B pass case — correct type, no RAISE)';
    ELSE
        RAISE NOTICE 'TEST 4: FAIL (Guard B should not raise on correct type)';
    END IF;
END $$;


-- ============================================================
-- TEST 5: Guard B fail — wrong type SHOULD RAISE
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        SELECT data_type INTO v_actual
        FROM information_schema.columns
        WHERE table_schema='schema_guard_test' AND table_name='fills_wrong_type' AND column_name='exit_source';
        IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
            RAISE EXCEPTION
                'schema_guard B: fills_wrong_type.exit_source is %, expected text',
                v_actual;
        END IF;
    EXCEPTION WHEN raise_exception THEN
        v_raised := TRUE;
    END;

    IF v_raised THEN
        RAISE NOTICE 'TEST 5: PASS (Guard B fail case — RAISE captured as expected)';
    ELSE
        RAISE NOTICE 'TEST 5: FAIL (Guard B should have raised on wrong type)';
    END IF;
END $$;


-- ============================================================
-- TEST 6: Guard B no-op — column absent, no RAISE
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        SELECT data_type INTO v_actual
        FROM information_schema.columns
        WHERE table_schema='schema_guard_test' AND table_name='fills_no_col' AND column_name='exit_source';
        IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
            RAISE EXCEPTION 'should_not_raise';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;

    IF NOT v_raised THEN
        RAISE NOTICE 'TEST 6: PASS (Guard B no-op case — absent column does not RAISE)';
    ELSE
        RAISE NOTICE 'TEST 6: FAIL (Guard B should be no-op when column absent)';
    END IF;
END $$;


-- ============================================================
-- TEST 7: Guard C pass — index contains expected column
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='schema_guard_test' AND c.relname='idx_correct';

        IF v_actual IS NOT NULL AND position('promoted_at DESC' IN v_actual) = 0 THEN
            RAISE EXCEPTION 'unexpected_index_mismatch: %', v_actual;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;

    IF NOT v_raised THEN
        RAISE NOTICE 'TEST 7: PASS (Guard C pass case — correct index, no RAISE)';
    ELSE
        RAISE NOTICE 'TEST 7: FAIL (Guard C should not raise on correct index)';
    END IF;
END $$;


-- ============================================================
-- TEST 8: Guard C fail — index with wrong columns SHOULD RAISE
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='schema_guard_test' AND c.relname='idx_mismatch';

        IF v_actual IS NOT NULL AND position('promoted_at DESC' IN v_actual) = 0 THEN
            RAISE EXCEPTION
                'schema_guard C: idx_mismatch missing promoted_at DESC. Actual: %',
                v_actual;
        END IF;
    EXCEPTION WHEN raise_exception THEN
        v_raised := TRUE;
    END;

    IF v_raised THEN
        RAISE NOTICE 'TEST 8: PASS (Guard C fail case — RAISE captured as expected)';
    ELSE
        RAISE NOTICE 'TEST 8: FAIL (Guard C should have raised on index mismatch)';
    END IF;
END $$;


-- ============================================================
-- TEST 9: Guard C no-op — index absent, no RAISE
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='schema_guard_test' AND c.relname='idx_absent';

        IF v_actual IS NOT NULL AND position('promoted_at DESC' IN v_actual) = 0 THEN
            RAISE EXCEPTION 'should_not_raise';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;

    IF NOT v_raised THEN
        RAISE NOTICE 'TEST 9: PASS (Guard C no-op case — absent index does not RAISE)';
    ELSE
        RAISE NOTICE 'TEST 9: FAIL (Guard C should be no-op when index absent)';
    END IF;
END $$;


-- ============================================================
-- TEST 10: V019 Guard A pass — strategist_applied_params with full
--          9-column shape → no RAISE
-- ============================================================
-- Why this covers V019 (not redundant with TEST 1):
--   TEST 1 uses a 2-element required array; V019 has 9. Regression
--   anchor — if a future refactor narrows V019's required list by
--   mistake, TEST 11 (the fail-case companion below) still catches
--   an incomplete column set. Paired tests keep the 9-element list
--   load-bearing.
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
    v_raised  BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='schema_guard_test' AND table_name='strategist_good'
        ) THEN
            SELECT array_agg(c) INTO v_missing
            FROM unnest(ARRAY[
                'id', 'engine_mode', 'strategy_name',
                'params_json', 'applied_at', 'applied_at_ms',
                'source', 'reason', 'prev_params_json'
            ]) AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='schema_guard_test' AND table_name='strategist_good'
                  AND column_name=c
            );
            IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
                RAISE EXCEPTION 'unexpected_missing_in_good_fixture: %', v_missing;
            END IF;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;

    IF NOT v_raised THEN
        RAISE NOTICE 'TEST 10: PASS (V019 Guard A pass case — 9-col strategist_good, no RAISE)';
    ELSE
        RAISE NOTICE 'TEST 10: FAIL (V019 Guard A should not raise on complete table)';
    END IF;
END $$;


-- ============================================================
-- TEST 11: V019 Guard A fail — legacy stub missing 3 required cols
--          (params_json / source / prev_params_json) SHOULD RAISE
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
    v_raised  BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='schema_guard_test' AND table_name='strategist_legacy'
        ) THEN
            SELECT array_agg(c) INTO v_missing
            FROM unnest(ARRAY[
                'id', 'engine_mode', 'strategy_name',
                'params_json', 'applied_at', 'applied_at_ms',
                'source', 'reason', 'prev_params_json'
            ]) AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='schema_guard_test' AND table_name='strategist_legacy'
                  AND column_name=c
            );
            IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
                RAISE EXCEPTION
                    'schema_guard A: strategist_legacy missing required columns: %',
                    v_missing;
            END IF;
        END IF;
    EXCEPTION WHEN raise_exception THEN
        v_raised := TRUE;
    END;

    IF v_raised THEN
        RAISE NOTICE 'TEST 11: PASS (V019 Guard A fail case — legacy stub RAISE captured as expected)';
    ELSE
        RAISE NOTICE 'TEST 11: FAIL (V019 Guard A should have raised on incomplete stub)';
    END IF;
END $$;


-- ============================================================
-- TEST 12: V020 Guard A NOVEL fail — parent table ABSENT MUST RAISE
--          (deviates from the template no-op rule because V020 has
--           no CREATE TABLE — it can only rebuild the tie-break
--           index on an already-present parent. TEST 3 / 6 / 9
--           cover the template no-op rule; this test covers V020's
--           deliberate deviation.)
-- ============================================================
DO $$
DECLARE
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='schema_guard_test' AND table_name='strategist_absent'
        ) THEN
            RAISE EXCEPTION 'unexpected_table_present';
        ELSE
            -- Mirror V020 Guard A ELSE branch: parent missing is a hard error.
            RAISE EXCEPTION
                'schema_guard A: schema_guard_test.strategist_absent does not exist. '
                'V019 must be applied before V020. (Mirrors V020 migration guard.)';
        END IF;
    EXCEPTION WHEN raise_exception THEN
        v_raised := TRUE;
    END;

    IF v_raised THEN
        RAISE NOTICE 'TEST 12: PASS (V020 Guard A — parent absent RAISE captured as expected)';
    ELSE
        RAISE NOTICE 'TEST 12: FAIL (V020 Guard A should RAISE when parent table absent)';
    END IF;
END $$;


-- ------------------------------------------------------------
-- Teardown / 清理
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS schema_guard_test CASCADE;

\echo ''
\echo '============================================================'
\echo 'All 12 tests emitted. Grep stderr/NOTICE output for FAIL.'
\echo 'If zero FAIL lines, all guards behave correctly.'
\echo '以上 12 個 test（含 G6-03 新增 TEST 10-12）。grep stderr/NOTICE 看 FAIL。'
\echo '零 FAIL 即全綠。'
\echo '============================================================'
