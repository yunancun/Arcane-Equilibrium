-- ============================================================
-- V018: paper_state_checkpoint — Cross-Restart Drawdown Continuity
-- 跨重啟 Drawdown 連續性 — P1-5 DEMO-REBOOT-PNL-RESET-1 方案 A2
--
-- MODULE_NOTE (EN): Persists peak_balance + session_start_ts per engine_mode
--   so PaperState can rebuild its drawdown reference on restart instead of
--   resetting to the restored balance (which hides live drawdown breaches
--   across an engine crash/restart). Reset semantics (A2): operator-driven
--   only — an IPC handler + FastAPI route DELETE the row and log to
--   change_audit_log (Root Principle #8 trade explainability).
-- MODULE_NOTE (中): 為每個 engine_mode 持久化 peak_balance + session_start_ts，
--   讓 PaperState 重啟後重建 drawdown 參考點，而不是重置到 restored balance
--   （後者會讓 live drawdown breach 被重啟洗掉）。重置語義（A2）：僅 operator
--   手動觸發——IPC handler + FastAPI 路由 DELETE 行並寫 change_audit_log（根原則
--   #8 交易可解釋）。
--
-- Schema design rationale:
--   * PK = engine_mode — only ever 4 rows max (paper/demo/live/live_demo).
--     No time dimension; not a hypertable.
--   * peak_balance stored as DOUBLE PRECISION to match PaperState.balance.
--   * session_start_ts is WHEN the current equity curve began — preserved
--     across restarts until operator resets.
--   * updated_at uses NOW() trigger-free; writers bump on every UPSERT.
--
-- Idempotent: IF NOT EXISTS so re-running is safe.
--
-- Source: TODO §P1-5 (DEMO-REBOOT-PNL-RESET-1 方案 A2)
-- ============================================================

CREATE TABLE IF NOT EXISTS trading.paper_state_checkpoint (
    engine_mode      TEXT PRIMARY KEY,
    peak_balance     DOUBLE PRECISION NOT NULL,
    session_start_ts TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT paper_state_checkpoint_engine_mode_check
        CHECK (engine_mode IN ('paper', 'demo', 'live', 'live_demo')),
    CONSTRAINT paper_state_checkpoint_peak_nonneg
        CHECK (peak_balance >= 0)
);

COMMENT ON TABLE trading.paper_state_checkpoint IS
    'Per-engine peak_balance + session_start_ts for cross-restart drawdown continuity (P1-5 A2). '
    '每個 engine_mode 跨重啟保留 peak_balance 與 session_start_ts。'
    'Reset semantics: operator-driven only (IPC reset_drawdown_baseline). '
    '重置語義：僅 operator 手動觸發（IPC reset_drawdown_baseline）。';

COMMENT ON COLUMN trading.paper_state_checkpoint.engine_mode IS
    'One of paper/demo/live/live_demo. / paper/demo/live/live_demo 之一。';

COMMENT ON COLUMN trading.paper_state_checkpoint.peak_balance IS
    'Highest balance ever observed in this session. Drives drawdown_pct calc. / '
    '本 session 觀察到的歷史最高 balance；驅動 drawdown_pct 計算。';

COMMENT ON COLUMN trading.paper_state_checkpoint.session_start_ts IS
    'Wall-clock time when the current equity curve began. Reset only by operator. / '
    '當前 equity curve 起始時刻；僅 operator 重置時更新。';
