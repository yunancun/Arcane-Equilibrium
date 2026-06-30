# Operator Brief - IBKR Stock/ETF FastAPI IPC Method Allowlist Guard

Date: 2026-06-30

## Summary

PM added a source-only AST guard for Stock/ETF FastAPI IPC method selection.

- Every `stock_etf_routes.py` `ipc.call(...)` must use a named method constant.
- The resolved method set must exactly match the readonly Stock/ETF
  status/readiness IPC allowlist.
- Future paper preview/submit/cancel/replace, fill import, shadow evaluation,
  readonly-probe preview, or other non-status methods fail the guard if wired to
  the FastAPI GET/status surface.

## Verification

- Python no-write static guard: `8 passed`
- Full Stock/ETF FastAPI/static: `102 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
