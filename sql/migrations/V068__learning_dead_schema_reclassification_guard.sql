-- V068: learning/agent dead-schema reclassification guard
--
-- MODULE_NOTE:
--   The original W-AUDIT-4 F-11 plan grouped several 0-row tables as
--   removable dead schema. Source audit corrected the scope: most entries have
--   active route, cron, Rust writer, or recently-added Agent Spine contract
--   references. This migration records the corrected classification as
--   metadata only. It performs no destructive cleanup.

DO $$
BEGIN
    IF to_regclass('learning.foundation_model_features') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.foundation_model_features IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: retained; DL-3 foundation writer/report and Phase4 routes reference this table.');
    END IF;

    IF to_regclass('learning.weekly_review_log') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.weekly_review_log IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: retained; Phase4 weekly review routes read/update this table behind operator-scoped controls.');
    END IF;

    IF to_regclass('learning.pattern_insights') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.pattern_insights IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: retained; ai_service_feedback writes and reads Analyst pattern insight rows.');
    END IF;

    IF to_regclass('learning.experiment_ledger') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.experiment_ledger IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: retained; experiment ledger code paths and governance/evolution surfaces still reference this concept.');
    END IF;

    IF to_regclass('learning.ml_parameter_suggestions') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.ml_parameter_suggestions IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: retained pending Optuna/governance UI decision; do not remove under dead-schema cleanup.');
    END IF;

    IF to_regclass('agent.decision_state_changes') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE agent.decision_state_changes IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: retained; V064 Agent Spine decision-store contract surface, even if current runtime state-change rows are absent.');
    END IF;

    IF to_regclass('learning.promotion_pipeline') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.promotion_pipeline IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: review-only; Python promotion_pipeline is in-process today, so DB ownership requires a separate architecture decision.');
    END IF;

    IF to_regclass('learning.rl_transitions') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.rl_transitions IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: review-only placeholder; no production removal in this migration.');
    END IF;

    IF to_regclass('learning.symbol_clusters') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.symbol_clusters IS ' ||
            quote_literal('W-AUDIT-4 V068 reclassified: review-only placeholder; no production removal in this migration.');
    END IF;
END $$;
