# IBKR Stock/ETF Reference Data Sources Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only reference-data contract hardening**
Scope: `stock_etf_reference_data_sources_v1` identity/source-version gate for corporate-action, FX, fee, and tax/FTT source-as-of records.

## Result

The reference-data source contract is now aligned with the exact-id/source-version hardening pattern:

- `StockEtfReferenceDataSourcesV1` requires exact `contract_id == stock_etf_reference_data_sources_v1`.
- The contract requires `source_version == 1`; default and blocked template posture remains `source_version = 0`.
- The blocker is now explicit: `StockEtfReferenceDataSourcesBlocker::SourceVersionMismatch`.
- Regression coverage rejects fixture-like contract ids and wrong source versions.
- The Phase 0 manifest validator now consumes the shared `STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID` constant instead of a handwritten string.
- The blocked template remains parseable, secret-free, and non-authoritative.
- The Phase 0 packet spec and broker settings README now document the exact contract-id/source-version requirement.

This hardening closes the gap where a reference-data artifact could satisfy the corporate-action/FX/fee/tax evidence shape but not prove the current named source version.

## Hard Boundary

This checkpoint did not contact IBKR, inspect secrets, create connectors, ingest market/reference data, write scorecards, apply migrations, open Postgres, start collectors, start the evidence clock, route paper orders, or authorize:

- IBKR API calls or healthchecks
- IBKR connector implementation
- broker-paper order submission, cancel, or replace
- reference-data ingestion runtime
- active migration apply
- audit writer/runtime
- GUI lane authority
- release, tiny-live, or live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_reference_data_sources.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/tests/stock_etf_reference_data_sources_acceptance.rs rust/openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_reference_data_sources_acceptance --test stock_etf_phase0_manifest_acceptance` - 6 reference-data tests + 6 Phase0 manifest tests passed
- `cargo test -p openclaw_types` - 35 unit/golden + 187 integration/acceptance passed; 0 doc-tests
- `cargo test -p openclaw_types -- --list` - 35 unit/golden + 187 integration/acceptance listed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. Reference-data contracts remain source-only; they do not authorize ingestion, connector runtime, evidence-clock start, scorecard writing, paper orders, release, tiny-live, or live.
