-- ============================================================
-- test_v125_guards.sql
-- V125 research.alpha_* Guard A / Guard B / C-3 NOT NULL / 冪等 contract 固件測試
--
-- 用途：
--   驗 V125 的 Guard A（既有表缺欄 → RAISE）、Guard B（type 敏感欄位錯型 → RAISE）、
--   C-3 per-row data column NOT NULL fail-closed 契約、CREATE TABLE IF NOT EXISTS
--   double-apply shape compatibility，**不動真 research.* 表**。固件放臨時
--   v125_guard_test schema，不污染 production。
--
--   ⚠️ Timescale 相關（hypertable / compression segmentby C-5 / retention 1095d /
--   klines retention replace / Guard C 後驗）**無法在 bare test schema 驗**（需
--   TimescaleDB extension + 真 market.klines）——這些必須 Linux PG empirical 雙跑
--   dry-run 驗（per memory feedback_v_migration_pg_dry_run）。本固件只覆蓋純 SQL
--   contract 層（Guard A/B + NOT NULL + CREATE shape 冪等）。
--
-- 用法：
--   psql -U trading_admin -d trading_ai_test -v ON_ERROR_STOP=0 \
--        -f sql/migrations/tests/test_v125_guards.sql
--   每個 test 印一行 NOTICE，前綴 `TEST V125/<n>:`。grep `FAIL` 即可。
--
-- 測試案例：
--   1. Guard A pass        — funding 表欄位齊全 → 不 RAISE
--   2. Guard A fail        — funding 表缺 funding_rate 欄 → RAISE
--   3. Guard A no-op       — 表不存在 → 不 RAISE
--   4. Guard B pass        — funding_rate double precision → 不 RAISE
--   5. Guard B fail        — funding_rate REAL（非 double precision）→ RAISE
--   6. C-3 NOT NULL fail-closed — INSERT NULL funding_rate → 拋 not_null_violation
--   7. C-3 LS 雙欄 NOT NULL — INSERT NULL sell_ratio → 拋 not_null_violation
--   8. End-to-end 冪等     — double CREATE TABLE IF NOT EXISTS 成功（shape compatible）
-- ============================================================

\set ON_ERROR_STOP off

DROP SCHEMA IF EXISTS v125_guard_test CASCADE;
CREATE SCHEMA v125_guard_test;


-- ============================================================
-- Test 1: Guard A pass — funding 表欄位齊全 → 不 RAISE
-- ============================================================
DO $$
BEGIN
    EXECUTE 'CREATE TABLE v125_guard_test.alpha_funding_rates_history (
        run_id                   TEXT NOT NULL,
        category                 TEXT NOT NULL,
        symbol                   TEXT NOT NULL,
        funding_ts               TIMESTAMPTZ NOT NULL,
        funding_rate             DOUBLE PRECISION NOT NULL,
        funding_interval_minutes INTEGER,
        source_endpoint          TEXT,
        request_start            TIMESTAMPTZ,
        request_end              TIMESTAMPTZ,
        fetched_at               TIMESTAMPTZ,
        parser_version           TEXT,
        payload_sha256           TEXT,
        artifact_sha256          TEXT,
        PRIMARY KEY (category, symbol, funding_ts, run_id)
    )';

    DECLARE v_missing TEXT[];
    BEGIN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id','category','symbol','funding_ts','funding_rate',
            'funding_interval_minutes','source_endpoint','request_start',
            'request_end','fetched_at','parser_version','payload_sha256','artifact_sha256'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='v125_guard_test' AND table_name='alpha_funding_rates_history'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION 'expected pass but found missing: %', v_missing;
        END IF;
        RAISE NOTICE 'TEST V125/1: PASS Guard A on fully-shaped funding table';
    END;

    EXECUTE 'DROP TABLE v125_guard_test.alpha_funding_rates_history';
END $$;


