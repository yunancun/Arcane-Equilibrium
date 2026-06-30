# 2026-07-01 PM Checkpoint — Rust IPC Bybit Runtime Separation Guard

PM completed a source-only guard preventing Stock/ETF Rust IPC handler/test
source from importing or calling Bybit runtime/order code paths.

Scope:

- Add handler split structure coverage for `stock_etf.rs`,
  `stock_etf/request_summaries.rs`, and `stock_etf/status_summaries.rs`.
- Add fixture split structure coverage for parent `stock_etf.rs`,
  `stock_etf/request_contracts.rs`, and `stock_etf/status_fixtures.rs`.
- Block Bybit REST/WS/Earn clients, order manager/router, paper state,
  bounded-probe active-order modules, the legacy paper submit handler, and
  direct order method call tokens.
- Preserve contract-level negative posture fields such as
  `bybit_ipc_reused=false`, `bybit_path_reused=false`, and the legacy Bybit
  channel regression; the prohibited part is runtime code-path coupling.

Verification:

- `python3 -B -m py_compile tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`:
  PASS
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`:
  `10 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`:
  `115 passed`
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`:
  `2 passed`
- `git diff --check`: PASS

Boundary:

- No Rust runtime behavior change.
- No endpoint or IPC method change.
- No IBKR contact.
- No IBKR SDK import.
- No socket/HTTP client.
- No env/secret read or materialization.
- No connector runtime.
- No read probe execution.
- No paper order/cancel/replace.
- No fill import.
- No DB/evidence/scorecard writer.
- No tiny-live/live authority.
- No Linux runtime sync/restart.
- No Bybit behavior change.
