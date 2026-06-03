-- ============================================================
-- V130: research.listing_capture_events — production listing capture-only collector
--       逐筆 listing 微觀結構儲存層（COLLECTOR-LISTING-CAPTURE-PROD）
--
--   listing-fade alpha 研究的 promotion-grade 證據儲存層：production standalone
--   collector（helper_scripts/collectors/listing_capture/）前向累積新上市 perp 的
--   上市瞬間逐筆 publicTrade + phase transition + capture_lag + 1m kline 摘要。
--   listing 的上市瞬間不可 retro-backfill（provenance 不純），故此表為前向 seed
--   累積資產（n≥30 有效 listing 估 ~Q4 2026），**不設 retention drop policy**（OQ-4）。
--
-- 動機 / Motivation:
--   既有 market.klines 從 2026-04-05 起，但過去 52 新上市的上市瞬間沒存。Gate-A
--   88.1% PROCEED + 逆選擇 +6.6bps（QC 2026-05-31）支持 listing-fade 研究，但缺
--   逐筆首成交資料。collector 雙寫：(a) market.klines（既有表，additive，ON CONFLICT
--   DO NOTHING）讓 listing 1m bar 進主 klines 表；(b) 本新表逐筆 publicTrade（klines
--   表沒有逐筆）+ phase transition + capture_lag，帶完整 leak-free provenance。
--
--   ⚠️ 本 migration 僅建 schema 表 + Timescale hypertable + index + Guard。
--   collector daemon / pg_sink writer / WS 捕捉 / systemd 全不在本 migration 範圍。
--
-- SOURCE: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--production_listing_capture_collector_design.md
--   §3.2 schema + PM OQ-3 裁定（dedup 鍵含 Bybit trade_id `i`）+ OQ-4（不設 retention）
--
-- 範圍 / Scope (V130):
--   §A CREATE SCHEMA IF NOT EXISTS research（idempotent；V125 已建，此處冪等保險）
--   §B research.listing_capture_events CREATE TABLE IF NOT EXISTS + Guard A
--   §C 轉 hypertable（time col event_ts_exchange，7d chunk）+ compression（30d，
--       segmentby=symbol）— **無 retention policy**（OQ-4：listing 研究核心資產不清）
--   §D Guard B type 反射 + Guard C 後驗（hypertable / segmentby / index / 無 retention）
--
-- 設計決策（折入 PM OQ 裁定 + V125 範式）:
--   【OQ-3 dedup PK 含 trade_id + TimescaleDB hypertable 約束】
--     (本 migration 最 load-bearing 的 dedup 契約)
--     PK = (symbol, event_kind, event_ts_exchange, price, trade_id)
--     為什麼含 trade_id：listing pump 同價同毫秒可能多筆成交（高頻 taker 連續吃單）；
--     僅 (symbol,kind,event_ts,price) 會把這些誤併為一筆（資料損失）。Bybit
--     publicTrade 每筆帶 `i`（trade ID，全 symbol 唯一），進 PK 防誤併。
--     非 public_trade 事件（phase_transition / capture_lag / kline_1m）無 trade_id：
--     用 '' 空字串佔位（NOT NULL DEFAULT ''），這些事件 kind 對同一 (symbol,kind,
--     event_ts,price) 本就唯一（phase transition 每 symbol 每時刻一筆）。
--     【Linux PG dry-run 抓到的硬約束】PK 必含 hypertable 分區欄 event_ts_exchange
--     （TimescaleDB「cannot create a unique index without the column used in
--     partitioning」）。故 PK 用 timestamptz event_ts_exchange（分區欄）本體，非
--     BIGINT 鏡像 event_ts_exchange_ms。event_ts_exchange_ms 保留為一般欄（resume
--     query GROUP BY + clock-skew 診斷用；與 event_ts_exchange 同一時刻）。同 V125
--     history 表 PK 含 timestamptz time col（funding_ts/ts）範式。
--
--   【event_ts_exchange 為 hypertable time col + 排序鍵】
--     leak-free provenance：研究只能用交易所事件時刻排序（point-in-time，無
--     look-ahead）；ingest_ts_local_ms / ingest_minus_event_ms 僅供 clock-skew 診斷。
--     hypertable 分區用 event_ts_exchange（TIMESTAMPTZ）→ chunk/compression 用
--     INTERVAL（非 BIGINT-ms）。
--
--   【無 retention policy】(OQ-4，與 V125 的 1095d 不同)
--     listing 上市瞬間不可重捕，是研究核心資產；n≥30 累積要 ~Q4 2026，任何 drop
--     policy 都可能毀尚未分析的資料。故本 hypertable **不加 retention**（Guard C
--     反向斷言 0 個 retention job，防後續誤加）。資料量級可控（單次 listing pump
--     數萬筆 × ~6-10/月，遠小於 market.klines 1.44M rows）。
--
--   【冪等 double-apply 全 no-op】(per CLAUDE §Data「applying twice」+ memory
--     feedback_v_migration_pg_dry_run：first-apply PASS ≠ re-apply 安全)
--     - CREATE SCHEMA / TABLE IF [NOT] EXISTS         → 第二次 no-op（Guard A 已驗 shape）
--     - create_hypertable(... if_not_exists => TRUE)  → 第二次 no-op
--     - ALTER TABLE ... SET (timescaledb.compress)    → 包 NOT EXISTS guard，已啟用則 skip
--     - CREATE INDEX IF NOT EXISTS                    → 第二次 no-op（Guard C 已驗 shape）
--     - COMMENT ON                                    → 可重跑
--
--   【compressed-twin column-level op nested EXCEPTION】(per V114/V125 教訓)
--     本表無 column-level GRANT，主要 twin 風險來自 compression enable / segmentby
--     在 re-apply 時的傳播。compression enable 整段包 nested BEGIN/EXCEPTION 吞
--     duplicate_object / undefined_column，first-run 落定後 re-apply skip 不破冪等
--     （抄 V125:596-608 nested EXCEPTION 範式）。
--
-- Timescale 政策:
--   | chunk interval | 7 days        |
--   | compression    | after 30 days（segmentby=symbol）|
--   | retention      | 無（OQ-4 不設 drop）|
--
-- Idempotency 重跑兩次必 PASS（per memory feedback_v_migration_pg_dry_run
--   double-apply mandatory）。本 migration 須 Linux PG empirical 雙跑 dry-run 才能
--   sign-off（Mac mock PG 抓不到 Timescale runtime semantic）。
--
-- Guard（fail-closed + idempotent）:
--   Timescale preguard — extension 必存，否則 RAISE（不靜默 skip hypertable 政策）
--   Guard A — CREATE TABLE IF NOT EXISTS 前驗既有表必要欄完整（缺 → RAISE）
--   Guard B — type 敏感欄位反射（time col / price / size / provenance / trade_id）
--   Guard C — 建後驗 hypertable + segmentby=symbol + load-bearing index + 無 retention
--
-- E2 review checklist:
--   1. Guard A 對必要欄完整性（重跑 shape drift → RAISE）
--   2. OQ-3：PK 含 trade_id（symbol, event_kind, event_ts_exchange, price, trade_id）
--      — PK 用 timestamptz event_ts_exchange（hypertable 分區欄必入 PK）
--   3. compress_segmentby = 'symbol'（低基數，不含高基數欄）
--   4. 冪等：compression enable 包 NOT EXISTS guard + nested EXCEPTION
--   5. OQ-4：Guard C 反向斷言 0 retention job（listing 資產不清）
--   6. event_ts_exchange 為 hypertable time col + chunk 7d
--   7. rollback：DROP RESTRICT（非 CASCADE）；有 row → 標 inactive 概念不適用（純資料表，
--      無 run ledger），rollback 即 DROP（僅當確認無生產捕捉資料）
--
-- 硬邊界:
--   - 不碰 market.klines row shape（collector 對 klines 走 additive ON CONFLICT DO
--     NOTHING，不 ALTER）。
--   - 不改 max_retries / live_execution_allowed / execution_authority / system_mode（無關）。
--   - capture-only：本表只存 public market 捕捉資料，無 order / intent / lease 欄。
--   - append-only 語義：前向累積；rollback 不靜默刪生產捕捉資料。
--
-- migration latest: V127 → V130（V127 aeg_regime_labels 已 applied；V130 避撞）。
-- ============================================================

