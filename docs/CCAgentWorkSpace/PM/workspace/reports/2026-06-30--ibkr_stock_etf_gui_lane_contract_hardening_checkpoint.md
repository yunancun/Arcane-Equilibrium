# PM Checkpoint - IBKR Stock/ETF GUI Lane Contract Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 Phase 4 GUI lane source contract

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the Phase 4 GUI readiness contract so future GUI
display artifacts must prove exact named-contract identity and source-version
alignment before they can be used for route/cache/auth review.

## Changed

- Added exported `STOCK_ETF_GUI_LANE_CONTRACT_ID`.
- `StockEtfGuiLaneContractV1` now requires
  `contract_id == gui_lane_contract_v1` and `source_version == 1`.
- The Phase 0 manifest validator now consumes the shared GUI lane contract
  constant instead of a raw string.
- The default-blocked GUI template exposes `source_version = 0` and still fails
  closed.
- Acceptance tests now reject the old `gui_lane_contract_v1_fixture` id and
  wrong source versions.

## Boundary

No GUI runtime route was served or changed. No IBKR contact, healthcheck,
IB Gateway/TWS startup, secret read/create/serialization, connector runtime,
collector, evidence-clock start, scorecard writer, DB apply, GUI lane
authority, paper order, tiny-live, live, or Bybit live execution behavior change.

The GUI contract remains display-only. Client lane state, localStorage, query
params, hidden fields, and GUI readiness/badges cannot authorize broker effects.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_gui_lane_contract_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `14 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `177` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_gui_lane_contract.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/tests/stock_etf_gui_lane_contract_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

Phase 4 runtime GUI work still requires actual route/cache/auth negative tests,
screenshots, crypto regression evidence, and release packet evidence. First IBKR
contact remains blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
