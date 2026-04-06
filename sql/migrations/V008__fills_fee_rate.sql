-- ============================================================
-- V008 — Add fee_rate column to trading.fills
-- V008 — 為 trading.fills 添加 fee_rate 列
-- ============================================================
--
-- Adds the per-symbol effective taker fee rate captured at
-- execution time. Implicit rate is recoverable via fee/(qty*price)
-- but an explicit column simplifies cost-analysis queries and
-- VIP-tier audits.
-- 顯式記錄成交時的 per-symbol 有效 taker 費率。
-- ============================================================

ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS fee_rate REAL DEFAULT 0;

COMMENT ON COLUMN trading.fills.fee_rate IS
    'effective taker fee rate at execution time (Bybit per-symbol, 0.00055 = 0.055%)';
