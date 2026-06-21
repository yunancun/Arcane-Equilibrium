# Cost-Gate Learning Plan Refresh Preflight

Date: 2026-06-21

## Result

The cost-gate learning loop now refreshes its bounded demo-learning plan before materializing rejects, and activation preflight rejects fresh-but-unusable plans.

This improves the planned runtime activation path, but it does not activate runtime by itself.

## Operator-Relevant Details

- A plan is activation-ready only if it is recent, schema-correct, `READY_FOR_DEMO_LEARNING_PROBE`, `OPERATOR_REVIEW`, and has selected candidates.
- The cron wrapper refreshes `demo_learning_lane_plan_latest.json` each run unless `OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN=0` is explicitly set.
- Plan refresh status is visible in `logs/cost_gate_learning_lane.log`.
- No runtime source sync, cron install, writer enablement, restart, PG write, Bybit call, order authority, or Cost Gate lowering happened in this checkpoint.

Next operator action remains source reconcile/sync on `trade-core`, then run the activation runbook with the approved source head.
