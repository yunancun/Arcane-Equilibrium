# AEG-S3 candidate-specific matrix inputs and formal fail-closed matrices

Date: 2026-06-12
Host: Linux `trade-core`
Scope: artifact-only wiring and robustness matrix runs for AEG-S3 true candidate metrics. No CI, no deploy, no restart, no DB write, no exchange call, no runtime mutation.

## Code

- Commit: `25ec85dd` (`[skip ci] Add AEG-S3 matrix input wiring`)
- Added `helper_scripts/research/aeg_s3_matrix_inputs/`.
- Input: an existing `candidate_metrics` artifact run dir.
- Outputs:
  - candidate-specific diagnostic `breadth_ladder` artifact with matching `candidate_id`
  - fail-closed `execution_realism.json`
- Policy: `fail_closed_candidate_metrics_only_no_breadth_claim`

This deliberately does not claim breadth evidence or execution realism. It only fixes lineage so `aeg_robustness_matrix` no longer needs to borrow unrelated `multiday_trend_reference` smoke breadth.

## Verification

Mac focused checks:

```text
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py -q
3 passed

PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_panel_export.py \
  helper_scripts/research/tests/test_aeg_s3_funding_revive.py \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py \
  helper_scripts/research/tests/test_gate_b_probe.py -q
91 passed
```

Additional checks:

- `python3 -m compileall -q helper_scripts/research/aeg_s3_matrix_inputs helper_scripts/research/aeg_robustness_matrix helper_scripts/research/aeg_execution_realism helper_scripts/research/aeg_breadth_ladder`
- Static forbidden-route scan on `helper_scripts/research/aeg_s3_matrix_inputs/`: no hits.

## Regime artifact

Used regime artifact:

- `/tmp/openclaw/alpha_history_runs/l2_owed_v127_pop_20260610`
- `label_count=7696`
- `lineage_status=pass`
- `healthcheck.status=PASS`
- Regime coverage: bear 2839, bull 558, chop 2181, high-vol 486, range 1632

This replaced the older `aeg_regime_smoke_20260605`, whose labels only covered range/chop and was not adequate for the AEG-S3 true candidate metrics.

## funding_revive

Matrix inputs:

- Run: `aeg_s3_funding_revive_matrix_inputs_v125_20260611T200033Z_oos20260301_pbo18`
- Breadth dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_matrix_inputs_v125_20260611T200033Z_oos20260301_pbo18`
- Execution realism: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_matrix_inputs_v125_20260611T200033Z_oos20260301_pbo18_execution_realism/execution_realism.json`
- Breadth policy: `fail_closed_candidate_metrics_only_no_breadth_claim`
- Execution status: `FAIL`
- First execution blocker: `missing_evidence_source_tier`

Robustness matrix:

- Run: `aeg_s3_funding_revive_robustness_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_robustness_v125_20260611T200033Z_oos20260301_pbo18`
- Row count: 6
- Coverage gate: `FAIL`
- Feature lineage: `PASS`
- Survivorship mode: `current_survivor_or_unverified`
- Execution realism mode: `unverified_missing_missing`
- Candidate metrics status: 5 `PASS`
- Final labels: 4 `insufficient evidence`, 2 `kill`
- `non_bull_independent_pass=false`

Key rows:

| Regime | final_label | net_bps | PSR | DSR | PBO | Key blockers |
|---|---|---:|---:|---:|---:|---|
| bear | insufficient evidence | 23.97480762 | 0.81948714 | 0.0 | 0.54583333 | coverage; PSR; DSR; PBO; survivorship; execution |
| bull | kill | -13.23188867 | 0.37083893 | 0.0 | 0.54583333 | net<=0; PSR; DSR; PBO; coverage; survivorship; execution |
| chop | insufficient evidence | 35.85131217 | 0.96751686 | 0.0 | 0.54583333 | DSR; PBO; coverage; survivorship; execution |
| high-vol | kill | -27.58515008 | 0.36154665 | 0.0 | 0.54583333 | net<=0; PSR; DSR; PBO; coverage; survivorship; execution |
| range | insufficient evidence | 28.47633004 | 0.87099642 | 0.0 | 0.54583333 | PSR; DSR; PBO; coverage; survivorship; execution |

