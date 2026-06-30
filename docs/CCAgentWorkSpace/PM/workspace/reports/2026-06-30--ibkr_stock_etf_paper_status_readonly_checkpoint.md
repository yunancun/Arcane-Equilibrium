# PM Checkpoint — IBKR Stock/ETF Paper Status Read-Only Surface

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` Phase 4B display-only paper lifecycle status surface.

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

This checkpoint adds a read-only paper-status view for the Stock/ETF IBKR lane. It does not start Phase 2, contact IBKR, read/create secrets, start a connector, import fills, apply DB changes, or route paper/live orders.

## Changes

- Rust IPC fixture:
  - Added `stock_etf.get_paper_status`.
  - Registered it as read-only / `IpcSlotRequirement::None`.
  - Returns a blocked `phase2_paper_status_source_fixture` from the local `BrokerLifecycleEventLogV1` contract shape.
  - Preserves `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, `bybit_ipc_reused=false`, and `db_apply_performed=false`.
- FastAPI:
  - Added authenticated `GET /api/v1/stock-etf/paper-status`.
  - Calls only `stock_etf.get_paper_status` with empty params.
  - Applies no-store/private cache headers plus `Vary: Authorization`.
  - Ignores query/header supplied Phase 2, paper-order, fill-import, attestation, and first-contact claims.
  - Converts broker ids, accepted lifecycle events, paper order/fill activity, DB apply, side-effect, and authority signals into `contract_violation_blocked`.
- GUI:
  - Added Paper Lifecycle summary metric and `Paper Status` panel to `tab-stock-etf.html`.
  - Shows lifecycle contract state, order/fill id presence, idempotency/reconciliation fields, and reconstructability readiness.
  - Uses only `ocApi(... method: 'GET' ...)`; no forms, direct `fetch`, browser storage authority, secret widgets, or order widgets.
- Contract:
  - `lane_scoped_ipc_v1` now includes `GetPaperStatus` as display-only / non-effect-capable.
  - `gui_lane_contract_v1` now requires six exact display-only GET surfaces:
    `/api/v1/stock-etf/readiness`,
    `/api/v1/stock-etf/lane-status`,
    `/api/v1/stock-etf/evidence-status`,
    `/api/v1/stock-etf/universe-status`,
    `/api/v1/stock-etf/shadow-status`,
    `/api/v1/stock-etf/paper-status`.
  - Blocked GUI template and Phase 0 named contract packet were updated.

## Verification

- `rustfmt --edition 2021` on changed Rust files except `rust/openclaw_types/src/lib.rs`.
- `python3 -m py_compile` on Stock/ETF route and tests.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`: `11 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance --test stock_etf_lane_scoped_ipc_acceptance`: `17 passed`.
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`: `42 passed`.
- Node inline script parser for `tab-stock-etf.html`: `checked 2 inline scripts`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`: PASS, including `35` unit/golden tests, all integration/acceptance tests, and `0` doc-tests.
- `cargo check --manifest-path rust/Cargo.toml --workspace`: PASS.
- `git diff --check`: PASS.

## Review Notes

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py` is now `1550` lines and `test_stock_etf_routes.py` is now `1736` lines. Both remain under the `2000` hard cap, but they are well above the `800` review-attention threshold. I kept this checkpoint cohesive and did not mix in a helper extraction refactor; the next Stock/ETF read surface should first split shared normalizers and test fixtures.
- E2/E4 subagents were not spawned because the current Codex tool policy for this session does not expose repo subagent execution; PM ran the focused regression surface locally instead.
- No Linux `trade-core` source sync/restart was performed. Runtime remains intentionally untouched for this source-only checkpoint.

## Boundary

No IBKR API call, no healthcheck, no secret slot access/creation, no connector runtime, no paper account snapshot, no broker paper attestation, no paper order, no cancel/replace, no fill import, no lifecycle event writer, no DB apply, no GUI lane selector authority, no tiny-live/live, and no Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology/session evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
