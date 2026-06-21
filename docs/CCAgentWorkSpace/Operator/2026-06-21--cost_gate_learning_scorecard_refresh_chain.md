# Cost-Gate Learning Scorecard Refresh Chain

Date: 2026-06-21

## Result

The cost-gate learning cron source now refreshes the reject counterfactual scorecard before refreshing the plan and downstream learning artifacts.

This completes the planned recurring learning chain in source, but it does not activate runtime by itself.

## Operator-Relevant Details

- The recurring chain is: counterfactual scorecard -> bounded plan -> reject materializer -> blocked-outcome refresh -> blocked-outcome review.
- Scorecard refresh status is visible in `logs/cost_gate_learning_lane.log` and alpha-discovery blocker rows.
- Scorecard refresh failures make the loop `ERROR`.
- No runtime source sync, cron install, writer enablement, restart, PG write, Bybit call, order authority, or Cost Gate lowering happened in this checkpoint.

Next operator action remains source reconcile/sync on `trade-core`, then run the activation runbook with the approved source head.
