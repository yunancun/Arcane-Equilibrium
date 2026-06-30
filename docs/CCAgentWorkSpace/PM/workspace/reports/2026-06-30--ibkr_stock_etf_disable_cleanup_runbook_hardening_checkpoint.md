# IBKR Stock/ETF Disable Cleanup Runbook Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only disable/cleanup runbook hardening**
Scope: `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` identity/source-version gate for the Stock/ETF IBKR paper/shadow shutdown evidence contract.

## Result

The disable/cleanup runbook source contract is now fail-closed on both artifact identity and source version:

- `StockEtfDisableCleanupRunbookV1` requires exact `runbook_id == stock_etf_kill_switch_and_disable_cleanup_runbook_v1`.
- The runbook now requires `source_version == 1`; default and blocked template posture remains `source_version = 0`.
- `StockEtfDisableCleanupBlocker::SourceVersionMismatch` rejects stale, fixture-like, or unsigned runbook artifacts.
- The Phase 0 manifest validator now consumes the shared `STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID` constant instead of a handwritten string.
- The blocked template remains parseable, secret-free, and non-authoritative.
- The Phase 0 packet spec and broker settings README now document the exact runbook-id/source-version requirement.

This hardening closes the gap where a shutdown/cleanup artifact could present valid proof shape but not prove the current named source version.

## Hard Boundary

This checkpoint did not stop services, read environment variables, mutate DB state, delete or truncate data, inspect secrets, create secret slots, contact IBKR, start connectors, route paper orders, start collectors, start the evidence clock, or authorize:

- IBKR API calls or healthchecks
- IBKR connector implementation
- broker-paper order submission, cancel, or replace
- destructive rollback/cleanup
- active migration apply
- audit writer/runtime
- GUI lane authority
- release, tiny-live, or live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_disable_cleanup_runbook.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/tests/stock_etf_disable_cleanup_runbook_acceptance.rs rust/openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_disable_cleanup_runbook_acceptance --test stock_etf_phase0_manifest_acceptance` - 7 disable/cleanup tests + 6 Phase0 manifest tests passed
- `cargo test -p openclaw_types` - 35 unit/golden + 186 integration/acceptance passed; 0 doc-tests
- `cargo test -p openclaw_types -- --list` - 35 unit/golden + 186 integration/acceptance listed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. Disable/cleanup evidence remains source-only; it does not authorize runtime shutdown, DB cleanup, paper/shadow launch, release, tiny-live, or live.
