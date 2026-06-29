# IBKR Stock/ETF Broker Capability Registry Contract Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only broker capability registry**
Scope: `broker_capability_registry_v1` for `stock_etf_cash` IBKR read-only / paper / shadow operation boundaries.

## Result

The Phase 0 contract packet now has a machine-checkable Rust source contract for the Stock/ETF broker capability registry:

- `openclaw_types::stock_etf_broker_capability_registry` defines `StockEtfBrokerCapabilityRegistryV1`, operation entries, typed blockers, and verdict output.
- The validator requires the complete operation matrix: health/account/market/contract reads, paper submit/cancel/replace/fill import, shadow signal/fill reconstruction, scorecard derivation, live order denial, margin/short denial, options/CFD denial, and transfer/account-write denial.
- It requires `stock_etf_cash` / IBKR scope, Bybit live execution unchanged, Python broker write authority denied, IBKR live denied, CFD/margin reserved denied, required audit fields, audit event requirement, and source artifact hash requirement.
- Paper write rows must be Rust-owned and carry external gate, paper attestation, scoped authorization, Decision Lease, Guardian, and paper lifecycle gates.
- Denied rows must carry exact typed denials: `ibkr_live_not_authorized`, `stock_etf_cash_only`, `instrument_kind_denied`, and `account_write_denied`.
- It rejects first IBKR contact and serialized secret content in the registry artifact.
- `settings/broker/stock_etf_broker_capability_registry.template.toml` is default BLOCKED and secret-free.

This closes the gap where the broker operation matrix was specified in prose and partly covered by evaluator tests, but not represented as a reusable source artifact for future PM/E2/E4/QA review.

## Dispatch Note

Normal feature flow is `PM -> PA -> E1 -> E2 -> E4 -> QA -> PM`. This checkpoint was handled in the main session because no subagent tool was available in this turn and the change is a narrow source-only contract with no runtime, broker, secret, PG, or deploy surface. PM performed triage, implementation, focused adversarial checks, and regression locally; full role signoff is still required before any effect-capable paper-route implementation.

## Hard Boundary

This checkpoint does not contact IBKR, create a connector, create or read secrets, inspect account ids, route orders, create paper order entry, open sockets, start collectors, apply migrations, write audit rows, start the evidence clock, or authorize:

- IBKR API call or healthcheck
- broker-paper order submission/cancel/replace
- Python broker write authority
- GUI lane authority
- tiny-live/live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_broker_capability_registry.rs rust/openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_broker_capability_registry_acceptance` - 8 passed
- `cargo test -p openclaw_types` - 35 unit/golden + 118 integration passed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable Phase 2 PASS artifact. Any future paper-route implementation still needs external gate PASS, session attestation, paper attestation, scoped authorization, Decision Lease, Guardian, lifecycle idempotency, E2/E4/QA review, and PM/Operator signoff.
