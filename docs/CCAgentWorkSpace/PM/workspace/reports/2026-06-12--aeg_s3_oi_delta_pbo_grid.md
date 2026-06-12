# AEG-S3 oi_delta PBO grid run

Date: 2026-06-12
Host: Linux `trade-core`
Scope: artifact-only oi_delta PBO grid generation from the existing V125/V127 true panel. No CI, no deploy, no restart, no DB write, no exchange call, no runtime mutation.

## Code

- Commit: `5a0f9ab3` (`[skip ci] Add OI delta PBO grid support`)
- Added opt-in `pbo_candidates` generation to `aeg_s3_oi_delta`.
- CLI now supports `--include-default-pbo-grid` and `--pbo-grid-json`.
- Default behavior remains no PBO unless a grid is explicitly requested.

## Verification

Mac focused checks:

```text
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_oi_delta.py -q
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
83 passed
```

Additional checks:

- `python3 -m compileall -q helper_scripts/research/aeg_s3_oi_delta helper_scripts/research/aeg_s3_candidate_rows helper_scripts/research/aeg_candidate_metrics`
- Static forbidden-route scan on `helper_scripts/research/aeg_s3_oi_delta/`: no hits.

## True artifact run

Input panel:

- `/tmp/openclaw/alpha_history_runs/aeg_s3_v125_panel_20260611T200033Z/oi_delta_panel.jsonl`
- OOS split: `2026-03-01`
- Selected cell: `lb24h_h24h_tail0.2_cost5_long_high_short_low`
- Grid: 18 cells (`lookback_hours` 24/48/72 x `horizon_hours` 24/48/72 x `tail_frac` 0.15/0.2, `cost_bps=5`, `side_mode=long_high_short_low`)

Evidence:

- Run: `aeg_s3_oi_delta_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_oi_delta_v125_20260611T200033Z_oos20260301_pbo18`
- Samples: 294
- Mean accepted net: `2.42005018 bps`
- Daily returns: 294
- Rejects: `missing_oi_delta_or_prior_oi=20`, `missing_forward_return_or_future_price=20`
- PBO grid status: `produced_candidate_grid`
- Included PBO candidates: 18/18
- Regime counts: bear 117, bull 16, chop 89, high-vol 13, range 59

Direct rows:

- Run: `aeg_s3_oi_delta_direct_rows_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_oi_delta_direct_rows_v125_20260611T200033Z_oos20260301_pbo18`
- Regime rows: 5
- PBO status: `measured`

Candidate metrics:

- Run: `aeg_s3_oi_delta_candidate_metrics_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_oi_delta_candidate_metrics_v125_20260611T200033Z_oos20260301_pbo18`
- Adapter status: 3 `PASS`, 2 `FAIL`
- Freshness: 3 `recent_90_180_measured`, 2 `unmeasured`

Regime rows:

| Regime | net_bps | n_independent | PSR | DSR | PBO | Adapter status | Reject reasons |
|---|---:|---:|---:|---:|---:|---|---|
| bear | -21.01386229 | 117 | 0.10119047 | 0.0 | 0.9125 | PASS | [] |
| bull | 36.09161073 | 16 | 0.76302072 | 0.0 | 0.9125 | FAIL | n_days_below_30; missing_oos_sharpe; n_independent_below_30; missing_recent_90d_net_bps; missing_recent_180d_net_bps |
| chop | 6.07737439 | 89 | 0.61319253 | 0.0 | 0.9125 | PASS | [] |
| high-vol | -5.43022579 | 13 | 0.45413853 | 0.0 | 0.9125 | FAIL | n_days_below_30; missing_oos_sharpe; n_independent_below_30; missing_recent_90d_net_bps; missing_recent_180d_net_bps |
| range | 35.97216074 | 59 | 0.94116581 | 0.0 | 0.9125 | PASS | [] |

## Interpretation

`missing_pbo` is resolved for oi_delta. The candidate-metrics adapter now has measured PBO, so the previous missing-PBO blocker is closed.

This is still not promotion evidence. Under the robustness matrix thresholds already in code (`PSR >= 0.95`, `DSR >= 0.95`, `PBO < 0.5`, positive IS/OOS Sharpe and positive net), oi_delta fails clearly:

- PBO is `0.9125`, far above the `<0.5` threshold.
- All regimes have `DSR=0.0`.
- No regime clears both PSR and net with adequate freshness/sample support.
- `bear` and `high-vol` have negative net.
- `bull` and `high-vol` also fail sample/freshness/OOS completeness at adapter level.

Formal robustness matrix was not run with the existing `multiday_trend_reference` smoke breadth artifact, because that would produce a mismatched candidate_id and confuse evidence lineage. A candidate-specific breadth/execution-realism path is still required for a formal matrix artifact, but current PBO/DSR/PSR values already block oi_delta promotion.

## Next

1. Keep `oi_delta` as non-promotable under the current predeclared grid.
2. Continue waiting for operator-timed Gate-B true transition artifact for listing-fade.
3. If we continue AEG-S3 before Gate-B arrives, the next engineering item is candidate-specific breadth/execution-realism wiring for formal matrix artifacts, not another PSR-only sweep.
4. Require E2/MIT/QC independent review before any AEG-S3 row is treated as promotion proof.
