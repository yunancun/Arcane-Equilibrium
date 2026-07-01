# PM Report — Stock/ETF Release Packet Route Exact Contract-Violation Guard

Date: 2026-07-01
Role: PM(default)
Scope: Source-only/test-only hardening for the Stock/ETF FastAPI release-packet route.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Python release-packet route test so
`contract_violations` are asserted as an exact ordered vector instead of a broad
subset check.

## Changes

- Added `EXPECTED_RELEASE_PACKET_CONTRACT_VIOLATIONS` for top-level
  side-effect flags, launch-authority drift, lane/environment drift, release
  packet identity/acceptance drift, reviewer-role drift, evidence/hash/log
  coverage drift, migration evidence drift, manifest-hash drift, kill-disable
  cleanup proof drift, and destructive cleanup requests.
- Converted the release-packet route contract-violation check from
  `issubset(set(data["contract_violations"]))` to an exact ordered list
  assertion.
- Added a local source guard preventing this release-packet test file from
  reintroducing loose `set(data["contract_violations"])`,
  `in data["contract_violations"]`, or subset checks before the guard.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_release_packet_status_routes.py --tb=short` — 5 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_release_packet_status_routes.py --tb=short` — 15 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 142 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_release_packet_status_routes.py` — PASS.
- Release-packet no-loose contract violation assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No FastAPI route behavior changed. No connector production code, GUI behavior,
Rust IPC behavior, IBKR contact, IBKR SDK import, socket/client construction,
secret access or serialization, connector runtime, broker session, read-only
probe execution, paper order routing/cancel/replace, release launch, DB/evidence
writer, scorecard writer, evidence clock, paper-shadow launch, tiny-live/live
authorization, Linux runtime sync/restart, destructive DB cleanup, or Bybit
behavior changed.

Sub-agent note: no subagent was spawned because the available tool policy only
permits spawning when the operator explicitly requests subagents/parallel agent
work. This was a narrow source-only test checkpoint verified locally with
focused and broad Stock/ETF Python tests.
