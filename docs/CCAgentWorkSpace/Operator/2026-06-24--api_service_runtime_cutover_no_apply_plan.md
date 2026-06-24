# Operator Note — API Service Runtime Cutover No-Apply Plan

Date: 2026-06-24

## Result

`P1-API-SERVICE-OWNERSHIP-RUNTIME-CUTOVER-REVIEW` is `DONE_WITH_CONCERNS`.

The repo now emits a no-apply `api_service_runtime_cutover_plan_v1` inside `api_service_env_parity.py`.

This plan is intentionally not an apply script and not restart authority. It preserves the reviewed manual uvicorn shape for a future systemd cutover review:

- host `100.91.109.86`
- port `8000`
- workers `4`
- working directory from the manual process snapshot
- runtime env-key parity without copying inline secrets

## Boundary

No systemd file was written, no daemon-reload was run, no process was signaled, no service was started/stopped/restarted, no crontab/env/runtime mutation was performed, and no PG/Bybit/live/probe/order authority was granted.

The broad Demo API authorization is useful operational permission, but it is not treated as live/mainnet authority or as an implicit bounded-probe/order authorization object.

## Fixes From Review

- Direct `OPENCLAW_DATABASE_URL` / `DSN` required env keys are now treated as secret and redacted instead of materialized into unit lines.
- `/usr/bin/python3 -m uvicorn app.main:app ...` wrapper commands are preserved correctly.
- Non-uvicorn command prefixes fail closed with `proposed_exec_start_incomplete`.

## Verification

- API env-parity + runtime-health hygiene tests: `35 passed`.
- Focused E2/E4 API env-parity tests: `13 passed`.
- `py_compile`: passed.
- `git diff --check`: passed.
- Supplied-snapshot CLI smoke: `API_SERVICE_ENV_PARITY_DRIFT`, with `apply_allowed=false` and `restart_allowed=false`.

## Next

Any real service cutover should be a separate runtime mutation checkpoint with fresh snapshots, E3 review, exact unit diff, backup/rollback proof, PID/cmdline/cwd revalidation, and post-cutover health verification.
