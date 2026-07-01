# Stock/ETF Reference Data Sources Runtime Authority Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase3 reference-data source authority hardening

## 結論

已補強 `StockEtfReferenceDataSourcesV1` artifact 對 evidence-clock freeze、USD-only FX posture、
Bybit unchanged、IBKR contact、connector runtime、secret serialization、tiny-live/live authority posture
的 coverage。這次只改 acceptance 與 source-static guard，不改 Rust production code、IPC method、
runtime、IBKR connector、secret、reference-data ingestion、scorecard writer、DB/evidence writer、
paper order route 或 tiny-live/live authority。

## 變更

- Rust acceptance 新增
  `reference_sources_reject_runtime_freeze_and_authority_cross_wire_independently`。
- 證明 `environment=LiveReservedDenied` 只產生 `EnvironmentDenied`。
- 證明 `frozen_for_evidence_clock=false` 只產生 `EvidenceClockFreezeMissing`。
- 證明 `base_currency=UnknownDenied` 只產生 `CurrencyDenied`。
- 證明 `bybit_live_execution_unchanged=false` 只產生 `BybitLiveExecutionNotProtected`。
- 證明 `ibkr_contact_performed=true` 只產生 `IbkrContactPerformed`。
- 證明 `connector_runtime_started=true` 只產生 `ConnectorRuntimeStarted`。
- 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- 證明 `live_or_tiny_live_authorized=true` 只產生 `LiveOrTinyLiveAuthorized`。
- Python source-static guard 新增 accepted fixture body parser，拒絕 live environment、missing evidence
  freeze、missing source names/as-of、unknown currencies、Bybit changed、IBKR contact、connector
  runtime、secret serialization、tiny-live/live authority 被 hardcoded 到 accepted fixture，並鎖住
  default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_reference_data_sources_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_reference_data_sources_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_reference_data_sources_acceptance`：`7 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 reference-data ingestion、scorecard writer、DB/evidence writer、paper order route、tiny-live/live
  authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
