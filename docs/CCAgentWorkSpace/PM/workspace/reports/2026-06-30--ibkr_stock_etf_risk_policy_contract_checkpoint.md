# IBKR Stock/ETF Risk Policy Contract Checkpoint

Date: 2026-06-30
Owner: PM
Scope: ADR-0048 / AMD-2026-06-29-01 `stock_etf_cash` paper/shadow source contract
Status: Source checkpoint accepted; no runtime authority

## Summary

新增 `stock_etf_risk_policy_v1`，把既有 dormant
`settings/risk_control_rules/risk_config_stock_etf_paper.toml` 轉成可機器驗證的
Stock/ETF cash risk policy contract。

The contract validates:

- `asset_lane=stock_etf_cash`, `broker=ibkr`, paper/shadow-only environment.
- Source posture remains `enabled=false` and `shadow_only=true`.
- Finite positive order / position / daily notional caps with ordered limits.
- Bounded open-order and open-position counts.
- Cash-only denials for margin, short, options, CFD, transfer, and live.
- Stock/ETF/cash universe allowlist plus crypto/CFD denied kinds.
- Frozen universe, instrument identity, market session, cost model, Rust
  authority, session attestation, Decision Lease, Guardian, idempotency, and
  broker reconciliation prerequisites.
- Bybit live execution unchanged and no IBKR contact / connector runtime /
  secret serialization.

## Code And Contract Changes

- Added Rust source validator:
  `rust/openclaw_types/src/stock_etf_risk_policy.rs`.
- Added acceptance tests:
  `rust/openclaw_types/tests/stock_etf_risk_policy_acceptance.rs`.
- Added blocked, secret-free template:
  `settings/broker/stock_etf_risk_policy.template.toml`.
- Wired `stock_etf_risk_policy_v1` into:
  `stock_etf_phase0_manifest`, `lane_scoped_ipc_v1`, and
  `broker_capability_registry_v1`.
- Updated Phase 0 contract packet, manifest JSON, ADR-0048, broker/risk README,
  governance register, document index, and initiative index.

## Verification

- Focused linked tests:
  `cargo test -p openclaw_types --test stock_etf_risk_policy_acceptance --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_phase0_manifest_acceptance`
  passed: 28 tests.
- Full crate:
  `cargo test -p openclaw_types` passed: 35 unit/golden tests, 163
  integration/acceptance tests, 0 doc-tests.
- Targeted `rustfmt --check` for touched Rust files passed.
- `git diff --check` passed.

## Boundary

This checkpoint is source-only. It does not contact IBKR, read or create
secrets, start a connector, start an evidence clock, route paper orders, write
scorecards, apply DB migrations, enable GUI lane authority, authorize tiny-live
or live, or change Bybit live execution behavior.

The first IBKR contact remains blocked until real secret/topology evidence and
an immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
