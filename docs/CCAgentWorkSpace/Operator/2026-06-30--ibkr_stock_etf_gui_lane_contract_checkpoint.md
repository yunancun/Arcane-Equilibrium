# Operator Summary - IBKR Stock/ETF GUI Lane Contract

Date: 2026-06-30
Status: **GUI lane source contract done; GUI authority still blocked**

PM added a Rust source contract for `gui_lane_contract_v1`.

It validates future Stock/ETF GUI lane evidence for:

- default displayed lane remains `crypto_perp`
- readiness endpoint is GET-only
- Stock/ETF surface is display-only
- client lane state is untrusted
- localStorage/query params/hidden fields cannot authorize
- no POST routes
- no order widgets
- no secret widgets
- no IBKR contact on render
- route/cache/auth partition evidence
- stale-cache cross-lane denial
- crypto tab and Decision Lease/risk regression evidence

Safety result:

- default contract blocks
- template is secret-free
- contact and secret serialization are rejected
- effect-capable GUI surfaces are rejected
- denied live order, secret-slot creation, and pre-gate IBKR contact operations are required

Verified:

- targeted rustfmt: pass
- GUI lane contract acceptance tests: 7 passed
- full `openclaw_types`: 35 unit/golden + 103 integration passed

Still blocked:

- no immutable Phase 2 PASS artifact
- no real secret/topology evidence
- no IBKR API call or healthcheck
- no secret creation or secret-content read
- no connector
- no paper order
- no GUI write/POST route
- no GUI lane authority
- no collector
- no evidence clock
- no tiny-live/live/margin/short/options/CFD/transfer/account-management/Client Portal path

This is source contract work only. It makes the GUI boundary reviewable; it is not runtime approval.
