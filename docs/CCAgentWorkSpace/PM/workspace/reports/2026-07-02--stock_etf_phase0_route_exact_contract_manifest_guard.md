# PM Report — Stock/ETF Phase0 Route Exact Contract Manifest Guard

Date: 2026-07-02
Role: PM(default)
Scope: Source-only/test-only hardening for the FastAPI Stock/ETF Phase0 status route.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Phase0 route test so the accepted API `contracts`
surface must match the complete ordered 36-item Phase0 contract manifest rather
than only proving a few required contract IDs are present.

## Changes

- Added `EXPECTED_PHASE0_CONTRACTS` to
  `test_stock_etf_phase0_status_routes.py`.
- Replaced Phase0 accepted-route contract membership assertions with exact
  `data["contracts"] == EXPECTED_PHASE0_CONTRACTS` and tied
  `contract_count` to the expected vector length.
- Extended the local source guard so loose `set(...)`, membership, or subset
  assertions cannot return for either `contract_violations` or `contracts`.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_phase0_status_routes.py --tb=short` — 5 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 144 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_phase0_status_routes.py` — PASS.
- Phase0 no-loose contract/contracts assertion scan — PASS.
- Changed-file `git diff --check` — PASS.

## Boundary

No FastAPI route behavior changed. No Rust IPC handler behavior, GUI behavior,
connector production code, IBKR contact, IBKR SDK import, socket/client
construction, secret access or serialization, connector runtime, broker session,
read-only probe execution, paper order routing/cancel/replace, release launch,
DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch,
tiny-live/live authorization, Linux runtime sync/restart, destructive DB
cleanup, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because the available tool policy only
permits spawning when the operator explicitly requests subagents/parallel agent
work. This was a narrow FastAPI route test hardening checkpoint verified locally
with focused and broad Stock/ETF Python tests.
