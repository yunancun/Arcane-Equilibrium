# PM Checkpoint - IBKR Stock/ETF Rust Status IPC Untrusted Params Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only Rust IPC status params guard

## Result

- Added `stock_etf_status_methods_ignore_untrusted_params`.
- The Rust IPC regression covers all Stock/ETF status/readiness methods.
- Each method is called with `{}` params and with malicious non-empty params
  claiming live, Bybit, paper submit, IBKR contact, secret touch, order routing,
  and Bybit IPC reuse.
- Results must match exactly, proving direct IPC params cannot influence
  status/readiness fixture output.

## Verification

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs`: PASS
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_status_methods_ignore_untrusted_params -- --nocapture`: `1 passed`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`: `31 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `104 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
