# PM Report: Cost-Gate Learning Activation Preflight

Date: 2026-06-21

## Objective

Turn the question "is demo still accumulating learning data after cost-gate rejects?" into a machine-checkable preflight instead of a manual artifact hunt.

## Current Runtime Read

Read-only Linux probe found `trade-core` behind origin/main by 5 commits and dirty. `/tmp/openclaw/cost_gate_learning_lane/` currently has only `demo_learning_lane_plan_latest.json` and empty policy stdout.

Missing runtime evidence:

- no `probe_ledger.jsonl`
- no `blocked_outcome_review_latest.json`
- no `cron_heartbeat/cost_gate_learning_lane.last_fire`
- no `logs/cost_gate_learning_lane.log`

Conclusion: cost-gate-rejected demo signals are not yet accumulating outcome evidence on runtime.

## Change

Added `helper_scripts/research/cost_gate_learning_lane/status.py` as the public status/preflight Module for the cost-gate demo-learning lane.

It centralizes:

- required source-file readiness checks
- demo-learning plan freshness
- `probe_ledger.jsonl` summary
- learning cron heartbeat/status/latest refresh-review artifact summary
- blocked-signal outcome review status
- activation classification

`alpha_discovery_throughput.runtime_runner` now imports these public status helpers instead of carrying a private cost-gate summary implementation.

## Preflight Answers

The new CLI emits direct booleans for:

- `has_accumulated_ledger_rows`
- `currently_accumulating_evidence`
- `cost_gate_rejects_recorded`
- `silent_drop_risk`
- `blocked_signal_outcomes_recorded`
- `blocked_signal_profitability_review_available`

Primary statuses include `NOT_ACCUMULATING`, `LOOP_RUNNING_NO_LEDGER_ROWS`, `ADMISSION_ONLY_NEEDS_OUTCOME_REFRESH`, `BLOCKED_OUTCOMES_ACCUMULATING`, `REVIEW_CANDIDATE_OPERATOR_REVIEW`, and fail-closed source/plan/loop health states.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 31 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` passed
- `PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status --data-dir /tmp/openclaw --print-json` passed

## Boundary

Source/test/docs + local read-only artifact smoke only. No deploy, restart, PG write/schema migration, Bybit private/signed/trading call, order authority, auth/risk/runtime/config mutation, main Cost Gate lowering, execution proof, signal proof, or promotion proof.
