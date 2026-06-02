-- ============================================================
-- V125: research.alpha_* — AEG (Alpha-Edge Generator) S1 歷史儲存層 / FND-1 approved branch
--
--   AEG-S1 歷史採集（funding / open_interest / long_short_ratio / OHLCV provenance）
--   的 promotion-grade 證據儲存層。建立獨立 research schema，與 market.* (live writer
--   truth) / panel.* (短期衍生 panel) / learning.* (模型訓練 state) 邊界明確分離。
--
-- 動機 / Motivation:
--   FND-1 批准 1095d 歷史研究證據 branch（當前 Alpha-Edge 證據窗 = 18 個月）。
--   AEG-S1 需把已驗 Bybit 歷史 endpoint（funding/OI/LS/OHLCV）落 PG，供 alpha
--   scoring / promotion replay 重建。每筆歷史證據必可回溯到一次 accepted run +
--   artifact digest（manifest_sha256 / payload_sha256），不可被後續 run 靜默覆蓋。
--
--   ⚠️ 本 migration 僅建 schema + 表 + Timescale 政策 + klines retention 延長。
--   endpoint client / historical writer / backfill / collector / alpha scoring
--   全不在本 migration 範圍（per design packet §9 Explicit Exclusions）。
--
-- SOURCE: docs/execution_plan/2026-06-01--aeg_s1_mit_storage_migration_design_packet.md
--   §2 schema 決策 / §3 run+page ledger / §4 OHLCV provenance（不改 klines row shape）
--   / §5 dedicated history 表 + identity / §6 Timescale 政策 / §7 Guard / §8 rollback
--
-- 範圍 / Scope (V125):
--   §A CREATE SCHEMA IF NOT EXISTS research (idempotent)
--   §B 6 表 CREATE TABLE IF NOT EXISTS + Guard A（既有表缺欄 → RAISE）：
--       1. research.alpha_history_ingest_runs   — 每次 accepted 採集 run 一列（run ledger）
--       2. research.alpha_history_ingest_pages  — endpoint/page 級 provenance + coverage
--       3. research.alpha_klines_provenance     — OHLCV 寫入 market.klines 的 append-only 來源帳
--       4. research.alpha_funding_rates_history — funding 歷史（hypertable on funding_ts）
--       5. research.alpha_open_interest_history — OI 歷史（hypertable on ts）
--       6. research.alpha_long_short_ratio_history — 多空比歷史（hypertable on ts）
--   §C 3 history 表轉 hypertable（time col per packet §5，7d chunk）
--       + compression（30d，segmentby=symbol）+ retention（1095d）
--   §D market.klines retention 365d → 1095d 替換（remove+add，抄 V075 範式）
--       — 保留既有 14d compression policy 不動（per packet §7）
--   §E Guard C 後驗 + retention job 唯一性斷言
--
-- 設計決策（折入 E2/E4/MIT 三方 review must-fix）:
--   【C-3 per-row data column NOT NULL】(本 migration 最重要 fail-closed 契約)
--     - alpha_funding_rates_history.funding_rate          NOT NULL
--     - alpha_open_interest_history.open_interest         NOT NULL
--     - alpha_long_short_ratio_history.buy_ratio          NOT NULL
--     - alpha_long_short_ratio_history.sell_ratio         NOT NULL
--     為什麼 fail-closed：既有 Bybit parser 對缺值 default 0.0；若 schema 容許 NULL/0.0
--     入庫，silent fake-zero 會污染 PIT (point-in-time) alpha 證據 → promotion replay
--     誤判（0.0 funding 看似存在實為缺值）。schema 用 NOT NULL 強制「該 row 必有有效
--     資料值」契約底線；writer 端 parse-fail 必 reject（不寫 0.0 row、不寫 NULL row），
--     由 backfill writer 負責（本 migration 範圍外）。對齊 V115 basis_pct NOT NULL 範式。
--
--   【C-5 compress_segmentby = symbol 低基數】
--     3 history 表 compression segmentby 全用 'symbol'（低基數，~25-143 sym）。
--     為什麼不含 run_id：run_id 是高基數（每次 run 一新值，無上界），含進 segmentby
--     會讓 compressed chunk 按 (symbol, run_id) 過度切割 → 壓縮碎片化 + 壓縮率崩潰。
--     run_id 留在 orderby（與時間一起排序）即可保 query locality，不入 segmentby。
--
--   【冪等 double-apply 全 no-op】(per CLAUDE §Data「applying twice」+ memory
--     feedback_v_migration_pg_dry_run：first-apply PASS ≠ re-apply 安全)
--     - CREATE SCHEMA / TABLE IF [NOT] EXISTS         → 第二次 no-op（Guard A 已驗 shape）
--     - create_hypertable(... if_not_exists => TRUE)  → 第二次 no-op
--     - ALTER TABLE ... SET (timescaledb.compress)    → 包 NOT EXISTS guard，已啟用則 skip
--     - add_compression_policy / add_retention_policy → if_not_exists => TRUE（重複會 RAISE，
--       這是最易踩處；klines retention 用 remove+add 確定性替換）
--     - CREATE INDEX IF NOT EXISTS                    → 第二次 no-op（Guard C 已驗 shape）
--     - COMMENT ON                                    → 可重跑
--
--   【compressed-twin column-level op nested EXCEPTION】(per packet §7 + V114 教訓)
--     本 migration 對 research history 表**無 column-level GRANT**（不像 V114），故主要
--     twin 風險來自 compression enable / segmentby 在 re-apply 時的傳播。compression
--     enable 整段包 nested BEGIN/EXCEPTION 吞 duplicate_object / undefined_column，
--     first-run 落定後 re-apply skip 不破冪等（抄 V114:249-257 nested EXCEPTION 範式）。
--
--   【schema 選擇 research.* 非 learning.*】(per packet §2)
--     research.* 使「promotion-grade 歷史證據」邊界顯式：非 live market writer truth
--     (market.*)、非短期衍生 panel (panel.*)、非模型訓練 state (learning.*)。
--
--   【run_id TEXT 非 UUID】(per packet §3)
--     AEG artifact 可能用 UUID / ULID / deterministic label；強制 UUID 會造成無謂 adapter
--     工作。TEXT PRIMARY KEY（非空），後續 migration 可加 generated UUID surrogate。
--
-- Timescale 政策（per packet §6，3 history 表統一）:
--   | chunk interval | 7 days   |
--   | compression    | after 30 days |
--   | retention      | 1095 days |
--   3 history time col 皆 TIMESTAMPTZ（funding_ts / ts / ts）→ chunk/compression/
--   retention 全用 INTERVAL（**非 BIGINT-ms**；BIGINT-ms 只用於 BIGINT time col 如 V115
--   panel.basis_panel.snapshot_ts_ms）。run/page/provenance 3 帳本表 = plain table
--   （非 time-series volume，無 hypertable / 無 retention，與 market.symbol_universe
--   _snapshots plain table 同類）。
--
-- market.klines retention 設計（per packet §7）:
--   - 保留 compress after 14 days（V006:31-32）不動。
--   - retention after 365 days（V006:66）→ replace 為 after 1095 days。
--   - klines time col = TIMESTAMPTZ ts（V002:122）→ retention 用 INTERVAL '1095 days'
--     （**非 BIGINT-ms**）。
--   - replace 後 assert 恰好一個 active retention job（drop_after = 1095 days）。
--   - rollback 還原 365 days。
--
-- Idempotency 重跑兩次必 PASS（per memory feedback_v_migration_pg_dry_run
--   double-apply mandatory）。本 migration 須 Linux PG empirical 雙跑 dry-run 才能 sign-off
--   （Mac mock PG 抓不到 Timescale runtime semantic）。
--
-- Guard（per packet §7，fail-closed + idempotent）:
--   Timescale preguard — extension 必存，否則 RAISE（不靜默 skip hypertable 政策）
--   Guard A — 每個 CREATE TABLE IF NOT EXISTS 前驗既有表必要欄完整（缺 → RAISE）
--   Guard B — type 敏感欄位反射（run_id / digest / timestamp / numeric / boolean）
--   Guard C — 建後驗 load-bearing index + Timescale 政策
--   Retention guard — 反射既有 klines retention，冪等替換，assert 恰好一個 1095d job
--
-- E2 review checklist:
--   1. Guard A 對 6 表必要欄完整性（重跑 shape drift → RAISE）
--   2. C-3：4 個 data column NOT NULL（funding_rate / open_interest / buy_ratio / sell_ratio）
--   3. C-5：3 history 表 compress_segmentby = 'symbol'（不含 run_id 高基數）
--   4. 冪等：compression enable 包 NOT EXISTS guard + nested EXCEPTION；policy 用 if_not_exists
--   5. klines retention：INTERVAL '1095 days'（非 BIGINT-ms）；remove+add；保留 14d compression
--   6. rollback：DROP RESTRICT（非 CASCADE）；有 accepted row → 標 inactive 不靜默刪；klines 還原 365d
--   7. 3 history hypertable time col 對齊 packet §5（funding_ts / ts / ts）+ chunk 7d
--
-- 硬邊界:
--   - 不碰 market.klines / market.funding_rates / market.open_interest /
--     market.long_short_ratio row shape（OHLCV provenance 走獨立 research.alpha_klines
--     _provenance 帳本，不 ALTER market.klines）。
--   - 不改 max_retries / live_execution_allowed / execution_authority / system_mode（無關）。
--   - append-only 語義：history / provenance 表設計為前向累積；rollback 不靜默刪 accepted row。
--
-- Mark/index/premium price klines 不在本 migration（FND-4 未批准其儲存選擇，packet §9）。
--
-- migration latest: V115 → V125（AEG 保留槽，per packet Verdict；V116-124 為 M5/M7/M12/M13
--   + funding_arb V3 + collector audit-ledger 預留，V125 避撞）。
-- ============================================================

