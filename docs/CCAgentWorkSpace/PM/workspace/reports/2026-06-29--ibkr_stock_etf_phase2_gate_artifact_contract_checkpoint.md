# IBKR Stock/ETF Phase 2 Gate Artifact Contract Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - artifact contract only**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow research lane.

## Result

The immutable Phase 2 external-surface gate artifact contract is now source-defined:

- `openclaw_types::ibkr_phase2_artifact` defines `IbkrPhase2GateArtifactV1`.
- Validation requires artifact id, ADR/AMD match, source commit, created timestamp, immutable storage path, PM + Operator reviewers, sealed artifact, valid 64-char hex hashes, external gate PASS, policy prerequisite flags, and policy/gate flag consistency.
- Any artifact with `ibkr_call_performed=true` or a rejected external gate remains blocked.
- `settings/broker/ibkr_phase2_gate_artifact.template.toml` is intentionally empty/BLOCKED and secret-free.

## Hard Boundary

This checkpoint does not create an immutable PASS artifact and does not authorize:

- IBKR API call, healthcheck, or IBKR Gateway/TWS connection
- IBKR connector implementation
- secret-slot creation or credential write
- broker-paper order submission
- active DB migration apply
- GUI stock/ETF runtime activation
- evidence clock start
- live, tiny-live, margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue. This is pure type validation in `openclaw_types`.

## Verification

- `cargo test -p openclaw_types --test ibkr_phase2_artifact_acceptance` - 6 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 37 integration tests passed
- `rustfmt --check rust/openclaw_types/src/ibkr_phase2_artifact.rs rust/openclaw_types/tests/ibkr_phase2_artifact_acceptance.rs` - pass
- `git diff --check` - pass

## Next Gate

The first IBKR read-only healthcheck remains blocked until a real reviewed artifact satisfying this contract exists and records `ibkr_call_performed=false` for the gate itself.
