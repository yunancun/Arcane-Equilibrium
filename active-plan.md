# Active Plan

Version: v1.7
Date: 2026-05-15
Source: TODO.md v30 + PM Stage 0R reports + `[27]` post-grace closure + W-AUDIT-8a Phase C0/C1 update + A4-C PM/PA/FA archive/RCA card + A4-C RCA start + W-AUDIT-8b spec v0.1 + v30 source-sync checkpoint

## Current Sprint

- Sprint posture: post-N+0/N+1 cleanup; active work is alpha/LG/ops gating, not Stage 1 execution.
- Business-chain target: 65% -> 70% is blocked until a future green Stage 0R packet selects a demo micro-canary cohort.

## This Week Focus

- Stage 0R: DONE and still GATE-RED. A4-C is archived from the active promotion path and retained diagnostic-only; `P1-A4C-RCA-1` started read-only and strengthened the archive read (`avg_net_bps=-1.0013`, `PSR(0)=0.1904`, `DSR=0`, R2(120)=0; finite X=5/Y=0.20 probe only +1.4739 bps).
- OI-confirmed 5m packet: spec-only. It defines `bb_breakout_oi_confirmed_5m` replay acceptance, but did not run replay and cannot authorize canary/promotion.
- `[55]`: source-cleared by `P1-HEALTHCHECK-55-INVARIANT`; patched `trade-core` DB check proves `25/25` fully-filled plan chains have real-fill ER and `0` are missing.
- `[67]`: fixed by feature-baseline apply; active rows restored to 646 across 19 symbols / 34 feature names.
- `[27]`: post-grace closed by direct 2026-05-15 18:12 UTC narrow probe PASS; it is no longer the active hard blocker.
- W-AUDIT-8a Phase C0: SOURCE/DOC closed. `market.liquidations` exists but has 0 rows; production topic builders are guarded against dormant/poison liquidation topics. C1 proof plan + standalone probe script exist; C1 still waits for 24h BB standalone WS proof of `allLiquidation.{symbol}`.
- W-AUDIT-8b: Funding Skew Directional spec v0.1 exists; next step is QC/MIT/BB review and Stage 0R replay design, not implementation.
- Replay-first validation: before sign-off, first decide whether replay/counterfactual replay can check the claim. Run it when applicable and safe; otherwise state why DB/live-runtime/WS/healthcheck evidence is required.
- Passive healthcheck source correction: `[4] phys_lock_runtime` and `[Xb] pipeline_triangulation` are fixed/PASS by `7108035d`.

## Runtime Healthcheck

- 2026-05-15 18:12 UTC direct post-grace narrow probe closed `[27]`: demo stale=3.4m / 30min_n=4; live_demo had no verdict/DCS activity in the 30m window and is inactive rather than frozen. `[66]` and `[67]` also PASSed.
- The full passive wrapper previously hung after rebuild; a future full-suite passive rerun remains useful housekeeping, but `[27]` is no longer the active hard blocker.
- Earlier 2026-05-15 12:25-12:45 UTC hard FAIL `[67]` is closed by feature-baseline restore; `[55]` is source-cleared.
- Current attention WARNs stay business/runtime maturity: `[40]` negative realized edge, `[59]` H0 acceptance quiet/missing live_demo snapshot, `[20]` H-state stub shape, `[45]` pricing source/age, plus sample-maturity/advisory watches.
- V079 is applied on `trade-core`; `learning.strategy_trial_ledger` exists and has 16,212 rows.

## Blockers

- 🚨 Stage 0R GATE-RED: A4-C `eligible_for_demo_canary=false` and archived from active promotion. RCA start remains below revive/promotion bands; it may only produce a new preregistered hypothesis, not a demo launch.
- 🚨 `P0-EDGE-1`: 5 textbook strategies still lack durable positive net edge.
- 🚨 `P0-LG-1/2/3` and `P0-OPS-1..4`: true-live infrastructure and governance still incomplete.
- ⛔ W-AUDIT-8a C1: liquidation writer/pulse revival is blocked until BB proves `allLiquidation.{symbol}` safe on an isolated WS connection for 24h.

## Available P1 Tasks

- `P1-A4C-RCA-1`
- `P1-FILL-LINEAGE-MONITOR`
- `P1-STARTUP-BURST-MITIGATION`
- `P1-V083-HALT-SESSION-CTX` current-log follow-up
- `P1-W6-5-ML-METRICS`
- `P1-AUDIT-PERF-5`
- `P1-AUDIT-AI-UX-7`

## Engine Status

- Linux `trade-core` is the active runtime machine.
- Pre-v30 Mac/origin/Linux source was verified clean/synced at `9a72d054`; this v30 update is source/docs only. Runtime binary code line remains rebuilt `7b33ab2e` because the later docs/helper sync did not rebuild/restart.
- Signed live authorization is absent and true-live remains blocked.
- Paper is disabled and remains blocked for promotion evidence.

## Next Step

Do not launch Stage 1 demo micro-canary from A4-C or the OI-confirmed 5m spec. Start with `P1-A4C-RCA-1` as a read-only RCA only; if it does not produce a new preregistered hypothesis that QC/MIT accept, keep A4-C diagnostic-only and move alpha engineering to the 24h W-AUDIT-8a C1 BB standalone proof plus W-AUDIT-8b Funding Skew QC/MIT/BB review and replay design. W-AUDIT-8c Liquidation Cluster waits for C1. True-live remains blocked by edge/LG/ops gates.
