# Stock/ETF PIT Universe Source Authority Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase3 PIT universe source-authority hardening

## 結論

已補強 `StockEtfPitUniverseV1` artifact 對 evidence-clock freeze、survivorship-bias controls、Bybit
unchanged、IBKR live denial、IBKR contact、secret serialization posture 的 coverage。這次只改
acceptance 與 source-static guard，不改 Rust production code、IPC method、runtime、IBKR connector、
secret、market-data collection、scorecard writer、DB/evidence writer、paper order route 或 tiny-live/live
authority。

## 變更

- Rust acceptance 新增
  `pit_universe_rejects_freeze_survivorship_and_authority_cross_wire_independently`。
- 證明 `frozen_for_evidence_clock=false` 只產生 `UniverseNotFrozenForEvidenceClock`。
- 證明 `survivorship_bias_controls_present=false` 只產生 `SurvivorshipControlsMissing`。
- 證明 `bybit_live_execution_unchanged=false` 只產生 `BybitLiveExecutionNotProtected`。
- 證明 `ibkr_live_denied=false` 只產生 `IbkrLiveNotDenied`。
- 證明 `ibkr_contact_performed=true` 只產生 `IbkrContactPerformed`。
- 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- Python source-static guard 新增 accepted fixture body parser，拒絕 crypto/Bybit lane、missing universe
  identity/hash/as-of/count、missing freeze/survivorship controls、Bybit changed、IBKR live not denied、
  IBKR contact、secret serialization 被 hardcoded 到 accepted fixture，並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_pit_universe_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_pit_universe_source_static.py --tb=short`：`9 passed`。
- `cargo test -p openclaw_types --test stock_etf_pit_universe_acceptance`：`8 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 market-data collection、scorecard writer、DB/evidence writer、paper order route、tiny-live/live
  authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
