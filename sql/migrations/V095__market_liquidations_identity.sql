-- ============================================================
-- V095: market.liquidations lossy idempotency correction
--
-- Purpose / 目的:
--   Align the liquidation row identity with Bybit `allLiquidation.{symbol}`
--   `data[]` item granularity. The old `(symbol, ts, side)` primary key can
--   collapse multiple same-ms same-side items. V095 preserves one row per
--   `(symbol, ts, side, qty, price)` without rewriting existing data.
--
-- Scope / 範圍:
--   - No production subscription enablement
--   - No data rewrite/backfill/truncate
--   - Drop only the old lossy primary key when it exactly equals
--     `(symbol, ts, side)`
--   - Add primary key `(symbol, ts, side, qty, price)`
--   - Add NOT VALID side CHECK for `Buy` / `Sell`
-- ============================================================

-- ============================================================
-- Guard A: market.liquidations must exist with V002 baseline columns
-- Guard A：market.liquidations 必須存在且 V002 baseline 欄位俱在
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'market' AND table_name = 'liquidations'
    ) THEN
        RAISE EXCEPTION
            'V095 Guard A FAIL: market.liquidations missing — V002 must have applied first. Re-check migration order.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY['ts', 'symbol', 'side', 'qty', 'price']) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'market'
          AND table_name = 'liquidations'
          AND column_name = c
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V095 Guard A FAIL: market.liquidations missing required columns: %. Resolve V002 schema drift before applying V095.',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- Guard B: existing column types and primary-key shape must be known
-- Guard B：欄位型別與既有主鍵形狀必須可識別
-- ============================================================
DO $$
DECLARE
    v_ts_type TEXT;
    v_symbol_type TEXT;
    v_side_type TEXT;
    v_qty_type TEXT;
    v_price_type TEXT;
    v_pk_cols TEXT[];
BEGIN
    SELECT data_type INTO v_ts_type
    FROM information_schema.columns
    WHERE table_schema = 'market'
      AND table_name = 'liquidations'
      AND column_name = 'ts';

    SELECT data_type INTO v_symbol_type
    FROM information_schema.columns
    WHERE table_schema = 'market'
      AND table_name = 'liquidations'
      AND column_name = 'symbol';

    SELECT data_type INTO v_side_type
    FROM information_schema.columns
    WHERE table_schema = 'market'
      AND table_name = 'liquidations'
      AND column_name = 'side';

    SELECT data_type INTO v_qty_type
    FROM information_schema.columns
    WHERE table_schema = 'market'
      AND table_name = 'liquidations'
      AND column_name = 'qty';

    SELECT data_type INTO v_price_type
    FROM information_schema.columns
    WHERE table_schema = 'market'
      AND table_name = 'liquidations'
      AND column_name = 'price';

    IF v_ts_type IS DISTINCT FROM 'timestamp with time zone'
       OR v_symbol_type IS DISTINCT FROM 'text'
       OR v_side_type IS DISTINCT FROM 'text'
       OR v_qty_type IS DISTINCT FROM 'real'
       OR v_price_type IS DISTINCT FROM 'real' THEN
        RAISE EXCEPTION
            'V095 Guard B FAIL: market.liquidations type drift. Expected ts=timestamptz, symbol=text, side=text, qty=real, price=real; got ts=%, symbol=%, side=%, qty=%, price=%.',
            v_ts_type, v_symbol_type, v_side_type, v_qty_type, v_price_type;
    END IF;

    SELECT array_agg(a.attname ORDER BY x.ord) INTO v_pk_cols
    FROM pg_constraint c
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS x(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
    WHERE c.conrelid = 'market.liquidations'::regclass
      AND c.contype = 'p';

    IF v_pk_cols IS NOT NULL
       AND v_pk_cols <> ARRAY['symbol', 'ts', 'side']
       AND v_pk_cols <> ARRAY['symbol', 'ts', 'side', 'qty', 'price'] THEN
        RAISE EXCEPTION
            'V095 Guard B FAIL: market.liquidations primary key has unexpected columns %. Expected old (symbol, ts, side) or new (symbol, ts, side, qty, price).',
            v_pk_cols;
    END IF;
END $$;

-- ============================================================
-- Main DDL: side CHECK, NOT VALID to avoid historical row scan
-- 主 DDL：side CHECK 使用 NOT VALID，避免掃描歷史 row
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'market.liquidations'::regclass
          AND conname = 'chk_market_liquidations_side_v095'
    ) THEN
        ALTER TABLE market.liquidations
            ADD CONSTRAINT chk_market_liquidations_side_v095
            CHECK (side IN ('Buy', 'Sell')) NOT VALID;
        RAISE NOTICE
            'V095: added NOT VALID CHECK chk_market_liquidations_side_v095';
    ELSE
        RAISE NOTICE
            'V095: chk_market_liquidations_side_v095 already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL: replace only the exact old lossy primary key
