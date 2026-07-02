# PM Report — Stock/ETF Readiness Denied Operations Exact Guard

Date: 2026-07-02
Role: PM(default)
Scope: Source-only/test-only hardening for the FastAPI Stock/ETF readiness route.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens readiness route tests so the displayed
`denied_operations` surface must match the complete ordered Stock/ETF denial
vector instead of proving only two denied operations are present.

## Changes

- Added `EXPECTED_DENIED_OPERATIONS` to
  `test_stock_etf_readiness_routes.py`.
- Replaced loose membership assertions for `denied_operations` with exact
  ordered vector assertions on both IPC fail-closed and readonly fixture paths.
- Extended the local source guard so loose `set(...)`, membership, or subset
  assertions cannot return for `denied_operations`.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_readiness_routes.py --tb=short` — 7 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 144 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_readiness_routes.py` — PASS.
- Readiness denied-operations no-loose assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No FastAPI route behavior changed. No Rust IPC handler behavior, GUI behavior,
connector production code, IBKR contact, IBKR SDK import, socket/client
construction, secret access or serialization, connector runtime, broker session,
read-only probe execution, paper order routing/cancel/replace, release launch,
DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch,
tiny-live/live authorization, Linux runtime sync/restart, destructive DB
cleanup, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because this was a narrow route-test
hardening checkpoint with direct local verification and no runtime or
exchange-facing action.
