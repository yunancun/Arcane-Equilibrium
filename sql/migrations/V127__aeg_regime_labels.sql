-- ============================================================
-- V127: research.aeg_regime_labels + research.aeg_regime_transitions
--       — AEG-S2 component (a) Regime Label Runner 的儲存層
--
--   AEG-S2 證據自動化層的 (a) 組件：版本化、凍結、leak-free 的 per-symbol +
--   BTC-anchored daily regime 標籤儲存。供候選評分層（listing-fade / trend）
--   讀 `WHERE classifier_version=<pinned>` 重建 regime slice，候選不能移動 regime
--   邊界來 fit 策略（ADR-0047 rule 7 + S0 §2.1 immutability）。
--
-- 動機 / Motivation:
--   AEG-S0 凍結分類器 `aeg_regime_v0.1.0`（5 main + 11 overlay flag + per-symbol
--   AND anchor + feature-lineage）。S2 (a) productionize 此分類器為 batch research
--   runner，把每個 closed daily bar 的 regime 標籤 + 凍結 feature 落 PG，作為 (c)
--   robustness matrix 的 regime 軸來源。
--
--   ⚠️ 本 migration 僅建 2 表 + Timescale 政策。regime runner（分類器 code /
--   feature 計算 / leak-free PIT / feature_lineage.parquet / backfill）全不在本
--   migration 範圍（per MIT design report component (a)，runner 為獨立 IMPL 任務）。
--
-- SOURCE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-03--aeg_s2_evidence_automation_design.md
--   Component (a) §a.2 storage schema / §a.3 versioning / §a.4 leak-free PIT
--   Template: sql/migrations/V125__aeg_alpha_history_storage.sql（Guard A/B/C +
--   Timescale preguard + hypertable + compression + retention 既有 pattern）
--
-- 範圍 / Scope (V127):
--   §A CREATE SCHEMA IF NOT EXISTS research (idempotent；V125 已建，第二次 no-op)
--   §B 2 表 CREATE TABLE IF NOT EXISTS + Guard A（既有表缺欄 → RAISE）：
--       1. research.aeg_regime_labels      — per-symbol daily regime 標籤（hypertable on signal_ts）
--       2. research.aeg_regime_transitions — regime 轉移事件（hypertable on transition_ts）
--   §C Guard B（type 敏感欄反射）
--   §D 2 表轉 hypertable（7d chunk）+ compression（30d，segmentby=symbol）+ retention（1095d）
--   §E hot-path index（Guard C 前置建立）
--   §F Guard C 後驗（COMMIT 後獨立檢查）
--   §G ROLLBACK 註解
--
-- 設計決策（折入 MIT schema + V125 既有 pattern）:
--   【classifier_version 入 PK = immutability 軸】(MIT §a.3，本 migration 最重要契約)
--     PK = (classifier_version, symbol, timeframe, signal_ts, run_id)。
--     為什麼：新 classifier 版本（bump v0.2.0）寫新列，舊 verdict 列 immutable 可重現
--     （ADR-0047 rule 7：分類器須在 scoring 前固定）。無 version 軸 → 新版本會 silent
--     overwrite / ON CONFLICT 衝突 → 候選可移 regime 邊界 fit 策略（禁）。這正是 MIT
--     report BLOCKING FINDING 拒絕重用 V002 `market.regime_snapshots`（PK 無 version 軸）
--     的根因。
--
--   【schema = research.* 非 market.*】(MIT BLOCKING FINDING)
--     不重用 V002 `market.regime_snapshots`（intraday 5m/15m/1h/4h、無版本、無 overlay
--     flag、無 run_id provenance、regime TEXT 無 CHECK，與 AEG daily-anchor/版本化語義
--     不相容）。在 research.* 建版本化 AEG-native 表；V002 表保持不動（dormant slot）。
--
--   【10 feature 欄 = REAL，允許 NULL】(MIT §a.2)
--     ret_30d / ret_90d / rv_30d / rv_90d / trend_z_30 / ma_50 / ma_200 /
--     efficiency_30 / direction_flip_30 / rv_30d_percentile_365 全 REAL（4-byte，
--     符合 MIT schema 明示；非 V125 的 DOUBLE PRECISION）。
--     為什麼允許 NULL（非 C-3 fail-closed）：feature 是「凍結診斷快照」非「fail-closed
--     交易資料值」；insufficient_context 列（context_bars 不足）部分 feature 必為 NULL
--     （200d MA 在 <200 bar 時無法算）。NOT NULL 的是 main_regime 等「該 bar 必有的
--     分類結果 + provenance」欄（見下），不是衍生 feature。
--     對比 V125 C-3：V125 的 funding_rate/open_interest/buy_ratio/sell_ratio 是 fail-closed
--     資料值（parser 缺值 default 0.0 會 silent fake-zero 污染 PIT），故 NOT NULL；本表
--     的 feature 是分類器內部產物，insufficient_context 語義由 main_regime + flag 顯式
--     承載，feature NULL 不污染證據。
--
--   【market_anchor_regime denormalized 允許 NULL】(MIT §a.2)
--     BTCUSDT 同 signal_ts 的 main_regime，冗餘存避免消費者 self-join。允許 NULL：
--     BTC anchor 列本身寫入時 anchor 可能尚未算（或非 BTC 列在 anchor 缺失時）。
--
--   【compress_segmentby = symbol 低基數】(沿用 V125 C-5)
--     2 表 compression segmentby 全用 'symbol'（低基數 ~25-293 sym）。
--     為什麼不含 classifier_version / run_id：classifier_version 極低基數（理論可選但
--     2 表多為單一 pinned version，segment 切割收益低）；run_id 高基數（每 run 一新值，
--     無上界）→ 含進 segmentby 會壓縮碎片化 + 壓縮率崩潰。classifier_version / run_id
--     留在 orderby（與時間一起排序）保 query locality（同 V125 對 run_id 的處理）。
--
--   【冪等 double-apply 全 no-op】(per CLAUDE「applying twice」+ V114/V125 教訓)
--     - CREATE SCHEMA / TABLE IF [NOT] EXISTS         → 第二次 no-op（Guard A 已驗 shape）
--     - create_hypertable(... if_not_exists => TRUE)  → 第二次 no-op
--     - ALTER TABLE ... SET (timescaledb.compress)    → 包 NOT EXISTS guard，已啟用則 skip
--     - add_compression_policy / add_retention_policy → if_not_exists => TRUE
--     - CREATE INDEX IF NOT EXISTS                    → 第二次 no-op（Guard C 已驗 shape）
--     - COMMENT ON                                    → 可重跑
--
--   【§F Guard C 在 COMMIT 後 + TSDB 2.26.1 compression_settings 反射】(V125 §E 教訓，硬繼承)
--     §F Guard C 後驗在顯式 COMMIT 之後執行（autocommit 區）。TimescaleDB 2.26.1 的
--     timescaledb_information.compression_settings **無 segmentby 欄**（舊版才有）；
--     「某欄是否為 segmentby」的判定 = 該欄 row 的 segmentby_column_index IS NOT NULL。
--     V125 §E 初版用 `.segmentby` 欄 → deploy crash-loop（DDL 已落 + §E 報錯 → migrator
--     abort → sqlx 未記版本 → 重啟 re-apply §A-§E 再炸）。本 migration 直接用正確反射。
--
-- Timescale 政策（同 V125 research-history 決策 + MIT §a.2）:
--   | chunk interval | 7 days   |
--   | compression    | after 30 days |
--   | retention      | 1095 days |
--   2 表 time col 皆 TIMESTAMPTZ（signal_ts / transition_ts）→ chunk/compression/
--   retention 全用 INTERVAL（**非 BIGINT-ms**）。
--
-- Idempotency 重跑兩次必 PASS（per memory feedback_v_migration_pg_dry_run
--   double-apply mandatory）。本 migration 須 Linux PG empirical 雙跑 dry-run 才能
--   sign-off（Mac mock PG 抓不到 Timescale runtime semantic）。
--
-- Guard（per V125 pattern，fail-closed + idempotent）:
--   Timescale preguard — extension 必存，否則 RAISE（不靜默 skip hypertable 政策）
--   Guard A — 每個 CREATE TABLE IF NOT EXISTS 前驗既有表必要欄完整（缺 → RAISE）
--   Guard B — type 敏感欄反射（classifier_version/run_id/signal_ts/feature/boolean/jsonb）
--   Guard C — 建後驗 hypertable + segmentby + retention + load-bearing index（§F，COMMIT 後）
--
-- E2 review checklist:
--   1. Guard A 對 2 表必要欄完整性（重跑 shape drift → RAISE）
--   2. PK 含 classifier_version（immutability 軸）+ hypertable time col（Timescale 要求）
--   3. CHECK：timeframe IN ('1d','4h_to_1d')；main_regime 6-enum
--   4. 10 feature 欄 = REAL（非 double precision，照 MIT schema）
--   5. compress_segmentby = 'symbol'（不含 classifier_version/run_id 高基數）
--   6. §F Guard C 在 COMMIT 後 + 用 segmentby_column_index IS NOT NULL（非 .segmentby 欄）
--   7. 冪等：compression enable 包 NOT EXISTS guard + nested EXCEPTION；policy 用 if_not_exists
--   8. rollback：DROP RESTRICT（非 CASCADE）
--
-- 硬邊界:
--   - 不碰 V002 market.regime_snapshots / market.regime_transitions（保持 dormant，
--     MIT BLOCKING FINDING；那是 intraday producer 的獨立議題）。
--   - 不碰 V125 已建 research.alpha_* 6 表（disjoint，純新增 2 表）。
--   - 不改 max_retries / live_execution_allowed / execution_authority / system_mode（無關）。
--   - append-only 語義：label / transition 表前向累積；rollback 不靜默刪 row（標 superseded）。
--
-- migration latest: V126 → V127（AEG-S2 (a) 槽；Linux _sqlx_migrations head=126 已確認
--   V125/V126 applied；V116-124 held 給 M5/M7/M12/M13 + funding_arb V3，V127 避撞；
--   V128 reserved-if-needed 給 deferred breadth 表 per MIT report b.3）。
-- ============================================================

