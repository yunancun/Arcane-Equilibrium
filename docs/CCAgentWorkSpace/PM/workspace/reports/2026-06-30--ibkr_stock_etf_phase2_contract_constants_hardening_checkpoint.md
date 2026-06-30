# IBKR Stock/ETF Phase2 Contract Constants Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only contract id constant convergence**
Scope: Phase 0 manifest, broker capability gates, lane-scoped IPC gates, and audit event fixture references.

## Result

The remaining Phase 0 / Phase 2 named contract ids now have shared Rust constants instead of duplicated handwritten strings:

- `asset_lane_taxonomy_v1`
- `phase2_ibkr_external_surface_gate_v1`
- `non_bybit_api_allowlist_v1`
- `ibkr_api_session_topology_v1`
- `ibkr_session_attestation_v1`
- `feature_flag_secret_auth_matrix_v1`
- `ibkr_paper_order_lifecycle_v1`
- `broker_lifecycle_event_log_v1`
- `ibkr_paper_attestation_v1`
- `ibkr_redaction_policy_v1`

The Phase 0 manifest validator, Phase 0 acceptance tests, broker capability registry gates, lane-scoped IPC gates, and asset-lane audit event fixture now consume shared constants where that does not introduce reverse module coupling.

This checkpoint does not change any validation semantics. It reduces contract-id drift risk before later Phase 2 / paper lifecycle hardening work.

## Hard Boundary

This checkpoint did not contact IBKR, inspect secrets, create connectors, start collectors, ingest market/reference data, write scorecards, apply migrations, open Postgres, start the evidence clock, route paper orders, or authorize:

- IBKR API calls or healthchecks
- IBKR connector implementation
- broker-paper order submission, cancel, or replace
- market/reference-data ingestion runtime
- active migration apply
- audit writer/runtime
- GUI lane authority
- release, tiny-live, or live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt` on touched non-root Rust source/test files - pass; crate root `rust/openclaw_types/src/lib.rs` was edited but intentionally not rustfmt-formatted.
- Focused tests: `cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_audit_events_acceptance --test ibkr_phase2_gate_acceptance --test ibkr_phase2_policy_acceptance --test ibkr_paper_lifecycle_acceptance --test ibkr_feature_flag_secret_auth_acceptance` - 63 tests passed
- `cargo test -p openclaw_types` - 35 unit/golden + 188 integration/acceptance passed; 0 doc-tests
- `cargo test -p openclaw_types -- --list` - 35 unit/golden + 188 integration/acceptance listed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. These constants do not authorize connector runtime, evidence-clock start, paper orders, release, tiny-live, or live.
