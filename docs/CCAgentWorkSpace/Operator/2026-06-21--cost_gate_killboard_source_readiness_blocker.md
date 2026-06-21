# Operator Note — Cost-Gate Killboard Source-Readiness Blocker

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

Alpha-discovery now checks the cost-gate learning-lane source activation state
before allowing the cost-gate arm to appear probe-ready.

If the learning-lane source is missing, dirty, behind, or expected-head
mismatched, the cost-gate blocker becomes:

```text
source_health / cost_gate_learning_lane_source_not_activation_ready
```

## Why

The current runtime alpha artifact still shows `cost_gate_demo_learning_lane` as
`probe_ready`, but runtime facts contradict it: source is still old, cron is not
installed, and no learning ledger/materializer/outcome loop exists.

This patch prevents that stale artifact shape from being mistaken for true demo
probe readiness once runtime runs the updated code.

## Boundaries

This checkpoint did not:

- sync runtime source
- install or edit crontab
- enable writer
- append runtime ledger rows
- write PG
- call Bybit private/signed APIs
- restart services
- lower the main Cost Gate
- grant order authority

## Next Step

Runtime still needs operator-approved source reconcile/sync. After that, use the
runbook sequence: pre-install refresh-only -> activation preflight -> cron
dry-run/install if green.