BEGIN;

-- ============================================================
-- Timescale preguard: TimescaleDB extension 必存
-- 為什麼 fail-closed（不靜默 skip）：本 migration 核心交付 = 3 hypertable + compression
--   + retention + klines retention 延長。若 extension 缺，靜默 skip 會留下「表建了但
--   無 chunk rotate / 無 retention 自動化」的假完成狀態，違反 fail-loud 原則。
--   trade-core 生產 PG 已裝 TimescaleDB 2.26.1（packet §1 reflection），缺失 = 環境異常。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE EXCEPTION
            'V125 Timescale preguard FAIL: TimescaleDB extension missing. '
            '本 migration 需 hypertable + compression + retention，不可在無 Timescale '
            '環境靜默 skip。請於有 TimescaleDB 的 PG 上 apply。';
    END IF;
END $$;

-- ============================================================
-- §A CREATE SCHEMA IF NOT EXISTS research (idempotent)
-- research namespace = AEG promotion-grade 歷史證據邊界；與 market.* / panel.* /
-- learning.* 分離（per packet §2）。第二次 apply no-op。
-- ============================================================
CREATE SCHEMA IF NOT EXISTS research;

COMMENT ON SCHEMA research IS
    'AEG (Alpha-Edge Generator) promotion-grade 歷史證據 namespace（V125）。'
    '非 market.* live writer truth、非 panel.* 短期衍生、非 learning.* 模型 state。'
    'alpha_history_ingest_runs/pages = run+page 帳本；alpha_klines_provenance = '
    'OHLCV 寫入 market.klines 的來源帳；alpha_*_history = funding/OI/LS 歷史 hypertable。';

