# A4-C Unblock Engineering Card — PM/PA/FA

Date: 2026-05-15
Scope: Formal engineering card only. No code change, no DB write, no runtime
restart, no auth mutation, no paper enablement, no demo launch.

## Verdict

A4-C BTC→Alt Lead-Lag remains archived from active promotion and retained as
diagnostic infrastructure only.

PM accepts PA's bounded RCA path only as a diagnostic revive attempt:
`P1-A4C-RCA-1` may run read-only queries and produce a report. It may not spend
Demo micro-canary budget, relax Stage 0R gates, enable paper, or launch Stage 1.

FA verdict is binding for budget: A4-C does not currently justify a 7d Demo
micro-canary. Producer silence was fixed, but Step 5b still failed hard:

- `avg_net_bps=+0.3552`
- `t=0.2231`
- `PSR(0)=0.5877`
- `DSR=0.0000`
- bootstrap lower tail below zero
- R²(60/120/300)=`0.0009/0.0005/0.0027`
- no per-symbol eligible cohort

## Card Added To TODO

`TODO.md` v29 now carries the formal PM/PA/FA card:

- `P0-A4C-FA-GATE-1` — archive A4-C from active promotion.
- `P0-A4C-DEMO-BUDGET-GATE` — block Demo budget unless a future per-symbol
  Stage 0R packet is green.
- `P1-A4C-RCA-1` — next read-only Stage 0R RCA.
- `P1-A4C-REV-1` — gated bounded preregistered revise-or-archive decision.
- `P1-A4C-RERUN-1` — gated Stage 0R rerun if revision is approved.
- `P0-ALPHA-SWITCH-8B-8C` — switch effort to Funding Skew / Liquidation Cluster
  if A4-C RCA does not produce a QC/MIT-accepted hypothesis.

## Required Order

1. Run `P1-A4C-RCA-1` read-only RCA.
2. If RCA finds no new preregistered hypothesis, keep A4-C diagnostic-only and
   move to W-AUDIT-8b / W-AUDIT-8a C1.
3. If RCA does find a plausible hypothesis, PA writes the bounded revision,
   QC/MIT account for trial count K / DSR / PBO, and FA re-checks Demo budget.
4. Only after a green rerun may PM request operator approval for Stage 1 Demo
   micro-canary.

## Hard Boundaries

- No `OPENCLAW_ENABLE_PAPER=1` for promotion evidence.
- No Stage 1 Demo launch from RCA.
- No live / LiveDemo relaxation.
- No auth, risk, lease, runtime, or production WS mutation.
- No acceptance-gate relaxation to make A4-C pass.
