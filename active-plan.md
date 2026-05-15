# Active Plan

Version: v1.1
Date: 2026-05-15
Source: TODO.md v22 + PM Stage 0R verification report + passive healthcheck fix `7108035d`

## Current Sprint

- Sprint: N+0 W1-W2 FOUNDATION HEAVY
- Business-chain target: 63% -> 65%

## This Week Focus

- Stage 0R verification: DONE. Verdict is GATE-RED; A4-C is not eligible for demo canary.
- Step 4 fill-lineage WARN resolution: resolve `[55]` `WARN_REAL_FILL_PROPAGATION_PARTIAL`, or get explicit operator waiver before any Stage 1 demo micro-canary launch.
- Passive healthcheck source correction: `[4] phys_lock_runtime` and `[Xb] pipeline_triangulation` are source-fixed by `7108035d`; 2026-05-15 12:45 UTC full unfiltered runtime run PASSed both checks (`[4]` exit_features phys_lock 24h=1 / 7d=109; `[Xb]` close-fill-linked 15/15/15).

## Runtime Healthcheck

- 2026-05-15 12:25-12:45 UTC `trade-core` full `passive_wait_healthcheck.py` run, no `--check` filter: 67 checks total = 55 PASS / 11 WARN / 1 FAIL.
- Only hard FAIL: `[67] feature_baseline_readiness` has `active feature_baselines=0`; keep `P1-WA4B-INSERT-1` active until the feature-baseline apply path populates active 34-dim baselines.
- Attention WARNs: `[40]` realized edge remains negative, `[55]` real-fill propagation remains partial, `[59]` H0 acceptance has demo pipeline quiet + missing live_demo snapshot, `[20]` H-state stub shape regressed, `[45]` pricing binding source/age remains weak. Other WARNs are sample-maturity/advisory watches.

## Blockers

- 🚨 Stage 0R GATE-RED: A4-C `eligible_for_demo_canary=false` (commit `6799e7ef`). No Stage 1 demo cohort selected.
- ⚠️ `WARN_REAL_FILL_PROPAGATION_PARTIAL`: 15/89 real-fill reports. Demo canary remains blocked unless this reaches PASS or the operator accepts a micro-canary waiver.
- 🚨 `[67] feature_baseline_readiness` FAIL: `observability.feature_baselines` has no active baselines; drift_events remains gated until `P1-WA4B-INSERT-1` is implemented/applied.

## Available P1 Tasks

- `P1-HEALTHCHECK-55-INVARIANT`
- `P1-FILL-LINEAGE-MONITOR`
- `P1-STARTUP-BURST-MITIGATION`
- `P1-V083-HALT-SESSION-CTX` runtime deploy verification
- `P1-W6-5-ML-METRICS`
- `P1-AUDIT-PERF-5`
- `P1-AUDIT-AI-UX-7`

## Engine Status

- Linux `trade-core` is the active runtime machine.
- Demo and live pipelines are active.
- Paper is disabled and remains blocked for promotion evidence.

## Next Step

Do not launch Stage 1 demo micro-canary from the current A4-C packet. Next work is `[55]` invariant cleanup plus A4-C diagnostic maturity / revise-or-archive, while continuing Alpha Surface Phase C/D and alternative alpha candidates.
