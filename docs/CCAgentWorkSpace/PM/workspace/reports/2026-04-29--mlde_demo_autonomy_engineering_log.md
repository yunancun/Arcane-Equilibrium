# MLDE Demo Autonomy Engineering Log

Date: 2026-04-29 19:05 CEST
Branch: main

## Scope

Implemented the latest decision: ML, DreamEngine, and other ML producers may learn from demo data and autonomously tune demo strategy/risk/leverage parameters. Tuned models or parameter proposals for live must remain governance-gated.

Hard boundary preserved:

- Demo can apply bounded autonomous changes.
- Live/live_demo cannot be mutated by this path.
- Live promotion is only a governed candidate requiring GovernanceHub, Decision Lease, and existing live gates.

## Commits

- `94e3cbb` Enable demo MLDE autonomous applier
  - Added V032 audit table `learning.mlde_param_applications`.
  - Added `program_code/ml_training/mlde_demo_applier.py`.
  - Wired demo applier into `EdgeEstimatorScheduler`.
  - Added healthcheck `[37] mlde_demo_applier`.
  - Added tests and PM/Codex/CLAUDE/TODO documentation.

- `fd19346` Tighten MLDE attribution regression window
  - Changed `[35]` attribution regression default from 90 minutes to 30 minutes.
  - Prevents legacy pre-fix rows from keeping the healthcheck red after the repaired deploy.

- `0f50f24` Prime scheduler DB env before MLDE backfill
  - Started bridging DB env before scheduler label backfill.

- `656c788` Pass DB URL into scheduler label backfill
  - Passed file-backed `OPENCLAW_DATABASE_URL` directly into `edge_label_backfill`.
  - Fixed scheduler backfill `no password supplied` runtime gap.

## Runtime Deployment

Linux `trade-core` was fast-forwarded and restarted with:

```bash
git pull --ff-only origin main
bash helper_scripts/restart_all.sh --keep-auth
```

No rebuild was performed.

Final Linux runtime commit:

- `656c788ae1b34e5ef278d70cf4f02c3fb5c4f309`

Engine/API restarted successfully and watchdog reported all engines alive.

## Verification

Local verification:

- MLDE/scheduler/healthcheck target tests: `42 passed`
- Follow-up scheduler patch tests: `5 passed`
- `compileall`: passed
- `git diff --check`: passed

Linux verification after final deploy:

- V031 migration: success
- V032 migration: success
- `learning.linucb_state`: 15 arms
- MLDE advisory rows 24h: 10
- `learning.mlde_param_applications`: 0 rows, expected until actionable demo recommendation meets thresholds

Healthcheck highlights after final deploy:

- `[34] intent_signal_attribution`: PASS
- `[35] mlde_learning_data_contract`: PASS
- `[36] mlde_shadow_recommendations`: PASS
- `[37] mlde_demo_applier`: WARN only because no applier decisions exist yet
- Overall healthcheck: WARN, not FAIL

Scheduler observability confirmed the backfill fix:

- latest scheduler rows: `scheduler_ok`
- latest `backfill_error_class`: empty
- previous rows had `OperationalError`, now cleared

## Current State

MLDE learning is now online in demo:

- LinUCB state exists and is being refreshed.
- Advisory rows are being produced.
- Demo autonomous applier is wired and audited.

The applier has not applied a demo change yet because current actionable recommendations are not above the configured sample/confidence gates. This is expected and preferable.

## Remaining Gaps

- `[37]` will remain WARN until a recommendation is eligible and the applier records a decision.
- `[33] maker_fill_rate` remains a strategy/execution edge issue, not an ML wiring blocker.
- Rust active LinUCB arm-space remains `v1_15`; richer `mlde_arm_id` is currently shadow/advisory only and needs a separate migration before becoming active runtime policy.
