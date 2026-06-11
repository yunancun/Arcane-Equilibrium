# 2026-06-11 AEG-S3 Candidate Direct Rows Builder Implementation

## Status

`STATUS: DONE_WITH_CONCERNS`

PM-local implementation is complete for the generic AEG-S3 direct rows interface.
It does not yet produce true listing fade / oi_delta / funding revive candidate
rows; those remain the next evidence tasks.

## Implemented

- Added `helper_scripts/research/aeg_s3_candidate_rows/`.
- Added CLI `aeg_s3_candidate_rows.harness`:
  `--candidate-evidence-json` + `--run-id` -> artifact run dir.
- Input contract is explicit candidate-owned evidence:
  `samples[]` with `sample_ts_utc`, `regime`, `gross_bps`, `cost_bps`, `net_bps`,
  `independence_bucket`, optional `is_oos`; optional `daily_returns`; optional
  `pbo_candidates`.
- Output contract is a direct report with top-level `candidate_regime_metrics`,
  consumable by existing `aeg_candidate_metrics`.
- Added artifacts:
  `candidate_direct_metrics_report.json`, `candidate_rows_summary.json`,
  `candidate_sample_returns.csv`, `candidate_daily_returns.json`,
  `manifest.json`, `artifact_index.json`.
- Updated `helper_scripts/SCRIPT_INDEX.md` and `TODO.md`.

## Fail-Closed Rules

- `net_bps` is computed only from explicit sample-level `net_bps`.
- `mean_daily_bps` is computed only from explicit `daily_returns`.
- `n_independent` is computed only from explicit `independence_bucket`; missing
  buckets do not fall back to row count or `n_days`.
- Missing PBO inputs leave `pbo=None`, causing downstream candidate metrics to
  reject the row.
- The module is artifact-only: no DB writes, runtime imports, Bybit auth, or
  trading path.

## Verification

Command:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py -q
```

Result:

```text
21 passed in 0.75s
```

Additional checks:

```bash
python3 -m compileall -q helper_scripts/research/aeg_s3_candidate_rows
```

Static forbidden-route search found no hits in
`helper_scripts/research/aeg_s3_candidate_rows/`; hits in the test file are only
the test's own forbidden-token list.

## Remaining AEG-S3 Work

1. Build candidate-specific evidence producers for listing fade, oi_delta, and
   funding revive.
2. Run each candidate through `aeg_s3_candidate_rows.harness`.
3. Feed each direct report through `aeg_candidate_metrics`.
4. Feed resulting `candidate_regime_metrics.csv` into `aeg_robustness_matrix`
   with execution realism and breadth/regime artifacts.
5. Require E2/MIT/QC review before treating any PASS as promotion evidence.

