# 2026-06-11 AEG-S3 Listing Fade Evidence Producer Design

## Status

`STATUS: DONE_WITH_CONCERNS`

Design is approved for a narrow artifact-only producer. It creates candidate
evidence JSON for the already implemented `aeg_s3_candidate_rows` harness. It
does not run the production collector, query PG, subscribe WS, or create
promotion evidence.

## Scope

Add:

```text
helper_scripts/research/aeg_s3_listing_fade/
  __init__.py
  builder.py
  artifact.py
  harness.py
helper_scripts/research/tests/test_aeg_s3_listing_fade.py
```

## Inputs

The producer accepts either:

1. A Gate-B run directory containing `capture_lag.jsonl` and `markout.jsonl`.
2. A JSONL export of `research.listing_capture_events` rows.

Both are offline files. The producer must not connect to PG or Bybit.

Required CLI parameters:

- `--run-id`
- `--horizon-s`
- `--round-trip-cost-bps`
- `--k-trials`

Regime assignment must be explicit through one of:

- `--regime-by-date-json`
- `--default-regime`

If neither is present, samples are rejected as missing regime. This avoids
creating an unlabeled regime that could pass downstream filters accidentally.

Optional:

- `--oos-start-date`
- `--allow-slow-capture` for diagnostic runs only; default excludes slow or
  missing capture.

## Sample Construction

One sample = one listing event window:

- entry = first public trade / markout trigger price
- exit = first observed price at or after `horizon_s`
- side = short fade
- `gross_bps = -markout_bps`
- `cost_bps = --round-trip-cost-bps`
- `net_bps = gross_bps - cost_bps`
- `independence_bucket = <sample_date>:<symbol>`
- `sample_unit = listing_event_window`

Daily returns are computed from explicit sample rows by sample date:

```text
daily_return[date] = sum(sample.net_bps on date) / 10000
```

This is not scalar-to-series synthesis; it is aggregation from explicit event
samples. If there are no accepted samples, no daily returns are emitted.

## PBO

The producer does not fabricate PBO. It may build `pbo_candidates` only when
the input contains enough explicit variant cells. The initial implementation
will leave PBO absent, causing downstream `aeg_candidate_metrics` to fail
closed with `missing_pbo` until candidate-grid evidence is added.

## Fail-Closed Rules

- Missing capture lag -> reject sample.
- `capture_verdict != PASS_CAPTURE` -> reject by default.
- Missing horizon fill -> reject sample.
- Missing regime -> reject sample.
- Missing cost/k-trials at CLI -> fail argument parsing.
- Gate-B `INCONCLUSIVE_NO_TRANSITION` run can produce zero samples, not a fake
  negative sample.
- No DB/runtime/trading imports or writes.

## Next After Implementation

1. Run the producer against any existing Gate-B true-transition run if present.
2. If no true-transition artifact exists, keep status as infrastructure-ready
   and wait for operator-timed 24h capture.
3. Feed produced evidence to `aeg_s3_candidate_rows.harness`.
4. Feed direct report to `aeg_candidate_metrics` and then `aeg_robustness_matrix`.

