# Operator Brief - IBKR Stock/ETF FastAPI Handler Client-State Guard

Date: 2026-06-30

## Summary

PM added a source-only AST guard for Stock/ETF FastAPI route handler inputs.

- Every `@stock_etf_router.get` handler may accept only `response` and/or
  authenticated `actor`.
- `actor` must be `Depends(base.current_actor)`.
- Future Request/Header/Query/Body/Cookie/Form-style client-state inputs fail
  the guard.

## Verification

- Python no-write static guard: `7 passed`
- Full Stock/ETF FastAPI/static: `101 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
