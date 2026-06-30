# 2026-07-01 PM Checkpoint — IBKR Connector Bybit Import Separation Guard

PM completed a source-only separation guard for the inert IBKR connector
skeleton.

Scope:

- Add an AST regression proving
  `program_code/broker_connectors/ibkr_connector/**/*.py` does not import Bybit
  connector or control-api modules.
- Block direct imports of `app`, `bybit_connector`,
  `exchange_connectors.bybit_connector`, and
  `program_code.exchange_connectors.bybit_connector`.
- Block literal dynamic imports through `__import__` and
  `importlib.import_module`.
- Preserve the existing `bybit_path_reused=false` display field while preventing
  accidental code-path reuse.

Verification:

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  `6 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  `17 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`:
  `114 passed`
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
