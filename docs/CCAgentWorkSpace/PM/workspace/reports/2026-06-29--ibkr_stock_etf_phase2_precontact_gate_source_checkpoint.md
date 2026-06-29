# IBKR Stock/ETF Phase 2 Pre-Contact Gate Source Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - source gate foundation only**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow research lane.

## Result

Phase 2 pre-contact source contracts are present for ADR-0048 / AMD-2026-06-29-01:

- `openclaw_types::ibkr_phase2_gate` defines `phase2_ibkr_external_surface_gate_v1` as a fail-closed typed contract.
- Default external-surface gate status is `BLOCKED`; every required boolean field must be true and `ibkr_call_performed` must remain false before any IBKR contact is allowed.
- `non_bybit_api_allowlist_v1` is represented as typed action classification: read-style actions require the external gate, paper writes require later paper-order gates, and live/margin/short/options/CFD/transfer/account-management/Client Portal paths are typed denials.
- `ibkr_session_attestation_v1` is represented as a pure validation contract for loopback host, paper gateway default port, non-live account fingerprint, non-world-readable secret slot, no env-var credential fallback, expiry window, and redacted artifact hash.
- `settings/broker/ibkr_external_surface_gate.toml` is a source template only and remains intentionally `BLOCKED`.

## Hard Boundary

This checkpoint does not create an immutable Phase 2 PASS artifact and does not authorize:

- IBKR API call, healthcheck, or IBKR Gateway/TWS connection
- IBKR connector implementation
- secret-slot creation or credential write
- broker-paper order submission
- active DB migration apply
- GUI stock/ETF runtime activation
- evidence clock start
- live, tiny-live, margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue. The new code is an `openclaw_types` pure validation module and does not touch Bybit execution handlers.

## Verification

- `cargo test -p openclaw_types --test ibkr_phase2_gate_acceptance` - 8 passed
- `cargo test -p openclaw_types --test stock_etf_lane_acceptance` - 8 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 23 integration tests passed
- `rustfmt --check rust/openclaw_types/src/ibkr_phase2_gate.rs rust/openclaw_types/tests/ibkr_phase2_gate_acceptance.rs` - pass
- `git diff --check` - pass

## Next Gate

The next safe step is implementation/review of the actual immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact process. First IBKR read-only healthcheck remains blocked until that artifact exists, is reviewed, and records `ibkr_call_performed=false` for the gate itself.
