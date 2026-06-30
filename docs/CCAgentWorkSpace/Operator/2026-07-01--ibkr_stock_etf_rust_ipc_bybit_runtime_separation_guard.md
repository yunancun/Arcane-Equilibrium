# 2026-07-01 Operator Brief — Rust IPC Bybit Runtime Separation Guard

PM added a source-only guard proving Stock/ETF Rust IPC source does not import
or call Bybit runtime/order paths.

What changed:

- Handler guard scans `stock_etf.rs`, `request_summaries.rs`, and
  `status_summaries.rs`.
- Fixture guard scans parent `stock_etf.rs`, `request_contracts.rs`, and
  `status_fixtures.rs`.
- It blocks Bybit REST/WS/Earn clients, order manager/router, paper state,
  bounded-probe active-order modules, legacy paper submit handler calls, and
  direct order method call tokens.
- Contract/posture text such as `bybit_ipc_reused=false`,
  `bybit_path_reused=false`, and the legacy Bybit channel regression remains
  allowed.

Verification passed:

- Rust IPC split static guards: `10 passed`
- Full Stock/ETF FastAPI/static: `115 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no Rust runtime behavior change, endpoint/IPC method change,
IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read
probe execution, paper order/cancel/replace, fill import, DB/evidence writer,
tiny-live/live authority, Linux runtime sync/restart, or Bybit behavior change.
