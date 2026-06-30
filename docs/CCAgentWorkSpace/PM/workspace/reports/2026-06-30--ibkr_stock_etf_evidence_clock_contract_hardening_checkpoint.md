# PM Checkpoint - IBKR Stock/ETF Evidence-Clock Contract Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `stock_etf_evidence_clock_v1` source-only hardening

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the Phase 3 evidence-clock day checker. Future
Stock/ETF evidence-clock day packets must now prove exact named contract
identity, source-version alignment, lane/broker/environment binding, and
provenance hashes before a PASS_DAY or QUARANTINED_DAY shape can be accepted.

## Changed

- Added exported `STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID`.
- `StockEtfEvidenceClockDayV1` now requires:
  `contract_id`, `source_version`, `asset_lane`, `broker`, `environment`,
  `source_artifact_hash`, `market_data_provenance_contract_hash`, and
  `scorecard_input_bundle_hash`.
- The checker now rejects Bybit-live regression and checker-side IBKR contact,
  connector runtime, runtime evidence-clock start, scorecard writer, DB apply,
  serialized secret content, and tiny-live/live authority.
- `WINDOW_COMPLETE` remains rejected by the source checker alone.
- Broker capability registry, lane-scoped IPC, and Phase 0 manifest now consume
  the shared evidence-clock contract constant.
- Expanded `settings/broker/stock_etf_phase3_evidence_contracts.toml` with the
  default-blocked evidence-clock day fields.
- Updated ADR-0048, the Phase 0 named contract packet spec, settings README,
  specification register, document/initiative indexes, PM/Codex memory, and
  Operator brief.

## Boundary

No IBKR contact, no IBKR process startup, no secret read/create/serialization,
no connector runtime, no collector, no runtime evidence-clock start, no
scorecard writer, no DB apply, no GUI lane authority, no paper order, no
tiny-live, no live, and no Bybit live execution behavior change.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `33 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `174` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_phase3_evidence.rs openclaw_types/src/stock_etf_broker_capability_registry.rs openclaw_types/src/stock_etf_lane_scoped_ipc.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/tests/stock_etf_phase3_evidence_acceptance.rs openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.
