-- ============================================================
-- V011 — Phase 4 (4-11): DL-3 Foundation Model features table
-- V011 — Phase 4 子任務 4-11：DL-3 基礎模型特徵表
-- ============================================================
--
-- Source / 來源:
--   docs/references/2026-04-06--phase4_execution_plan_v2.md §4-11
--   docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md DL-3
--
-- Purpose / 用途:
--   Persist zero-shot forecast outputs from time-series foundation models
--   (TimesFM / Chronos) for later A/B comparison (4-12) and Go-No-Go (4-13).
--   Fail-soft writes: rows may have ok=false with error_msg populated.
--   保存來自時序基礎模型（TimesFM / Chronos）的 zero-shot 預測輸出，
--   供後續 A/B 比較（4-12）與 Go-No-Go（4-13）使用。
--   Fail-soft 寫入：行可能 ok=false 並帶 error_msg。
--
-- Notes / 備註:
--   - Idempotent: IF NOT EXISTS everywhere. Re-running V011 is a no-op.
--   - Hypertable with 7-day chunks aligns with other learning.* tables.
--   - 全部 IF NOT EXISTS，可重跑。Hypertable 7 天 chunk 與其他 learning.* 對齊。
-- ============================================================

CREATE TABLE IF NOT EXISTS learning.foundation_model_features (
    time         TIMESTAMPTZ NOT NULL,
    symbol       TEXT NOT NULL,
    model        TEXT NOT NULL,           -- 'timesfm-1.0-200m' / 'chronos-t5-tiny' / etc
    horizon_min  INT NOT NULL,            -- forecast horizon in minutes / 預測時程（分鐘）
    forecast     JSONB NOT NULL,          -- {pred_mean: [], pred_std: [], ...}
    latency_ms   INT NOT NULL,
    ok           BOOLEAN NOT NULL DEFAULT TRUE,
    error_msg    TEXT
);

-- Convert to TimescaleDB hypertable if extension available / 若 TimescaleDB 可用則轉為 hypertable
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'learning.foundation_model_features',
            'time',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_fmf_symbol_time
    ON learning.foundation_model_features (symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_fmf_model_time
    ON learning.foundation_model_features (model, time DESC);
