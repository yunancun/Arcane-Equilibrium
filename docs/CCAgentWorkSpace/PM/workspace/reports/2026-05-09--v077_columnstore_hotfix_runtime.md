# V077 Columnstore Runtime Hotfix

Date: 2026-05-09
Role: PM
Status: RUNTIME HOTFIX IN PROGRESS

## Trigger

After the operator-authorized three-side sync plus `restart_all.sh --rebuild
--keep-auth`, the Rust release build and API restart succeeded, but engine
startup aborted during auto-migrate V077.

The failing database error was:

`operation not supported on hypertables that have columnstore enabled`

The table was `trading.fills`. `_sqlx_migrations` showed V068-V076 had applied
and V077 had not.

## Fix

V077 now keeps the original named CHECK path as the preferred enforcement
mechanism. If Timescale returns `feature_not_supported`, V077 installs
`trading.enforce_fills_engine_mode_known_values()` and
`trg_fills_engine_mode_known_values` as a same-predicate BEFORE
INSERT/UPDATE trigger fallback.

This keeps canonical runtime modes bounded to `paper`, `demo`, `live`, and
`live_demo`, while allowing the audited pre-2026-04-19 CEST
`demo_archive_20260418` rows. Existing rows are not rewritten, and columnstore
is not disabled.

## Verification

- `python3 -m pytest tests/migrations/test_v077_fills_engine_mode_archive_check.py -q`
  -> 5 passed
- `git diff --check`
- Linux PG dry-run with `BEGIN ... ROLLBACK` against the current runtime DB
  passed and produced the expected trigger-fallback notice.

## Boundary

The rebuild/restart was explicitly operator-authorized. No live auth mutation,
scanner authority change, Executor hard authority, strategy/risk config
mutation, MAG-083/MAG-084 unlock, or true-live API action was performed.

PM SIGN-OFF: CONDITIONAL until the patched V077 is committed, pushed, pulled on
Linux, and the engine restart verifies fresh snapshots.
