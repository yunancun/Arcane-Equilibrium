# 2026-06-30 IBKR Stock/ETF FastAPI Route Method Partition Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- Stock/ETF FastAPI route tests now assert the OpenAPI surface exposes only `GET /api/v1/stock-etf/readiness`.
- Runtime negative tests now assert `POST`, `PUT`, `PATCH`, and `DELETE` return `405` for both `/api/v1/stock-etf` and `/api/v1/stock-etf/readiness`.
- Existing static no-write tests still scan Stock/ETF/IBKR Python and static GUI surfaces for broker write methods, forbidden write route decorators, forbidden IBKR broker modules, direct `fetch`, forms, browser storage lane authority, and Stock/ETF write IPC strings.

## Boundary

- This is a source-only FastAPI route-method negative-test checkpoint.
- No IBKR contact, healthcheck, socket, connector construction, secret read/create/serialization, paper order, fill import, audit writer, DB apply, GUI authority, lane selector authority, release, Phase 2 start, tiny-live, or live authority was added or exercised.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`
  - passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - `16 passed`
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow and test-only; route-method negative tests plus the existing static no-write guard cover the regression surface.

## Next Gate

Continue Phase 1/4 readiness hardening. Do not proceed to Phase 2 IBKR read-only contact until the immutable external-surface PASS artifact and real secret/topology evidence exist.
