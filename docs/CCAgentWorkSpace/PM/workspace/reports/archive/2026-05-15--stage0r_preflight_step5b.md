# 2026-05-15 — Stage 0R Preflight Step 5b

## Scope

Step 5b rerun of W2 A4-C BTC→Alt Lead-Lag Stage 0R preflight on
`trade-core` after restoring the diagnostic producer via
`OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC=1`.

Runtime target:

- host: `trade-core`
- repo: `/home/ncyu/BybitOpenClaw/srv`
- observed Linux HEAD: `a7900d38`
- engine watchdog: demo alive, live alive, paper disabled
- report command: `python3 helper_scripts/reports/w2/w2_paper_edge_report.py --window-days 7 --dry-run`
- health check: direct `[57]` function call because the remote CLI revision does not support narrow `--check [57]`

Boundary: read-only SQL/report verification. No paper enablement, demo canary
launch, runtime config change, live auth mutation, rebuild, restart, or deploy
was performed.

## Tooling

Stage 0R smoke test passed:

- plus15 fixture emits `eligible_for_demo_canary=true`
- plus5_15 fixture emits defer diagnostics
- minus5 fixture emits revise/archive
- PSR(0), DSR(K=95), block-bootstrap CI, and R2(N) smoke checks passed

`[57] btc_lead_lag_panel_health` passed by direct check:

- window: 60m
- total_n: 60
- age: 27.2s
- cohort: 7/7
- extreme: 2/60 = 3.3%
- book imbalance: real, avg_abs=0.7040, nonnull_n=60/60

## Data Surface

Direct 7d panel distribution after restoration:

| Source tier | Snapshots | Expanded rows | No signal | Long | Short | Signal rows | No-signal pct | Signal pct | Kline join OK | Latest snapshot UTC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `cross_asset_btc_lead_lag` | 619 | 4,333 | 4,203 | 46 | 84 | 130 | 97.00% | 3.00% | 4,079 | 2026-05-11 10:22:48 |
| `cross_asset_btc_lead_lag_diagnostic` | 201 | 1,407 | 1,286 | 14 | 107 | 121 | 91.40% | 8.60% | 1,407 | 2026-05-15 13:53:14 |
| **All** | 820 | 5,740 | 5,489 | 60 | 191 | 251 | 95.63% | 4.37% | 5,486 | 2026-05-15 13:53:14 |

Fact: expected_dir distribution improved versus Step 5a's prior all-source
97% NO_SIGNAL state. Current all-source NO_SIGNAL is 95.63%, and the restored
diagnostic source itself is 91.40% NO_SIGNAL / 8.60% signal.

Inference: the diagnostic producer is no longer silent-dead and is now
contributing fresh non-zero expected_dir rows. The signal remains sparse.

## Stage 0R Metrics

Latest Stage 0R report at `2026-05-15T13:53:54Z` fetched 5,740 rows over 7d.

Pooled metrics:

| Metric | Result | Gate |
|---|---:|---|
| normal signal sample n | 231 | pooled n improved, per-symbol n still below 100 |
| avg_net_bps | +0.3552 | FAIL: below +5 and +15 diagnostic bands |
| t-stat | +0.2231 | FAIL: not > 2.0 |
| PSR(0) | 0.5877 | FAIL: threshold >= 0.95 |
| DSR(K=95) | 0.0000 | FAIL: threshold >= 0.95 |
| 95% block-bootstrap CI | [-1.0329, +2.1833] | FAIL: lower tail below zero |
| R2(60/120/300) pooled | 0.0009 / 0.0005 / 0.0027 | FAIL: R2(120) < 0.04; R2(300) > R2(60) |

Per-symbol `eligible_for_demo_canary` remained false for all 7 cohort symbols:
ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, AVAXUSDT, DOTUSDT.

Best average was DOTUSDT at +3.78 bps with n=33, t=0.959, PSR(0)=0.825, DSR=0.
It remains below the +5 defer band and far below the +15 eligible band.

## Verdict

**GATE-RED: `eligible_for_demo_canary=false`.**

Facts:

- Producer restoration fixed the silent diagnostic-row problem.
- `[57]` is PASS.
- expected_dir distribution improved from prior all-source ~97% NO_SIGNAL to
  95.63% NO_SIGNAL, with diagnostic-source signal share at 8.60%.
- Stage 0R remains below required edge/statistical thresholds.
- `[55]` still warns:
  `WARN_REAL_FILL_PROPAGATION_PARTIAL`, `chains_with_real_fill_report=24`,
  `chains=138`, `bad_report_quality=0`.
- `[58]` is PASS as Stage 0 default / no stage transitions.

Remaining blockers for Stage 1 demo micro-canary launch:

1. Stage 0R must turn green: current `eligible_for_demo_canary=false`.
2. `[55]` fill-lineage must reach PASS or receive explicit PM/operator waiver.
3. Operator-approved strategy x symbol cohort is absent because no cohort is eligible.

PM sign-off: **BLOCKED** for Stage 1 demo canary launch. The correct next path
is A4-C revise/archive analysis or continued diagnostic maturity, not demo
micro-canary launch.
