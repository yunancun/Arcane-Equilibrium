-- ============================================================
-- V033: Strategy-name attribution cleanup — trading.fills.exit_reason
-- 策略名稱歸因清理 — trading.fills.exit_reason
-- Created 2026-04-29 per PA design report
-- `2026-04-29--strategy_name_attribution_cleanup_design.md` §4 W1-T1
-- ============================================================
--
-- Purpose / 用途：
--   strategy_name 在 close path 上長期被當作「動態 trace 字串」使用
--   （`risk_close:TRAILING STOP: peak X% - current Y% = ... locked Z% ...`），
--   讓 24h distinct cardinality 升至 25+。新增 nullable TEXT 欄位
--   `exit_reason` 為動態 trace 的專屬欄位，並把 strategy_name 收斂為
--   5 個 enum-like 值（ma_crossover / bb_reversion / bb_breakout /
--   grid_trading / funding_arb）+ 系統路徑（unattributed:bybit_auto /
--   risk_close:halt_session）。
--
--   strategy_name has long been overloaded as a free-text trace field on
--   the close path (e.g. `risk_close:TRAILING STOP: peak X% - current Y%
--   = ... locked Z% ...`), pushing 24h distinct cardinality to 25+.
--   We add a nullable TEXT column `exit_reason` to carry the dynamic
--   trace, and converge strategy_name to the 5 enum-like entry strategy
--   names + system audit paths.
--
-- Semantics / 語義：
--   strategy_name (post-V033 invariant)
--     entry path → 5 enum-like values:
--       ma_crossover / bb_reversion / bb_breakout / grid_trading / funding_arb
--     close path (strategy-driven exit) → same 5 values (entry attribution)
--     close path (risk-driven exit)     → same 5 values (entry attribution)
--     close path (halt session)         → "risk_close:halt_session" (special)
--     close path (unattributed audit)   → "unattributed:bybit_auto"
--
--   exit_reason (new)
--     entry path → NULL
--     close path → free-text reason ("TRAILING STOP: peak X%..." / "phys_lock_gate4_giveback" / ...)
--     unattributed audit → NULL (existing audit row has no reason text)
--     historical row (pre-V033) → NULL (legacy strategy_name still carries trace; LIKE-based healthcheck still works)
--
-- Backwards compatibility / 向後相容：
--   - ADD COLUMN IF NOT EXISTS → 歷史 ~263k row 的 exit_reason 為 NULL
--   - prefix-LIKE healthcheck 對歷史 row 仍命中 strategy_name；新 row
--     需走 (strategy_name LIKE ... OR exit_reason LIKE ...) 雙語法（W1-T4）
--   - V031 mlde_edge_training_rows view 讀 trading.intents 不受影響
--
-- Rollback / 回滾：
--   ALTER TABLE trading.fills DROP COLUMN IF EXISTS exit_reason;
--   DROP INDEX IF EXISTS trading.idx_fills_exit_reason_prefix;
--
-- TimescaleDB note / TimescaleDB 備註：
--   ADD COLUMN 對 hypertable 是 metadata-only 改動（不 rewrite chunks），
--   263k row 大表友善。partial index 建立採 IF NOT EXISTS 同樣 idempotent。
--
-- Related migrations / 關聯：
--   V021 trading.fills.exit_source     ← Combine Layer ExitSource tag
--   V028 trading.fills.* execution     ← reference_price / slippage_bps 等
--   V032 mlde_demo_param_applications  ← 上一個 V### migration

-- ------------------------------------------------------------
-- Schema Guard A — verify trading.fills exists with required cols
-- Schema Guard A — 驗證 trading.fills 存在且必要欄位俱在
-- ------------------------------------------------------------
-- Why / 為何：
--   trading.fills 是核心 hypertable，由 V003 / V008 / V015 / V021 /
--   V028 / V029 等多次 ALTER 累積而來。本 migration 假設先前所有
--   migration 已套用且 column shape 正確；若 (例如) V021 從未 land、
--   exit_source 缺席，下面的 ADD COLUMN exit_reason 仍會成功，但
--   下游 trading_writer.rs INSERT 會在 batch flush 時報 column does
--   not exist 並失敗。提前 RAISE 比 silent skip 安全。
--
--   trading.fills is the core hypertable, accreted by V003 / V008 /
--   V015 / V021 / V028 / V029 etc. This migration assumes prior
--   migrations landed and column shape is correct; if e.g. V021 never
--   landed, ADD COLUMN exit_reason still succeeds but downstream
--   trading_writer.rs INSERT will fail at batch flush time with
--   "column does not exist". RAISE early is safer than silent skip.
--
-- Template source: sql/migrations/templates/schema_guard_template.sql § Guard A
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'trading'
          AND table_name   = 'fills'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts', 'fill_id', 'order_id', 'symbol', 'side',
            'qty', 'price', 'fee', 'realized_pnl',
            'strategy_name', 'context_id', 'engine_mode',
            'entry_context_id', 'exit_source'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'trading'
              AND table_name   = 'fills'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: trading.fills exists but missing required columns: %. '
                'Prior migration likely failed (V003/V008/V015/V021/V028); resolve '
                'legacy schema (re-apply prior migrations) before V033.',
                v_missing;
        END IF;
    ELSE
        -- trading.fills should always exist by V033; absence = bootstrap broken.
        -- 到 V033 時 trading.fills 必存在；缺席代表 bootstrap 損壞。
        RAISE EXCEPTION
            'schema_guard A: trading.fills does not exist — V003 was never applied. '
            'Re-bootstrap DB (helper_scripts/linux_bootstrap_db.sh --apply) before V033.';
    END IF;
