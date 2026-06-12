# 2026-06-12 AEG-S3 Gate-B evidence chain wrapper

Scope: artifact-only wrapper for the fresh Gate-B listing_fade evidence chain. No CI, no deploy, no rebuild/restart, no DB write, no auth/risk/trading mutation.

## Result

- Code checkpoint: `75ed19c8` (`[skip ci] Add AEG-S3 Gate-B evidence chain`)
- Added `helper_scripts/research/aeg_s3_gate_b_chain/`.
- The wrapper orchestrates existing artifact-only harnesses:
  - `aeg_s3_listing_fade`
  - `aeg_s3_candidate_rows`
  - `aeg_candidate_metrics`
  - `aeg_s3_execution_observations`
  - `aeg_s3_event_execution_realism`
  - optional `aeg_s3_event_breadth`
  - optional `aeg_robustness_matrix`
- Output chain artifact:
  - `gate_b_chain_summary.json`
  - `manifest.json`
  - `artifact_index.json`

The wrapper does not collect data, call Bybit, write the DB, or touch runtime. It fixes the post-alert command chain and records the child artifact paths plus gate results.

## Usage Shape

Execution-realism chain only:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_chain.harness \
  --run-id <run_id> \
  --gate-b-run-dir <fresh_gate_b_run_dir> \
  --horizon-s 60 \
  --round-trip-cost-bps 5 \
  --k-trials 12 \
  --default-regime chop \
  --allow-slow-capture \
  --order-notional-usdt 1 \
  --slippage-floor-bps 1 \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

Full formal matrix chain:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_chain.harness \
  --run-id <run_id> \
  --gate-b-run-dir <fresh_gate_b_run_dir> \
  --horizon-s 60 \
  --round-trip-cost-bps 5 \
  --k-trials 12 \
  --default-regime chop \
  --allow-slow-capture \
  --order-notional-usdt 1 \
  --slippage-floor-bps 1 \
  --fnd2-run-dir <fnd2_pit_universe_run_dir> \
  --regime-run-dir <aeg_regime_run_dir> \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

`--fnd2-run-dir` and `--regime-run-dir` are deliberately paired. Supplying only one fails fast.

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
# 52 passed
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
# 52 passed
```

Mac/Linux compileall OK. Mac/Linux static forbidden-route search had no hits for `aeg_s3_gate_b_chain`.

## Linux True Artifact Smoke

Input:

- old Gate-B run: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`

Command:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_chain.harness \
  --run-id aeg_s3_gate_b_chain_listing_smoke_20260612 \
  --gate-b-run-dir /tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847 \
  --horizon-s 60 \
  --round-trip-cost-bps 5 \
  --k-trials 12 \
  --default-regime chop \
  --allow-slow-capture \
  --order-notional-usdt 1 \
  --slippage-floor-bps 1 \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

Output:

- artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_chain_listing_smoke_20260612`
- listing_sample_count: `2`
- execution_observation_count: `2`
- chain_status: `COMPLETE_EXECUTION_REALISM_FAIL`
- execution_realism_status: `FAIL`
- reject_reasons: `sample_count_below_30`

Interpretation: the orchestration is wired on real artifact paths. The old run remains non-promotable because it has only two matched samples.

## Next Gate

When Gate-B watcher emits a fresh actionable alert:

1. Run isolated 24h Gate-B probe.
2. Run `aeg_s3_gate_b_chain.harness`.
3. Require `>=30` matched observations before treating execution realism as eligible to pass.
4. If FND2/regime artifacts are provided, inspect the formal matrix output.
5. Do not treat wrapper completion as promotion proof; E2/MIT/QC review remains required.

