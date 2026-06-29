# IBKR Stock/ETF Asset-Lane Audit Event Contract Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only immutable audit event references**
Scope: `audit.asset_lane_events_v1` for `stock_etf_cash` paper/shadow evidence.

## Result

The Phase 0 contract packet now has a machine-checkable source contract for immutable stock/ETF lane event references:

- `openclaw_types::stock_etf_audit_events` defines `StockEtfAssetLaneEventV1`, event kinds, typed blockers, and verdict output.
- The validator requires schema version, event id/kind, sequence number, genesis or previous event hash, event time, producer commit, actor, source, lane/broker/environment/operation, permission scope, account/session fingerprint hashes, decision/order ids, allowed/denial invariant, payload hash, raw artifact hash, redacted summary hash, source artifact hash, and input artifact hashes.
- It rejects non-`stock_etf_cash`, non-IBKR, live environment, unknown event kind, broken hash-chain shape, missing denial reason on denied events, denial reason on allowed events, serialized secret content, and inline raw payload.
- `settings/broker/stock_etf_asset_lane_events.template.toml` is default BLOCKED and secret-free.
- The Phase 0 manifest now includes `audit.asset_lane_events_v1`.

This gives paper lifecycle, DQ, scorecard input, release packet, and future eligibility evidence a shared immutable reference shape while preserving daily scorecards as derived artifacts.

## Hard Boundary

This checkpoint does not write audit rows, apply DB migrations, write PG, read or create secret slots, inspect secret contents, start IB Gateway/TWS, open sockets, start collectors, start the evidence clock, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission/cancel/replace
- active DB migration apply
- GUI lane authority
- tiny-live/live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt --check rust/openclaw_types/src/stock_etf_audit_events.rs rust/openclaw_types/tests/stock_etf_audit_events_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_audit_events_acceptance` - 8 passed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable Phase 2 PASS artifact. These audit event references are source-only until a reviewed writer, DDL apply, and real artifact archive path are separately approved.
