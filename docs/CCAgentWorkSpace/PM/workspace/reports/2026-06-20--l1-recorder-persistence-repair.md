# L1 Recorder Persistence Repair

Date: 2026-06-20
Owner: PM

## Summary

`market.l1_events` stopped because the running engine was restarted without the recorder-v2 env flag. The active PID had:

- `OPENCLAW_RECORD_L1_EVENTS=`
- `OPENCLAW_RECORD_TICKS=1`

That explains why `market.trades` and `market.ob_top` remained fresh while `market.l1_events` stopped at `2026-06-17 21:55:45+02`.

## Fix

`helper_scripts/restart_all.sh` now mirrors the durable env pattern used by other engine gates:

- parent operator env still wins
- otherwise `OPENCLAW_RECORD_L1_EVENTS` is read from `basic_system_services.env`
- `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL` is read the same way

A static regression test prevents returning to parent-only behavior.

## Runtime Repair

On `trade-core`, the non-secret env-file values were set:

- `OPENCLAW_RECORD_L1_EVENTS=1`
- `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL=50`

Then an engine-only restart was performed:

- command: `bash helper_scripts/restart_all.sh --engine-only --keep-auth`
- no rebuild
- no API restart
- no schema migration

New engine PID: `4155643`.

## Verification

Local:

- `bash -n helper_scripts/restart_all.sh`
- `python3 -m pytest -q tests/structure/test_restart_all_keep_auth_preflight_static.py` -> 5 passed
- `git diff --check` clean

Linux:

- same bash/pytest/diff-check passed after selective deploy
- `/proc/4155643/environ` confirmed `OPENCLAW_RECORD_L1_EVENTS=1` and L1 cap `50`
- read-only PG query showed `l1_max_ts=2026-06-20T02:19:20.531+02`, `l1_rows_5m=2635`, stale `0.027min`
- `recorder_health_cron.sh` status showed `rows_24h=4566`, `stale_min=0.03`, crossed/locked `0.00`

## Boundary

This repaired the recorder path and data freshness. It is not a trading promotion proof.

No Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation, no PG table write/schema migration, no API restart, and no rebuild were performed.

## Next

Let the bounded daily fill_sim refresh regenerate current-regime adverse-selection data now that fresh L1 is accruing. MM promotion remains blocked until maker-fill sample, adverse-selection, and net-edge gates are positive with adequate sample size.
