# PM Authorization - ALR P2-3 Service Only

Date: 2026-07-09
State: `SERVICE_ONLY_APPLY_AUTHORIZED_ENGINE_RESTART_DENIED`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

PM accepts the fresh E3 and BB service-only verdicts. Apply only the dedicated
database identity, private DSN, reviewed user unit, and bounded startup drain.
If role/unit/start verification fails, stop the ALR unit and preserve all
append-only evidence; do not broaden privileges or restart the engine.

The next state after a successful service-only apply is
`P2_3_SERVICE_RUNNING_ENGINE_NOTIFIER_DORMANT`. P2-4 may use the bounded
persisted backlog. P2-8 remains blocked on a separately safe scanner-event
activation path.
