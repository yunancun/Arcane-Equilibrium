# IBKR Stock/ETF Phase 5 Release Packet Contract Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - source-only release packet contract**
Scope: `stock_etf_release_packet_v1` typed release/shakedown evidence contract.

## Result

Phase 5 now has a machine-checkable source contract for the release packet:

- `openclaw_types::stock_etf_release_packet` defines release manifest hashes, PG migration evidence, kill/disable cleanup proof, and the `StockEtfReleasePacketV1` validator.
- The release packet requires ADR/AMD/spec paths, source commit, reviewer roles, role reports, E2/E3/E4/QA log hashes, manifest hashes, redaction fixture hash, GUI screenshots, DQ manifests, scorecard regeneration outputs, kill/disable cleanup proof, evidence archive pointer/hash, paper-shadow window completion, engineering shakedown completion, and sealing.
- Required roles are `PM`, `Operator`, `E2`, `E3`, `E4`, `QA`, `QC`, and `MIT`.
- PG dry-run and double-apply hashes are required only when migrations are declared.
- Kill/disable proof requires all stock/ETF and IBKR flags disabled, `OPENCLAW_STOCK_ETF_SHADOW_ONLY` preserved, collector stopped, GUI stock views disabled/hidden, live secret absence proven, forward-only evidence archive, and no destructive DB cleanup.
- The validator rejects serialized secret content and any live/tiny-live authority.
- `settings/broker/stock_etf_release_packet.template.toml` is default BLOCKED and secret-free.

This checkpoint makes Phase 5 release/shakedown evidence auditable without starting runtime evidence collection or granting any trading authority.

## Hard Boundary

This checkpoint does not create a PASS artifact, read or create secret slots, inspect secret contents, start IB Gateway/TWS, open sockets, start evidence collection, write PG, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission/cancel/replace
- active DB migration apply
- GUI lane authority
- evidence clock start
- tiny-live/live discussion or execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt --check rust/openclaw_types/src/stock_etf_release_packet.rs rust/openclaw_types/tests/stock_etf_release_packet_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_release_packet_acceptance` - 7 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 75 integration tests passed
- `git diff --check -- rust/openclaw_types/src/lib.rs rust/openclaw_types/src/stock_etf_release_packet.rs rust/openclaw_types/tests/stock_etf_release_packet_acceptance.rs settings/broker/README.md settings/broker/stock_etf_release_packet.template.toml` - pass

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable Phase 2 PASS artifact. A future real release packet also requires actual evidence archive, screenshots, DQ manifests, scorecard outputs, role reports, and shakedown evidence; this source contract alone does not complete Phase 5.