BEGIN;

-- ============================================================
-- Timescale preguard: TimescaleDB extension 必存
-- 為什麼 fail-closed（不靜默 skip）：本 migration 核心交付 = 2 hypertable + compression
--   + retention。若 extension 缺，靜默 skip 會留下「表建了但無 chunk rotate / 無 retention
--   自動化」的假完成狀態，違反 fail-loud 原則。trade-core 生產 PG 已裝 TimescaleDB
--   2.26.1（V125 reflection），缺失 = 環境異常。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE EXCEPTION
            'V127 Timescale preguard FAIL: TimescaleDB extension missing. '
            '本 migration 需 hypertable + compression + retention，不可在無 Timescale '
            '環境靜默 skip。請於有 TimescaleDB 的 PG 上 apply。';
    END IF;
END $$;

-- ============================================================
-- §A CREATE SCHEMA IF NOT EXISTS research (idempotent)
-- research namespace = AEG promotion-grade 證據邊界（V125 已建）。第二次 apply no-op。
-- ============================================================
CREATE SCHEMA IF NOT EXISTS research;

-- ============================================================
-- §B.1 research.aeg_regime_labels — per-symbol daily regime 標籤（hypertable on signal_ts）
-- per MIT §a.2。PK (classifier_version, symbol, timeframe, signal_ts, run_id)。
-- classifier_version 入 PK = immutability 軸（ADR-0047 rule 7）。
-- ============================================================

