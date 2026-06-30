# IBKR Stock/ETF Paper Lifecycle Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only paper lifecycle hardening**
Scope: `ibkr_paper_order_lifecycle_v1` and `broker_lifecycle_event_log_v1` identity/source-version gates for paper lifecycle evidence.

## Result

The paper lifecycle event source contract is now fail-closed on both named contract identities and source version:

- `BrokerLifecycleEventLogV1` requires exact `lifecycle_contract_id == ibkr_paper_order_lifecycle_v1`.
- `BrokerLifecycleEventLogV1` requires exact `event_log_contract_id == broker_lifecycle_event_log_v1`.
- The event evidence now requires `source_version == 1`; default and blocked template posture remains `source_version = 0`.
- New typed blockers reject stale, fixture-like, or unsigned lifecycle/event-log artifacts.
- The blocked template remains parseable, secret-free, and non-authoritative.
- The Phase 0 packet spec and broker settings README now document the exact lifecycle/event-log/source-version requirement.

This hardening closes the gap where paper lifecycle evidence could validate state transitions and hashes but not prove the current named lifecycle/event-log source contracts.

## Hard Boundary

This checkpoint did not contact IBKR, inspect secrets, create connectors, route paper orders, cancel/replace orders, import fills, start collectors, write audit rows, apply migrations, open Postgres, start the evidence clock, or authorize:

- IBKR API calls or healthchecks
- IBKR connector implementation
- broker-paper order submission, cancel, replace, or fill import
- active migration apply
- audit writer/runtime
- GUI lane authority
- release, tiny-live, or live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/ibkr_paper_lifecycle.rs rust/openclaw_types/tests/ibkr_paper_lifecycle_acceptance.rs` - pass
- `cargo test -p openclaw_types --test ibkr_paper_lifecycle_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance` - 32 tests passed
- `cargo test -p openclaw_types` - 35 unit/golden + 189 integration/acceptance passed; 0 doc-tests
- `cargo test -p openclaw_types -- --list` - 35 unit/golden + 189 integration/acceptance listed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. Paper lifecycle evidence remains source-only; it does not authorize connector runtime, IPC runtime, paper orders, fill import, evidence-clock start, release, tiny-live, or live.
