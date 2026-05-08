-- V070: replay dead-schema reclassification guard
--
-- MODULE_NOTE:
--   The original W-AUDIT-4 F-11 replay cleanup list treated several 0-row
--   replay tables as dead. Source audit corrected that scope: these tables are
--   replay/operator infrastructure with route, cron, advisory, or signed
--   approval contracts. This migration records the corrected classification as
--   metadata only. It performs no destructive cleanup.

DO $$
BEGIN
    IF to_regclass('replay.handoff_requests') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE replay.handoff_requests IS ' ||
            quote_literal('W-AUDIT-4 V070 reclassified: retained; handoff_routes atomically writes typed replay handoff requests and governance audit rows.');
    END IF;

    IF to_regclass('replay.mlde_replay_veto_log') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE replay.mlde_replay_veto_log IS ' ||
            quote_literal('W-AUDIT-4 V070 reclassified: retained; MLDE advisory veto surface is referenced by mlde_shadow_advisor and DreamEngine candidate flow.');
    END IF;

    IF to_regclass('replay.tier_promotion_approval') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE replay.tier_promotion_approval IS ' ||
            quote_literal('W-AUDIT-4 V070 reclassified: retained; V057 signed tier-promotion approval contract with restricted public write access.');
    END IF;

    IF to_regclass('replay.business_kpi_snapshots') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE replay.business_kpi_snapshots IS ' ||
            quote_literal('W-AUDIT-4 V070 reclassified: retained; Wave9 business KPI collector writes daily KPI snapshots.');
    END IF;

    IF to_regclass('replay.audit_incident_summaries') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE replay.audit_incident_summaries IS ' ||
            quote_literal('W-AUDIT-4 V070 reclassified: retained; Wave9 incident scan writes daily audit summaries.');
    END IF;
END $$;