BEGIN;

-- ============================================================
-- Timescale preguard: TimescaleDB extension 必存
-- 為什麼 fail-closed（不靜默 skip）：本 migration 核心交付 = hypertable + compression。
--   若 extension 缺，靜默 skip 會留下「表建了但無 chunk rotate」的假完成狀態，違反
--   fail-loud 原則。trade-core 生產 PG 已裝 TimescaleDB 2.26.1，缺失 = 環境異常。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE EXCEPTION
            'V130 Timescale preguard FAIL: TimescaleDB extension missing. '
            '本 migration 需 hypertable + compression，不可在無 Timescale 環境靜默 '
            'skip。請於有 TimescaleDB 的 PG 上 apply。';
    END IF;
END $$;

-- ============================================================
-- §A CREATE SCHEMA IF NOT EXISTS research（idempotent）
-- research namespace 已由 V125 建立；此處冪等保險（若 V130 在 V125 前單獨 apply）。
-- 第二次 apply no-op。
-- ============================================================
CREATE SCHEMA IF NOT EXISTS research;

-- ============================================================
-- §B research.listing_capture_events — 逐筆 listing 捕捉事件（hypertable）
-- 每筆 publicTrade / phase_transition / capture_lag / kline_1m 一列。
-- PK 含 trade_id（OQ-3）防 listing pump 同價同毫秒誤併。
-- ============================================================

