-- ============================================================
-- V129: learning.lease_ipc_divergence_snapshot
--       — SM Option 2 收斂 soak 可觀測性（P5-SM-OPTION2 B-3）的 PG 投影表
--
--   SM Option 2 step-(i) soak 的「可觀測性橋接」。Python comparator
--   （governance_divergence.py 的 in-memory `_COUNTERS`：total/matches/divergences）
--   是 API worker process-local 記憶體，獨立 passive_wait_healthcheck cron process
--   讀不到（既非 HTTP、又不落 PG）。本表是 comparator 計數器的 best-effort PG snapshot：
--   API process 內一個 fail-soft flusher 週期 UPSERT 此表，cron healthcheck 以
--   SQL-cursor 模式（與既有 checks_*.py 同 pattern）讀此表 + freshness 判 soak gate。
--
-- 動機 / Motivation:
--   PA 設計 `2026-06-03--p5_sm_soak_observability_redesign.md` §3 B-3（recommend）：
--   不走 HTTP（不污染 /healthz dependency-free 契約、不動 CSRF 豁免硬編碼清單、
--   不新增無 auth 端點），改 counter → PG snapshot → SQL healthcheck。**完全不碰
--   HTTP / CSRF / auth 攻擊面**（最不擴大攻擊面選項）。
--
--   ⚠️ 本 migration 僅建 1 表。flusher（Python）/ EQUIV sampler / SQL healthcheck
--   全不在本 migration 範圍（獨立 IMPL 任務 E1-B/C/D）。
--
-- SOURCE: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--p5_sm_soak_observability_redesign.md
--   §3 B-3 機制設計 / §4 E1-A 任務 / §5 R2 stale snapshot 偽 pass 緩解（freshness gate）。
--   Template: sql/migrations/V054__lease_transitions_audit_writer.sql（Guard A + Guard C
--     CREATE INDEX IF NOT EXISTS + CHECK 條件式加既有 pattern）。
--
-- 範圍 / Scope (V129):
--   §A CREATE SCHEMA IF NOT EXISTS learning（idempotent；早於 V054 已建，第二次 no-op）
--   §B CREATE TABLE IF NOT EXISTS learning.lease_ipc_divergence_snapshot + Guard A
--      （既有表缺必要欄 → RAISE）
--   §C 條件式 CHECK 約束（counter 非負；total >= matches + divergences 不變式）
--   §D Guard C：load-bearing index（snapshot_key UNIQUE — UPSERT 目標）
--   §E ROLLBACK 註解
--
-- 設計決策:
--   【非 hypertable — 是「current-value snapshot」非 time-series】
--     對比 V054 lease_transitions（append-only 事件流 → hypertable）：本表是
--     comparator 計數器的*當前值* snapshot，每個 snapshot_key 最多 1 row（UPSERT
--     覆蓋）。soak gate 讀的是「現在 divergences==0 且 total>=N 且夠新鮮」，不需要
--     歷史保留 / chunk rotate / compression。故不轉 hypertable、不需 Timescale。
--     這也讓本 migration 在無 Timescale 的 PG 上同樣可 apply（不像 V125/V127 有
--     Timescale preguard），降低部署風險。
--
--   【snapshot_key 單一 row 設計 = UPSERT 目標】
--     PK = snapshot_key TEXT（預設值 'singleton'）。flusher 永遠 UPSERT 同一個
--     'singleton' key → 表至多 1 row（不無界增長）。保留 TEXT key 而非寫死單 row
--     是為了：若未來 multi-worker 各自 flush 需區分（worker pid / lease-axis），可
--     用不同 key 而不改 schema。當前 flusher 只寫 'singleton'（leader-elected 單一
--     writer，見 E1-B）。
--
--   【freshness 欄 = updated_at TIMESTAMPTZ（DB-side now()）+ flusher_ts_ms（flusher 端 epoch ms）】
--     為什麼兩個時間：
--       - updated_at（DB now()）：healthcheck 判「snapshot 是否夠新鮮」的權威。**這是
--         R2 stale-snapshot 偽 pass 緩解的核心**——flusher 若死，updated_at 凍結，
--         healthcheck freshness gate 偵測 stale 並 FAIL（不可把「讀不到/凍結」當綠燈）。
--       - flusher_ts_ms（flusher 端 time.time()*1000）：診斷用，比對 DB now() 與 flusher
--         clock skew；非 gate 權威（避免 flusher clock drift 影響 gate 判定）。
--
--   【counter 欄 BIGINT NOT NULL — 對齊 in-memory _COUNTERS 語義】
--     total / matches / divergences 皆 BIGINT NOT NULL DEFAULT 0（單調累加；soak 視窗
--     遠低於 BIGINT 上限）。CHECK 約束釘住 comparator 不變式（見 §C）：三者非負 +
--     total >= matches + divergences（每筆比對恰計入 total，且要嘛 match 要嘛 divergence；
--     no-opinion 計入 matches，見 governance_divergence.record_divergence）。
--
--   【flag_enabled BOOLEAN — soak gate 前置】
--     記錄 flush 當下 OPENCLAW_LEASE_PYTHON_IPC_ENABLED 是否 == "1"。soak gate
--     要求 flag_enabled=true（flag-OFF = legacy local SM，comparator 不 fire，
--     counter 不該被當綠燈）。healthcheck 讀此欄判前置（G-1：flag-OFF → 非 PASS）。
--
--   【冪等 double-apply 全 no-op】(per CLAUDE「applying twice」+ V054/V114/V127 教訓)
--     - CREATE SCHEMA / TABLE IF [NOT] EXISTS → 第二次 no-op（Guard A 已驗 shape）
--     - 條件式 ADD CONSTRAINT（pg_constraint 探測存在 → skip）→ 第二次 no-op
--     - CREATE [UNIQUE] INDEX IF NOT EXISTS → 第二次 no-op（Guard C 已驗 shape）
--     - COMMENT ON → 可重跑
--
-- Idempotency 重跑兩次必 PASS（per memory feedback_v_migration_pg_dry_run
--   double-apply mandatory）。本 migration 須 Linux PG empirical 雙跑 dry-run 才能
--   sign-off（Mac mock PG 抓不到 PG runtime semantic）。本表無 Timescale，雙跑風險
--   低於 V125/V127，但 ADD CONSTRAINT 條件式探測 + UNIQUE index 仍須 Linux 實證。
--
-- Guard（per V054 pattern，fail-closed + idempotent）:
--   Guard A — CREATE TABLE IF NOT EXISTS 前驗既有表必要欄完整（缺 → RAISE）
--   Guard B — N/A（無 column type ALTER；只 NEW table CREATE + 條件式 CHECK）
--   Guard C — 建後驗 UNIQUE index 到位（UPSERT ON CONFLICT 目標）
--
-- E2 review checklist:
--   1. Guard A 對必要欄完整性（重跑 shape drift → RAISE）
--   2. 非 hypertable 是有意決策（current-value snapshot 非 time-series；見上）
--   3. CHECK：counter 非負 + total >= matches + divergences（comparator 不變式）
--   4. UNIQUE(snapshot_key) 是 UPSERT 目標（flusher ON CONFLICT (snapshot_key) DO UPDATE）
--   5. freshness 權威 = updated_at（DB now()）；flusher_ts_ms 僅診斷
--   6. flag_enabled 欄供 healthcheck 判 soak gate 前置（flag-OFF 非 PASS）
--   7. 冪等：ADD CONSTRAINT 條件式探測 + index IF NOT EXISTS
--
-- 硬邊界:
--   - 不碰 V054 learning.lease_transitions（P-LIVE 信號讀現有表，read-only；本表 disjoint）。
--   - 不改 max_retries / live_execution_allowed / execution_authority / system_mode（無關）。
--   - 本表純觀測投影；step-(iv) cleanup 會連同 comparator + dual-write mirror 一起退役
--     （soak 0 divergence 後）。屆時可 DROP 本表（見 §E）。
--
-- migration latest: V127 → V129（Linux _sqlx_migrations head 預期含 V125/V126/V127；
--   V116-124 held 給 M5/M7/M12/M13 + funding_arb V3；前一序號讓給並行 session 的
--   listing-capture collector（sqlx 不容同號），本 soak 表 renumber 至 V129；breadth
--   ladder 是 artifact-only 不佔號，故 V129 collision-safe）。
-- ============================================================

