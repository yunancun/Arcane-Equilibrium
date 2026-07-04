-- ============================================================
-- V148: V142/V143/V144 Guard A retrofit — recorder 三表 + strategist_promotions
--       必要欄反射（P2-11 ① V 系遷移衛生，冷審計 R2 修復 Phase B2）
--
-- 目的 / Motivation:
--   V142（market.trades / market.ob_top）、V143（market.l1_events）、
--   V144（learning.strategist_promotions）的 header 註釋聲稱含 Guard A，但三檔
--   body 實際 DO-block 數 = 0（2026-07-04 MIT 取證親讀）。三表已 applied 且寫入
--   活躍 —— prod 現狀無恙，但 fresh-DB replay（CI schema_contract_test）與異環境
--   部署缺真 fail-closed 防線：既有表若 shape drift（缺欄），寫入方只會在 runtime
--   batch flush 才報難解錯誤。本 migration 補上四個 Guard A 型反射 DO-block。
--
--   已 applied 的 V142/143/144 檔 header 同批改為誠實表述（「Guard A 由 V148
--   retrofit 提供」）→ 檔案 checksum 漂移，deploy 時必跑 bin/repair_migration_checksum
--   （不手改 _sqlx_migrations；memory P0 sqlx hash drift SOP）。
--
-- 範圍 / Scope (V148):
--   §A Guard A — market.trades 必要 5 欄反射
--   §B Guard A — market.ob_top 必要 6 欄反射
--   §C Guard A — market.l1_events 必要 9 欄反射
--   §D Guard A — learning.strategist_promotions 必要 16 欄反射
--   無其他 DDL；冪等雙跑全 NOTICE-skip（純讀反射，無寫入）。
--
-- 編號決策:
--   2026-07-04 ssh trade-core 親查 prod _sqlx_migrations max(version)=145；
--   repo file chain：V146（未 apply）+ 本批 V147。next-free = V148。
--   sqlx forward-only：本 file apply 時 V142/143/144 必已就位（缺表=真斷鏈，RAISE）。
--
-- 硬邊界:
--   - 純讀反射 + RAISE；不 CREATE / ALTER / UPDATE 任何物件。
--   - 不碰 max_retries / live_execution_allowed / execution_authority / system_mode。
-- ============================================================

-- ==========================================================
-- §A Guard A — market.trades（V142 §A，5 欄）
-- ==========================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF to_regclass('market.trades') IS NULL THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: market.trades does not exist — V142 was never '
            'applied (broken migration chain). Re-apply V142 before V148.';
    END IF;
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY['ts', 'symbol', 'side', 'price', 'qty']) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'market' AND table_name = 'trades'
          AND column_name = c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: market.trades missing required columns: %. '
            'Resolve schema drift (vs V142 §A DDL) before proceeding.', v_missing;
    END IF;
    RAISE NOTICE 'V148 Guard A PASS: market.trades (5 columns) intact.';
END $$;

-- ==========================================================
-- §B Guard A — market.ob_top（V142 §B，6 欄）
-- ==========================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF to_regclass('market.ob_top') IS NULL THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: market.ob_top does not exist — V142 was never '
            'applied (broken migration chain). Re-apply V142 before V148.';
    END IF;
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts', 'symbol', 'best_bid', 'bid_size', 'best_ask', 'ask_size'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'market' AND table_name = 'ob_top'
          AND column_name = c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: market.ob_top missing required columns: %. '
            'Resolve schema drift (vs V142 §B DDL) before proceeding.', v_missing;
    END IF;
    RAISE NOTICE 'V148 Guard A PASS: market.ob_top (6 columns) intact.';
END $$;

-- ==========================================================
-- §C Guard A — market.l1_events（V143 §A，9 欄）
-- ==========================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF to_regclass('market.l1_events') IS NULL THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: market.l1_events does not exist — V143 was never '
            'applied (broken migration chain). Re-apply V143 before V148.';
    END IF;
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts', 'symbol', 'best_bid', 'bid_size', 'best_ask', 'ask_size',
        'update_id', 'seq', 'is_snapshot'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'market' AND table_name = 'l1_events'
          AND column_name = c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: market.l1_events missing required columns: %. '
            'Resolve schema drift (vs V143 §A DDL) before proceeding.', v_missing;
    END IF;
    RAISE NOTICE 'V148 Guard A PASS: market.l1_events (9 columns) intact.';
END $$;

-- ==========================================================
-- §D Guard A — learning.strategist_promotions（V144 §B，16 欄）
-- ==========================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF to_regclass('learning.strategist_promotions') IS NULL THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: learning.strategist_promotions does not exist — '
            'V144 was never applied (broken migration chain). Re-apply V144 before V148.';
    END IF;
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'id', 'action', 'strategy_name', 'symbol', 'source_engine',
        'target_engine', 'pre_promotion_params_json', 'promoted_params_json',
        'criteria_verdict', 'criteria_input_json', 'actor_id', 'gate_passed',
        'applied_at', 'applied_at_ms', 'reverts_promotion_id', 'reason'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning' AND table_name = 'strategist_promotions'
          AND column_name = c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V148 Guard A FAIL: learning.strategist_promotions missing required '
            'columns: %. Resolve schema drift (vs V144 §B DDL) before proceeding.',
            v_missing;
    END IF;
    RAISE NOTICE 'V148 Guard A PASS: learning.strategist_promotions (16 columns) intact.';
END $$;

-- ============================================================
-- 驗證 / Verification (double-apply idempotency)
-- ============================================================
-- 純讀反射，無任何 DDL/DML；重跑任意次皆 4 × NOTICE PASS，rc=0 冪等。
-- ROLLBACK：無物件可回滾（本 migration 不建任何東西）。
-- ============================================================
