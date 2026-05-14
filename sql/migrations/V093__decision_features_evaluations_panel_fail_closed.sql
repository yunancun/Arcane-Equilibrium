-- ============================================================
-- V093: decision_features_evaluations panel fail-closed outcomes
--
-- W-AUDIT-8a Phase B B-4 requires bb_breakout to persist an evaluation row
-- when AlphaSurface.oi_delta_panel is unavailable. V086 is already occupied
-- on current main by governance reject/close reason codes, so this forward-only
-- migration extends the V082 evaluation table allowlists at the next available
-- migration number.
--
-- Scope:
--   1. Add evaluation_outcome = 'oi_panel_unavailable'
--   2. Add evidence_source_tier = 'panel_fail_closed'
--   3. Allow side = 0 for pre-direction fail-closed panel rows
--
-- Guard A: table and required columns must exist before altering constraints.
-- Idempotency: drop/re-add constraints to the same definitions; repeated apply
-- is lossless and preserves existing rows.
-- ============================================================

BEGIN;

DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name = 'decision_features_evaluations'
    ) THEN
        RAISE EXCEPTION
            'V093 Guard A FAIL: learning.decision_features_evaluations missing — V082 must apply first.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'evaluation_outcome',
        'evidence_source_tier',
        'side'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'decision_features_evaluations'
          AND column_name = c
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V093 Guard A FAIL: learning.decision_features_evaluations missing columns: %',
            v_missing;
    END IF;
END $$;

ALTER TABLE learning.decision_features_evaluations
    DROP CONSTRAINT IF EXISTS chk_decision_features_evaluations_outcome;

ALTER TABLE learning.decision_features_evaluations
    ADD CONSTRAINT chk_decision_features_evaluations_outcome
    CHECK (evaluation_outcome IN (
        'accept',
        'reject',
        'reject_add',
        'shadow_fill',
        'fallback_use_legacy',
        'fallback_fail_closed',
        'use_legacy_no_predictor',
        'oi_panel_unavailable'
    ));

ALTER TABLE learning.decision_features_evaluations
    DROP CONSTRAINT IF EXISTS chk_decision_features_evaluations_evidence_tier;

ALTER TABLE learning.decision_features_evaluations
    ADD CONSTRAINT chk_decision_features_evaluations_evidence_tier
    CHECK (evidence_source_tier IN (
        'evaluation_log',
        'shadow_synthetic',
        'panel_fail_closed'
    ));

ALTER TABLE learning.decision_features_evaluations
    DROP CONSTRAINT IF EXISTS chk_decision_features_evaluations_side;

ALTER TABLE learning.decision_features_evaluations
    ADD CONSTRAINT chk_decision_features_evaluations_side
    CHECK (side IN (-1, 0, 1));

COMMIT;
