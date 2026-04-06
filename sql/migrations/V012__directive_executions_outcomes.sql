-- ============================================================================
-- V012 — Add outcome tracking columns to learning.directive_executions
-- V012 — 為 learning.directive_executions 加上 outcome 追蹤欄位
-- ============================================================================
--
-- Phase 4 子任務 4-03 / 4-02 follow-up.
--
-- Background:
--   V004 created `learning.directive_executions` with the columns
--   (execution_id, directive_id, ts, action_taken, result jsonb, success).
--   The Phase 4 spec calls for first-class outcome columns (PnL / Sharpe at
--   multiple horizons + computed_at + strategy_scope) so the Teacher Card
--   and offline analysis can query without JSONB extraction.
--
--   4-02 stored outcome details inside `result` JSONB; this migration adds
--   first-class columns and 4-03 backfills + computes new rows on a periodic
--   sweep.
--
-- 背景：
--   V004 建立的 `learning.directive_executions` 只有 (execution_id, directive_id,
--   ts, action_taken, result jsonb, success) 欄位。Phase 4 spec 要求 outcome
--   一級欄位（PnL/Sharpe 多 horizon + computed_at + strategy_scope），讓 Teacher
--   Card 與離線分析免去 JSONB 解析。
--
--   4-02 把 outcome 細節塞進 `result` JSONB；本 migration 加一級欄位，
--   4-03 做 backfill + 定期 sweep 計算新行。
-- ============================================================================

ALTER TABLE learning.directive_executions
    ADD COLUMN IF NOT EXISTS outcome_pnl_1h     REAL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS outcome_pnl_4h     REAL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS outcome_pnl_24h    REAL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS outcome_pnl_7d     REAL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS outcome_sharpe_24h REAL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS outcome_computed_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS strategy_scope     TEXT DEFAULT NULL;

COMMENT ON COLUMN learning.directive_executions.outcome_pnl_1h IS
    'realized PnL in the 1h window after directive applied (USD) / 套用後 1 小時內實現 PnL (美元)';
COMMENT ON COLUMN learning.directive_executions.outcome_pnl_4h IS
    'realized PnL in the 4h window after directive applied (USD) / 套用後 4 小時內實現 PnL (美元)';
COMMENT ON COLUMN learning.directive_executions.outcome_pnl_24h IS
    'realized PnL in the 24h window after directive applied (USD) / 套用後 24 小時內實現 PnL (美元)';
COMMENT ON COLUMN learning.directive_executions.outcome_pnl_7d IS
    'realized PnL in the 7d window after directive applied (USD) / 套用後 7 天內實現 PnL (美元)';
COMMENT ON COLUMN learning.directive_executions.outcome_sharpe_24h IS
    '24h hourly-Sharpe over realized returns after directive applied / 套用後 24 小時內以每小時報酬計算的 Sharpe';
COMMENT ON COLUMN learning.directive_executions.outcome_computed_at IS
    'when the outcome columns were last computed (NULL = pending) / outcome 欄位上次計算時間 (NULL = 待計算)';
COMMENT ON COLUMN learning.directive_executions.strategy_scope IS
    'strategy name targeted by the directive (used to filter trading.fills for outcome) / directive 針對的策略名稱 (用於從 trading.fills 過濾 outcome)';

-- ============================================================================
-- Index: pending outcomes (outcome_computed_at IS NULL)
-- 索引：待計算 outcome (outcome_computed_at IS NULL)
-- Used by the Rust outcome_tracker sweep to find rows that need processing.
-- 給 Rust outcome_tracker sweep 用，找出需要處理的 row。
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_directive_executions_pending_outcomes
    ON learning.directive_executions (ts)
    WHERE outcome_computed_at IS NULL;

-- ============================================================================
-- 完成 / Done
-- ============================================================================