-- Guard A: aeg_regime_labels 既有表必要欄完整性（缺 ≥1 → RAISE）
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'aeg_regime_labels'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'classifier_version', 'run_id', 'signal_ts', 'symbol', 'timeframe',
            'main_regime', 'market_anchor_regime', 'high_vol_overlay', 'overlay_flags',
            'ret_30d', 'ret_90d', 'rv_30d', 'rv_90d', 'trend_z_30',
            'ma_50', 'ma_200', 'efficiency_30', 'direction_flip_30', 'rv_30d_percentile_365',
            'context_bars', 'insufficient_context', 'feature_rules_digest',
            'git_sha', 'git_dirty', 'created_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'aeg_regime_labels'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V127 Guard A FAIL: research.aeg_regime_labels exists but missing '
                'required columns: %. 解決 legacy schema drift（DROP + re-apply 或 ALTER ADD）'
                '後重跑 V127.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.aeg_regime_labels (
    -- classifier_version：凍結分類器版本字串（'aeg_regime_v0.1.0'）；PK 首欄 = immutability 軸
    classifier_version    TEXT             NOT NULL,
    -- run_id：FK-spirit → research.alpha_history_ingest_runs.run_id（lineage，不靜默覆蓋）
    run_id                TEXT             NOT NULL,
    -- signal_ts：被標 bar 的 signal 時點（UTC，closed bar）；hypertable time col
    signal_ts             TIMESTAMPTZ      NOT NULL,
    -- symbol：per-symbol；'BTCUSDT' 列兼 market anchor 來源
    symbol                TEXT             NOT NULL,
    -- timeframe：CHECK 限 '1d' / '4h_to_1d'（S0 §2.2 兩種 closed-bar 構造）
    timeframe             TEXT             NOT NULL DEFAULT '1d'
                                           CHECK (timeframe IN ('1d', '4h_to_1d')),
    -- main_regime：5 main + insufficient_context；CHECK 防 V002 vocabulary 混雜（S0 §1.7）
    main_regime           TEXT             NOT NULL
                                           CHECK (main_regime IN (
                                               'bull', 'bear', 'high-vol',
                                               'chop', 'range', 'insufficient_context'
                                           )),
    -- market_anchor_regime：BTCUSDT 同 signal_ts 的 main_regime（denormalized 免 self-join）；
    -- 允許 NULL（anchor 列本身 / anchor 缺失時）
    market_anchor_regime  TEXT,
    high_vol_overlay      BOOLEAN          NOT NULL DEFAULT false,
    -- overlay_flags：11 個 S0 §2.8 flag 的 bool map（JSONB）
    overlay_flags         JSONB            NOT NULL DEFAULT '{}'::jsonb,
    -- 10 凍結 feature 欄（REAL，照 MIT §a.2；允許 NULL — insufficient_context 列部分 feature 無法算）
    ret_30d               REAL,
    ret_90d               REAL,
    rv_30d                REAL,
    rv_90d                REAL,
    trend_z_30            REAL,
    ma_50                 REAL,
    ma_200                REAL,
    efficiency_30         REAL,
    direction_flip_30     REAL,
    rv_30d_percentile_365 REAL,
    -- context_bars：算此標籤所用的 closed bar 數（PIT context 深度）
    context_bars          INTEGER          NOT NULL,
    insufficient_context  BOOLEAN          NOT NULL DEFAULT false,
    -- feature_rules_digest：sha256 of frozen feature/threshold 定義；runner 若 running code
    -- digest ≠ classifier_version 註冊值 → 拒寫（防凍結版本字串下 silent drift，MIT §a.3）
    feature_rules_digest  TEXT             NOT NULL,
    git_sha               TEXT             NOT NULL,
    git_dirty             BOOLEAN          NOT NULL,
    created_at            TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (classifier_version, symbol, timeframe, signal_ts, run_id)
);

