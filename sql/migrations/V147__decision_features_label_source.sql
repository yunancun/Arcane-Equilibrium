-- ============================================================
-- V147: learning.decision_features.label_source — label lineage typed 欄位
--       （P1-3 訓練 label 污染修復 durable 段，冷審計 R2 修復 Phase B2）
--
-- 目的 / Motivation:
--   governance reject path（intent_processor emit_decision_feature_intent_rejected）
--   每天寫 ~46k 條合成 label（label_close_tag='rejected_governance'、
--   label_net_edge_bps=0.0）。2026-07-04 runtime 實測：已標籤 5,374,541 行中
--   5,370,972 行（99.93%）為合成 —— 訓練集被淹沒成常數預測器（pinball skill 恆 0）。
--   訓練側 SQL 過濾（parquet_etl / mlde_shadow_advisor）已以 label_close_tag
--   字串慣例修復；本 migration 把 lineage 從字串慣例升級為 typed 欄位，讓任何
--   未來消費者可以按 label_source 明確區分「真實 outcome」與「合成 reject」，
--   不再依賴對 close_tag 字面值的隱性知識。
--
--   欄位語義：
--     'realized_fill'    — edge_label_backfill.py Pass 1 回填的真實 close 結果
--     'synthetic_reject' — Rust reject path 直寫的合成 negative label
--     NULL               — 未標籤行 / 歷史 Pass 2(excluded)、Pass 3(abandoned)
--                          行（label_net_edge_bps 為 NULL，非訓練樣本）
--
-- 範圍 / Scope (V147):
--   §Guard A — decision_features 存在且帶 label 基線欄（缺 → RAISE）
--   §Guard B — label_source 已存在時的型別反射（非 text → RAISE）
--   §Body    — ADD COLUMN IF NOT EXISTS + CHECK 約束（NOT VALID 先掛）
--   §Backfill— 歷史已標籤行分批 UPDATE（ts 窗口批次，走 idx_decision_features_ts）
--   §Validate— VALIDATE CONSTRAINT（backfill 後全表驗證）
--   §Guard C — 後驗：欄位 + 約束到位且 validated（fail-loud）
--
-- 編號決策（migration 號是 git 看不見的全局命名空間）:
--   2026-07-04 ssh trade-core 親查 prod _sqlx_migrations max(version)=145；
--   repo file chain 最高 = V146（未 apply）。next-free = V147。
--
-- 寫入方 / Writers（現狀 + 待接線 follow-up）:
--   - 【本 migration 已做】歷史已標籤行由下方 §Backfill 分批 UPDATE 全數標齊
--     （CASE：rejected_governance → 'synthetic_reject'，其餘 → 'realized_fill'）。
--   - 【前向寫入尚未接線 — 明確 follow-up，非本批】Rust DecisionFeatureMsg 增
--     label_source 欄（reject path 寫 'synthetic_reject'）+ edge_label_backfill.py
--     Pass 1 寫 'realized_fill'。此段涉 6 處 struct constructor + writer SQL $16，
--     須 cargo build/test 驗證；Mac 開發機無 cargo（memory 教訓）→ 交 E4 Linux
--     wave 實作驗證，不在本 wave 盲改不可編譯驗證的 Rust。
--   - 【接線前的正確性保證】前向新行 label_source 暫為 NULL，但 lineage 仍
--     可由既有 label_close_tag 字串重建（rejected_governance ⇔ synthetic_reject）；
--     訓練側過濾（parquet_etl / mlde_shadow_advisor）已獨立以 label_close_tag
--     生效，不依賴本欄 → 本 migration 是「歷史 lineage 落 typed 欄 + 前向欄位就位」
--     的可獨立 apply 半步，非 dead column（歷史全標齊 + 有明確接線 follow-up）。
--   - CHECK 允許 NULL 故未接線期間的前向 NULL 行合法；舊 binary rollback 安全。
--
-- 冪等 double-apply 全 no-op（per memory feedback_v_migration_pg_dry_run）:
--   - ADD COLUMN IF NOT EXISTS → 第二次 skip
--   - CHECK 約束 DO-block 查 pg_constraint 先 → 第二次 skip
--   - Backfill 掃 label_source IS NULL AND label_net_edge_bps IS NOT NULL
--     → 第二次 0 行，迴圈立即結束
--   - VALIDATE CONSTRAINT 只在 convalidated=false 時執行 → 第二次 skip
--
-- 硬邊界:
--   - 不碰 max_retries / live_execution_allowed / execution_authority / system_mode。
--   - 純 additive + backfill；不改既有欄位、不刪任何行。
--   - 不改訓練判準本體（訓練側過濾以 label_close_tag 字串已獨立生效，A/B 不依賴本欄）。
-- ============================================================

