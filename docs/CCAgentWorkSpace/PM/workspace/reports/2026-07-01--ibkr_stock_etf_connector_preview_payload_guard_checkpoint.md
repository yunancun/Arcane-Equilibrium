# 2026-07-01 PM Checkpoint — IBKR Connector Preview Payload Guard

PM completed a source-only hardening checkpoint for the inert IBKR connector
skeleton preview payloads.

Scope:

- Make `IbkrReadOnlyClient.connection_plan()` explicitly fail closed with the
  connector surface id, `accepted=false`, `status=blocked_source_only`,
  `phase2_gate_not_accepted`, and `connection_plan_blocked`.
- Add exact payload-shape regression coverage for connection plan, readiness,
  account snapshot, market data, contract details, paper lifecycle, fill import,
  and static fixture previews.
- Keep all preview payloads secret-free and side-effect-free: no network contact,
  no secret material, no paper/live channel, no broker write authority, no DB
  apply authority, and no Bybit path reuse.

Verification:

- `python3 -B -m py_compile program_code/broker_connectors/ibkr_connector/readonly_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`:
  `5 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`:
  `17 passed`
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`:
  `113 passed`
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
