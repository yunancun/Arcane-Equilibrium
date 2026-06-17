-- V145: Add maker adverse-selection markout column to trading.fills.
-- V145：為 trading.fills 增加 maker adverse-selection markout 欄位。
--
-- 背景（為何需要本欄）：
--   maker fill 的 slippage_bps 歷史上 756/756 全 NULL，根因是 fill recording
--   path（loop_exchange.rs）以 `if liquidity_role=="taker"` 把 maker markout
--   gate 掉。markout 純函數 adverse_slippage_bps 早已存在且 signed-by-side，
--   只是被那一行 gate 關閉。本 migration 解開該 gate 的下游欄位需求。
--
--   裁決：新欄 maker_markout_bps，**不複用** slippage_bps。兩者語意正交：
--     - slippage_bps   = taker 執行劣勢（穿越 spread 的代價）。
--     - maker_markout_bps = maker adverse selection（掛單成交後 mid 朝對我
--                            不利方向走多少；正值=被 informed flow 逆選）。
--   混在同一欄會讓下游 cost-floor 分析與 market-making edge verdict 雙重歧義。
--   slippage_bps 對 maker 維持 NULL（誠實：maker 無「穿越 spread」執行滑點）；
--   maker_markout_bps 只在 liquidity_role=='maker' 的 fill 填值，taker 永遠 NULL。
--
--   無 backfill：歷史 maker fill 無 mid@submit 記錄，無法回填（誠實 NULL）；
--   本欄只前向採集。column 為 NULL-able additive，舊 binary 對它無感（不寫即
--   恆 NULL）→ migration 可先行 apply，binary rollback 安全。
--
-- 模板來源 / Template source：
--   sql/migrations/templates/schema_guard_template.sql § Guard A & Guard B
-- 參考實作 / Reference implementations：
--   V028（reference_price/slippage_bps/liquidity_role 同表同範式）

-- ------------------------------------------------------------
-- Schema Guard A — verify trading.fills exists with V028 baseline cols
-- Schema Guard A — 驗證 trading.fills 存在且帶 V028 baseline 欄位
-- ------------------------------------------------------------
-- Why / 為何：
--   本 migration 只 ALTER trading.fills（不 CREATE），且 maker_markout_bps 的
--   語意依賴 V028 引入的 slippage_bps / liquidity_role / reference_price 三欄
--   已就位（markout 寫入點與 slippage 寫入點按 liquidity_role 互斥分流）。
--   若這些前置欄缺席，代表 V028 未套用，立即 RAISE 比靜默 ADD COLUMN 安全。
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
            'ts', 'fill_id', 'symbol', 'engine_mode',
            'slippage_bps', 'liquidity_role', 'reference_price'
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
                'V028 baseline (slippage_bps/liquidity_role/reference_price) must be '
                'applied before V145.',
                v_missing;
        END IF;
    ELSE
        -- trading.fills must exist by V145; absence = bootstrap broken.
        -- 到 V145 時 trading.fills 必存在；缺席代表 bootstrap 損壞。
        RAISE EXCEPTION
            'schema_guard A: trading.fills does not exist — V003 was never applied. '
            'Re-bootstrap DB (helper_scripts/linux_bootstrap_db.sh --apply) before V145.';
    END IF;
END $$;

-- ------------------------------------------------------------
-- Schema Guard B — verify maker_markout_bps type when already present
-- Schema Guard B — maker_markout_bps 已存在時的型別驗證
-- ------------------------------------------------------------
-- ADD COLUMN IF NOT EXISTS 在欄位已存在但型別錯時會靜默跳過，等下游 writer
-- batch flush 才報難解的 type mismatch。Guard B 把失敗點上移到 apply 階段
-- （冪等 double-apply 下亦為 no-op）。
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'maker_markout_bps';
    IF v_actual IS NOT NULL AND v_actual <> 'double precision' THEN
        RAISE EXCEPTION
            'schema_guard B: trading.fills.maker_markout_bps is %, expected double precision. '
            'Resolve via ALTER COLUMN TYPE or DROP COLUMN + re-apply V145.',
            v_actual;
    END IF;
END $$;

-- ------------------------------------------------------------
-- Body / 主體
-- ------------------------------------------------------------
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS maker_markout_bps DOUBLE PRECISION;

COMMENT ON COLUMN trading.fills.maker_markout_bps IS
    'Signed adverse-selection markout in bps for maker fills (mid@submit vs fill price). '
    'Positive = adverse (informed flow); NULL for taker/paper fills.';

-- Hot-path index (Guard C 範式)：只索引非 NULL（=maker fill），用於 24h
-- maker-markout 分佈分析的 engine_mode/symbol 時序掃描。
CREATE INDEX IF NOT EXISTS idx_fills_maker_markout
    ON trading.fills (engine_mode, symbol, ts DESC)
    WHERE maker_markout_bps IS NOT NULL;
