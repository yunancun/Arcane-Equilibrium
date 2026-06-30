# 2026-07-01 Operator Brief - IBKR Stock/ETF Rust IPC Secret/Env Material Static Guard

PM completed a source-only Rust IPC structure checkpoint for Stock/ETF / IBKR
secret and environment material access.

- Handler split guard scans `stock_etf.rs`, `request_summaries.rs`, and
  `status_summaries.rs`.
- Fixture-test split guard scans the Rust parent IPC test plus
  `request_contracts.rs` and `status_fixtures.rs`.
- The only allowed env path in the handler is the existing typed
  `StockEtfFeatureFlags::from_env()` feature-flag call.
- Direct env bypass, secret-file readers, include material macros,
  network/socket clients, and direct IBKR SDK tokens are forbidden.

Verification passed:

- Rust IPC split static guards: `8 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- Full Stock/ETF FastAPI/static: `112 passed`
- `git diff --check`

Boundary unchanged: no Rust runtime behavior change, no IBKR contact, no broker
SDK/network client, no connector runtime, no secret access, no read probe
execution, no paper order, no DB/evidence writer, no tiny-live/live authority,
and no Bybit behavior change.
