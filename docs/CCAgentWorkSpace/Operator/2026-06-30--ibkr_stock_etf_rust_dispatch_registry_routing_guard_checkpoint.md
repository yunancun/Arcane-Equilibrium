# Operator Brief - IBKR Stock/ETF Rust Dispatch Registry Routing Guard

Date: 2026-06-30

## Summary

PM moved Stock/ETF Rust IPC routing to the method registry source of truth.

- `dispatch.rs` no longer carries a duplicated Stock/ETF method list.
- `is_stock_etf_fixture_method(...)` accepts only registered `stock_etf.`
  methods with `slot=None`.
- Legacy `submit_paper_order` and unknown methods do not route through the
  Stock/ETF fixture helper.
- This lowers registry/dispatch/live-token drift risk without changing Bybit
  routing or enabling IBKR runtime authority.

## Verification

- `rustfmt`: PASS
- Engine `stock_etf` filter: `31 passed`
- Full Stock/ETF FastAPI/static: `104 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
