# PM Report — Stock/ETF Launch Route Exact Contract-Violation Guard

Date: 2026-07-01
Role: PM(default)
Scope: Source-only/test-only hardening for the Stock/ETF FastAPI launch route.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Python launch route test so `contract_violations`
are asserted as an exact ordered vector instead of a broad subset check.

## Changes

- Added `EXPECTED_LAUNCH_CONTRACT_VIOLATIONS` for top-level side-effect flags,
  launch-authority drift, lane/environment drift, release/runbook/tiny-live
  identity drift, accepted-before-audit drift, release readiness drift, runbook
  side-effect drift, tiny-live evidence/review/metric drift, and tiny-live
  decision drift.
- Converted the launch route contract-violation check from
  `issubset(set(data["contract_violations"]))` to an exact ordered list
  assertion.
- Added a local source guard preventing this launch test file from reintroducing
  loose `set(data["contract_violations"])`, `in data["contract_violations"]`,
  or subset checks before the guard.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_launch_status_routes.py --tb=short` — 6 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_launch_status_routes.py --tb=short` — 16 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 143 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_launch_status_routes.py` — PASS.
- Launch no-loose contract violation assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No FastAPI route behavior changed. No connector production code, GUI behavior,
Rust IPC behavior, IBKR contact, IBKR SDK import, socket/client construction,
secret access or serialization, connector runtime, broker session, read-only
probe execution, paper order routing/cancel/replace, release launch,
DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch,
tiny-live/live authorization, Linux runtime sync/restart, destructive DB
cleanup, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because the available tool policy only
permits spawning when the operator explicitly requests subagents/parallel agent
work. This was a narrow source-only test checkpoint verified locally with
focused and broad Stock/ETF Python tests.
