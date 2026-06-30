# IBKR Stock/ETF Market Data Provenance Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only market-data provenance hardening**
Scope: `stock_market_data_provenance_v1` identity/source-version gate for Stock/ETF IBKR paper/shadow market-data facts.

## Result

The market-data provenance source contract is now covered by the exact-id/source-version hardening pattern:

- `StockMarketDataProvenanceV1` requires exact `contract_id == stock_market_data_provenance_v1`.
- The contract requires `source_version == 1`; default and blocked template posture remains `source_version = 0`.
- Regression coverage rejects fixture-like contract ids and wrong source versions.
- The Phase 0 manifest validator now consumes the shared `STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID` constant instead of a handwritten string.
- The blocked template remains parseable, secret-free, and non-authoritative.
- The Phase 0 packet spec and broker settings README now document the exact contract-id/source-version requirement.

This hardening closes the gap where market-data provenance could carry the right lane/broker/source hash shape but not prove the current named source version.

## Hard Boundary

This checkpoint did not contact IBKR, inspect secrets, create connectors, start collectors, ingest market data, write scorecards, apply migrations, open Postgres, start the evidence clock, route paper orders, or authorize:

- IBKR API calls or healthchecks
- IBKR connector implementation
- broker-paper order submission, cancel, or replace
- market-data ingestion runtime
- active migration apply
- audit writer/runtime
- GUI lane authority
- release, tiny-live, or live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/tests/stock_etf_phase3_evidence_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance --test stock_etf_phase0_manifest_acceptance` - 13 Phase3 evidence tests + 6 Phase0 manifest tests passed
- `cargo test -p openclaw_types` - 35 unit/golden + 188 integration/acceptance passed; 0 doc-tests
- `cargo test -p openclaw_types -- --list` - 35 unit/golden + 188 integration/acceptance listed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. Market-data provenance remains source-only; it does not authorize ingestion, connector runtime, collector start, evidence-clock start, scorecard writing, paper orders, release, tiny-live, or live.
