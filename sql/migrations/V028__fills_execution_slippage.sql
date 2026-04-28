-- V028: Store dispatch-time execution references and signed adverse slippage.
-- V028：記錄送單時刻參考價與有符號 adverse slippage。

ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS reference_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS reference_ts_ms BIGINT,
    ADD COLUMN IF NOT EXISTS reference_source TEXT,
    ADD COLUMN IF NOT EXISTS slippage_bps DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS liquidity_role TEXT,
    ADD COLUMN IF NOT EXISTS fill_latency_ms BIGINT;

COMMENT ON COLUMN trading.fills.reference_price IS
    'Dispatch-time execution reference price. For taker fills this is same-side BBO when available.';
COMMENT ON COLUMN trading.fills.reference_ts_ms IS
    'Millisecond timestamp of reference_price.';
COMMENT ON COLUMN trading.fills.reference_source IS
    'Reference source such as bbo_same_side or dispatch_last_fallback.';
COMMENT ON COLUMN trading.fills.slippage_bps IS
    'Signed adverse execution slippage in basis points. Positive is worse; NULL when not safely attributable.';
COMMENT ON COLUMN trading.fills.liquidity_role IS
    'Liquidity role for execution attribution: maker, taker, unknown, or paper_sim.';
COMMENT ON COLUMN trading.fills.fill_latency_ms IS
    'Milliseconds between local order registration and exchange execution update.';

CREATE INDEX IF NOT EXISTS idx_fills_execution_slippage
    ON trading.fills (engine_mode, symbol, ts DESC)
    WHERE slippage_bps IS NOT NULL;