-- ============================================================
-- §B.2 research.aeg_regime_transitions — regime 轉移事件（hypertable on transition_ts）
-- per MIT §a.2。PK (classifier_version, symbol, timeframe, transition_ts, run_id)。
-- 首次給 regime_transitions 真實列 — AEG-native daily-anchor，非 V002 intraday。
-- ============================================================

-- Guard A: aeg_regime_transitions 既有表必要欄完整性
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'aeg_regime_transitions'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'classifier_version', 'run_id', 'symbol', 'timeframe',
            'transition_ts', 'from_regime', 'to_regime', 'trigger_feature', 'created_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'aeg_regime_transitions'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V127 Guard A FAIL: research.aeg_regime_transitions exists but missing '
                'required columns: %. 解決 legacy schema drift 後重跑 V127.', v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.aeg_regime_transitions (
    classifier_version  TEXT             NOT NULL,
    run_id              TEXT             NOT NULL,
    symbol              TEXT             NOT NULL,
    timeframe           TEXT             NOT NULL DEFAULT '1d'
                                         CHECK (timeframe IN ('1d', '4h_to_1d')),
    -- transition_ts：轉移發生的 signal 時點（UTC，closed bar）；hypertable time col
    transition_ts       TIMESTAMPTZ      NOT NULL,
    -- from_regime / to_regime：同 main_regime 詞表（CHECK 防混雜）
    from_regime         TEXT             NOT NULL
                                         CHECK (from_regime IN (
                                             'bull', 'bear', 'high-vol',
                                             'chop', 'range', 'insufficient_context'
                                         )),
    to_regime           TEXT             NOT NULL
                                         CHECK (to_regime IN (
                                             'bull', 'bear', 'high-vol',
                                             'chop', 'range', 'insufficient_context'
                                         )),
    -- trigger_feature：觸發轉移的 feature 快照（JSONB；diagnostic，允許 NULL）
    trigger_feature     JSONB,
    created_at          TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (classifier_version, symbol, timeframe, transition_ts, run_id)
);

