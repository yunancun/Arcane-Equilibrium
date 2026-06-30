# PM Checkpoint - IBKR Stock/ETF Risk Policy Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `stock_etf_risk_policy_v1`

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the Stock/ETF paper/shadow risk-policy contract so
future risk-policy artifacts must prove exact contract identity and
source-version alignment before paper-order, shadow-fill, or scorecard gates can
depend on their `risk_config_hash`.

## Changed

- `StockEtfRiskPolicyV1` now requires
  `contract_id == stock_etf_risk_policy_v1` and `source_version == 1`.
- Added a typed `SourceVersionMismatch` blocker.
- `StockEtfRiskPolicyV1::from_source_config` now emits `source_version = 1`
  while preserving the dormant source config `meta.version` as config version.
- The Phase 0 manifest validator consumes the shared risk policy contract
  constant instead of a raw string.
- The default-blocked risk policy template exposes `source_version = 0` and
  remains fail-closed.
- Acceptance tests now reject a fixture-like risk-policy id and wrong source
  versions.

## Boundary

No IBKR contact, connector runtime, paper order, IPC runtime, market-data
collection, evidence clock, scorecard writer, DB apply, GUI lane authority,
secret read/create/serialization, tiny-live, live, or Bybit live execution
behavior change occurred.

The risk policy remains a source-only contract over dormant configuration. It
does not enable runtime trading, paper orders, broker effects, or risk bypass.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_risk_policy_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance
```

Result: `31 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `184` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_risk_policy.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/tests/stock_etf_risk_policy_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

Any runtime risk-policy activation, paper order route, shadow-fill use, or
scorecard derivation still requires separate reviewed runtime authority plus
external-surface PASS, scoped IPC, paper attestation, Decision Lease, Guardian,
idempotency, audit, lifecycle, broker capability, and release gates. First IBKR
contact remains blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
