# Operator Brief — IBKR Stock/ETF Instrument Identity Contract

日期：2026-06-30
結論：source-only checkpoint complete；不授權 IBKR contact。

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

PM 新增 `instrument_identity_contract_v1`，把 future IBKR
Stock/ETF/Cash point-in-time identity 變成 machine-checkable contract。

## What This Adds

- Rust validator: `StockEtfInstrumentIdentityV1`
- Blocked template: `settings/broker/stock_etf_instrument_identity.template.toml`
- Acceptance coverage for default-denied posture, accepted PIT fixture,
  venue/currency/tradability/PRIIPs/hash blockers, contact/secret blockers,
  and template parsing.
- Phase 0 manifest now explicitly lists `instrument_identity_contract_v1`。

## What It Blocks

The validator rejects crypto/CFD instruments, unknown venues, cash/noncash venue
mismatch, non-USD v1 currency, untradable/halted instruments, blocked PRIIPs KID
state, missing PIT/hash/calendar/fractional-policy evidence, prior IBKR contact,
and serialized secret content.

## Boundary

No IBKR API contact occurred. No contract-details call, market-data subscription,
secret read, connector runtime, paper order, DB migration/apply, evidence-clock
start, GUI lane authority, release approval, tiny-live, or live authority is
granted.

Bybit remains the only active live execution venue. First IBKR contact remains
blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