-- Guard A: listing_capture_events 既有表必要欄完整性（缺 ≥1 → RAISE）
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'listing_capture_events'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'event_ts_exchange', 'symbol', 'event_kind', 'trade_id',
            'launch_time_ms', 'price', 'side', 'size',
            'prev_status', 'new_status', 'cur_auction_phase',
            'capture_lag_ms', 'capture_verdict',
            'kline_open', 'kline_high', 'kline_low', 'kline_close',
            'kline_volume', 'kline_turnover', 'kline_confirm',
            'ingest_ts_local_ms', 'event_ts_exchange_ms', 'ingest_minus_event_ms',
            'collector_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'listing_capture_events'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V130 Guard A FAIL: research.listing_capture_events exists but missing '
                'required columns: %. 解決 legacy schema drift（DROP + re-apply 或 ALTER ADD）'
                '後重跑 V130。', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.listing_capture_events (
    -- 交易所事件時刻（leak-free 排序鍵 + hypertable time col）
    event_ts_exchange    TIMESTAMPTZ NOT NULL,
    symbol               TEXT        NOT NULL,
    -- event_kind enum：限小詞表（4 類捕捉事件）
    event_kind           TEXT        NOT NULL
                                     CHECK (event_kind IN (
                                         'public_trade', 'phase_transition',
                                         'capture_lag', 'kline_1m'
                                     )),
    -- OQ-3：Bybit publicTrade trade_id `i`（public_trade 事件用；其餘事件用 '' 佔位）。
    -- 進 PK 防 listing pump 同價同毫秒多筆誤併。NOT NULL DEFAULT '' 使非 trade 事件
    -- 仍可入 PK（同 (symbol,kind,event_ts_ms,price) 對 phase/lag/kline 本就唯一）。
    trade_id             TEXT        NOT NULL DEFAULT '',
    launch_time_ms       BIGINT,                          -- 該 symbol 鎖定的 launchTime

    -- ── public_trade 欄 ──
    price                DOUBLE PRECISION,
    side                 TEXT,                            -- 'Buy' | 'Sell'
    size                 DOUBLE PRECISION,

    -- ── phase_transition 欄 ──
    prev_status          TEXT,                            -- e.g. 'PreLaunch'
    new_status           TEXT,                            -- e.g. 'Trading'
    cur_auction_phase    TEXT,                            -- Bybit curAuctionPhase（相位時間線）

    -- ── capture_lag 欄 ──
    capture_lag_ms       BIGINT,                          -- first publicTrade event_ts − launchTime
    capture_verdict      TEXT,                            -- PASS_CAPTURE | SLOW_CAPTURE | NO_LAUNCH_TIME

    -- ── kline_1m 欄（confirm bar 摘要；逐筆主資料在 public_trade）──
    kline_open           DOUBLE PRECISION,
    kline_high           DOUBLE PRECISION,
    kline_low            DOUBLE PRECISION,
    kline_close          DOUBLE PRECISION,
    kline_volume         DOUBLE PRECISION,
    kline_turnover       DOUBLE PRECISION,
    kline_confirm        BOOLEAN,                         -- 該 bar 是否已 confirm

    -- ── leak-free provenance（每 row 必帶）──
    ingest_ts_local_ms   BIGINT      NOT NULL,            -- 本地 ingest 時刻（僅診斷）
    event_ts_exchange_ms BIGINT      NOT NULL,            -- 交易所事件時刻（毫秒鏡像）
    ingest_minus_event_ms BIGINT     NOT NULL,            -- clock-skew / 延遲診斷
    collector_version    TEXT        NOT NULL,            -- collector COLLECTOR_VERSION

    -- OQ-3 dedup：同 symbol 同 kind 同 exchange-event-ts 同 price 同 trade_id = 同事件。
    -- PK 用 timestamptz event_ts_exchange（hypertable 分區欄必入 PK，Linux PG dry-run
    -- 抓到的 TimescaleDB 約束）；event_ts_exchange_ms 為同一時刻的 BIGINT 鏡像（resume
    -- query / 診斷用，非 PK 成員）。
    PRIMARY KEY (symbol, event_kind, event_ts_exchange, price, trade_id)
);

