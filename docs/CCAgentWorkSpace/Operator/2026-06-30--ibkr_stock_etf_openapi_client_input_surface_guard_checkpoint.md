# Operator Brief - IBKR Stock/ETF OpenAPI Client Input Surface Guard

Date: 2026-06-30

## Summary

PM added a source-only OpenAPI guard for Stock/ETF client input exposure.

- Every `/api/v1/stock-etf...` GET operation is scanned.
- `requestBody` is forbidden.
- Parameters are limited to the existing optional `Authorization` auth header.
- Future query/path/header/cookie/body client-state inputs fail the guard.

## Verification

- Stock/ETF route tests: `14 passed`
- Full Stock/ETF FastAPI/static: `104 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
