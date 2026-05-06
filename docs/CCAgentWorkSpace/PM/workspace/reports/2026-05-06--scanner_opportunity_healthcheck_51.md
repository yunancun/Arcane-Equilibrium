# Scanner Opportunity Healthcheck [51]

**Date**: 2026-05-06  
**Commit**: `90db1e1c`  
**Scope**: add passive healthcheck `[51] scanner_opportunity_shadow_acceptance` for Scanner Opportunity v1.

## What Changed

`[51]` is a shadow-only acceptance monitor. It does not add a new trading gate, does not mutate risk/strategy parameters, and does not touch the Rust execution path.

It verifies three neutral row-proof contracts:

1. `trading.scanner_snapshots.candidates[*].strategy_judgments.*.opportunity` exists on recent scanner routes.
2. `trading.intents.details.scanner.opportunity` is preserved on scanner-origin intents.
3. `learning.mlde_edge_training_rows.metadata.scanner.opportunity.opportunity_lcb_bps` can be compared with realized `net_bps_after_fee`.

Verdict behavior:

- Snapshot opportunity coverage `<95%` over 3h => `FAIL`.
- Intent opportunity coverage `<95%` over 3h, only when scanner intent sample `>=3` => `FAIL`.
- Labeled outcomes `<10` over 24h => `WARN`, not false `FAIL`.
- Positive LCB bucket with enough sample (`>=10`) and negative realized net => `FAIL`.

## Files

| File | Change |
|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_scanner_market.py` | Adds `[51]` SQL and verdict logic beside `[41]`. |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | Wires `[51]` into the cursor healthcheck block after `[50]`. |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | Re-exports the new check. |
| `helper_scripts/db/test_scanner_opportunity_healthcheck.py` | Adds 7 mock tests for coverage, warmup, calibration, and read-only SQL shape. |

## Verification

Mac:

- `python3 -m pytest helper_scripts/db/test_scanner_opportunity_healthcheck.py -q` -> `7 passed`
- `python3 -m pytest helper_scripts/db/test_scanner_opportunity_healthcheck.py helper_scripts/db/test_pricing_binding_healthcheck.py -q` -> `17 passed`
- `python3 -m compileall -q helper_scripts/db/passive_wait_healthcheck helper_scripts/db/test_scanner_opportunity_healthcheck.py`
- `python3 -m helper_scripts.db.passive_wait_healthcheck --help | grep -E '\[51\]|scanner_opportunity'`
- `git diff --check`

Linux `trade-core`:

- `git -C ~/BybitOpenClaw/srv pull --ff-only` -> fast-forward to `90db1e1c`
- `python3 -m pytest ~/BybitOpenClaw/srv/helper_scripts/db/test_scanner_opportunity_healthcheck.py -q` -> `7 passed`
- `bash ~/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck.sh --quiet` -> `SUMMARY: FAIL` from pre-existing `[42]`, `[42c]`, `[50]`; new `[51]` returned `WARN`.

`[51]` runtime result at `2026-05-06T17:43:30Z`:

```text
WARN [51] scanner_opportunity_shadow_acceptance 3h snapshot routes=340/340 (100.0%), scans=6; 3h scanner intents=4/4 (100.0%); 24h labels=7, positive_lcb_n=2, avg_net=-31.81bps, positive_avg=27.93bps, nonpositive_avg=-55.70bps, corr=0.22 — insufficient labeled outcomes for calibration (min=10)
```

## Adversarial Review

- No SQL mutation path exists in `[51]`; tests assert no `INSERT`, `UPDATE`, or `DELETE` in the generated SQL.
- Low sample is deliberately `WARN`, so the new monitor cannot create false production failure while the shadow signal is warming up.
- Coverage failures are `FAIL`, because missing opportunity fields break learning before there is enough data to judge edge.
- The current runtime shows row proof is complete (`100%` snapshot and intent coverage), but calibration is not yet acceptance-grade (`7` labels, min `10`).
- This is not edge止血 yet. It is the durable measurement layer needed before any future enforcement can be justified.

## Remaining Gaps

- `[40]` realized edge remains negative (`24h avg_net=-27.93bps` in the same healthcheck run).
- `[42]`, `[42c]`, and `[50]` remain real runtime FAILs and are unrelated to `[51]`.
- Scanner opportunity should remain shadow-only until labeled sample crosses threshold and positive-LCB realized net stays non-negative with enough sample.
