-- V126__schema_hygiene_cleanup.sql
--
-- MODULE_NOTE:
--   模塊用途：schema hygiene 清理 — drop 已死的事故備份表、空 legacy 表、
--     以及 trading.decision_context_snapshots 上一組無依賴的死欄位。
--     來源 = CC + MIT 已 vet 的校正方案（P0-EDGE-1 周邊 hygiene；
--     編號註記見 TODO.md「v92 V### 對帳」：SQL head 為 V115，AEG storage
--     design 佔 V125 以保留 V116-V124 規劃槽，本 DB hygiene 清理排 V126）。
--   主要區塊：
--     Packet 1 — drop 4 個 2026-04-14 FA-PHANTOM-1 事故備份表（故意非空）。
--     Packet 2 — drop 6 個空 legacy 表（V005 rename 遺留）。
--     Packet 3 — drop 7 個乾淨死欄位 on trading.decision_context_snapshots。
--   依賴：無新依賴；只移除既有死物件。
--   硬邊界：
--     - 全 destructive drop 一律 RESTRICT（非 CASCADE）+ IF EXISTS（冪等）。
--     - 任何意外殘留依賴 / 非預期非空 → fail-loud（RAISE EXCEPTION），
--       絕不靜默 CASCADE 吞噬。
--     - 不觸碰任何 active table / view，不改 hard boundary
--       （max_retries / live_execution_allowed / execution_authority /
--       system_mode）。
--     - 不創新物件、不改 schema 形狀（純回收）。
--
-- Ticket: P0-EDGE-1 周邊 schema hygiene（CC + MIT vet 後校正方案 Packet 1-3）
-- Guard 範式參考：V096__drop_dead_learning_tables.sql / V069（pg_depend 守衛）。
--
-- ============================================================
-- 事務控制（重要 — 與 runner 契約對齊）
-- ------------------------------------------------------------
--   auto-migration runner（rust/openclaw_engine/src/database/migrations.rs）
--   預設把每個 migration 包進 sqlx 事務，除非檔首字面為「-- no-transaction」。
--   本檔不走 no-transaction opt-out。最近且已成功套用的同類 migration
--   （V090 / V092 / V097 / V113 / V115）皆在 body 內顯式寫 BEGIN;...COMMIT;，
--   本檔沿用該既定慣例（與最新、同樣觸碰 hypertable 的 V115 對齊），
--   使整個清理為單一原子單位：任一 Guard RAISE → 整批回滾。
--   ⚠️ runner-tx 包裹與顯式 BEGIN/COMMIT 的交互 + hypertable DROP COLUMN
--   屬 PG runtime semantic，必須 Linux double-apply dry-run 實證
--   （Mac mock 抓不到）。
-- ============================================================

BEGIN;

-- ============================================================
-- Packet 1 — DROP 4 個 FA-PHANTOM-1 事故備份表
-- ------------------------------------------------------------
--   背景：2026-04-14 FA-PHANTOM-1 事故（on_tick.rs margin_util 忽略
--     leverage，全策略系統性誤觸 CloseAll；見記憶庫 project_fa_phantom_bug）
--     當時對 4 張交易表做了 snapshot 備份，表名後綴
--     `_damaged_20260414_130607`。皆為 plain table（非 hypertable），
--     audit 確認 0 production writer / 0 reader / 0 view 依賴
--     （grep 全集除本 migration 外 0 命中）。
--
--   ⚠️ 為什麼這裡【不】用 count(*)=0 guard（與 V096/V069 不同）：
--     這 4 張是事故證據備份表，【故意非空】（例如
--     trading.risk_verdicts_damaged_20260414_130607 ≈ 4,183,014 行 / 903MB）。
--     沿用 V096 的「非空即 fail」會把正常情況誤判成 guard 失敗。
--     因此本 packet 只保留 pg_depend dependents=0 guard
--     （drop 前 assert 無任何 view/rule 依賴），不檢查行數。
--
--   ⚠️ 部署前置（runbook 步驟，非 SQL 內）：DROP 前已對 4 表各做
--     `pg_dump -Fc` → gzip → NAS forensic 存證，並記錄 sha256 + 行數。
--     未來 auditor 看到「非空 destructive drop」不要誤判為 guard regression：
--     這是有意設計，證據已離線歸檔，dump 完成是 operator deploy gate。
--     dump checksum / 行數清單見本 PR 描述 / deploy runbook（不內嵌 SQL，
--     避免把 checksum 釘死在版本控制的 SQL 內隨時間 stale）。

