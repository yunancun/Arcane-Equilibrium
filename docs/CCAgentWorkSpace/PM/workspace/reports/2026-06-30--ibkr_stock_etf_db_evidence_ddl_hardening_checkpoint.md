# IBKR Stock/ETF DB Evidence DDL Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only DB DDL contract hardening**
Scope: `stock_etf_db_evidence_ddl_v1` identity/source-version gate for `stock_etf_cash` paper/shadow evidence storage.

## Result

The DB evidence DDL source contract is now fail-closed on both artifact identity and source version:

- `StockEtfDbEvidenceDdlContractV1` requires exact `contract_id == stock_etf_db_evidence_ddl_v1`.
- The contract now requires `source_version == 1`; default and blocked template posture remains `source_version = 0`.
- `StockEtfDbEvidenceDdlBlocker::SourceVersionMismatch` rejects stale, fixture-like, or unsigned DB DDL contract artifacts.
- The Phase 0 manifest validator now consumes the shared `STOCK_ETF_DB_EVIDENCE_CONTRACT_ID` constant instead of a handwritten string.
- The blocked template remains parseable, secret-free, and non-authoritative.
- The Phase 0 packet spec and broker settings README now document the exact contract-id/source-version requirement.

This hardening closes the gap where a DB evidence DDL artifact could present the right source-only shape but not prove the current named source version.

## Hard Boundary

This checkpoint did not copy SQL into `sql/migrations/`, open Postgres, run PG dry-run, register sqlx migrations, apply DDL, write PG, inspect secrets, contact IBKR, start collectors, start the evidence clock, or authorize:

- IBKR API calls or healthchecks
- IBKR connector implementation
- broker-paper order submission, cancel, or replace
- active migration apply
- audit writer/runtime
- GUI lane authority
- tiny-live/live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_db_evidence_ddl.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/tests/stock_etf_db_evidence_ddl_acceptance.rs rust/openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_db_evidence_ddl_acceptance --test stock_etf_phase0_manifest_acceptance` - 8 DB DDL tests + 6 Phase0 manifest tests passed
- `cargo test -p openclaw_types` - 35 unit/golden + 185 integration/acceptance passed; 0 doc-tests
- `cargo test -p openclaw_types -- --list` - 35 unit/golden + 185 integration/acceptance listed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. DB migration apply remains separately blocked by E2/E4 review, Linux PG dry-run, idempotency double-apply proof, and explicit PM/Operator migration authorization.
