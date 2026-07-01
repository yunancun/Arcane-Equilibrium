# PM Report — Stock/ETF Reconciliation Route Exact Contract-Violation Guard

Date: 2026-07-01
Role: PM(default)
Scope: Source-only/test-only hardening for the Stock/ETF FastAPI reconciliation route.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Python reconciliation route test so
`contract_violations` are asserted as an exact ordered vector instead of a broad
subset check.

## Changes

- Added `EXPECTED_RECONCILIATION_CONTRACT_VIOLATIONS` for top-level side-effect
  flags, lane/environment drift, reconciliation readiness flags, lifecycle/event
  log/shadow/reconciliation contract drift, and matching artifact drift.
- Converted the reconciliation route contract-violation check from
  `issubset(set(data["contract_violations"]))` to an exact ordered list
  assertion.
- Added a local source guard preventing this reconciliation test file from
  reintroducing loose `set(data["contract_violations"])`,
  `in data["contract_violations"]`, or subset checks before the guard.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_reconciliation_status_routes.py --tb=short` — 6 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_reconciliation_status_routes.py --tb=short` — 16 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 137 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_reconciliation_status_routes.py` — PASS.
- Reconciliation no-loose contract violation assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No FastAPI route behavior changed. No connector production code, GUI behavior,
Rust IPC behavior, IBKR contact, IBKR SDK import, socket/client construction,
secret access or serialization, connector runtime, broker session, read-only
probe execution, paper order routing, fill import, DB/evidence/scorecard writer,
evidence clock, paper-shadow launch, tiny-live/live authorization, Linux runtime
sync/restart, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because the available tool policy only
permits spawning when the operator explicitly requests subagents/parallel agent
work. This was a narrow source-only test checkpoint verified locally with
focused and broad Stock/ETF Python tests.
