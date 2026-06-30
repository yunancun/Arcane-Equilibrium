# 2026-07-01 PM Checkpoint — Python Runtime Side-Effect Static Guard

PM completed a source-only runtime side-effect guard for the scoped Stock/ETF /
IBKR Python surface.

Scope:

- Add an AST guard over the existing Stock/ETF/IBKR scoped Python file list.
- Block imports of `time`, `datetime`, `asyncio`, `threading`,
  `multiprocessing`, `subprocess`, `concurrent`.
- Block timing/background-work calls including `sleep`, `time`, `monotonic`,
  `perf_counter`, `now`, `utcnow`, `fromtimestamp`, `Thread`, `Process`,
  `Popen`, `run`, `create_task`, and `to_thread`.
- Preserve existing Bybit runtime modules by scanning only Stock/ETF FastAPI
  routes/normalizers and the inert IBKR connector skeleton.

Verification:

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  `19 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  `8 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`:
  `118 passed`
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`:
  `2 passed`
- `git diff --check`: PASS

Boundary:

- No endpoint or IPC method change.
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
