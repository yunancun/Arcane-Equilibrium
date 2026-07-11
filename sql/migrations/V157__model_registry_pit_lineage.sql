-- ============================================================
-- V157: learning.model_registry PIT lineage 欄位
--       training_window_start / training_window_end / pit_manifest_hash
--       （ML 稽核 remediation Item 7 — 讓 lineage 可重建而不翻動 production
--        contract_bound_run）
--
-- 目的 / Motivation:
--   V023 的 model_registry 只記 train_date（DATE，訓練「執行日」）與
--   training_sample_size（樣本數），無法回答「這個模型是用哪段時窗的資料訓練的」
--   與「綁定的 PIT dataset manifest 是哪一份」。稽核要重建 lineage 目前只能靠
--   acceptance_report JSONB 內的 PIT binding sidecar；而 production 量產路徑
--   contract_bound_run=False（預設），sidecar 多為 not_contract_bound 空殼。
--
--   本 migration 走 SOURCE 路線（非「翻 cron contract_bound_run」的 runtime 路線）：
--   直接在 registry row 加三個可獨立重建 lineage 的 typed 欄，由
--   run_training_pipeline 於每次 register 一併寫入：
--     training_window_start — 本次訓練資料 timestamps 的最小值（UTC）
--     training_window_end   — 本次訓練資料 timestamps 的最大值（UTC）
--     pit_manifest_hash     — PIT dataset manifest hash（contract-bound run 才有；
--                             非 contract-bound run 為 NULL）
--   如此不動 production contract_bound_run 亦能讓每筆 registry row 自身承載
--   訓練時窗，稽核可直接重建，而非只能靠 sidecar。
--
-- 範圍 / Scope (V157):
--   §Guard A — learning.model_registry 存在且帶 V023 基線欄（缺 → RAISE）
--   §Guard B — 三個新欄已存在時的型別反射（型別不符 → RAISE）
--   §Body    — 3× ADD COLUMN IF NOT EXISTS（nullable、無 default → catalog-only，
--              不重寫表；無 backfill：歷史 row 的訓練時窗無法事後重建，留 NULL）
--   §Guard C — 後驗：三欄到位且型別正確（fail-loud）
--
-- 編號決策（migration 號是 git 看不見的全局命名空間）:
--   repo file chain 最高 = V156（V151..V156 為 ALR 系列）。next-free = V157。
--   apply 前另於 trade-core prod _sqlx_migrations 親查 max(version) 交叉確認。
--
-- 冪等 double-apply 全 no-op（per memory feedback_v_migration_pg_dry_run）:
--   - ADD COLUMN IF NOT EXISTS → 第二次 skip
--   - Guard B 第二次見型別已符 → 不 RAISE
--   - Guard C 兩次皆 PASS
--   本 migration 純 additive nullable，無 CHECK/backfill/index，天然冪等。
--
-- 硬邊界:
--   - 不碰 canary_status / promoted_at / verdict / 任何晉升欄；不動 _latest、
--     proof promotion、unique index、production-latest index。
--   - 純 additive nullable 欄；不改既有欄、不刪任何 row。
--   - 舊 binary rollback 安全（新欄 nullable，舊 writer 不寫即 NULL）。
-- ============================================================

-- ------------------------------------------------------------
-- Guard A — learning.model_registry 存在且帶 V023 基線欄
-- 為什麼：本 migration 只 ALTER（不 CREATE）。若表不存在或仍是 V004-era legacy
-- stub（缺 canary_status），盲 ADD COLUMN 會在錯誤 shape 上加欄；RAISE 比靜默安全。
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF to_regclass('learning.model_registry') IS NULL THEN
        RAISE EXCEPTION
            'V157 Guard A FAIL: learning.model_registry does not exist — '
            'V023 was never applied. Re-bootstrap DB before V157.';
    END IF;
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'strategy', 'engine_mode', 'quantile', 'schema_version', 'train_date',
        'verdict', 'canary_status', 'training_sample_size'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name   = 'model_registry'
          AND column_name  = c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V157 Guard A FAIL: learning.model_registry missing required V023 '
            'columns: %. Likely a legacy V004-era stub — resolve before V157.',
            v_missing;
    END IF;
    RAISE NOTICE 'V157 Guard A PASS: learning.model_registry V023 baseline intact.';
END $$;

-- ------------------------------------------------------------
-- Guard B — 三個新欄已存在時的型別反射
-- 為什麼：ADD COLUMN IF NOT EXISTS 對「已存在但型別錯」靜默跳過，等 writer
-- flush 才報難解 type mismatch；Guard B 把失敗點上移到 apply 階段。
-- 期望型別：timestamp/timestamp → 'timestamp with time zone'；hash → 'text'。
-- ------------------------------------------------------------
DO $$
DECLARE
    v_type TEXT;
