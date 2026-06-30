# 2026-06-30 IBKR Stock/ETF FastAPI Redirect Auth Partition Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- `GET /api/v1/stock-etf` tab redirect now requires the same authenticated actor dependency as the Stock/ETF read APIs.
- Added a negative test proving unauthenticated redirect access returns `401`.
- Existing route-method tests still prove the Stock/ETF API namespace exposes only GET routes and rejects POST/PUT/PATCH/DELETE with `405`.

## Boundary

- This is a source-only FastAPI auth partition checkpoint.
- No IBKR contact, healthcheck, socket, connector construction, secret read/create/serialization, paper order, fill import, audit writer, DB apply, GUI authority, lane selector authority, release, Phase 2 start, tiny-live, or live authority was added or exercised.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`
  - passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - `22 passed`
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow and auth-only; focused FastAPI/static no-write tests cover the regression surface.

## Next Gate

Continue Phase 4 display-only Stock/ETF views or Phase 1 source-fixture hardening. Do not proceed to Phase 2 IBKR read-only contact until the immutable external-surface PASS artifact and real secret/topology evidence exist.
