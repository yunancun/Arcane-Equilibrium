# Operator Brief — IBKR Stock/ETF FastAPI Route IPC Query Helper Guard

Date: 2026-06-30

## What changed

- `stock_etf_routes.py` now uses one central `_query_stock_etf_status(ipc, method)` helper instead of 16 duplicated query helpers.
- Endpoint paths, auth, no-store headers, method constants, normalizers, response envelopes, and OpenAPI GET-only behavior are unchanged.
- Route source size dropped from `587` to `393` lines.
- Static guard now proves only one `ipc.call(method, params={})` exists and that all 16 route handlers use allowlisted readonly Stock/ETF method constants.

## Checks

- `py_compile`: PASS
- Route/no-write focused tests: `24 passed`
- Full Stock/ETF FastAPI/static tests: `105 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No endpoint or IPC-method expansion. No IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior change.
