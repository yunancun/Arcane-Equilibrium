-- ============================================================
-- V137: learning.lease_ipc_soak_events
--       — P5-SM-OPTION2 step-(i) soak 監測重設計（第二輪）的 epoch/flag 事件帳本
--
--   SM Option 2 step-(i) soak 的「連續性記帳」（G2）+「斷點偵測」（G3）。V129
--   （lease_ipc_divergence_snapshot）是 current-value UPSERT（無歷史）；comparator /
--   canary 計數器是 API worker process-local 記憶體（restart 歸零）。本表是 append-only
--   小事件帳本：flusher leader 在 epoch 邊界（API 重啟）/ flag 變遷 / canary 失敗連段 /
--   counter regression 時寫一筆，讓獨立 cron healthcheck `[82]` 能以 SQL 重建「連續
--   有效 soak 窗」並跨 epoch 求和累計 probe 數。
--
-- 動機 / Motivation:
--   PA 設計 `2026-06-10--p5sm_soak_observability_redesign.md` §3.1（V### NEW 表）+
--   §4 gate S3/S4 + PM 時間參數定案 `2026-06-10--p5sm_soak_cadence_decision.md`
--   （cadence 300s→120s）。前兩次 soak（06-03 / 06-07）因 flag 一次性 operator-env
--   + restart 計數歸零而無聲終結；本表讓「soak 中斷」「epoch 切換」「flag 變遷」
--   全部留下 append-only 痕跡。
--
--   ⚠️ 本 migration 僅建 1 表 + 1 index。flusher 擴充（E1-B）/ canary（E1-C）/
--   `[82]` healthcheck（E1-D）全不在本 migration 範圍。
--
-- SOURCE: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--p5sm_soak_observability_redesign.md
--   §3.1（schema 草案）/ §3.4（restart 不終結 soak）/ §4（S3/S4 證據源）。
--   Template: sql/migrations/V129__lease_ipc_divergence_snapshot.sql（Guard A + 條件式
--     CHECK + COMMENT pattern；同 step-(iv) 退役組）。
--
-- 範圍 / Scope (V137):
--   §A CREATE SCHEMA IF NOT EXISTS learning（idempotent；V054 已建，第二次 no-op）
--   §B CREATE TABLE IF NOT EXISTS learning.lease_ipc_soak_events + Guard A
--      （既有表缺必要欄 → RAISE）
--   §C 條件式 CHECK 約束（event_type 白名單；pg_constraint 探測 skip）
--   §D Guard C：created_at index（`[82]` 窗查詢路徑）
--   §E ROLLBACK 註解
--
-- 設計決策:
--   【append-only 事件流，但非 hypertable】
--     低速表：soak 兩週 < ~100 row（epoch 邊界 + flag 變遷 + 罕見異常事件），無
--     chunk rotate / compression 需求。對比 V054 lease_transitions（高頻事件流 →
--     hypertable）。無 Timescale 依賴 → 在無 Timescale 的 PG 同樣可 apply。
--
--   【event_type 白名單 —— 比 PA §3.1 草案多 2 型（E1 最小安全偏差，報告已標註）】
--     PA 草案 4 型：flusher_start / epoch_rollover / flag_change / canary_leader_start。
--     E1 增 2 型，理由 = 否則 S3/S4 兩個 gate 條件在 PG 結構性不可機器判定：
--       - 'canary_fail_streak'：S3「無 ≥15min 失敗連段」—— V129 'canary' row 只有
--         累計 attempts/ok/fail，散發失敗與連續失敗不可區分；canary 在程內偵測連段
--         跨 15min 時 breach 計數 +1，flusher 觀測到增量即寫本事件。`[82]` 看窗內
--         有無此事件即可判 S3 連段條件。
--       - 'counter_regression'：S4「0 次 counter regression 無對應 epoch_rollover」——
--         flusher 程內觀測到計數器倒退（單調不變式破壞）時寫本事件留痕；`[82]` 另以
--         「當前 row total < 本 epoch 內事件快照 max」做無狀態交叉偵測。
--
--   【prev_* 欄語義 = 「事件當下的計數器快照」】
--     epoch_rollover：前一 epoch 的終值（被 UPSERT 覆寫前搶救，損失 ≤30s）。
--     其他事件型：事件 emit 當下的本 epoch 計數快照（供 `[82]` 做 epoch 內
--     regression 交叉偵測：當前 row 值不得低於窗內任何事件快照）。
--     全部 NULL-able：flag_change 等事件在計數讀取失敗時仍可記錄事件本身。
--
--   【flag_enabled NOT NULL —— 每筆事件都記 flag 狀態】
--     S4「窗內 0 次 flag-OFF 觀測」的證據軸之一：任何 flag_enabled=false 的事件
--     都是一次 OFF 觀測（連同 V129 兩 row 的 flag_enabled 共同構成觀測面）。
--
--   【detail JSONB —— 低頻擴充位】
--     epoch_rollover 攜 prev_singleton_updated_at_epoch_s / prev_canary_updated_at_epoch_s
--     （供 `[82]` 算 epoch 間隙 ≤30min）；counter_regression 攜 before/after；
--     canary_fail_streak 攜 breaches / consecutive_failures。schema 不為這些開欄
--     （低速表 + step-(iv) 整組退役，JSONB 足夠且免未來 ALTER）。
--
--   【冪等 double-apply 全 no-op】(per CLAUDE「applying twice」+ V129 同 pattern)
--     - CREATE SCHEMA / TABLE IF NOT EXISTS → 第二次 no-op（Guard A 已驗 shape）
--     - 條件式 ADD CONSTRAINT（pg_constraint 探測存在 → skip）→ 第二次 no-op
--     - CREATE INDEX IF NOT EXISTS → 第二次 no-op（Guard C 驗到位）
--     - COMMENT ON → 可重跑
--
-- Idempotency 重跑兩次必 PASS（per memory feedback_v_migration_pg_dry_run
--   double-apply mandatory）。本 migration 須 Linux PG empirical 雙跑 dry-run
--   （BEGIN/apply/ROLLBACK + double-apply）才能 sign-off。
--
-- Guard（per V054/V129 pattern，fail-closed + idempotent）:
--   Guard A — CREATE TABLE IF NOT EXISTS 前驗既有表必要欄完整（缺 → RAISE）
--   Guard B — N/A（無 column type ALTER；只 NEW table CREATE + 條件式 CHECK）
--   Guard C — 建後驗 created_at index 到位（`[82]` 窗查詢 load-bearing）
--
-- E2 review checklist:
--   1. Guard A 對必要欄完整性（重跑 shape drift → RAISE）
--   2. append-only：無 UPDATE/DELETE 路徑（writer 只 INSERT；retention 由 step-(iv)
--      DROP 整表解決，毋需 per-row 清理）
--   3. CHECK：event_type 白名單 6 型（PA 4 型 + E1 偏差 2 型，理由見上）
--   4. prev_* 全 NULL-able（事件本身的記錄不被計數讀取失敗阻斷）
--   5. created_at DEFAULT now() = DB-side 權威（`[82]` 窗計算基準）
--   6. 冪等：ADD CONSTRAINT 條件式探測 + index IF NOT EXISTS
--
-- 硬邊界:
--   - 不碰 V054 learning.lease_transitions / V129 lease_ipc_divergence_snapshot
--     （`[82]` 對它們 read-only；本表 disjoint）。
--   - 不改 max_retries / live_execution_allowed / execution_authority / system_mode（無關）。
--   - 本表純觀測帳本；step-(iv) cleanup 連同 canary/flusher 擴充/`[82]`/V129 一起
--     退役（屆時 DROP 本表，見 §E）。
--
-- migration latest: V136 → V137（檔案 max = V136__l2_provenance_columns.sql；
--   Linux _sqlx_migrations max(version) = 136（2026-06-10 ssh 親證）；V137 free）。
-- ============================================================

