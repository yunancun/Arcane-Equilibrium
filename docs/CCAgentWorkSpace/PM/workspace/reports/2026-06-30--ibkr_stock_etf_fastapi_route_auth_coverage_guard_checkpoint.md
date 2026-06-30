# PM Checkpoint - IBKR Stock/ETF FastAPI Route Auth Coverage Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only route auth guard

## Result

- Added `test_stock_etf_all_registered_get_routes_require_auth`.
- The guard derives all Stock/ETF OpenAPI GET paths, adds the authenticated root
  redirect `/api/v1/stock-etf`, and verifies each route returns `401` without
  the `current_actor` dependency override.
- This prevents future display-only Stock/ETF routes from being added without
  authentication.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`: `12 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `98 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
