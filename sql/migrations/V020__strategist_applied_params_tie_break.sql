-- V020: STRATEGIST-PERSIST-TIE-BREAK-1 (2026-04-23, FA H1 post-commit audit)
-- Add `id DESC` tie-break to idx_strategist_applied_engine_strategy_ts so
-- concurrent writers (Strategist auto cycle + manual_promote) writing rows
-- with identical applied_at_ms get a deterministic order (highest id wins).
-- Without this tie-break, DISTINCT ON falls back to PG physical row order
-- (not stable; depends on page layout), which would intermittently restore
-- the older of two concurrent applies at engine startup.
--
-- V020：STRATEGIST-PERSIST-TIE-BREAK-1（2026-04-23，FA H1 post-commit audit）
-- 為 idx_strategist_applied_engine_strategy_ts 末加 `id DESC` tie-break：
-- 並發 writer（Strategist 自動 cycle + manual_promote）若寫入同 ms 的 row，
-- DISTINCT ON 查詢可確定取 id 最大者（最晚寫入）。無此 tie-break 時
-- PG 回 physical row order（page layout 決定，非穩定），會間歇性在 engine
-- startup restore 時取到兩個並發 apply 中較舊的一筆。
--
-- Phase 5+ STRATEGIST-PROMOTE-TRIGGER-1 上線前必修（當前 Demo 單 writer
-- 不觸發此 race，但促升接通後 manual_promote + 自動 cycle 並發會活化）。

-- ------------------------------------------------------------
-- Schema Guard A (retrofit 2026-04-24, V023 postmortem · G6-03 Wave 1)
-- ------------------------------------------------------------
-- Why on V020 / 為何 V020 也要加：
--   V020 has no CREATE TABLE — only DROP + CREATE INDEX on
--   `learning.strategist_applied_params`. If the parent table is
--   missing or carries a legacy stub without the indexed columns
--   (engine_mode / strategy_name / applied_at_ms / id), the DROP /
--   CREATE INDEX below will fail with low-signal errors ("relation
--   does not exist" or "column does not exist"). Guard A on the
--   parent table fails fast with a high-signal message pointing
--   at V019 drift.
--
--   V020 無 CREATE TABLE，僅針對 `learning.strategist_applied_params`
--   做 DROP + CREATE INDEX。若父表缺失或為缺欄位的 legacy stub
--   （engine_mode / strategy_name / applied_at_ms / id），下方
--   DROP / CREATE INDEX 會以低信噪錯誤失敗（"relation does not exist"
--   或 "column does not exist"）。在父表加 Guard A 提前拋高信噪
--   錯誤，明確指向 V019 drift。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name   = 'strategist_applied_params'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'engine_mode', 'strategy_name', 'applied_at_ms'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'strategist_applied_params'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: learning.strategist_applied_params exists but missing index columns required by V020 tie-break: %. '
                'V019 likely drifted (legacy stub or partial apply). '
                'Resolve V019 schema (DROP + re-apply V019) before re-applying V020.',
                v_missing;
        END IF;
    ELSE
        RAISE EXCEPTION
            'schema_guard A: learning.strategist_applied_params does not exist. '
            'V019 must be applied successfully before V020 can rebuild its tie-break index. '
            'Run V019 first, then re-apply V020.';
    END IF;
END $$;

DROP INDEX IF EXISTS learning.idx_strategist_applied_engine_strategy_ts;

CREATE INDEX idx_strategist_applied_engine_strategy_ts
    ON learning.strategist_applied_params
    (engine_mode, strategy_name, applied_at_ms DESC, id DESC);

COMMENT ON INDEX learning.idx_strategist_applied_engine_strategy_ts IS
    'STRATEGIST-PERSIST-TIE-BREAK-1 (2026-04-23): (engine_mode, strategy_name, '
    'applied_at_ms DESC, id DESC) — DISTINCT ON restore query deterministic '
    'tie-break for concurrent writers under Phase 5+ promote flow.';
