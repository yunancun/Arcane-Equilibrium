# PM Checkpoint - IBKR Stock/ETF Rust IPC Handler Request Summary Split Guard

日期：2026-06-30
角色：PM(default)
Scope：ADR-0048 `stock_etf_cash` Rust IPC production handler structure.

## Verdict

`DONE_SOURCE_ONLY_BEHAVIOR_PRESERVED`

This checkpoint is a production Rust structure refactor only. It moves the
Stock/ETF request parsing and source-only paper/fill/shadow/readonly-probe
summary helpers into a dedicated child module while preserving handler entry,
dispatch routing, IPC methods, status payloads, and test-observed behavior.

## Changes

- Added `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/request_summaries.rs`.
- Moved request parsing and summary helpers:
  - `operation_for_method_and_params`
  - `request_from_params`
  - `paper_request_envelope_summary`
  - `fill_import_request_summary`
  - `shadow_signal_request_summary`
  - `readonly_probe_request_ipc_summary`
- Kept `stock_etf.rs` responsible for IPC entry, status method routing, Phase0/Phase2
  summaries, data/policy/authorization summaries, and explicit child imports.
- Updated `tests/structure/test_stock_etf_ipc_handler_split_static.py` to require
  exactly `request_summaries.rs` and `status_summaries.rs`, cap each parent/child
  handler file at `1200` lines, and block network/IBKR SDK tokens in child modules.

## Size Result

- `stock_etf.rs`: `823` lines, down from `1292`.
- `request_summaries.rs`: `477` lines.
- `status_summaries.rs`: `934` lines.

Every Stock/ETF Rust IPC handler module is now below the `1200` line cap.

## Verification

- `rustfmt --check`: PASS.
- Engine `stock_etf` filter: `31 passed`.
- Rust IPC handler/test split static guards: `6 passed`.
- Full Stock/ETF FastAPI/static suite: `105 passed`.
- Focused IBKR timeline + trace-title structure tests: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, dispatch route, IBKR API call, IBKR SDK import,
socket/HTTP client, secret access/creation, connector runtime, read probe
execution, paper order, cancel/replace, fill import, evidence writer, DB apply,
evidence clock, tiny-live/live authority, or Bybit live execution behavior
change.
