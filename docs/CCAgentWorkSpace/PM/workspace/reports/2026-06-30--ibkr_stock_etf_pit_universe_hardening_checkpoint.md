# PM Checkpoint - IBKR Stock/ETF PIT Universe Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `stock_etf_pit_universe_contract_v1`

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the point-in-time Stock/ETF universe contract so future
universe membership artifacts must prove exact contract identity and
source-version alignment before evidence-clock, shadow-signal, preview, or
scorecard gates can depend on their universe hashes.

## Changed

- `StockEtfPitUniverseV1` now requires
  `contract_id == stock_etf_pit_universe_contract_v1` and `source_version == 1`.
- Added a typed `SourceVersionMismatch` blocker.
- The Phase 0 manifest validator consumes the shared PIT universe contract
  constant instead of a raw string.
- Broker capability shadow/signal and scorecard gates consume the shared PIT
  universe constant.
- `lane_scoped_ipc_v1` preview and shadow gates consume the same shared PIT
  universe constant.
- The default-blocked PIT universe template exposes `source_version = 0` and
  remains fail-closed.
- Acceptance tests now reject a fixture-like PIT universe id and wrong source
  versions.

## Boundary

No IBKR contact, connector runtime, market-data collection, universe ingestion,
paper order, IPC runtime, evidence clock, scorecard writer, DB apply, GUI lane
authority, secret read/create/serialization, tiny-live, live, or Bybit live
execution behavior change occurred.

The PIT universe contract remains source-only metadata. It does not authorize
data collection, evidence-clock start, scorecard derivation, paper orders, or
broker effects.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_pit_universe_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `30 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `182` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_pit_universe.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/src/stock_etf_lane_scoped_ipc.rs openclaw_types/src/stock_etf_broker_capability_registry.rs openclaw_types/tests/stock_etf_pit_universe_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

Any real universe materialization, market-data collection, evidence-clock use,
shadow-signal generation, or scorecard derivation still requires separate
reviewed runtime authority plus instrument identity, reference data, market
provenance, risk policy, redaction/audit, and external-surface gates. First IBKR
contact remains blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
