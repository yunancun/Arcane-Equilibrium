# AEG-S3 funding_revive evidence producer implementation

Date: 2026-06-11
Owner: PM/Codex
Scope: artifact-only research helper; no runtime, DB, exchange, IPC, auth, or trading-path mutation.

## What changed

- Added `helper_scripts/research/aeg_s3_funding_revive/`.
- Produces `funding_revive_candidate_evidence.json` consumable by `aeg_s3_candidate_rows`.
- Implements single-symbol funding stress unwind windows:
  - negative funding stress exits toward neutral => long event;
  - positive funding stress exits toward neutral => short event.
- Keeps funding accounting explicit:
  - `gross_bps = sided_price_return_bps + funding_pnl_bps`;
  - `net_bps = gross_bps - round_trip_cost_bps`;
  - missing holding-window funding PnL rejects the event instead of assuming zero.
- Uses conservative independence buckets: `<sample_date>:funding_revive`.
- Emits daily returns as the mean accepted event net per date.
- Does not produce PBO; downstream direct rows/candidate metrics fail closed with `missing_pbo` until a true candidate grid exists.

## Contract boundaries

- This does not reopen the closed `funding_tilt` / cross-sectional carry thesis.
- Input is offline JSONL only.
- Regime is required from row, date map, or explicit default.
- No live data access or persistence route exists in the package.

## Validation

Focused TDD test:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_funding_revive.py -q
```

Result: `6 passed`.

AEG-S3 focused regression:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_funding_revive.py \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_gate_b_probe.py -q
```

Result: `76 passed`.

Compile/static:

```bash
python3 -m compileall -q helper_scripts/research/aeg_s3_funding_revive helper_scripts/research/aeg_s3_oi_delta helper_scripts/research/aeg_s3_listing_fade helper_scripts/research/aeg_s3_candidate_rows
rg -n "control_api_v1|psycopg2|asyncpg|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" helper_scripts/research/aeg_s3_funding_revive
```

Result: compileall passed; forbidden-route scan returned no package hits.

## Next

Run the broader AEG-S3 focused regression and then use real exported funding/price/regime panel data to generate true candidate rows. Promotion remains blocked on real artifacts, PBO grid evidence, and independent review.
