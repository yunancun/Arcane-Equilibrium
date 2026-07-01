# 2026-07-01 — Stock/ETF Rust Source Coverage Static Guard

## Scope

PM added a source-only meta guard for IBKR/Stock-ETF Rust source coverage.

This is not a Rust behavior change, not an IPC runtime change, not IBKR contact, not connector
runtime wiring, not secret access, not paper order routing, and not a Bybit behavior change. It only
locks that Stock/ETF/IBKR Rust contract and IPC handler files remain directly referenced by
structure, acceptance, engine IPC, or control-api tests.

## Guard Added

- `tests/structure/test_stock_etf_rust_source_coverage_static.py`

The guard pins:

- all current `rust/openclaw_types/src/**/*ibkr*.rs` and `**/*stock_etf*.rs` files are selected;
- the Stock/ETF IPC handler parent and all child modules under
  `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/` are selected;
- nested child modules such as paper-order fixtures/validation, Phase3 market-data, scorecard input
  components/bundle, precontact, request/status summaries, and scorecard summary remain in scope;
- Bybit runtime modules such as REST client, order manager, and bounded-probe active-order are not
  selected;
- every selected Rust source file is directly referenced by existing tests outside this guard.

## Verification

- New structure guard py_compile: PASS.
- Focused new guard pytest: `3 passed`.
- Focused Stock/ETF/IBKR source-static structure subset: PASS.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No IBKR SDK import, no socket/HTTP, no secret read or creation, no connector runtime, no read-only
probe, no result import, no evidence or scorecard writer, no DB apply, no paper order route, no
tiny-live/live authorization, and no Bybit live/demo execution change.
