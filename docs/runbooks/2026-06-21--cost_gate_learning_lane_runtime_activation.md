# Cost-Gate Learning Lane Runtime Activation Runbook

**Status:** Draft / operator-gated  
**Runbook ID:** RUNBOOK-COST-GATE-LEARNING-ACTIVATION-001  
**Module:** Cost Gate demo-learning lane  
**Applies to:** Linux runtime `trade-core`  
**Last updated:** 2026-06-21

> **Hands off -- operator only:** this runbook describes the activation path. It does not authorize runtime source sync, crontab edits, env edits, process restart, ledger append, PG writes, Bybit calls, order authority, or Cost Gate lowering. Before executing any write step, confirm `TODO.md` operator action and latest PM/Operator report.

## Purpose

The cost-gate learning lane turns recorded demo/live_demo Cost Gate rejects into blocked-signal learning evidence:

1. PG `learning.decision_features` records Cost Gate rejects.
2. `reject_materializer.py` materializes eligible PG rows into `probe_admission_decision` JSONL rows.
3. `outcome_refresh.py` marks later market movement as `blocked_signal_outcome`.
4. `outcome_review.py` classifies side-cells as collect-more, keep-blocked, or operator-review candidate.

This is a learning/evidence loop. It does not lower the main Cost Gate and does not grant order authority.

## Activation Gates

| Gate | Required evidence | Write permission needed |
|---|---|---|
| A. Runtime source ready | `trade-core` is synced to expected `origin/main`, clean enough for activation, required files present | source reconcile/sync only |
| B. Preflight green | `cost_gate_learning_lane.status` reports source/plan readiness and expected head match | none if read-only |
| C. Artifact cron installed | dry-run crontab entry reviewed, then installed with apply flag | crontab edit |
| D. Append enabled | operator accepts local JSONL append boundary for materialized rejects/outcomes | local artifact writes |
| E. Hot-path writer enabled, optional | running engine env explicitly has `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1` | env edit + approved restart |
| F. Review loop observed | materializer/latest, ledger, refresh/latest, review/latest grow over 24-72h | observation only |

## Pre-Activation Read-Only Audit

Run from Mac or a PM shell. These commands are read-only.

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && \
  printf "HEAD=" && git rev-parse HEAD && \
  printf "BRANCH=" && git branch --show-current && \
  git status --branch --short | sed -n "1,80p"'
```

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && \
  for p in \
    helper_scripts/research/cost_gate_learning_lane/status.py \
    helper_scripts/research/cost_gate_learning_lane/reject_materializer.py \
    helper_scripts/cron/cost_gate_learning_lane_cron.sh \
    helper_scripts/cron/install_cost_gate_learning_lane_cron.sh; do
      if [ -e "$p" ]; then echo "PRESENT $p"; else echo "MISSING $p"; fi
    done'
```

```bash
ssh trade-core 'crontab -l 2>/dev/null | grep -E "cost_gate_learning_lane|demo_learning" || true'
```

```bash
ssh trade-core 'find /tmp/openclaw/cost_gate_learning_lane -maxdepth 1 -type f \
  -printf "%TY-%Tm-%Td %TH:%TM:%TS %p\n" 2>/dev/null | sort'
```

```bash
ssh trade-core 'psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -qAt -c "
SELECT count(*)
FROM learning.decision_features
WHERE engine_mode IN (\$\$demo\$\$, \$\$live_demo\$\$)
  AND ts >= now() - interval \$\$4 hours\$\$
  AND reject_reason_code LIKE \$\$cost_gate%\$\$;
"'
```

Expected state before activation:

- PG rejects may already be abundant.
- If source files are missing or checkout is behind/dirty, stop and do source reconcile first.
- If only `demo_learning_lane_plan_latest.json` exists and no ledger/materializer/review artifact exists, the learning loop is not active.

## Source Reconcile / Sync Gate

This gate is operator-owned because runtime is dirty. Do not run `git pull`, `reset`, `checkout`, or `clean` blindly.

Minimum safe sequence:

1. Record current runtime status:

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && \
  git status --porcelain=v1 > /tmp/openclaw/cost_gate_runtime_dirty_status_before_sync.txt && \
  git diff --name-status > /tmp/openclaw/cost_gate_runtime_dirty_diff_names_before_sync.txt'
```

2. Review whether dirty files are generated artifacts, local runtime WIP, or stale source drift.
3. Preserve any runtime-only files that must not be lost.
4. Sync to the PM-approved commit.
5. Re-run the read-only audit above.

Do not continue to cron activation unless these files are present:

- `helper_scripts/research/cost_gate_learning_lane/status.py`
- `helper_scripts/research/cost_gate_learning_lane/reject_materializer.py`
- `helper_scripts/research/cost_gate_learning_lane/outcome_refresh.py`
- `helper_scripts/research/cost_gate_learning_lane/outcome_review.py`
- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`

## Activation Preflight

After source is synced, run read-only preflight from runtime:

```bash
PM_APPROVED_HEAD=REPLACE_WITH_PM_APPROVED_SHA
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && \
  PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
    --data-dir /tmp/openclaw \
    --repo-root /home/ncyu/BybitOpenClaw/srv \
    --expected-head ${PM_APPROVED_HEAD} \
    --auto-detect-engine-pid \
    --print-json"
```