END $$;

-- ------------------------------------------------------------
-- Schema Guard B — if exit_reason already exists, must be TEXT
-- Schema Guard B — exit_reason 已存在時必為 TEXT
-- ------------------------------------------------------------
-- Why / 為何：
--   `ADD COLUMN IF NOT EXISTS` 在 column 已存在但 type 不對時靜默
--   跳過；下游 b.push_bind(exit_reason.as_deref()) 與 TEXT column 對
--   接，類型錯會在 batch INSERT 時報 type mismatch 而非建表時。提前
--   RAISE 讓部署失敗點上移到 migration apply 階段。
--
--   `ADD COLUMN IF NOT EXISTS` silently skips when column exists with
--   wrong type; downstream b.push_bind(exit_reason.as_deref()) expects
--   TEXT, type drift surfaces only at batch INSERT runtime.
--
-- Template source: sql/migrations/templates/schema_guard_template.sql § Guard B
DO $$
DECLARE
    v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading'
      AND table_name   = 'fills'
      AND column_name  = 'exit_reason';

    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.exit_reason exists as type %, expected text. '
            'Legacy drift detected — resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V033.',
            v_actual;
    END IF;
END $$;

-- ------------------------------------------------------------
-- 1. Add column (nullable TEXT) / 加欄位（可 NULL TEXT）
-- ------------------------------------------------------------
-- nullable 設計：
--   - entry path fill 永 NULL
--   - 歷史 ~263k row 永 NULL（legacy strategy_name 自帶 trace）
--   - 不變式由 trading_writer.rs / build_close_tags 雙端維護
--   - W1-T4 healthcheck [39] exit_reason_coverage 驗 close path 必填
--
-- Nullable design:
--   - entry path fills always NULL
--   - historical rows (~263k) always NULL (legacy trace lives in strategy_name)
--   - invariant maintained by trading_writer.rs + build_close_tags helper
--   - W1-T4 healthcheck [39] exit_reason_coverage validates close path coverage
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS exit_reason TEXT;

-- ------------------------------------------------------------
-- 2. Partial index for exit_reason prefix queries
--    Healthcheck dual-syntax 升級後（W1-T4）會用
--    `... LIKE 'phys_lock_%'` 等 pattern 查 close path；
--    text_pattern_ops 對 LIKE prefix 有 B-tree 加速。
--    Predicate WHERE exit_reason IS NOT NULL：歷史 100% NULL +
--    entry path 100% NULL → 索引只覆蓋 close fills，省空間。
--
-- Partial index for exit_reason LIKE-prefix queries (W1-T4 dual-syntax
-- healthcheck). text_pattern_ops accelerates B-tree LIKE prefix.
-- Partial WHERE NOT NULL: only close fills enter the index, saving
-- disk vs full index over historical NULL-heavy data.
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fills_exit_reason_prefix
    ON trading.fills (exit_reason text_pattern_ops)
    WHERE exit_reason IS NOT NULL;

-- ------------------------------------------------------------
-- 3. Column / index COMMENTs (bilingual)
--    雙語 COMMENT
-- ------------------------------------------------------------
COMMENT ON COLUMN trading.fills.exit_reason IS
    'V033 (2026-04-29): Free-text exit reason for close-path fills. '
    'NULL for entry fills, historical rows, and unattributed audit rows. '
    'Examples: "TRAILING STOP: peak 8.46% - current 6.46% = ...", '
    '"phys_lock_gate4_giveback", "ma_reverse_cross", "fast_track". '
    'Companion to strategy_name which is now restricted to 5 enum-like '
    'values (ma_crossover/bb_reversion/bb_breakout/grid_trading/funding_arb) '
    '+ system paths (unattributed:bybit_auto / risk_close:halt_session). '
    '/ V033（2026-04-29）：close path fill 的自由文字退場原因；entry fill / '
    '歷史 row / unattributed audit row 為 NULL。strategy_name 同步收斂為 '
    '5 個 enum-like 入場策略名 + 系統路徑。';

COMMENT ON INDEX trading.idx_fills_exit_reason_prefix IS
    'V033 (2026-04-29): Partial B-tree index on exit_reason with '
    'text_pattern_ops for LIKE-prefix queries by W1-T4 healthcheck. '
    'Predicate WHERE NOT NULL keeps the index small (only close fills enter). '
    '/ V033 (2026-04-29)：exit_reason 的 partial B-tree (text_pattern_ops) 索引， '
    '供 W1-T4 healthcheck LIKE-prefix 查詢加速；partial WHERE NOT NULL 限制 '
    '在 close fill 上，索引大小小於全表索引。';
