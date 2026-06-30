# PM Checkpoint - IBKR Stock/ETF Instrument Identity Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `instrument_identity_contract_v1`

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the point-in-time Stock/ETF instrument identity
contract so future symbol identity artifacts must prove exact contract identity
and source-version alignment before contract-details, market-data, paper-intent,
or IPC gates can depend on them.

## Changed

- `StockEtfInstrumentIdentityV1` now requires
  `contract_id == instrument_identity_contract_v1` and `source_version == 1`.
- Added a typed `SourceVersionMismatch` blocker.
- The Phase 0 manifest validator consumes the shared instrument identity
  contract constant instead of a raw string.
- Broker capability contract-details gates and lane-scoped IPC paper/preview
  gates consume the same shared instrument identity constant.
- The default-blocked instrument identity template exposes `source_version = 0`
  and remains fail-closed.
- Acceptance tests now reject a fixture-like instrument identity id and wrong
  source versions.

## Boundary

No IBKR contract-details call, market-data subscription, connector runtime,
secret read/create/serialization, paper order, IPC runtime, evidence clock,
scorecard writer, DB apply, GUI lane authority, tiny-live, live, or Bybit live
execution behavior change occurred.

The instrument identity contract remains source-only point-in-time metadata. It
does not authorize IBKR contact, broker effects, paper orders, or data
collection.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_instrument_identity_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `31 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `181` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_instrument_identity.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/src/stock_etf_lane_scoped_ipc.rs openclaw_types/src/stock_etf_broker_capability_registry.rs openclaw_types/tests/stock_etf_instrument_identity_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

Any real contract-details read, market-data subscription, paper intent, or
instrument universe materialization still requires separate reviewed runtime
authority plus external-surface PASS, session/topology evidence, redaction,
rate-limit, audit, PIT universe, risk policy, and IPC gates. First IBKR contact
remains blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
