# IBKR Stock/ETF Phase 2 IPC Pre-Contact Status Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - IPC fixture status only**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow research lane.

## Result

The existing `stock_etf.*` IPC fixture now exposes Phase 2 pre-contact status without adding a connector or new external method:

- `stock_etf.get_lane_status`, `stock_etf.get_readiness`, and stock/ETF paper/shadow fixture responses include a `phase2` object.
- `phase2.external_surface_gate` reports `status=BLOCKED`, `ibkr_contact_allowed=false`, blockers, and `ibkr_call_performed=false`.
- `phase2.policy_prerequisites` reports source policy prerequisite flags from `openclaw_types::ibkr_phase2_policies`.
- `immutable_pass_artifact_present=false`, `first_ibkr_contact_allowed=false`, `connector_enabled=false`, `secret_slot_touched=false`, and `order_routed=false` are explicit in the response.
- No new IPC method was added; method registry remains the same lane-scoped stock/ETF fixture set.

## Hard Boundary

This checkpoint does not authorize:

- IBKR API call, healthcheck, or IBKR Gateway/TWS connection
- IBKR connector implementation
- secret-slot creation or credential write
- broker-paper order submission
- active DB migration apply
- GUI stock/ETF runtime activation
- evidence clock start
- live, tiny-live, margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue. The legacy `submit_paper_order` path still requires the existing paper command channel, while `stock_etf.submit_paper_order` remains an isolated fixture denial.

## Verification

- `cargo test -p openclaw_engine ipc_server::tests::stock_etf` - 4 passed
- `cargo test -p openclaw_engine ipc_server::method_registry::tests::stock_etf_methods_are_registered_as_lane_scoped_fixtures` - 1 passed
- `rustfmt --edition 2021 --check rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs` - pass
- `git diff --check` - pass

Warnings observed are pre-existing Rust test warnings (`async_trait` unused import and `ScriptedSpawn` visibility) and unrelated to this checkpoint.

## Next Gate

Next work remains the immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact process. The first IBKR read-only healthcheck remains blocked until that reviewed artifact exists and records `ibkr_call_performed=false` for the gate itself.
