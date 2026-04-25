-- ============================================================
-- V025: Partial index for outcome_backfiller pending scan
--   trading.decision_context_snapshots(ts) WHERE outcome_backfilled = FALSE
-- 部分索引以加速 outcome_backfiller pending scan
-- ============================================================
--
-- Background / 背景 (G7-08, 2026-04-24):
--   `outcome_backfiller` (rust/openclaw_engine/src/database/outcome_backfiller.rs)
--   每 5 分鐘跑一次 BACKFILL_SQL，pending CTE 從 ~770k 行的
--   trading.decision_context_snapshots 撈 200 行待回填上下文。
--   生產 log 觀察：sqlx slow-statement WARN 每 5 分鐘觸發，
--   elapsed: 1.5s, slow_threshold: 1s。
--
--   EXPLAIN ANALYZE 顯示 pending CTE 佔絕大部分時間（kline
--   correlated sub-selects 已經有 (symbol, timeframe, ts) BTree
--   命中，每個 ~0.01ms × 200 loops 共 <2ms）：
--
--     -> Parallel Seq Scan on decision_context_snapshots
--          (cost=0.00..216808.59 rows=79636 width=84)
--          (actual time=3.700..115.119 rows=49386 loops=3)
--          Filter: ((NOT outcome_backfilled) AND (last_price IS NOT NULL)
--                   AND (last_price > 0) AND (ts < now() - '25:00:00'))
--          Rows Removed by Filter: 208509
--          Buffers: shared hit=486 read=209766
--
--   表 size 1.6 GB（1.6 億 page * 8KB），seq scan 每次讀 209k pages；
--   buffer cache 5 分鐘被其他 writer 擠掉後再跑就退化成 cold-read，
--   觀察到 1.5s 即此情境。Hot cache 下還可在 168ms 完成，但任何
--   並發 INSERT (decision_context_snapshots 持續寫入) 都會增加
--   dirty page 與 cache miss。
--
--   148,153 rows 命中 pending filter（時間 + 未回填 + price>0），
--   187,091 rows 是 outcome_backfilled = FALSE（含 25h 內的新行）。
--   Partial index 只索引未回填的 ~187k 行，size 約 5-10MB。
--
-- What this migration does / 本遷移做什麼：
--   單一 CREATE INDEX IF NOT EXISTS — 部分索引限制在
--   outcome_backfilled = FALSE AND last_price > 0 的 rows，
--   按 ts ASC 排（order key match pending CTE 的 ORDER BY ts ASC）。
--
--   Planner 行為預期：
--   1. Filter outcome_backfilled = FALSE → 命中 partial index condition
--   2. ts < NOW() - INTERVAL '25 hours' → 用 index range scan
--   3. ORDER BY ts ASC LIMIT 200 → index 已排序，直接 scan 前 200 row
--
--   預期效益：1.5s → <50ms（索引大小 ~10MB，全部 in memory 後續
--   每次 cycle 都是 hot read）。Rows Removed by Filter 從 208k → ~0。
--
-- Idempotency / 冪等性：
--   `CREATE INDEX IF NOT EXISTS` — 重複執行 no-op。
--   無 DDL 對既有資料的影響（純加索引）。
--   無 Guard A/B 必要（不建表、不加欄位）。
--   Guard C 雖適用 hot-path 索引，但這是新索引（無 legacy drift 風險），
--   下一次操作即直接 CREATE，無需在 CREATE 前做 shape 比對。
--
--   重複跑兩次 `psql -f V025__outcome_backfill_pending_index.sql`：
--   第二次 CREATE INDEX IF NOT EXISTS 直接 no-op，無 RAISE。
--
-- Rollback / 回滾：
--   DROP INDEX IF EXISTS trading.idx_dcs_outcome_backfill_pending;
--   無資料損失（純索引）。
--
-- Engine auto_migrate path / Engine 自動遷移路徑：
--   `OPENCLAW_AUTO_MIGRATE=1` 時 engine 啟動偵測 V025（version 25
--   > LEGACY_APPLIED_MAX_VERSION 23 + 24），透過 `Migrator::run_direct`
--   視為 pending → 自動套用、寫入 `_sqlx_migrations` 一行新 row。
--   手動 `bash helper_scripts/linux_bootstrap_db.sh --apply` 同樣套用。
--
-- Test / 測試:
--   套用後跑 `EXPLAIN (ANALYZE, BUFFERS) WITH pending AS (...)` 驗
--   plan 從 Parallel Seq Scan 改為 Index Scan + Limit；execution_time
--   應 <50ms（vs 168ms hot / 1500ms cold pre-fix）。
-- ============================================================


-- ------------------------------------------------------------
-- Partial index on (ts) WHERE outcome_backfilled = FALSE
-- 部分索引：(ts)，僅 outcome_backfilled = FALSE 的 rows
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dcs_outcome_backfill_pending
    ON trading.decision_context_snapshots (ts ASC)
    WHERE outcome_backfilled = FALSE
      AND last_price IS NOT NULL
      AND last_price > 0;

COMMENT ON INDEX trading.idx_dcs_outcome_backfill_pending IS
    'V025 (G7-08, 2026-04-24): Partial index for outcome_backfiller '
    'pending scan. Covers WHERE outcome_backfilled = FALSE AND last_price > 0; '
    'ORDER BY ts ASC LIMIT 200 picks first 200 entries directly. '
    'Expected ~187k rows (4-5% of full 770k table); ~10MB on-disk. '
    'Reduces BACKFILL_SQL pending CTE from 1.5s cold seq-scan to <50ms.';
