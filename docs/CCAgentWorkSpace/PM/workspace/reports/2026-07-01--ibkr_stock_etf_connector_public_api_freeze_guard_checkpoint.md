# 2026-07-01 PM Checkpoint — IBKR Connector Public API Freeze Guard

PM completed a source-only public API freeze for the inert IBKR connector
skeleton.

Scope:

- Freeze `program_code.broker_connectors.ibkr_connector.__all__` to the
  source-only surface id, read-only client, paper boundary client, endpoint
  config, and surface status.
- Freeze `IbkrReadOnlyClient` public class surface to `config`,
  `readiness()`, `connection_plan()`, `account_snapshot_preview()`,
  `market_data_preview()`, and `contract_details_preview()`.
- Freeze `IbkrPaperClientBoundary` public class surface to
  `lifecycle_readiness()` and `fill_import_readiness()`.
- Preserve the existing forbidden write-method guard and add exact surface
  coverage so runtime-start, order-write, secret/network, or Bybit-reuse
  entrypoints cannot appear under alternative public names.

Verification:

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  `8 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  `18 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`:
  `117 passed`
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
