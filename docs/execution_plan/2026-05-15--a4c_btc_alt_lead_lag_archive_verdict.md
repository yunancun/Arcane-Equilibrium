# A4-C BTC→Alt Lead-Lag — Revise-Or-Archive Verdict

Date: 2026-05-15
Status: Archived as promotion candidate; retained as diagnostic infrastructure
Scope: PM decision after Stage 0R Step 5b. No code deletion, no runtime mutation, no config change, no demo launch.

## Verdict

A4-C should be archived from the active promotion path now.

It may remain as a diagnostic cross-asset panel / feature source, but it should not consume the next alpha implementation slot and must not request Stage 1 Demo micro-canary.

## Basis

Stage 0R Step 5b after diagnostic producer restoration still returned `eligible_for_demo_canary=false`.

Key facts from the PM report:

- pooled normal-signal `n=231`
- `avg_net_bps=+0.3552`
- `t=0.2231`
- `PSR(0)=0.5877`
- `DSR(K=95)=0.0000`
- block-bootstrap CI `[-1.0329, +2.1833]`
- pooled R²(60/120/300)=`0.0009/0.0005/0.0027`
- no per-symbol `eligible_for_demo_canary=true`
- all-source `NO_SIGNAL=95.63%`; diagnostic source signal density improved to 8.60% but remains weak

The A4-C spec already defined the archive rule:

- if N=120 R² < 0.04, revise to N=60
- if N=60 R² also < 0.04, archive the A4-C path

Step 5b has N=60 R² `0.0009`, which is not close to the minimum predictive threshold. Threshold loosening would be selection pressure without evidence of predictive power.

## What Remains Useful

Keep:

- `panel.btc_lead_lag_panel` as diagnostic evidence
- `[57] btc_lead_lag_panel_health` as source-freshness and producer-health check
- cross-asset panel rows for future Hypothesis Pipeline feature exploration

Do not keep:

- A4-C as a Stage 0R promotion candidate
- A4-C as the next Stage 1 demo cohort source
- any paper-based A4-C promotion language
- threshold/signal-density tuning as a standalone alpha task

## Future Reopen Conditions

Reopen only if a new hypothesis changes the predictive variable, not just thresholds.

Acceptable reopen triggers:

- new lead source beyond BTC 1m return, such as liquidation pulse or orderflow imbalance after W-AUDIT-8a C1/D
- regime-specific causal hypothesis with predeclared split and purge/embargo validation
- Hypothesis Pipeline proposes a different cross-asset feature with OOS evidence

Non-triggers:

- lowering `threshold_X`
- lowering `threshold_Y`
- selecting one symbol after seeing the failed pooled result
- using paper evidence after AMD-2026-05-15-01

## Queue Impact

Next alpha work should move to:

1. W-AUDIT-8a C1 BB standalone liquidation topic proof.
2. W-AUDIT-8b Funding Skew Directional spec/replay.
3. W-AUDIT-8c Liquidation Cluster spec only after C1 proof.

This is a docs/planning verdict only. It does not remove existing source code.
