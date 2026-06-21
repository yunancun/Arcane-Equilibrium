# Operator Note — Cost-Gate Learning Pre-Install Refresh Bridge

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

The cost-gate learning cron wrapper now has a safe pre-install mode:

```bash
OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY=1
```

That mode refreshes the read-only scorecard and demo-learning plan, writes a
status row with `preinstall_refresh_only=true`, and stops before ledger or
outcome stages.

## Why It Matters

The installer correctly fails closed unless the demo-learning plan is `READY`.
But the cron wrapper is also the thing that refreshes the plan. Without this
bridge, a stale/missing plan could block cron installation before cron ever had
a chance to refresh it.

The runbook now adds a pre-install refresh-only step between source sync and
activation preflight.

## Boundaries

This checkpoint did not:

- sync runtime source
- install or edit crontab
- enable the hot-path writer
- append runtime ledger rows
- write PG
- call Bybit private/signed APIs
- restart services
- lower the main Cost Gate
- grant order authority

## Operator Next Step

If proceeding, first approve runtime source reconcile/sync on `trade-core`.
Then use the runbook step:

`docs/runbooks/2026-06-21--cost_gate_learning_lane_runtime_activation.md`

Run refresh-only first, then activation preflight, then cron dry-run/install
only if preflight is green.
