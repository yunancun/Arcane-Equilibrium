# 2026-06-12 AEG-S3 sidecar matrix wiring

Scope: artifact-only AEG-S3 formal matrix input wiring. No CI, no deploy, no rebuild/restart, no DB write, no auth/risk/trading mutation.

## Result

- Code checkpoint: `66a9e511` (`[skip ci] Wire AEG-S3 sidecar matrix inputs`)
- `aeg_s3_matrix_inputs` now accepts provided sidecar artifacts:
  - `--breadth-run-dir` for existing `breadth_ladder.csv` / `breadth_ladder_summary.json`
  - `--execution-realism-json` for existing canonical `execution_realism.json`
- Missing sidecars preserve the original fail-closed behavior:
  - generated candidate-specific placeholder breadth
  - unverified execution realism
- Provided sidecars are validated before use:
  - breadth `candidate_id` must match candidate metrics
  - execution `candidate_id` / `strategy_family` / `parameter_cell_id` must match candidate metrics
  - execution must carry `status` and `execution_realism_mode`

This closes the guest/sidecar wiring gap: event breadth and empirical execution artifacts can be selected by the formal matrix input layer instead of being rebuilt or ignored.

## Files

- `helper_scripts/research/aeg_s3_matrix_inputs/builder.py`
- `helper_scripts/research/aeg_s3_matrix_inputs/harness.py`
- `helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py`
- `helper_scripts/SCRIPT_INDEX.md`
- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`

## Verification

Mac:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_s3_event_breadth.py \
  helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py -q
# 24 passed

python3 -m compileall -q helper_scripts/research/aeg_s3_matrix_inputs \
  helper_scripts/research/aeg_execution_realism \
  helper_scripts/research/aeg_breadth_ladder \
  helper_scripts/research/aeg_robustness_matrix

rg -n "control_api_v1|psycopg2|asyncpg|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" \
  helper_scripts/research/aeg_s3_matrix_inputs
# no hits
```

Linux `trade-core`:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_s3_event_breadth.py \
  helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py -q
# 24 passed
```

Linux sidecar smoke:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_matrix_inputs.harness \
  --run-id aeg_s3_funding_revive_sidecar_inputs_v125_20260611T200033Z_oos20260301_pbo18 \
  --candidate-metrics-run-dir /tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_candidate_metrics_v125_20260611T200033Z_oos20260301_pbo18 \
  --breadth-run-dir /tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_event_breadth_v125_20260611T200033Z_oos20260301_pbo18 \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

Output highlights:

- `breadth_input_mode=provided_breadth_artifact`
- `breadth_policy=single_symbol_event_samples_filtered_by_fnd2_alive_mask`
- `execution_input_mode=unverified_placeholder`
- `execution_realism_mode=unverified_missing_missing`

Formal matrix smoke:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_robustness_matrix.harness \
  --run-id aeg_s3_funding_revive_robustness_sidecar_inputs_v125_20260611T200033Z_oos20260301_pbo18 \
  --regime-run-dir /tmp/openclaw/alpha_history_runs/l2_owed_v127_pop_20260610 \
  --breadth-run-dir /tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_event_breadth_v125_20260611T200033Z_oos20260301_pbo18 \
  --candidate-metrics-run-dir /tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_candidate_metrics_v125_20260611T200033Z_oos20260301_pbo18 \
  --execution-realism-json /tmp/openclaw/alpha_history_runs/aeg_s3_funding_revive_sidecar_inputs_v125_20260611T200033Z_oos20260301_pbo18_execution_realism/execution_realism.json \
  --strategy-family funding_revive \
  --parameter-cell-id lb21_h24h_stress2_exit1_cost5 \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

Output:

- row_count: `24`
- coverage gate: `PASS`
- feature lineage: `PASS`
- survivorship mode: `pit_fnd2_delisted_proof`
- execution realism mode: `unverified_missing_missing`
- final labels: `16 insufficient evidence`, `8 kill`

## Current Gate State

Funding revive is still non-promotable:

- DSR remains `0.0`
- PBO remains `0.54583333`
- execution realism still lacks `>=30` matched empirical observations

Gate-B is not blocked by passive waiting anymore. The dedicated watcher remains the trigger source. Next action is either:

- `[GATE-B-WATCH]` fresh Pre-Market / PreLaunch / conversion alert -> start isolated 24h probe
- collect `>=30` matched empirical execution observations -> run `aeg_s3_event_execution_realism` and rerun formal matrix with `--execution-realism-json`

