# PM Checkpoint - IBKR Stock/ETF GUI Endpoint Template Consistency Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only route/template drift guard

## Result

- Added `test_stock_etf_openapi_paths_match_gui_lane_contract_template` to compare FastAPI OpenAPI Stock/ETF GET paths with `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations.
- The guard excludes root redirect `/api/v1/stock-etf`, because it is an authenticated redirect rather than a GUI lane contract status endpoint.
- The endpoint parser covers numeric keys such as `phase0_status_endpoint`.
- This does not add endpoints, activate GUI runtime authority, contact IBKR, or change Bybit behavior.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`: `11 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `96 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector runtime,
secret access/creation, read probe execution, paper order/cancel/replace, fill
import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
