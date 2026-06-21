# Cost-Gate Cron Installer Apply Preflight

Date: 2026-06-21

## Verdict

PM SIGN-OFF: CONDITIONAL.

The source-side checkpoint is ready after focused checks. Runtime activation is still not authorized by this report.

## What Changed

- `helper_scripts/cron/install_cost_gate_learning_lane_cron.sh` now runs `cost_gate_learning_lane.status.build_cost_gate_learning_lane_activation_preflight` before any crontab write when `OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1`.
- Apply defaults to `OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT=1` and `OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD=1`.
- Apply requires `OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD` or `OPENCLAW_EXPECTED_SOURCE_HEAD`, then fails closed unless source files are ready, the checkout is activation-ready, expected head matches, and plan status is `READY`.
- The installer does not require existing ledger/outcome rows. That is intentional: installing the cron is the bounded path that starts reject materialization and blocked-outcome accumulation.

## Boundary

No runtime source sync, crontab edit, env edit, deploy, rebuild, restart, ledger append, PG write/schema migration, Bybit private/signed/trading call, writer enablement, order authority, or main Cost Gate lowering was performed.

`OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT=0` remains available only as an explicit bypass knob. It should require a separate PM/operator note because it bypasses the apply-time safety gate.

## Verification

- `bash -n helper_scripts/cron/install_cost_gate_learning_lane_cron.sh helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q`
- `git diff --check`

## Remaining Work

1. Operator approves runtime source reconcile/sync on `trade-core`.
2. Operator supplies the approved source head for the installer.
3. Run the activation runbook dry-run and apply path on runtime.
4. Observe whether materialized rejects, blocked outcomes, and reviews begin accumulating before any discussion of probe authority or Cost Gate changes.
