# Operator Brief - IBKR Stock/ETF FastAPI Route Cache Header Coverage Guard

Date: 2026-06-30

## Summary

PM added a source-only FastAPI cache/header coverage guard for Stock/ETF routes.

- The guard derives all Stock/ETF OpenAPI GET paths and adds the root redirect.
- Every route must emit private/no-store cache headers and `Vary: Authorization`.
- This prevents future display-only Stock/ETF surfaces from leaking stale or
  cross-actor status through shared caches.

## Verification

- Stock/ETF route tests: `13 passed`
- Full Stock/ETF FastAPI/static: `99 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
