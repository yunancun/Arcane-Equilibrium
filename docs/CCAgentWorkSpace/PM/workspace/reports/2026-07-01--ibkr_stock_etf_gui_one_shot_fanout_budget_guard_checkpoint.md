# 2026-07-01 PM Checkpoint — GUI One-Shot Fanout Budget Guard

PM completed a static efficiency guard for the Stock/ETF GUI one-shot load path.

Scope:

- Guard `tab-stock-etf.js` to one `Promise.all` and one
  `waitForServerUp(loadReadiness)` call.
- Guard the Stock/ETF GUI fanout at exactly 16 `ocApi` calls.
- Require every call to be GET-only with `timeoutMs: 5000` and
  `toastOnError: false`.
- Prevent display-only GUI drift into extra API fanout, longer timeout budgets,
  or repeated loaders before runtime approval.

Verification:

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  `21 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`:
  `120 passed`
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`:
  `2 passed`
- `git diff --check`: PASS

Boundary:

- No endpoint or IPC method change.
- No client input change.
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
