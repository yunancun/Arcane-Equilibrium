# PM Checkpoint - IBKR Stock/ETF Python Connector Network Static Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only static guard hardening

## Result

- Hardened `test_stock_etf_python_no_write_static_guard.py` so Stock/ETF / IBKR Python surfaces cannot import network client modules while the IBKR connector remains source-only and inert.
- The guard now rejects direct imports of `socket`, `http.client`, `requests`, `httpx`, `urllib`, `urllib3`, `aiohttp`, `websocket`, and `websockets`.
- The guard also rejects dynamic `__import__()` / `import_module()` loading of forbidden direct IBKR SDK modules or network modules.
- The scan remains scoped to Stock/ETF / IBKR Python surfaces and `program_code/broker_connectors/ibkr_connector/`; it does not scan or change existing Bybit connector modules.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `4 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector runtime,
secret access/creation, read probe execution, paper order/cancel/replace, fill
import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
