# AEG-S3 panel exporter implementation

Date: 2026-06-11
Owner: PM/Codex
Scope: artifact/export helper only; no runtime, exchange, IPC, auth, trading path, or database write mutation.

## What changed

- Added `helper_scripts/research/aeg_s3_panel_export/`.
- Added a pure builder that converts offline price/OI/funding/regime rows into:
  - `oi_delta_panel.jsonl` for `aeg_s3_oi_delta`;
  - `funding_revive_panel.jsonl` for `aeg_s3_funding_revive`.
- Added a Linux PG read-only loader for:
  - `research.alpha_open_interest_history`;
  - `research.alpha_funding_rates_history`;
  - `market.klines`;
  - `research.aeg_regime_labels`.
- Added a CLI harness that writes both panels and `panel_export_summary.json`.

## Policy

- OI rows are daily-resampled: latest OI per symbol/date plus daily close.
- Funding rows keep every explicit funding settlement row.
- Regime join prefers symbol-date labels, then date-majority fallback.
- Missing price or regime rejects rows; no synthetic default is invented.
- This exporter does not run candidate promotion, candidate metrics, or robustness matrix by itself.

## Validation

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_panel_export.py -q
```

Result: `5 passed`.

AEG-S3 focused regression:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_panel_export.py \
  helper_scripts/research/tests/test_aeg_s3_funding_revive.py \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_gate_b_probe.py -q
```

Result: `81 passed`.

Compile/help/static:

```bash
python3 -m compileall -q helper_scripts/research/aeg_s3_panel_export helper_scripts/research/aeg_s3_funding_revive helper_scripts/research/aeg_s3_oi_delta helper_scripts/research/aeg_s3_listing_fade helper_scripts/research/aeg_s3_candidate_rows
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_panel_export.harness --help
rg -n "control_api_v1|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" helper_scripts/research/aeg_s3_panel_export
```

Result: compileall passed; CLI help rendered; forbidden-route scan returned no package hits.

## Next

After sync to Linux, run the exporter against the accepted V125 run and feed the emitted JSONL files into `aeg_s3_oi_delta` and `aeg_s3_funding_revive`. Promotion remains blocked on PBO candidate grids and independent review.
