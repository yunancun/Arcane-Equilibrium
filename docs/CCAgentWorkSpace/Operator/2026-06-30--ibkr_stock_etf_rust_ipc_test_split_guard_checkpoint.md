# Operator Brief - IBKR Stock/ETF Rust IPC Test Split Guard

Date: 2026-06-30

## Summary

PM split the oversized Stock/ETF Rust IPC fixture test file without changing
runtime behavior.

- Account/Reconciliation/Scorecard/Launch/Release/Disable status fixture tests
  now live in `rust/openclaw_engine/src/ipc_server/tests/stock_etf/status_fixtures.rs`.
- Parent `stock_etf.rs` is down from `2532` lines to `1852`; the child module is
  `685` lines.
- A new structure guard enforces the 2000-line cap on the parent and child
  Stock/ETF IPC test files and blocks IBKR SDK / socket / HTTP client tokens in
  the moved fixture module.
- This is test/source hygiene only; no handler, dispatch, Bybit, or IBKR runtime
  authority changed.

## Verification

- `rustfmt`: PASS
- Engine `stock_etf` filter: `31 passed`
- Rust IPC split static guard: `2 passed`
- Full Stock/ETF FastAPI/static: `105 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No new endpoint, IBKR contact, SDK import, socket/HTTP, secret access/creation,
connector runtime, read probe execution, paper order/cancel/replace, fill import,
evidence writer, DB apply, evidence clock, tiny-live/live authority, or Bybit
behavior change.
