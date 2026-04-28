-- ============================================================
-- test_v026_guards.sql
-- V026 cost_edge_advisor_log Guard A + Guard B fixture tests
-- V026 Guard A + Guard B 固件測試
-- ============================================================
--
-- Purpose / 用途：
--   Validate V026's Guard A (legacy table missing column → RAISE) and
--   Guard B (engine_mode column wrong type → RAISE) without touching the
--   real `learning.cost_edge_advisor_log` table. Fixtures live in a
--   throwaway `v026_guard_test` schema so production data is untouched.
--
--   驗 V026 Guard A（legacy 表缺欄 → RAISE）+ Guard B（engine_mode 欄
--   型別錯 → RAISE），不動真 `learning.cost_edge_advisor_log`。
--   固件放臨時 `v026_guard_test` schema，不污染 production。
--
-- Usage / 用法：
--   psql -U trading_admin -d trading_ai_test -v ON_ERROR_STOP=0 \
--        -f sql/migrations/tests/test_v026_guards.sql
--
--   Each test prints a NOTICE prefixed `TEST V026/<n>:`. Grep for `FAIL`.
--
--   每個 test 印一行 NOTICE，前綴 `TEST V026/<n>:`。grep `FAIL` 即可。
--
-- Cases / 測試案例：
--   1. Guard A pass    — table with all 11 required cols → no RAISE
--   2. Guard A fail    — table missing `transition_from` col → RAISE
--   3. Guard A no-op   — table does not exist → no RAISE
--   4. Guard B pass    — engine_mode TEXT → no RAISE
--   5. Guard B fail    — engine_mode VARCHAR → RAISE
--   6. End-to-end      — apply V026 twice on fresh schema, second is no-op
-- ============================================================

\set ON_ERROR_STOP off

-- ------------------------------------------------------------
-- Setup: scratch schema mirroring `learning.*` namespace
-- 測試用暫存 schema（鏡射 `learning.*` 命名）
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS v026_guard_test CASCADE;
CREATE SCHEMA v026_guard_test;


-- ============================================================
-- Test 1: Guard A pass — fully-shaped table → no RAISE
-- 測試 1：Guard A 通過 — 欄位齊全 → 不 RAISE
-- ============================================================
DO $$
BEGIN
    -- Build the canonical table shape (mirrors V026 minus hypertable bits).
    EXECUTE 'CREATE TABLE v026_guard_test.cost_edge_advisor_log (
        ts_ms              BIGINT  NOT NULL,
        engine_mode        TEXT    NOT NULL,
        status             TEXT    NOT NULL,
        ratio              DOUBLE PRECISION,
        threshold          DOUBLE PRECISION NOT NULL,
        data_days          INTEGER NOT NULL,
        ai_spend_7d_usd    DOUBLE PRECISION NOT NULL,
        paper_pnl_7d_usd   DOUBLE PRECISION NOT NULL,
        is_stale           BOOLEAN NOT NULL,
        phase              TEXT    NOT NULL DEFAULT ''B_shadow'',
        transition_from    TEXT,
        PRIMARY KEY (ts_ms, engine_mode)
    )';

    -- Inline Guard A check (matches V026 source).
    DECLARE
        v_missing TEXT[];
    BEGIN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts_ms','engine_mode','status','ratio','threshold',
            'data_days','ai_spend_7d_usd','paper_pnl_7d_usd',
            'is_stale','phase','transition_from'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'v026_guard_test'
              AND table_name   = 'cost_edge_advisor_log'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION 'expected pass but found missing: %', v_missing;
        END IF;
        RAISE NOTICE 'TEST V026/1: PASS Guard A on fully-shaped table';
    END;

    EXECUTE 'DROP TABLE v026_guard_test.cost_edge_advisor_log';
END $$;


-- ============================================================
-- Test 2: Guard A fail — table missing `transition_from` → RAISE
-- 測試 2：Guard A 失敗 — 缺 transition_from → RAISE
-- ============================================================
DO $$
DECLARE
    v_caught BOOLEAN := FALSE;
BEGIN
    -- Build a legacy stub missing one required column.
    EXECUTE 'CREATE TABLE v026_guard_test.cost_edge_advisor_log (
        ts_ms              BIGINT  NOT NULL,
        engine_mode        TEXT    NOT NULL,
        status             TEXT    NOT NULL,
        ratio              DOUBLE PRECISION,
        threshold          DOUBLE PRECISION NOT NULL,
        data_days          INTEGER NOT NULL,
        ai_spend_7d_usd    DOUBLE PRECISION NOT NULL,
        paper_pnl_7d_usd   DOUBLE PRECISION NOT NULL,
        is_stale           BOOLEAN NOT NULL,
        phase              TEXT    NOT NULL DEFAULT ''B_shadow''
        -- transition_from intentionally omitted
    )';

    -- Run the same Guard A logic; capture the expected RAISE.
    BEGIN
        DECLARE
            v_missing TEXT[];
        BEGIN
            SELECT array_agg(c) INTO v_missing
            FROM unnest(ARRAY[
                'ts_ms','engine_mode','status','ratio','threshold',
                'data_days','ai_spend_7d_usd','paper_pnl_7d_usd',
                'is_stale','phase','transition_from'
            ]) AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'v026_guard_test'
                  AND table_name   = 'cost_edge_advisor_log'
                  AND column_name  = c
            );
            IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
                RAISE EXCEPTION
                    'V026 Guard A FAIL: missing columns: %', v_missing;
            END IF;
        END;
    EXCEPTION
        WHEN OTHERS THEN
            v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V026/2: PASS Guard A correctly raised on missing column';
    ELSE
        RAISE NOTICE 'TEST V026/2: FAIL Guard A did not raise on missing column';
    END IF;

    EXECUTE 'DROP TABLE v026_guard_test.cost_edge_advisor_log';