-- ------------------------------------------------------------
-- Guard A — learning.decision_features 存在且帶 label 基線欄
-- 為什麼：本 migration 只 ALTER（不 CREATE），且 backfill CASE 依賴
-- label_close_tag / label_net_edge_bps（V017 基線）就位；缺欄=schema drift，
-- RAISE 比靜默 ADD COLUMN 安全。
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF to_regclass('learning.decision_features') IS NULL THEN
        RAISE EXCEPTION
            'V147 Guard A FAIL: learning.decision_features does not exist — '
            'V017 was never applied. Re-bootstrap DB before V147.';
    END IF;
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'context_id', 'ts', 'engine_mode', 'strategy_name', 'symbol',
        'label_net_edge_bps', 'label_close_tag', 'label_filled_at'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name   = 'decision_features'
          AND column_name  = c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V147 Guard A FAIL: learning.decision_features missing required '
            'columns: %. V017 baseline must be intact before V147.', v_missing;
    END IF;
    RAISE NOTICE 'V147 Guard A PASS: learning.decision_features baseline intact.';
END $$;

-- ------------------------------------------------------------
-- Guard B — label_source 已存在時的型別反射
-- 為什麼：ADD COLUMN IF NOT EXISTS 對「已存在但型別錯」靜默跳過，等 Rust writer
-- flush 才報難解 type mismatch；Guard B 把失敗點上移到 apply 階段。
-- ------------------------------------------------------------
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'learning' AND table_name = 'decision_features'
      AND column_name = 'label_source';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V147 Guard B FAIL: decision_features.label_source is %, expected text. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V147.',
            v_actual;
    END IF;
END $$;

-- ------------------------------------------------------------
-- Body — additive nullable 欄位（無 default → catalog-only，不重寫 15 GB 表）
-- ------------------------------------------------------------
ALTER TABLE learning.decision_features
    ADD COLUMN IF NOT EXISTS label_source TEXT;

-- CHECK 約束：NOT VALID 先掛（不掃全表），backfill 完成後 VALIDATE。
-- NULL 通過 CHECK（IN 對 NULL 回 NULL 非 false）→ 舊 binary / 未標籤行合法。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_decision_features_label_source'
          AND conrelid = 'learning.decision_features'::regclass
    ) THEN
        ALTER TABLE learning.decision_features
            ADD CONSTRAINT chk_decision_features_label_source
            CHECK (label_source IN ('realized_fill', 'synthetic_reject'))
            NOT VALID;
        RAISE NOTICE 'V147: chk_decision_features_label_source added (NOT VALID).';
    ELSE
        RAISE NOTICE 'V147: chk_decision_features_label_source already present — skip.';
    END IF;
END $$;

COMMENT ON COLUMN learning.decision_features.label_source IS
    'P1-3 label lineage (V147): ''realized_fill'' = edge_label_backfill Pass 1 '
    'real close outcome; ''synthetic_reject'' = Rust governance-reject synthetic '
    'negative label (label_close_tag=''rejected_governance''); NULL = unlabeled / '
    'excluded / abandoned rows (label_net_edge_bps IS NULL) or pre-V147 writer rows.';