-- 全 migration 包在單一 transaction（原子 all-or-nothing；對齊 V129 pattern）。
-- 無 Timescale → 無「Guard 須 COMMIT 後 autocommit 反射」需求，全部 DDL + Guard
-- 皆可在同一 transaction 內安全執行。
BEGIN;

-- ============================================================
-- §A CREATE SCHEMA IF NOT EXISTS learning (idempotent)
-- learning namespace 早於 V054 已建；第二次 apply no-op。
-- ============================================================
CREATE SCHEMA IF NOT EXISTS learning;

-- ============================================================
-- §B learning.lease_ipc_soak_events — soak epoch/flag 事件帳本
-- ============================================================

-- Guard A: 既有表必要欄完整性（缺 ≥1 → RAISE）
-- 為什麼 fail-closed：若舊版 schema drift（缺 prev_* 快照欄或 created_at），`[82]`
--   跨 epoch 求和 / 窗計算會靜默失真（讀不到欄 → query error → check 誤判）。缺欄
--   一律 RAISE 強制 operator 解 drift 後重跑（不靜默 ALTER）。
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'lease_ipc_soak_events'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'event_type', 'flag_enabled',
            'prev_total', 'prev_matches', 'prev_divergences',
            'prev_canary_attempts', 'prev_canary_ok', 'prev_canary_fail',
            'detail', 'created_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning' AND table_name = 'lease_ipc_soak_events'
              AND column_name = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V137 Guard A FAIL: learning.lease_ipc_soak_events exists but missing '
                'required columns: %. 解決 legacy schema drift（DROP + re-apply 或 '
                'ALTER ADD）後重跑 V137.', v_missing;
        END IF;
        RAISE NOTICE 'V137 Guard A: learning.lease_ipc_soak_events already present with all required columns';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.lease_ipc_soak_events (
    id                    BIGSERIAL    PRIMARY KEY,
    -- 事件型（白名單 CHECK 見 §C；語義見頭部設計決策）。
    event_type            TEXT         NOT NULL,
    -- 事件當下 OPENCLAW_LEASE_PYTHON_IPC_ENABLED == "1"（S4 flag-OFF 觀測軸之一）。
    flag_enabled          BOOLEAN      NOT NULL DEFAULT FALSE,
    -- comparator 計數快照（epoch_rollover = 前一 epoch 終值；其他事件 = emit 當下值）。
    prev_total            BIGINT       NULL,
    prev_matches          BIGINT       NULL,
    prev_divergences      BIGINT       NULL,
    -- canary 計數快照（同上語義；attempts/ok/fail 對映 V129 'canary' row 的
    -- total/matches/divergences 欄位映射，COMMENT 文檔化於 E1-B）。
    prev_canary_attempts  BIGINT       NULL,
    prev_canary_ok        BIGINT       NULL,
    prev_canary_fail      BIGINT       NULL,
    -- 低頻擴充位（epoch 間隙時間戳 / regression before-after / streak 細節）。
    detail                JSONB        NULL,
    -- DB-side now() = `[82]` 窗計算的權威時間（writer clock drift 不影響窗判定）。
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ============================================================
-- §C 條件式 CHECK 約束（event_type 白名單；重跑 pg_constraint 探測 skip）
-- 釘住事件型集合：未知事件型直接 INSERT 失敗（fail-loud），防 writer 端 typo
-- 讓 `[82]` 的型別過濾靜默漏讀。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lease_ipc_soak_events_type'
          AND conrelid = 'learning.lease_ipc_soak_events'::regclass
    ) THEN
        ALTER TABLE learning.lease_ipc_soak_events
            ADD CONSTRAINT chk_lease_ipc_soak_events_type
            CHECK (event_type IN (
                'flusher_start', 'epoch_rollover', 'flag_change',
                'canary_leader_start', 'canary_fail_streak', 'counter_regression'
            ));
        RAISE NOTICE 'V137: added CHECK chk_lease_ipc_soak_events_type (event_type whitelist)';
    ELSE
        RAISE NOTICE 'V137: chk_lease_ipc_soak_events_type already present; skipping';
    END IF;
