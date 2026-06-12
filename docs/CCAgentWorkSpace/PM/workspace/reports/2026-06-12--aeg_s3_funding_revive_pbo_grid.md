# AEG-S3 funding_revive PBO grid run

Date: 2026-06-12
Host: Linux `trade-core`
Scope: artifact-only funding_revive PBO grid generation from the existing V125/V127 true panel. No CI, no deploy, no restart, no DB write, no exchange call, no runtime mutation.

## Code

- Commit: `03b308c7` (`[skip ci] Add funding revive PBO grid support`)
- Added opt-in `pbo_candidates` generation to `aeg_s3_funding_revive`.
- CLI now supports `--include-default-pbo-grid` and `--pbo-grid-json`.
- Default behavior remains no PBO unless a grid is explicitly requested.

## Verification

Mac focused checks:

```text
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_funding_revive.py -q
7 passed

PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_panel_export.py \
  helper_scripts/research/tests/test_aeg_s3_funding_revive.py \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_gate_b_probe.py -q
82 passed
```

Additional checks:

- `python3 -m compileall -q helper_scripts/research/aeg_s3_funding_revive helper_scripts/research/aeg_s3_candidate_rows helper_scripts/research/aeg_candidate_metrics`
- Static forbidden-route scan on `helper_scripts/research/aeg_s3_funding_revive/`: no hits.

## True artifact run

Input panel:

- `/tmp/openclaw/alpha_history_runs/aeg_s3_v125_panel_20260611T200033Z/funding_revive_panel.jsonl`
- OOS split: `2026-03-01`
- Selected cell: `lb21_h24h_stress2_exit1_cost5`
- Grid: 18 cells (`lookback_points` 14/21/28 x `horizon_hours` 24/48 x `stress_z` 1.5/2.0/2.5, `exit_z=1`, `cost_bps=5`)

Evidence:

- Run: `aeg_s3_funding_revive_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_v125_20260611T200033Z_oos20260301_pbo18`
- Samples: 938
- Rejects: `overlap_spacing=59`, `missing_forward_return_or_future_price=1`
- PBO grid status: `produced_candidate_grid`
- Included PBO candidates: 18/18

Direct rows:

- Run: `aeg_s3_funding_revive_direct_rows_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_direct_rows_v125_20260611T200033Z_oos20260301_pbo18`
- Regime rows: 5
- PBO status: `measured`

Candidate metrics:

- Run: `aeg_s3_funding_revive_candidate_metrics_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_candidate_metrics_v125_20260611T200033Z_oos20260301_pbo18`
- Adapter status: 5/5 `PASS`
- Freshness: 5/5 `recent_90_180_measured`

Regime rows:

| Regime | net_bps | n_independent | PSR | DSR | PBO | Adapter status |
|---|---:|---:|---:|---:|---:|---|
| bear | 23.97480762 | 133 | 0.81948714 | 0.0 | 0.54583333 | PASS |
| bull | -13.23188867 | 53 | 0.37083893 | 0.0 | 0.54583333 | PASS |
| chop | 35.85131217 | 142 | 0.96751686 | 0.0 | 0.54583333 | PASS |
| high-vol | -27.58515008 | 37 | 0.36154665 | 0.0 | 0.54583333 | PASS |
| range | 28.47633004 | 116 | 0.87099642 | 0.0 | 0.54583333 | PASS |

## Interpretation

`missing_pbo` is resolved for funding_revive. The candidate-metrics adapter now passes because all matrix-critical fields are present.

This is still not promotion evidence. Under the robustness matrix thresholds already in code (`PSR >= 0.95`, `DSR >= 0.95`, `PBO < 0.5`, positive IS/OOS Sharpe and positive net), funding_revive fails before review:

- All regimes have `DSR=0.0`.
- PBO is `0.54583333`, above the `<0.5` threshold.
- Only `chop` clears PSR, but it still fails DSR and PBO.
- `bull` and `high-vol` have negative net.

Formal robustness matrix was not run with the existing `multiday_trend_reference` smoke breadth artifact, because that would produce a mismatched candidate_id and confuse evidence lineage. A funding-specific breadth/execution-realism path is still required for a formal matrix artifact, but current DSR/PBO values already block funding_revive promotion.

## Next

1. Build and run `oi_delta` candidate-grid PBO on the same true panel.
2. Keep funding_revive as non-promotable unless a new, predeclared parameter family clears DSR and PBO.
3. Continue waiting for operator-timed Gate-B true transition artifact for listing-fade.
4. Require E2/MIT/QC independent review before any AEG-S3 row is treated as promotion proof.
