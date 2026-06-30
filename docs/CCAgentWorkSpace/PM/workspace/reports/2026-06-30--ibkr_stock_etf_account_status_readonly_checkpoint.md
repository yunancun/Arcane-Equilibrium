# PM Checkpoint - IBKR Stock/ETF Account Status Read-Only Surface

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` Phase 4 display-only IBKR account/connector status surface.

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

This checkpoint adds a read-only account/connector-status view for the Stock/ETF IBKR lane. It does not start Phase 2, contact IBKR, read/create secrets, start a connector, request an account snapshot, route paper/live orders, import fills, apply DB changes, or activate any Bybit runtime behavior.

## Changes

- Rust IPC fixture:
  - Added `stock_etf.get_account_status`.
  - Registered it in dispatch and method registry as read-only / `IpcSlotRequirement::None`.
  - Returns a blocked `phase2_account_status_source_fixture` from local account cash-ledger, session-attestation, and paper-attestation policy shapes.
  - Preserves `phase2_started=false`, `account_snapshot_present=false`, `portfolio_positions_snapshot_present=false`, `cash_ledger_present=false`, `session_attestation_present=false`, `connector_runtime_started=false`, `gateway_socket_open=false`, `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, `bybit_ipc_reused=false`, and `db_apply_performed=false`.
- FastAPI:
  - Added authenticated no-store `GET /api/v1/stock-etf/account-status`.
  - Calls only `stock_etf.get_account_status` with empty params.
  - Ignores query/header supplied Phase 2, account snapshot, session, and first-contact claims.
  - Fail-closes IPC unavailable/errors to `degraded` and converts real IPC payload side effects, account/session hash presence, live fingerprint signals, contract drift, connector runtime, and DB apply into `contract_violation_blocked`.
- GUI:
  - Added `IBKR Account` summary metric and `Account / Connector Status` panel to `tab-stock-etf.html`.
  - Renders account snapshot, session attestation, paper-attestation policy, connector/socket flags, and blockers.
  - Uses only `ocApi(... method: 'GET' ...)`; no forms, direct `fetch`, browser storage authority, secret widgets, or order widgets.
- Contract:
  - `lane_scoped_ipc_v1` now includes `GetAccountStatus` as display-only / non-effect-capable.
  - `gui_lane_contract_v1` now requires exact display-only GET `/api/v1/stock-etf/account-status`.
  - Blocked GUI template was updated with the account-status endpoint in disabled GET-only state.

## Verification

- `python3 -m py_compile` on touched Stock/ETF route, normalizer, fixture, route tests, and static guard: PASS.
- `rustfmt --check --edition 2021` on changed Rust files except `rust/openclaw_types/src/lib.rs`: PASS.
- `git diff --check`: PASS.
- Node inline script parser for `tab-stock-etf.html`: PASS.
- `python3 -m pytest` on all Stock/ETF route tests plus static no-write guard: `52 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`: `13 passed` in the targeted unit filter; remaining integration targets were filtered with 0 tests and no failures.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance --test stock_etf_lane_scoped_ipc_acceptance`: `17 passed`.

## Review Notes

- The first Python route verification caught an IPC-down normalization issue: account fallback was being reclassified as `contract_violation_blocked`. PM fixed it so IPC unavailable remains degraded/fail-closed while real IPC payload violations still block.
- E2/E4 subagents were not spawned because the current Codex tool policy for this session does not expose repo subagent execution; PM ran the focused regression surface locally instead.
- No Linux `trade-core` source sync/restart was performed. Runtime remains intentionally untouched for this source-only checkpoint.

## Boundary

No IBKR API call, healthcheck, secret slot access/creation, connector runtime, account snapshot, portfolio snapshot, cash ledger retrieval, broker paper attestation, paper order, cancel/replace, fill import, lifecycle writer, scorecard writer, DB apply, GUI lane selector authority, Phase 2 start, Phase 3 start, tiny-live/live permission, or Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology/session evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
