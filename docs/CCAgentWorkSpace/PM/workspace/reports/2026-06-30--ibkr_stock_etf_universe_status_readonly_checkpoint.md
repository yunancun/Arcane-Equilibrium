# PM Checkpoint — IBKR Stock/ETF Universe Status Read-Only Surface

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` Phase 4B display-only universe status surface.

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

This checkpoint adds a read-only universe-status view for the Stock/ETF IBKR lane. It does not start Phase 2/3, does not contact IBKR, does not read/create secrets, does not start a connector or collector, does not apply DB changes, and does not route paper/live orders.

## Changes

- Rust IPC fixture:
  - Added `stock_etf.get_universe_status`.
  - Registered it as read-only / `IpcSlotRequirement::None`.
  - Returns a blocked `phase3_universe_status_source_fixture` from local `StockEtfPitUniverseV1` contract shape.
  - Preserves `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, and `bybit_ipc_reused=false`.
- FastAPI:
  - Added authenticated `GET /api/v1/stock-etf/universe-status`.
  - Calls only `stock_etf.get_universe_status` with empty params.
  - Applies no-store/private cache headers plus `Vary: Authorization`.
  - Ignores query/header supplied lane, Phase 3, collector, DB, and first-contact claims.
  - Converts side-effect signals into `contract_violation_blocked`.
- GUI:
  - Added Universe summary metric and `Universe Status` panel to `tab-stock-etf.html`.
  - Uses only `ocApi(... method: 'GET' ...)`; no forms, direct `fetch`, browser storage authority, or order widgets.
- Contract:
  - `gui_lane_contract_v1` now requires four exact display-only GET surfaces:
    `/api/v1/stock-etf/readiness`,
    `/api/v1/stock-etf/lane-status`,
    `/api/v1/stock-etf/evidence-status`,
    `/api/v1/stock-etf/universe-status`.
  - Blocked template and Phase 0 named contract packet were updated.

## Verification

- `rustfmt --edition 2021` on changed Rust files except `rust/openclaw_types/src/lib.rs`.
- `python3 -m py_compile` on Stock/ETF route and tests.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`: `9 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance`: `9 passed`.
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `32 passed`.
- Node inline script parser for `tab-stock-etf.html`: `checked 2 inline scripts`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`: `35` unit/golden + `198` integration/acceptance + `0` doc-tests.
- `git diff --check`: PASS.

## Role Chain Note

This was handled as a PM-local source-only checkpoint. E2/E4 subagents were not spawned because the current Codex tool policy for this session does not expose repo subagent execution; PM ran the focused regression surface locally instead. No Linux `trade-core` source sync/restart was performed.

## Boundary

No IBKR API call, no healthcheck, no secret slot access/creation, no connector runtime, no market-data collector, no evidence clock runtime, no scorecard writer, no DB apply, no paper order, no fill import, no GUI lane selector authority, no tiny-live/live, and no Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