-- ============================================================
-- §C Guard B: type 敏感欄反射（per V125 Guard B pattern）
-- 為什麼：runner 寫入靠 type 對齊；type drift = silent write fail / 精度損失。
--   驗 classifier_version (text) / run_id (text) / time col (timestamptz) /
--   feature col (real) / boolean / jsonb。column 不存在 v_actual=NULL → skip
--   （CREATE TABLE 已負責建）。
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- labels: classifier_version 必 text（PK 首欄 immutability 軸型別契約）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_labels' AND column_name='classifier_version';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_labels.classifier_version is %, expected text.', v_actual;
    END IF;

    -- labels: signal_ts timestamptz（hypertable time col）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_labels' AND column_name='signal_ts';
    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_labels.signal_ts is %, expected timestamptz.', v_actual;
    END IF;

    -- labels: overlay_flags jsonb
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_labels' AND column_name='overlay_flags';
    IF v_actual IS NOT NULL AND v_actual <> 'jsonb' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_labels.overlay_flags is %, expected jsonb.', v_actual;
    END IF;

    -- labels: feature col real（抽驗 ret_30d / rv_30d_percentile_365；照 MIT REAL 契約）
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_labels' AND column_name='ret_30d';
    IF v_actual IS NOT NULL AND v_actual <> 'real' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_labels.ret_30d is %, expected real.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_labels' AND column_name='rv_30d_percentile_365';
    IF v_actual IS NOT NULL AND v_actual <> 'real' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_labels.rv_30d_percentile_365 is %, expected real.', v_actual;
    END IF;

    -- labels: high_vol_overlay / insufficient_context / git_dirty boolean
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_labels' AND column_name='high_vol_overlay';
    IF v_actual IS NOT NULL AND v_actual <> 'boolean' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_labels.high_vol_overlay is %, expected boolean.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_labels' AND column_name='context_bars';
    IF v_actual IS NOT NULL AND v_actual <> 'integer' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_labels.context_bars is %, expected integer.', v_actual;
    END IF;

    -- transitions: classifier_version text + transition_ts timestamptz + trigger_feature jsonb
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_transitions' AND column_name='classifier_version';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_transitions.classifier_version is %, expected text.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_transitions' AND column_name='transition_ts';
    IF v_actual IS NOT NULL AND v_actual <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_transitions.transition_ts is %, expected timestamptz.', v_actual;
    END IF;
    SELECT data_type INTO v_actual FROM information_schema.columns
    WHERE table_schema='research' AND table_name='aeg_regime_transitions' AND column_name='trigger_feature';
    IF v_actual IS NOT NULL AND v_actual <> 'jsonb' THEN
        RAISE EXCEPTION 'V127 Guard B FAIL: aeg_regime_transitions.trigger_feature is %, expected jsonb.', v_actual;
    END IF;
END $$;

-- ============================================================
-- §D 2 表轉 hypertable + compression + retention
-- per MIT §a.2 + V125 pattern：chunk 7d / compression 30d / retention 1095d。
-- time col 皆 TIMESTAMPTZ → 全用 INTERVAL（非 BIGINT-ms）。
--
-- 【C-5】compress_segmentby = 'symbol'（低基數）；classifier_version / run_id 入 orderby
--   （高基數 run_id 不入 segmentby 防壓縮碎片化）。
--
-- 【冪等 + compressed-twin nested EXCEPTION】compression enable 包 NOT EXISTS guard
--   （已啟用 → skip ALTER）+ nested BEGIN/EXCEPTION（吞 re-apply 時 twin 傳播相關
--   duplicate_object / undefined_column；抄 V125:590-612 範式）。policy 用 if_not_exists。
-- ============================================================

