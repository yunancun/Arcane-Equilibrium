# GUI Bybit-first Demo PnL Final Archive

Date: 2026-05-23
Role: PM final verification / archive
Operator decision: 1A2A3A

## Verdict

PASS. The GUI Bybit-first Demo PnL scope is closed after adversarial verification.

The original `21 failed / 12 skipped` connector baseline is no longer current. Final Mac verification is:

- Focused GUI/Bybit/restart matrix: `60 passed`
- Full connector suite: `4199 passed, 12 skipped, 440 warnings`
- Syntax/static checks: `bash -n restart_all.sh`, Python `py_compile`, `node --check common.js`, scoped `git diff --check` all PASS

The remaining 12 skips are opt-in/live-PG/replay/observer/G3-08/risk-escalation environment skips. None are GUI Bybit-first PnL failures.

Linux / origin sync verification:

- Linux `trade-core` fast-forwarded from `1d1dff01` to `d731b34e`.
- Linux syntax/static checks: PASS.
- Linux focused GUI/Bybit/restart matrix: `60 passed`.
- Linux full connector suite: `4201 passed, 10 skipped, 448 warnings`.
- Linux runtime restarted with `restart_all.sh --keep-auth`; shared engine socket gate passed.
- Runtime smoke: startup-status HTTP 200, closed-pnl unauthenticated GET HTTP 401, engine watchdog `engine_alive=true`.

## Closed Gaps

- Bybit cursor signing now uses one canonical encoded query string for both URL and HMAC preimage, avoiding `%253A/%252C` cursor double encoding.
- PG fallback now respects `start_time` and `end_time`.
- `rc is None` fallback now returns PG rows when available instead of swallowing a `NameError` into an empty disabled payload.
- Blocking Bybit/cache/PG/strategy enrichment work is moved through `asyncio.to_thread`.
- Three Bybit failures in 60s now expose `bybit_failure_count_60s` and `degraded_until_ms`; GUI shows the operator-contact degraded banner.
- `restart_all.sh` uses one shared `ENGINE_SOCKET` for engine spawn, API spawn, and readiness gate.
- Legacy `test_pnl_series` fixture no longer confuses `SET LOCAL statement_timeout` with the aggregate SQL.

## Review

- E2 re-review: PASS
- BB re-review: PASS
- E4 regression: PASS

## Archive

Root `GUI-TODO.md` was removed and archived at:

- `docs/archive/2026-05-23--gui_bybit_first_pnl_refactor.md`

Active `TODO.md` was updated to reflect final verification status and the current `4199 passed / 0 failed / 12 skipped` connector result.

## Accepted Scope Boundaries

Per 1A2A3A:

- No 24h reconcile cron this sprint.
- No `/demo/wallet-truth` endpoint this sprint.
- Backend keeps 4 `strategy_source` values; GUI folds labels.
- PG `trading.fills` remains read-only from GUI and remains the audit/ML source.
