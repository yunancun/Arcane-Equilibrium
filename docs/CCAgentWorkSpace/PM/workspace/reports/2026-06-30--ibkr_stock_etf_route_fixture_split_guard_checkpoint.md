# PM Checkpoint - IBKR Stock/ETF Route Fixture Split Guard

日期：2026-06-30
角色：PM(default)
Scope：ADR-0048 `stock_etf_cash` FastAPI display-only route test fixtures.

## Verdict

`DONE_SOURCE_ONLY_BEHAVIOR_PRESERVED`

This checkpoint is a test-fixture structure refactor only. It splits the oversized
Stock/ETF route fixture helper into a same-name package while preserving the
existing import surface for all route tests. It does not change production route
code, endpoints, JSON response contracts, GUI behavior, Rust IPC, IBKR runtime
authority, or Bybit runtime behavior.

## Changes

- Removed the legacy flat fixture helper:
  `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/stock_etf_route_fixtures.py`.
- Added same-name package:
  `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/stock_etf_route_fixtures/`.
- Split fixture responsibilities into:
  - `app.py`
  - `phase2_payloads.py`
  - `phase3_payloads.py`
  - `phase5_payloads.py`
  - `__init__.py`
- Preserved `from stock_etf_route_fixtures import ...` for existing tests through
  explicit re-exports.
- Added `tests/structure/test_stock_etf_route_fixtures_split_static.py` to keep
  the helper split, export surface, and source-only payload boundary from
  drifting.

## Size Result

- Removed flat helper: `1525` lines.
- `__init__.py`: `57` lines.
- `app.py`: `63` lines.
- `phase2_payloads.py`: `482` lines.
- `phase3_payloads.py`: `629` lines.
- `phase5_payloads.py`: `364` lines.

Every route fixture module is now below the `800` review-attention threshold.

## Verification

- Route fixture `py_compile`: PASS.
- Route fixture split static guard: `3 passed`.
- Full Stock/ETF FastAPI/static suite: `105 passed`.
- Focused IBKR timeline + trace-title structure tests: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, IBKR API call, IBKR SDK import, socket/HTTP client,
secret access/creation, connector runtime, read probe execution, paper order,
cancel/replace, fill import, evidence writer, DB apply, evidence clock,
tiny-live/live authority, or Bybit live execution behavior change. First IBKR
contact remains blocked until the relevant Phase 2 external-surface gates pass
with immutable evidence.
