# IBKR Stock/ETF Phase 2 Pre-Contact Identity Hardening Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only Phase 2 pre-contact identity hardening**
Scope: `phase2_ibkr_external_surface_gate_v1`, `ibkr_api_session_topology_v1`, `ibkr_session_attestation_v1`, `feature_flag_secret_auth_matrix_v1`, and Phase 2 prerequisite policy identities.

## Result

The Phase 2 pre-contact source contracts now fail closed on named contract identity and source version:

- `IbkrExternalSurfaceGateV1` requires exact `contract_id == phase2_ibkr_external_surface_gate_v1` and `source_version == 1`.
- `IbkrApiSessionTopologyV1` requires exact `contract_id == ibkr_api_session_topology_v1` and `source_version == 1`.
- `IbkrSessionAttestationV1` requires exact `contract_id == ibkr_session_attestation_v1` and `source_version == 1`.
- `FeatureFlagSecretAuthMatrixV1` requires exact `contract_id == feature_flag_secret_auth_matrix_v1` and `source_version == 1`.
- Phase 2 prerequisite policies now carry and validate exact ids/source versions for redaction, rate limit, audit event, paper attestation, and Python no-write guard.
- Blocked external-surface/runtime/auth templates expose empty ids plus `source_version=0`; policy prerequisite templates carry exact source ids but remain non-authorizing prerequisites, not PASS artifacts.
- The Phase 0 packet spec and broker settings README now document these exact identity/version requirements.

This closes the gap where Phase 2 pre-contact artifacts could satisfy shape/boolean checks without proving they came from the current named contract source.

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

- `rustfmt rust/openclaw_types/src/ibkr_phase2_gate.rs rust/openclaw_types/src/ibkr_phase2_runtime.rs rust/openclaw_types/src/ibkr_phase2_policies.rs rust/openclaw_types/src/ibkr_feature_flag_secret_auth.rs rust/openclaw_types/tests/ibkr_phase2_gate_acceptance.rs rust/openclaw_types/tests/ibkr_phase2_runtime_acceptance.rs rust/openclaw_types/tests/ibkr_phase2_policy_acceptance.rs rust/openclaw_types/tests/ibkr_feature_flag_secret_auth_acceptance.rs` - pass
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_gate_acceptance --test ibkr_phase2_runtime_acceptance --test ibkr_phase2_policy_acceptance --test ibkr_feature_flag_secret_auth_acceptance` - 32 tests passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_artifact_acceptance --test ibkr_phase2_gate_acceptance --test ibkr_phase2_runtime_acceptance --test ibkr_phase2_policy_acceptance --test ibkr_feature_flag_secret_auth_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance` - 62 tests passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` - 35 unit/golden + 191 integration/acceptance passed; 0 doc-tests
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types -- --list` - 35 unit/golden + 191 integration/acceptance listed
- `cargo check --manifest-path rust/Cargo.toml --workspace` - pass

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact. This source hardening does not authorize connector runtime, IPC runtime, paper orders, fill import, evidence-clock start, release, tiny-live, or live.
