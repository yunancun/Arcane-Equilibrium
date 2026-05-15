# Active Plan

Version: v1.3
Date: 2026-05-15
Source: TODO.md v25 + PM/PA/FA 5-day audit sync + PM Stage 0R reports + `trade-core` passive healthcheck 2026-05-15T15:47:01Z

## Current Sprint

- Sprint posture: post-N+0/N+1 cleanup; active work is alpha/LG/ops gating, not Stage 1 execution.
- Business-chain target: 65% -> 70% is blocked until a future green Stage 0R packet selects a demo micro-canary cohort.

## This Week Focus

- Stage 0R: DONE and still GATE-RED. A4-C is not eligible for demo canary.
- OI-confirmed 5m packet: spec-only. It defines `bb_breakout_oi_confirmed_5m` replay acceptance, but did not run replay and cannot authorize canary/promotion.
- `[55]`: source-cleared by `P1-HEALTHCHECK-55-INVARIANT`; patched `trade-core` DB check proves `25/25` fully-filled plan chains have real-fill ER and `0` are missing.
- `[67]`: fixed by feature-baseline apply; active rows restored to 646 across 19 symbols / 34 feature names.
- `[27]`: new hard FAIL in latest full passive healthcheck; intent persistence is stale while DCS/verdicts continue.
- Passive healthcheck source correction: `[4] phys_lock_runtime` and `[Xb] pipeline_triangulation` are fixed/PASS by `7108035d`.

## Runtime Healthcheck

- 2026-05-15 15:47 UTC full passive wait healthcheck is still FAIL due `[27] intents_counter_freeze`: demo stale=50.1m, live_demo stale=46.2m, 30min intents=0 while approved verdicts and DCS evaluations continued.
- Earlier 2026-05-15 12:25-12:45 UTC hard FAIL `[67]` is closed by feature-baseline restore; `[55]` is source-cleared.
- Current attention WARNs stay business/runtime maturity: `[40]` negative realized edge, `[59]` H0 acceptance quiet/missing live_demo snapshot, `[20]` H-state stub shape, `[45]` pricing source/age, plus sample-maturity/advisory watches.
- V079 is applied on `trade-core`; `learning.strategy_trial_ledger` exists and has 16,212 rows.

## Blockers

- 🚨 Stage 0R GATE-RED: A4-C `eligible_for_demo_canary=false` (commit `6799e7ef`). No Stage 1 demo cohort selected.
- 🚨 `[27] intents_counter_freeze`: runtime intent persistence wedge; clear `P1-INTENT-FREEZE-27` before any canary/promotion-sensitive runtime action.
- 🚨 `P0-EDGE-1`: 5 textbook strategies still lack durable positive net edge.
- 🚨 `P0-LG-1/2/3` and `P0-OPS-1..4`: true-live infrastructure and governance still incomplete.
- ⚠️ Linux `trade-core` source worktree has unrelated dirty WIP; do not force-pull or reset during sync.

## Available P1 Tasks

- `P1-FILL-LINEAGE-MONITOR`
- `P1-STARTUP-BURST-MITIGATION`
- `P1-V083-HALT-SESSION-CTX` current-log follow-up
- `P1-W6-5-ML-METRICS`
- `P1-AUDIT-PERF-5`
- `P1-AUDIT-AI-UX-7`

## Engine Status

- Linux `trade-core` is the active runtime machine.
- Demo and live pipelines are active.
- Paper is disabled and remains blocked for promotion evidence.

## Next Step

Do not launch Stage 1 demo micro-canary from the current A4-C packet or the OI-confirmed 5m spec. Next work is A4-C diagnostic maturity / revise-or-archive, then Alpha Surface Phase C/D and alternative alpha candidates, while keeping true-live blocked by edge/LG/ops gates.
