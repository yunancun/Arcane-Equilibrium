-- V069: drop dead observability scorer_predictions
--
-- MODULE_NOTE:
--   W-AUDIT-4 originally proposed dropping scorer_predictions and
--   model_performance. Source audit corrected the scope:
--   - observability.scorer_predictions has no production reader/writer.
--   - observability.model_performance is still read by canary_promoter.
--   - observability.feature_baselines and observability.drift_events are kept
--     for the drift-detector contract pending V072 resolution.
--
-- Boundary:
--   This migration refuses to drop non-empty tables and uses RESTRICT
--   semantics. It does not touch model_performance, feature_baselines, or
--   drift_events.

DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('observability.scorer_predictions') IS NULL THEN
        RAISE NOTICE 'V069: observability.scorer_predictions already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM observability.scorer_predictions' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V069 Guard A FAIL: observability.scorer_predictions is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'observability.scorer_predictions'::regclass
      AND dependent.oid <> 'observability.scorer_predictions'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V069 Guard A FAIL: observability.scorer_predictions has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS observability.scorer_predictions RESTRICT;
