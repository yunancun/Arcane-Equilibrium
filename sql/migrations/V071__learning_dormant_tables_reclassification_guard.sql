-- V071: learning dormant-table reclassification guard
--
-- MODULE_NOTE:
--   The original W-AUDIT-4 F-11 plan suggested archiving or removing dormant
--   learning tables. Source audit corrected the scope: these are live
--   configuration, env-gated observability, AI usage, and Claude Teacher
--   contracts. This migration records the corrected classification as metadata
--   only. It performs no destructive cleanup.

DO $$
BEGIN
    IF to_regclass('learning.cost_edge_advisor_log') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.cost_edge_advisor_log IS ' ||
            quote_literal('W-AUDIT-4 V071 reclassified: retained; CostEdgeAdvisor persistence is env-gated observability, not dead schema.');
    END IF;

    IF to_regclass('learning.ai_usage_log') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.ai_usage_log IS ' ||
            quote_literal('W-AUDIT-4 V071 reclassified: retained; Rust AI budget tracker writes usage and API/weekly-report paths read usage.');
    END IF;

    IF to_regclass('learning.ai_budget_config') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.ai_budget_config IS ' ||
            quote_literal('W-AUDIT-4 V071 reclassified: retained; live AI budget configuration is read/written by Rust budget tracker and operator IPC/API.');
    END IF;

    IF to_regclass('learning.directive_executions') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.directive_executions IS ' ||
            quote_literal('W-AUDIT-4 V071 reclassified: retained; Claude Teacher applier/outcome tracker and Phase4 routes depend on this audit table.');
    END IF;

    IF to_regclass('learning.teacher_directives') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE learning.teacher_directives IS ' ||
            quote_literal('W-AUDIT-4 V071 reclassified: retained; Claude Teacher writer persists accepted directives here before execution audit rows.');
    END IF;
END $$;
