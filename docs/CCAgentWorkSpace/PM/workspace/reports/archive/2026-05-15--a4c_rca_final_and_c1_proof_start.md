# A4-C RCA Final Verdict + C1 Proof Start

Date: 2026-05-15
Scope: `P1-A4C-RCA-1` final RCA verdict and `W-AUDIT-8a C1` standalone proof start. No production WS subscription change, no parser/writer revival, no DB write, no runtime restart, no auth change, no paper/demo launch, no risk/config mutation.

## Verdict

`P1-A4C-RCA-1` is closed as **no revive hypothesis found**.

Do not open `P1-A4C-REV-1`. Do not rerun A4-C Stage 0R for the same BTC 1m return + xcorr feature shape. A4-C remains archived from promotion and diagnostic-only.

The next alpha work is:

1. `W-AUDIT-8a C1` BB standalone 24h `allLiquidation.{symbol}` proof.
2. `W-AUDIT-8b` Funding Skew QC/MIT/BB review + Stage 0R replay design.
3. `W-AUDIT-8c` Liquidation Cluster only after C1 passes and MIT schema review signs off.

## RCA Evidence

Read-only A4-C refresh on `trade-core` fetched `6,713` rows and stayed red:

- pooled normal-signal `n=434`
- `avg_net_bps=-1.0013`
- `t=-0.8646`
- `PSR(0)=0.1904`
- `DSR(K=95)=0.0000`
- block-bootstrap CI `[-1.7887, 0.3944]`
- R²(60/120/300)=`0.0004/0.0000/0.0042`
- no per-symbol `eligible_for_demo_canary=true`

The only bounded threshold probe with positive pooled average was X=5 bps / Y=0.20:

- `n=1707`
- `avg_net_bps=+1.4739`
- `t=2.7251`

This is below even the +5 bps defer band per symbol and far below the +15 bps Stage 0R eligible band. Threshold loosening alone is therefore not a valid preregistered revive trigger.

## QC / MIT Decision

QC(default) verdict: reject/archive. Main reasons: the main 7d RCA is negative, predictive R² is effectively absent, and the best finite loosened threshold is economically trivial.

MIT(default) verdict: archive. Data availability is no longer the blocker; diagnostic rows and joins are usable. The blocker is methodology/alpha: BTC 1m lead return + xcorr has near-zero predictive power. Future reopen requires a materially different predictive variable such as liquidation/orderflow/funding features, with preregistered purge/embargo validation and explicit K/DSR/PBO handling.

## C1 Standalone Proof

The 60s isolated smoke passed but is **not** a C1 proof:

- report: `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_20260515T195158Z.md`
- verdict: `SMOKE_PASS_NOT_C1_PROOF`
- observed duration: `60.2s`
- subscribe failures: `0`
- poison events: `0`
- control topics received data

Started the 24h isolated public WS proof on `trade-core`:

- started UTC: `2026-05-15T19:53:09Z`
- expected finish UTC if uninterrupted: `2026-05-16T19:53:09Z`
- process PID: `4100789`
- log: `/tmp/openclaw/audit/liquidation_topic_probe/nohup_20260515T195309Z.log`
- command shape: `OPENCLAW_DATA_DIR=/tmp/openclaw python3 helper_scripts/bybit/liquidation_topic_probe.py --topic allLiquidation.BTCUSDT --duration-sec 86400`

C1 remains blocked until the 24h report finishes cleanly and BB + MIT sign off. Production `full_subscription_list()` must continue to exclude `liquidation.*`, `price-limit.*`, `adl-notice.*`, and `allLiquidation*`.

## Boundaries

This checkpoint did not perform:

- production WS topic revival
- parser or writer restoration
- `market.liquidations` writes
- runtime rebuild/restart
- live auth renewal
- paper enablement
- demo micro-canary launch
- risk, sizing, TOML, or config mutation