-- ------------------------------------------------------------
-- Backfill — 歷史已標籤行分批 UPDATE
-- 為什麼分批：2026-07-04 實測已標籤行 5.37M（表 15 GB）。單條 UPDATE 一次鎖住
-- 全部行且單語句記憶體壓力大；按 ts 窗（1 天）批次走 idx_decision_features_ts，
-- 每批 ~50k 行、確定性推進（不會像 LIMIT 批次那樣重掃已更新行）。
-- 只觸 label_net_edge_bps IS NOT NULL 行；Pass 2/3（excluded/abandoned）與
-- 未標籤行保 NULL（非訓練樣本，lineage 語義=未標）。
-- ------------------------------------------------------------
DO $$
DECLARE
    v_min_ts   TIMESTAMPTZ;
    v_max_ts   TIMESTAMPTZ;
    v_cursor   TIMESTAMPTZ;
    v_step     INTERVAL := INTERVAL '1 day';
    v_batch    BIGINT;
    v_total    BIGINT := 0;
BEGIN
    SELECT min(ts), max(ts) INTO v_min_ts, v_max_ts
    FROM learning.decision_features
    WHERE label_net_edge_bps IS NOT NULL
      AND label_source IS NULL;

    IF v_min_ts IS NULL THEN
        RAISE NOTICE 'V147 backfill: no labeled rows pending — skip (idempotent re-apply).';
        RETURN;
    END IF;

    v_cursor := v_min_ts;
    WHILE v_cursor <= v_max_ts LOOP
        UPDATE learning.decision_features
           SET label_source = CASE
                   WHEN label_close_tag = 'rejected_governance' THEN 'synthetic_reject'
                   ELSE 'realized_fill'
               END
         WHERE ts >= v_cursor AND ts < v_cursor + v_step
           AND label_net_edge_bps IS NOT NULL
           AND label_source IS NULL;
        GET DIAGNOSTICS v_batch = ROW_COUNT;
        v_total := v_total + v_batch;
        IF v_batch > 0 THEN
            RAISE NOTICE 'V147 backfill: window % → % rows (cumulative %)',
                v_cursor, v_batch, v_total;
        END IF;
        v_cursor := v_cursor + v_step;
    END LOOP;

    RAISE NOTICE 'V147 backfill complete: % rows updated.', v_total;
END $$;

-- ------------------------------------------------------------
-- Validate — backfill 後全表驗證 CHECK（第二次 apply：已 validated → skip）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_decision_features_label_source'
          AND conrelid = 'learning.decision_features'::regclass
          AND NOT convalidated
    ) THEN
        ALTER TABLE learning.decision_features
            VALIDATE CONSTRAINT chk_decision_features_label_source;
        RAISE NOTICE 'V147: chk_decision_features_label_source VALIDATED.';
    ELSE
        RAISE NOTICE 'V147: constraint already validated — skip.';
    END IF;
END $$;

-- ------------------------------------------------------------
-- Guard C — 後驗：欄位 + 約束到位且 validated（fail-loud）
-- ------------------------------------------------------------
DO $$
DECLARE
    v_ok BOOLEAN;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning' AND table_name = 'decision_features'
          AND column_name = 'label_source' AND data_type = 'text'
    ) THEN
        RAISE EXCEPTION 'V147 Guard C FAIL: label_source column missing or wrong type.';
    END IF;
    SELECT convalidated INTO v_ok
    FROM pg_constraint
    WHERE conname = 'chk_decision_features_label_source'
      AND conrelid = 'learning.decision_features'::regclass;
    IF v_ok IS NULL THEN
        RAISE EXCEPTION 'V147 Guard C FAIL: chk_decision_features_label_source missing.';
    END IF;
    IF NOT v_ok THEN
        RAISE EXCEPTION 'V147 Guard C FAIL: chk_decision_features_label_source not validated.';
    END IF;
    RAISE NOTICE 'V147: all guards PASS — label_source lineage column live.';
END $$;

-- ============================================================
-- ROLLBACK（手動執行；本專案 sqlx forward-only）:
--   ALTER TABLE learning.decision_features
--       DROP CONSTRAINT IF EXISTS chk_decision_features_label_source;
--   ALTER TABLE learning.decision_features DROP COLUMN IF EXISTS label_source;
--   （本 wave 尚未接線前向 Rust writer，故現階段 rollback 無 binary 相依；
--    未來接線 label_source $16 INSERT 後，rollback 本欄前須先回退 binary，
--    否則 reject path 寫入失敗（writer fail-soft re-pend，交易不受影響）。）
--   sqlx checksum drift → 用 bin/repair_migration_checksum 工作流。
-- ============================================================
