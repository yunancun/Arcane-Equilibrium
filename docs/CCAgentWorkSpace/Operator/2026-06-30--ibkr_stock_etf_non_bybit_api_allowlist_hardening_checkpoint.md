# 2026-06-30 IBKR Stock/ETF Non-Bybit API Allowlist Hardening Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- Added source-only `openclaw_types::ibkr_non_bybit_api_allowlist::NonBybitApiAllowlistV1`.
- The contract now requires exact `contract_id == non_bybit_api_allowlist_v1` and `source_version == 1`.
- The allowlist pins all 23 non-Bybit/IBKR actions exactly once across read, paper-write, and denied buckets.
- Bucket validation is tied to `classify_non_bybit_api_action`, so classifier drift and contract drift fail together.
- The validator rejects Client Portal Web API use, live orders, account transfer, margin, short, options, CFD, market-data entitlement purchase, account-management writes, IBKR contact, serialized secrets, and Bybit-live regression.
- The blocked `settings/broker/ibkr_external_surface_gate.toml` template now exposes `[allowlist] contract_id=""` and `source_version=0`, preserving default blocked posture.
- The allowlist implementation was split out of `ibkr_phase2_gate.rs`; file sizes are now `ibkr_phase2_gate.rs=484` and `ibkr_non_bybit_api_allowlist.rs=379`, avoiding growth past the 800-line review-attention threshold.

## Boundary

- No IBKR contact, healthcheck, socket, connector construction, secret read/create/serialization, paper order, fill import, audit writer, DB apply, GUI authority, release, tiny-live, or live authority was added or exercised.
- Existing Bybit live execution code paths were not changed.
- First IBKR contact remains blocked until real secret/topology evidence and an immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- Focused gate acceptance:
  `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_gate_acceptance`
  - `10 passed`
- Linked IBKR/Phase0 acceptance:
  `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_artifact_acceptance --test ibkr_phase2_gate_acceptance --test ibkr_phase2_runtime_acceptance --test ibkr_phase2_policy_acceptance --test ibkr_feature_flag_secret_auth_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance`
  - `65 passed`
- Full openclaw_types:
  `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`
  - `35` unit/golden tests passed
  - `194` integration/acceptance tests passed
  - `0` doc-tests
- Test inventory:
  `cargo test --manifest-path rust/Cargo.toml -p openclaw_types -- --list`
  - `35` unit/golden tests
  - `194` integration/acceptance tests
  - `0` doc-tests
- Workspace type check:
  `cargo check --manifest-path rust/Cargo.toml --workspace`
  - passed

## Dispatch Note

This checkpoint was handled locally by PM because the available sub-agent tool policy permits spawning only when the user explicitly asks for sub-agents or parallel agent work. Repo PM rules prefer E2/E4 separation; E2 was therefore not spawned under the tool constraint. E4-equivalent regression coverage was performed locally with focused, linked, full `openclaw_types`, and workspace checks.

## Next Gate

Continue hardening remaining pre-contact source contracts and templates only. Do not open IBKR contact, runtime connector, secret slot, paper order, DB writer, GUI lane authority, tiny-live, or live scope from this checkpoint.
