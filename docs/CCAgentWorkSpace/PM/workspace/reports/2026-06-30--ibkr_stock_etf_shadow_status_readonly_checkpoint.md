# PM Checkpoint — IBKR Stock/ETF Shadow Status Read-Only Surface

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` Phase 4B display-only shadow status surface.

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

This checkpoint adds a read-only shadow-status view for the Stock/ETF IBKR lane. It does not start Phase 2/3, contact IBKR, read/create secrets, start a connector/collector, emit shadow signals, generate shadow fills, apply DB changes, write scorecards, or route paper/live orders.

## Changes

- Rust IPC fixture:
  - Added `stock_etf.get_shadow_status`.
  - Registered it as read-only / `IpcSlotRequirement::None`.
  - Returns a blocked `phase3_shadow_status_source_fixture` from local `StockShadowFillModelV1` and `StockEtfStrategyHypothesisV1` contract shapes.
  - Preserves `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, and `bybit_ipc_reused=false`.
- FastAPI:
  - Added authenticated `GET /api/v1/stock-etf/shadow-status`.
  - Calls only `stock_etf.get_shadow_status` with empty params.
  - Applies no-store/private cache headers plus `Vary: Authorization`.
  - Ignores query/header supplied Phase 3, shadow-fill, scorecard, DB, and first-contact claims.
  - Converts side-effect and authority signals into `contract_violation_blocked`.
- GUI:
  - Added Shadow summary metric and `Shadow Status` panel to `tab-stock-etf.html`.
  - Shows synthetic-shadow separation, paper/live fill links, strategy hypothesis state, profitability claims, and live/tiny-live authority claims.
  - Uses only `ocApi(... method: 'GET' ...)`; no forms, direct `fetch`, browser storage authority, or order widgets.
- Contract:
  - `gui_lane_contract_v1` now requires five exact display-only GET surfaces:
    `/api/v1/stock-etf/readiness`,
    `/api/v1/stock-etf/lane-status`,
    `/api/v1/stock-etf/evidence-status`,
    `/api/v1/stock-etf/universe-status`,
    `/api/v1/stock-etf/shadow-status`.
  - Blocked template and Phase 0 named contract packet were updated.

## Verification

- `rustfmt --edition 2021` on changed Rust files except `rust/openclaw_types/src/lib.rs`.
- `python3 -m py_compile` on Stock/ETF route and tests.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`: `10 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance`: `9 passed`.
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `37 passed`.
- Node inline script parser for `tab-stock-etf.html`: `checked 2 inline scripts`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`: `35` unit/golden + `198` integration/acceptance + `0` doc-tests.
- `git diff --check`: PASS.

## Review Notes

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py` is now `1263` lines. This is below the `2000` hard cap but above the `800` review-attention threshold. I did not split it in this checkpoint to avoid mixing a route-normalizer refactor into a source-only read-surface change. The next similar Stock/ETF endpoint should first extract shared normalizer/test helpers.
- E2/E4 subagents were not spawned because the current Codex tool policy for this session does not expose repo subagent execution; PM ran the focused regression surface locally instead. No Linux `trade-core` source sync/restart was performed.

## Boundary

No IBKR API call, no healthcheck, no secret slot access/creation, no connector runtime, no market-data collector, no shadow collector, no shadow signal emission, no shadow fill generation, no evidence clock runtime, no scorecard writer, no DB apply, no paper order, no fill import, no GUI lane selector authority, no tiny-live/live, and no Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