-- ============================================================
-- §B.1 research.alpha_history_ingest_runs — run ledger（plain table）
-- 每次 accepted AEG 歷史採集 run 一列。run_id TEXT PK（接受 UUID/ULID/label）。
-- per packet §3。plain table（非 time-series volume，無 hypertable）。
-- ============================================================

-- Guard A: alpha_history_ingest_runs 既有表必要欄完整性（缺 ≥1 → RAISE）
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'alpha_history_ingest_runs'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id', 'program', 'storage_branch', 'window_start', 'window_end',
            'artifact_root', 'manifest_sha256', 'git_sha', 'git_dirty',
            'status', 'created_at', 'completed_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'alpha_history_ingest_runs'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V125 Guard A FAIL: research.alpha_history_ingest_runs exists but missing '
                'required columns: %. 解決 legacy schema drift（DROP + re-apply 或 ALTER ADD）'
                '後重跑 V125。', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.alpha_history_ingest_runs (
    -- run_id：TEXT PK（接受 UUID/ULID/artifact label；非空）。per packet §3 決策。
    run_id           TEXT         NOT NULL,
    program          TEXT         NOT NULL,                     -- e.g. 'aeg_s1'
    storage_branch   TEXT,                                      -- e.g. 'fnd1_approved_klines_1095d_research_history'
    window_start     TIMESTAMPTZ,                               -- 分析採集窗起
    window_end       TIMESTAMPTZ,                               -- 分析採集窗止
    artifact_root    TEXT,                                      -- artifact 目錄（若有）
    manifest_sha256  TEXT,                                      -- manifest.json digest（小寫 hex）
    git_sha          TEXT,                                      -- source checkout
    git_dirty        BOOLEAN,                                   -- source dirty flag
    -- status：run 生命週期 enum；CHECK 限小詞表（per packet §3）
    status           TEXT         NOT NULL DEFAULT 'planned'
                                  CHECK (status IN (
                                      'planned', 'running', 'accepted',
                                      'failed', 'superseded', 'inactive'
                                  )),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ,
    PRIMARY KEY (run_id)
);

-- ============================================================
-- §B.2 research.alpha_history_ingest_pages — endpoint/page 級 provenance（plain table）
-- key (run_id, page_id)；page_id deterministic（endpoint+symbol+interval+window+cursor+seq）。
-- per packet §3。coverage_status 限小詞表。
-- ============================================================

-- Guard A: alpha_history_ingest_pages 既有表必要欄完整性
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'alpha_history_ingest_pages'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id', 'page_id', 'endpoint_id', 'category', 'symbol',
            'timeframe_or_period', 'request_start', 'request_end',
            'cursor_in', 'cursor_out', 'ret_code', 'ret_msg', 'http_status',
            'payload_sha256', 'artifact_sha256', 'expected_rows', 'observed_rows',
            'coverage_pct', 'coverage_status', 'fetched_at', 'parser_version', 'error'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'alpha_history_ingest_pages'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V125 Guard A FAIL: research.alpha_history_ingest_pages exists but missing '
                'required columns: %. 解決 legacy schema drift 後重跑 V125.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.alpha_history_ingest_pages (
    run_id              TEXT         NOT NULL,
    page_id             TEXT         NOT NULL,                  -- deterministic page key
    endpoint_id         TEXT,
    category            TEXT,                                   -- bybit category (linear/inverse/spot)
    symbol              TEXT,
    timeframe_or_period TEXT,                                   -- kline interval 或 OI/LS period
    request_start       TIMESTAMPTZ,
    request_end         TIMESTAMPTZ,
    cursor_in           TEXT,
    cursor_out          TEXT,
    ret_code            INTEGER,                                -- bybit retCode
    ret_msg             TEXT,
    http_status         INTEGER,
    payload_sha256      TEXT,                                   -- 原始 payload digest
    artifact_sha256     TEXT,                                   -- artifact 落盤 digest
    expected_rows       BIGINT,
    observed_rows       BIGINT,
    coverage_pct        DOUBLE PRECISION,
    -- coverage_status：限小詞表（per packet §3）
    coverage_status     TEXT
                        CHECK (coverage_status IS NULL OR coverage_status IN (
                            'pass', 'partial', 'failed', 'skipped', 'not_applicable'
                        )),
    fetched_at          TIMESTAMPTZ,
    parser_version      TEXT,
    error               TEXT,
    PRIMARY KEY (run_id, page_id)
);

-- ============================================================
-- §B.3 research.alpha_klines_provenance — OHLCV 來源帳（plain table，append-only）
-- per packet §4：不 ALTER market.klines row shape；用獨立帳本記 OHLCV 寫入來源。
-- identity = (run_id, endpoint_id, category, symbol, timeframe, window_start, window_end)。
-- ============================================================

-- Guard A: alpha_klines_provenance 既有表必要欄完整性
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'alpha_klines_provenance'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id', 'endpoint_id', 'category', 'symbol', 'timeframe',
            'window_start', 'window_end', 'storage_surface',
            'request_start', 'request_end', 'parser_version', 'git_sha', 'git_dirty',
            'payload_sha256', 'artifact_sha256', 'expected_rows', 'observed_rows',
            'coverage_pct', 'coverage_status', 'created_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'alpha_klines_provenance'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V125 Guard A FAIL: research.alpha_klines_provenance exists but missing '
                'required columns: %. 解決 legacy schema drift 後重跑 V125.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.alpha_klines_provenance (
    run_id           TEXT         NOT NULL,
    endpoint_id      TEXT         NOT NULL,
    category         TEXT         NOT NULL,
    symbol           TEXT         NOT NULL,
    timeframe        TEXT         NOT NULL,
    window_start     TIMESTAMPTZ  NOT NULL,
    window_end       TIMESTAMPTZ  NOT NULL,
    -- storage_surface：寫入目標表（固定 'market.klines'，per packet §4）
    storage_surface  TEXT         NOT NULL DEFAULT 'market.klines',
    request_start    TIMESTAMPTZ,
    request_end      TIMESTAMPTZ,
    parser_version   TEXT,
    git_sha          TEXT,
    git_dirty        BOOLEAN,
    payload_sha256   TEXT,
    artifact_sha256  TEXT,
    expected_rows    BIGINT,
    observed_rows    BIGINT,
    coverage_pct     DOUBLE PRECISION,
    coverage_status  TEXT
                     CHECK (coverage_status IS NULL OR coverage_status IN (
                         'pass', 'partial', 'failed', 'skipped', 'not_applicable'
                     )),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, endpoint_id, category, symbol, timeframe, window_start, window_end)
);

