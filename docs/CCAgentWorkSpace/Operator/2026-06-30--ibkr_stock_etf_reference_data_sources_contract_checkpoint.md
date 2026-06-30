# Operator Summary - IBKR Stock/ETF Reference Data Sources Contract

Date: 2026-06-30
Status: Source checkpoint only; runtime still blocked

新增 `stock_etf_reference_data_sources_v1`，讓 future Stock/ETF Phase 3 /
scorecard 所需的 corporate-action、FX、fee、tax/FTT、withholding-treatment
來源可以被 Rust machine-check。

What changed:

- New Rust validator and blocked template for reference-data source-as-of
  records.
- Phase 0 manifest now includes `stock_etf_reference_data_sources_v1`.
- Phase 3 frozen inputs now require a reference-data source contract hash.
- Broker capability shadow-fill and scorecard rows now require the
  reference-data source gate.

Verification so far:

- Focused linked tests passed: 28 tests.
- Full `cargo test -p openclaw_types` passed: 35 unit/golden + 168
  integration/acceptance + 0 doc-tests.
- Targeted Rust format check passed.

Still not authorized:

- No IBKR contact or healthcheck.
- No secret read/create/serialization.
- No connector runtime.
- No collector or market/reference data ingestion.
- No paper order routing.
- No evidence clock or scorecard writer.
- No GUI lane authority.
- No tiny-live/live.
- No Bybit live execution behavior change.

Next hard blocker is unchanged: real secret/topology evidence plus immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact before first IBKR contact.
