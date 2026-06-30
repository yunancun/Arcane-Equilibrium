# PM Checkpoint - IBKR Stock/ETF Route Test Split

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` FastAPI display-only route tests.

## Verdict

`DONE_SOURCE_ONLY_BEHAVIOR_PRESERVED`

This checkpoint is a test-structure refactor only. It splits the overgrown Stock/ETF route test file by endpoint domain and moves shared fake IPC/client fixtures into a helper module. It does not change production code, endpoints, JSON response contracts, GUI behavior, Rust IPC, Bybit runtime behavior, or any IBKR external surface.

## Changes

- Moved shared Stock/ETF route-test setup and fake payload builders to `stock_etf_route_fixtures.py`.
- Split endpoint-specific route tests into:
  - `test_stock_etf_lane_status_routes.py`
  - `test_stock_etf_readiness_routes.py`
  - `test_stock_etf_evidence_status_routes.py`
  - `test_stock_etf_universe_status_routes.py`
  - `test_stock_etf_shadow_status_routes.py`
  - `test_stock_etf_paper_status_routes.py`
- Kept `test_stock_etf_routes.py` focused on route registration, auth, OpenAPI GET-only shape, redirect, and static GUI registration/display-only checks.

## Size Result

- `stock_etf_route_fixtures.py`: `400` lines.
- `test_stock_etf_routes.py`: `144` lines, down from `1736`.
- `test_stock_etf_lane_status_routes.py`: `132` lines.
- `test_stock_etf_readiness_routes.py`: `313` lines.
- `test_stock_etf_evidence_status_routes.py`: `198` lines.
- `test_stock_etf_universe_status_routes.py`: `196` lines.
- `test_stock_etf_shadow_status_routes.py`: `225` lines.
- `test_stock_etf_paper_status_routes.py`: `234` lines.

Every Stock/ETF route-test module is now below the `800` review-attention threshold.

## Verification

- `python3 -m py_compile` on the Stock/ETF route fixture helper, split route tests, and no-write/static guard: PASS.
- `python3 -m pytest -q` on all split Stock/ETF route tests plus `test_stock_etf_python_no_write_static_guard.py`: `42 passed`.
- `git diff --check`: PASS.

## Review Notes

- This is intentionally behavior-preserving. The test count remains `42 passed`, matching the pre-split focused route/static guard suite.
- E2/E4 subagents were not spawned because the current Codex tool policy for this session does not expose repo subagent execution; PM ran focused local regression instead.
- No Linux `trade-core` source sync/restart was performed. Runtime remains intentionally untouched for this source-only checkpoint.

## Boundary

No IBKR API call, healthcheck, secret slot access/creation, connector runtime, paper account snapshot, broker paper attestation, paper order, cancel/replace, fill import, lifecycle writer, DB apply, GUI lane selector authority, tiny-live/live permission, or Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology/session evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
