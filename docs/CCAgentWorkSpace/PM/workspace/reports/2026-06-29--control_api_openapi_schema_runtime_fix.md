# Control API OpenAPI Schema Runtime Fix

Date: 2026-06-29
Owner: PM
Status: DONE_WITH_CONCERNS
Runtime transition: DONE_WITH_CONCERNS

## Summary

The Control API `/openapi.json` runtime 500 was traced to `replay_advisory_routes.py` using postponed annotations. Linux `trade-core` runs FastAPI `0.115.12` and Pydantic `2.11.2`, which failed schema generation with an unresolved `ReplayAdvisoryRankRequest` forward reference. Mac local venv is newer and did not reproduce the failure, so the regression test now asserts the replay advisory router OpenAPI schema directly.

Source commit:

- `d9c25fe1` `Fix replay advisory OpenAPI schema on runtime`

## Verification

Local:

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_advisory_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_advisory_routes.py`
- `PYTHONPATH=program_code/exchange_connectors/bybit_connector/control_api_v1 python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_advisory_routes.py` -> `4 passed`
- Full local app OpenAPI generation -> `FULL_OPENAPI_OK 288`

Runtime:

- Runtime checkout clean on `main...origin/main`
- Learning cron expected-head markers repinned to runtime HEAD, count `9`
- Runtime py_compile for route and test passed
- Runtime focused replay advisory tests -> `4 passed`
- Runtime full app OpenAPI generation -> `FULL_OPENAPI_OK 288`
- Runtime HTTP `/openapi.json` -> `200`, OpenAPI `3.1.0`, `288` paths
- Protected Demo balance endpoint still returns `401` when unauthenticated

## Runtime Boundary

Only `openclaw-trading-api.service` was restarted to load the source fix. Engine PID `877736` remained alive and was not restarted. No secret/env mutation, private Bybit call, credential validation request, Decision Lease acquire/release, order/cancel/modify, registry/PG write, model load, Cost Gate lowering, live/mainnet authority, promotion authority, or profit proof occurred.

## Remaining Blockers

The API schema/runtime hygiene blocker is resolved, but bounded Demo execution remains blocked by:

- Demo API slot prefix mismatch: current `FWkGZX...`, expected `BHw4...`
- `BYBIT_MODE=read_only` and `BYBIT_CONNECTOR_WRITE_ENABLED=false`
- serving/proof chain not ready
- no candidate-matched order/fill/fee/slippage/reconstruction evidence

Next step remains secure operator Demo key/secret entry through `/api/v1/settings/api-key/{slot}` with slot `demo`, plus reviewed Demo-only connector mode cutover, then a fresh readiness/final-window gate run.
