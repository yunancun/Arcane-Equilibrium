-- ============================================================
-- V015: Engine Mode Separation — Multi-Engine Data Isolation
-- 引擎模式分離 — 多引擎數據隔離
--
-- Design: Signal Diamond — market data + signals shared,
--         intents/fills/orders/positions per-mode (paper/demo/live).
-- 設計：Signal Diamond — 市場數據 + 信號共享，
--       意圖/成交/訂單/持倉按模式分離（paper/demo/live）。
--
-- Source: DB_TODO.md Phase 1
-- ============================================================

-- ── trading.intents ─────────────────────────────────────────
ALTER TABLE trading.intents
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';
CREATE INDEX IF NOT EXISTS idx_intents_engine_mode_ts
    ON trading.intents (engine_mode, ts DESC);

-- ── trading.risk_verdicts ───────────────────────────────────
ALTER TABLE trading.risk_verdicts
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';
CREATE INDEX IF NOT EXISTS idx_risk_verdicts_engine_mode_ts
    ON trading.risk_verdicts (engine_mode, ts DESC);

-- ── trading.orders ──────────────────────────────────────────
-- DEPRECATED: is_paper column retained for Grafana backward compat.
-- 已棄用：is_paper 列保留以兼容 Grafana。
ALTER TABLE trading.orders
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';
CREATE INDEX IF NOT EXISTS idx_orders_engine_mode_ts
    ON trading.orders (engine_mode, ts DESC);
COMMENT ON COLUMN trading.orders.is_paper IS 'DEPRECATED — use engine_mode instead / 已棄用 — 改用 engine_mode';

-- ── trading.order_state_changes ─────────────────────────────
ALTER TABLE trading.order_state_changes
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';
CREATE INDEX IF NOT EXISTS idx_order_state_changes_engine_mode_ts
    ON trading.order_state_changes (engine_mode, ts DESC);

-- ── trading.fills ───────────────────────────────────────────
-- DEPRECATED: is_paper column retained for Grafana backward compat.
-- 已棄用：is_paper 列保留以兼容 Grafana。
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';
CREATE INDEX IF NOT EXISTS idx_fills_engine_mode_ts
    ON trading.fills (engine_mode, ts DESC);
COMMENT ON COLUMN trading.fills.is_paper IS 'DEPRECATED — use engine_mode instead / 已棄用 — 改用 engine_mode';

-- ── trading.position_snapshots ──────────────────────────────
-- DEPRECATED: is_paper column retained for Grafana backward compat.
-- 已棄用：is_paper 列保留以兼容 Grafana。
ALTER TABLE trading.position_snapshots
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';
CREATE INDEX IF NOT EXISTS idx_position_snapshots_engine_mode_ts
    ON trading.position_snapshots (engine_mode, ts DESC);
COMMENT ON COLUMN trading.position_snapshots.is_paper IS 'DEPRECATED — use engine_mode instead / 已棄用 — 改用 engine_mode';

-- ── trading.decision_context_snapshots ──────────────────────
ALTER TABLE trading.decision_context_snapshots
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';
CREATE INDEX IF NOT EXISTS idx_decision_context_engine_mode_ts
    ON trading.decision_context_snapshots (engine_mode, ts DESC);

-- ── trading.decision_outcomes ───────────────────────────────
-- No writer exists yet; column added for future correct wiring.
-- 尚無 writer；預先加列以備未來接線。
ALTER TABLE trading.decision_outcomes
    ADD COLUMN IF NOT EXISTS engine_mode TEXT NOT NULL DEFAULT 'paper';

-- ── agent.ai_invocations (nullable — AI calls may predate mode) ─
ALTER TABLE agent.ai_invocations
    ADD COLUMN IF NOT EXISTS engine_mode TEXT DEFAULT NULL;

-- ============================================================
-- Verification / 驗證
-- ============================================================
-- SELECT column_name FROM information_schema.columns
--   WHERE table_schema = 'trading' AND table_name = 'intents'
--   AND column_name = 'engine_mode';
-- Expected: 1 row