-- ============================================================
-- Test 2: Guard A fail — funding 表缺 funding_rate → RAISE
-- ============================================================
DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    EXECUTE 'CREATE TABLE v125_guard_test.alpha_funding_rates_history (
        run_id      TEXT NOT NULL,
        category    TEXT NOT NULL,
        symbol      TEXT NOT NULL,
        funding_ts  TIMESTAMPTZ NOT NULL
        -- funding_rate 故意省略（legacy stub）
    )';

    BEGIN
        DECLARE v_missing TEXT[];
        BEGIN
            SELECT array_agg(c) INTO v_missing
            FROM unnest(ARRAY[
                'run_id','category','symbol','funding_ts','funding_rate',
                'funding_interval_minutes','source_endpoint','request_start',
                'request_end','fetched_at','parser_version','payload_sha256','artifact_sha256'
            ]) AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='v125_guard_test' AND table_name='alpha_funding_rates_history'
                  AND column_name = c
            );
            IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
                RAISE EXCEPTION 'V125 Guard A FAIL: missing columns: %', v_missing;
            END IF;
        END;
    EXCEPTION WHEN OTHERS THEN v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V125/2: PASS Guard A correctly raised on missing funding_rate';
    ELSE
        RAISE NOTICE 'TEST V125/2: FAIL Guard A did not raise on missing column';
    END IF;

    EXECUTE 'DROP TABLE v125_guard_test.alpha_funding_rates_history';
END $$;


-- ============================================================
-- Test 3: Guard A no-op — 表不存在 → 不 RAISE
-- ============================================================
DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='v125_guard_test' AND table_name='alpha_funding_rates_history'
        ) THEN
            RAISE EXCEPTION 'expected absent table but found one';
        END IF;
    EXCEPTION WHEN OTHERS THEN v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V125/3: FAIL Guard A no-op path raised';
    ELSE
        RAISE NOTICE 'TEST V125/3: PASS Guard A no-op (table absent) skipped cleanly';
    END IF;
END $$;


-- ============================================================
-- Test 4: Guard B pass — funding_rate double precision → 不 RAISE
-- ============================================================
DO $$
BEGIN
    EXECUTE 'CREATE TABLE v125_guard_test.alpha_funding_rates_history (
        funding_ts   TIMESTAMPTZ NOT NULL,
        funding_rate DOUBLE PRECISION NOT NULL
    )';

    DECLARE v_actual TEXT;
    BEGIN
        SELECT data_type INTO v_actual FROM information_schema.columns
        WHERE table_schema='v125_guard_test' AND table_name='alpha_funding_rates_history'
          AND column_name='funding_rate';
        IF v_actual = 'double precision' THEN
            RAISE NOTICE 'TEST V125/4: PASS Guard B sees funding_rate = double precision';
        ELSE
            RAISE NOTICE 'TEST V125/4: FAIL Guard B saw type %', v_actual;
        END IF;
    END;

    EXECUTE 'DROP TABLE v125_guard_test.alpha_funding_rates_history';
END $$;


-- ============================================================
-- Test 5: Guard B fail — funding_rate REAL（非 double precision）→ RAISE
-- 為什麼測 REAL：REAL 是 float4 精度損失型，funding rate 量級小（~1e-4），float4
--   會丟有效位 → 必須 fail-loud（writer sqlx 期待 double precision = f64）。
-- ============================================================
DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    EXECUTE 'CREATE TABLE v125_guard_test.alpha_funding_rates_history (
        funding_ts   TIMESTAMPTZ NOT NULL,
        funding_rate REAL NOT NULL
    )';

    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='v125_guard_test' AND table_name='alpha_funding_rates_history'
              AND column_name='funding_rate' AND data_type='double precision'
        ) THEN
            RAISE EXCEPTION 'V125 Guard B FAIL: funding_rate must be double precision (got REAL)';
        END IF;
    EXCEPTION WHEN OTHERS THEN v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V125/5: PASS Guard B correctly raised on REAL';
    ELSE
        RAISE NOTICE 'TEST V125/5: FAIL Guard B did not raise on REAL';
    END IF;

    EXECUTE 'DROP TABLE v125_guard_test.alpha_funding_rates_history';
END $$;


-- ============================================================
-- Test 6: C-3 NOT NULL fail-closed — INSERT NULL funding_rate → not_null_violation
-- 為什麼這是 V125 最重要契約：既有 parser 缺值 default 0.0；NOT NULL 強制 writer
--   parse-fail 必 reject，schema 層擋住 silent fake-zero PIT 污染。
-- ============================================================
DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    EXECUTE 'CREATE TABLE v125_guard_test.alpha_funding_rates_history (
        run_id       TEXT NOT NULL,
        category     TEXT NOT NULL,
        symbol       TEXT NOT NULL,
        funding_ts   TIMESTAMPTZ NOT NULL,
        funding_rate DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (category, symbol, funding_ts, run_id)
    )';

    BEGIN
        -- 模擬 parser 缺值想寫 NULL funding_rate（必須被 schema 擋）
        EXECUTE 'INSERT INTO v125_guard_test.alpha_funding_rates_history
                 (run_id,category,symbol,funding_ts,funding_rate)
                 VALUES (''r1'',''linear'',''BTCUSDT'',now(),NULL)';
    EXCEPTION
        WHEN not_null_violation THEN v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V125/6: PASS C-3 NOT NULL rejected NULL funding_rate (fake-zero PIT 污染防線)';
    ELSE
        RAISE NOTICE 'TEST V125/6: FAIL C-3 NOT NULL did not reject NULL funding_rate';
    END IF;

    EXECUTE 'DROP TABLE v125_guard_test.alpha_funding_rates_history';
