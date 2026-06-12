# 2026-06-12 AEG-S3 Gate-B full-matrix PBO readiness

Scope: regression guard and Linux artifact-only dry-run for the full Gate-B listing_fade chain with PBO, event breadth, and formal robustness matrix. No CI, no deploy, no rebuild/restart, no DB write, no auth/risk/trading mutation.

## Result

- Test checkpoint: `235858f4` (`[skip ci] Guard Gate-B matrix PBO path`)
- The full formal matrix regression in `test_aeg_s3_gate_b_chain.py` now supplies a PBO grid and asserts:
  - `listing_pbo_status == produced_candidate_grid`
  - candidate rows summary `pbo_status == measured`

This prevents a future drift where the execution-only Gate-B path carries listing PBO while the full matrix path silently loses it.

## Verification

Mac:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_gate_b_chain.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_s3_event_breadth.py \
  helper_scripts/research/tests/test_aeg_s3_execution_observations.py \
  helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py -q
# 54 passed
```

Linux `trade-core` after pulling `235858f4`:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_gate_b_chain.py \
  helper_scripts/research/tests/test_aeg_s3_execution_observations.py \
  helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_s3_event_breadth.py \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py -q
# 54 passed
```

## Linux Full Formal Smoke

Inputs:

- old Gate-B run: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`
- true FND2 run: `/tmp/openclaw/alpha_history_runs/fnd2_18mo_real_20260603`
- regime run: `/tmp/openclaw/alpha_history_runs/aeg_regime_smoke_20260605`

Command:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_chain.harness \
  --run-id aeg_s3_gate_b_chain_listing_pbo_formal_smoke_final_20260612 \
  --gate-b-run-dir /tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847 \
  --horizon-s 60 \
  --round-trip-cost-bps 5 \
  --k-trials 12 \
  --default-regime chop \
  --allow-slow-capture \
  --order-notional-usdt 1 \
  --slippage-floor-bps 1 \
  --include-default-pbo-grid \
  --fnd2-run-dir /tmp/openclaw/alpha_history_runs/fnd2_18mo_real_20260603 \
  --regime-run-dir /tmp/openclaw/alpha_history_runs/aeg_regime_smoke_20260605 \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

Output:

- chain artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_chain_listing_pbo_formal_smoke_final_20260612`
- formal matrix artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_chain_listing_pbo_formal_smoke_final_20260612_formal_matrix`
- `listing_sample_count=2`
- `execution_observation_count=2`
- `listing_pbo_status=produced_candidate_grid`
- formal matrix `row_count=12`
- coverage gate `PASS`
- survivorship mode `pit_fnd2_delisted_proof`
- final labels: `7 insufficient evidence`, `5 kill`
- `chain_status=COMPLETE_MATRIX_NON_PROMOTABLE`
- reject reason: `sample_count_below_30`

Interpretation: the full execution + event breadth + formal matrix + PBO chain is operational on real artifact paths. The old run remains non-promotable because it has only two matched observations.

## Next Gate

When Gate-B watcher emits a fresh actionable alert:

1. Run isolated 24h Gate-B probe.
2. Run `aeg_s3_gate_b_chain.harness --include-default-pbo-grid --fnd2-run-dir <FND2> --regime-run-dir <REGIME>`.
3. Require `>=30` matched observations before treating execution realism as eligible to pass.
4. Inspect formal matrix labels and PBO status.
5. Do not treat full-chain completion as promotion proof; E2/MIT/QC review remains required.
