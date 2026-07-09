# Keep-Auth Missing-Auth RCA

Date: 2026-05-09
Role: PM
Status: DONE

## Finding

The later `restart_all.sh --rebuild --keep-auth` did not itself delete
`authorization.json`. Linux archived engine log
`/tmp/openclaw/engine_logs/engine-1778289328.log` shows the earlier boot at
`2026-05-09T01:11:28Z` consumed a `manual` restart sentinel and cleared the
signed live authorization. Later keep-auth restarts preserved that already
missing state.

## Fix

`helper_scripts/restart_all.sh --keep-auth` now performs a read-only preflight:
if the live slot has `api_key` and `api_secret` but `authorization.json` is
absent, it prints an explicit warning that the restart will preserve auth
absence and that the operator must renew through signed
`/api/v1/live/auth/renew`.

## Verification

- `bash -n helper_scripts/restart_all.sh`
- `python3 -m pytest -q tests/structure/test_restart_all_keep_auth_preflight_static.py`
- `git diff --check`

## Boundary

The guard is warning-only and read-only. It does not write, renew, delete, or
revoke `authorization.json`; it does not restart services, mutate live auth,
enable true mainnet, change strategy/risk config, or unlock MAG-083/MAG-084.

PM SIGN-OFF: APPROVED.
