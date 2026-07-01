# Stock/ETF Instrument Identity Authority Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；instrument identity authority hardening

## 結論

已補強 `StockEtfInstrumentIdentityV1` artifact 對 Bybit unchanged、IBKR live denial、margin/short
denial、options/CFD denial、IBKR contact、secret serialization posture 的 coverage。這次只改
acceptance 與 source-static guard，不改 Rust production code、IPC method、runtime、IBKR connector、
secret、market-data subscription、scorecard writer、DB/evidence writer、paper order route 或
tiny-live/live authority。

## 變更

- Rust acceptance 新增
  `instrument_identity_rejects_live_margin_secret_and_authority_cross_wire_independently`。
- 證明 `bybit_live_execution_unchanged=false` 只產生 `BybitLiveExecutionNotProtected`。
- 證明 `ibkr_live_denied=false` 只產生 `IbkrLiveNotDenied`。
- 證明 `margin_short_denied=false` 只產生 `MarginShortNotDenied`。
- 證明 `options_cfd_denied=false` 只產生 `OptionsCfdNotDenied`。
- 證明 `ibkr_contact_performed=true` 只產生 `IbkrContactPerformed`。
- 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- Python source-static guard 新增 accepted fixture body parser，拒絕 crypto/Bybit lane、missing instrument
  identity/as-of/calendar、Bybit changed、IBKR live not denied、margin/short/options/CFD not denied、
  IBKR contact、secret serialization 被 hardcoded 到 accepted fixture，並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_instrument_identity_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_instrument_identity_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_instrument_identity_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 market-data subscription、scorecard writer、DB/evidence writer、paper order route、tiny-live/live
  authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
