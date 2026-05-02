-- V028: Store dispatch-time execution references and signed adverse slippage.
-- V028：記錄送單時刻參考價與有符號 adverse slippage。
--
-- Retrofit (AUDIT-2026-05-02-P1-1, 2026-05-02): added Guard A + 6 Guard B
-- blocks per CLAUDE.md §七 (V023 silent-noop postmortem). 4-day cold audit
-- found V028 missing these guards; ALTER TABLE ADD COLUMN IF NOT EXISTS
-- silently skips when an existing column has the wrong type, leaving
-- downstream writers (trading_writer.rs / shadow_exit_writer.rs) to fail at
-- batch flush with confusing "type mismatch" errors. Guards surface the
-- drift at migration apply time instead.
--
-- 回補（AUDIT-2026-05-02-P1-1，2026-05-02）：依 CLAUDE.md §七（V023 靜默
-- no-op 事後調查）補上 Guard A + 6 個 Guard B。CC 4 天 cold audit 發現 V028
-- 漏 guard；ALTER TABLE ADD COLUMN IF NOT EXISTS 在欄位已存在但型別錯時
-- 會靜默跳過，等下游 writer batch flush 才報難解的「type mismatch」。
-- 補上 guard 把失敗點上移到 migration apply 階段。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A & Guard B
-- Reference implementations / 參考實作：
--   V021 / V023 / V027 / V033

-- ------------------------------------------------------------
-- Schema Guard A — verify trading.fills exists with required cols
-- Schema Guard A — 驗證 trading.fills 存在且必要欄位俱在
-- ------------------------------------------------------------
-- Why / 為何：
--   trading.fills is the core hypertable accreted by V003 / V008 / V015 /
--   V017 / V021 etc. V028 only ALTERs it, so the parent must already exist
--   with the columns earlier migrations introduced. If a prior migration was
--   never applied, RAISE early — silent ADD COLUMN onto an incomplete
--   parent leaves bootstrap broken in subtle ways.
--
--   trading.fills 是 V003/V008/V015/V017/V021 等多次 ALTER 累積的核心 hypertable。
--   V028 只 ALTER 不 CREATE，父表必須先存在且帶之前 migration 引入的欄位；
--   若前面 migration 沒套用，立即 RAISE，比靜默 ADD COLUMN 安全。
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
                'Prior migration likely failed (V003/V008/V015/V017/V021); resolve '
                'legacy schema (re-apply prior migrations) before V028.',
                v_missing;
        END IF;
    ELSE
        -- trading.fills must exist by V028; absence = bootstrap broken.
        -- 到 V028 時 trading.fills 必存在；缺席代表 bootstrap 損壞。
        RAISE EXCEPTION
            'schema_guard A: trading.fills does not exist — V003 was never applied. '
            'Re-bootstrap DB (helper_scripts/linux_bootstrap_db.sh --apply) before V028.';
    END IF;
END $$;

-- ------------------------------------------------------------
-- Schema Guard B (×6) — verify each ADD COLUMN target type when present
-- Schema Guard B (×6) — 6 個 ADD COLUMN 目標型別已存在時的型別驗證
-- ------------------------------------------------------------
-- One DO block per column to keep diagnostic messages self-explanatory
-- (mirrors V021/V033 style). All blocks are no-op when the column is
-- absent — the ALTER TABLE below will create them with the correct type.
--
-- 每欄一個 DO block，diagnostic 訊息自說明（鏡 V021/V033 風格）；欄位不
-- 存在時皆 no-op，下方 ALTER TABLE 會以正確型別建立。

-- Guard B-1: reference_price must be double precision
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'reference_price';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.reference_price is %, expected double precision. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V028.',
            v_actual;
    END IF;
END $$;

-- Guard B-2: reference_ts_ms must be bigint
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'reference_ts_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.reference_ts_ms is %, expected bigint. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V028.',
            v_actual;
    END IF;
END $$;

-- Guard B-3: reference_source must be text
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'reference_source';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.reference_source is %, expected text. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V028.',
            v_actual;
    END IF;
END $$;

-- Guard B-4: slippage_bps must be double precision
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'slippage_bps';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.slippage_bps is %, expected double precision. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V028.',
            v_actual;
    END IF;
END $$;

-- Guard B-5: liquidity_role must be text
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'liquidity_role';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.liquidity_role is %, expected text. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V028.',
            v_actual;
    END IF;
END $$;

-- Guard B-6: fill_latency_ms must be bigint
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'fill_latency_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.fill_latency_ms is %, expected bigint. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V028.',
            v_actual;
    END IF;
END $$;

-- ------------------------------------------------------------
-- Original V028 body (unchanged) / 原 V028 主體（未動）
-- ------------------------------------------------------------
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
