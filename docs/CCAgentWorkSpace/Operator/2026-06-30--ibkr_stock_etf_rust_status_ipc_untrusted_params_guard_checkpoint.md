# Operator Brief - IBKR Stock/ETF Rust Status IPC Untrusted Params Guard

Date: 2026-06-30

## Summary

PM added a source-only Rust IPC regression for Stock/ETF status/readiness
params handling.

- All Stock/ETF status/readiness methods are covered.
- Each method must return the same result for `{}` params and malicious
  non-empty params.
- Malicious params claim live, Bybit, paper submit, IBKR contact, secret touch,
  order routing, and Bybit IPC reuse.
- Direct IPC callers cannot influence status/readiness fixture output through
  params.

## Verification

- `rustfmt`: PASS
- Focused engine test: `1 passed`
- Engine `stock_etf` filter: `31 passed`
- Full Stock/ETF FastAPI/static: `104 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
