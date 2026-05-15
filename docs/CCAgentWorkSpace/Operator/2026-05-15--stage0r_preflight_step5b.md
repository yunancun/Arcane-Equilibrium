# 2026-05-15 — Stage 0R Preflight Step 5b

PM reran W2 A4-C BTC→Alt Lead-Lag Stage 0R preflight on `trade-core` after
restoring the diagnostic producer.

Verdict: **BLOCKED / GATE-RED**.

Key facts:

- `[57] btc_lead_lag_panel_health`: PASS.
- Latest diagnostic snapshot: 2026-05-15 13:53:14 UTC.
- Diagnostic source now has 201 snapshots / 1,407 expanded rows / 121 non-zero
  expected_dir rows.
- All-source NO_SIGNAL improved from the prior ~97% state to 95.63%; diagnostic
  source alone is 91.40% NO_SIGNAL / 8.60% signal.
- Stage 0R report at 2026-05-15T13:53:54Z fetched 5,740 rows.
- Pooled metrics: avg_net_bps `+0.3552`, t-stat `0.2231`, PSR(0) `0.5877`,
  DSR(K=95) `0.0000`, CI `[-1.0329, +2.1833]`, R2(120) `0.0005`.
- `eligible_for_demo_canary=false` for pooled and all 7 symbols.
- `[55]` remains `WARN_REAL_FILL_PROPAGATION_PARTIAL` with
  `chains_with_real_fill_report=24/138`.
- `[58]` is PASS for Stage 0 default / no transitions.

Stage 1 demo micro-canary launch remains blocked. Main blockers:

1. Stage 0R is still red.
2. `[55]` still needs PASS or explicit waiver.
3. No operator-approved eligible strategy x symbol cohort exists.

No paper enablement, demo canary launch, runtime config change, live auth
mutation, rebuild, restart, or deploy was performed.