-- 主 DDL：僅在既有主鍵完全等於舊 lossy 形狀時替換
-- ============================================================
DO $$
DECLARE
    v_pk_name TEXT;
    v_pk_cols TEXT[];
BEGIN
    SELECT c.conname, array_agg(a.attname ORDER BY x.ord)
      INTO v_pk_name, v_pk_cols
    FROM pg_constraint c
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS x(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
    WHERE c.conrelid = 'market.liquidations'::regclass
      AND c.contype = 'p'
    GROUP BY c.conname;

    IF v_pk_cols = ARRAY['symbol', 'ts', 'side', 'qty', 'price'] THEN
        RAISE NOTICE
            'V095: market.liquidations already has item-level primary key; skipping';
        RETURN;
    END IF;

    IF v_pk_cols = ARRAY['symbol', 'ts', 'side'] THEN
        EXECUTE format('ALTER TABLE market.liquidations DROP CONSTRAINT %I', v_pk_name);
        RAISE NOTICE
            'V095: dropped old lossy primary key constraint %', v_pk_name;
    ELSIF v_pk_cols IS NOT NULL THEN
        RAISE EXCEPTION
            'V095 Guard B FAIL: refusing to drop unexpected primary key %. Columns=%.',
            v_pk_name, v_pk_cols;
    END IF;

    ALTER TABLE market.liquidations
        ADD CONSTRAINT liquidations_pkey
        PRIMARY KEY (symbol, ts, side, qty, price);
    RAISE NOTICE
        'V095: added item-level primary key (symbol, ts, side, qty, price)';
END $$;

-- ============================================================
-- Guard C: final identity and CHECK constraint must match expectation
-- Guard C：最終 identity 與 CHECK constraint 必須符合預期
-- ============================================================
DO $$
DECLARE
    v_pk_cols TEXT[];
    v_constraint_def TEXT;
BEGIN
    SELECT array_agg(a.attname ORDER BY x.ord) INTO v_pk_cols
    FROM pg_constraint c
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS x(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
    WHERE c.conrelid = 'market.liquidations'::regclass
      AND c.contype = 'p';

    IF v_pk_cols IS DISTINCT FROM ARRAY['symbol', 'ts', 'side', 'qty', 'price'] THEN
        RAISE EXCEPTION
            'V095 Guard C FAIL: market.liquidations primary key mismatch after DDL. Actual=%; expected (symbol, ts, side, qty, price).',
            v_pk_cols;
    END IF;

    SELECT pg_get_constraintdef(oid)
      INTO v_constraint_def
    FROM pg_constraint
    WHERE conrelid = 'market.liquidations'::regclass
      AND conname = 'chk_market_liquidations_side_v095';

    IF v_constraint_def IS NULL
       OR position('Buy' IN v_constraint_def) = 0
       OR position('Sell' IN v_constraint_def) = 0 THEN
        RAISE EXCEPTION
            'V095 Guard C FAIL: chk_market_liquidations_side_v095 missing or mismatched. Actual=%.',
            v_constraint_def;
    END IF;
END $$;
