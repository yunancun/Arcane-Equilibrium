# PM Checkpoint - IBKR Stock/ETF Status Normalizer Split

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` FastAPI display-only status surfaces.

## Verdict

`DONE_SOURCE_ONLY_BEHAVIOR_PRESERVED`

This checkpoint is a structural refactor only. It splits the overgrown Stock/ETF FastAPI status normalizers out of the route layer and into small domain modules. It does not add endpoints, change response contracts, start Phase 2/3, contact IBKR, read/create secrets, start a connector, route paper/live orders, apply DB changes, or alter Bybit runtime behavior.

## Changes

- `stock_etf_routes.py` now contains only:
  - authenticated GET route handlers,
  - no-store/private response-header application,
  - IPC client lookup/query helpers,
  - method names for the six read-only Stock/ETF IPC fixtures.
- Fail-closed constants, contract ids, no-store headers, primitive coercion helpers, and shared API allowlist validation moved to `stock_etf_status_common.py`.
- Domain-specific status shaping moved to:
  - `stock_etf_readiness_normalizers.py`
  - `stock_etf_evidence_normalizers.py`
  - `stock_etf_universe_normalizers.py`
  - `stock_etf_shadow_normalizers.py`
  - `stock_etf_paper_normalizers.py`
- `stock_etf_status_normalizers.py` remains as a thin aggregation import point for route stability.

## Size Result

- `stock_etf_routes.py`: `1550` lines before this checkpoint, `257` lines after.
- `stock_etf_status_normalizers.py`: `13` lines.
- `stock_etf_status_common.py`: `331` lines.
- `stock_etf_readiness_normalizers.py`: `169` lines.
- `stock_etf_evidence_normalizers.py`: `286` lines.
- `stock_etf_universe_normalizers.py`: `162` lines.
- `stock_etf_shadow_normalizers.py`: `229` lines.
- `stock_etf_paper_normalizers.py`: `234` lines.

Every new Stock/ETF status normalizer module is below the `800` review-attention threshold.

## Verification

- `python3 -m py_compile` on the Stock/ETF route, all new normalizer modules, and focused Stock/ETF tests: PASS.
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `42 passed`.
- `git diff --check`: PASS.

## Review Notes

- `test_stock_etf_routes.py` remains `1736` lines. It is below the `2000` hard cap but above the `800` review-attention threshold. The next Python route-test touch should extract shared Stock/ETF fixtures/assertion helpers instead of adding more inline cases.
- E2/E4 subagents were not spawned because the current Codex tool policy for this session does not expose repo subagent execution; PM ran focused local regression instead.
- No Linux `trade-core` source sync/restart was performed. Runtime remains intentionally untouched for this source-only checkpoint.

## Boundary

No new IBKR API call, healthcheck, secret slot access/creation, connector runtime, paper account snapshot, broker paper attestation, paper order, cancel/replace, fill import, lifecycle writer, DB apply, GUI lane selector authority, tiny-live/live permission, or Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology/session evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
