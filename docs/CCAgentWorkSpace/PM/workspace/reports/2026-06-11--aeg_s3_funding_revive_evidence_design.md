# 2026-06-11 AEG-S3 Funding Revive Evidence Producer Design

## Status

`STATUS: DONE_WITH_CONCERNS`

Design is approved for a narrow artifact-only `funding_revive` evidence
producer. It turns an offline funding/price panel export into candidate
evidence JSON consumable by `aeg_s3_candidate_rows`. It does not query PG, call
Bybit, import runtime code, mutate state, or create promotion evidence by
itself.

The concern is intentional: `funding_tilt` is closed as NO-GO-C. This producer
must not silently reopen that hypothesis. `funding_revive` is scoped as a
different event-window hypothesis:

- not cross-sectional funding-tilt tertile carry;
- not a delta-neutral carry trade;
- not a fixed APR funding-short revival;
- yes: single-symbol funding stress unwinds, then an explicit post-stress
  event window tests whether price plus realized funding PnL clears cost.

## Scope

Add:

```text
helper_scripts/research/aeg_s3_funding_revive/
  __init__.py
  builder.py
  artifact.py
  harness.py
helper_scripts/research/tests/test_aeg_s3_funding_revive.py
```

## Input Contract

The producer accepts one offline JSONL panel:

```text
--panel-jsonl /path/to/funding_revive_panel.jsonl
```

Each row represents one symbol at one funding/price timestamp. Supported raw
fields:

- `symbol`
- `ts_utc`, `ts`, `timestamp`, `sample_ts_utc`, or `ts_ms`
- `funding_bps`, or `funding_rate` as fraction
- `price`, `close`, `mark_price`, or `entry_price`
- optional `funding_zscore`
- optional `forward_return_bps` as un-sided price return
- optional `funding_pnl_bps`
- optional `regime`

If `funding_zscore` is absent, it is computed per symbol from prior
`--lookback-points` funding observations. If `forward_return_bps` is absent,
it is computed from current price to first same-symbol price at or after
`--horizon-hours`. If `funding_pnl_bps` is absent, it is computed from explicit
funding rows inside the holding window. Missing window funding rows reject the
event instead of assuming zero.

The SQL/export step is external and explicit. This producer does not connect to
`research.alpha_funding_rates_history`.

## Required CLI Parameters

- `--run-id`
- `--panel-jsonl`
- `--lookback-points`
- `--horizon-hours`
- `--stress-z`
- `--exit-z`
- `--round-trip-cost-bps`
- `--k-trials`

Regime must be explicit through one of:

- row-level `regime`
- `--regime-by-date-json`
- `--default-regime`

If none is present, events are rejected as `missing_regime`.

## Event Construction

One sample = one funding stress-revive event window.

Per symbol:

1. A negative stress starts when `funding_zscore <= -stress_z`.
2. A negative stress revives when it returns to `funding_zscore >= -exit_z`.
   The event side is long.
3. A positive stress starts when `funding_zscore >= stress_z`.
4. A positive stress unwinds when it returns to `funding_zscore <= exit_z`.
   The event side is short.
5. Exit is first same-symbol row at or after `--horizon-hours`.

Sample accounting:

```text
gross_price_bps = side * forward_price_return_bps
funding_pnl_bps = sum(-side * funding_bps_settlement) over holding window
gross_bps       = gross_price_bps + funding_pnl_bps
net_bps         = gross_bps - round_trip_cost_bps
```

`side=+1` means long. `side=-1` means short. This matches the existing
funding-tilt accounting convention: long pays positive funding and receives
negative funding; short receives positive funding.

`independence_bucket = <sample_date>:funding_revive`, not symbol-specific. This
is deliberately conservative: same-day funding stress events are market-clustered
and must not inflate `n_independent`.

Daily returns are aggregated from accepted explicit samples only:

```text
daily_return[date] = mean(sample.net_bps on date) / 10000
```

Mean rather than sum is used because same-day multi-symbol events are an
equal-weight event basket, not unlimited leverage.

## PBO

Initial implementation does not fabricate PBO. It leaves `pbo_candidates`
absent, so downstream `aeg_candidate_metrics` fails closed with `missing_pbo`
until an explicit parameter-grid export exists.

## Fail-Closed Rules

- Missing symbol/timestamp -> reject row.
- Missing funding bps/rate -> reject row.
- Missing zscore and insufficient prior funding window -> reject row for event
  eligibility.
- Missing price/forward return -> reject event.
- Missing explicit funding PnL window -> reject event.
- Missing regime -> reject event.
- Overlapping same-symbol event window -> reject event.
- No DB/runtime/trading imports or writes.

## Difference From Closed Funding-Tilt

`funding_tilt` NO-GO-C was a cross-sectional carry portfolio whose positive net
was mostly down-beta / short-squeeze-insurance exposure, with carry unable to
clear cost. `funding_revive` does not reuse that hypothesis. It only packages
explicit post-stress event windows so the AEG-S3 matrix can decide from
sample-level gross/funding/cost/net rows. If the same cost-wall or beta-mask
failure appears, downstream metrics and reviews should reject it.

## Next After Implementation

1. Run against an offline export fixed to the accepted V125 funding history run.
2. Feed `funding_revive_candidate_evidence.json` to `aeg_s3_candidate_rows`.
3. Feed the direct report to `aeg_candidate_metrics` and then
   `aeg_robustness_matrix`.
4. Add candidate-grid PBO only from explicit grid output; do not synthesize it
   from the selected cell.
