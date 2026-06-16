-- ============================================================
-- V141: research.kline_calibration — intraday kline 真值校準 / drift guardrail 帳本
--       （INTRADAY-KLINES-PERMANENT-FIX R3，PA 設計 §3.3）
--
-- 目的 / Motivation:
--   intraday klines（1m/5m/15m/1h/4h）一度是 live WS tick-synth 路徑產生的退化單快照
--   bar（close 攜真值但錯位一格、wicks 死、range 2-37%、turnover 近 0）。R1 producer fix
--   改走 WS-confirmed-candle 直寫真值後，本表是「持續驗證 market.klines 仍對齊 Bybit
--   authoritative REST」的監測帳本：Rust bin kline_calibration_checker（cron 觸發）對旋轉
--   採樣的 (symbol, timeframe, window) 拉 local market.klines + Bybit get_klines 對齊 ts，
--   算 close_match / range_ratio / corr@0 / corr@+1 / turnover_nonzero / gap，drift 命中即
--   走既有耐久 alert sink（alerts.jsonl）並把該 cell 留作 R4 recal 隊列。
--
--   ⚠️ 本 migration 僅建 schema 表 + index + Guard。checker bin / cron wrapper / healthcheck
--   全不在本 migration 範圍。
--
-- SOURCE: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-16--intraday-klines-permanent-fix-architecture.md §3.3
--
-- 範圍 / Scope (V141):
--   §A CREATE SCHEMA IF NOT EXISTS research（idempotent；V125 已建，此處冪等保險）
--   §B research.kline_calibration CREATE TABLE IF NOT EXISTS + Guard A（必要欄完整性）
--   §C Guard B type 反射（metric 欄 real / time 欄 timestamptz / drift_flag boolean）
--   §C-index hot-path index（最舊 checked_ts 取旋轉游標 + drift cell hot-list 重採）
--   §D Guard C 後驗（表存在 + PK + index 到位）
--
-- 設計決策:
--   【非 hypertable（與 V130/V125 不同）】
--     本表是低基數監測帳本：旋轉採樣每跑 ~30 cell × daily ≈ 900 row/月，遠小於
--     market.klines 的 1.44M。無 time-series chunk rotate / compression 需求，普通表足夠；
--     避免 TimescaleDB compressed-chunk 對後續 R4 recal 工作流的無謂耦合。research schema
--     append-only 慣例（只 INSERT，run_id 區分各跑）。
--
--   【PK = (run_id, symbol, timeframe, window_start, window_end)】
--     一次 checker run（run_id = uuid）對一個 (symbol, timeframe) 在一個對齊窗只算一次。
--     同 run 對同 cell 同窗重跑 ON CONFLICT DO NOTHING 冪等（checker 內 round-robin 不會
--     在同 run 重複採同 cell；PK 是防禦縱深）。不同 run_id 保各自快照（drift 時間線可追）。
--
--   【metric 欄全 nullable REAL】
--     樣本不足（對齊 bar < 2 無法算 corr / range_ratio）時 metric 欄留 NULL（fail-soft，不
--     偽造 0），checker 在 row 仍寫 drift_flag=false + drift_reasons='insufficient_sample'。
--     對齊 root principle #6（不確定保守）+ #10（事實/推論/假設分離：NULL=未測，非=測得 0）。
--
--   【冪等 double-apply 全 no-op】(per CLAUDE §Data「applying twice」)
--     - CREATE SCHEMA / TABLE IF NOT EXISTS → 第二次 no-op（Guard A 已驗 shape）
--     - CREATE INDEX IF NOT EXISTS         → 第二次 no-op（Guard C 已驗 shape）
--     - COMMENT ON                         → 可重跑
--
-- Idempotency 重跑兩次必 PASS（per memory feedback_v_migration_pg_dry_run double-apply
--   mandatory）。本 migration 須 Linux PG empirical 雙跑 dry-run 才能 sign-off
--   （Mac mock PG 抓不到 PG runtime semantic）—— E1-B 已標為 sign-off 前 blocker。
--
-- Guard（fail-closed + idempotent）:
--   Guard A — CREATE TABLE IF NOT EXISTS 前驗既有表必要欄完整（缺 → RAISE）
--   Guard B — type 敏感欄位反射（metric real / time timestamptz / drift_flag boolean）
--   Guard C — 建後驗 表存在 + PK + load-bearing index 到位
--
-- E2 review checklist:
--   1. Guard A 對必要欄完整性（重跑 shape drift → RAISE）
--   2. PK = (run_id, symbol, timeframe, window_start, window_end) 確保同 run 同窗冪等
--   3. metric 欄全 nullable（樣本不足留 NULL，不偽造 0）
--   4. idx_kline_calibration_rotation（checked_ts ASC）= 旋轉游標取最舊先採
--   5. idx_kline_calibration_drift（drift_flag, checked_ts DESC）= drift cell hot-list
--   6. 純監測帳本：無 order / intent / lease / live 欄；checker 只讀 market.klines 不寫
--   7. rollback：DROP RESTRICT（純監測資料，無外部依賴）
--
-- 硬邊界:
--   - 不碰 market.klines row shape（checker 對 klines 純唯讀，不 ALTER）。
--   - 不改 max_retries / live_execution_allowed / execution_authority / system_mode（無關）。
--   - monitoring-only：本表只存校準判定，無 order / intent / lease 欄；不授權任何 live 行為。
--   - append-only 語義：前向累積；rollback 不靜默刪生產校準帳。
--
-- migration latest: V139 → V141（V139 agent_memory_store 已 applied）。
--   ⚠️ 跳 V140：V140 號已被 helper_scripts/db/manual_V140_agent_memory_vector.sql
--   占用（L2 記憶層 pgvector，PA 2026-06-11 spec 路徑 B「不入 sqlx 鏈、operator 手動 apply」）。
--   為避免 sqlx 鏈號與 manual path-B 號歧義（migration 號是 git 看不見的全局命名空間，
--   撞號=load-bearing bug，見 memory V137/[82] 教訓），本 sqlx migration 取下一自由號 V141。
-- ============================================================

