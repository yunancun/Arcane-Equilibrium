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

DROP INDEX IF EXISTS learning.idx_strategist_applied_engine_strategy_ts;

CREATE INDEX idx_strategist_applied_engine_strategy_ts
    ON learning.strategist_applied_params
    (engine_mode, strategy_name, applied_at_ms DESC, id DESC);

COMMENT ON INDEX learning.idx_strategist_applied_engine_strategy_ts IS
    'STRATEGIST-PERSIST-TIE-BREAK-1 (2026-04-23): (engine_mode, strategy_name, '
    'applied_at_ms DESC, id DESC) — DISTINCT ON restore query deterministic '
    'tie-break for concurrent writers under Phase 5+ promote flow.';