-- Packet 1.1 — trading.risk_verdicts_damaged_20260414_130607
DO $$
DECLARE
    v_dependents BIGINT;
BEGIN
    IF to_regclass('trading.risk_verdicts_damaged_20260414_130607') IS NULL THEN
        RAISE NOTICE 'V126 P1.1: trading.risk_verdicts_damaged_20260414_130607 already absent';
        RETURN;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'trading.risk_verdicts_damaged_20260414_130607'::regclass
      AND dependent.oid <> 'trading.risk_verdicts_damaged_20260414_130607'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 1.1 FAIL: trading.risk_verdicts_damaged_20260414_130607 has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS trading.risk_verdicts_damaged_20260414_130607 RESTRICT;

-- Packet 1.2 — trading.fills_damaged_20260414_130607
DO $$
DECLARE
    v_dependents BIGINT;
BEGIN
    IF to_regclass('trading.fills_damaged_20260414_130607') IS NULL THEN
        RAISE NOTICE 'V126 P1.2: trading.fills_damaged_20260414_130607 already absent';
        RETURN;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'trading.fills_damaged_20260414_130607'::regclass
      AND dependent.oid <> 'trading.fills_damaged_20260414_130607'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 1.2 FAIL: trading.fills_damaged_20260414_130607 has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS trading.fills_damaged_20260414_130607 RESTRICT;

-- Packet 1.3 — trading.intents_damaged_20260414_130607
DO $$
DECLARE
    v_dependents BIGINT;
BEGIN
    IF to_regclass('trading.intents_damaged_20260414_130607') IS NULL THEN
        RAISE NOTICE 'V126 P1.3: trading.intents_damaged_20260414_130607 already absent';
        RETURN;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'trading.intents_damaged_20260414_130607'::regclass
      AND dependent.oid <> 'trading.intents_damaged_20260414_130607'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 1.3 FAIL: trading.intents_damaged_20260414_130607 has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS trading.intents_damaged_20260414_130607 RESTRICT;

-- Packet 1.4 — trading.orders_damaged_20260414_130607
DO $$
DECLARE
    v_dependents BIGINT;
BEGIN
    IF to_regclass('trading.orders_damaged_20260414_130607') IS NULL THEN
        RAISE NOTICE 'V126 P1.4: trading.orders_damaged_20260414_130607 already absent';
        RETURN;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'trading.orders_damaged_20260414_130607'::regclass
      AND dependent.oid <> 'trading.orders_damaged_20260414_130607'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 1.4 FAIL: trading.orders_damaged_20260414_130607 has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS trading.orders_damaged_20260414_130607 RESTRICT;

-- ============================================================
-- Packet 2 — DROP 6 個空 legacy 表
-- ------------------------------------------------------------
--   背景：V005__indexes_views.sql 在 schema 重構時把舊 public.* 表
--     RENAME 為 *_legacy（見 V005:313-353）。audit 確認 0 rows、
--     0 view 依賴、0 production reader/writer。
--   guard：完整守衛 = count(*)=0 + pg_depend dependents=0（與 V096 對齊）。
--     非空或有依賴 → RAISE fail-loud（這些表【應該】是空的；若非空代表
--     有非預期 writer，必須先查清而非盲 drop）。

-- Packet 2.1 — public.ai_cost_events_legacy
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('public.ai_cost_events_legacy') IS NULL THEN
        RAISE NOTICE 'V126 P2.1: public.ai_cost_events_legacy already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM public.ai_cost_events_legacy' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.1 FAIL: public.ai_cost_events_legacy is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'public.ai_cost_events_legacy'::regclass
      AND dependent.oid <> 'public.ai_cost_events_legacy'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.1 FAIL: public.ai_cost_events_legacy has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS public.ai_cost_events_legacy RESTRICT;

-- Packet 2.2 — public.market_tickers_legacy
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('public.market_tickers_legacy') IS NULL THEN
        RAISE NOTICE 'V126 P2.2: public.market_tickers_legacy already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM public.market_tickers_legacy' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.2 FAIL: public.market_tickers_legacy is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'public.market_tickers_legacy'::regclass
      AND dependent.oid <> 'public.market_tickers_legacy'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.2 FAIL: public.market_tickers_legacy has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS public.market_tickers_legacy RESTRICT;

