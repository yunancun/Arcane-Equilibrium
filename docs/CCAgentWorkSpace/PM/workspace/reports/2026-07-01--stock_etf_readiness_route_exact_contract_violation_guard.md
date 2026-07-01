# PM Report — Stock/ETF Readiness Route Exact Contract-Violation Guard

Date: 2026-07-01
Role: PM(default)
Scope: Source-only/test-only hardening for the Stock/ETF FastAPI readiness route.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Python readiness route tests so
`contract_violations` are asserted as exact ordered vectors instead of broad
`set(...)` or membership checks.

## Changes

- Added ordered expected vectors for readiness aggregate side-effect
  violations, missing API allowlist contract violations, and boolean
  `source_version` normalization violations.
- Converted the readiness route tests from loose membership/set checks to exact
  `data["contract_violations"] == ...` assertions.
- Added a local source guard preventing this readiness test file from
  reintroducing loose `set(data["contract_violations"])`,
  `in data["contract_violations"]`, or subset checks before the guard.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_readiness_routes.py --tb=short` — 7 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_readiness_routes.py --tb=short` — 17 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 128 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_readiness_routes.py` — PASS.
- Readiness no-loose contract violation assertion scan — PASS.
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
