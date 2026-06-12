# 2026-06-12 AEG-S3 listing_fade PBO grid wiring

Scope: artifact-only AEG-S3 listing_fade candidate-grid PBO wiring plus Gate-B chain pass-through. No CI, no deploy, no rebuild/restart, no DB write, no auth/risk/trading mutation.

## Result

- Code checkpoint: `3d03698c` (`[skip ci] Add listing fade PBO grid wiring`)
- `aeg_s3_listing_fade.harness` now accepts:
  - `--include-default-pbo-grid`
  - `--pbo-grid-json`
- `aeg_s3_gate_b_chain.harness` passes those PBO knobs into the listing evidence stage.
- Gate-B chain summary and CLI output now expose `listing_pbo_status`.

The default remains conservative: listing_fade does not produce PBO unless the caller explicitly requests a grid. If a requested grid has fewer than 10 included candidate cells, the status is `insufficient_candidate_grid`, not a synthetic pass.

## Why This Was Next

Gate-B should not block all development while waiting for a fresh listing window. Before this patch, a future fresh Gate-B run could produce enough observations but still hit a known matrix gap: listing_fade had no candidate-grid PBO output. This patch removes that known wiring gap without fabricating evidence from old samples.

## Verification

Mac:

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

Linux `trade-core`:

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

Compile/static:

- Mac compileall OK.
- Linux compileall OK.
- Mac forbidden-route scan via `rg`: no hits.
- Linux `rg` was unavailable, so fallback `grep -R -E` was used: no hits.

## Linux True Artifact Smoke

Input:

- old Gate-B run: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`

Command:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_chain.harness \
  --run-id aeg_s3_gate_b_chain_listing_pbo_smoke_20260612 \
  --gate-b-run-dir /tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847 \
  --horizon-s 60 \
  --round-trip-cost-bps 5 \
  --k-trials 12 \
  --default-regime chop \
  --allow-slow-capture \
  --order-notional-usdt 1 \
  --slippage-floor-bps 1 \
  --include-default-pbo-grid \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

Output:

- artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_chain_listing_pbo_smoke_20260612`
- listing_sample_count: `2`
- execution_observation_count: `2`
- listing_pbo_status: `produced_candidate_grid`
- chain_status: `COMPLETE_EXECUTION_REALISM_FAIL`
- execution_realism_status: `FAIL`
- reject_reasons: `sample_count_below_30`

Interpretation: PBO pass-through is wired on real artifact paths. The old run remains non-promotable because it has only two matched samples.

## Next Gate

When Gate-B watcher emits a fresh actionable alert:

1. Run isolated 24h Gate-B probe.
2. Run `aeg_s3_gate_b_chain.harness --include-default-pbo-grid`.
3. Require `>=30` matched observations before execution realism is eligible to pass.
4. Inspect `listing_pbo_status`; it should be `produced_candidate_grid` if enough horizon/cost cells are present.
5. Do not treat wrapper or PBO completion as promotion proof; E2/MIT/QC review remains required.
