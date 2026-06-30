# Operator Brief - IBKR Stock/ETF FastAPI IPC Empty Params Guard

Date: 2026-06-30

## Summary

PM added a source-only AST guard for Stock/ETF FastAPI IPC status reads.

- Every `stock_etf_routes.py` IPC call must use literal `params={}`.
- Any future attempt to forward query params, headers, or client lane claims
  into Rust IPC status methods fails the guard.
- This preserves display-only, client-state-untrusted FastAPI behavior.

## Verification

- Python no-write static guard: `6 passed`
- Full Stock/ETF FastAPI/static: `100 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
