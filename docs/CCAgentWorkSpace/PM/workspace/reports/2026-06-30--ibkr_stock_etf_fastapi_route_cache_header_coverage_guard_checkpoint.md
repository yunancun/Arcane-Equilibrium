# PM Checkpoint - IBKR Stock/ETF FastAPI Route Cache Header Coverage Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only route cache/header guard

## Result

- Added `test_stock_etf_all_registered_get_routes_are_private_no_store`.
- The guard derives all Stock/ETF OpenAPI GET paths, adds the root redirect
  `/api/v1/stock-etf`, and verifies private/no-store cache headers plus
  `Vary: Authorization`.
- This keeps future display-only Stock/ETF routes cache-partitioned and private
  by default.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`: `13 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `99 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