For writer process activation review:

```bash
PM_APPROVED_HEAD=REPLACE_WITH_PM_APPROVED_SHA
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && \
  PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
    --data-dir /tmp/openclaw \
    --repo-root /home/ncyu/BybitOpenClaw/srv \
    --expected-head ${PM_APPROVED_HEAD} \
    --require-process-writer-enabled \
    --print-json"
```

Interpretation:

- `runtime_source_ready_for_activation=true` is required before any activation.
- `plan.plan_status=READY` now means the plan artifact is recent, schema-correct, `READY_FOR_DEMO_LEARNING_PROBE`, `OPERATOR_REVIEW`, and has selected candidates. A recent source-error or no-candidate plan is not activation-ready.
- `reject_materializer_*` answers should be absent/false before cron first run and present after.
- `runtime_writer_process_enabled=false` is acceptable for materializer-only activation; it is not acceptable if the operator explicitly wants hot-path capture.

## Cron Dry Run

Preview only:

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && \
  OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv \
  OPENCLAW_DATA_DIR=/tmp/openclaw \
  OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS=1 \
  OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS=1 \
  OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES=1 \
  OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0 \
  helper_scripts/cron/install_cost_gate_learning_lane_cron.sh'
```

Review the proposed crontab entry. It should point to the synced repo and `/tmp/openclaw`.
The dry run also prints the apply preflight posture. Default apply requires read-only activation preflight plus an expected source head.
The installed wrapper refreshes the demo-learning plan at the start of every run unless `OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN=0` is explicitly set.

## Cron Install

Requires explicit operator approval. The installer now runs the read-only activation preflight before any crontab write by default. It fails closed unless:

- `OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD` or `OPENCLAW_EXPECTED_SOURCE_HEAD` is supplied.
- runtime source files are present.
- the checkout is activation-ready and matches the expected head.
- the demo-learning plan is `READY`.

Existing ledger/outcome rows are not required at install time because this cron is the bounded path that starts materializing PG rejects and refreshing blocked outcomes. `OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT=0` is an explicit bypass knob and should not be used without a separate PM/operator note.

```bash
PM_APPROVED_HEAD=REPLACE_WITH_PM_APPROVED_SHA
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && \
  OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 \
  OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD=${PM_APPROVED_HEAD} \
  OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv \
  OPENCLAW_DATA_DIR=/tmp/openclaw \
  OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS=1 \
  OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS=1 \
  OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES=1 \
  OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0 \
  helper_scripts/cron/install_cost_gate_learning_lane_cron.sh"
```

Rollback:

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && \
  OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 \
  helper_scripts/cron/install_cost_gate_learning_lane_cron.sh --remove'
```

## Optional Hot-Path Writer

Cron materialization can recover rejects already recorded in PG. Hot-path writer captures eligible rejects directly into the JSONL ledger from the running engine, but it requires env edit and approved restart.

Do not enable it unless the operator explicitly approves:

- env file update for `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`
- optional explicit plan/ledger paths
- approved restart path with `--keep-auth`
- post-restart process-env preflight proving the running engine loaded the writer env

## Post-Activation Observation

After the first scheduled run or a manually approved wrapper run:

```bash
ssh trade-core 'ls -la /tmp/openclaw/cost_gate_learning_lane && \
  tail -n 5 /tmp/openclaw/logs/cost_gate_learning_lane.log 2>/dev/null || true'
```

```bash
PM_APPROVED_HEAD=REPLACE_WITH_PM_APPROVED_SHA
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && \
  PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
    --data-dir /tmp/openclaw \
    --repo-root /home/ncyu/BybitOpenClaw/srv \
    --expected-head ${PM_APPROVED_HEAD} \
    --auto-detect-engine-pid \
    --print-json"
```

Healthy learning-loop progression:

- `reject_materializer_latest.json` exists.
- `probe_ledger.jsonl` has `probe_admission_decision` rows.
- `outcome_refresh_latest.json` has windows and blocked outcomes after price horizon maturity.
- `blocked_outcome_review_latest.json` reports one of:
  - `COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES`
  - `NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE`
  - `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`

Only the last status can trigger operator review for bounded demo probe authority. It still does not grant order authority by itself.

## Stop / Rollback Conditions

Stop and report if any of the following occurs:

- source preflight reports missing source files or expected-head mismatch
- materializer rc nonzero
- refresh/review rc nonzero
- ledger rows grow but all rows are malformed
- disk usage under `/tmp/openclaw` becomes unsafe
- review status unexpectedly implies promotion evidence or order authority
- any Bybit/private/trading call appears in logs

Rollback cron first. If hot-path writer was enabled, disable env and restart through the approved path.

## Current Known Runtime State On 2026-06-21

The latest read-only audit found:

- runtime source at `917be4cc9a3d3549328155f1863d42400c70267f`, behind current `origin/main`
- runtime dirty with many modified/untracked files
- only early `cost_gate_learning_lane/policy.py` present under runtime untracked files
- no materializer/status/cron source files present
- no cost-gate learning cron entry
- running engine writer env unset
- PG rejects abundant: 27,071 in the latest 4h audit, 4,423,477 total

This means the next blocker is runtime reconcile/sync/activation, not lack of reject data.
