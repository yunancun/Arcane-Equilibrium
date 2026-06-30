# PM Checkpoint - IBKR Stock/ETF GUI Data/Policy Fallback Split Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only GUI bundle hygiene

## Result

- Split the Data Foundation / Policy fallback payloads from
  `tab-stock-etf.js` into `tab-stock-etf-data-policy.js`.
- Loaded the split before the main Stock/ETF GUI loader.
- Reduced `tab-stock-etf.js` from `1976` to `1805` lines.
- Added a static regression requiring every Stock/ETF GUI bundle file to stay
  at or below the 2000-line governance cap.

## Verification

- Stock/ETF JS `node --check`: PASS
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `10 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `105 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no new endpoint, IBKR contact, SDK import, socket/HTTP,
connector runtime, secret access/creation, read probe execution, paper
order/cancel/replace, fill import, evidence writer, DB apply, evidence clock,
tiny-live, live, or Bybit behavior change.
