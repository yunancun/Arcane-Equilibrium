-- ============================================================================
-- V013 — Weekly review log for Phase 4 operator approval workflow
-- V013 — Phase 4 operator 批准流程的週度審查日誌
-- ============================================================================
--
-- Phase 4 子任務 4-20.
--
-- Each row represents a Phase 4 weekly review cycle: an automated
-- generator (program_code/ml_training/weekly_report_generator.py) inserts
-- a row with metrics + report path; the operator later UPDATEs approved
-- (TRUE / FALSE) via /api/v1/phase4/weekly_review/{approve,reject}.
--
-- 每行代表 Phase 4 一個週度審查週期：自動生成器
-- (weekly_report_generator.py) 插入一行帶 metrics + 報告路徑；
-- operator 之後透過 /api/v1/phase4/weekly_review/{approve,reject}
-- UPDATE approved (TRUE / FALSE)。
-- ============================================================================

CREATE TABLE IF NOT EXISTS learning.weekly_review_log (
    review_id        SERIAL PRIMARY KEY,
    week_iso         TEXT NOT NULL,
    generated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved         BOOLEAN,
    approved_at      TIMESTAMPTZ,
    approved_by      TEXT,
    decision_notes   TEXT,
    metrics_json     JSONB NOT NULL,
    report_md_path   TEXT
);

COMMENT ON TABLE learning.weekly_review_log IS
    'Phase 4 weekly review log: operator approves or rejects each week learning cycle';
COMMENT ON COLUMN learning.weekly_review_log.week_iso IS
    'ISO week identifier (e.g., 2026-W15) / ISO 週識別字 (例如 2026-W15)';
COMMENT ON COLUMN learning.weekly_review_log.approved IS
    'NULL = pending operator review; TRUE = approved; FALSE = rejected';
COMMENT ON COLUMN learning.weekly_review_log.metrics_json IS
    'DoD A/C/E metrics + cost + module health snapshot at generation time';

CREATE INDEX IF NOT EXISTS idx_weekly_review_pending
    ON learning.weekly_review_log (week_iso) WHERE approved IS NULL;

-- 完成 / Done
