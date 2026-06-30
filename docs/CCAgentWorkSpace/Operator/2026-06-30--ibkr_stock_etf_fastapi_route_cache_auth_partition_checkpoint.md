# 2026-06-30 IBKR Stock/ETF FastAPI Route Cache Auth Partition Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- Stock/ETF readiness and tab redirect responses now emit `Cache-Control: no-cache, no-store, private, max-age=0, must-revalidate`, `Pragma: no-cache`, `Expires: 0`, and `Vary: Authorization`.
- Route tests now prove client-supplied lane/paper/contact state in query parameters or headers is ignored: the route still calls only `stock_etf.get_readiness` with empty params and uses the Rust IPC payload as source of truth.
- Existing auth coverage still requires authentication for `/api/v1/stock-etf/readiness`.

## Boundary

- This is a GET-only FastAPI route/cache/auth partition checkpoint.
- No IBKR contact, healthcheck, socket, connector construction, secret read/create/serialization, paper order, fill import, audit writer, DB apply, GUI authority, lane selector authority, release, Phase 2 start, tiny-live, or live authority was added or exercised.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`
  - passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - `14 passed`
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow and API-only; focused route/cache/auth and static no-write tests cover the regression surface.

## Next Gate

Continue Phase 1/4 readiness hardening. Do not proceed to Phase 2 IBKR read-only contact until the immutable external-surface PASS artifact and real secret/topology evidence exist.