-- 全 migration 包在單一 transaction（原子 all-or-nothing；對齊 V054 critical-section
-- + V127 pattern）。本表無 Timescale → 無「Guard C 須在 COMMIT 後（autocommit）反射」
-- 需求（V125/V127 §F 那是 TSDB compression_settings 反射特性），全部 DDL + Guard
-- 皆可在同一 transaction 內安全執行。
BEGIN;

-- ============================================================
-- §A CREATE SCHEMA IF NOT EXISTS learning (idempotent)
-- learning namespace 早於 V054 已建；第二次 apply no-op。
-- ============================================================
CREATE SCHEMA IF NOT EXISTS learning;

-- ============================================================
-- §B learning.lease_ipc_divergence_snapshot — comparator 計數器 PG 投影
-- ============================================================

-- Guard A: 既有表必要欄完整性（缺 ≥1 → RAISE）
-- 為什麼 fail-closed：若舊版 schema drift（缺 freshness 欄或 counter 欄），healthcheck
--   freshness gate 會失效（讀不到 updated_at → 可能被誤當綠燈），違反 R2 緩解。缺欄
--   一律 RAISE 強制 operator 解 drift 後重跑（不靜默 ALTER）。
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'lease_ipc_divergence_snapshot'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'snapshot_key', 'total', 'matches', 'divergences',
            'flag_enabled', 'flusher_ts_ms', 'updated_at', 'created_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning' AND table_name = 'lease_ipc_divergence_snapshot'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V129 Guard A FAIL: learning.lease_ipc_divergence_snapshot exists but missing '
                'required columns: %. 解決 legacy schema drift（DROP + re-apply 或 ALTER ADD）'
                '後重跑 V129.', v_missing;
        END IF;
        RAISE NOTICE 'V129 Guard A: learning.lease_ipc_divergence_snapshot already present with all required columns';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.lease_ipc_divergence_snapshot (
    -- snapshot_key：UPSERT 目標 key；flusher 永遠寫 'singleton' → 表至多 1 row。
    -- 保留 TEXT key 供未來 multi-writer 區分（當前單一 leader-elected writer）。
    snapshot_key   TEXT        NOT NULL DEFAULT 'singleton',
    -- comparator 計數器快照（對齊 governance_divergence._COUNTERS 三鍵）。
    total          BIGINT      NOT NULL DEFAULT 0,
    matches        BIGINT      NOT NULL DEFAULT 0,
    divergences    BIGINT      NOT NULL DEFAULT 0,
    -- flush 當下 OPENCLAW_LEASE_PYTHON_IPC_ENABLED 是否 == "1"（soak gate 前置）。
    flag_enabled   BOOLEAN     NOT NULL DEFAULT FALSE,
    -- flusher 端 epoch ms（time.time()*1000）；診斷用（比對 clock skew），非 gate 權威。
    flusher_ts_ms  BIGINT      NOT NULL,
    -- updated_at：DB-side now()；**healthcheck freshness gate 的權威**（flusher 死 →
    --   凍結 → freshness gate FAIL，R2 stale 偽 pass 緩解核心）。
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_key)
);

