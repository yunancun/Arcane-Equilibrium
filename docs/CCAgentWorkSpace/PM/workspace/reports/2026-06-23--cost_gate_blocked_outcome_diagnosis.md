# Cost Gate Blocked-Outcome Diagnosis

Date: 2026-06-23
Source checkpoint: `51a1c4ad`

## Summary

The Cost Gate learning lane outcome review now distinguishes why blocked
signals did or did not clear the review gate. This closes a learning gap where
gross-positive but after-cost-insufficient signals could be treated like generic
`rejected_no_edge` outcomes.

New `cost_gate_demo_learning_lane_blocked_outcome_review_v2` fields:

- `learning_diagnosis`
- `cost_gate_escape_recommendation`
- `false_negative_candidate`
- `edge_amplification_required`
- aggregate diagnosis / recommendation counts

The alpha discovery path now routes gross-positive cost-cushion misses to:

- primary blocker: `cost_gate_blocked_signal_edge_amplification_required`
- next trigger: `amplify_edge_or_reduce_friction_for_same_side_cell`

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` -> `83 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py` -> `174 passed`
- `python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py` -> `17 passed`
- `python3 -m py_compile ...` -> passed
- `git diff --check` -> passed

## Boundary

No CI, PG write, schema migration, Bybit private/signed/trading call,
deploy/rebuild/restart, crontab install, env/auth/risk/order/strategy mutation,
global Cost Gate lowering, probe/order authority, actual order, or promotion
proof.
