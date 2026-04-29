# Post-MLDE Follow-Through 1-5

Date: 2026-04-29 19:26 CEST

Deploy update: commit `a3659d7` is pushed and deployed on Linux via `restart_all.sh --rebuild --keep-auth`. Engine PID `691042`; API PID `691117`.

## Result

- `[37] mlde_demo_applier`: fixed the false WARN path by writing a deduped `skipped/no_eligible_recommendations` audit row when the applier runs but has no eligible recommendation.
- `[33] maker_fill_rate`: persisted PostOnly/TIF observability into `trading.orders.time_in_force` and `trading.intents.details`.
- `[12] bb_breakout`: 5m 14d sweep found no statistically credible reason to switch runtime timeframe.
- G8-01 W2/W3: existing 26-case unit suite and 8-scenario integration suite are present and passed targeted pytest.
- Maintenance: `verify_ipc_token` now rejects empty secrets; stale TODO entries for G8 W2/W3 and G3-09 docstring clarify were closed.

## Verification

- MLDE / healthcheck / maker pytest: 26 passed.
- G8 pytest: 42 passed.
- Rust IPC token tests: 5 passed.
- Rust pending-registration order shape tests: 8 passed.
- Rust intent persistence tests: 2 passed.
- Full Rust lib regression: 2365 passed.
- Post-deploy healthcheck: SUMMARY WARN remains `[12]`, `[33]`, `[11]`; `[37]` cleared. `[33]` `postonly_order_rows` is now accumulating.

No live autonomy boundary was loosened.