-- ---- §D.1 aeg_regime_labels ----
SELECT create_hypertable(
    'research.aeg_regime_labels',
    'signal_ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='aeg_regime_labels'
    ) THEN
        BEGIN
            ALTER TABLE research.aeg_regime_labels SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby   = 'signal_ts DESC, classifier_version, run_id'
            );
            RAISE NOTICE 'V127: compression enabled on aeg_regime_labels (segmentby=symbol)';
        EXCEPTION
            WHEN duplicate_object OR undefined_column THEN
                -- re-apply 場景：compressed twin 已存在；compression 設定已落，skip 不破冪等
                RAISE NOTICE 'V127: compression ALTER skipped on aeg_regime_labels '
                             '(already enabled / twin exists; idempotent)';
        END;
    ELSE
        RAISE NOTICE 'V127: compression already enabled on aeg_regime_labels; skipping ALTER';
    END IF;
END $$;

SELECT add_compression_policy('research.aeg_regime_labels', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('research.aeg_regime_labels', INTERVAL '1095 days', if_not_exists => TRUE);

-- ---- §D.2 aeg_regime_transitions ----
SELECT create_hypertable(
    'research.aeg_regime_transitions',
    'transition_ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema='research' AND hypertable_name='aeg_regime_transitions'
    ) THEN
        BEGIN
            ALTER TABLE research.aeg_regime_transitions SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby   = 'transition_ts DESC, classifier_version, run_id'
            );
            RAISE NOTICE 'V127: compression enabled on aeg_regime_transitions (segmentby=symbol)';
        EXCEPTION
            WHEN duplicate_object OR undefined_column THEN
                RAISE NOTICE 'V127: compression ALTER skipped on aeg_regime_transitions '
                             '(already enabled / twin exists; idempotent)';
        END;
    ELSE
        RAISE NOTICE 'V127: compression already enabled on aeg_regime_transitions; skipping ALTER';
    END IF;
END $$;

