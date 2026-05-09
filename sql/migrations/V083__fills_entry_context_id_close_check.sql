-- ============================================================
-- V083: W-AUDIT-4b-M2 — trading.fills entry_context_id close-fill enforcement
--
-- 動機 / Motivation:
--   2026-05-09 MIT PG 直查：trading.fills 24h 175 fills 中只 67 個有
--   entry_context_id (38%)，導致 edge_label_backfill EXISTS join 99% 失敗 →
--   `learning.decision_features.label_filled_at` 大量 NULL → ML training pool
--   缺正樣本標籤 → attribution_chain_ok ratio 不可恢復。
--
--   Root cause 分布：
--     A) ENTRY fills (open path) 設計上 entry_context_id = NULL（it IS the
--        entry，與 edge_label_backfill SQL 對齊：`WHERE entry_context_id IS NULL`
--        識別 entry row）。這部分是 BY DESIGN，**不需要修**。
--     B) CLOSE fills 應該攜帶 entry's context_id 但偶有空，原因：
--        - paper_state.entry_context_id 在 engine restart 後丟（in-memory）
--        - orphan adopt / 被外部 pipeline 開倉、未經 4 個 set_entry_context_id
--          call site 之一
--        - 部分 IPC close path 漏設
--
-- 範圍 / Scope (V083):
--   1. Hot-path 索引補強：W-AUDIT-4b-M2 backfill cron 需要 (strategy_name,
--      engine_mode, symbol, side, ts) 多欄複合索引，加速「找最近 entry fill」
--      lookup（partial index WHERE entry_context_id IS NULL）。
--   2. **NOT VALID** partial CHECK constraint：close fills（exit_reason IS
--      NOT NULL）必須攜 entry_context_id。NOT VALID 不掃 historical row，
--      只對新 INSERT 生效，避免破 175 行歷史資料中的 67%（NULL close fills）。
--      Future migration（M2 觀察期過後）可加 VALIDATE CONSTRAINT 強化。
--   3. 不遷移 / 不回填歷史：V083 純 forward-only schema enhancement；
--      實際 backfill 由 helper_scripts/cron/edge_label_backfill_cron.sh
--      M2 新 step 處理（每 30min 跑一次，UPDATE NULL → entry's context_id）。
--   4. 加 telemetry view：observability.fills_entry_context_id_health
--      讓 healthcheck `[新-fills_entry_ctx_health]`（後續 ticket）可讀
--      24h close fills 中 entry_context_id IS NULL ratio。
--
-- 不變式 / Invariants:
--   - V083 落地後 ENTRY fills（exit_reason IS NULL）entry_context_id 恆 NULL
--     by design — edge_label_backfill SQL 第 192 行的
--     `entry_context_id IS NULL  -- entry row, not a close` 保留。
--   - V083 落地後 CLOSE fills（exit_reason IS NOT NULL）entry_context_id 應
--     恆 NOT NULL（NOT VALID CHECK 對新 INSERT 強制）；writer-side WARN log
--     在 violation 時 fail-soft 不阻 fill INSERT（避免 producer 卡死）。
--   - hot-path 索引選用 partial WHERE entry_context_id IS NULL 縮小索引體積
--     （生產資料 ~62% rows 是 entry，自然 NULL）。
--
-- ML training 安全性 / ML Training Safety:
--   下游 SELECT trading.fills 不變；既有 backfill SQL 使用
--     `WHERE entry_context_id IS NULL` 識別 entry row，V083 不破。
--   close fills 補齊 entry_context_id 後：
--     edge_label_backfill EXISTS subquery 命中率：
--       baseline 38% (67/175) → 目標 95%+（cron 全量補齊後）
--     → label_filled_at 補齊 → ML training set 樣本數 ≥ 100/24h
--     → attribution_chain_ok 0.5% → 25-40%
--
-- 對應產品 / Product impact:
--   1. attribution_chain_ok ratio 補正
--   2. learning.decision_features.label_net_edge_bps 樣本數恢復
--   3. ML training negative class（reject path / unfilled close）正確識別
--
-- Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
--       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M2
--       TODO.md v19 §5 invariant 5+19 (P1-INSERT-PATH ticket family)
-- ============================================================

