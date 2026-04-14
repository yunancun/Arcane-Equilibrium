-- ============================================================
-- V017 ROLLBACK — Edge Predictor Tables (EDGE-P3-1)
-- 回滾 V017 遷移 — 邊緣預測器表
--
-- 使用時機：V017 部署後發現故障，在尚無生產資料寫入新列前回滾。
-- When to use: V017 deployed but found faulty, before any production writes
-- land in the new columns/tables.
--
-- ⚠️ DATA-LOSS WARNING / 資料損失警告：
--   - DROP TABLE learning.decision_features / learning.decision_shadow_fills
--     會永久刪除已寫入的 feature 快照與 shadow fills。
--   - ALTER TABLE DROP COLUMN 會永久刪除 predicted_q10/q50/q90 + disagreed 等列。
--   - 僅在「確認尚無 downstream ML 訓練使用這些資料」時執行。
--
-- 執行方式 / Usage:
--   psql "$DSN" -v ON_ERROR_STOP=1 -f sql/migrations/V017_rollback.sql
-- ============================================================

BEGIN;

-- ----- learning schema：新表 drop -----
DROP TABLE IF EXISTS learning.decision_shadow_fills;
DROP TABLE IF EXISTS learning.decision_features;

-- ----- trading.decision_context_snapshots：8 新列 drop -----
ALTER TABLE trading.decision_context_snapshots
    DROP COLUMN IF EXISTS predict_latency_us,
    DROP COLUMN IF EXISTS disagreed,
    DROP COLUMN IF EXISTS shrinkage_decision,
    DROP COLUMN IF EXISTS predictor_decision,
    DROP COLUMN IF EXISTS predicted_q90,
    DROP COLUMN IF EXISTS predicted_q50,
    DROP COLUMN IF EXISTS predicted_q10;

DROP INDEX IF EXISTS trading.idx_dcs_predicted_q50;

-- ----- trading.fills：entry_context_id drop -----
ALTER TABLE trading.fills
    DROP COLUMN IF EXISTS entry_context_id;

DROP INDEX IF EXISTS trading.idx_fills_entry_ctx;

COMMIT;

-- ============================================================
-- 驗證回滾完成 / Verify rollback
-- ============================================================
-- SELECT column_name FROM information_schema.columns
--   WHERE table_schema='trading' AND table_name='decision_context_snapshots'
--   AND column_name IN ('predicted_q10','predicted_q50','predicted_q90',
--                       'predictor_decision','shrinkage_decision',
--                       'disagreed','predict_latency_us');
-- Expected: 0 rows
--
-- SELECT column_name FROM information_schema.columns
--   WHERE table_schema='trading' AND table_name='fills'
--   AND column_name='entry_context_id';
-- Expected: 0 rows
--
-- SELECT to_regclass('learning.decision_features'),
--        to_regclass('learning.decision_shadow_fills');
-- Expected: 2 NULL