BEGIN;

-- ============================================================
-- §A CREATE SCHEMA IF NOT EXISTS research（idempotent）
-- research namespace 已由 V125 建立；此處冪等保險（若 V141 在 V125 前單獨 apply）。
-- 第二次 apply no-op。
-- ============================================================
CREATE SCHEMA IF NOT EXISTS research;

-- ============================================================
-- §B research.kline_calibration — intraday kline 真值校準判定（普通表，append-only）
-- 每 (run_id, symbol, timeframe, window) 一列。
-- ============================================================

-- Guard A: kline_calibration 既有表必要欄完整性（缺 ≥1 → RAISE）
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'kline_calibration'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id', 'checked_ts', 'symbol', 'timeframe',
            'window_start', 'window_end',
            'close_match_pct', 'range_ratio', 'corr_shift0', 'corr_shift1',
            'turnover_nonzero_pct', 'gap_pct',
            'observed_rows', 'expected_rows',
            'drift_flag', 'drift_reasons', 'checker_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'kline_calibration'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V141 Guard A FAIL: research.kline_calibration exists but missing '
                'required columns: %. 解決 legacy schema drift（DROP + re-apply 或 ALTER ADD）'
                '後重跑 V141。', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.kline_calibration (
    -- 一次 checker run（uuid）+ 採樣 cell + 對齊窗 = 一筆校準判定
    run_id               TEXT        NOT NULL,
    -- 本筆寫入時刻（旋轉游標排序鍵：取最舊 checked_ts 的 cell 下一批優先採）
    checked_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol               TEXT        NOT NULL,
    timeframe            TEXT        NOT NULL,   -- '1m' | '5m' | '15m' | '1h' | '4h'
    -- 採樣窗 [window_start, window_end)（UTC；對齊 local 與 Bybit 的 ts 比較區間）
    window_start         TIMESTAMPTZ NOT NULL,
    window_end           TIMESTAMPTZ NOT NULL,

    -- ── truth-test metrics（全 nullable：樣本不足留 NULL，不偽造 0）──
    -- local.close == bybit.close（相對誤差 < 1e-4）佔對齊 bar 比例
    close_match_pct      REAL,
    -- mean(local.high-low) / mean(bybit.high-low)：tick-synth 退化 → 遠 < 1（PA 閾值 < 0.5 drift）
    range_ratio          REAL,
    -- corr(local close 回報, bybit close 回報) @ shift 0（PA 閾值 < 0.9 drift）
    corr_shift0          REAL,
    -- 同上 @ shift +1（診斷 one-bar offset；非門檻，落表供分析）
    corr_shift1          REAL,
    -- local.turnover > 0 佔比（tick-synth 路徑近 0；PA all-zero drift）
    turnover_nonzero_pct REAL,
    -- (expected - observed) / expected：缺 bar 率（PA 閾值 > 5% drift）
    gap_pct              REAL,

    -- ── 覆蓋計數 ──
    observed_rows        INTEGER     NOT NULL DEFAULT 0,  -- 對齊窗內 local 實得 bar 數
    expected_rows        INTEGER     NOT NULL DEFAULT 0,  -- expected_bars_for(window, period)

    -- ── drift 判定 ──
    drift_flag           BOOLEAN     NOT NULL DEFAULT FALSE,
    drift_reasons        TEXT        NOT NULL DEFAULT '', -- 逗號分隔命中門檻（'range_ratio,corr_shift0' 等）
    checker_version      TEXT        NOT NULL,            -- bin CHECKER_VERSION（邏輯變動遞增）

    -- 一次 run 對同 cell 同窗只算一次（防禦縱深；checker round-robin 不重採同 cell）。
    PRIMARY KEY (run_id, symbol, timeframe, window_start, window_end)
);