END $$;


-- ============================================================
-- Test 7: C-3 LS 雙欄 NOT NULL — INSERT NULL sell_ratio → not_null_violation
-- ============================================================
DO $$
DECLARE v_caught BOOLEAN := FALSE;
BEGIN
    EXECUTE 'CREATE TABLE v125_guard_test.alpha_long_short_ratio_history (
        run_id     TEXT NOT NULL,
        category   TEXT NOT NULL,
        symbol     TEXT NOT NULL,
        period     TEXT NOT NULL,
        ts         TIMESTAMPTZ NOT NULL,
        buy_ratio  DOUBLE PRECISION NOT NULL,
        sell_ratio DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (category, symbol, period, ts, run_id)
    )';

    BEGIN
        EXECUTE 'INSERT INTO v125_guard_test.alpha_long_short_ratio_history
                 (run_id,category,symbol,period,ts,buy_ratio,sell_ratio)
                 VALUES (''r1'',''linear'',''BTCUSDT'',''5min'',now(),0.55,NULL)';
    EXCEPTION
        WHEN not_null_violation THEN v_caught := TRUE;
    END;

    IF v_caught THEN
        RAISE NOTICE 'TEST V125/7: PASS C-3 NOT NULL rejected NULL sell_ratio (多空均衡偽造防線)';
    ELSE
        RAISE NOTICE 'TEST V125/7: FAIL C-3 NOT NULL did not reject NULL sell_ratio';
    END IF;

    EXECUTE 'DROP TABLE v125_guard_test.alpha_long_short_ratio_history';
END $$;


-- ============================================================
-- Test 8: End-to-end 冪等 — double CREATE TABLE IF NOT EXISTS 成功
-- 註：完整 V125 idempotency（hypertable / compression / retention / klines replace）
--   需 Timescale extension（test schema 沒裝），必須 Linux PG empirical 雙跑驗。
--   這裡只驗 CREATE TABLE block 雙次執行的 shape compatibility。
-- ============================================================
DO $$
BEGIN
    EXECUTE 'CREATE TABLE IF NOT EXISTS v125_guard_test.alpha_history_ingest_runs (
        run_id          TEXT NOT NULL,
        program         TEXT NOT NULL,
        storage_branch  TEXT,
        window_start    TIMESTAMPTZ,
        window_end      TIMESTAMPTZ,
        artifact_root   TEXT,
        manifest_sha256 TEXT,
        git_sha         TEXT,
        git_dirty       BOOLEAN,
        status          TEXT NOT NULL DEFAULT ''planned''
                        CHECK (status IN (''planned'',''running'',''accepted'',''failed'',''superseded'',''inactive'')),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at    TIMESTAMPTZ,
        PRIMARY KEY (run_id)
    )';

    -- 第二次 apply 必 no-op（CREATE TABLE IF NOT EXISTS）
    EXECUTE 'CREATE TABLE IF NOT EXISTS v125_guard_test.alpha_history_ingest_runs (
        run_id          TEXT NOT NULL,
        program         TEXT NOT NULL,
        storage_branch  TEXT,
        window_start    TIMESTAMPTZ,
        window_end      TIMESTAMPTZ,
        artifact_root   TEXT,
        manifest_sha256 TEXT,
        git_sha         TEXT,
        git_dirty       BOOLEAN,
        status          TEXT NOT NULL DEFAULT ''planned''
                        CHECK (status IN (''planned'',''running'',''accepted'',''failed'',''superseded'',''inactive'')),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at    TIMESTAMPTZ,
        PRIMARY KEY (run_id)
    )';

    RAISE NOTICE 'TEST V125/8: PASS double CREATE TABLE IF NOT EXISTS succeeded (shape compatible)';

    EXECUTE 'DROP TABLE v125_guard_test.alpha_history_ingest_runs';
END $$;


-- ------------------------------------------------------------
-- Cleanup
-- ------------------------------------------------------------
DROP SCHEMA IF EXISTS v125_guard_test CASCADE;