-- ============================================================
-- §C 條件式 CHECK 約束（counter 不變式；重跑 pg_constraint 探測 skip）
-- 釘住 comparator record_divergence 的不變式不被未來 schema 重構打破：
--   - 三 counter 非負（單調累加，永不為負）
--   - total >= matches + divergences（每筆比對恰計入 total 一次，且分類為 match 或
--     divergence；no-opinion 計入 matches。故 matches + divergences == total，用 >=
--     寬鬆守衛允許 flusher 讀 counter 與寫 PG 之間 comparator 又累加的瞬時 skew）。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lease_ipc_div_snapshot_nonneg'
          AND conrelid = 'learning.lease_ipc_divergence_snapshot'::regclass
    ) THEN
        ALTER TABLE learning.lease_ipc_divergence_snapshot
            ADD CONSTRAINT chk_lease_ipc_div_snapshot_nonneg
            CHECK (total >= 0 AND matches >= 0 AND divergences >= 0);
        RAISE NOTICE 'V129: added CHECK chk_lease_ipc_div_snapshot_nonneg (counters non-negative)';
    ELSE
        RAISE NOTICE 'V129: chk_lease_ipc_div_snapshot_nonneg already present; skipping';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lease_ipc_div_snapshot_total_ge'
          AND conrelid = 'learning.lease_ipc_divergence_snapshot'::regclass
    ) THEN
        ALTER TABLE learning.lease_ipc_divergence_snapshot
            ADD CONSTRAINT chk_lease_ipc_div_snapshot_total_ge
            CHECK (total >= matches + divergences);
        RAISE NOTICE 'V129: added CHECK chk_lease_ipc_div_snapshot_total_ge (total >= matches + divergences)';
    ELSE
        RAISE NOTICE 'V129: chk_lease_ipc_div_snapshot_total_ge already present; skipping';
    END IF;