END $$;

-- ============================================================
-- §D Guard C: created_at index（`[82]` 窗查詢 load-bearing）
-- `[82]` 每 6h 以 created_at 範圍掃窗（≤14d）；表雖低速，index 讓 retention 失守
-- （理論上限）時查詢仍有界。IF NOT EXISTS 冪等；建後驗到位。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_lease_ipc_soak_events_created_at
    ON learning.lease_ipc_soak_events (created_at);

DO $$
DECLARE v_has_idx BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'learning' AND tablename = 'lease_ipc_soak_events'
          AND indexname = 'idx_lease_ipc_soak_events_created_at'
    ) INTO v_has_idx;
    IF NOT v_has_idx THEN
        RAISE EXCEPTION
            'V137 Guard C FAIL: idx_lease_ipc_soak_events_created_at 缺失 — '
            '`[82]` 窗查詢 load-bearing index 必須存在.';
    END IF;
    RAISE NOTICE 'V137 Guard C: idx_lease_ipc_soak_events_created_at present';
END $$;

-- ============================================================
-- §COMMENT 語義文檔（idempotent: COMMENT ON 可重跑）
-- ============================================================
COMMENT ON TABLE learning.lease_ipc_soak_events IS
    'P5-SM-OPTION2 step-(i) soak 監測（第二輪重設計，V137）：append-only epoch/flag '
    '事件帳本。flusher leader 在 epoch 邊界（API 重啟，搶救前 epoch 計數終值）/ flag '
    '變遷 / canary 失敗連段（≥15min）/ counter regression 時 INSERT 一筆。`[82]` '
    'lease_ipc_soak_window healthcheck 讀本表 + V129 兩 row 重建連續有效 soak 窗'
    '（S3/S4 gate）。低速（soak 兩週 < ~100 row）非 hypertable。writer 只 INSERT'
    '（append-only）；step-(iv) cleanup 連同 canary/flusher 擴充/`[82]`/V129 退役後 DROP。';
