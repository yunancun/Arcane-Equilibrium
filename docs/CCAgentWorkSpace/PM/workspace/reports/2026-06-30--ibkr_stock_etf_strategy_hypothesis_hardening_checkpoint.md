# PM Checkpoint - IBKR Stock/ETF Strategy Hypothesis Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `stock_etf_strategy_hypothesis_contract_v1`

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the pre-registered Stock/ETF strategy hypothesis
contract so future hypothesis artifacts must prove exact contract identity and
source-version alignment before evidence-clock, shadow-signal, or scorecard
gates can depend on their strategy hashes.

## Changed

- `StockEtfStrategyHypothesisV1` now requires
  `contract_id == stock_etf_strategy_hypothesis_contract_v1` and
  `source_version == 1`.
- Added a typed `SourceVersionMismatch` blocker.
- The Phase 0 manifest validator consumes the shared strategy hypothesis
  contract constant instead of a raw string.
- Broker capability shadow/signal and scorecard gates consume the shared
  strategy hypothesis constant.
- `lane_scoped_ipc_v1` shadow gates consume the same shared strategy hypothesis
  constant.
- The default-blocked strategy hypothesis template exposes `source_version = 0`
  and remains fail-closed.
- Acceptance tests now reject a fixture-like strategy hypothesis id and wrong
  source versions.

## Boundary

No IBKR contact, connector runtime, market-data collection, paper order, IPC
runtime, evidence clock, scorecard writer, DB apply, GUI lane authority,
profitability claim, secret read/create/serialization, tiny-live, live, or
Bybit live execution behavior change occurred.

The strategy hypothesis contract remains source-only preregistration metadata.
It does not authorize evidence-clock start, scorecard derivation, paper orders,
profitability claims, or broker effects.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_strategy_hypothesis_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `30 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `183` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_strategy_hypothesis.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/src/stock_etf_lane_scoped_ipc.rs openclaw_types/src/stock_etf_broker_capability_registry.rs openclaw_types/tests/stock_etf_strategy_hypothesis_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

Any real hypothesis materialization, shadow-signal generation, evidence-clock
use, or scorecard derivation still requires separate reviewed runtime authority
plus PIT universe, reference data, market provenance, risk policy,
redaction/audit, and external-surface gates. First IBKR contact remains blocked
until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
