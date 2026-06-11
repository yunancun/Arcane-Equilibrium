# 2026-06-11 AEG-S3 OI Delta Evidence Producer Implementation

## Status

`STATUS: DONE_WITH_CONCERNS`

The OI-delta evidence producer is implemented and unit-tested as PM-local
infrastructure. It does not create promotion proof because no accepted V125
OI/price/regime panel export and no candidate-grid PBO evidence were available
in this session.

## Implemented

- Added `helper_scripts/research/aeg_s3_oi_delta/`.
- Added CLI `aeg_s3_oi_delta.harness`.
- Supported offline JSONL panel input:
  - raw `open_interest` + price rows, where the builder computes OI delta and
    horizon forward returns;
  - precomputed `oi_delta_pct` + `forward_return_bps` rows, for research exports
    that already materialized the leak-free features.
- Output artifact:
  - `oi_delta_candidate_evidence.json`
  - `oi_delta_evidence_summary.json`
  - `manifest.json`
  - `artifact_index.json`
- Updated `helper_scripts/SCRIPT_INDEX.md` and `TODO.md`.

## Evidence Rules

- One sample = one non-overlapping cross-sectional rebalance window.
- `oi_delta_pct` is computed from same-symbol prior OI at `--lookback-hours`
  when not supplied.
- Forward return is computed from same-symbol signal price to
  `--horizon-hours` future price when not supplied.
- Default side = `long_high_short_low`.
- `gross_bps = mean(top-tail forward return) - mean(bottom-tail forward return)`.
- `net_bps = gross_bps - --round-trip-cost-bps`.
- `independence_bucket = <signal_ts>:oi_delta_rebalance`.
- `--min-spacing-hours` defaults to `--horizon-hours` to prevent overlapping
  windows from being counted as independent samples.
- Regime must be explicit via row-level `regime`, `--regime-by-date-json`, or
  `--default-regime`.
- Daily returns are aggregated from accepted explicit samples only.
- PBO is intentionally absent until explicit candidate-grid evidence exists.

## Verification

Focused command:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py -q
```

Result:

```text
6 passed in 0.14s
```

Focused regression with the adjacent AEG-S3 path:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_gate_b_probe.py -q
```

Result:

```text
70 passed in 1.52s
```

Additional checks:

```bash
python3 -m compileall -q helper_scripts/research/aeg_s3_oi_delta \
  helper_scripts/research/aeg_s3_listing_fade \
  helper_scripts/research/aeg_s3_candidate_rows
```

Static forbidden-route search found no hits in
`helper_scripts/research/aeg_s3_oi_delta/`; hits in the test file are only the
test's own forbidden-token list.

The synthetic end-to-end path intentionally reaches `aeg_candidate_metrics` as
`FAIL` with only `missing_pbo`, while `net_bps` is negative after the explicit
round-trip cost. This matches the prior research conclusion: OI delta can carry
information, but the standalone candidate is blocked by costs unless a future
variant provides materially better economics.

## Remaining Work

1. Export an offline panel fixed to the accepted V125 OI history run
   (`18b3c2f8...`) plus aligned price and regime labels.
2. Run the producer and feed its evidence through:
   `aeg_s3_candidate_rows` -> `aeg_candidate_metrics` ->
   `aeg_robustness_matrix`.
3. Add explicit `oi_delta` candidate-grid evidence for PBO.
4. Send to E2/MIT/QC before any promotion interpretation.