-- ============================================================
-- Guard B: type 敏感欄位反射
-- 為什麼：checker（Rust bin）寫入靠 type 對齊；type drift = silent write fail / 精度損失。
--   驗 metric (real) / time col (timestamptz) / drift_flag (boolean)。
--   column 不存在 v_actual=NULL → skip（CREATE TABLE 已負責建）。
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- checked_ts 必 timestamptz（旋轉游標排序鍵）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='kline_calibration' AND column_name='checked_ts';
    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'V141 Guard B FAIL: kline_calibration.checked_ts is %, expected timestamptz.', v_actual;
    END IF;

    -- corr_shift0 必 real（metric 型別契約；checker 綁 f32）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='kline_calibration' AND column_name='corr_shift0';
    IF v_actual IS NOT NULL AND v_actual <> 'real' THEN
        RAISE EXCEPTION 'V141 Guard B FAIL: kline_calibration.corr_shift0 is %, expected real.', v_actual;
    END IF;

    -- range_ratio 必 real
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='kline_calibration' AND column_name='range_ratio';
    IF v_actual IS NOT NULL AND v_actual <> 'real' THEN
        RAISE EXCEPTION 'V141 Guard B FAIL: kline_calibration.range_ratio is %, expected real.', v_actual;
    END IF;

    -- drift_flag 必 boolean
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='kline_calibration' AND column_name='drift_flag';
    IF v_actual IS NOT NULL AND v_actual <> 'boolean' THEN
        RAISE EXCEPTION 'V141 Guard B FAIL: kline_calibration.drift_flag is %, expected boolean.', v_actual;
    END IF;
END $$;

-- ============================================================
-- §C-index Hot-path indexes
-- 1. (checked_ts ASC) — 旋轉游標：取「最舊 checked_ts」的 (symbol,tf) 下一批優先採，
--    確保 ~26 天全 153×5 cell 輪一遍（round-robin 公平採樣）。
-- 2. (drift_flag, checked_ts DESC) — drift cell hot-list：drift 命中 cell 下次優先重採，
--    並供 R4 recal runbook --from-calibration-queue 取待 recal 清單。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_kline_calibration_rotation
    ON research.kline_calibration (checked_ts ASC);
CREATE INDEX IF NOT EXISTS idx_kline_calibration_drift
    ON research.kline_calibration (drift_flag, checked_ts DESC);

