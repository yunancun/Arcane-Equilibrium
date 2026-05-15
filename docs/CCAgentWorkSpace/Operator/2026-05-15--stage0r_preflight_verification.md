# 2026-05-15 — Stage 0R Preflight Verification

Step 5a reran W2 A4-C BTC→Alt Lead-Lag Stage 0R preflight on Linux
`trade-core` at repo head `eb181d70`, using
`sql/queries/w2_btc_alt_lead_lag_counterfactual.sql` through the existing
W2 report CLI.

Verdict: **GATE-RED — `eligible_for_demo_canary=false`**.

Key metrics:

| Metric | Result |
|---|---:|
| fetched rows | 4,417 |
| normal signal n | 122 |
| avg_net_bps | -3.5570 |
| t-stat | -1.5345 |
| PSR(0) | 0.0542 |
| DSR(K=95) | 0.0000 |
| 95% bootstrap CI | [-3.9919, -1.2380] |
| pooled R²(60/120/300) | 0.0004 / 0.0000 / 0.0017 |

No per-symbol cohort qualified. Best diagnostic symbol was `DOTUSDT`
(`+2.36 bps`, `n=16`, `t=0.671`, `DSR=0.000`), which is below the +5 defer
band and not eligible.

Source-tier sanity: legacy panel rows=619; diagnostic source rows=12 snapshots
/ 84 expanded rows / 0 non-zero expected_dir at check time. The SQL path is
alive, but diagnostic producer maturity and statistical edge are insufficient.

No Stage 1 demo micro-canary should be launched from this evidence packet.

Boundary: read-only verification only. No paper enablement, demo canary launch,
runtime config change, live auth mutation, rebuild, restart, or deploy.
