# AEG-S3 true V125/V127 panel first candidate rows

Date: 2026-06-11
Host: Linux `trade-core`
Scope: read-only artifact generation from accepted V125/V127 storage. No deploy, no restart, no DB write, no exchange call, no runtime mutation.

## Source

- V125 accepted alpha history run: `18b3c2f8-6125-42a8-a42c-cfcc8aec9406`
- Export run: `aeg_s3_v125_panel_20260611T200033Z`
- Export artifact dir: `/tmp/openclaw/alpha_history_runs/aeg_s3_v125_panel_20260611T200033Z`
- OOS split used for producer re-runs: `2026-03-01` (mechanical recent holdout for first bite)

## Export result

`aeg_s3_panel_export` emitted:

- `oi_delta_panel.jsonl`: 5,920 rows, 20 symbols, date span `2025-08-10` to `2026-06-01`
- `funding_revive_panel.jsonl`: 19,536 rows, 20 symbols, date span `2025-08-10` to `2026-06-01`
- Rejected rows: 35,609 total
  - OI: `missing_regime=8566`, `missing_price=40`
  - Funding: `missing_regime=26937`, `missing_price=66`

Interpretation: V127 regime label coverage starts at 2025-08-10, so earlier V125 funding/OI history correctly fails closed instead of receiving synthetic regimes.

Implementation note: the first OI run exposed a real exporter policy bug. Per-symbol regimes created mixed-regime cross-sectional windows, causing downstream `missing_regime`. Fixed in commit `5c37ba48`: OI panel now uses date-level regime; funding_revive keeps symbol-date regime.

## Producer result

`oi_delta`:

- Evidence run: `aeg_s3_oi_delta_v125_20260611T200033Z_oos20260301`
- Samples: 294
- Mean accepted net: `2.42005018 bps`
- Daily returns: 294
- Rejects: `missing_oi_delta_or_prior_oi=20`, `missing_forward_return_or_future_price=20`
- Regime counts: bear 117, chop 89, range 59, bull 16, high-vol 13

`funding_revive`:

- Evidence run: `aeg_s3_funding_revive_v125_20260611T200033Z_oos20260301`
- Samples: 938
- Mean accepted net: `22.636507258416 bps`
- Daily returns: 261
- Rejects: `overlap_spacing=59`, `missing_forward_return_or_future_price=1`
- Regime counts: bear 309, chop 278, range 219, bull 88, high-vol 44

## Candidate metrics result

`oi_delta` candidate metrics run: `aeg_s3_oi_delta_candidate_metrics_v125_20260611T200033Z_oos20260301`

- Rows: 5, all `FAIL`
- Key rows:
  - bear: net `-21.01386229`, n_independent 117, PSR `0.10119047`, reject `missing_pbo`
  - chop: net `6.07737439`, n_independent 89, PSR `0.61319253`, reject `missing_pbo`
  - range: net `35.97216074`, n_independent 59, PSR `0.94116581`, reject `missing_pbo`
  - bull/high-vol: additionally fail n<30 and missing OOS/freshness due low sample count

`funding_revive` candidate metrics run: `aeg_s3_funding_revive_candidate_metrics_v125_20260611T200033Z_oos20260301`

- Rows: 5, all `FAIL`
- Key rows:
  - bear: net `23.97480762`, n_independent 133, PSR `0.81948714`, reject `missing_pbo`
  - chop: net `35.85131217`, n_independent 142, PSR `0.96751686`, reject `missing_pbo`
  - range: net `28.47633004`, n_independent 116, PSR `0.87099642`, reject `missing_pbo`
  - bull: net `-13.23188867`, n_independent 53, reject `missing_pbo`
  - high-vol: net `-27.58515008`, n_independent 37, reject `missing_pbo`

All rows remain non-promotable. PBO is absent by design until candidate-grid evidence exists. DSR is still `0.0` in the rows inspected, so robustness matrix review must not read positive PSR-only cells as durable edge.

## Next

Next executable item: produce candidate-grid PBO evidence for `oi_delta` and `funding_revive`, then rerun candidate metrics and robustness matrix. `funding_revive` chop is the highest-priority first grid because it has n_independent 142, PSR 0.9675, and positive net, but it is still blocked by missing PBO and DSR quality.