-- ============================================================
-- §B.4 research.alpha_funding_rates_history — funding 歷史（hypertable on funding_ts）
-- per packet §5。identity = (category, symbol, funding_ts, run_id)；run_id 入 PK 保 lineage
-- （重複 run 保留各自證據，不靜默覆蓋）。
-- 【C-3】funding_rate NOT NULL：parser 缺值 default 0.0 會 silent fake-zero 污染 PIT。
-- ============================================================

-- Guard A: alpha_funding_rates_history 既有表必要欄完整性
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'alpha_funding_rates_history'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id', 'category', 'symbol', 'funding_ts', 'funding_rate',
            'funding_interval_minutes', 'source_endpoint', 'request_start',
            'request_end', 'fetched_at', 'parser_version', 'payload_sha256',
            'artifact_sha256'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'alpha_funding_rates_history'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V125 Guard A FAIL: research.alpha_funding_rates_history exists but missing '
                'required columns: %. 解決 legacy schema drift 後重跑 V125.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.alpha_funding_rates_history (
    run_id                   TEXT         NOT NULL,
    category                 TEXT         NOT NULL,
    symbol                   TEXT         NOT NULL,
    funding_ts               TIMESTAMPTZ  NOT NULL,             -- hypertable time col
    -- 【C-3】NOT NULL fail-closed：parser parse-fail 必 reject（不寫 0.0/NULL row）
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
);

-- ============================================================
-- §B.5 research.alpha_open_interest_history — OI 歷史（hypertable on ts）
-- per packet §5。identity = (category, symbol, interval_time, ts, run_id)。
-- 【C-3】open_interest NOT NULL。
-- ============================================================

-- Guard A: alpha_open_interest_history 既有表必要欄完整性
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'alpha_open_interest_history'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id', 'category', 'symbol', 'interval_time', 'ts', 'open_interest',
            'source_endpoint', 'request_start', 'request_end', 'cursor_lineage',
            'fetched_at', 'parser_version', 'payload_sha256', 'artifact_sha256'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'alpha_open_interest_history'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V125 Guard A FAIL: research.alpha_open_interest_history exists but missing '
                'required columns: %. 解決 legacy schema drift 後重跑 V125.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.alpha_open_interest_history (
    run_id           TEXT         NOT NULL,
    category         TEXT         NOT NULL,
    symbol           TEXT         NOT NULL,
    interval_time    TEXT         NOT NULL,                     -- bybit OI intervalTime (5min/1h/...)
    ts               TIMESTAMPTZ  NOT NULL,                     -- hypertable time col
    -- 【C-3】NOT NULL fail-closed
    open_interest    DOUBLE PRECISION NOT NULL,
    source_endpoint  TEXT,
    request_start    TIMESTAMPTZ,
    request_end      TIMESTAMPTZ,
    cursor_lineage   TEXT,
    fetched_at       TIMESTAMPTZ,
    parser_version   TEXT,
    payload_sha256   TEXT,
    artifact_sha256  TEXT,
    PRIMARY KEY (category, symbol, interval_time, ts, run_id)
);

-- ============================================================
-- §B.6 research.alpha_long_short_ratio_history — 多空比歷史（hypertable on ts）
-- per packet §5。identity = (category, symbol, period, ts, run_id)。
-- 【C-3】buy_ratio + sell_ratio 雙 NOT NULL。
-- ============================================================

-- Guard A: alpha_long_short_ratio_history 既有表必要欄完整性
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'alpha_long_short_ratio_history'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'run_id', 'category', 'symbol', 'period', 'ts', 'buy_ratio', 'sell_ratio',
            'source_endpoint', 'request_start', 'request_end', 'cursor_lineage',
            'fetched_at', 'parser_version', 'payload_sha256', 'artifact_sha256'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'alpha_long_short_ratio_history'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V125 Guard A FAIL: research.alpha_long_short_ratio_history exists but missing '
                'required columns: %. 解決 legacy schema drift 後重跑 V125.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.alpha_long_short_ratio_history (
    run_id           TEXT         NOT NULL,
    category         TEXT         NOT NULL,
    symbol           TEXT         NOT NULL,
    period           TEXT         NOT NULL,                     -- bybit LS period (5min/1h/...)
    ts               TIMESTAMPTZ  NOT NULL,                     -- hypertable time col
    -- 【C-3】NOT NULL fail-closed：buy/sell ratio 缺值 0.0 default 會偽造「多空均衡」
    buy_ratio        DOUBLE PRECISION NOT NULL,
    sell_ratio       DOUBLE PRECISION NOT NULL,
    source_endpoint  TEXT,
    request_start    TIMESTAMPTZ,
    request_end      TIMESTAMPTZ,
    cursor_lineage   TEXT,
    fetched_at       TIMESTAMPTZ,
    parser_version   TEXT,
    payload_sha256   TEXT,
    artifact_sha256  TEXT,
    PRIMARY KEY (category, symbol, period, ts, run_id)
);

