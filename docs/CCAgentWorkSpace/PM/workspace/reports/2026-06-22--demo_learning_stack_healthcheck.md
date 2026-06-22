# Demo Learning Stack Post-Install Healthcheck

## Summary

This checkpoint adds a read-only post-install healthcheck for the demo-learning stack.

v366 added an operator-gated installer. v367 adds the acceptance surface that proves whether the install actually caused runtime evidence accumulation.

The healthcheck is:

- `helper_scripts/cron/demo_learning_stack_healthcheck.py`

It classifies stack state as:

- `SOURCE_NOT_READY`
- `NOT_INSTALLED`
- `INSTALLED_NOT_FIRING`
- `FIRING_NO_RECENT_STATUS`
- `ERROR`
- `FIRING_BUT_ARTIFACTS_INCOMPLETE`
- `RUNNING_NO_LEDGER_ROWS`
- `LEDGER_ONLY_NEEDS_OUTCOME_REFRESH`
- `EVIDENCE_STACK_ACTIVE`

## What It Checks

- local git source HEAD
- expected-head match
- dirty source paths
- active crontab entries for both stack crons
- `demo_learning_evidence_audit.last_fire`
- `cost_gate_learning_lane.last_fire`
- latest demo-learning evidence status JSONL row
- latest Cost Gate learning-lane status JSONL row
- latest demo-learning evidence JSON
- latest Cost Gate blocked-outcome review JSON
- Cost Gate stage return codes
- ledger rows
- blocked-signal outcome rows
- blocked-outcome review status

## Runtime Read-Only Check

During this checkpoint, PM rechecked `trade-core` read-only:

- runtime source still at `917be4cc9a3d3549328155f1863d42400c70267f`
- runtime checkout still reports `main...origin/main [behind 5]`
- runtime checkout still has many dirty/untracked paths
- no active crontab entries for `demo_learning_evidence_audit` or `cost_gate_learning_lane`
- `/tmp/openclaw/cost_gate_learning_lane/` still has only the old plan artifact and empty stdout
- `/tmp/openclaw/cron_heartbeat/` has many active runtime cron heartbeats, but not the demo-learning stack heartbeats

This confirms the current blocker remains runtime source reconcile + operator-approved stack install. The new healthcheck is ready for after that step.

## Verification

Final local checks for this checkpoint:

```bash
python3 -m pytest -q \
  helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py \
  helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py \
  helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py \
  helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py

python3 -m py_compile \
  helper_scripts/cron/demo_learning_stack_healthcheck.py \
  helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py \
  helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py \
  helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py \
  helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py

bash -n \
  helper_scripts/cron/install_demo_learning_stack_crons.sh \
  helper_scripts/cron/demo_learning_evidence_audit_cron.sh \
  helper_scripts/cron/install_demo_learning_evidence_audit_cron.sh \
  helper_scripts/cron/cost_gate_learning_lane_cron.sh \
  helper_scripts/cron/install_cost_gate_learning_lane_cron.sh

git diff --check
```

Results:

- cron/healthcheck tests: `33 passed in 0.38s`
- `py_compile` passed
- `bash -n ...` passed
- `git diff --check` passed

## Boundary

Source/test/docs plus read-only runtime ssh/git/ls/crontab/artifact inspection only. No runtime source sync, artifact refresh, crontab/env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, execution proof, or promotion proof.

## Operator Use

After runtime source is reconciled to the pushed commit and the stack installer has applied successfully:

```bash
cd /home/ncyu/BybitOpenClaw/srv
python3 helper_scripts/cron/demo_learning_stack_healthcheck.py \
  --data-dir /tmp/openclaw \
  --repo-root /home/ncyu/BybitOpenClaw/srv \
  --expected-head <pushed_commit_sha> \
  --fail-on-not-active
```

Do not consider bounded demo-probe review until this returns `EVIDENCE_STACK_ACTIVE` or a PM/operator explicitly accepts a narrower diagnostic status.
