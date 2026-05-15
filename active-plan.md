# Active Plan

Version: v1.4
Date: 2026-05-15
Source: TODO.md v28 + PM Stage 0R reports + `[27]` post-grace closure + W-AUDIT-8a Phase C0 inventory + replay-first validation update

## Current Sprint

- Sprint posture: post-N+0/N+1 cleanup; active work is alpha/LG/ops gating, not Stage 1 execution.
- Business-chain target: 65% -> 70% is blocked until a future green Stage 0R packet selects a demo micro-canary cohort.

## This Week Focus

- Stage 0R: DONE and still GATE-RED. A4-C is not eligible for demo canary.
- OI-confirmed 5m packet: spec-only. It defines `bb_breakout_oi_confirmed_5m` replay acceptance, but did not run replay and cannot authorize canary/promotion.
- `[55]`: source-cleared by `P1-HEALTHCHECK-55-INVARIANT`; patched `trade-core` DB check proves `25/25` fully-filled plan chains have real-fill ER and `0` are missing.
- `[67]`: fixed by feature-baseline apply; active rows restored to 646 across 19 symbols / 34 feature names.
- `[27]`: post-grace closed by direct 2026-05-15 18:12 UTC narrow probe PASS; it is no longer the active hard blocker.
- W-AUDIT-8a Phase C0: SOURCE/DOC closed. `market.liquidations` exists but has 0 rows; production topic builders are guarded against dormant/poison liquidation topics; C1 waits for BB standalone WS proof.
- Replay-first validation: before sign-off, first decide whether replay/counterfactual replay can check the claim. Run it when applicable and safe; otherwise state why DB/live-runtime/WS/healthcheck evidence is required.
- Passive healthcheck source correction: `[4] phys_lock_runtime` and `[Xb] pipeline_triangulation` are fixed/PASS by `7108035d`.

## Runtime Healthcheck

- 2026-05-15 18:12 UTC direct post-grace narrow probe closed `[27]`: demo stale=3.4m / 30min_n=4; live_demo had no verdict/DCS activity in the 30m window and is inactive rather than frozen. `[66]` and `[67]` also PASSed.
- The full passive wrapper previously hung after rebuild; a future full-suite passive rerun remains useful housekeeping, but `[27]` is no longer the active hard blocker.
- Earlier 2026-05-15 12:25-12:45 UTC hard FAIL `[67]` is closed by feature-baseline restore; `[55]` is source-cleared.
- Current attention WARNs stay business/runtime maturity: `[40]` negative realized edge, `[59]` H0 acceptance quiet/missing live_demo snapshot, `[20]` H-state stub shape, `[45]` pricing source/age, plus sample-maturity/advisory watches.
- V079 is applied on `trade-core`; `learning.strategy_trial_ledger` exists and has 16,212 rows.

## Blockers

- 🚨 Stage 0R GATE-RED: A4-C `eligible_for_demo_canary=false` (commit `6799e7ef`). No Stage 1 demo cohort selected.
- 🚨 `P0-EDGE-1`: 5 textbook strategies still lack durable positive net edge.
- 🚨 `P0-LG-1/2/3` and `P0-OPS-1..4`: true-live infrastructure and governance still incomplete.
- ⛔ W-AUDIT-8a C1: liquidation writer/pulse revival is blocked until BB proves a safe liquidation topic on an isolated WS connection.

## Available P1 Tasks

- `P1-FILL-LINEAGE-MONITOR`
- `P1-STARTUP-BURST-MITIGATION`
- `P1-V083-HALT-SESSION-CTX` current-log follow-up
- `P1-W6-5-ML-METRICS`
- `P1-AUDIT-PERF-5`
- `P1-AUDIT-AI-UX-7`

## Engine Status

- Linux `trade-core` is the active runtime machine.
- Mac/origin/Linux source are synced to `81bc0862`; runtime binary code line remains rebuilt `7b33ab2e` because Phase C0/replay-first changes did not rebuild/restart.
- Signed live authorization is absent and true-live remains blocked.
- Paper is disabled and remains blocked for promotion evidence.

## Next Step

Do not launch Stage 1 demo micro-canary from the current A4-C packet or the OI-confirmed 5m spec. Next alpha work is W-AUDIT-8a C1 only after BB standalone WS proof, then `W-AUDIT-8c` Liquidation Cluster and `W-AUDIT-8b` Funding Skew, while keeping true-live blocked by edge/LG/ops gates.
