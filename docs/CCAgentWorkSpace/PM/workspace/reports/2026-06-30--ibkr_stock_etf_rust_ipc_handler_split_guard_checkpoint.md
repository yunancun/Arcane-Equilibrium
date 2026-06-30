# PM Checkpoint - IBKR Stock/ETF Rust IPC Handler Split Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only Rust IPC handler split guard

## Result

- Split tail Stock/ETF Rust IPC status summary builders into
  `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`.
- Reduced parent `stock_etf.rs` from `2217` lines to `1292` lines; the child
  status-summary module is `934` lines.
- Kept the parent handler responsible for IPC entry, readiness, Phase 2
  precontact summary, operation selection, and request envelope parsing.
- Added `tests/structure/test_stock_etf_ipc_handler_split_static.py` so the
  handler parent and child files stay below the 2000-line governance cap.
- The new guard also checks the moved builder functions remain in the child
  module and blocks IBKR SDK / socket / HTTP client tokens there.

## Verification

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`: PASS
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`: `31 passed`
- `python3 -m pytest -q tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`: `4 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `105 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no new endpoint, IPC method, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access/creation, read probe execution,
paper order/cancel/replace, fill import, evidence writer, DB apply, evidence
clock, tiny-live, live, or Bybit behavior change.