-- ============================================================
-- Guard B: type 敏感欄位反射
-- 為什麼：writer（pg_sink）寫入靠 type 對齊；type drift = silent write fail / 精度損失。
--   驗 time col (timestamptz) / numeric (double precision) / trade_id+provenance (text/bigint)。
--   column 不存在 v_actual=NULL → skip（CREATE TABLE 已負責建）。
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- event_ts_exchange 必 timestamptz（hypertable time col 契約）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='listing_capture_events' AND column_name='event_ts_exchange';
    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'V130 Guard B FAIL: listing_capture_events.event_ts_exchange is %, expected timestamptz.', v_actual;
    END IF;

    -- trade_id 必 text（PK 型別契約，OQ-3）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='listing_capture_events' AND column_name='trade_id';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION 'V130 Guard B FAIL: listing_capture_events.trade_id is %, expected text.', v_actual;
    END IF;

    -- price 必 double precision（PK 成員 + 逐筆價）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='listing_capture_events' AND column_name='price';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION 'V130 Guard B FAIL: listing_capture_events.price is %, expected double precision.', v_actual;
    END IF;

    -- event_ts_exchange_ms 必 bigint（毫秒鏡像 + PK 成員）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='listing_capture_events' AND column_name='event_ts_exchange_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION 'V130 Guard B FAIL: listing_capture_events.event_ts_exchange_ms is %, expected bigint.', v_actual;
    END IF;

    -- kline_confirm 必 boolean
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='listing_capture_events' AND column_name='kline_confirm';
    IF v_actual IS NOT NULL AND v_actual <> 'boolean' THEN
        RAISE EXCEPTION 'V130 Guard B FAIL: listing_capture_events.kline_confirm is %, expected boolean.', v_actual;
    END IF;
END $$;

-- ============================================================
-- §C 轉 hypertable + compression（無 retention，OQ-4）
-- chunk 7d / compression 30d segmentby=symbol。time col event_ts_exchange（TIMESTAMPTZ）
-- → 用 INTERVAL（非 BIGINT-ms）。
--
-- 【冪等 + compressed-twin nested EXCEPTION】compression enable 包 NOT EXISTS guard
--   （已啟用 → skip ALTER）+ nested BEGIN/EXCEPTION（吞 re-apply 時 twin 傳播相關
--   duplicate_object / undefined_column；抄 V125:596-608 範式）。
-- ⚠️ 不加 retention policy（OQ-4：listing 研究核心資產，n≥30 累積要 ~Q4，不可 drop）。
-- ============================================================
SELECT create_hypertable(
    'research.listing_capture_events',
    'event_ts_exchange',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='listing_capture_events'
    ) THEN
        BEGIN
            ALTER TABLE research.listing_capture_events SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby   = 'event_ts_exchange DESC'
            );
            RAISE NOTICE 'V130: compression enabled on listing_capture_events (segmentby=symbol)';
        EXCEPTION
            WHEN duplicate_object OR undefined_column THEN
                -- re-apply 場景：compressed twin 已存在；compression 設定已落，skip 不破冪等
                RAISE NOTICE 'V130: compression ALTER skipped on listing_capture_events '
                             '(already enabled / twin exists; idempotent)';
        END;
    ELSE
        RAISE NOTICE 'V130: compression already enabled on listing_capture_events; skipping ALTER';
    END IF;