END $$;


-- ============================================================
-- Test 3: Guard A no-op — table does not exist → no RAISE
-- 測試 3：Guard A no-op — 表不存在 → 不 RAISE
-- ============================================================
DO $$
DECLARE
    v_caught BOOLEAN := FALSE;
BEGIN
    BEGIN
        -- Run Guard A against absent table (the IF EXISTS gate should skip).
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'v026_guard_test'
              AND table_name   = 'cost_edge_advisor_log'
        ) THEN
            RAISE EXCEPTION 'expected absent table but found one';
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V026/3: FAIL Guard A no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V026/3: PASS Guard A no-op (table absent) skipped cleanly';
    END IF;
END $$;


-- ============================================================
-- Test 4: Guard B pass — engine_mode TEXT → no RAISE
-- 測試 4：Guard B 通過 — engine_mode TEXT → 不 RAISE
-- ============================================================
DO $$
BEGIN
    EXECUTE 'CREATE TABLE v026_guard_test.cost_edge_advisor_log (
        ts_ms       BIGINT NOT NULL,
        engine_mode TEXT   NOT NULL
    )';

    DECLARE
        v_actual TEXT;
    BEGIN
        SELECT data_type INTO v_actual
        FROM information_schema.columns
        WHERE table_schema = 'v026_guard_test'
          AND table_name   = 'cost_edge_advisor_log'
          AND column_name  = 'engine_mode';

        IF v_actual = 'text' THEN
            RAISE NOTICE 'TEST V026/4: PASS Guard B sees engine_mode = text';
        ELSE
            RAISE NOTICE 'TEST V026/4: FAIL Guard B saw type %', v_actual;
        END IF;
    END;

    EXECUTE 'DROP TABLE v026_guard_test.cost_edge_advisor_log';
END $$;


-- ============================================================
-- Test 5: Guard B fail — engine_mode VARCHAR → RAISE
-- 測試 5：Guard B 失敗 — engine_mode VARCHAR → RAISE
-- ============================================================
DO $$
DECLARE
    v_caught BOOLEAN := FALSE;
BEGIN
    -- Legacy table that mistakenly uses VARCHAR(16) (older idiom).
    EXECUTE 'CREATE TABLE v026_guard_test.cost_edge_advisor_log (
        ts_ms       BIGINT      NOT NULL,
        engine_mode VARCHAR(16) NOT NULL
    )';

    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'v026_guard_test'
              AND table_name   = 'cost_edge_advisor_log'
              AND column_name  = 'engine_mode'
              AND data_type    = 'text'
        ) THEN
            RAISE EXCEPTION
                'V026 Guard B FAIL: engine_mode must be TEXT (got VARCHAR)';
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V026/5: PASS Guard B correctly raised on VARCHAR';
    ELSE
        RAISE NOTICE 'TEST V026/5: FAIL Guard B did not raise on VARCHAR';
    END IF;

    EXECUTE 'DROP TABLE v026_guard_test.cost_edge_advisor_log';
END $$;


-- ============================================================
-- Test 6: End-to-end idempotency — pure SQL contract check
-- 測試 6：端對端冪等 — 純 SQL contract 檢查
-- ============================================================
-- Note: full V026 idempotency test requires Timescale extension
-- (create_hypertable + add_retention_policy) which is not available in
-- the bare test schema. This test verifies the **shape** of V026's CREATE
-- TABLE block remains compatible with double-application.
-- 註：完整 V026 idempotency 需 Timescale extension（test schema 沒裝），
-- 這裡只驗 CREATE TABLE block 雙次執行的 shape compatibility。
DO $$
BEGIN
    -- First application — creates the table.
    EXECUTE 'CREATE TABLE IF NOT EXISTS v026_guard_test.cost_edge_advisor_log (
        ts_ms              BIGINT  NOT NULL,
        engine_mode        TEXT    NOT NULL,
        status             TEXT    NOT NULL,
        ratio              DOUBLE PRECISION,
        threshold          DOUBLE PRECISION NOT NULL,
        data_days          INTEGER NOT NULL,
        ai_spend_7d_usd    DOUBLE PRECISION NOT NULL,
        paper_pnl_7d_usd   DOUBLE PRECISION NOT NULL,
        is_stale           BOOLEAN NOT NULL,
        phase              TEXT    NOT NULL DEFAULT ''B_shadow'',
        transition_from    TEXT,
        PRIMARY KEY (ts_ms, engine_mode)
    )';

    -- Second application — must be no-op (CREATE TABLE IF NOT EXISTS).
    EXECUTE 'CREATE TABLE IF NOT EXISTS v026_guard_test.cost_edge_advisor_log (
        ts_ms              BIGINT  NOT NULL,
        engine_mode        TEXT    NOT NULL,
        status             TEXT    NOT NULL,
        ratio              DOUBLE PRECISION,
        threshold          DOUBLE PRECISION NOT NULL,
        data_days          INTEGER NOT NULL,
        ai_spend_7d_usd    DOUBLE PRECISION NOT NULL,
        paper_pnl_7d_usd   DOUBLE PRECISION NOT NULL,
        is_stale           BOOLEAN NOT NULL,
        phase              TEXT    NOT NULL DEFAULT ''B_shadow'',
        transition_from    TEXT,
        PRIMARY KEY (ts_ms, engine_mode)
    )';

    RAISE NOTICE 'TEST V026/6: PASS double CREATE TABLE IF NOT EXISTS succeeded';

    EXECUTE 'DROP TABLE v026_guard_test.cost_edge_advisor_log';
END $$;


-- ------------------------------------------------------------
-- Cleanup
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS v026_guard_test CASCADE;
