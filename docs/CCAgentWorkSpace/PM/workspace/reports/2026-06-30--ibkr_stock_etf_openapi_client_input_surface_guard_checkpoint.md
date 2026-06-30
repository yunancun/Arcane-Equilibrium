# PM Checkpoint - IBKR Stock/ETF OpenAPI Client Input Surface Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only OpenAPI input guard

## Result

- Added `test_stock_etf_openapi_exposes_no_client_state_inputs`.
- The route/OpenAPI guard scans every `/api/v1/stock-etf...` GET operation.
- Operations may not expose `requestBody`.
- Parameters may only include the existing optional `Authorization` header from
  auth.
- This prevents query/path/header/cookie/body client-state inputs from appearing
  in the public Stock/ETF OpenAPI contract.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`: `14 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `104 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
