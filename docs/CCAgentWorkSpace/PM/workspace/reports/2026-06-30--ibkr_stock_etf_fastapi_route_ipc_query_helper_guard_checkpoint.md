# IBKR Stock/ETF FastAPI Route IPC Query Helper Guard Checkpoint

Date: 2026-06-30
Owner: PM
Scope: Stock/ETF FastAPI route source hygiene only

## Summary

This checkpoint reduces duplicated Stock/ETF FastAPI IPC query logic without changing behavior or authority.

- Collapsed 16 duplicated `_query_stock_etf_*` status helpers in `stock_etf_routes.py` into one `_query_stock_etf_status(ipc, method)` helper.
- Preserved every endpoint, auth dependency, no-store header, method constant, normalizer, response envelope, and OpenAPI GET-only surface.
- Reduced `stock_etf_routes.py` from `587` to `393` lines.
- Updated the Python no-write static guard so it now proves:
  - there is exactly one `ipc.call(method, params={})` site;
  - all 16 route handlers call the central helper only with allowlisted readonly Stock/ETF method constants;
  - write IPC methods, IBKR SDK imports, network clients, persistence, file writers, and client-state route args remain blocked.

## Verification

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `24 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `105 passed`
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP client, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior change.
