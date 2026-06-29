# IBKR Stock/ETF Phase 3 Evidence Contracts Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - source-only Phase 3 evidence checkers**
Scope: `stock_etf_cash` market-data provenance, DQ, frozen inputs, and evidence-clock checker contracts.

## Result

Phase 3 now has source-defined evidence checker contracts:

- `openclaw_types::stock_etf_phase3_evidence` defines market-data provenance, frozen evidence inputs, daily DQ manifest, evidence-clock day status, and typed blockers.
- Market-data provenance requires source/vendor, entitlement tier, raw payload hash, received/exchange time, adjusted/unadjusted marker, corporate-action version hash, symbol, instrument identity hash, and calendar session id.
- Frozen inputs require universe, benchmark, cost model, strategy hypothesis, paper-vs-shadow divergence threshold hashes, corporate-action/FX/fee as-of, GUI evidence view availability, and daily scorecard regeneration pass.
- DQ manifest shape is separated from pass-day quality, so quarantined days can carry valid manifests without being counted as PASS days.
- Evidence-clock `PASS_DAY` requires 5-day green IBKR read-only/paper connector evidence, 5-day green shadow collector evidence, accepted frozen inputs, and full DQ quality.
- `QUARANTINED_DAY` requires a valid manifest shape and an actual DQ failure.
- `WINDOW_COMPLETE` is not source-authorized by the checker fixture.
- `settings/broker/stock_etf_phase3_evidence_contracts.toml` is default BLOCKED and secret-free.

This checkpoint defines Phase 3 readiness logic without ingesting data, starting a clock, writing scorecards, or contacting IBKR.

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

- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance` - 8 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 68 integration tests passed
- `rustfmt --check rust/openclaw_types/src/stock_etf_phase3_evidence.rs rust/openclaw_types/tests/stock_etf_phase3_evidence_acceptance.rs` - pass
- `git diff --check` - pass

## Next Gate

First IBKR contact remains blocked. Runtime Phase 3 cannot start until Phase 2 real secret/topology evidence and immutable PASS artifact exist, and Phase 3 collectors/scorecard writers still require separate implementation and verification.
