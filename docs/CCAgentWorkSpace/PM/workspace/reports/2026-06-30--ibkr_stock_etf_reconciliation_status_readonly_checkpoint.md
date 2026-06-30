# PM Checkpoint - IBKR Stock/ETF Reconciliation Status Read-Only Surface

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` Phase 4 display-only paper/shadow reconciliation status surface.

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

This checkpoint adds a read-only reconciliation-status view for the Stock/ETF IBKR lane. It does not start Phase 2 or Phase 3, contact IBKR, read/create secrets, start a connector, route paper/live orders, import fills, run a scorecard writer, apply DB changes, or activate any Bybit runtime behavior.

## Changes

- Rust IPC fixture:
  - Added `stock_etf.get_reconciliation_status`.
  - Registered it in dispatch and method registry as read-only / `IpcSlotRequirement::None`.
  - Returns a blocked `phase3_reconciliation_status_source_fixture` from local paper lifecycle and shadow-fill contract shapes.
  - Preserves `phase3_started=false`, `paper_shadow_reconciliation_started=false`, `scorecard_writer_started=false`, `db_apply_performed=false`, `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, and `bybit_ipc_reused=false`.
- FastAPI:
  - Added authenticated no-store `GET /api/v1/stock-etf/reconciliation-status`.
  - Calls only `stock_etf.get_reconciliation_status` with empty params.
  - Ignores query/header supplied Phase 3, reconciliation, first-contact, and paper/shadow readiness claims.
  - Converts mismatched lane/broker/environment, side effects, contract-id drift, accepted lifecycle/shadow evidence, ids, hashes, divergence, unmatched counts, scorecard writer, and DB apply signals into `contract_violation_blocked`.
- GUI:
  - Added `Reconciliation` summary metric and `Reconciliation Status` panel to `tab-stock-etf.html`.
  - Renders lifecycle/shadow blockers, evidence-id presence, link state, divergence, unmatched counts, scorecard writer, DB apply, and contract violations.
  - Uses only `ocApi(... method: 'GET' ...)`; no forms, direct `fetch`, browser storage authority, secret widgets, or order widgets.
- Contract:
  - `lane_scoped_ipc_v1` now includes `GetReconciliationStatus` as display-only / non-effect-capable.
  - `gui_lane_contract_v1` now requires exact display-only GET `/api/v1/stock-etf/reconciliation-status`.
  - Blocked GUI template was updated with the reconciliation endpoint in disabled GET-only state.

## Verification

- `python3 -m py_compile` on Stock/ETF route, normalizer, fixture, route tests, and static guard: PASS.
- `rustfmt --check --edition 2021` on changed Rust files except `rust/openclaw_types/src/lib.rs`: PASS.
- `git diff --check`: PASS.
- Node inline script parser for `tab-stock-etf.html`: `parsed 7 inline script(s)`.
- `python3 -m pytest -q` on all Stock/ETF route tests plus static no-write guard: `47 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`: `12 passed` in the targeted unit filter; remaining integration targets were filtered with 0 tests and no failures.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance --test stock_etf_lane_scoped_ipc_acceptance`: `17 passed`.

## Review Notes

- The first engine verification failed because the handler arm existed but dispatch/method-registry allowlists had not been extended. PM fixed the registry/dispatch gap and reran the focused Rust/Python/GUI checks green.
- E2/E4 subagents were not spawned because the current Codex tool policy for this session does not expose repo subagent execution; PM ran the focused regression surface locally instead.
- No Linux `trade-core` source sync/restart was performed. Runtime remains intentionally untouched for this source-only checkpoint.

## Boundary

No IBKR API call, healthcheck, secret slot access/creation, connector runtime, paper account snapshot, broker paper attestation, paper order, cancel/replace, fill import, lifecycle writer, scorecard writer, DB apply, GUI lane selector authority, Phase 2 start, Phase 3 start, tiny-live/live permission, or Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology/session evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
