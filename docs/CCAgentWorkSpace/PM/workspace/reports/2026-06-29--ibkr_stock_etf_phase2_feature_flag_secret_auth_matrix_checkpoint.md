# IBKR Stock/ETF Phase 2 Feature-Flag Secret Auth Matrix Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - source-only authorization matrix**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow research lane.

## Result

Phase 2 now has a source-defined `feature_flag_secret_auth_matrix_v1` contract:

- `openclaw_types::ibkr_feature_flag_secret_auth` defines `FeatureFlagSecretAuthMatrixV1`, `StockEtfAuthorizationEnvelopeV1`, and typed blockers.
- The matrix requires server/Rust authority and explicitly denies GUI lane-state override.
- Read-only flag enablement does not imply paper-write authority.
- Paper flag enablement does not imply live, margin, short, options, CFD, transfer, or account-management authority.
- `stock_etf_shadow_only=true` blocks paper orders even when read-only and paper flags are enabled.
- A paper authorization candidate must carry a valid secret-slot contract, immutable Phase 2 gate artifact, session attestation, scoped authorization envelope, matching secret/account fingerprints, risk-config hash, and unexpired envelope.
- `settings/broker/ibkr_feature_flag_secret_auth_matrix.toml` is default BLOCKED and secret-free.

This checkpoint keeps IBKR authorization semantics separate from Bybit execution paths while reusing the common lane taxonomy, Phase 2 artifact validation, session attestation, runtime secret contract, and feature-flag parser.

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

- `cargo test -p openclaw_types --test ibkr_feature_flag_secret_auth_acceptance` - 7 passed
- `cargo test -p openclaw_types` - 35 unit/golden tests + 52 integration tests passed
- `rustfmt --check rust/openclaw_types/src/ibkr_feature_flag_secret_auth.rs rust/openclaw_types/tests/ibkr_feature_flag_secret_auth_acceptance.rs` - pass
- `git diff --check` - pass

## Next Gate

First IBKR contact remains blocked. The next source-only gap is paper order lifecycle/event-log contract hardening or Phase 3 data/provenance contracts; any real IBKR contact still requires real secret/topology evidence plus an immutable Phase 2 PASS artifact.
