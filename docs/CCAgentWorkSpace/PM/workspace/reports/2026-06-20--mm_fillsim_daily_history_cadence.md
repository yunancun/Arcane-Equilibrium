# 2026-06-20 -- MM fill_sim daily history cadence

## Summary

v257 fixed fill_sim freshness correctness, but the default cadence still worked against the cross-window evidence goal: `fill_sim_refresh_cron.sh` ran daily, yet `OPENCLAW_FILL_SIM_MAX_AGE_H` defaulted to 60h. That means valid windows would normally accumulate about every 2.5 days, not daily.

This patch changes the default report max-age from 60h to 18h. With the installed daily 06:05 UTC cron, a normal prior-day run is old enough to refresh again, while same-day/manual refreshes still avoid unnecessary repeat work unless `OPENCLAW_FILL_SIM_FORCE=1` is set.

## Verification

Local checks:
- `python3 -m pytest -q helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` = 11 passed
- `bash -n helper_scripts/cron/fill_sim_refresh_cron.sh`
- `git diff --check`

Linux selective runtime sync:
- Synced `helper_scripts/cron/fill_sim_refresh_cron.sh` and `helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` to `trade-core`.
- Linux `bash -n helper_scripts/cron/fill_sim_refresh_cron.sh` passed.
- Linux `python3 -m pytest -q helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` passed 11/11.

Runtime note:
- No forced production fill_sim rerun was needed for this cadence-only patch. The latest valid production report remains the v257 fresh-L1 report, and the next natural daily cron can add the next history window when the report age crosses 18h.

## Read

This still does not promote MM. It improves evidence velocity: the history scorecard can now accumulate daily-ish valid windows instead of waiting ~60h between refreshes.

## Boundary

No rebuild, no restart, no DB write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order mutation, and no strategy parameter change.

Writes are limited to source/test/docs and selective Linux source sync.
