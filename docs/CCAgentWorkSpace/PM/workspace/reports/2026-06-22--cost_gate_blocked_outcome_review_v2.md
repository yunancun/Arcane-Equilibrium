# Cost Gate Blocked Outcome Review v2

## Summary

This checkpoint improves the Cost Gate learning loop at the point that matters for profitability: when demo/live_demo signals are blocked, the blocked-outcome review now ranks which side-cell most looks like a missed profitable opportunity.

`cost_gate_learning_lane.outcome_review` now emits schema `cost_gate_demo_learning_lane_blocked_outcome_review_v2`. The existing conservative review gate is unchanged, but each reviewed side-cell now carries:

- `wrongful_block_score`
- `net_cost_cushion_bps`
- `net_positive_margin_pct`
- sample margin and review rank
- gross/cost aggregates
- horizon counts and dominant horizon

Activation preflight, learning-loop status, cron status JSON, and alpha-discovery blocker rows mirror the top review opportunity, so operator/QC review can identify the strongest bounded demo-probe candidate without manually parsing the full artifact.

## Why

The previous review artifact could say a blocked side-cell cleared review thresholds, but it did not make the relative opportunity obvious. That left the next action too vague: "review blocked outcomes" rather than "review this side-cell first because it has the strongest missed-profit evidence."

This update turns blocked-signal outcome review into a ranked decision surface while preserving the existing safety posture.

## Files

- `helper_scripts/research/cost_gate_learning_lane/outcome_review.py`
- `helper_scripts/research/cost_gate_learning_lane/status.py`
- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
- `helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/outcome_review.py helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `108 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py` -> `12 passed`
- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh`

## Boundary

Source/test/docs only. No runtime source sync, artifact refresh, crontab/env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, Cost Gate lowering, order authority, execution proof, or promotion proof.

## Next

After operator-approved runtime source reconcile and learning-lane activation, the runtime artifact should expose `blocked_signal_top_review_*` fields. If those fields show a review candidate, the next gate remains operator/QC review before any bounded demo-probe authority.