END $$;

SELECT add_compression_policy('research.listing_capture_events', INTERVAL '30 days', if_not_exists => TRUE);
-- ⚠️ 故意 NOT add_retention_policy（OQ-4）。

-- ============================================================
-- §C-index Hot-path indexes
-- 1. (symbol, event_ts_exchange DESC) — per-symbol 時序查詢（listing-fade 微觀結構研究）
-- 2. (event_kind, event_ts_exchange DESC) — 按事件類型篩（如只看 phase_transition）
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_listing_capture_symbol_ts
    ON research.listing_capture_events (symbol, event_ts_exchange DESC);
CREATE INDEX IF NOT EXISTS idx_listing_capture_kind_ts
    ON research.listing_capture_events (event_kind, event_ts_exchange DESC);

-- ============================================================
-- §COMMENT 語義文檔（idempotent: COMMENT ON 可重跑）
-- ============================================================
COMMENT ON TABLE research.listing_capture_events IS
    'production listing capture-only collector 逐筆證據表（V130；'
    'COLLECTOR-LISTING-CAPTURE-PROD）。time col event_ts_exchange，7d chunk / 30d '
    'compress segmentby=symbol / **無 retention**（OQ-4 listing 研究核心資產不清）。'
    'PK (symbol,event_kind,event_ts_exchange,price,trade_id) 含 Bybit trade_id `i`'
    '（OQ-3 防 listing pump 同價同毫秒誤併；PK 用 timestamptz event_ts_exchange 因'
    'hypertable 分區欄必入 PK）。event_kind: public_trade/phase_transition/'
    'capture_lag/kline_1m。capture-only：無 order/intent/lease 欄。';

