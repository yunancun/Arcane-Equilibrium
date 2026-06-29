# IBKR Stock/ETF Phase 2 Artifact Runtime Evidence Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - artifact now requires runtime evidence**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow research lane.

## Result

The Phase 2 immutable gate artifact now validates runtime evidence as first-class launch evidence:

- `IbkrPhase2GateArtifactV1` embeds `IbkrSecretSlotContractV1` and `IbkrApiSessionTopologyV1`.
- The artifact rejects missing or invalid secret-slot evidence with `SecretSlotContractRejected`.
- The artifact rejects missing or invalid API session topology evidence with `ApiSessionTopologyRejected`.
- The artifact rejects gate/runtime inconsistency with `RuntimeGateFlagMismatch`, including a gate that claims secret readiness while embedded runtime evidence is absent or mismatched.
- The blocked artifact template now includes explicit empty secret-slot and API topology evidence sections, so a real PASS artifact cannot be represented by gate booleans alone.

This closes the source-level gap between the prior immutable artifact shell and the runtime evidence contracts. A valid artifact must now carry coherent, validated secret/topology evidence in addition to PM/Operator review metadata, hashes, gate PASS state, and policy prerequisite flags.

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

- `cargo test -p openclaw_types --test ibkr_phase2_artifact_acceptance` - 7 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 45 integration tests passed
- `rustfmt --check rust/openclaw_types/src/ibkr_phase2_artifact.rs rust/openclaw_types/tests/ibkr_phase2_artifact_acceptance.rs` - pass
- `git diff --check` - pass

## Next Gate

The first IBKR read-only healthcheck remains blocked until real secret/topology evidence is produced without leaking secrets, an immutable Phase 2 PASS artifact validates that embedded evidence, and the artifact records `ibkr_call_performed=false` for the gate itself.