-- ============================================================
-- §COMMENT 語義文檔（idempotent: COMMENT ON 可重跑）
-- ============================================================
COMMENT ON TABLE research.kline_calibration IS
    'intraday kline 真值校準 / drift guardrail 帳本（V141；INTRADAY-KLINES-PERMANENT-FIX '
    'R3）。Rust bin kline_calibration_checker（cron 觸發）對旋轉採樣 (symbol,timeframe,window) '
    '拉 local market.klines + Bybit get_klines 對齊 ts，算 close_match/range_ratio/corr@0/'
    'corr@+1/turnover_nonzero/gap，drift 命中走既有耐久 alert sink 並留作 R4 recal 隊列。'
    'metric 欄全 nullable（樣本不足留 NULL 不偽造 0）。monitoring-only：無 order/intent/'
    'lease 欄；checker 只讀 market.klines 不寫。append-only。';

COMMENT ON COLUMN research.kline_calibration.range_ratio IS
    'mean(local.high-low) / mean(bybit.high-low)：tick-synth 退化 bar 的 range 僅 2-37% '
    'Bybit 真值 → 遠 < 1；PA 閾值 < 0.5 命中 drift。NULL = 對齊 bar < 1 無法算（fail-soft）。';

COMMENT ON COLUMN research.kline_calibration.corr_shift1 IS
    'corr(local close 回報, bybit close 回報) @ shift +1：tick-synth one-bar offset 的指紋'
    '（≈ 0.98）。非門檻（不觸 drift），落表供分析 R1 修復是否消除 offset（修好後應降至無關）。';

COMMIT;

-- ============================================================
-- §D Guard C 後驗（COMMIT 後獨立檢查；不在 transaction 內，純讀驗證）
--   - 表存在
--   - PK 存在（防誤 DROP）
--   - 關鍵 hot-path index 到位（rotation + drift）
-- 任一不符 → RAISE EXCEPTION（fail-loud）。
-- ============================================================
DO $$
DECLARE
    v_count    INTEGER;
    v_has_pk   BOOLEAN;
BEGIN
    -- 表存在
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables
    WHERE table_schema='research' AND table_name='kline_calibration';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'V141 Guard C FAIL: research.kline_calibration 不存在.';
    END IF;

    -- PK 存在
    SELECT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema='research' AND table_name='kline_calibration'
          AND constraint_type='PRIMARY KEY'
    ) INTO v_has_pk;
    IF NOT v_has_pk THEN
        RAISE EXCEPTION 'V141 Guard C FAIL: research.kline_calibration 缺 PRIMARY KEY.';
    END IF;

    -- 關鍵 hot-path index 到位
    SELECT COUNT(*) INTO v_count
    FROM pg_indexes
    WHERE schemaname='research'
      AND indexname IN ('idx_kline_calibration_rotation', 'idx_kline_calibration_drift');
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'V141 Guard C FAIL: 關鍵 hot-path index 預期 2，實得 %.', v_count;
    END IF;

    RAISE NOTICE 'V141: all guards PASS —';
    RAISE NOTICE '  - research.kline_calibration 普通表（append-only monitoring 帳本）';
    RAISE NOTICE '  - PK (run_id,symbol,timeframe,window_start,window_end)；hot-path index ×2 到位';
    RAISE NOTICE '';
    RAISE NOTICE 'Next（本 migration 範圍外）:';
    RAISE NOTICE '  - kline_calibration_checker bin + cron wrapper + healthcheck [91]';
    RAISE NOTICE '  - R4 recal runbook（decompress -> overwrite -> truth-test gate -> recompress）';
END $$;

-- ============================================================
-- §E ROLLBACK（手動執行；非 sqlx down migration — 本專案 sqlx forward-only）
--   1. DROP 新 research.kline_calibration 用 RESTRICT（非 CASCADE）——若有依賴物件
--      DROP 會 fail-loud，避免靜默連鎖刪除。
--   2. 純監測帳本（無不可重捕資料）：rollback 即 DROP（校準判定可由下次 cron 重算）。
--   3. 不刪 market.klines（checker 對 klines 純唯讀，rollback 不碰主 klines）。
--   4. sqlx checksum drift → 用既有 repair_migration_checksum 工作流（不手改 _sqlx_migrations）。
--
-- 完整 teardown:
--   DROP TABLE IF EXISTS research.kline_calibration RESTRICT;
--   -- research schema 由 V125 共用，rollback 不 DROP SCHEMA。
-- ============================================================
