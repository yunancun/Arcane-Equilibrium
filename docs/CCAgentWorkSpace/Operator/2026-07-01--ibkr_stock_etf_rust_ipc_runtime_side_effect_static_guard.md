# 2026-07-01 Operator Brief — Rust IPC Runtime Side-Effect Static Guard

PM added a source-only guard keeping Stock/ETF Rust IPC source free of clock,
thread/task, and process side effects.

What changed:

- Handler guard scans `stock_etf.rs`, `request_summaries.rs`, and
  `status_summaries.rs`.
- Fixture guard scans parent `stock_etf.rs`, `request_contracts.rs`, and
  `status_fixtures.rs`.
- The guard blocks time/clock, thread/task spawn, sleep, and process command
  tokens before any IBKR runtime approval.

Verification passed:

- Rust IPC split static guards: `12 passed`
- Full Stock/ETF FastAPI/static: `118 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no Rust runtime behavior change, endpoint/IPC method change,
IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read
probe execution, paper order/cancel/replace, fill import, DB/evidence writer,
tiny-live/live authority, Linux runtime sync/restart, or Bybit behavior change.
