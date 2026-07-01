# Stock/ETF Phase3 Evidence Clock Runtime Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase3 evidence-clock runtime boundary hardening

## 結論

已補強 `StockEtfEvidenceClockDayV1` artifact 對 Bybit unchanged、IBKR contact、connector runtime、
evidence clock runtime、scorecard writer、DB apply、secret serialization、tiny-live/live authority、IBKR
connector green dependency、shadow collector green dependency posture 的 coverage。這次只改 acceptance
與 source-static guard，不改 Rust production code、IPC method、runtime、IBKR connector、secret、
DB/evidence writer、paper order route 或 tiny-live/live authority。

## 變更

- Rust acceptance 新增
  `evidence_clock_day_rejects_runtime_writer_secret_and_authority_cross_wire_independently`。
- 證明 `bybit_live_execution_unchanged=false` 只產生 `BybitLiveExecutionNotProtected`。
- 證明 `checker_contacted_ibkr=true` 只產生 `IbkrContactPerformed`。
- 證明 `checker_started_connector_runtime=true` 只產生 `ConnectorRuntimeStarted`。
- 證明 `checker_started_evidence_clock=true` 只產生 `EvidenceClockRuntimeStarted`。
- 證明 `checker_wrote_scorecard=true` 只產生 `ScorecardWriterStarted`。
- 證明 `checker_applied_db=true` 只產生 `DbApplyPerformed`。
- 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- 證明 `live_or_tiny_live_authorized=true` 只產生 `LiveOrTinyLiveAuthorized`。
- 證明 `ibkr_readonly_paper_connector_green_5d=false` 只產生
  `IbkrConnectorNotGreenFiveDays`。
- 證明 `shadow_collector_green_5d=false` 只產生 `ShadowCollectorNotGreenFiveDays`。
- Python source-static guard 新增 evidence-clock `pass_day_fixture()` body parser，拒絕 live
  environment、Bybit changed、IBKR contact、connector runtime、evidence clock runtime、scorecard
  writer、DB apply、secret serialization、tiny-live/live authority、missing green dependencies、
  `WindowComplete` status 被 hardcoded 到 pass-day fixture，並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_phase3_evidence_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_phase3_evidence_source_static.py --tb=short`：`13 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance`：`22 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 evidence clock runtime、scorecard writer、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