-- ============================================================
-- Guard B: type 敏感欄位反射（per packet §7 Guard B）
-- 為什麼：writer（backfill）寫入靠 type 對齊；type drift = silent write fail / 精度損失 /
--   fake-zero 漏網。驗 run_id (text) / digest (text) / timestamp (timestamptz) /
--   numeric data col (double precision) / boolean。column 不存在 v_actual=NULL → skip
--   （CREATE TABLE 已負責建）。
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- run ledger run_id 必 text（PK 型別契約）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_history_ingest_runs' AND column_name='run_id';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_history_ingest_runs.run_id is %, expected text.', v_actual;
    END IF;

    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_history_ingest_runs' AND column_name='git_dirty';
    IF v_actual IS NOT NULL AND v_actual <> 'boolean' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_history_ingest_runs.git_dirty is %, expected boolean.', v_actual;
    END IF;

    -- funding：time col timestamptz + data col double precision（C-3 fail-closed 型別）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_funding_rates_history' AND column_name='funding_ts';
    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_funding_rates_history.funding_ts is %, expected timestamptz.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_funding_rates_history' AND column_name='funding_rate';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_funding_rates_history.funding_rate is %, expected double precision.', v_actual;
    END IF;

    -- OI：time col timestamptz + open_interest double precision
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_open_interest_history' AND column_name='ts';
    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_open_interest_history.ts is %, expected timestamptz.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_open_interest_history' AND column_name='open_interest';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_open_interest_history.open_interest is %, expected double precision.', v_actual;
    END IF;

    -- LS：time col timestamptz + buy/sell ratio double precision
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_long_short_ratio_history' AND column_name='ts';
    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_long_short_ratio_history.ts is %, expected timestamptz.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_long_short_ratio_history' AND column_name='buy_ratio';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_long_short_ratio_history.buy_ratio is %, expected double precision.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='alpha_long_short_ratio_history' AND column_name='sell_ratio';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION 'V125 Guard B FAIL: alpha_long_short_ratio_history.sell_ratio is %, expected double precision.', v_actual;
    END IF;
END $$;

-- ============================================================
-- §C 3 history 表轉 hypertable + compression + retention
-- per packet §6：chunk 7d / compression 30d / retention 1095d。time col 皆 TIMESTAMPTZ
-- → 全用 INTERVAL（非 BIGINT-ms）。
--
-- 【C-5】compress_segmentby = 'symbol'（低基數）；run_id 入 orderby（高基數，不入 segmentby
--   防壓縮碎片化）。
--
-- 【冪等 + compressed-twin nested EXCEPTION】compression enable 包 NOT EXISTS guard
--   （已啟用 → skip ALTER）+ nested BEGIN/EXCEPTION（吞 re-apply 時 twin 傳播相關
--   duplicate_object / undefined_column；抄 V114:249-257 範式）。policy 用 if_not_exists。
-- ============================================================

-- ---- §C.1 alpha_funding_rates_history ----
SELECT create_hypertable(
    'research.alpha_funding_rates_history',
    'funding_ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='alpha_funding_rates_history'
    ) THEN
        BEGIN
            ALTER TABLE research.alpha_funding_rates_history SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby   = 'funding_ts DESC, run_id'
            );
            RAISE NOTICE 'V125: compression enabled on alpha_funding_rates_history (segmentby=symbol)';
        EXCEPTION
            WHEN duplicate_object OR undefined_column THEN
                -- re-apply 場景：compressed twin 已存在；compression 設定已落，skip 不破冪等
                RAISE NOTICE 'V125: compression ALTER skipped on alpha_funding_rates_history '
                             '(already enabled / twin exists; idempotent)';
        END;
    ELSE
        RAISE NOTICE 'V125: compression already enabled on alpha_funding_rates_history; skipping ALTER';
    END IF;
END $$;

SELECT add_compression_policy('research.alpha_funding_rates_history', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('research.alpha_funding_rates_history', INTERVAL '1095 days', if_not_exists => TRUE);

-- ---- §C.2 alpha_open_interest_history ----
SELECT create_hypertable(
    'research.alpha_open_interest_history',
    'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='alpha_open_interest_history'
    ) THEN
        BEGIN
            ALTER TABLE research.alpha_open_interest_history SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby   = 'ts DESC, run_id'
            );
            RAISE NOTICE 'V125: compression enabled on alpha_open_interest_history (segmentby=symbol)';
        EXCEPTION
            WHEN duplicate_object OR undefined_column THEN
                RAISE NOTICE 'V125: compression ALTER skipped on alpha_open_interest_history '
                             '(already enabled / twin exists; idempotent)';
        END;
    ELSE
        RAISE NOTICE 'V125: compression already enabled on alpha_open_interest_history; skipping ALTER';
    END IF;
END $$;

SELECT add_compression_policy('research.alpha_open_interest_history', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('research.alpha_open_interest_history', INTERVAL '1095 days', if_not_exists => TRUE);

-- ---- §C.3 alpha_long_short_ratio_history ----
SELECT create_hypertable(
    'research.alpha_long_short_ratio_history',
    'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='alpha_long_short_ratio_history'
    ) THEN
        BEGIN
            ALTER TABLE research.alpha_long_short_ratio_history SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby   = 'ts DESC, run_id'
            );
            RAISE NOTICE 'V125: compression enabled on alpha_long_short_ratio_history (segmentby=symbol)';
        EXCEPTION
            WHEN duplicate_object OR undefined_column THEN
                RAISE NOTICE 'V125: compression ALTER skipped on alpha_long_short_ratio_history '
                             '(already enabled / twin exists; idempotent)';
        END;
    ELSE
        RAISE NOTICE 'V125: compression already enabled on alpha_long_short_ratio_history; skipping ALTER';
    END IF;
END $$;

