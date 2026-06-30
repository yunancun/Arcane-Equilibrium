# PM Checkpoint - IBKR Stock/ETF FastAPI IPC Method Allowlist Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only IPC method guard

## Result

- Added `test_stock_etf_routes_call_only_readonly_status_ipc_methods`.
- The AST guard verifies every `stock_etf_routes.py` `ipc.call(...)` uses a
  named method constant.
- The resolved method set must exactly match the readonly Stock/ETF
  status/readiness IPC allowlist.
- This prevents paper preview/submit/cancel/replace, fill import, shadow
  evaluation, readonly-probe preview, or other non-status methods from entering
  the FastAPI GET/status surface.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `8 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `102 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
