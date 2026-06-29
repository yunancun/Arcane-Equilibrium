# IBKR Stock/ETF GUI Lane Contract Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only GUI lane contract**
Scope: `gui_lane_contract_v1` for `stock_etf_cash` display-only readiness.

## Result

The Phase 0 contract packet now has a machine-checkable Rust source contract for the Stock/ETF IBKR GUI lane boundary:

- `openclaw_types::stock_etf_gui_lane_contract` defines `StockEtfGuiLaneContractV1`, typed blockers, and verdict output.
- The validator requires default displayed lane `crypto_perp`, GET-only `/api/v1/stock-etf/readiness`, display-only semantics, client lane state treated as untrusted, and denied localStorage/query-param/hidden-field authority.
- It rejects POST routes, order widgets, secret widgets, IBKR contact on render, visible paper-order entry, missing stock-live disabled display, and CFD surfaces that are not hidden or fail-closed.
- It requires route/cache/auth partition evidence, stale-cache cross-lane denial, existing crypto tab regression evidence, Decision Lease/risk regression evidence, source/test hashes, and explicit denied effect operations.
- It rejects any artifact that records `ibkr_contact_performed=true` or `secret_content_serialized=true`.
- `settings/broker/stock_etf_gui_lane_contract.template.toml` is default BLOCKED and secret-free.

This closes the gap between the display-only Phase 4 GUI slice and a reusable source artifact that future PM/E2/E4/QA review can validate before any fuller GUI view or lane selector discussion.

## Hard Boundary

This checkpoint does not serve pages, change runtime routes, contact IBKR, create or read secret slots, start IB Gateway/TWS, open sockets, route orders, create paper order entry, authorize lane selection, start collectors, start the evidence clock, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission/cancel/replace
- GUI POST/write route
- GUI lane authority
- tiny-live/live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_gui_lane_contract.rs rust/openclaw_types/tests/stock_etf_gui_lane_contract_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_gui_lane_contract_acceptance` - 7 passed
- `cargo test -p openclaw_types` - 35 unit/golden + 103 integration passed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable Phase 2 PASS artifact. This GUI lane contract is source-only until runtime GUI authority, route/cache/auth partitions, screenshots, and paper/shadow release evidence are separately approved.
