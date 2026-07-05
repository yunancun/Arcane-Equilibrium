-- ============================================================
-- V149: V142/V143 compression/retention policy — timescaledb extension guard
--       retrofit（冷審計 R2 殘餘 MIT[LOW]，V006 已知缺陷複製修正）
--
-- 目的 / Motivation:
--   V142（market.trades / market.ob_top）與 V143（market.l1_events）的
--   §C 壓縮策略（ALTER TABLE ... SET (timescaledb.compress...)、
--   add_compression_policy）與 §D 保留策略（add_retention_policy）三類語句
--   為無條件執行 —— 未包在 hypertable 建立所用的
--   `IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='timescaledb')` 守衛內。
--   在無 timescaledb 的 PG（fresh bootstrap / 異環境 / CI schema_contract_test）
--   套 V142/V143 時，會在 timescaledb.compress reloption 或 add_*_policy 函數處
--   RAISE（未知 reloption / 函數不存在），整條遷移鏈斷。
--   （V006 有同缺陷；V148 只補 Guard A 必要欄反射，未動 compression/retention guard。）
--
--   為什麼須新開檔而非原地改 V142/V143：兩檔已 applied，原地改 body 破
--   _sqlx_migrations checksum（硬約束不改已 applied schema；memory P0 sqlx hash
--   drift SOP）。故循 V148 先例出 retrofit migration，把三表的 compression/retention
--   語句在有 timescaledb 時「冪等 re-assert」，無 timescaledb 時整段 NOTICE-skip。
--
-- 範圍 / Scope (V149):
--   §A Guard A — 三表存在檢查（缺表=斷鏈，RAISE）。
--   §B extension-guarded compression + retention re-assert（market.trades /
--       market.ob_top / market.l1_events），全包在單一
--       `IF EXISTS(... timescaledb ...)` DO-block 內。
--   無新表 / 無新欄；純把既有策略語句包進 extension guard 並冪等重申。
--
-- 冪等設計:
--   ALTER TABLE ... SET(timescaledb.compress...)：重設同值 = no-op reassert。
--   add_compression_policy / add_retention_policy：if_not_exists => TRUE ⇒ 已存在
--   則 no-op。故任意次重跑（含有/無 timescaledb 兩態）rc=0。
--   無 timescaledb 之空 PG：整個 §B DO-block 走 ELSE 分支 RAISE NOTICE 跳過，rc=0。
--
-- 編號決策:
--   本 worktree base=e29adde76：repo sql/migrations/ 最大版本號為 V148
--   （V147__decision_features_label_source / V148__recorder_promotions_guard_retrofit
--   皆已就位為修復波部署檔）。next-free = V149。
--   sqlx forward-only：本 file apply 時 V142/143 必已就位（缺表=真斷鏈，§A RAISE）。
--   Linux PG dry-run + apply 由 conductor 部署側執行（同 V147/V148），Mac 側不 apply、
--   不改 sqlx head（Mac sandbox 無 timescaledb，無法驗 reloption 語義）。
--
-- 硬邊界:
--   - 不 CREATE / DROP 任何表；不改欄；不碰 max_retries / live_execution_allowed /
--     execution_authority / system_mode。
--   - 純把既有 V142/V143 策略語句包進 extension guard 並冪等重申。
-- ============================================================

-- ==========================================================
-- §A Guard A — 三表存在檢查（缺表 = V142/V143 未套，斷鏈 RAISE）
-- ==========================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    SELECT array_agg(t) INTO v_missing
    FROM unnest(ARRAY[
        'market.trades', 'market.ob_top', 'market.l1_events'
    ]) AS t
    WHERE to_regclass(t) IS NULL;
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V149 Guard A FAIL: recorder tables missing: %. '
            'V142/V143 were never applied (broken migration chain). '
            'Re-apply V142/V143 before V149.', v_missing;
    END IF;
    RAISE NOTICE 'V149 Guard A PASS: recorder tables (trades/ob_top/l1_events) present.';
END $$;

-- ==========================================================
-- §B extension-guarded compression + retention re-assert
--   為什麼 fail-open（無 timescaledb 時整段跳過）：壓縮/保留策略是 timescaledb
--   專屬能力，無此 extension 的環境（fresh bootstrap / CI / 異環境）不需要、也
--   無法建立這些策略；此處 skip 是「該環境本就不套此策略」的正確語義，非降級。
--   有 timescaledb 時則冪等重申（if_not_exists 保冪等），修補 V142/V143 原檔在
--   無 guard 下對無-extension 環境的斷鏈風險。
-- ==========================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        -- market.trades（V142 §C/§D：壓縮 7d、保留 45d）
        ALTER TABLE market.trades
            SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
        PERFORM add_compression_policy('market.trades', INTERVAL '7 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('market.trades', INTERVAL '45 days', if_not_exists => TRUE);

        -- market.ob_top（V142 §C/§D：壓縮 7d、保留 30d）
        ALTER TABLE market.ob_top
            SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
        PERFORM add_compression_policy('market.ob_top', INTERVAL '7 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('market.ob_top', INTERVAL '30 days', if_not_exists => TRUE);

        -- market.l1_events（V143 §C/§D：壓縮 7d、保留 21d）
        ALTER TABLE market.l1_events
            SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
        PERFORM add_compression_policy('market.l1_events', INTERVAL '7 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('market.l1_events', INTERVAL '21 days', if_not_exists => TRUE);

        RAISE NOTICE 'V149: timescaledb present — compression/retention policies re-asserted (idempotent) for 3 recorder tables.';
    ELSE
        RAISE NOTICE 'V149: timescaledb absent — compression/retention re-assert skipped (NOTICE-skip), rc=0. This is correct for non-timescaledb environments.';
    END IF;
END $$;

-- ============================================================
-- 驗證 / Verification (double-apply idempotency)
-- ============================================================
-- 有 timescaledb：重跑 → ALTER SET 同值 no-op、add_*_policy if_not_exists no-op，
--   每跑 §A NOTICE PASS + §B NOTICE re-asserted，rc=0 冪等。
-- 無 timescaledb（空 PG / CI schema_contract_test）：§A PASS（表若已建）、§B 走 ELSE
--   NOTICE-skip，rc=0 —— 修補了 V142/V143 在無 extension 下的斷鏈。
-- ROLLBACK：§B ALTER TABLE ... SET 為 reloption，可於獨立事務 RESET；本 migration
--   不新建物件，無表可 DROP。
--   驗證查詢（有 timescaledb 時預期 3 行）：
--   SELECT hypertable_name FROM timescaledb_information.compression_settings
--     WHERE hypertable_name IN ('trades','ob_top','l1_events')
--     GROUP BY hypertable_name ORDER BY hypertable_name;
-- 註：Mac 無 timescaledb，須 Linux PG dry-run（CLAUDE Data/Migrations 規範）。
-- ============================================================
