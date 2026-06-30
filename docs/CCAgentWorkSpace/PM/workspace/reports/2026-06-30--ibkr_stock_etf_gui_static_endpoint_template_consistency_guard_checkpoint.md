# PM Checkpoint - IBKR Stock/ETF GUI Static Endpoint Template Consistency Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only static GUI/template drift guard

## Result

- Added `test_stock_etf_static_gui_endpoint_set_matches_gui_lane_contract_template`.
- The guard scans the Stock/ETF static GUI bundle for `/api/v1/stock-etf...`
  endpoint strings and requires that set to equal
  `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations.
- This complements the OpenAPI/template guard and prevents GUI source from
  drifting ahead of, or behind, the source contract.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `5 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `97 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
