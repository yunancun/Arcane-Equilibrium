# P0-NEW-ISSUE-1 Live Pipeline Healthcheck

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

Added passive healthcheck `[56] live_pipeline_active` for the LiveDemo
`auth_missing` regression. `[Xb]` already exists as `pipeline_triangulation`,
so this checkpoint uses the next numeric slot instead of reusing `[Xb]`.

The check is filesystem-only and read-only:

- live slot configured = non-empty `live/api_key` + `live/api_secret`
- configured live slot requires non-empty `live/authorization.json`
- authorized live slot requires fresh `pipeline_snapshot_live.json`
- local/dev can opt out with `OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED=0`

## Runtime Fact

Linux `trade-core` currently has live slot key/secret/endpoint files present,
but `live/authorization.json` is missing. Engine log at 2026-05-09 01:37 UTC
shows `LIVE PIPELINE REFUSED TO START error_kind="file_missing"` for LiveDemo.

## Verification

- `python3 -m pytest helper_scripts/db/test_live_pipeline_healthcheck.py -q`
  -> 7 passed
- `python3 -m py_compile` for the new check, runner, package init, and test
- Local import smoke: unconfigured Mac dev slot PASS-skips as expected

## Boundary

No live auth renewal, no manual `authorization.json` write, no true-live API
action, no rebuild/restart, no DB mutation, no scanner authority change, no
Executor hard authority, no strategy/risk config mutation, and no MAG-083/084
unlock.

PM SIGN-OFF: APPROVED for source/test partial. Runtime recovery still requires
operator renewal through the signed live-auth route.