BEGIN
    -- training_window_start
    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_schema = 'learning' AND table_name = 'model_registry'
      AND column_name = 'training_window_start';
    IF v_type IS NOT NULL AND v_type <> 'timestamp with time zone' THEN
        RAISE EXCEPTION
            'V157 Guard B FAIL: model_registry.training_window_start is %, '
            'expected timestamp with time zone.', v_type;
    END IF;

    -- training_window_end
    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_schema = 'learning' AND table_name = 'model_registry'
      AND column_name = 'training_window_end';
    IF v_type IS NOT NULL AND v_type <> 'timestamp with time zone' THEN
        RAISE EXCEPTION
            'V157 Guard B FAIL: model_registry.training_window_end is %, '
            'expected timestamp with time zone.', v_type;
    END IF;

    -- pit_manifest_hash
    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_schema = 'learning' AND table_name = 'model_registry'
      AND column_name = 'pit_manifest_hash';
    IF v_type IS NOT NULL AND v_type <> 'text' THEN
        RAISE EXCEPTION
            'V157 Guard B FAIL: model_registry.pit_manifest_hash is %, '
            'expected text.', v_type;
    END IF;
END $$;

-- ------------------------------------------------------------
-- Body — additive nullable 欄位（無 default → catalog-only，不重寫表）
-- 無 backfill：歷史 row 的訓練資料時窗無法事後可靠重建（train_date 只有日期粒度、
-- 無 window，且原始 timestamps 已不在 registry），故留 NULL 表「該 row 早於 V157，
-- lineage 欄未採集」。前向新 row 由 run_training_pipeline 寫入實值。
-- ------------------------------------------------------------
ALTER TABLE learning.model_registry
    ADD COLUMN IF NOT EXISTS training_window_start TIMESTAMPTZ;
ALTER TABLE learning.model_registry
    ADD COLUMN IF NOT EXISTS training_window_end   TIMESTAMPTZ;
ALTER TABLE learning.model_registry
    ADD COLUMN IF NOT EXISTS pit_manifest_hash     TEXT;

COMMENT ON COLUMN learning.model_registry.training_window_start IS
    'PIT lineage (V157): min(training timestamps) UTC — 本次訓練資料時窗起點。'
    'NULL = pre-V157 row 或無 timestamps 的 run。由 run_training_pipeline 於 register '
    '時寫入，供稽核重建 lineage 而不必翻動 production contract_bound_run。';
COMMENT ON COLUMN learning.model_registry.training_window_end IS
    'PIT lineage (V157): max(training timestamps) UTC — 本次訓練資料時窗終點。'
    'NULL = pre-V157 row 或無 timestamps 的 run。';
COMMENT ON COLUMN learning.model_registry.pit_manifest_hash IS
    'PIT lineage (V157): 綁定的 PIT dataset manifest hash（training_pit_manifest_'
    'binding.manifest_hash）。contract-bound run 才有值；非 contract-bound（production '
    '量產預設）為 NULL。與 acceptance_report JSONB 內 binding 互為冗餘可交叉驗。';

-- ------------------------------------------------------------
-- Guard C — 後驗：三欄到位且型別正確（fail-loud）
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    SELECT array_agg(spec.col) INTO v_missing
    FROM (VALUES
        ('training_window_start', 'timestamp with time zone'),
        ('training_window_end',   'timestamp with time zone'),
        ('pit_manifest_hash',     'text')
    ) AS spec(col, want)
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning' AND table_name = 'model_registry'
          AND column_name = spec.col AND data_type = spec.want
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V157 Guard C FAIL: model_registry PIT lineage columns missing or '
            'wrong type: %.', v_missing;
    END IF;
    RAISE NOTICE 'V157: all guards PASS — model_registry PIT lineage columns live.';
END $$;

-- ============================================================
-- ROLLBACK（手動執行；本專案 sqlx forward-only）:
--   ALTER TABLE learning.model_registry DROP COLUMN IF EXISTS pit_manifest_hash;
--   ALTER TABLE learning.model_registry DROP COLUMN IF EXISTS training_window_end;
--   ALTER TABLE learning.model_registry DROP COLUMN IF EXISTS training_window_start;
--   （新欄 nullable、無下游 NOT NULL 相依 → rollback 前無需先回退 binary；
--    新 writer 寫入這三欄，舊 binary 不寫即 NULL，皆合法。）
--   sqlx checksum drift → 用 bin/repair_migration_checksum 工作流。
-- ============================================================
