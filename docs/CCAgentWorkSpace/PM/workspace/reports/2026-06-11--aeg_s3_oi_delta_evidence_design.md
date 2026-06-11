# 2026-06-11 AEG-S3 OI Delta Evidence Producer Design

## Status

`STATUS: DONE_WITH_CONCERNS`

Design is approved for a narrow artifact-only `oi_delta` evidence producer. It
turns an offline panel export into candidate evidence JSON consumable by
`aeg_s3_candidate_rows`. It does not query PG, call Bybit, import runtime code,
or create promotion evidence by itself.

The concern is intentional: prior review found `oi_delta` information existed
but standalone gross edge was below VIP0 taker cost. This producer preserves
that cost wall by emitting explicit gross/cost/net sample returns instead of
repairing weak economics downstream.

## Scope

Add:

```text
helper_scripts/research/aeg_s3_oi_delta/
  __init__.py
  builder.py
  artifact.py
  harness.py
helper_scripts/research/tests/test_aeg_s3_oi_delta.py
```

## Input Contract

The producer accepts one offline JSONL panel:

```text
--panel-jsonl /path/to/oi_delta_panel.jsonl
```

Each row represents one symbol at one signal timestamp. Supported raw fields:

- `symbol`
- `ts_utc`, `ts`, `timestamp`, `sample_ts_utc`, or `ts_ms`
- `open_interest` or `oi`
- `price`, `close`, `mark_price`, or `entry_price`
- optional `regime`

The producer can also consume precomputed candidate rows when the export
already contains:

- `oi_delta_pct`
- `forward_return_bps` or `fwd_return_bps`

If `oi_delta_pct` is absent, it is computed from same-symbol prior OI at
`--lookback-hours`. If forward return is absent, it is computed from same-symbol
price at the signal timestamp and price at `--horizon-hours`.

V125 provenance alignment:

- `research.alpha_open_interest_history` source rows should use `interval_time =
  1h`, `open_interest NOT NULL`, and fixed/latest accepted `run_id`.
- This producer still takes a file export only; the SQL query that creates the
  file remains an explicit operator/research step.

## Required CLI Parameters

- `--run-id`
- `--panel-jsonl`
- `--lookback-hours`
- `--horizon-hours`
- `--round-trip-cost-bps`
- `--k-trials`

Regime must be explicit through one of:

- row-level `regime`
- `--regime-by-date-json`
- `--default-regime`

If none is present, rebalance windows are rejected as `missing_regime`.

## Sample Construction

One sample = one non-overlapping cross-sectional rebalance window.

At each accepted signal timestamp:

1. Keep symbols with valid `oi_delta_pct` and forward return.
2. Sort by `oi_delta_pct`.
3. Select top and bottom tails using `--tail-frac`.
4. Default side is `long_high_short_low`.
5. `gross_bps = mean(top.forward_return_bps) - mean(bottom.forward_return_bps)`.
6. `cost_bps = --round-trip-cost-bps`.
7. `net_bps = gross_bps - cost_bps`.
8. `independence_bucket = <signal_ts>:oi_delta_rebalance`.
9. `sample_unit = oi_delta_rebalance_window`.

`--min-spacing-hours` defaults to `--horizon-hours`. Windows closer than this
are rejected as overlapping, so `n_independent` can be derived from explicit
buckets rather than row count.

Daily returns are aggregated only from accepted explicit samples:

```text
daily_return[date] = sum(sample.net_bps on date) / 10000
```

## PBO

Initial implementation does not fabricate PBO. It leaves `pbo_candidates`
absent, so downstream `aeg_candidate_metrics` fails closed with `missing_pbo`
until an explicit parameter-grid export exists.

## Fail-Closed Rules

- Missing symbol/timestamp -> reject row.
- Missing OI delta and no valid prior OI -> reject row.
- Missing forward return and no valid future price -> reject row.
- Missing regime -> reject window.
- Fewer than `--min-symbols` valid symbols -> reject window.
- Empty or overlapping tail sets -> reject window.
- Overlapping rebalance timestamp -> reject window.
- No DB/runtime/trading imports or writes.

## Next After Implementation

1. Run against an offline export fixed to the accepted V125 OI history run.
2. Feed `oi_delta_candidate_evidence.json` to `aeg_s3_candidate_rows`.
3. Feed the direct report to `aeg_candidate_metrics` and then
   `aeg_robustness_matrix`.
4. Add candidate-grid PBO only from explicit grid output; do not synthesize it
   from the selected cell.
