-- ============================================================
-- V094: EDGE-P2-3 Phase 1b close-maker-first audit persistence
--
-- Purpose / 目的:
--   Add two hot audit columns to trading.fills for close-maker-first
--   observation, while leaving lower-frequency per-fill context in the
--   existing details JSONB payload.
--   為 close-maker-first 觀察在 trading.fills 增加兩個 hot audit 欄位，
--   低頻單筆上下文繼續放在既有 details JSONB payload。
--
-- Scope / 範圍:
--   - ADD close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE
--   - ADD close_maker_fallback_reason TEXT NULL with a 10-value NOT VALID CHECK
--   - ADD a partial index for close_maker_attempt = TRUE
--   - No data rewrite, no backfill, no runtime enablement
--   - 不重寫歷史資料、不回填、不啟用任何 runtime 行為
--
-- Parent specs:
--   docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md
--   docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md
--   docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md
-- ============================================================

-- ============================================================
-- Guard A: trading.fills must exist with V003/V017/V083 baseline columns
-- Guard A：trading.fills 必須存在且 V003/V017/V083 baseline 欄位俱在
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'trading' AND table_name = 'fills'
    ) THEN
        RAISE EXCEPTION
            'V094 Guard A FAIL: trading.fills missing — V003 must have applied first. Re-check migration order.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts',
        'fill_id',
        'order_id',
        'symbol',
        'side',
        'qty',
        'price',
        'strategy_name',
        'context_id',
        'entry_context_id',
        'engine_mode',
        'exit_reason',
        'details'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading'
          AND table_name = 'fills'
          AND column_name = c
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V094 Guard A FAIL: trading.fills missing required columns: %. Resolve V003/V017/V033/V083 schema drift before applying V094.',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- Guard B: existing V094 columns must match the required types
-- Guard B：若 V094 欄位已存在，型別與 nullable/default 必須對齊
-- ============================================================
DO $$
DECLARE
    v_data_type TEXT;
    v_is_nullable TEXT;
    v_column_default TEXT;
BEGIN
    SELECT data_type, is_nullable, column_default
      INTO v_data_type, v_is_nullable, v_column_default
    FROM information_schema.columns
    WHERE table_schema = 'trading'
      AND table_name = 'fills'
      AND column_name = 'close_maker_attempt';

    IF v_data_type IS NOT NULL THEN
        IF v_data_type IS DISTINCT FROM 'boolean'
           OR v_is_nullable IS DISTINCT FROM 'NO'
           OR coalesce(v_column_default, '') NOT ILIKE '%false%' THEN
            RAISE EXCEPTION
                'V094 Guard B FAIL: trading.fills.close_maker_attempt drift. Expected BOOLEAN NOT NULL DEFAULT FALSE, got type=%, nullable=%, default=%.',
                v_data_type, v_is_nullable, v_column_default;
        END IF;
    END IF;

    SELECT data_type, is_nullable, column_default
      INTO v_data_type, v_is_nullable, v_column_default
    FROM information_schema.columns
    WHERE table_schema = 'trading'
      AND table_name = 'fills'
      AND column_name = 'close_maker_fallback_reason';

    IF v_data_type IS NOT NULL THEN
        IF v_data_type IS DISTINCT FROM 'text'
           OR v_is_nullable IS DISTINCT FROM 'YES'
           OR v_column_default IS NOT NULL THEN
            RAISE EXCEPTION
                'V094 Guard B FAIL: trading.fills.close_maker_fallback_reason drift. Expected TEXT NULL DEFAULT NULL, got type=%, nullable=%, default=%.',
                v_data_type, v_is_nullable, v_column_default;
        END IF;
    END IF;
END $$;

-- ============================================================
-- Main DDL: append-only audit columns
-- 主 DDL：append-only audit 欄位
-- ============================================================
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS close_maker_fallback_reason TEXT NULL;

