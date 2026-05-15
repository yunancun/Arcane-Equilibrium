# W-AUDIT-8b — A4-A Funding Skew Directional Spec

Date: 2026-05-15
Status: Spec v0.2 review/design / no strategy implementation authority
Scope: New alpha candidate using AlphaSurface Tier 2 `FundingSkew` + `OIDeltaPanel`. No live/demo launch, no risk/sizing change, no runtime config mutation.

## PM Verdict

Funding Skew is allowed to move to Stage 0R replay design because Phase B funding/OI panels are already live and `[66]` panel freshness passed on 2026-05-15. It is not a resurrection of retired `funding_arb`.

This strategy treats funding as a cross-sectional crowding signal, not as a funding-payment capture or cash-and-carry arbitrage. Positive expected funding income must not be counted in promotion metrics until funding settlement attribution is first-class and MIT signs the ledger join.

2026-05-15 QC/MIT/BB review result: **conditional approve for Stage 0R replay design only**. No implementation, demo launch, config mutation, or promotion evidence is authorized by this spec. The next source task may only be a read-only Stage 0R replay query/report design or implementation packet after PA handoff.

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
- `funding_source_tier`
- `oi_source_tier`
- `strategy_variant='funding_skew_directional.v0_2'`
- `alpha_source_id='funding_skew_directional'`
- `funding_interval_min` or `funding_interval_hour`
- `source_mode` in `{ws_current, rest_settled}` when funding fields enter the report

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

Stage 0R v0.2 locks the first price-action confirmation as a fixed point-in-time filter, not a grid:

- `price_stall_or_breakdown`: prior closed 5m return `<= 0`
- `price_hold_or_breakout`: prior closed 5m return `>= 0`

Any later variant of price-action confirmation must be preregistered and counted in `K_total`.

Initial thresholds for replay grid only:

- `z_hi`: 1.5 / 2.0 / 2.5
- `p_hi`: 0.85 / 0.90 / 0.95
- `p_lo`: 0.15 / 0.10 / 0.05
- `oi_min_pct`: 1.0 / 2.0 / 3.0 over 15m
- holding horizon: 30m primary; 15m and 60m sensitivity cells

These are trial parameters for Stage 0R replay. They must not be promoted as TOML defaults before DSR/PBO acceptance.

Counted candidate grid:

```text
K_new_min = 25 symbols
          × 2 direction branches
          × 3 z_hi
          × 3 percentile-pairs
          × 3 oi_min_pct
          × 3 horizons
          = 4050 inspected cells before prior comparable trials
```

`K_total = K_prior + K_new_min + any additional inspected variants`. `K_prior` must be read from comparable `learning.strategy_trial_ledger` rows or conservatively declared.

## Replay-First Validation

Stage 0R must run before any demo canary request.

Mandatory report fields:

- pooled and per-symbol `n` plus `n_eff`
- avg gross/net bps after fee/slippage
- funding payment attribution mode: primary eligibility must be `excluded`
- funding interval and source mode (`ws_current` ticker surface vs `rest_settled` history)
- PSR(0) with skew/kurt adjustment
- DSR with explicit `K_total`
- block-bootstrap CI with 60m primary block and 8h funding-cycle sensitivity
- CSCV PBO
- parameter sensitivity surface, not single best cell only
- stale-panel, missing-panel, and settlement-window exclusion counts
- panel latest times, ages, source tiers, and cohort coverage
- cost-edge ratio and maker/taker split
- direction-branch breakdown: crowded-long fade vs crowded-short squeeze
- baseline lift versus no-funding/OI-confirmation baseline

Promotion floor:

- no symbol may be eligible below `n_eff >= 100`
- active direction branch must have `n_eff >= 50`
- pooled sample should be `n_eff >= 300`
- sample must span at least 14 funding cycles
- no single day or funding cycle may contribute more than 25% of eligible rows
- `avg_net_bps >= +15`
- PSR(0) >= 0.95
- DSR >= 0.95 with explicit `K_total`
- PBO <= 0.20
- 95% block-bootstrap lower bound > 0
- adjacent grid cells must show a plateau rather than a single lucky threshold cliff
- no positive edge may depend on unverified funding settlement income

Output is only `eligible_for_demo_canary=true/false`. It is not Stage 1 PASS.

## Implementation Boundary

Allowed next source task, after PA handoff:

1. Add replay query/report for `funding_skew_directional`.
2. Add read-only diagnostic feature extraction.
3. Add fail-closed evaluation reasons for unavailable/stale panels.

Explicitly forbidden in this spec phase:

- changing risk sizing or leverage
- enabling demo/live trading
- counting unverified funding payments as profit
- reusing retired `funding_arb` code path as-is
- adding basis/spot execution assumptions
- assuming every Bybit symbol has the same funding interval
- high-fanout REST polling for funding or OI
- overloading raw panel `source_tier` with strategy labels
- opening live or live_demo Stage 1 without green Stage 0R + operator approval

## Open Questions

1. PA must decide whether v0.2 fixed 5m price-action confirmation is sufficient for the first replay, or whether a narrower preregistered variant set is needed.
2. MIT must define the exact `K_prior` query against `learning.strategy_trial_ledger`.
3. BB must sign the funding interval / source-mode fields in the Stage 0R report before replay implementation.

## Acceptance For Spec v1

- QC signs the signal formula, 30m primary horizon, `K_total`, DSR/PBO gates, and sample floors.
- MIT signs raw-panel as-of joins, stale handling, source-tier separation, and funding-attribution mode.
- BB signs Bybit funding interval/source-mode compatibility and REST/WS rate-limit posture.
- PM updates TODO with this spec as the current `W-AUDIT-8b` source.
