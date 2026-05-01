# TODO next batch: [22], G8-05, LG-5

Date: 2026-05-01
Status: Complete for this batch

## Summary

- `[22] trading_pipeline_silent_gap` was recalibrated in `b283fda`.
  - DCS/fill cliff still FAILs when unexplained.
  - Recent `Working` PostOnly maker orders now downgrade to WARN.
  - Rejected-only recent risk/cost gates also downgrade to WARN.
- G8-05 landed in `25d8e54`.
  - Existing AI tab now includes an AI Cost ROI Monitor.
  - The cost card now reads nested Layer2 `/cost` fields.
  - The adaptive ROI display now reads `roi_7d`.
- LG-5 constrained autonomous live RFC landed in `25d8e54`.

## Verification

- `python3 -m py_compile helper_scripts/db/passive_wait_healthcheck/checks_engine.py helper_scripts/db/test_f7_new_healthchecks.py`
- `python3 helper_scripts/db/test_f7_new_healthchecks.py` -> 43/0
- tab-ai inline JS syntax check -> 2 scripts
- `git diff --check`
- Linux F7 tests -> 43/0
- Linux wrapper -> SUMMARY WARN exit 0

## Runtime State

- No rebuild or restart was performed.
- Rust engine runtime remains the `daab51c` scanner deploy.
- Linux wrapper at 2026-05-01 22:29 CEST returned SUMMARY WARN exit 0.
- `[22]` now reports WARN with `working_maker_orders_1h=3`, which matches the maker no-fill interpretation.

## Boundary

No trading, risk/strategy parameter, live authorization, DB write, cron install, SIGHUP, rebuild, restart, HTTPS deploy, or true live action was performed.

Rank 9 HTTPS deploy remains explicit runtime/deploy work and was intentionally skipped.
