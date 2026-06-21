# Cost-Gate Learning Pre-Install Refresh Bridge

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime activation still operator-gated

## Summary

This checkpoint fixes an activation deadlock in the cost-gate learning lane.

Previous source state was internally consistent only after cron was running:
`cost_gate_learning_lane_cron.sh` could refresh scorecard and plan at the start
of each run, but `install_cost_gate_learning_lane_cron.sh` also required
`plan_status=READY` before writing the crontab entry. If runtime source was
synced but the plan artifact was missing or stale, the installer could fail
before the self-refreshing cron had any chance to create the plan.

## Change

- Added `OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY=1` to
  `helper_scripts/cron/cost_gate_learning_lane_cron.sh`.
- In this mode the wrapper refreshes scorecard and plan, writes the normal
  learning-loop status row with `preinstall_refresh_only=true`, then skips:
  - historical scorecard review
  - reject materializer
  - outcome refresh
  - blocked-outcome review
- Updated the runtime activation runbook to run this bridge after source
  reconcile and before activation preflight.
- Added static coverage proving the cutoff happens after plan refresh and
  before materializer/outcome/review stages.

## Verification

- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`
- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q` -> `12 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> `62 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `36 passed`
- `git diff --check`
- Local artifact-only smoke with:
  - `OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY=1`
  - `OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD=0`
  - all append/materialize/probe flags disabled

Smoke result: wrote `demo_learning_lane_plan_latest.json`, heartbeat, and
`logs/cost_gate_learning_lane.log` with `preinstall_refresh_only=true`; no
ledger append or materializer/outcome/review execution occurred.

## Boundary

No runtime source sync, crontab edit/install, env edit, deploy, rebuild,
restart, runtime ledger append, PG write/schema migration, Bybit private/signed
call, writer enablement, order authority, or main Cost Gate lowering.

## Next Required Runtime Step

Operator must still approve runtime source reconcile/sync on `trade-core`.
After that, run the pre-install refresh-only command from the runbook, then run
activation preflight and cron dry-run/install only if the preflight is green.