COMMENT ON COLUMN learning.lease_ipc_soak_events.event_type IS
    '事件型白名單：flusher_start（flusher leader 啟動）/ epoch_rollover（API 重啟，'
    'prev_* 攜前一 epoch 計數終值 + detail 攜前 epoch 末次 flush 時間戳供間隙計算）/ '
    'flag_change（OPENCLAW_LEASE_PYTHON_IPC_ENABLED 變遷）/ canary_leader_start'
    '（canary 開始 probe）/ canary_fail_streak（失敗連段跨 15min，S3 連段證據）/ '
    'counter_regression（程內計數器倒退，S4 記帳完整性證據）。';
COMMENT ON COLUMN learning.lease_ipc_soak_events.prev_canary_attempts IS
    'canary 計數快照：epoch_rollover = 前一 epoch 終值（`[82]` 跨 epoch 求和累計 '
    'probe 數）；其他事件型 = emit 當下本 epoch 值（`[82]` epoch 內 regression 交叉'
    '偵測：當前 V129 canary row total 不得低於窗內任何事件快照）。';
COMMENT ON COLUMN learning.lease_ipc_soak_events.created_at IS
    'DB-side now()；`[82]` 窗計算（連續有效窗錨點 / epoch 間隙 ≤30min / 72h soak '
    '活性回看）的權威時間。';

COMMIT;

-- ============================================================
-- §E ROLLBACK（手動執行；非 sqlx down migration — 本專案 sqlx forward-only）
-- per V129 rollback pattern：
--   1. 本表純觀測帳本，無下游 FK 依賴 → DROP RESTRICT 安全（若有依賴會 fail-loud）。
--   2. step-(iv) cleanup（cutover 後監測面整組退役）時連同 V129 一起 DROP。
--   3. sqlx checksum drift → 用既有 repair_migration_checksum 工作流（不手改 _sqlx_migrations）。
--
-- 完整 teardown:
--   DROP TABLE IF EXISTS learning.lease_ipc_soak_events RESTRICT;
--   -- 不 DROP SCHEMA learning（lease_transitions 等大量表仍在）。
-- ============================================================
