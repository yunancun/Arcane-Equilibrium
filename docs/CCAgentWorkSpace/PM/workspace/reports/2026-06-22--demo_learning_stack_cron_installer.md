# Demo Learning Stack Cron Installer

## Summary

This checkpoint adds a single operator-gated install surface for the demo-learning evidence heartbeat plus the Cost Gate learning-lane cron.

The purpose is to stop splitting runtime activation across two independent installer commands. The stack installer makes the intended activation order explicit:

1. validate expected runtime source HEAD and clean checkout
2. run Cost Gate preinstall refresh
3. run read-only Cost Gate activation preflight
4. apply the demo-learning evidence cron installer
5. apply the Cost Gate learning-lane cron installer

No runtime install was performed in this checkpoint.

## Files

- `helper_scripts/cron/install_demo_learning_stack_crons.sh`
- `helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py`
- `helper_scripts/SCRIPT_INDEX.md`
- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- `docs/CCAgentWorkSpace/Operator/2026-06-22--demo_learning_stack_cron_installer.md`

## Installer Contract

- Linux-only.
- Default behavior is dry-run preview.
- Real install/remove requires `OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1`.
- Apply/preflight requires `OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD` or `OPENCLAW_EXPECTED_SOURCE_HEAD`.
- Apply path verifies runtime source `git rev-parse HEAD` matches the expected prefix and `git status --porcelain` is empty.
- Preinstall refresh delegates to `cost_gate_learning_lane_cron.sh` with `OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY=1`.
- Activation preflight calls `cost_gate_learning_lane.status.build_cost_gate_learning_lane_activation_preflight`.
- Child crontab writes remain delegated to the existing reviewed child installers.
- `--remove` removes Cost Gate learning first, then demo-learning evidence.

## Why This Matters

The v365 runtime audit showed the demo engine was alive but the learning loop was not:

- Cost Gate rejects were recorded in PG.
- Recent intents/orders/fills were absent.
- Demo-learning evidence cron was absent.
- Cost Gate learning-lane cron was absent.
- Runtime alpha artifact was stale and actionability was untrusted.

The new stack installer does not solve runtime staleness by itself. It gives the operator a safer next command once runtime source reconciliation is approved.

## Verification

Final local checks for this checkpoint:

```bash
bash -n helper_scripts/cron/install_demo_learning_stack_crons.sh \
  helper_scripts/cron/demo_learning_evidence_audit_cron.sh \
  helper_scripts/cron/install_demo_learning_evidence_audit_cron.sh \
  helper_scripts/cron/cost_gate_learning_lane_cron.sh \
  helper_scripts/cron/install_cost_gate_learning_lane_cron.sh

python3 -m pytest -q \
  helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py \
  helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py \
  helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py

python3 -m py_compile \
  helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py \
  helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py \
  helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py

git diff --check
```

Results:

- `bash -n ...` passed
- cron static tests: `29 passed in 0.05s`
- `py_compile` passed
- `git diff --check` passed

## Boundary

Source/test/docs only. No runtime source sync, artifact refresh, crontab/env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, execution proof, or promotion proof.

## Next Action

Operator-approved runtime sequence remains:

1. reconcile or sync `trade-core` source to the pushed expected commit, preserving/reviewing dirty runtime paths
2. run the stack installer dry-run with `OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD=<commit>`
3. apply only after preflight passes
4. observe demo-learning evidence and Cost Gate learning-lane artifacts before considering any bounded demo probe review
