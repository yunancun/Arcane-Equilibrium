# Cost-Gate Cron Installer Apply Preflight

Date: 2026-06-21

## Result

The cost-gate learning cron installer now fails closed before writing crontab unless the read-only activation preflight passes with the PM-approved source head.

This makes the next activation step safer, but it does not activate runtime by itself.

## Operator-Relevant Details

- Apply requires `OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD` or `OPENCLAW_EXPECTED_SOURCE_HEAD` by default.
- The installer checks source readiness, runtime checkout activation readiness, expected-head match, and plan readiness.
- It intentionally does not require existing ledger rows because the cron is what begins materializing PG rejects and refreshing blocked outcomes.
- No runtime source sync, cron install, writer enablement, restart, PG write, Bybit call, order authority, or Cost Gate lowering happened in this checkpoint.

Next operator action remains unchanged in substance: approve runtime source reconcile/sync first, then run the activation runbook with the approved source head.
