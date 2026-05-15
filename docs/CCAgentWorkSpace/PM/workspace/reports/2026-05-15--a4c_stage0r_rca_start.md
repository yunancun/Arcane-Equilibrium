# A4-C Stage 0R RCA Start

Date: 2026-05-15
Scope: `P1-A4C-RCA-1` read-only start. Commands ran on `trade-core`; no DB
write, no runtime restart, no auth mutation, no config change, no paper/demo
launch.

## Stage 0R Refresh

Current 7d dry-run report fetched `6,713` counterfactual rows for the same
7-symbol cohort.

Pooled current result:

- normal-regime signal sample `n=434`
- `avg_net_bps=-1.0013`
- `t=-0.8646`
- `PSR(0)=0.1904`
- `DSR(K=95)=0.0000`
- 95% block-bootstrap CI `[-1.7887, 0.3944]`
- R²(60/120/300)=`0.0004/0.0000/0.0042`

Per-symbol all remain `eligible_for_demo_canary=false`; no symbol has both
adequate sample and positive enough edge.

## NO_SIGNAL / Data Cause Snapshot

Expanded panel rows by source tier:

| source_tier | rows | snapshots | no_signal | no_signal_pct | long | short | extreme | btc_abs_le_10 | xcorr_abs_lt_040 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `cross_asset_btc_lead_lag` | 4,333 | 619 | 4,203 | 97.00% | 46 | 84 | 0 | 3,885 | 954 |
| `cross_asset_btc_lead_lag_diagnostic` | 2,380 | 340 | 2,056 | 86.39% | 125 | 199 | 21 | 1,925 | 630 |

Main early finding: the BTC lead-return threshold dominates sparsity. Across
symbols, `btc_abs_le_10` is 830/959 rows per symbol in the current 7d window.
That means most rows cannot emit a signal before xcorr even matters.

## Threshold Sensitivity Probe

Read-only counterfactual recomputation over finite X/Y thresholds:

| X bps | Y min | n | avg_bps | t |
|---:|---:|---:|---:|---:|
| 5.0 | 0.20 | 1,707 | +1.4739 | +2.7251 |
| 5.0 | 0.30 | 1,538 | +1.2783 | +2.3164 |
| 5.0 | 0.40 | 1,365 | +1.0481 | +1.8455 |
| 10.0 | 0.40 | 434 | -1.0013 | -0.8646 |
| 15.0 | 0.40 | 170 | -4.3926 | -2.2028 |
| 20.0 | 0.40 | 101 | -7.0124 | -2.3905 |

Lowering X to 5 bps produces more samples and weak positive average, but still
falls far below the `+15 bps` Stage 0R eligible band. Higher thresholds are
negative.

Best finite-probe per-symbol result for X=5 / Y=0.20:

| symbol | n | avg_bps | t |
|---|---:|---:|---:|
| ADAUSDT | 180 | +2.9028 | +0.8897 |
| DOTUSDT | 242 | +2.6205 | +1.8615 |
| XRPUSDT | 251 | +1.8014 | +1.9544 |
| ETHUSDT | 267 | +1.5900 | +2.3416 |

Even the best bounded loosened threshold remains below the +5 defer band for
per-symbol average, and far below +15.

## PM Read

Fact: current evidence strengthens the FA archive verdict. The obvious
threshold loosen path improves sample count but does not create enough edge.

Inference: A4-C likely lacks a tradable lead-lag effect in the current cohort /
feature shape. Continue `P1-A4C-RCA-1` only to finish the RCA report and decide
whether QC/MIT see a genuinely new preregistered hypothesis. Otherwise switch
to `W-AUDIT-8b` / `W-AUDIT-8a C1` as planned.
