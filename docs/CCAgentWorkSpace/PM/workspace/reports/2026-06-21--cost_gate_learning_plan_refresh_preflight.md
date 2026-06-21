# Cost-Gate Learning Plan Refresh Preflight

Date: 2026-06-21

## Verdict

PM SIGN-OFF: CONDITIONAL.

The source-side learning-loop durability fix is ready. Runtime activation is still blocked on operator-approved `trade-core` source reconcile/sync and cron install.

## What Changed

- `helper_scripts/cron/cost_gate_learning_lane_cron.sh` now refreshes the bounded plan first by running `cost_gate_learning_lane.policy`.
- The wrapper writes dated `demo_learning_lane_plan_*.json`, updates `demo_learning_lane_plan_latest.json`, then materializes rejects and refreshes outcomes.
- The status log now records `plan_rc`, `refresh_plan`, `plan_policy_status`, `plan_gate_status`, and `plan_selected_probe_candidate_count`.
- `cost_gate_learning_lane.status` no longer treats freshness alone as plan readiness. A plan must be recent, schema-correct, `READY_FOR_DEMO_LEARNING_PROBE`, `OPERATOR_REVIEW`, and non-empty.
- Plan refresh failures now make the learning loop `ERROR` instead of being hidden behind materializer/review status.

## Why It Matters

The previous source loop could be installed with a ready plan but then decay after the plan aged out. This checkpoint keeps the learning loop self-refreshing and makes policy-not-ready states explicit before activation.

## Verification

- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`
- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
- Local artifact-only cron smoke with no scorecard/PG wrote a diagnostic `SOURCE_SCORECARD_UNAVAILABLE` plan and status line.
- `git diff --check`

## Boundary

No runtime source sync, crontab edit, env edit, deploy, rebuild, restart, runtime ledger append, PG write/schema migration, Bybit private/signed/trading call, writer enablement, order authority, or main Cost Gate lowering was performed.

## Remaining Work

1. Operator approves runtime source reconcile/sync on `trade-core`.
2. Run the activation runbook with the PM-approved source head.
3. Confirm recurring plan refresh, reject materialization, blocked-outcome refresh, and outcome review are accumulating before any probe authority discussion.
