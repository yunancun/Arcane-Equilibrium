# V077 Columnstore Runtime Hotfix

Date: 2026-05-09
Role: PM
Status: DEPLOYED / RUNTIME VERIFIED

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
- Linux pulled hotfix commit `49ceeb61` and restarted the engine with
  `restart_all.sh --engine-only --keep-auth`.
- Runtime DB now records V077 in `_sqlx_migrations`, and
  `trg_fills_engine_mode_known_values` exists on `trading.fills`.
- Engine process restarted as PID `4080150`; API remains on PID `4076067`.
- Passive healthcheck returned `SUMMARY: WARN` with no hard FAIL; `[55]`
  Agent Decision Spine lineage PASSed with `chains=121`,
  `chains_with_lease=96`, and `bad_report_quality=0`.

## Runtime Caveat

The live authorization file is missing at
`/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json`,
so the Rust engine refused to spawn the LiveDemo/live pipeline at boot and is
running demo-only after the hotfix restart. No manual live auth restore or
renewal was performed, because that would be a live-auth mutation requiring
separate operator approval.

## Boundary

The rebuild/restart was explicitly operator-authorized. No live auth mutation,
scanner authority change, Executor hard authority, strategy/risk config
mutation, MAG-083/MAG-084 unlock, or true-live API action was performed.

PM SIGN-OFF: APPROVED for V077 hotfix deployment; live pipeline remains
operator-auth blocked until separately renewed.