-- ============================================================
-- Main DDL: 10-value fallback enum CHECK, NOT VALID
-- 主 DDL：10 值 fallback enum CHECK，NOT VALID
--
-- NOT VALID avoids historical row scans and mirrors prior migration practice.
-- NOT VALID 避免掃描歷史 row，對齊既有 migration 範式。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'trading.fills'::regclass
          AND conname = 'chk_fills_close_maker_fallback_reason_v094'
    ) THEN
        ALTER TABLE trading.fills
            ADD CONSTRAINT chk_fills_close_maker_fallback_reason_v094
            CHECK (
                close_maker_fallback_reason IS NULL
                OR close_maker_fallback_reason IN (
                    'timeout_taker',
                    'postonly_reject',
                    'cancel_grace_expired',
                    'ack_lost',
                    'rate_limit_pause_global',
                    'rate_limit_backoff_per_symbol',
                    'fast_escalate_safety_upgrade',
                    'not_attempted_safety_path',
                    'engine_shutdown_safety',
                    'fallback_to_taker_mandatory'
                )
            ) NOT VALID;
        RAISE NOTICE
            'V094: added NOT VALID CHECK chk_fills_close_maker_fallback_reason_v094';
    ELSE
        RAISE NOTICE
            'V094: chk_fills_close_maker_fallback_reason_v094 already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL: hot-path partial index for close-maker attempted fills
-- 主 DDL：close-maker attempt hot-path partial index
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_fills_close_maker_attempt_v094
    ON trading.fills (engine_mode, ts DESC)
    WHERE close_maker_attempt = TRUE;

-- ============================================================
-- Guard C: CHECK constraint and partial index must match expectation
-- Guard C：CHECK constraint 與 partial index 必須符合預期
-- ============================================================
DO $$
DECLARE
    v_constraint_def TEXT;
    v_index_def TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid)
      INTO v_constraint_def
    FROM pg_constraint
    WHERE conrelid = 'trading.fills'::regclass
      AND conname = 'chk_fills_close_maker_fallback_reason_v094';

    IF v_constraint_def IS NULL THEN
        RAISE EXCEPTION
            'V094 Guard C FAIL: chk_fills_close_maker_fallback_reason_v094 missing after DDL.';
    END IF;

    IF position('timeout_taker' IN v_constraint_def) = 0
       OR position('postonly_reject' IN v_constraint_def) = 0
       OR position('cancel_grace_expired' IN v_constraint_def) = 0
       OR position('ack_lost' IN v_constraint_def) = 0
       OR position('rate_limit_pause_global' IN v_constraint_def) = 0
       OR position('rate_limit_backoff_per_symbol' IN v_constraint_def) = 0
       OR position('fast_escalate_safety_upgrade' IN v_constraint_def) = 0
       OR position('not_attempted_safety_path' IN v_constraint_def) = 0
       OR position('engine_shutdown_safety' IN v_constraint_def) = 0
       OR position('fallback_to_taker_mandatory' IN v_constraint_def) = 0 THEN
        RAISE EXCEPTION
            'V094 Guard C FAIL: chk_fills_close_maker_fallback_reason_v094 enum mismatch. Actual: %. Expected all 10 enum values.',
            v_constraint_def;
    END IF;

    SELECT pg_get_indexdef(i.indexrelid)
      INTO v_index_def
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'trading'
      AND c.relname = 'idx_fills_close_maker_attempt_v094';

    IF v_index_def IS NULL THEN
        RAISE EXCEPTION
            'V094 Guard C FAIL: idx_fills_close_maker_attempt_v094 missing after DDL.';
    END IF;

    IF position('engine_mode' IN v_index_def) = 0
       OR position('ts' IN v_index_def) = 0
       OR position('close_maker_attempt' IN v_index_def) = 0
       OR position('true' IN lower(v_index_def)) = 0 THEN
        RAISE EXCEPTION
            'V094 Guard C FAIL: idx_fills_close_maker_attempt_v094 mismatch. Actual: %. Expected (engine_mode, ts DESC) WHERE close_maker_attempt = TRUE.',
            v_index_def;
    END IF;
END $$;
