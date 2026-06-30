# PM Checkpoint - IBKR Stock/ETF Python Persistence Static Guard

Date: 2026-06-30
Status: DONE_WITH_BOUNDARY - source-only Python persistence guard

## Result

- Added `test_stock_etf_ibkr_python_surface_has_no_persistence_or_file_writers`.
- The AST guard scans scoped Stock/ETF / IBKR Python files.
- It blocks DB/persistence/object-store imports such as psycopg, psycopg2,
  sqlalchemy, sqlite3, asyncpg, duckdb, redis, and boto3.
- It blocks local persistence/evidence-writer imports such as `db_pool`,
  `audit_persistence`, `state_store`, and `agent_event_store`.
- It blocks dynamic persistence imports and explicit file-writer calls including
  `write_text`, `write_bytes`, write-mode `open(...)`, and `os.replace(...)`.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `9 passed`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `103 passed`
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

## Boundary

This checkpoint grants no IBKR contact, SDK import, socket/HTTP, connector
runtime, secret access/creation, read probe execution, paper order/cancel/replace,
fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit
behavior change.