SELECT add_compression_policy('research.aeg_regime_transitions', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('research.aeg_regime_transitions', INTERVAL '1095 days', if_not_exists => TRUE);

-- ============================================================
-- §E Hot-path indexes（per MIT §a.2，建後由 §F Guard C 驗）
-- 1. (classifier_version, symbol, timeframe, signal_ts DESC) — pinned-version 單 symbol 時序熱查
-- 2. (classifier_version, signal_ts, main_regime)            — 跨 symbol regime slice 聚合
-- 3. (run_id, symbol)                                        — run lineage 重放
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_aeg_regime_labels_ver_sym_tf_ts
    ON research.aeg_regime_labels (classifier_version, symbol, timeframe, signal_ts DESC);
CREATE INDEX IF NOT EXISTS idx_aeg_regime_labels_ver_ts_regime
    ON research.aeg_regime_labels (classifier_version, signal_ts, main_regime);
CREATE INDEX IF NOT EXISTS idx_aeg_regime_labels_run_symbol
    ON research.aeg_regime_labels (run_id, symbol);

-- transitions：pinned-version 單 symbol 轉移時序 + run lineage
CREATE INDEX IF NOT EXISTS idx_aeg_regime_transitions_ver_sym_ts
    ON research.aeg_regime_transitions (classifier_version, symbol, timeframe, transition_ts DESC);
CREATE INDEX IF NOT EXISTS idx_aeg_regime_transitions_run_symbol
    ON research.aeg_regime_transitions (run_id, symbol);

-- ============================================================
-- §COMMENT 語義文檔（idempotent: COMMENT ON 可重跑）
-- ============================================================
COMMENT ON TABLE research.aeg_regime_labels IS
    'AEG-S2 (a) per-symbol daily regime 標籤 hypertable（V127；time col signal_ts，'
    '7d chunk / 30d compress segmentby=symbol / 1095d retention）。PK (classifier_version,'
    'symbol,timeframe,signal_ts,run_id) — classifier_version 入 PK = immutability 軸'
    '（ADR-0047 rule 7：分類器 scoring 前固定；新版本寫新列、舊列可重現）。NOT 重用 V002 '
    'market.regime_snapshots（intraday/無版本，語義不相容，MIT BLOCKING FINDING）。'
    '10 feature 欄 REAL 允許 NULL（insufficient_context 列部分 feature 無法算；非 fail-closed '
    '資料值，分類結果由 main_regime + flag 承載）。';
COMMENT ON TABLE research.aeg_regime_transitions IS
    'AEG-S2 (a) regime 轉移事件 hypertable（V127；time col transition_ts，7d/30d/1095d）。'
    'PK (classifier_version,symbol,timeframe,transition_ts,run_id)。AEG-native daily-anchor，'
    '非 V002 intraday；首次給 regime_transitions 真實列。';

COMMENT ON COLUMN research.aeg_regime_labels.classifier_version IS
    'immutability 軸（PK 首欄）：凍結分類器版本字串（aeg_regime_v0.1.0）。bump 版本寫新列、'
    '舊 verdict 列 immutable。候選讀 WHERE classifier_version=<pinned> → 不能移 regime 邊界 '
    'fit 策略（ADR-0047 rule 7）。';
COMMENT ON COLUMN research.aeg_regime_labels.feature_rules_digest IS
    'sha256 of frozen feature/threshold 定義。runner 若 running code digest ≠ classifier_version '
    '註冊值 → 拒寫（防凍結版本字串下 silent feature/threshold drift，MIT §a.3）。';
COMMENT ON COLUMN research.aeg_regime_labels.market_anchor_regime IS
    'BTCUSDT 同 signal_ts 的 main_regime（denormalized 免消費者 self-join）。允許 NULL：'
    'BTC anchor 列本身 / anchor 缺失時。';

COMMIT;

-- ============================================================
-- §F Guard C 後驗（COMMIT 後獨立檢查；不在 transaction 內，純讀驗證）
-- 【硬繼承 V125 §E 教訓】§F 在顯式 COMMIT 之後執行（autocommit 區）。compression_settings
--   反射用 segmentby_column_index IS NOT NULL（TSDB 2.26.1 無 .segmentby 欄；V125 §E 初版
--   用 .segmentby 欄導致 deploy crash-loop）。
-- per V125 Guard C pattern：
--   - 2 表全存在
--   - 2 表確為 hypertable（chunk = 7d）
--   - 2 表 compress_segmentby = 'symbol'（C-5）
--   - 2 表各有 1 retention job（drop_after = 1095 days）
--   - 關鍵 hot-path index 到位
-- 任一不符 → RAISE EXCEPTION（fail-loud）。
-- ============================================================
DO $$
DECLARE
    v_count          INTEGER;
    v_chunk          BIGINT;
    v_comp_enabled   BOOLEAN;
    v_symbol_segby   BOOLEAN;
    v_drop           INTERVAL;
    v_tbl            TEXT;
    v_timecol        TEXT;
    r RECORD;
BEGIN
    -- 2 表全存在
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables
    WHERE table_schema='research'
      AND table_name IN ('aeg_regime_labels', 'aeg_regime_transitions');
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'V127 Guard C FAIL: research aeg 2 表預期，實得 %.', v_count;
    END IF;

    -- 2 表逐一驗 hypertable chunk=7d + segmentby=symbol + retention=1095d
    FOR r IN
        SELECT * FROM (VALUES
            ('aeg_regime_labels', 'signal_ts'),
            ('aeg_regime_transitions', 'transition_ts')
        ) AS t(tbl, timecol)
    LOOP
        v_tbl := r.tbl; v_timecol := r.timecol;

        -- hypertable + chunk = 7d（TIMESTAMPTZ → time_interval 為 INTERVAL）
        SELECT EXTRACT(EPOCH FROM time_interval)::BIGINT INTO v_chunk
        FROM timescaledb_information.dimensions
        WHERE hypertable_schema='research' AND hypertable_name=v_tbl AND column_name=v_timecol;
        IF v_chunk IS NULL THEN
            RAISE EXCEPTION 'V127 Guard C FAIL: research.% 未建 hypertable on %.', v_tbl, v_timecol;
        END IF;
        IF v_chunk <> 604800 THEN  -- 7 days in seconds
            RAISE EXCEPTION 'V127 Guard C FAIL: research.% chunk = % sec（預期 604800 = 7d）.', v_tbl, v_chunk;
        END IF;

        -- C-5：compress_segmentby = symbol（segmentby_column_index IS NOT NULL；TSDB 2.26.1 反射）
        SELECT EXISTS (
            SELECT 1 FROM timescaledb_information.compression_settings
            WHERE hypertable_schema='research' AND hypertable_name=v_tbl
        ) INTO v_comp_enabled;
        IF NOT v_comp_enabled THEN
            RAISE EXCEPTION 'V127 Guard C FAIL: research.% compression 未啟用.', v_tbl;
        END IF;
        SELECT EXISTS (
            SELECT 1 FROM timescaledb_information.compression_settings
            WHERE hypertable_schema='research' AND hypertable_name=v_tbl
              AND attname='symbol' AND segmentby_column_index IS NOT NULL
        ) INTO v_symbol_segby;
        IF NOT v_symbol_segby THEN
            RAISE EXCEPTION
                'V127 Guard C FAIL: research.% compress_segmentby 不含 symbol（預期 symbol 為 segmentby 欄，C-5 低基數）.',
                v_tbl;
        END IF;

        -- retention = 1095d，恰好 1 個 job
        SELECT COUNT(*) INTO v_count
        FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_schema='research' AND hypertable_name=v_tbl;
        IF v_count <> 1 THEN
            RAISE EXCEPTION 'V127 Guard C FAIL: research.% retention job 數 = %（預期恰好 1）.', v_tbl, v_count;
        END IF;
        SELECT (config->>'drop_after')::INTERVAL INTO v_drop
        FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_schema='research' AND hypertable_name=v_tbl
        LIMIT 1;
        IF v_drop IS DISTINCT FROM INTERVAL '1095 days' THEN
            RAISE EXCEPTION 'V127 Guard C FAIL: research.% retention drop_after = %（預期 1095 days）.', v_tbl, v_drop;
        END IF;
    END LOOP;

    -- 關鍵 hot-path index 到位（抽驗 3 條 surface index）
    SELECT COUNT(*) INTO v_count
    FROM pg_indexes
    WHERE schemaname='research'
      AND indexname IN (
          'idx_aeg_regime_labels_ver_sym_tf_ts',
          'idx_aeg_regime_labels_ver_ts_regime',
          'idx_aeg_regime_transitions_ver_sym_ts'
      );
    IF v_count <> 3 THEN
        RAISE EXCEPTION 'V127 Guard C FAIL: 關鍵 hot-path index 預期 3，實得 %.', v_count;
    END IF;

    RAISE NOTICE 'V127: all guards PASS —';
    RAISE NOTICE '  - research schema + 2 表（aeg_regime_labels + aeg_regime_transitions，皆 hypertable）';
    RAISE NOTICE '  - 2 hypertable: chunk=7d / compress=30d segmentby=symbol(C-5) / retention=1095d';
    RAISE NOTICE '  - PK 含 classifier_version（immutability 軸）；main_regime 6-enum CHECK';
    RAISE NOTICE '  - 10 feature 欄 REAL（MIT §a.2）；overlay_flags JSONB';
    RAISE NOTICE '  - hot-path index 到位';
    RAISE NOTICE '';
    RAISE NOTICE 'Next（本 migration 範圍外，per MIT design report component (a)）:';
    RAISE NOTICE '  - regime runner: 分類器 code + leak-free PIT feature + feature_lineage.parquet';
    RAISE NOTICE '  - 修 full-sample vol-tercile cross-section leak（data_loader.py:300 不可繼承）';
    RAISE NOTICE '  - check_aeg_regime_labels_freshness() healthcheck（抓 producer 從沒跑 silent-dead）';
END $$;

-- ============================================================
-- §G ROLLBACK（手動執行；非 sqlx down migration — 本專案 sqlx forward-only）
-- per V125 §F rollback pattern：
--   1. DROP 新 research.aeg_* 表用 RESTRICT（非 CASCADE）——若有依賴物件 DROP 會 fail-loud。
--   2. 若任何 label/transition 表有 accepted 生產 row → **不靜默刪**：可改標 run status
--      （透過 research.alpha_history_ingest_runs，若 run lineage 已登）。
--   3. sqlx checksum drift → 用既有 repair_migration_checksum 工作流（不手改 _sqlx_migrations）。
--
-- 完整 teardown（僅當確認無 accepted row；DROP RESTRICT 防連鎖）:
--   DROP TABLE IF EXISTS research.aeg_regime_transitions RESTRICT;
--   DROP TABLE IF EXISTS research.aeg_regime_labels      RESTRICT;
--   -- 不 DROP SCHEMA research（V125 alpha_* 6 表仍在）。
-- ============================================================
