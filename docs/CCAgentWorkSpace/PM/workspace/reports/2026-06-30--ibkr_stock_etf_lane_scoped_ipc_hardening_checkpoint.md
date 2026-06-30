# PM Checkpoint - IBKR Stock/ETF Lane-Scoped IPC Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `lane_scoped_ipc_v1`

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the Rust-owned Stock/ETF IPC contract boundary so
future lane-scoped IPC artifacts must prove exact contract identity and
source-version alignment before they can support paper-effect rehearsal gates.

## Changed

- `StockEtfLaneScopedIpcContractV1` now requires
  `contract_id == lane_scoped_ipc_v1` and `source_version == 1`.
- Added a typed `SourceVersionMismatch` blocker.
- The Phase 0 manifest validator consumes the shared lane-scoped IPC contract
  constant instead of a raw string.
- Paper-effect self-gates inside `lane_scoped_ipc_v1` consume the shared IPC
  contract constant.
- The default-blocked IPC template exposes `source_version = 0` and still
  fails closed.
- Acceptance tests now reject a fixture-like IPC contract id and wrong source
  versions.

## Boundary

No IPC server was started, no IBKR contact or healthcheck occurred, no IB
Gateway/TWS process was started, no secret was read/created/serialized, no
connector runtime was introduced, no paper order was routed, no evidence clock
or scorecard writer was started, no DB apply occurred, no GUI lane authority was
granted, and no tiny-live/live or Bybit live execution behavior changed.

The IPC contract remains a source-only method matrix. It does not authorize any
paper effect by itself.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `14 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `180` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_lane_scoped_ipc.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

Any real IPC runtime, paper order route, or broker effect still requires
separate reviewed runtime authority plus external-surface PASS, paper
attestation, scoped authorization, Decision Lease, Guardian, risk policy,
idempotency, audit, lifecycle, and broker capability registry gates. First IBKR
contact remains blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
