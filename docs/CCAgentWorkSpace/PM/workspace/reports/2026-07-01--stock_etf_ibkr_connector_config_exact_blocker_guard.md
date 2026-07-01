# PM Report — Stock/ETF IBKR Connector Config Exact Blocker Guard

Date: 2026-07-01
Role: PM(default)
Scope: Source-only/test-only hardening for the inert IBKR connector skeleton tests.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint tightens the Python connector skeleton config test so risky
source-boundary blockers are asserted as an exact ordered vector instead of a
set/subset check.

## Changes

- Converted `IbkrReadOnlyEndpointConfig.validate_source_boundary()` risky config
  coverage from `set(...).issubset(...)` to exact ordered
  `RISKY_CONFIG_BLOCKERS` assertion.
- Added a local source guard preventing this connector skeleton test file from
  reintroducing `issubset(blockers)` or
  `set(config.validate_source_boundary())` before the guard.

## Verification

- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py --tb=short` — 12 passed.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py --tb=short` — 144 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py` — PASS.
- Connector config no-loose blocker assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No connector production code changed. No FastAPI route behavior, GUI behavior,
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
