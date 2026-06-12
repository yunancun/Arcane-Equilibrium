# 2026-06-12 AEG-S3 Gate-B preflight locator

Scope: artifact-only preflight/locator for the Gate-B listing_fade full-chain path. No CI, no deploy, no rebuild/restart, no DB write, no auth/risk/trading mutation.

## Result

- Code checkpoints:
  - `44a30afa` (`[skip ci] Add Gate-B preflight locator`)
  - `f4a58b3c` (`[skip ci] Tighten Gate-B preflight artifact validation`)
- New package: `helper_scripts/research/aeg_s3_gate_b_preflight/`
- New CLI:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_preflight.harness \
  --run-id <preflight_run_id> \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

The preflight scans local artifacts only:

- Gate-B run root: default `/tmp/openclaw/aeg_gate_b_runs`
- FND2/regime root: default `/tmp/openclaw/alpha_history_runs`
- required Gate-B files: `capture_lag.jsonl`, `markout.jsonl`, `ws_publictrade.jsonl`
- required FND2 files: `universe.csv`, `universe_summary.json`
- required regime files: `regime_labels.csv`, `regime_summary.json`

It then previews listing_fade sample/PBO readiness and emits the recommended full-chain `aeg_s3_gate_b_chain.harness` command.

## Status Semantics

- `PASS_READY_FOR_FULL_CHAIN`: artifacts present, PBO ready, sample count meets the configured threshold.
- `READY_BUT_SAMPLE_BELOW_GATE`: command is runnable, but not promotion-eligible because `sample_count < min_listing_samples`.
- `BLOCKED_PRECHECK_FAILED`: required artifact or semantic validation failed.

## Verification

Mac:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_gate_b_preflight.py \
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
# 58 passed
```

Linux `trade-core`:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_gate_b_preflight.py \
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
# 58 passed
```

Compile/static:

- Mac compileall OK.
- Linux compileall OK.
- Mac forbidden-route scan via `rg`: no hits.
- Linux fallback scan via `grep -R -E`: no hits.

## Linux Artifact Smokes

Explicit artifact smoke:

- run: `aeg_s3_gate_b_preflight_explicit_final_20260612`
- Gate-B: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`
- FND2: `/tmp/openclaw/alpha_history_runs/fnd2_18mo_real_20260603`
- regime: `/tmp/openclaw/alpha_history_runs/aeg_regime_smoke_20260605`
- status: `READY_BUT_SAMPLE_BELOW_GATE`
- sample_count: `2`
- pbo_status: `produced_candidate_grid`
- recommended command: generated

Auto-locator smoke:

- run: `aeg_s3_gate_b_preflight_auto_final_20260612`
- selected Gate-B: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`
- selected FND2: `/tmp/openclaw/alpha_history_runs/fnd2_18mo_real_20260603`
- selected regime: `/tmp/openclaw/alpha_history_runs/l2_owed_v127_pop_20260610`
- status: `READY_BUT_SAMPLE_BELOW_GATE`
- sample_count: `2`
- pbo_status: `produced_candidate_grid`
- recommended command: generated

Interpretation: the preflight is operational. It correctly does not promote the old Gate-B run because only two matched samples are available.

## Next Gate

When Gate-B watcher emits a fresh actionable alert:

1. Run isolated 24h Gate-B probe.
2. Run the preflight:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_preflight.harness \
  --run-id <fresh_preflight_run_id> \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

3. If status is not blocked and `sample_count >= 30`, execute the `recommended_command`.
4. Do not treat preflight readiness or full-chain completion as promotion proof; E2/MIT/QC review remains required.
