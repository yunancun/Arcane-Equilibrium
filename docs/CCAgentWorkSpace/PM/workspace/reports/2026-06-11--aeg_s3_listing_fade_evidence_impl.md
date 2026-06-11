# 2026-06-11 AEG-S3 Listing Fade Evidence Producer Implementation

## Status

`STATUS: DONE_WITH_CONCERNS`

The listing-fade evidence producer is implemented and tested as PM-local
infrastructure. It does not create promotion proof because no operator-timed
true Gate-B transition artifact and no listing-fade candidate-grid PBO evidence
were available in this session.

## Implemented

- Added `helper_scripts/research/aeg_s3_listing_fade/`.
- Added CLI `aeg_s3_listing_fade.harness`.
- Supported offline sources:
  - Gate-B run dir with `capture_lag.jsonl` + `markout.jsonl`.
  - JSONL export of V130-style `research.listing_capture_events` rows.
- Output artifact:
  - `listing_fade_candidate_evidence.json`
  - `listing_fade_evidence_summary.json`
  - `manifest.json`
  - `artifact_index.json`
- Updated `helper_scripts/SCRIPT_INDEX.md` and `TODO.md`.

## Evidence Rules

- One sample = one listing event window.
- Entry = first public trade / markout trigger price.
- Exit = first observed price at or after `--horizon-s`.
- Side = short listing fade.
- `gross_bps = -markout_bps`.
- `net_bps = gross_bps - --round-trip-cost-bps`.
- `independence_bucket = <sample_date>:<symbol>`.
- Regime must be explicit through `--regime-by-date-json` or `--default-regime`.
- Default capture policy accepts only `PASS_CAPTURE`; `SLOW_CAPTURE` requires
  explicit `--allow-slow-capture`.
- Daily returns are aggregated from accepted explicit samples only.
- PBO is intentionally absent until explicit candidate-grid evidence exists.

## Verification

Focused command:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_gate_b_probe.py -q
```

Result:

```text
64 passed in 1.77s
```

Additional checks:

```bash
python3 -m compileall -q helper_scripts/research/aeg_s3_listing_fade helper_scripts/research/aeg_s3_candidate_rows
```

Static forbidden-route search found no hits in
`helper_scripts/research/aeg_s3_listing_fade/`; hits in the test file are only
the test's own forbidden-token list.

The synthetic end-to-end path intentionally reaches
`aeg_candidate_metrics` as `FAIL` with only `missing_pbo`, proving the producer
does not fabricate PBO while preserving all other direct-row fields.

## Remaining Work

1. Import or wait for a true Gate-B transition artifact from the operator-timed
   24h run.
2. Add explicit listing-fade candidate-grid evidence for PBO.
3. Run produced evidence through:
   `aeg_s3_candidate_rows` -> `aeg_candidate_metrics` ->
   `aeg_robustness_matrix`.
4. Add sibling producers for `oi_delta` and `funding_revive`.
5. Send to E2/MIT/QC before any promotion interpretation.