-- ============================================================
-- Guard A: trading schema 必須已存在
-- Guard A: trading schema must exist (cheap fail-fast)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'trading'
    ) THEN
        RAISE EXCEPTION 'V083 Guard A FAIL: trading schema missing';
    END IF;
END $$;

-- ============================================================
-- Guard A2: trading.fills 必須存在且具必要欄位
-- Guard A2: trading.fills must exist with required columns
-- 對齊 V003 (基礎 schema) + V017 (entry_context_id) + V021 (exit_source)
-- + V033 (exit_reason)
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='trading' AND table_name='fills'
    ) THEN
        RAISE EXCEPTION
            'V083 Guard A2 FAIL: trading.fills missing — '
            'V003 must have applied first. Re-check migration order.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts', 'fill_id', 'symbol', 'side', 'strategy_name',
        'context_id', 'entry_context_id', 'engine_mode', 'exit_reason'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='trading' AND table_name='fills'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V083 Guard A2 FAIL: trading.fills missing required columns: %. '
            'Resolve V003/V017/V033 schema drift before applying V083.',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- Guard B: entry_context_id 欄位型別必須 TEXT (對齊 V017 ALTER)
-- Guard B: entry_context_id column type must be TEXT (matching V017 ALTER)
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='fills'
      AND column_name='entry_context_id';
    IF v_actual IS DISTINCT FROM 'text' THEN
        RAISE EXCEPTION
            'V083 Guard B FAIL: trading.fills.entry_context_id type drift. '
            'Expected text, got %. Re-check V017 application.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- Guard C: hot-path partial index 必須與預期欄位對齊
-- Guard C: hot-path partial index column list must match expectation
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='trading'
      AND c.relname='idx_fills_entry_lookup_v083';
    -- 預期 substring 須含「strategy_name」「engine_mode」「symbol」「side」「ts」
    -- (PostgreSQL pg_get_indexdef 順序與 CREATE INDEX 順序一致)
    IF v_actual IS NOT NULL
       AND (position('strategy_name' IN v_actual) = 0
            OR position('engine_mode' IN v_actual) = 0
            OR position('symbol' IN v_actual) = 0
            OR position('side' IN v_actual) = 0
            OR position('ts' IN v_actual) = 0) THEN
        RAISE EXCEPTION
            'V083 Guard C FAIL: idx_fills_entry_lookup_v083 column list mismatch. '
            'Actual: %. Expected to contain (strategy_name, engine_mode, symbol, side, ts). '
            'DROP INDEX + re-apply V083.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- 主 DDL：CHECK constraint NOT VALID
-- Main DDL: NOT VALID CHECK constraint
--
-- exit_reason IS NULL → entry fill (open path) — entry_context_id 可 NULL
-- exit_reason IS NOT NULL → close fill — entry_context_id 必 NOT NULL
--
-- NOT VALID：不掃 historical rows，只對 new INSERT 生效。M2 觀察期 7d 後
-- 若 close fills 100% 命中可再 ALTER ... VALIDATE CONSTRAINT 強制歷史。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_fills_close_has_entry_context_id_v083'
          AND conrelid = 'trading.fills'::regclass
    ) THEN
        ALTER TABLE trading.fills
            ADD CONSTRAINT chk_fills_close_has_entry_context_id_v083
            CHECK (exit_reason IS NULL OR entry_context_id IS NOT NULL)
            NOT VALID;
        RAISE NOTICE
            'V083: added NOT VALID CHECK chk_fills_close_has_entry_context_id_v083 '
            '(close fills must have entry_context_id; historical rows exempt)';
    ELSE
        RAISE NOTICE
            'V083: chk_fills_close_has_entry_context_id_v083 already present; skipping';
    END IF;
END $$;

-- ============================================================
-- 索引 / Indexes
--
-- idx_fills_entry_lookup_v083：W-AUDIT-4b-M2 backfill cron 的 hot-path index。
-- partial WHERE entry_context_id IS NULL 縮小索引體積（entry rows 自然 NULL，
-- 約占資料量 60%+；close fills NULL 是 backfill 對象）。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_fills_entry_lookup_v083
    ON trading.fills (strategy_name, engine_mode, symbol, side, ts)
    WHERE entry_context_id IS NULL;

