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


-- ------------------------------------------------------------
-- Teardown / 清理
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS schema_guard_test CASCADE;

\echo ''
\echo '============================================================'
\echo 'All 9 tests emitted. Grep stderr/NOTICE output for FAIL.'
\echo 'If zero FAIL lines, all guards behave correctly.'
\echo '以上 9 個 test。grep stderr/NOTICE 看 FAIL。零 FAIL 即全綠。'
\echo '============================================================'
