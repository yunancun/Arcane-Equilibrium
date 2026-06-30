# PM Checkpoint - IBKR Stock/ETF Rust IPC Request Contract Test Split Guard

日期：2026-06-30
角色：PM(default)
Scope：ADR-0048 `stock_etf_cash` Rust IPC fixture tests.

## Verdict

`DONE_SOURCE_ONLY_BEHAVIOR_PRESERVED`

This checkpoint is a Rust test-structure refactor only. It moves Stock/ETF
paper/fill/shadow/readonly-probe request contract fixture tests out of the large
IPC test parent module while preserving the exact assertions and dispatch path.
It does not change handler logic, IPC method registration, production route
code, GUI behavior, IBKR runtime authority, or Bybit runtime behavior.

## Changes

- Added `rust/openclaw_engine/src/ipc_server/tests/stock_etf/request_contracts.rs`.
- Moved request-contract tests for:
  - paper order request envelope validation and IPC method mismatch
  - paper fill import request validation
  - shadow signal request validation
  - readonly probe request validation and operation binding
  - legacy paper route channel boundary
  - live typed-denial boundary
- Kept `stock_etf.rs` responsible for readiness/lane/phase/status fixture regressions
  and shared helpers.
- Updated `tests/structure/test_stock_etf_ipc_tests_split_static.py` to require
  exactly `request_contracts.rs` and `status_fixtures.rs`, cap each parent/child
  test file at `1200` lines, and block network/IBKR SDK tokens in moved fixtures.

## Size Result

- `stock_etf.rs`: `1110` lines, down from `1852`.
- `request_contracts.rs`: `745` lines.
- `status_fixtures.rs`: `685` lines.

Every Stock/ETF Rust IPC test module is now below the `1200` line cap.

## Verification

- `rustfmt`: PASS.
- Engine `stock_etf` filter: `31 passed`.
- Rust IPC test split static guard: `3 passed`.
- Full Stock/ETF FastAPI/static suite: `105 passed`.
- Focused IBKR timeline + trace-title structure tests: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, IBKR API call, IBKR SDK import, socket/HTTP client,
secret access/creation, connector runtime, read probe execution, paper order,
cancel/replace, fill import, evidence writer, DB apply, evidence clock,
tiny-live/live authority, or Bybit live execution behavior change.
