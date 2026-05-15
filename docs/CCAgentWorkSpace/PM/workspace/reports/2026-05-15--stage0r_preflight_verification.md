# 2026-05-15 — Stage 0R Preflight Verification

## Scope

Step 5a rerun of W2 A4-C BTC→Alt Lead-Lag Stage 0R preflight after the
`snapshot_bucket_ts_ms` SQL alignment fix and diagnostic producer gate fix.

Runtime target:

- host: `trade-core`
- repo: `/home/ncyu/BybitOpenClaw/srv`
- Linux HEAD: `eb181d70`
- DB: `127.0.0.1 / trading_ai / trading_admin`
- SQL: `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql`
- tool: `python3 helper_scripts/reports/w2/w2_paper_edge_report.py --window-days 7 --dry-run`

## Tooling Smoke

`python3 helper_scripts/reports/w2/w2_paper_edge_report.py --smoke-test`
passed on Linux:

- plus15 fixture: eligible diagnostic path works
- plus5_15 fixture: defer diagnostic path works
- minus5 fixture: revise/archive path works
- PSR(0), DSR(K=95), block-bootstrap CI, and R²(N) smoke checks all passed

## Data Surface

Real Stage 0R report fetched `4,417` counterfactual rows over 7d for the
7-symbol cohort.

Source-tier sanity check:

| Source tier | Panel rows / snapshots | Expanded rows | Non-zero expected_dir | Kline join OK |
|---|---:|---:|---:|---:|
| `cross_asset_btc_lead_lag` | 619 | 4,333 | 130 | 4,079 |
| `cross_asset_btc_lead_lag_diagnostic` | 12 | 84 | 0 | 84 |
| **All** | 631 | 4,417 | 130 | 4,163 |

Fact: the SQL no longer has the old exact timestamp equality failure; rows are
returned and diagnostic source rows join at 100% in the current check.

Fact: the new diagnostic producer was still immature at check time: 12 snapshots
and 0 non-zero expected_dir rows.

## Mandatory Metrics

Pooled Stage 0R metrics:

| Metric | Result | Gate |
|---|---:|---|
| normal signal sample n | 122 | pooled n adequate, per-symbol n inadequate |
| avg_net_bps | -3.5570 | FAIL: below +5 and +15 bands |
| t-stat | -1.5345 | FAIL: not > 2.0 |
| PSR(0) | 0.0542 | FAIL: threshold >= 0.95 |
| DSR(K=95) | 0.0000 | FAIL: threshold >= 0.95 |
| 95% block-bootstrap CI | [-3.9919, -1.2380] | FAIL: negative and excludes zero |
| R²(60/120/300) pooled | 0.0004 / 0.0000 / 0.0017 | FAIL: R²(120) < 0.04; R²(300) > R²(60) |

Per-symbol diagnostic breakdown:

| Symbol | n | avg_net_bps | t-stat | PSR(0) | DSR | Verdict |
|---|---:|---:|---:|---:|---:|---|
| ETHUSDT | 24 | -1.99 | -1.122 | 0.143 | 0.000 | false |
| SOLUSDT | 20 | -3.67 | -1.022 | 0.147 | 0.000 | false |
| XRPUSDT | 17 | -3.63 | -1.355 | 0.089 | 0.000 | false |
| DOGEUSDT | 18 | -5.42 | -1.088 | 0.140 | 0.000 | false |
| ADAUSDT | 11 | -10.21 | -0.462 | 0.327 | 0.000 | false |
| AVAXUSDT | 16 | -4.93 | -1.059 | 0.137 | 0.000 | false |
| DOTUSDT | 16 | +2.36 | +0.671 | 0.719 | 0.000 | false |

Counterfactual delta:

- LONG rows are mostly weak/negative; only SOLUSDT LONG average is positive
  (`+4.24 bps`), still below the +5 defer band and far below +15.
- SHORT raw-forward rows are not enough to offset the signed net edge; pooled
  signed counterfactual edge is negative.
- No-signal baselines are near flat/slightly negative, consistent with sparse
  signal generation rather than broad alt drift.

## Verdict

**GATE-RED: `eligible_for_demo_canary=false`.**

Reasoning:

- Fact: pooled edge is negative (`-3.5570 bps`) and the bootstrap CI is fully
  negative.
- Fact: PSR(0), DSR(K=95), and t-stat fail.
- Fact: R²(120) fails pooled and for every symbol, so the lead-lag explanatory
  signal is not statistically meaningful in this evidence window.
- Fact: no per-symbol cohort reaches the n>=100 + t>2.0 + +15 bps diagnostic
  candidate threshold.
- Inference: the SQL/data path is sufficiently alive to evaluate the signal,
  but the current evidence does not justify spending a Stage 1 demo micro-canary.

No strategy x symbol cohort is selected for Stage 1. The best diagnostic symbol
is `DOTUSDT` by avg_net (`+2.36 bps`), but it is below the +5 defer band and
has `n=16`, `t=0.671`, `DSR=0.000`.

Needed before rerun:

- More diagnostic producer maturity, preferably enough non-zero expected_dir
  rows to support per-symbol n>=100.
- Re-check why the current diagnostic source produced 0 non-zero expected_dir
  over the first 12 snapshots; sparse signals are expected, but 0 cannot support
  Stage 0R.
- If future samples remain negative, revise/archive the A4-C lead-lag spec
  rather than launching Stage 1 demo.

Boundary: this was read-only SQL/report verification. No paper enablement, demo
canary launch, runtime config change, live auth mutation, rebuild, restart, or
deploy was performed.