SELECT add_compression_policy('research.alpha_long_short_ratio_history', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('research.alpha_long_short_ratio_history', INTERVAL '1095 days', if_not_exists => TRUE);

-- ============================================================
-- §B-index Hot-path indexes（per packet §6，建後由 Guard C 驗）
-- 1. (symbol, <time> DESC)         — symbol + 時間 DESC 熱查（surface-specific）
-- 2. (run_id, symbol, <time>)      — 按 run lineage 重放
-- 3. (coverage_status) partial     — coverage 報告（status <> 'pass'）— 限 ledger/provenance 表
-- ============================================================

-- run ledger：status 查 + program 查
CREATE INDEX IF NOT EXISTS idx_alpha_ingest_runs_status
    ON research.alpha_history_ingest_runs (status, created_at DESC);

-- pages：run lineage + coverage partial（status <> 'pass' 才是 coverage 報告關注對象）
CREATE INDEX IF NOT EXISTS idx_alpha_ingest_pages_run_symbol
    ON research.alpha_history_ingest_pages (run_id, symbol, fetched_at);
CREATE INDEX IF NOT EXISTS idx_alpha_ingest_pages_coverage_attn
    ON research.alpha_history_ingest_pages (coverage_status)
    WHERE coverage_status IS DISTINCT FROM 'pass';

-- klines provenance：run lineage + coverage partial
CREATE INDEX IF NOT EXISTS idx_alpha_klines_prov_run_symbol
    ON research.alpha_klines_provenance (run_id, symbol, window_start);
CREATE INDEX IF NOT EXISTS idx_alpha_klines_prov_coverage_attn
    ON research.alpha_klines_provenance (coverage_status)
    WHERE coverage_status IS DISTINCT FROM 'pass';

-- funding history：(symbol, funding_ts DESC) 熱查 + (run_id, symbol, funding_ts) lineage
CREATE INDEX IF NOT EXISTS idx_alpha_funding_symbol_ts
    ON research.alpha_funding_rates_history (symbol, funding_ts DESC);
CREATE INDEX IF NOT EXISTS idx_alpha_funding_run_symbol_ts
    ON research.alpha_funding_rates_history (run_id, symbol, funding_ts);

-- OI history：(symbol, ts DESC) + (run_id, symbol, ts)
CREATE INDEX IF NOT EXISTS idx_alpha_oi_symbol_ts
    ON research.alpha_open_interest_history (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alpha_oi_run_symbol_ts
    ON research.alpha_open_interest_history (run_id, symbol, ts);

-- LS history：(symbol, ts DESC) + (run_id, symbol, ts)
CREATE INDEX IF NOT EXISTS idx_alpha_ls_symbol_ts
    ON research.alpha_long_short_ratio_history (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alpha_ls_run_symbol_ts
    ON research.alpha_long_short_ratio_history (run_id, symbol, ts);

-- ============================================================
-- §D market.klines retention 365 → 1095 替換（抄 V075:128-129 範式）
-- per packet §7：保留 14d compression 不動；只 replace retention。
-- klines time col = TIMESTAMPTZ ts（V002:122）→ retention 用 INTERVAL '1095 days'
--   （**非 BIGINT-ms**；BIGINT-ms 只用於 BIGINT time col）。
-- remove_retention_policy(if_exists=>TRUE) + add_retention_policy(if_not_exists=>TRUE)
--   = 確定性替換 + 冪等（既有 365d job 移除後加 1095d；第二次 apply：移除 1095d 再加回，
--   結果仍恰好一個 1095d job）。
-- ⚠️ 不碰 market.klines compression policy（14d，V006:31-32）——只動 retention。
-- ============================================================
SELECT remove_retention_policy('market.klines', if_exists => TRUE);
SELECT add_retention_policy('market.klines', INTERVAL '1095 days', if_not_exists => TRUE);

-- ============================================================
-- §COMMENT 語義文檔（idempotent: COMMENT ON 可重跑）
-- ============================================================
COMMENT ON TABLE research.alpha_history_ingest_runs IS
    'AEG-S1 歷史採集 run 帳本（V125）。每次 accepted run 一列；run_id TEXT PK（UUID/ULID/'
    'label）。status enum: planned/running/accepted/failed/superseded/inactive。'
    'manifest_sha256 + git_sha 保 run 可回溯。plain table（無 hypertable）。';
COMMENT ON TABLE research.alpha_history_ingest_pages IS
    'AEG-S1 endpoint/page 級 provenance（V125）。key (run_id, page_id)；coverage_status '
    'enum: pass/partial/failed/skipped/not_applicable。payload/artifact sha256 保 page 可重建。';
COMMENT ON TABLE research.alpha_klines_provenance IS
    'AEG-S1 OHLCV 寫入 market.klines 的 append-only 來源帳（V125）。不 ALTER market.klines '
    'row shape（per packet §4）；identity = run_id+endpoint+category+symbol+timeframe+window。';
COMMENT ON TABLE research.alpha_funding_rates_history IS
    'AEG-S1 funding 歷史 hypertable（V125；time col funding_ts，7d chunk / 30d compress / '
    '1095d retention）。PK (category,symbol,funding_ts,run_id) 保 run lineage 不靜默覆蓋。'
    'funding_rate NOT NULL（C-3 fail-closed：parser 缺值 0.0-default 會 silent fake-zero '
    '污染 PIT 證據；parse-fail 由 backfill writer reject）。compress segmentby=symbol（C-5）。';
COMMENT ON TABLE research.alpha_open_interest_history IS
    'AEG-S1 OI 歷史 hypertable（V125；time col ts，7d/30d/1095d）。PK (category,symbol,'
    'interval_time,ts,run_id)。open_interest NOT NULL（C-3）。compress segmentby=symbol（C-5）。';
COMMENT ON TABLE research.alpha_long_short_ratio_history IS
    'AEG-S1 多空比歷史 hypertable（V125；time col ts，7d/30d/1095d）。PK (category,symbol,'
    'period,ts,run_id)。buy_ratio/sell_ratio 雙 NOT NULL（C-3：缺值 0.0 會偽造多空均衡）。'
    'compress segmentby=symbol（C-5）。';

COMMENT ON COLUMN research.alpha_funding_rates_history.funding_rate IS
    'C-3 fail-closed NOT NULL：funding rate 缺值不可入庫。既有 Bybit parser 對缺值 '
    'default 0.0；0.0 funding 與「真實 0 funding」不可區分 → 污染 PIT alpha 證據。'
    'writer parse-fail 必 reject（不寫此 row），由 backfill writer 負責。';
COMMENT ON COLUMN research.alpha_open_interest_history.open_interest IS
    'C-3 fail-closed NOT NULL：OI 缺值不可入庫（同 funding_rate 理由）。';
COMMENT ON COLUMN research.alpha_long_short_ratio_history.buy_ratio IS
    'C-3 fail-closed NOT NULL：多空比 buy 側缺值不可入庫；0.0 default 會偽造多空均衡。';
COMMENT ON COLUMN research.alpha_long_short_ratio_history.sell_ratio IS
    'C-3 fail-closed NOT NULL：多空比 sell 側缺值不可入庫；0.0 default 會偽造多空均衡。';

COMMIT;

-- ============================================================
-- §E Guard C 後驗（COMMIT 後獨立檢查；不在 transaction 內，純讀驗證）
-- per packet §7 Guard C + Retention guard：
--   - 6 表全存在
--   - 3 history 表確為 hypertable（chunk = 7d）
--   - 3 history 表 compress_segmentby = 'symbol'（C-5）
--   - 3 history 表各有 1 retention job（drop_after = 1095 days）
--   - market.klines retention 恰好 1 個 active job（drop_after = 1095 days）
--   - 關鍵 hot-path index 到位
-- 任一不符 → RAISE EXCEPTION（fail-loud）。
-- ============================================================
DO $$
DECLARE
    v_count          INTEGER;
    v_chunk          BIGINT;
    v_comp_enabled   BOOLEAN;
    v_symbol_segby   BOOLEAN;
    v_klines_jobs    INTEGER;
    v_klines_drop    INTERVAL;
    v_drop           INTERVAL;
    v_tbl            TEXT;
    v_timecol        TEXT;
    -- 3 history 表 (table, time col) 對照
    r RECORD;
BEGIN
    -- 6 表全存在
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables
    WHERE table_schema='research'
      AND table_name IN (
          'alpha_history_ingest_runs', 'alpha_history_ingest_pages',
          'alpha_klines_provenance', 'alpha_funding_rates_history',
          'alpha_open_interest_history', 'alpha_long_short_ratio_history'
      );
    IF v_count <> 6 THEN
        RAISE EXCEPTION 'V125 Guard C FAIL: research 6 表預期，實得 %.', v_count;
    END IF;

    -- 3 history 表逐一驗 hypertable chunk=7d + segmentby=symbol + retention=1095d
    FOR r IN
        SELECT * FROM (VALUES
            ('alpha_funding_rates_history', 'funding_ts'),
            ('alpha_open_interest_history', 'ts'),
            ('alpha_long_short_ratio_history', 'ts')
        ) AS t(tbl, timecol)
    LOOP
        v_tbl := r.tbl; v_timecol := r.timecol;

        -- hypertable + chunk = 7d（TIMESTAMPTZ → time_interval 為 INTERVAL）
        SELECT EXTRACT(EPOCH FROM time_interval)::BIGINT INTO v_chunk
        FROM timescaledb_information.dimensions
        WHERE hypertable_schema='research' AND hypertable_name=v_tbl AND column_name=v_timecol;
        IF v_chunk IS NULL THEN
            RAISE EXCEPTION 'V125 Guard C FAIL: research.% 未建 hypertable on %.', v_tbl, v_timecol;
        END IF;
        IF v_chunk <> 604800 THEN  -- 7 days in seconds
            RAISE EXCEPTION 'V125 Guard C FAIL: research.% chunk = % sec（預期 604800 = 7d）.', v_tbl, v_chunk;
        END IF;

        -- C-5：compress_segmentby = symbol
        -- 為什麼不查 segmentby 欄：TimescaleDB 2.26.1 的
        -- timescaledb_information.compression_settings 無 segmentby 欄（舊版才有）；
        -- 實際 schema = (hypertable_schema, hypertable_name, attname,
        -- segmentby_column_index, orderby_column_index, orderby_asc, orderby_nullsfirst)。
        -- 「某欄是 segmentby 欄」的判定 = 該欄 row 的 segmentby_column_index IS NOT NULL。
        -- 先驗「compression 已啟用」（任一 row 存在），再驗「symbol 確為 segmentby 欄」，
        -- 兩種失敗分別 RAISE，保持 Guard C fail-loud 語義（C-5：低基數 symbol，run_id 走 orderby）。
        SELECT EXISTS (
            SELECT 1 FROM timescaledb_information.compression_settings
            WHERE hypertable_schema='research' AND hypertable_name=v_tbl
        ) INTO v_comp_enabled;
        IF NOT v_comp_enabled THEN
            RAISE EXCEPTION 'V125 Guard C FAIL: research.% compression 未啟用.', v_tbl;
        END IF;
        SELECT EXISTS (
            SELECT 1 FROM timescaledb_information.compression_settings
            WHERE hypertable_schema='research' AND hypertable_name=v_tbl
              AND attname='symbol' AND segmentby_column_index IS NOT NULL
        ) INTO v_symbol_segby;
        IF NOT v_symbol_segby THEN
            RAISE EXCEPTION
                'V125 Guard C FAIL: research.% compress_segmentby 不含 symbol（預期 symbol 為 segmentby 欄，C-5 低基數）.',
                v_tbl;
        END IF;

        -- retention = 1095d，恰好 1 個 job
        SELECT COUNT(*) INTO v_count
        FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_schema='research' AND hypertable_name=v_tbl;
        IF v_count <> 1 THEN
            RAISE EXCEPTION 'V125 Guard C FAIL: research.% retention job 數 = %（預期恰好 1）.', v_tbl, v_count;
        END IF;
        SELECT (config->>'drop_after')::INTERVAL INTO v_drop
        FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_schema='research' AND hypertable_name=v_tbl
        LIMIT 1;
        IF v_drop IS DISTINCT FROM INTERVAL '1095 days' THEN
            RAISE EXCEPTION 'V125 Guard C FAIL: research.% retention drop_after = %（預期 1095 days）.', v_tbl, v_drop;
        END IF;
    END LOOP;

    -- Retention guard：market.klines 恰好 1 個 retention job，drop_after = 1095 days
    SELECT COUNT(*) INTO v_klines_jobs
    FROM timescaledb_information.jobs
    WHERE proc_name='policy_retention'
      AND hypertable_schema='market' AND hypertable_name='klines';
    IF v_klines_jobs <> 1 THEN
        RAISE EXCEPTION
            'V125 Retention guard FAIL: market.klines retention job 數 = %（預期恰好 1）.', v_klines_jobs;
    END IF;
    SELECT (config->>'drop_after')::INTERVAL INTO v_klines_drop
    FROM timescaledb_information.jobs
    WHERE proc_name='policy_retention'
      AND hypertable_schema='market' AND hypertable_name='klines'
    LIMIT 1;
    IF v_klines_drop IS DISTINCT FROM INTERVAL '1095 days' THEN
        RAISE EXCEPTION
            'V125 Retention guard FAIL: market.klines retention drop_after = %（預期 1095 days）.', v_klines_drop;
    END IF;

    -- 關鍵 hot-path index 到位（抽驗 4 條 surface index）
    SELECT COUNT(*) INTO v_count
    FROM pg_indexes
    WHERE schemaname='research'
      AND indexname IN (
          'idx_alpha_funding_symbol_ts', 'idx_alpha_oi_symbol_ts',
          'idx_alpha_ls_symbol_ts', 'idx_alpha_ingest_pages_coverage_attn'
      );
    IF v_count <> 4 THEN
        RAISE EXCEPTION 'V125 Guard C FAIL: 關鍵 hot-path index 預期 4，實得 %.', v_count;
    END IF;

    RAISE NOTICE 'V125: all guards PASS —';
    RAISE NOTICE '  - research schema + 6 表（3 ledger plain + 3 history hypertable）';
    RAISE NOTICE '  - 3 history hypertable: chunk=7d / compress=30d segmentby=symbol(C-5) / retention=1095d';
    RAISE NOTICE '  - C-3 NOT NULL: funding_rate / open_interest / buy_ratio / sell_ratio';
    RAISE NOTICE '  - market.klines retention 365d -> 1095d（恰好 1 job；14d compression 不動）';
    RAISE NOTICE '  - hot-path index + coverage partial index 到位';
    RAISE NOTICE '';
    RAISE NOTICE 'Next（本 migration 範圍外，per packet §9）:';
    RAISE NOTICE '  - PA-backfill: endpoint client + historical writer（parse-fail reject，C-3 由 writer 強制）';
    RAISE NOTICE '  - backfill run / collector / alpha scoring / promotion report 皆獨立任務';
END $$;

-- ============================================================
-- §F ROLLBACK（手動執行；非 sqlx down migration — 本專案 sqlx forward-only）
-- per packet §8：
--   1. 還原 market.klines retention 365 days。
--   2. DROP 新 research.alpha_* 表用 RESTRICT（非 CASCADE）——若有依賴物件 DROP 會 fail-loud，
--      避免靜默連鎖刪除。
--   3. 若任何 history/provenance 表有 accepted 生產/backfill row → **不靜默刪**：保留 row，
--      改標 run status='inactive'（不刪證據）。
--   4. 永不刪 market.klines OHLCV row 作為 rollback。
--   5. sqlx checksum drift → 用既有 repair_migration_checksum 工作流（不手改 _sqlx_migrations）。
--
-- 安全 rollback（有 accepted row 時，標 inactive 不刪）:
--   UPDATE research.alpha_history_ingest_runs SET status='inactive'
--   WHERE status IN ('accepted','running','planned');
--   SELECT remove_retention_policy('market.klines', if_exists => TRUE);
--   SELECT add_retention_policy('market.klines', INTERVAL '365 days', if_not_exists => TRUE);
--
-- 完整 teardown（僅當確認無 accepted row；DROP RESTRICT 防連鎖）:
--   SELECT remove_retention_policy('market.klines', if_exists => TRUE);
--   SELECT add_retention_policy('market.klines', INTERVAL '365 days', if_not_exists => TRUE);
--   DROP TABLE IF EXISTS research.alpha_long_short_ratio_history RESTRICT;
--   DROP TABLE IF EXISTS research.alpha_open_interest_history    RESTRICT;
--   DROP TABLE IF EXISTS research.alpha_funding_rates_history    RESTRICT;
--   DROP TABLE IF EXISTS research.alpha_klines_provenance        RESTRICT;
--   DROP TABLE IF EXISTS research.alpha_history_ingest_pages     RESTRICT;
--   DROP TABLE IF EXISTS research.alpha_history_ingest_runs      RESTRICT;
--   DROP SCHEMA IF EXISTS research RESTRICT;  -- 僅當 research 無其他物件
-- ============================================================
