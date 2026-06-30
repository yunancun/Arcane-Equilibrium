# PM Checkpoint - IBKR Stock/ETF Rust Dispatch Registry Routing Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only Rust dispatch registry routing guard

## Result

- Added `is_stock_etf_fixture_method(...)` in `method_registry.rs`.
- The helper accepts only registered `stock_etf.` methods with `slot=None`.
- `dispatch.rs` now routes Stock/ETF IPC methods through the registry helper
  instead of a duplicated hand-written method list.
- Registry tests prove every Stock/ETF method is accepted by the helper while
  legacy `submit_paper_order` and unknown methods are not.

## Verification

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/dispatch.rs rust/openclaw_engine/src/ipc_server/method_registry.rs`: PASS
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`: `31 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `104 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
