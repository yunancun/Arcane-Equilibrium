# 2026-06-12 AEG-S3 event breadth wiring and funding_revive matrix

Scope: artifact-only AEG-S3 event breadth wiring plus Linux true artifact runs. No CI, no deploy, no restart, no DB write, no auth/risk/trading mutation.

## Code checkpoint

- Commit: `8fed7073` (`[skip ci] Add AEG-S3 event breadth adapter`)
- Added `helper_scripts/research/aeg_s3_event_breadth/`.
- The adapter supports single-symbol event candidates:
  - `funding_revive`: `sample.symbol`
  - `listing_fade`: `sample.source_symbol` / `sample.symbol`
- `oi_delta` is explicitly unsupported because its samples are cross-sectional baskets (`top_symbols` / `bottom_symbols`) rather than one event symbol. It fails closed instead of being split into fake symbol breadth.

## Verification

- Mac focused regression: `79 passed`
  - `test_aeg_s3_event_breadth.py`
  - `test_aeg_s3_matrix_inputs.py`
  - `test_aeg_s3_funding_revive.py`
  - `test_aeg_s3_listing_fade.py`
  - `test_aeg_s3_oi_delta.py`
  - `test_aeg_s3_candidate_rows.py`
  - `test_aeg_candidate_metrics.py`
  - `test_aeg_robustness_matrix.py`
  - `test_aeg_breadth_ladder.py`
- `python3 -m compileall -q helper_scripts/research/aeg_s3_event_breadth helper_scripts/research/aeg_breadth_ladder helper_scripts/research/aeg_robustness_matrix helper_scripts/research/aeg_s3_matrix_inputs`
- Static forbidden-route scan on `aeg_s3_event_breadth`: no hits.
- Linux smoke for new tests: `3 passed`.

## Mainline Gate-B status

Linux artifact scan still found no true Gate-B/listing transition artifact. Current files matching Gate-B/listing/transition patterns are only:

- `/tmp/openclaw/alpha_history_runs/aeg_regime_smoke_20260605/regime_transitions.*`
- `/tmp/openclaw/alpha_history_runs/l2_owed_v127_pop_20260610/regime_transitions.*`

So listing-fade mainline remains waiting on the operator-timed 24h PreLaunch capture artifact.

## funding_revive true breadth artifact

Inputs:

- Candidate evidence: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_v125_20260611T200033Z_oos20260301_pbo18/funding_revive_candidate_evidence.json`
- FND-2 universe: `/tmp/openclaw/alpha_history_runs/fnd2_18mo_real_20260603`
- FND-2 delisted proof: `255`, `survivor_rejection_status=PASS`

Run:

- `aeg_s3_funding_revive_event_breadth_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_event_breadth_v125_20260611T200033Z_oos20260301_pbo18`
- Row count: `4`
- Survivorship healthcheck: `PASS`
- `survivorship_inherited_from_fnd2=true`
- Verdict hint: `breadth_real`

Per-tier summary:

| tier | breadth | delisted | net_bps | n_independent | PSR | DSR | PBO | promotion note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| core25_pinned | 25 | 0 | 27.57418929 | 259 | 0.97970529 | 0 | 0.54583333 | eligible tier |
| top_liquidity_40_50 | 64 | 0 | 22.63650726 | 261 | 0.95855395 | 0 | 0.54583333 | excluded: asof-constant liquidity |
| full_survivorship | 829 | 255 | 22.63650726 | 261 | 0.95855395 | 0 | 0.54583333 | eligible tier |
| scanner_active_asof | 31 | 0 | 27.57418929 | 259 | 0.97970529 | 0 | 0.54583333 | excluded: scanner overlap-only |

This resolves the prior placeholder breadth/survivorship gap for funding_revive. It does not resolve DSR/PBO.

## Formal matrix with true event breadth

Run:

- `aeg_s3_funding_revive_robustness_event_breadth_v125_20260611T200033Z_oos20260301_pbo18`
- Artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_robustness_event_breadth_v125_20260611T200033Z_oos20260301_pbo18`
- Row count: `24`
- Coverage gate: `PASS`
- Feature lineage: `PASS`
- Survivorship mode: `pit_fnd2_delisted_proof`
- Execution realism mode: `unverified_missing_missing`
- Final labels: `16 insufficient evidence`, `8 kill`

Common reject reasons are still correct:

- `dsr_k_below_0_95`
- `pbo_at_or_above_0_5`
- `missing_evidence_source_tier` from fail-closed execution realism
- Some regime rows also have `net_bps_non_positive`, `net_to_cost_ratio_below_2`, `is_sharpe_non_positive`, or `psr_0_below_0_95`.

## oi_delta fail-closed check

Real `oi_delta` evidence was intentionally rejected by the event-breadth adapter:

- Command exit: `1`
- Error: `UnsupportedCandidateEvidence: unsupported_candidate_for_event_breadth:oi_delta`

This is the desired behavior. Cross-sectional basket evidence needs a separate breadth design; it must not be converted into fake single-symbol event breadth.

## PM conclusion

The part-2 breadth wiring moved from candidate-metrics placeholder to true FND-2 PIT survivorship evidence for `funding_revive`. The candidate remains non-promotable because DSR is `0`, PBO is above the `<0.5` gate, and execution realism is still unverified.

Next executable work:

1. Mainline: ingest the operator-timed Gate-B/listing transition artifact when it exists, then run listing_fade evidence/direct rows/event breadth/matrix.
2. Parallel infrastructure: design empirical execution-realism evidence for AEG-S3 event candidates; do not promote any matrix until E2/MIT/QC independently review the true breadth + execution inputs.