-- ============================================================
-- Telemetry view：observability.fills_entry_context_id_health
--
-- 24h close fills 中 entry_context_id IS NULL 的 ratio。
-- 健康閾值：
--   PASS  : ratio < 5%
--   WARN  : 5% ≤ ratio < 30%
--   FAIL  : ratio ≥ 30%
-- 對齊 PA spec：「24h fill writer entry_context_id 非 NULL ratio ≥ 95%」
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'observability'
    ) THEN
        RAISE NOTICE
            'V083: observability schema missing — skipping telemetry view '
            '(legacy bootstrap; not blocking V083 main DDL)';
    ELSE
        EXECUTE $view$
            CREATE OR REPLACE VIEW observability.fills_entry_context_id_health AS
            WITH window_24h AS (
                SELECT *
                FROM trading.fills
                WHERE ts > NOW() - INTERVAL '24 hours'
                  AND exit_reason IS NOT NULL
                  AND (strategy_name IS NULL OR strategy_name NOT LIKE 'unattributed:%')
            )
            SELECT
                engine_mode,
                COUNT(*) AS close_fills_24h,
                COUNT(entry_context_id) AS with_entry_ctx,
                COUNT(*) FILTER (WHERE entry_context_id IS NULL) AS null_entry_ctx,
                CASE
                    WHEN COUNT(*) = 0 THEN NULL::DOUBLE PRECISION
                    ELSE 1.0 - (COUNT(entry_context_id)::DOUBLE PRECISION / COUNT(*))
                END AS null_ratio
            FROM window_24h
            GROUP BY engine_mode;
        $view$;
        RAISE NOTICE 'V083: created/replaced observability.fills_entry_context_id_health';
    END IF;
END $$;

-- ============================================================
-- Comments
-- ============================================================
COMMENT ON CONSTRAINT chk_fills_close_has_entry_context_id_v083
    ON trading.fills IS
    'W-AUDIT-4b-M2 NOT VALID CHECK (V083): close fills (exit_reason NOT NULL) '
    '必須攜 entry_context_id。NOT VALID 不掃歷史；對 new INSERT 生效。'
    'M2 觀察期 7d 後若全綠可 ALTER VALIDATE CONSTRAINT 強化歷史。';

COMMENT ON INDEX trading.idx_fills_entry_lookup_v083 IS
    'W-AUDIT-4b-M2 partial index (V083) for backfill cron lookup. '
    'WHERE entry_context_id IS NULL 縮小體積。'
    '(strategy_name, engine_mode, symbol, side, ts) 對齊 backfill SQL JOIN 條件。';

-- ============================================================
-- Verification / 驗證查詢（操作者手動執行）
-- ============================================================
-- 1. CHECK constraint 已 NOT VALID 模式 attached:
--    SELECT conname, pg_get_constraintdef(oid), convalidated
--    FROM pg_constraint
--    WHERE conrelid='trading.fills'::regclass
--      AND conname='chk_fills_close_has_entry_context_id_v083';
--    Expected: 1 row, convalidated=false (NOT VALID)
--
-- 2. partial index 已建立:
--    SELECT indexname, indexdef
--    FROM pg_indexes
--    WHERE schemaname='trading' AND indexname='idx_fills_entry_lookup_v083';
--    Expected: 1 row 含 WHERE (entry_context_id IS NULL)
--
-- 3. telemetry view 可查（24h baseline）:
--    SELECT * FROM observability.fills_entry_context_id_health;
--    Expected: 1-3 rows by engine_mode (paper/demo/live_demo)
--
-- 4. NOT VALID 不破歷史 fills（dry-run 兩次冪等驗證）:
--    -- run V083 first time → NOTICE-only PASS
--    -- run V083 second time → all NOTICE skip, 0 RAISE (idempotent)
--    -- existing fills 不被掃 → INSERT 既有 NULL entry_context_id close fill
--    --   不會 trigger constraint
--
-- ============================================================
