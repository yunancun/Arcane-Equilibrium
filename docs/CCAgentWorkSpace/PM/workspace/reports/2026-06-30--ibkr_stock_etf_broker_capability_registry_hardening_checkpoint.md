# PM Checkpoint - IBKR Stock/ETF Broker Capability Registry Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `broker_capability_registry_v1`

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the central Stock/ETF IBKR broker operation matrix so
future registry artifacts must prove exact contract identity and source-version
alignment before they can support read, paper, shadow, or scorecard gates.

## Changed

- `StockEtfBrokerCapabilityRegistryV1` now requires
  `registry_id == broker_capability_registry_v1` and `source_version == 1`.
- Added a typed `SourceVersionMismatch` blocker.
- The Phase 0 manifest validator consumes the shared broker registry contract
  constant instead of a raw string.
- `lane_scoped_ipc_v1` paper-effect and preview gates consume the same shared
  broker registry constant.
- The default-blocked broker registry template exposes `source_version = 0`
  and still fails closed.
- Acceptance tests now reject a fixture-like registry id and wrong source
  versions.

## Boundary

No IBKR contact, healthcheck, IB Gateway/TWS startup, secret read/create/
serialization, connector runtime, market-data ingestion, paper order, evidence
clock, scorecard writer, DB apply, GUI lane authority, release, tiny-live, live,
or Bybit live execution behavior change occurred.

The registry remains a source-only operation matrix. It does not authorize
paper effects, IBKR contact, release, tiny-live, or live execution.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_broker_capability_registry_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_lane_scoped_ipc_acceptance
```

Result: `22 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `179` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_broker_capability_registry.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/src/stock_etf_lane_scoped_ipc.rs openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist. Any paper
order route still requires separate reviewed runtime authority, scoped IPC,
paper attestation, Decision Lease, Guardian, risk policy, idempotency, audit,
and lifecycle gates.
