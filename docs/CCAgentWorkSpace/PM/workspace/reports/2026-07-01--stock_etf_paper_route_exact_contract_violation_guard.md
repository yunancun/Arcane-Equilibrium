# PM Report — Stock/ETF Paper Route Exact Contract-Violation Guard

Date: 2026-07-01
Role: PM(default)
Scope: Source-only/test-only hardening for the Stock/ETF FastAPI paper route.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Python paper route tests so `contract_violations`
are asserted as exact ordered vectors instead of broad subset or membership
checks.

## Changes

- Added `EXPECTED_PAPER_CONTRACT_VIOLATIONS` for top-level side-effect flags,
  DB apply drift, lane/environment drift, Phase2/paper lifecycle flags,
  lifecycle/event-log/request contract drift, lifecycle gate leakage,
  lifecycle identity/hash/redaction lineage, request-contract leakage, and
  reconstructability readiness/manual-review drift.
- Added `EXPECTED_STALE_PAPER_CONTRACT_VIOLATIONS` for the stale lifecycle
  shape regression case.
- Converted the paper route contract-violation checks from
  `issubset(set(data["contract_violations"]))` and membership assertions to
  exact ordered list assertions.
- Added a local source guard preventing this paper test file from reintroducing
  loose `set(data["contract_violations"])`, `in data["contract_violations"]`,
  or subset checks before the guard.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_paper_status_routes.py --tb=short` — 7 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_paper_status_routes.py --tb=short` — 17 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 140 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_paper_status_routes.py` — PASS.
- Paper no-loose contract violation assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No FastAPI route behavior changed. No connector production code, GUI behavior,
Rust IPC behavior, IBKR contact, IBKR SDK import, socket/client construction,
secret access or serialization, connector runtime, broker session, read-only
probe execution, paper order routing/cancel/replace, fill import, lifecycle
writer, DB/evidence/scorecard writer, evidence clock, paper-shadow launch,
tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior
changed.

Sub-agent note: no subagent was spawned because the available tool policy only
permits spawning when the operator explicitly requests subagents/parallel agent
work. This was a narrow source-only test checkpoint verified locally with
focused and broad Stock/ETF Python tests.
