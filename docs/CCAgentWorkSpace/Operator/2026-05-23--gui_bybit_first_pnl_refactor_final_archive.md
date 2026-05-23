# GUI Bybit-first Demo PnL Final Archive

Date: 2026-05-23
Operator decision: 1A2A3A
Verdict: PASS / archived

Final verification:

- Focused GUI/Bybit/restart matrix: `60 passed`
- Full connector suite: `4199 passed, 12 skipped, 440 warnings`
- Linux focused GUI/Bybit/restart matrix: `60 passed`
- Linux full connector suite: `4201 passed, 10 skipped, 448 warnings`
- Syntax/static checks: PASS
- E2 re-review: PASS
- BB re-review: PASS
- E4 regression: PASS
- Linux runtime `restart_all.sh --keep-auth`: PASS; startup-status HTTP 200; closed-pnl unauthenticated GET HTTP 401; engine watchdog `engine_alive=true`.

Closed issues:

- Bybit cursor double encoding/signature mismatch fixed.
- PG fallback time window fixed.
- `_get_rust_client() is None` fallback fixed and tested.
- Async route blocking reduced with `asyncio.to_thread`.
- Three-fail Bybit degraded banner path fixed.
- `restart_all.sh` engine/API/socket gate alignment fixed.
- Legacy `test_pnl_series` fixture failure fixed.

The old `4171 passed / 21 failed / 12 skipped` status is obsolete. Current Mac connector status is `4199 passed / 0 failed / 12 skipped`; Linux is `4201 passed / 0 failed / 10 skipped`. Remaining skips are environment/opt-in skips, not GUI Bybit-first PnL failures.

Archive:

- `docs/archive/2026-05-23--gui_bybit_first_pnl_refactor.md`

Accepted 1A2A3A boundaries remain:

- No 24h reconcile cron this sprint.
- No `/demo/wallet-truth` endpoint this sprint.
- Backend keeps 4 `strategy_source`; GUI folds labels.
