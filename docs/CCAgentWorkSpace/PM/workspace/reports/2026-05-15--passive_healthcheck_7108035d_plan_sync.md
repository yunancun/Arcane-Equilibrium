# 2026-05-15 — Passive Healthcheck 7108035d Plan Sync

## Scope

PM runtime verification + meta-doc sync:

- Ran the full `trade-core` passive healthcheck through the canonical wrapper,
  with no `--check` filter.
- Verified commit `7108035d` fixes `[4] phys_lock_runtime` and `[Xb]
  pipeline_triangulation` behavior.
- Updated `active-plan.md` and `TODO.md` where they were stale against
  `7108035d`.

Boundary: no rebuild, restart, DB mutation, live auth mutation, or
strategy/risk parameter change.

## Result

Full healthcheck log: `/tmp/passive_wait_healthcheck_full_20260515.log`.

- Total: 67 checks
- PASS: 55
- WARN: 11
- FAIL: 1

`[4]` PASSed with `exit_features` phys_lock 24h=1 / 7d=109.
`[Xb]` PASSed with close-fill-linked 15/15/15; rejected-governance raw labels
are diagnostic-only under `7108035d`.

Only hard FAIL:

- `[67] feature_baseline_readiness`: active `observability.feature_baselines`
  rows are 0. This keeps `P1-WA4B-INSERT-1` active until the apply path
  populates active 34-dim baselines.

Attention WARNs:

- `[40]` realized edge is still negative.
- `[55]` real-fill propagation remains partial.
- `[59]` H0 acceptance is quiet for demo and missing the live_demo snapshot.
- `[20]` H-state gateway stub shape regressed.
- `[45]` pricing binding still uses weak source/age evidence.

Other WARNs are advisory or sample-maturity watches: `[41]`, `[42b]`, `[42c]`,
`[48]`, `[51]`, `[11]`.

## Verification

- `ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh"` completed.
- Count parse: 67 total / 55 PASS / 11 WARN / 1 FAIL.
- Narrow changed-check dry-run also PASSed `[4]` and `[Xb]`.
