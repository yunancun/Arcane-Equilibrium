# W-AUDIT-8b Funding Skew Review + Stage 0R Design

Date: 2026-05-15
Scope: PM integration of QC/MIT/BB review for `W-AUDIT-8b` Funding Skew Directional. This is review/design only. No strategy implementation, no demo/live launch, no runtime restart, no DB write, no auth change, no risk/sizing/config mutation.

## Verdict

`W-AUDIT-8b` is conditionally approved for **Stage 0R replay design only**.

It is not implementation-ready as a strategy. It may proceed to a read-only Stage 0R replay query/report packet after PA handoff. The replay output may only be `eligible_for_demo_canary=true/false`.

The active alpha lane is now:

1. Finish `W-AUDIT-8b` Stage 0R replay packet design.
2. Implement only the read-only replay/report path after PA sign-off.
3. Keep strategy skeleton / demo micro-canary / runtime config changes blocked until a future green Stage 0R report and operator approval.

## Current Runtime Panel Check

Read-only `trade-core` panel freshness probe:

```text
2026-05-15 22:13:14 CEST
panel_aggregator_health overall=PASS engine=ALIVE
funding=PASS(20929ms)
oi=PASS(20969ms)
```

This supports replay-design work, but it does not prove edge.

## QC Verdict

QC(default): valid research hypothesis, revise before v1.

Required corrections:

- Treat `crowded-long fade` and `crowded-short squeeze` as separate branches.
- Funding alone is not directional alpha; point-in-time price action must confirm the branch.
- Primary horizon is `30m`; `15m` and `60m` are sensitivity cells and count in `K`.
- Candidate unit is `strategy × symbol × direction-branch × parameter cell`.
- `DSR >= 0` is rejected; eligibility requires `DSR >= 0.95` or equivalent one-sided confidence.
- PBO must be time-blocked with purge/embargo; insufficient PBO power forces `eligible_for_demo_canary=false/defer_data`.

Stage 0R promotion floor:

- eligible symbol `n_eff >= 100`
- active branch `n_eff >= 50`
- pooled `n_eff >= 300`
- at least 14 funding cycles
- no single day or funding cycle > 25% of eligible rows
- `avg_net_bps >= +15`
- PSR(0) >= 0.95
- DSR >= 0.95 with explicit `K_total`
- PBO <= 0.20
- block-bootstrap lower bound > 0
- adjacent grid cells show a plateau

## MIT Verdict

MIT(default): conditional approve for Stage 0R design only.

Data requirements:

- Use raw `panel.funding_rates_panel` and `panel.oi_delta_panel`.
- Join latest panel row where `snapshot_ts_ms <= signal_ts_ms`.
- Do not use continuous aggregates unless buckets are proven fully closed before the signal.
- Preserve raw provenance as `funding_source_tier` and `oi_source_tier`; put `funding_skew_directional` in `strategy_variant` / `alpha_source_id`, not in raw `source_tier`.
- Row-level `age_ms` is required for both panels.
- `age_ms > 60s` is WARN/diagnostic.
- `age_ms > 300s` is eligibility exclusion and runtime no-action.
- Compute cross-sectional zscore/median from one as-of funding snapshot only.
- No future funding history, no future settlement outcome, no partially formed candles, no post-signal panel rows.
- Eligibility funding attribution mode is `excluded`. Positive funding income cannot count.

CV / replay controls:

- `label_end_ts = signal_ts + horizon`.
- Purge overlapping label windows.
- Use walk-forward / purged k-fold / CSCV.
- Include `K`, OOS pct >= 20%, CV protocol, and embargo satisfying repo invariant `>= max(7d, ceil(2 * half_life_days))`.

## BB Verdict

BB(default): approve to Stage 0R replay design; no exchange-facing blocker before replay design.

Required BB fields:

- Funding semantics: positive funding means longs pay shorts; negative means shorts pay longs.
- Do not assume every symbol uses an 8h interval; record `funding_interval_min` or `funding_interval_hour`.
- Keep ticker current/upcoming funding separate from REST settled funding history.
- If REST funding history is used, do not call it with only `startTime`.
- OI absolute size is not cross-symbol comparable for linear symbols; use per-symbol delta percent / zscore.
- Keep WS-first posture; do not add high-fanout REST polling.
- Public market data replay does not relax demo/live/true-live boundaries.

## Locked Stage 0R v0.2 Design

Signal variant:

- `strategy_variant='funding_skew_directional.v0_2'`
- `alpha_source_id='funding_skew_directional'`
- branches: `crowded_long_fade`, `crowded_short_squeeze`
- primary horizon: `30m`
- sensitivity horizons: `15m`, `60m`

First fixed price-action confirmation:

- short fade branch: prior closed 5m return `<= 0`
- long squeeze branch: prior closed 5m return `>= 0`

Grid:

- `z_hi`: 1.5 / 2.0 / 2.5
- percentile pairs: 0.85/0.15, 0.90/0.10, 0.95/0.05
- `oi_min_pct`: 1.0 / 2.0 / 3.0 over 15m
- horizons: 15m / 30m / 60m
- symbols: current 25-symbol panel cohort

Minimum counted cells:

```text
25 symbols × 2 branches × 3 z_hi × 3 percentile-pairs × 3 oi_min × 3 horizons
= 4050 new inspected cells
```

`K_total = K_prior + 4050 + any additional inspected variants`.

## Stage 0R Report Contract

Mandatory fields:

- panel latest times, ages, source tiers, and cohort coverage
- stale/missing exclusion counts
- per-symbol and pooled `n` / `n_eff`
- branch breakdown
- avg gross bps and avg net bps after conservative fee/slippage
- funding attribution mode, fixed to `excluded` for eligibility
- settlement-window counts and adverse-drag sensitivity
- PSR(0) with skew/kurtosis adjustment
- DSR with explicit `K_total`
- CSCV PBO
- block-bootstrap CI with 60m primary block and 8h funding-cycle sensitivity
- sensitivity grid with plateau check
- baseline lift versus no-funding/OI-confirmation baseline
- maker/taker split and cost-edge ratio
- final `eligible_for_demo_canary=true/false`

## Stop Rules

Reject / fail closed if any of the following occurs:

- pooled-only pass with no eligible `strategy × symbol × branch`
- vague or understated `K_total`
- missing PBO or underpowered PBO treated as waiver
- `DSR < 0.95`
- positive funding income counted without ledger-verified attribution
- stale panel rows included in eligibility
- post-hoc threshold expansion
- retired `funding_arb` code semantics or carry-arbitrage framing
- production config, risk, sizing, demo/live, or true-live mutation before future approval

## Next Task

Create the PA/E1 work packet for a read-only `funding_skew_directional` Stage 0R replay query/report. The work packet must not include a tradeable strategy implementation.
