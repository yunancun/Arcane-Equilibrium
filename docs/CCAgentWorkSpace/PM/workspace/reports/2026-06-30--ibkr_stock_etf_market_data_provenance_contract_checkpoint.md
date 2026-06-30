# PM Checkpoint — IBKR Stock/ETF Market-Data Provenance Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `stock_market_data_provenance_v1` source-only hardening

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

本 checkpoint 加硬 Phase 3 `stock_market_data_provenance_v1` source validator，
讓 future Stock/ETF quote/bar facts 在進入 shadow-fill reconstruction 或 scorecard
前，必須攜帶 lane/broker/environment、vendor/entitlement、payload/source hashes、
received/exchange timestamps、adjustment marker、instrument identity hash、calendar
session id，以及 Bybit-live unchanged / no-contact / no-secret 邊界。

## Changed

- `openclaw_types::stock_etf_phase3_evidence::StockMarketDataProvenanceV1`
  新增 contract id、source version、`asset_lane`、`broker`、`environment`、
  `source_artifact_hash`、Bybit 保護與 no-contact/no-secret/no-live flags。
- `STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID` exported。
- Broker capability registry now requires `stock_market_data_provenance_v1` for
  market-data read, shadow-fill reconstruction, and scorecard derivation.
- 新增 blocked template：
  `settings/broker/stock_market_data_provenance.template.toml`。
- 更新 Phase 0 spec、ADR-0048、settings README、document/initiative indexes、
  SPEC register、PM/Codex memory。

## Boundary

No IBKR contact, no IBKR process startup, no secret read/create/serialization,
no connector runtime, no collector, no market-data ingestion, no scorecard
writer, no DB apply, no GUI lane authority, no paper order, no tiny-live, no
live, and no Bybit live execution behavior change.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `25 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `171` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_phase3_evidence.rs openclaw_types/src/stock_etf_broker_capability_registry.rs openclaw_types/tests/stock_etf_phase3_evidence_acceptance.rs openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.
