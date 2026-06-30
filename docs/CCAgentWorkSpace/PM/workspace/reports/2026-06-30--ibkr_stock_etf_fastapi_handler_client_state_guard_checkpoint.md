# PM Checkpoint - IBKR Stock/ETF FastAPI Handler Client-State Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only route handler guard

## Result

- Added `test_stock_etf_get_route_handlers_accept_only_response_and_authenticated_actor`.
- The AST guard verifies every `@stock_etf_router.get` handler accepts only
  `response` and/or authenticated `actor`.
- The `actor` argument must be wired as `Depends(base.current_actor)`.
- This prevents Request/Header/Query/Body/Cookie/Form-style client state from
  entering Stock/ETF route handlers.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `7 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `101 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