## oi_delta

Matrix inputs:

- Run: `aeg_s3_oi_delta_matrix_inputs_v125_20260611T200033Z_oos20260301_pbo18`
- Breadth dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_oi_delta_matrix_inputs_v125_20260611T200033Z_oos20260301_pbo18`
- Execution realism: `/tmp/openclaw/alpha_history_runs/aeg_s3_oi_delta_matrix_inputs_v125_20260611T200033Z_oos20260301_pbo18_execution_realism/execution_realism.json`
- Breadth policy: `fail_closed_candidate_metrics_only_no_breadth_claim`
- Execution status: `FAIL`
- First execution blocker: `missing_evidence_source_tier`

Robustness matrix:

- Run: `aeg_s3_oi_delta_robustness_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_oi_delta_robustness_v125_20260611T200033Z_oos20260301_pbo18`
- Row count: 6
- Coverage gate: `FAIL`
- Feature lineage: `PASS`
- Survivorship mode: `current_survivor_or_unverified`
- Execution realism mode: `unverified_missing_missing`
- Candidate metrics status: 3 `PASS`, 2 `FAIL`
- Final labels: 3 `insufficient evidence`, 2 `kill`, 1 `stale-data artifact`
- `non_bull_independent_pass=false`

Key rows:

| Regime | final_label | net_bps | PSR | DSR | PBO | Key blockers |
|---|---|---:|---:|---:|---:|---|
| bear | kill | -21.01386229 | 0.10119047 | 0.0 | 0.9125 | net<=0; PSR; DSR; PBO; coverage; survivorship; execution |
| bull | stale-data artifact | 36.09161073 | 0.76302072 | 0.0 | 0.9125 | candidate metric FAIL; n<30; freshness; PSR; DSR; PBO; coverage; survivorship; execution |
| chop | insufficient evidence | 6.07737439 | 0.61319253 | 0.0 | 0.9125 | PSR; DSR; PBO; coverage; survivorship; execution |
| high-vol | kill | -5.43022579 | 0.45413853 | 0.0 | 0.9125 | candidate metric FAIL; net<=0; n<30; freshness; PSR; DSR; PBO; coverage; survivorship; execution |
| range | insufficient evidence | 35.97216074 | 0.94116581 | 0.0 | 0.9125 | PSR; DSR; PBO; coverage; survivorship; execution |

## Interpretation

This closes the wiring gap: AEG-S3 true candidate metrics can now flow into `aeg_robustness_matrix` with candidate-specific lineage and full V127 regime slices, without borrowing smoke breadth.

It does not close breadth or execution realism. Both are intentionally fail-closed:

- Breadth is `candidate_metrics_only`, not FND-2 tier evaluation.
- Execution realism is unverified and fails on missing empirical source/order/cost/capacity fields.
- Survivorship remains `current_survivor_or_unverified` until candidate-specific breadth is truly evaluated against FND-2 alive_from/alive_to.

Even if breadth/execution were later measured, the current funding_revive and oi_delta grids are still blocked by DSR/PBO/PSR quality. Neither candidate is promotion evidence.

## Next

1. Wait for or ingest operator-timed Gate-B true transition artifact for listing-fade.
2. If continuing infrastructure before Gate-B arrives, implement real candidate-specific breadth evaluation against FND-2 PIT tiers for AEG-S3 event candidates.
3. Execution realism must be measured from empirical fills/capacity evidence before any matrix PASS can be trusted.
4. E2/MIT/QC independent review remains mandatory before any AEG-S3 matrix output is treated as promotion proof.
