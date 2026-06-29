# IBKR Stock/ETF Tiny-Live ADR Eligibility Contract Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - source-only future ADR discussion gate**
Scope: `tiny_live_adr_eligibility_v1` typed eligibility contract.

## Result

Phase 0/5 now has a machine-checkable source contract for the future tiny-live ADR discussion gate:

- `openclaw_types::stock_etf_tiny_live_eligibility` defines `TinyLiveAdrEligibilityV1`, `TinyLiveAdrEligibilityDecision`, typed blockers, and verdict output.
- The validator requires ADR/AMD/spec path consistency, Phase 5 release packet hash, scorecard manifest hash, DQ manifest hash, statistical preregistration hash, QC/MIT review hashes, paper-shadow window completion, positive benchmark-relative after-cost LCB, independent-observation threshold, positive conservative cost-stress LCB, paper-vs-shadow divergence inside threshold, concentration/regime/freshness labels, QC/MIT review pass, `adr_discussion_only` decision, no serialized secret content, and sealing.
- `TinyLiveAuthorized` and `LiveAuthorized` decision values are explicit blockers even when all evidence fields are otherwise present.
- `settings/broker/stock_etf_tiny_live_adr_eligibility.template.toml` is default BLOCKED and secret-free.
- ADR-0048 and the Phase 0 named contract packet now clarify that this contract can only open a future ADR discussion and cannot authorize tiny-live/live.

This checkpoint prevents a positive paper/shadow scorecard from being interpreted as execution authority.

## Hard Boundary

This checkpoint does not create a PASS artifact, start an ADR, read or create secret slots, inspect secret contents, start IB Gateway/TWS, open sockets, start evidence collection, write PG, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission/cancel/replace
- active DB migration apply
- GUI lane authority
- evidence clock start
- tiny-live/live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_tiny_live_eligibility.rs rust/openclaw_types/tests/stock_etf_tiny_live_eligibility_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_tiny_live_eligibility_acceptance` - 6 passed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable Phase 2 PASS artifact. Future tiny-live can only be discussed through a new ADR after this eligibility contract has real paper/shadow evidence, review hashes, and `adr_discussion_only` output; it still cannot grant execution authority.
