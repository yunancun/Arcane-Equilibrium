# IBKR Stock/ETF Phase 2 Artifact + Secret Identity Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only Phase 2 artifact/secret identity hardening**
Scope: `IbkrPhase2GateArtifactV1` artifact envelope identity and `IbkrSecretSlotContractV1` secret-slot source identity.

## Result

The Phase 2 gate artifact chain now fails closed on the remaining pre-contact identity gaps:

- `IbkrPhase2GateArtifactV1` requires exact `contract_id == phase2_ibkr_external_surface_gate_v1` and `source_version == 1`.
- `IbkrSecretSlotContractV1` requires exact `contract_id == ibkr_secret_slot_contract_v1` and `source_version == 1`.
- The blocked gate artifact template now exposes empty ids plus `source_version=0` for the artifact envelope, embedded external-surface gate, secret-slot contract, and API session topology.
- The blocked runtime contract template now exposes empty secret-slot id plus `source_version=0`.
- Regression tests reject fixture-like artifact/secret ids and wrong source versions while preserving the existing sealed-artifact, reviewer, hash, policy-flag, runtime-evidence, and no-prior-contact checks.
- The Phase 0 packet spec and broker settings README now document the secret-slot source identity requirement.

This closes the gap where an immutable Phase 2 artifact could validate its nested gate/runtime shapes without proving the current artifact envelope and secret-slot source contract identities.

## Hard Boundary

This checkpoint did not contact IBKR, inspect secret contents, create secret slots, start IB Gateway/TWS, create connectors, route paper orders, cancel/replace orders, import fills, write audit rows, apply migrations, open Postgres, start collectors, start the evidence clock, or authorize:

- IBKR API calls or healthchecks
- IBKR connector implementation/runtime
- broker-paper order submission, cancel, replace, or fill import
- active migration apply or DB writes
- audit writer/runtime
- GUI lane authority
- release, tiny-live, or live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/ibkr_phase2_artifact.rs rust/openclaw_types/src/ibkr_phase2_runtime.rs rust/openclaw_types/tests/ibkr_phase2_artifact_acceptance.rs rust/openclaw_types/tests/ibkr_phase2_runtime_acceptance.rs rust/openclaw_types/tests/ibkr_feature_flag_secret_auth_acceptance.rs` - pass
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_artifact_acceptance --test ibkr_phase2_runtime_acceptance --test ibkr_feature_flag_secret_auth_acceptance` - 23 tests passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_artifact_acceptance --test ibkr_phase2_gate_acceptance --test ibkr_phase2_runtime_acceptance --test ibkr_phase2_policy_acceptance --test ibkr_feature_flag_secret_auth_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance` - 63 tests passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` - 35 unit/golden + 192 integration/acceptance passed; 0 doc-tests
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types -- --list` - 35 unit/golden + 192 integration/acceptance listed
- `cargo check --manifest-path rust/Cargo.toml --workspace` - pass

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. This source hardening does not authorize connector runtime, IPC runtime, paper orders, fill import, evidence-clock start, release, tiny-live, or live.