COMMENT ON COLUMN research.listing_capture_events.trade_id IS
    'OQ-3 dedup PK 成員：Bybit publicTrade `i`（trade ID）。public_trade 事件帶真值；'
    'phase_transition/capture_lag/kline_1m 用 '''' 佔位（這些事件對同 (symbol,kind,'
    'event_ts_exchange,price) 本就唯一）。為什麼進 PK：listing pump 同價同毫秒可能多筆'
    '成交，不含 trade_id 會誤併損失逐筆資料。';

COMMENT ON COLUMN research.listing_capture_events.event_ts_exchange IS
    'leak-free 排序鍵 + hypertable time col：研究只能用交易所事件時刻排序（PIT 無 '
    'look-ahead）。ingest_ts_local_ms / ingest_minus_event_ms 僅供 clock-skew 診斷，'
    '不可用於排序或構造特徵。';

COMMIT;

-- ============================================================
-- §D Guard C 後驗（COMMIT 後獨立檢查；不在 transaction 內，純讀驗證）
--   - 表存在
--   - 確為 hypertable（chunk = 7d）on event_ts_exchange
--   - compress_segmentby = 'symbol'
--   - **無 retention job**（OQ-4 反向斷言：恰好 0 個 policy_retention job）
--   - 關鍵 hot-path index 到位
-- 任一不符 → RAISE EXCEPTION（fail-loud）。
-- ============================================================
DO $$
DECLARE
    v_count          INTEGER;
    v_chunk          BIGINT;
    v_comp_enabled   BOOLEAN;
    v_symbol_segby   BOOLEAN;
    v_retention_jobs INTEGER;
BEGIN
    -- 表存在
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables
    WHERE table_schema='research' AND table_name='listing_capture_events';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'V130 Guard C FAIL: research.listing_capture_events 不存在.';
    END IF;

    -- hypertable + chunk = 7d on event_ts_exchange
    SELECT EXTRACT(EPOCH FROM time_interval)::BIGINT INTO v_chunk
    FROM timescaledb_information.dimensions
    WHERE hypertable_schema='research' AND hypertable_name='listing_capture_events'
      AND column_name='event_ts_exchange';
    IF v_chunk IS NULL THEN
        RAISE EXCEPTION 'V130 Guard C FAIL: research.listing_capture_events 未建 hypertable on event_ts_exchange.';
    END IF;
    IF v_chunk <> 604800 THEN  -- 7 days in seconds
        RAISE EXCEPTION 'V130 Guard C FAIL: research.listing_capture_events chunk = % sec（預期 604800 = 7d）.', v_chunk;
    END IF;

    -- compress_segmentby = symbol（TimescaleDB 2.26.1：segmentby_column_index IS NOT NULL，
    -- 同 V125:847-863 範式）
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='listing_capture_events'
    ) INTO v_comp_enabled;
    IF NOT v_comp_enabled THEN
        RAISE EXCEPTION 'V130 Guard C FAIL: research.listing_capture_events compression 未啟用.';
    END IF;
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='listing_capture_events'
          AND attname='symbol' AND segmentby_column_index IS NOT NULL
    ) INTO v_symbol_segby;
    IF NOT v_symbol_segby THEN
        RAISE EXCEPTION
            'V130 Guard C FAIL: research.listing_capture_events compress_segmentby 不含 symbol（預期 symbol 為 segmentby 欄）.';
    END IF;

    -- OQ-4 反向斷言：無 retention job（listing 資產不清）
    SELECT COUNT(*) INTO v_retention_jobs
    FROM timescaledb_information.jobs
    WHERE proc_name='policy_retention'
      AND hypertable_schema='research' AND hypertable_name='listing_capture_events';
    IF v_retention_jobs <> 0 THEN
        RAISE EXCEPTION
            'V130 Guard C FAIL: research.listing_capture_events retention job 數 = %（OQ-4 預期 0；'
            'listing 研究核心資產不可設 drop policy）.', v_retention_jobs;
    END IF;

    -- 關鍵 hot-path index 到位
    SELECT COUNT(*) INTO v_count
    FROM pg_indexes
    WHERE schemaname='research'
      AND indexname IN ('idx_listing_capture_symbol_ts', 'idx_listing_capture_kind_ts');
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'V130 Guard C FAIL: 關鍵 hot-path index 預期 2，實得 %.', v_count;
    END IF;

    RAISE NOTICE 'V130: all guards PASS —';
    RAISE NOTICE '  - research.listing_capture_events hypertable（chunk=7d on event_ts_exchange）';
    RAISE NOTICE '  - compress=30d segmentby=symbol；**無 retention**（OQ-4 listing 資產不清）';
    RAISE NOTICE '  - PK 含 trade_id（OQ-3 dedup）；hot-path index ×2 到位';
    RAISE NOTICE '';
    RAISE NOTICE 'Next（本 migration 範圍外）:';
    RAISE NOTICE '  - collector daemon + pg_sink writer（helper_scripts/collectors/listing_capture/）';
    RAISE NOTICE '  - systemd unit + restart-resume + JSONL fallback（OQ-5）';
END $$;

-- ============================================================
-- §E ROLLBACK（手動執行；非 sqlx down migration — 本專案 sqlx forward-only）
--   1. DROP 新 research.listing_capture_events 用 RESTRICT（非 CASCADE）——若有依賴物件
--      DROP 會 fail-loud，避免靜默連鎖刪除。
--   2. listing 捕捉資料不可重捕（OQ-4 核心資產）：rollback 前須確認無生產捕捉資料，
--      否則 DROP 會永久毀資料。建議先 SELECT count(*) 確認為 0 或已備份。
--   3. 不刪 market.klines（collector 對 klines 走 additive，rollback 不碰主 klines）。
--   4. sqlx checksum drift → 用既有 repair_migration_checksum 工作流（不手改 _sqlx_migrations）。
--
-- 完整 teardown（僅當確認無生產捕捉資料；DROP RESTRICT 防連鎖）:
--   DROP TABLE IF EXISTS research.listing_capture_events RESTRICT;
--   -- research schema 由 V125 共用，rollback 不 DROP SCHEMA。
-- ============================================================
