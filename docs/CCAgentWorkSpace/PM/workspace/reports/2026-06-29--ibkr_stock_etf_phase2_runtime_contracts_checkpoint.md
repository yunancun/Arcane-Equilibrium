# IBKR Stock/ETF Phase 2 Runtime Contracts Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - runtime evidence contracts only**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow research lane.

## Result

Phase 2 secret-slot and API topology evidence contracts are now source-defined:

- `openclaw_types::ibkr_phase2_runtime` defines `IbkrSecretSlotContractV1` and `IbkrApiSessionTopologyV1`.
- Secret-slot validation requires a present contract, hashed paper slot, absent/empty live slot, hashed secret-slot and account fingerprints, owner-only permissions, env-var credential fallback denial, and no serialized secret/account id.
- API topology validation requires `ib_gateway_tws_api`, runtime owner `trade-core`, loopback/unix-local host, paper gateway default port `4002`, paper gateway mode, paper environment, deterministic client id, process identity, account fingerprint hash, API server version, entitlement, startup, and expiry evidence.
- Live Gateway/TWS ports, network host, live mode, live environment, unhashed fingerprints, serialized secret material, and env-var credential fallback fail closed.
- `settings/broker/ibkr_phase2_runtime_contracts.toml` is intentionally incomplete/BLOCKED and secret-free.

## Hard Boundary

This checkpoint does not create secret slots, inspect secret contents, start IB Gateway/TWS, open sockets, create a PASS artifact, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission
- active DB migration apply
- GUI stock/ETF runtime activation
- evidence clock start
- live, tiny-live, margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue. This is pure type validation in `openclaw_types`.

## Verification

- `cargo test -p openclaw_types --test ibkr_phase2_runtime_acceptance` - 7 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 44 integration tests passed
- `rustfmt --check rust/openclaw_types/src/ibkr_phase2_runtime.rs rust/openclaw_types/tests/ibkr_phase2_runtime_acceptance.rs` - pass
- `git diff --check` - pass

## Next Gate

The first IBKR read-only healthcheck remains blocked until real secret/topology evidence is produced without leaking secrets, an immutable Phase 2 PASS artifact validates that evidence, and the artifact records `ibkr_call_performed=false` for the gate itself.
