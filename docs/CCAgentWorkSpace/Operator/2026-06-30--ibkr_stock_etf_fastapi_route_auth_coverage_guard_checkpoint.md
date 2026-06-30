# Operator Brief - IBKR Stock/ETF FastAPI Route Auth Coverage Guard

Date: 2026-06-30

## Summary

PM added a source-only FastAPI auth coverage guard for Stock/ETF endpoints.

- The guard derives all Stock/ETF OpenAPI GET paths and adds the root redirect.
- Every route must return `401` without an authenticated actor.
- This keeps future display-only Stock/ETF surfaces private by default.

## Verification

- Stock/ETF route tests: `12 passed`
- Full Stock/ETF FastAPI/static: `98 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