-- Packet 2.3 — public.observer_verdicts_legacy
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('public.observer_verdicts_legacy') IS NULL THEN
        RAISE NOTICE 'V126 P2.3: public.observer_verdicts_legacy already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM public.observer_verdicts_legacy' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.3 FAIL: public.observer_verdicts_legacy is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'public.observer_verdicts_legacy'::regclass
      AND dependent.oid <> 'public.observer_verdicts_legacy'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.3 FAIL: public.observer_verdicts_legacy has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS public.observer_verdicts_legacy RESTRICT;

-- Packet 2.4 — public.order_events_legacy
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('public.order_events_legacy') IS NULL THEN
        RAISE NOTICE 'V126 P2.4: public.order_events_legacy already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM public.order_events_legacy' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.4 FAIL: public.order_events_legacy is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'public.order_events_legacy'::regclass
      AND dependent.oid <> 'public.order_events_legacy'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.4 FAIL: public.order_events_legacy has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS public.order_events_legacy RESTRICT;

-- Packet 2.5 — public.position_snapshots_legacy
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('public.position_snapshots_legacy') IS NULL THEN
        RAISE NOTICE 'V126 P2.5: public.position_snapshots_legacy already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM public.position_snapshots_legacy' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.5 FAIL: public.position_snapshots_legacy is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'public.position_snapshots_legacy'::regclass
      AND dependent.oid <> 'public.position_snapshots_legacy'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.5 FAIL: public.position_snapshots_legacy has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS public.position_snapshots_legacy RESTRICT;

-- Packet 2.6 — public.trade_executions_legacy
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('public.trade_executions_legacy') IS NULL THEN
        RAISE NOTICE 'V126 P2.6: public.trade_executions_legacy already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM public.trade_executions_legacy' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.6 FAIL: public.trade_executions_legacy is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'public.trade_executions_legacy'::regclass
      AND dependent.oid <> 'public.trade_executions_legacy'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V126 Packet 2.6 FAIL: public.trade_executions_legacy has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS public.trade_executions_legacy RESTRICT;

-- ============================================================
-- Packet 3 — DROP 7 個乾淨死欄位 on trading.decision_context_snapshots
-- ------------------------------------------------------------
--   背景：這 7 欄由 V017__edge_predictor_tables.sql:99-106 加入
--     （edge predictor C16 + R5）。CC 驗證 0 writer / 0 reader /
--     0 view 依賴。
--   ⚠️ CC BLOCKER（已遵守）：recent_sequences 不在此列 —— 它被
--     learning.scorer_training_features VIEW SELECT（V005:267
--     `c.recent_sequences,`），是 view-fronted，不可在此 drop。
--     recent_sequences + regime_1h 那組 view-fronted 欄留待延後 Packet 4。
--   ⚠️ 唯一 view（learning.scorer_training_features，V005:221-282）的
--     SELECT 白名單已逐欄核對：下列 7 欄皆【不】在該 view 內，故 column-level
--     pg_depend dependents 為 0（runtime guard 會再 assert 一次）。
--   ⚠️ 連帶物件：predicted_q50 上有部分索引 idx_dcs_predicted_q50
--     （V017:126-128）。DROP COLUMN 會自動移除「只依賴該欄」的索引
--     （column-owned internal dependency，非 RESTRICT-blocking），屬預期行為，
--     非 guard regression。
--   ⚠️ table 型別注意：decision_context_snapshots 現為 plain table
--     （MIT Linux dry-run 2026-06-02 實測：timescaledb_information.hypertables
--     無此表 → 非 hypertable；先前註記引 V003:96 稱其為 1-day-chunk hypertable
--     有誤）。plain table 無 compressed twin，DROP COLUMN trivially safe。
--     若未來該表轉 hypertable 並啟用 column-level compression，需重評
--     （見 V017:113 disagreed 的 TimescaleDB 2.x compression 註記）。
--     此項已由 Linux double-apply dry-run 覆核。
--   做法：ALTER TABLE ... DROP COLUMN IF EXISTS（逐欄，冪等；
--     第二次 apply 全 no-op）。

ALTER TABLE trading.decision_context_snapshots
    DROP COLUMN IF EXISTS predictor_decision,
    DROP COLUMN IF EXISTS shrinkage_decision,
    DROP COLUMN IF EXISTS predict_latency_us,
    DROP COLUMN IF EXISTS disagreed,
    DROP COLUMN IF EXISTS predicted_q10,
    DROP COLUMN IF EXISTS predicted_q50,
    DROP COLUMN IF EXISTS predicted_q90;

COMMIT;
