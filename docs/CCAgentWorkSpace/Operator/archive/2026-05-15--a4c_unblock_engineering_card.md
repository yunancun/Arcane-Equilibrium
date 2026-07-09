# A4-C Unblock Engineering Card — PM/PA/FA

Date: 2026-05-15
Scope: Formal engineering card only. No code change, no DB write, no runtime
restart, no auth mutation, no paper enablement, no demo launch.

## Verdict

A4-C BTC→Alt Lead-Lag remains archived from active promotion and retained as
diagnostic infrastructure only.

`P1-A4C-RCA-1` may run read-only RCA. It may not spend Demo micro-canary budget,
relax Stage 0R gates, enable paper, or launch Stage 1.

FA verdict is binding for budget: Step 5b still failed hard
(`avg_net_bps=+0.3552`, `t=0.2231`, `PSR(0)=0.5877`, `DSR=0.0000`,
CI lower < 0, R² near zero, no eligible symbol).

## Next Order

1. Run `P1-A4C-RCA-1` read-only RCA.
2. If no new preregistered hypothesis appears, keep A4-C diagnostic-only and
   move to W-AUDIT-8b / W-AUDIT-8a C1.
3. If a hypothesis appears, require PA + QC/MIT + FA before any rerun can ask
   for Demo budget.
