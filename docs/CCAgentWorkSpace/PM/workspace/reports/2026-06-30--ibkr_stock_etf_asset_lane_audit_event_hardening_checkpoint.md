# PM Checkpoint - IBKR Stock/ETF Asset-Lane Audit Event Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 immutable `audit.asset_lane_events_v1` references

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the cross-phase Stock/ETF audit reference contract so
future event-reference artifacts must prove exact schema identity and
source-version alignment before they can be used as evidence pointers.

## Changed

- Added exported `STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID`.
- `StockEtfAssetLaneEventV1` now requires
  `schema_version == audit.asset_lane_events_v1` and `source_version == 1`.
- The Phase 0 manifest validator now consumes the shared audit event contract
  constant instead of a raw string.
- The default-blocked audit event template exposes `source_version = 0` and
  still fails closed.
- Acceptance tests now reject a fixture-like schema id and wrong source
  versions.

## Boundary

No audit row was written, no DDL was applied, no PG access was opened, and no
runtime writer was introduced. No IBKR contact, healthcheck, IB Gateway/TWS
startup, secret read/create/serialization, connector runtime, collector,
evidence-clock start, scorecard writer, DB apply, GUI lane authority, paper
order, tiny-live, live, or Bybit live execution behavior change.

The contract remains an immutable reference shape only. It does not authorize
audit persistence, broker effects, paper orders, release, tiny-live, or live.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_audit_events_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `15 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `178` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_audit_events.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/tests/stock_etf_audit_events_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

Any real audit writer, DB migration apply, event persistence, or archive
materialization still requires separate reviewed Phase 1/5 gates. First IBKR
contact remains blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
