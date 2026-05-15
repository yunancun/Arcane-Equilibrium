# W-AUDIT-8b — A4-A Funding Skew Directional Spec

Date: 2026-05-15
Status: Spec v0.1 / no implementation authority
Scope: New alpha candidate using AlphaSurface Tier 2 `FundingSkew` + `OIDeltaPanel`. No live/demo launch, no risk/sizing change, no runtime config mutation.

## PM Verdict

Funding Skew is allowed to move to spec now because Phase B funding/OI panels are already live and `[66]` panel freshness passed on 2026-05-15. It is not a resurrection of retired `funding_arb`.

This strategy treats funding as a cross-sectional crowding signal, not as a funding-payment capture or cash-and-carry arbitrage. Positive expected funding income must not be counted in promotion metrics until funding settlement attribution is first-class and MIT signs the ledger join.

## Distinction From Retired `funding_arb`

| Item | Retired `funding_arb` | W-AUDIT-8b Funding Skew |
|---|---|---|
| Core idea | single-symbol funding payment capture / basis-like arbitrage | cross-symbol crowding and squeeze/reversion signal |
| Spot leg | required for true arbitrage, absent in demo | not required |
| Positive funding payment in edge | historically incomplete / unsafe | excluded or conservatively treated as zero until ledger proof |
| AlphaSurface tag | old strategy retained only for audit | `FundingSkew` + `OIDeltaPanel` |
| Promotion path | retired by ADR-0018 | Stage 0R replay preflight → Stage 1 Demo micro-canary only |

## Hypothesis

Funding extremes encode crowded positioning. The directional edge is expected only when funding skew, OI delta, and price action agree on crowding pressure.

Candidate rules:

1. **Crowded-long fade**: symbol funding is top decile versus cohort median, OI 15m/1h is rising, price momentum is stalling, and spread to cohort median is widening → short-biased mean reversion.
2. **Crowded-short squeeze**: symbol funding is bottom decile, OI is rising, price holds above local support, and funding skew begins to mean-revert → long-biased squeeze follow-through.
3. **No-signal default**: funding extreme without OI confirmation, stale panel, or high spread/cost ratio emits no action.

## Data Contract

Inputs:

- `AlphaSurface.funding_curve`: `FundingCurveSnapshot` from `panel.funding_rates_panel`
- `AlphaSurface.oi_delta_panel`: `OIDeltaPanel` from `panel.oi_delta_panel`
- Tier 1 indicators for local trend/volatility confirmation
- AccountManager fee source for post-fee edge modelling

Required derived fields per symbol:

- `funding_bps`
- `funding_zscore_25sym`
- `funding_percentile_25sym`
- `funding_spread_to_median_bps`
- `oi_delta_15m_pct`
- `oi_delta_1h_pct`
- `local_vol_bps`
- `expected_dir` in `{-1, 0, +1}`
- `source_tier='funding_skew_directional'`

Staleness:

- funding panel WARN > 60s, FAIL > 300s
- OI panel WARN > 60s, FAIL > 300s
- any FAIL sets strategy output to no-action and writes an evaluation reason

## Signal Formula Draft

For each candidate symbol:

```text
funding_skew_bps = funding_bps(symbol) - median(funding_bps(cohort))
funding_z = robust_zscore(funding_bps(symbol), cohort)
oi_confirmed = abs(oi_delta_15m_pct) >= oi_min_pct
crowded_long = funding_z >= z_hi AND funding_percentile >= p_hi AND oi_confirmed
crowded_short = funding_z <= -z_hi AND funding_percentile <= p_lo AND oi_confirmed
```

Directional proposal:

```text
if crowded_long and price_stall_or_breakdown:
    expected_dir = -1
elif crowded_short and price_hold_or_breakout:
    expected_dir = +1
else:
    expected_dir = 0
```

Initial thresholds for replay grid only:

- `z_hi`: 1.5 / 2.0 / 2.5
- `p_hi`: 0.85 / 0.90 / 0.95
- `p_lo`: 0.15 / 0.10 / 0.05
- `oi_min_pct`: 1.0 / 2.0 / 3.0 over 15m
- holding horizon: 15m / 30m / 60m

These are trial parameters for Stage 0R replay. They must not be promoted as TOML defaults before DSR/PBO acceptance.

## Replay-First Validation

Stage 0R must run before any demo canary request.

Mandatory report fields:

- pooled and per-symbol `n`
- avg gross/net bps after fee/slippage
- funding payment attribution mode: `excluded`, `conservative_zero`, or `ledger_verified`
- PSR(0) with skew/kurt adjustment
- DSR with current strategy/symbol trial count
- block-bootstrap CI with 60m block size
- CSCV PBO
- parameter sensitivity surface, not single best cell only
- stale-panel exclusion counts
- cost-edge ratio and maker/taker split

Promotion floor:

- no symbol may be eligible below `n >= 100`
- pooled sample should be `n >= 300`
- `avg_net_bps > 0`
- PSR(0) >= 0.95
- DSR >= 0
- PBO <= 0.20
- 95% block-bootstrap lower bound must not be materially negative
- no positive edge may depend on unverified funding settlement income

Output is only `eligible_for_demo_canary=true/false`. It is not Stage 1 PASS.

## Implementation Boundary

Allowed next implementation, after PA/QC/MIT sign-off:

1. Add replay query/report for `funding_skew_directional`.
2. Add read-only diagnostic feature extraction.
3. Add strategy skeleton disabled by default.
4. Add fail-closed evaluation reasons for unavailable/stale panels.

Explicitly forbidden in this spec phase:

- changing risk sizing or leverage
- enabling demo/live trading
- counting unverified funding payments as profit
- reusing retired `funding_arb` code path as-is
- adding basis/spot execution assumptions
- opening live or live_demo Stage 1 without green Stage 0R + operator approval

## Open Questions

1. MIT must decide whether funding payment remains excluded or can be conservatively modelled as zero drag until ledger proof.
2. QC must choose whether the first replay should favour 15m or 30m holding horizon.
3. BB must confirm whether Bybit demo/public funding fields match mainnet enough for directional signal validation; execution remains demo-only after Stage 0R.

## Acceptance For Spec v1

- QC signs the signal formula and trial-count handling.
- MIT signs the data contract and funding-attribution mode.
- BB signs Bybit field compatibility.
- PM updates TODO with this spec as the current `W-AUDIT-8b` source.
