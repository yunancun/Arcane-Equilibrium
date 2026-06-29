# IBKR Stock/ETF Phase 2 Paper Lifecycle Event-Log Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - source-only lifecycle/event-log contract**
Scope: `stock_etf_cash` IBKR paper lifecycle evidence only.

## Result

Phase 2 now has source-defined paper order lifecycle and append-only event-log contracts:

- `openclaw_types::ibkr_paper_lifecycle` defines `BrokerLifecycleEventLogV1`, lifecycle event blockers, restart recovery input/action, and transition validation.
- The event log enforces `stock_etf_cash` + `ibkr` + non-live environment, paper lifecycle operations only, local order id, idempotency key, reconciliation run id, event id/time, artifact hashes, and allowed/denied reason consistency.
- Broker order id is required once the lifecycle has broker state; execution id and commission report id are required for partial/full fill states.
- Terminal states cannot transition back into active lifecycle states.
- `STATE_UNKNOWN` can only recover to `MANUAL_REVIEW_REQUIRED` or a reconciled terminal state with evidence.
- Restart recovery is fail-closed: preserve terminal state only with evidence hash, reconcile only with broker order id + idempotency key, otherwise mark `STATE_UNKNOWN`.
- `settings/broker/ibkr_paper_order_lifecycle.toml` is default BLOCKED and secret-free.

This checkpoint strengthens paper lifecycle evidence without creating an IBKR connector, broker order route, or runtime paper-order path.

## Hard Boundary

This checkpoint does not create a PASS artifact, read or create secret slots, inspect secret contents, start IB Gateway/TWS, open sockets, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission
- active DB migration apply
- GUI stock/ETF runtime activation
- evidence clock start
- live, tiny-live, margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `cargo test -p openclaw_types --test ibkr_paper_lifecycle_acceptance` - 8 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 60 integration tests passed
- `rustfmt --check rust/openclaw_types/src/ibkr_paper_lifecycle.rs rust/openclaw_types/tests/ibkr_paper_lifecycle_acceptance.rs` - pass
- `git diff --check` - pass

## Next Gate

First IBKR contact remains blocked. The next source-only gap is Phase 3 data/provenance/corporate-action/DQ evidence contracts; any real IBKR contact still requires real secret/topology evidence plus an immutable Phase 2 PASS artifact.
