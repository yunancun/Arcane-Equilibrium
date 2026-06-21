# Cost-Gate Learning Scorecard Refresh Chain

Date: 2026-06-21

## Verdict

PM SIGN-OFF: CONDITIONAL.

The source-side recurring learning chain is now complete. Runtime activation is still blocked on operator-approved `trade-core` source reconcile/sync and cron install.

## What Changed

- `helper_scripts/cron/cost_gate_learning_lane_cron.sh` now refreshes the read-only cost-gate reject counterfactual scorecard before the plan.
- The wrapper writes dated and latest Markdown/JSON scorecard artifacts under `cost_gate_counterfactual/`.
- The recurring chain is now: counterfactual scorecard -> bounded plan -> reject materializer -> blocked-outcome refresh -> blocked-outcome review.
- `cost_gate_learning_lane.status` and alpha-discovery blocker rows now expose scorecard refresh rc/status/probe-candidate count.
- Scorecard refresh failures mark the learning loop `ERROR` instead of being hidden behind downstream materializer/review state.

## Verification

- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`
- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
- Local artifact-only cron smoke with scorecard refresh disabled.
- `git diff --check`

## Boundary

No runtime source sync, crontab edit, env edit, deploy, rebuild, restart, runtime ledger append, PG write/schema migration, Bybit private/signed/trading call, writer enablement, order authority, or main Cost Gate lowering was performed.

## Remaining Work

1. Operator approves runtime source reconcile/sync on `trade-core`.
2. Run the activation runbook with the PM-approved source head.
3. Confirm scorecard, plan, materializer, outcome refresh, and review artifacts accumulate from runtime cron before any demo probe authority discussion.
