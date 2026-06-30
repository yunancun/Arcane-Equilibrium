# 2026-07-01 PM Checkpoint — FastAPI IBKR Connector Runtime Wiring Guard

PM completed a source-only guard preventing the inert IBKR connector skeleton
from being imported by the Stock/ETF FastAPI/control-api production surface
before runtime approval.

Scope:

- Add an AST regression over `control_api_v1/app` Stock/ETF / IBKR Python files.
- Block imports of `program_code.broker_connectors.ibkr_connector`,
  `broker_connectors.ibkr_connector`, and bare `ibkr_connector`.
- Block literal dynamic imports through `__import__`, `import_module`, and
  `importlib.import_module`.
- Keep dedicated skeleton tests free to import the source-only connector package.
- Preserve display-only payloads and routes; no runtime connector wiring.

Verification:

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  `18 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  `6 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`:
  `115 passed`
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`:
  `2 passed`
- `git diff --check`: PASS

Boundary:

- No IBKR contact.
- No IBKR SDK import.
- No socket/HTTP client.
- No env/secret read or materialization.
- No connector runtime.
- No read probe execution.
- No paper order/cancel/replace.
- No fill import.
- No DB/evidence/scorecard writer.
- No tiny-live/live authority.
- No Linux runtime sync/restart.
- No Bybit behavior change.
