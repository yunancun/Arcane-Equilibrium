# Stock/ETF Scorecard Inputs Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；scorecard inputs default lineage hardening

## 結論

已補強 `stock_etf_scorecard_inputs` 的 bundle 與五個 atomic input contract default exact-blocker
coverage。這次只改 acceptance 與 source-static guard，不改 Rust production validator、runtime、IBKR
connector、secret、DB/evidence writer、scorecard writer、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `StockEtfScorecardInputBundleV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 新增 cash ledger、cost model、benchmark、shadow fill model、storage capacity 五個 default
  atomic input validator 的完整順序 blocker vectors。
- Rust acceptance 補齊 accepted/template 對 `atomic_fact_input_hash`、`source_commit`、`live_fill_claimed`
  的 fail-closed/lineage 斷言。
- Python source-static guard 新增 component 與 bundle validator blocker ordering parser，鎖住 exact
  acceptance vectors 背後的 source emit order。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_scorecard_inputs_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_inputs_source_static.py --tb=short`：`10 passed`。
- `cargo test -p openclaw_types --test stock_etf_scorecard_inputs_acceptance`：`14 passed`。
- Full `cargo test -p openclaw_types`：`35` unit/golden + `337` integration/acceptance + `0` doc-tests。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 broker fill import、scorecard derivation、scorecard writer、DB/evidence writer、evidence clock start。
- 無 paper order routing、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
