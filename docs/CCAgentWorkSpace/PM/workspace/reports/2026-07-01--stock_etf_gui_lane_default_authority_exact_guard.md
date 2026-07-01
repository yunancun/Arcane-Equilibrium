# Stock/ETF GUI Lane Default Authority Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；GUI lane display-only boundary hardening

## 結論

已補強 `stock_etf_gui_lane_contract` 的 default GUI authority、endpoint、display-only、cache/auth partition、
denied-effect operation blocker coverage。這次只改 acceptance 與 source-static guard，不改 Rust production
validator、GUI runtime、IPC/API routes、IBKR connector、secret、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `StockEtfGuiLaneContractV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 contract id/source drift、client lane state authority、effect-capable GUI surfaces、
  route/cache/auth regression evidence、denied effect operations 固定為 exact vectors。
- Python source-static guard 新增 GUI lane validator blocker ordering parser，鎖住 exact acceptance vectors
  背後的 source emit order。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_gui_lane_contract_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_gui_lane_contract_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_gui_lane_contract_acceptance`：`9 passed`。
- Full `cargo test -p openclaw_types`：`35` unit/golden + `337` integration/acceptance + `0` doc-tests。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 GUI runtime、IPC/API route、endpoint behavior change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、broker session、DB/evidence writer、scorecard writer。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
