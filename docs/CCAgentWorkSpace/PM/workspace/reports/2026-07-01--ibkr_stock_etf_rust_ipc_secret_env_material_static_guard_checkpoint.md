# PM Checkpoint - IBKR Stock/ETF Rust IPC Secret/Env Material Static Guard

Date: 2026-07-01

Scope: Stock/ETF Rust IPC source split structure tests only.

## Outcome

PM added Rust structure guards proving Stock/ETF IPC handler and fixture-test
split files do not introduce direct env bypasses, secret-file/material readers,
network/socket clients, or direct IBKR SDK tokens.

## Guards

- Handler guard scans `stock_etf.rs`, `request_summaries.rs`, and
  `status_summaries.rs`.
- Fixture-test guard scans `stock_etf.rs`, `request_contracts.rs`, and
  `status_fixtures.rs` under the Rust IPC test tree.
- The parent handler must retain exactly one typed
  `StockEtfFeatureFlags::from_env()` feature-flag path.
- Forbidden tokens include direct `std::env` / `env::var`, `std::fs`,
  `File::open`, `read_to_string`, include material macros, `std::net`,
  socket/client crates, and direct IBKR SDK names.

## Verification

- Rust IPC split static guards: `8 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- Full Stock/ETF FastAPI/static: `112 passed`.
- `git diff --check`: PASS.

## Boundary

No Rust runtime behavior change, endpoint, IPC method, client input, IBKR
contact, SDK import, socket/HTTP, connector runtime, secret access, read probe
execution, paper order, fill import, evidence writer, DB apply, evidence clock,
tiny-live, live, or Bybit behavior change.