END $$;

-- ============================================================
-- §D Guard C: load-bearing index（UPSERT ON CONFLICT 目標）
-- PK(snapshot_key) 已隱含 UNIQUE；額外顯式驗 PK 到位（new-table index 不會
-- pre-exist 為不同定義，故無需 pg_get_indexdef compare）。
-- ============================================================
DO $$
DECLARE v_has_pk BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'learning.lease_ipc_divergence_snapshot'::regclass
          AND contype = 'p'
    ) INTO v_has_pk;
    IF NOT v_has_pk THEN
        RAISE EXCEPTION
            'V129 Guard C FAIL: learning.lease_ipc_divergence_snapshot 缺 PRIMARY KEY '
            '(snapshot_key) — UPSERT ON CONFLICT 目標必須存在.';
    END IF;
    RAISE NOTICE 'V129 Guard C: PRIMARY KEY(snapshot_key) present (UPSERT target OK)';
END $$;

-- ============================================================
-- §COMMENT 語義文檔（idempotent: COMMENT ON 可重跑）
-- ============================================================
COMMENT ON TABLE learning.lease_ipc_divergence_snapshot IS
    'SM Option 2 soak 可觀測性（P5-SM-OPTION2 B-3，V129）：governance_divergence.py '
    'in-memory comparator 計數器（total/matches/divergences）的 best-effort PG 投影。'
    'API process 內 fail-soft flusher 週期 UPSERT（snapshot_key=''singleton''，至多 1 row）；'
    'passive_wait_healthcheck cron 以 SQL-cursor 讀此表 + updated_at freshness 判 soak '
    'gate（flag_enabled AND divergences==0 AND total>=N AND fresh）。非 hypertable（current-'
    'value snapshot 非 time-series）。step-(iv) cleanup 連同 comparator 退役後可 DROP。';
COMMENT ON COLUMN learning.lease_ipc_divergence_snapshot.updated_at IS
    'DB-side now()；healthcheck freshness gate 的權威。flusher 死 → 凍結 → freshness '
    'gate FAIL（R2 stale-snapshot 偽 pass 緩解核心；不可把讀不到/凍結當綠燈）。';
COMMENT ON COLUMN learning.lease_ipc_divergence_snapshot.flag_enabled IS
    'flush 當下 OPENCLAW_LEASE_PYTHON_IPC_ENABLED == "1"。soak gate 要求 true（flag-OFF '
    '= legacy local SM，comparator 不 fire，counter 不該被當綠燈）。';
COMMENT ON COLUMN learning.lease_ipc_divergence_snapshot.flusher_ts_ms IS
    'flusher 端 epoch ms（time.time()*1000）；診斷用（比對 DB now() clock skew），'
    '非 gate 權威（避 flusher clock drift 影響 gate）。';

COMMIT;

-- ============================================================
-- §E ROLLBACK（手動執行；非 sqlx down migration — 本專案 sqlx forward-only）
-- per V054/V127 rollback pattern：
--   1. 本表純觀測投影，無下游 FK 依賴 → DROP RESTRICT 安全（若有依賴會 fail-loud）。
--   2. step-(iv) cleanup（soak 0 divergence 後，comparator + dual-write mirror 退役）
--      時連同 DROP 本表。
--   3. sqlx checksum drift → 用既有 repair_migration_checksum 工作流（不手改 _sqlx_migrations）。
--
-- 完整 teardown:
--   DROP TABLE IF EXISTS learning.lease_ipc_divergence_snapshot RESTRICT;
--   -- 不 DROP SCHEMA learning（lease_transitions 等大量表仍在）。
-- ============================================================
