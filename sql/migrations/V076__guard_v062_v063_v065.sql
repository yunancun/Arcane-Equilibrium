-- ============================================================
-- V076: Guard A retrofit for V062/V063/V065
--
-- This migration is intentionally read-only. It retrofits fail-fast checks for
-- migrations that predated the current Guard A convention:
--   - V062 trading.scanner_opportunity_decays advisory-only evidence table
--   - V063 market.market_tickers.funding_rate replay enrichment column
--   - V065 openclaw proposal / approval / channel-event ledger
--
-- Do not deploy V076 ahead of the rest of the W-AUDIT-4 migration set unless
-- the operator explicitly accepts the resulting migration version ordering.
-- ============================================================

DO $$
DECLARE
    v_missing TEXT[];
    v_col TEXT;
BEGIN
    IF to_regclass('trading.scanner_opportunity_decays') IS NULL THEN
        RAISE EXCEPTION 'V076 Guard A FAIL: V062 trading.scanner_opportunity_decays missing';
    END IF;

    v_missing := ARRAY[]::TEXT[];
    FOREACH v_col IN ARRAY ARRAY[
        'ts',
        'decay_id',
        'scan_id',
        'symbol',
        'authority_mode',
        'reason',
        'has_open_position',
        'position_review_required',
        'auto_close_allowed',
        'evidence',
        'payload'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'trading'
              AND table_name = 'scanner_opportunity_decays'
              AND column_name = v_col
        ) THEN
            v_missing := array_append(v_missing, v_col);
        END IF;
    END LOOP;

    IF cardinality(v_missing) > 0 THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V062 trading.scanner_opportunity_decays missing required columns: %',
            array_to_string(v_missing, ', ');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'trading'
          AND table_name = 'scanner_opportunity_decays'
          AND column_name = 'auto_close_allowed'
          AND data_type = 'boolean'
          AND column_default ILIKE '%false%'
    ) THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V062 trading.scanner_opportunity_decays.auto_close_allowed must be boolean default false';
    END IF;

    IF to_regclass('trading.idx_scanner_opportunity_decays_ts') IS NULL
       OR to_regclass('trading.idx_scanner_opportunity_decays_scan_id') IS NULL
       OR to_regclass('trading.idx_scanner_opportunity_decays_symbol_ts') IS NULL THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V062 trading.scanner_opportunity_decays advisory indexes missing';
    END IF;

    IF to_regclass('market.market_tickers') IS NULL THEN
        RAISE EXCEPTION 'V076 Guard A FAIL: V002 market.market_tickers missing before V063';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'market'
          AND table_name = 'market_tickers'
          AND column_name = 'funding_rate'
          AND data_type = 'real'
    ) THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V063 market.market_tickers.funding_rate missing or not REAL';
    END IF;

    IF to_regclass('openclaw.proposals') IS NULL THEN
        RAISE EXCEPTION 'V076 Guard A FAIL: V065 openclaw.proposals missing';
    END IF;

    IF to_regclass('openclaw.approval_decisions') IS NULL THEN
        RAISE EXCEPTION 'V076 Guard A FAIL: V065 openclaw.approval_decisions missing';
    END IF;

    IF to_regclass('openclaw.channel_events') IS NULL THEN
        RAISE EXCEPTION 'V076 Guard A FAIL: V065 openclaw.channel_events missing';
    END IF;

    v_missing := ARRAY[]::TEXT[];
    FOREACH v_col IN ARRAY ARRAY[
        'proposal_id',
        'source',
        'channel',
        'request_id',
        'proposal_type',
        'risk_class',
        'status',
        'evidence_refs',
        'required_approval_class',
        'operator_action_required',
        'side_effect_route',
        'payload',
        'created_at_ms'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'openclaw'
              AND table_name = 'proposals'
              AND column_name = v_col
        ) THEN
            v_missing := array_append(v_missing, v_col);
        END IF;
    END LOOP;

    IF cardinality(v_missing) > 0 THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V065 openclaw.proposals missing required columns: %',
            array_to_string(v_missing, ', ');
    END IF;

    v_missing := ARRAY[]::TEXT[];
    FOREACH v_col IN ARRAY ARRAY[
        'approval_id',
        'proposal_id',
        'request_id',
        'decision',
        'actor',
        'auth_result',
        'delegated_route'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'openclaw'
              AND table_name = 'approval_decisions'
              AND column_name = v_col
        ) THEN
            v_missing := array_append(v_missing, v_col);
        END IF;
    END LOOP;

    IF cardinality(v_missing) > 0 THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V065 openclaw.approval_decisions missing required columns: %',
            array_to_string(v_missing, ', ');
    END IF;

    v_missing := ARRAY[]::TEXT[];
    FOREACH v_col IN ARRAY ARRAY[
        'channel_event_id',
        'request_id',
        'ts_ms',
        'direction',
        'channel',
        'auth_profile',
        'event_type',
        'status',
        'payload_summary'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'openclaw'
              AND table_name = 'channel_events'
              AND column_name = v_col
        ) THEN
            v_missing := array_append(v_missing, v_col);
        END IF;
    END LOOP;

    IF cardinality(v_missing) > 0 THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V065 openclaw.channel_events missing required columns: %',
            array_to_string(v_missing, ', ');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'openclaw.proposals'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%evidence_refs%'
          AND pg_get_constraintdef(oid) ILIKE '%jsonb_array_length%'
          AND pg_get_constraintdef(oid) ILIKE '%> 0%'
    ) THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V065 openclaw.proposals evidence_refs non-empty check missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'openclaw.proposals'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%side_effect_route%'
          AND pg_get_constraintdef(oid) ILIKE '%/api/v1/governance/%'
          AND pg_get_constraintdef(oid) ILIKE '%live-auth%'
          AND pg_get_constraintdef(oid) ILIKE '%risk-config%'
          AND pg_get_constraintdef(oid) ILIKE '%deploy%'
          AND pg_get_constraintdef(oid) ILIKE '%restart%'
    ) THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V065 openclaw.proposals side_effect_route denylist check missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'openclaw.approval_decisions'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%delegated_route%'
          AND pg_get_constraintdef(oid) ILIKE '%/api/v1/governance/%'
    ) THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V065 openclaw.approval_decisions delegated_route governance check missing';
    END IF;

    IF to_regclass('openclaw.idx_openclaw_proposals_status_created') IS NULL
       OR to_regclass('openclaw.idx_openclaw_approval_decisions_proposal') IS NULL
       OR to_regclass('openclaw.idx_openclaw_channel_events_ts') IS NULL THEN
        RAISE EXCEPTION
            'V076 Guard A FAIL: V065 openclaw ledger indexes missing';
    END IF;

    RAISE NOTICE 'V076 Guard A PASS: V062/V063/V065 prerequisites verified';
END
$$;
