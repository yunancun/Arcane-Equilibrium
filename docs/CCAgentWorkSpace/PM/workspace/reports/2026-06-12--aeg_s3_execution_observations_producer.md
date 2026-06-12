# 2026-06-12 AEG-S3 execution observations producer

Scope: artifact-only producer for converting matched Gate-B listing capture evidence into the `execution_observations.jsonl` format consumed by `aeg_s3_event_execution_realism`. No CI, no deploy, no rebuild/restart, no DB write, no auth/risk/trading mutation.

## Result

- Code checkpoint: `9eaad929` (`[skip ci] Add AEG-S3 execution observations producer`)
- Added `helper_scripts/research/aeg_s3_execution_observations/`.
- The first source supports `listing_fade` candidate evidence plus an isolated Gate-B run directory:
  - `capture_lag.jsonl`
  - `markout.jsonl`
  - `ws_publictrade.jsonl`
- Output artifacts:
  - `execution_observations.jsonl`
  - `execution_observations_summary.json`
  - `manifest.json`
  - `artifact_index.json`
- Observations are matched to candidate `sample_id` / symbol / timestamp before aggregation. Unmatched rows are rejected and counted.

This closes the missing producer between Gate-B capture and event execution realism. The adapter is intentionally narrow: it supports `listing_fade` through Gate-B public trade prints only. It does not convert `funding_revive` historical samples or `oi_delta` baskets into single-symbol Gate-B observations.

## Files

- `helper_scripts/research/aeg_s3_execution_observations/__init__.py`
- `helper_scripts/research/aeg_s3_execution_observations/builder.py`
- `helper_scripts/research/aeg_s3_execution_observations/artifact.py`
- `helper_scripts/research/aeg_s3_execution_observations/harness.py`
- `helper_scripts/research/tests/test_aeg_s3_execution_observations.py`
- `helper_scripts/SCRIPT_INDEX.md`

## Verification

Mac:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_execution_observations.py \
  helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py -q
# 31 passed

python3 -m compileall -q helper_scripts/research/aeg_s3_execution_observations \
  helper_scripts/research/aeg_s3_event_execution_realism \
  helper_scripts/research/aeg_execution_realism \
  helper_scripts/research/aeg_s3_matrix_inputs

rg -n "control_api_v1|psycopg2|asyncpg|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" \
  helper_scripts/research/aeg_s3_execution_observations
# no hits
```

Linux `trade-core`:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_execution_observations.py \
  helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py -q
# 31 passed
```

Linux compileall and static forbidden-route search also passed.

## Linux True Artifact Smoke

Input Gate-B run:

- `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`

Step 1 generated listing fade candidate evidence:

- artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_listing_fade_gate_b_obs_smoke_20260612`
- sample_count: `2`
- rejected_sample_count: `0`

Step 2 generated execution observations at 10 USDT notional:

- artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_listing_fade_execution_obs_smoke_20260612`
- observation_count: `2`
- rejected_observation_count: `0`
- source tier: `calibrated_replay`
- order style: `taker`

Step 3 ran event execution realism:

- artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_listing_fade_execution_realism_smoke_20260612`
- status: `FAIL`
- execution_realism_mode: `unverified_calibrated_replay_taker`
- matched_observation_count: `2`
- reject_reasons: `sample_count_below_30`, `participation_rate_p95_above_0_05`
- cost_bps_round_trip_p95: `13.0`

A second 1 USDT run isolated the capacity issue:

- observations: `/tmp/openclaw/alpha_history_runs/aeg_s3_listing_fade_execution_obs_smoke_1usdt_20260612`
- execution realism: `/tmp/openclaw/alpha_history_runs/aeg_s3_listing_fade_execution_realism_smoke_1usdt_20260612`
- status: `FAIL`
- matched_observation_count: `2`
- reject_reasons: `sample_count_below_30`
- cost_bps_round_trip_p95: `13.0`

## Current Gate State

The producer and aggregator are wired. The old Gate-B smoke run is not promotion evidence because it only has two matched samples. The 10 USDT run also shows thin local capacity in that old window; reducing to 1 USDT removes the participation rejection but not the sample-count rejection.

Gate-B should not block unrelated development. It should gate only the final event evidence step:

- wait for `[GATE-B-WATCH]` fresh Pre-Market / PreLaunch / conversion alert or `ACTIONABLE_*` latest artifact
- run isolated 24h Gate-B probe
- produce `listing_fade` candidate evidence
- produce `execution_observations.jsonl`
- require `>=30` matched observations
- run `aeg_s3_event_execution_realism`
- pass the resulting `execution_realism.json` into formal matrix with `--execution-realism-json`

Boundary: Gate-B v0.1 uses publicTrade prints and does not claim historical orderbook-depth fill realism.
