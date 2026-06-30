# IBKR Stock/ETF Reference Data Sources Contract Checkpoint

Date: 2026-06-30
Owner: PM
Scope: ADR-0048 / AMD-2026-06-29-01 `stock_etf_cash` Phase 3 source contract
Status: Source checkpoint accepted; no runtime authority

## Summary

新增 `stock_etf_reference_data_sources_v1`，把 corporate-action、FX、fee、
tax/FTT、withholding-treatment 的 source-as-of records 變成可機器驗證的
Phase 3 / scorecard 前置 contract。

The contract validates:

- `asset_lane=stock_etf_cash`, `broker=ibkr`, read-only/paper/shadow-only
  environment.
- Source version 1 and explicit freeze for evidence-clock usage.
- Corporate-action source name, as-of timestamp, raw hash, adjustment-version
  hash, policy hash, and dividend-treatment hash.
- FX source name, as-of timestamp, USD base/quote currency treatment in v1, FX
  snapshot hash, and FX drag model hash.
- Fee schedule source name, as-of timestamp, commission schedule hash,
  exchange/regulatory fee hash, tax/FTT placeholder hash, and withholding-tax
  treatment hash.
- Source artifact hash, Bybit live unchanged proof, and no IBKR contact /
  connector runtime / secret serialization / tiny-live / live authority.

## Code And Contract Changes

- Added Rust source validator:
  `rust/openclaw_types/src/stock_etf_reference_data_sources.rs`.
- Added acceptance tests:
  `rust/openclaw_types/tests/stock_etf_reference_data_sources_acceptance.rs`.
- Added blocked, secret-free template:
  `settings/broker/stock_etf_reference_data_sources.template.toml`.
- Wired `stock_etf_reference_data_sources_v1` into:
  `stock_etf_phase0_manifest`, `stock_etf_phase3_evidence` frozen inputs, and
  `stock_etf_broker_capability_registry` shadow-fill / scorecard gates.
- Updated the Phase 0 contract packet, manifest JSON, ADR-0048, broker settings
  README, governance register addendum, document index, and initiative index.

## Verification

- Focused linked tests:
  `cargo test -p openclaw_types --test stock_etf_reference_data_sources_acceptance --test stock_etf_phase3_evidence_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_phase0_manifest_acceptance`
  passed: 28 tests.
- Full crate:
  `cargo test -p openclaw_types` passed: 35 unit/golden tests, 168
  integration/acceptance tests, 0 doc-tests.
- Targeted `rustfmt --check` for touched Rust files passed.

## Boundary

This checkpoint is source-only. It does not contact IBKR, read or create
secrets, start a connector, ingest market/reference data, start an evidence
clock, route paper orders, write scorecards, apply DB migrations, enable GUI
lane authority, authorize tiny-live/live, or change Bybit live execution
behavior.

The first IBKR contact remains blocked until real secret/topology evidence and
an immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
