# PM Checkpoint - IBKR Stock/ETF Scorecard Input Contract Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 Phase 3 scorecard input source contracts

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the existing scorecard input source contracts. Future
Stock/ETF scorecard input bundles must now prove exact named contract identity
and source-version alignment for the cash ledger, cost model, benchmark, shadow
fill, and storage capacity inputs before they can be treated as accepted source
evidence.

## Changed

- Added exported contract ids for:
  `broker_account_portfolio_cash_ledger_v1`,
  `cost_model_version_v1`, `benchmark_versions_v1`,
  `stock_shadow_fill_model_v1`, and `stock_etf_storage_capacity_v1`.
- Each scorecard input validator now requires the exact contract id and
  `source_version=1`.
- `StockEtfScorecardInputBundleV1` now requires market-data provenance,
  reference-data source, and risk-policy contract hashes.
- The bundle now rejects Bybit-live regression, IBKR contact, connector runtime,
  broker fill import, scorecard writer, DB apply, evidence-clock start,
  serialized secret content, and tiny-live/live authority.
- Broker capability and lane-scoped IPC gates now consume the shared scorecard
  contract constants instead of duplicate string literals.
- The default-blocked template
  `settings/broker/stock_etf_scorecard_inputs.template.toml` now includes the
  named contract fields, cross-contract hashes, and side-effect denial flags.
- Updated ADR-0048, Phase 0 named contract packet spec, settings README,
  specification register, document/initiative indexes, PM memory, and Operator
  brief.

## Boundary

No IBKR contact, no IBKR process startup, no secret read/create/serialization,
no connector runtime, no broker fill import, no collector, no scorecard writer,
no DB apply, no evidence clock, no GUI lane authority, no paper order, no
tiny-live, no live, and no Bybit live execution behavior change.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_scorecard_inputs_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `30 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `173` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_scorecard_inputs.rs openclaw_types/src/stock_etf_broker_capability_registry.rs openclaw_types/src/stock_etf_lane_scoped_ipc.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/tests/stock_etf_scorecard_inputs_acceptance.rs openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.
