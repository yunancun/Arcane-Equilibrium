# Operator Brief - IBKR Stock/ETF Rust IPC Handler Split Guard

Date: 2026-06-30

## Summary

PM split the oversized Stock/ETF Rust IPC handler file without changing runtime
behavior or IPC contracts.

- Tail status summary builders now live in
  `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`.
- Parent `stock_etf.rs` is down from `2217` lines to `1292`; the child module is
  `934` lines.
- Parent handler still owns IPC entry, readiness, Phase 2 precontact summary,
  operation selection, and request envelope parsing.
- A new structure guard enforces the 2000-line cap on the parent and child
  Stock/ETF IPC handler files and blocks IBKR SDK / socket / HTTP client tokens
  in the moved status-summary module.
- This is source hygiene only; no handler behavior, dispatch routing, Bybit
  behavior, or IBKR runtime authority changed.

## Verification

- `rustfmt`: PASS
- Engine `stock_etf` filter: `31 passed`
- Rust IPC handler/test split static guards: `4 passed`
- Full Stock/ETF FastAPI/static: `105 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No new endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, secret
access/creation, connector runtime, read probe execution, paper
order/cancel/replace, fill import, evidence writer, DB apply, evidence clock,
tiny-live/live authority, or Bybit behavior change.
