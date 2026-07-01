# PM Report — Stock/ETF IBKR Connector Preview Exact Blocker Guard

Date: 2026-07-01
Role: PM(default)
Scope: Source-only/test-only hardening for the inert Python IBKR connector skeleton.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Python IBKR connector skeleton preview tests so preview blockers are asserted as exact ordered vectors instead of loose membership or subset checks.

## Changes

- Added `EXPECTED_DEFAULT_BLOCKERS` for every inert connector preview payload:
  readiness, connection plan, account snapshot, market data, contract details, session attestation, readonly result-import preview, paper lifecycle, fill import, paper attestation, and fixtures.
- Converted risky endpoint config coverage to exact ordered blocker-vector assertions, preserving the validator emit order from `IbkrReadOnlyEndpointConfig.validate_source_boundary()`.
- Added a local source guard preventing the connector skeleton test from reintroducing loose payload blocker membership/subset checks.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py --tb=short` — 11 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_readiness_routes.py --tb=short` — 16 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 127 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py` — PASS.
- Connector no-loose blocker scan — PASS.
- `git diff --check` — PASS.

## Boundary

No connector production code changed. No FastAPI route behavior, GUI behavior, Rust IPC behavior, IBKR contact, IBKR SDK import, socket/client construction, secret access or serialization, connector runtime, broker session, read-only probe execution, paper order routing, fill import, DB/evidence/scorecard writer, evidence clock, paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because the available tool policy only permits spawning when the operator explicitly requests subagents/parallel agent work. This was a narrow source-only test checkpoint verified locally with focused and broad Stock/ETF Python tests.
