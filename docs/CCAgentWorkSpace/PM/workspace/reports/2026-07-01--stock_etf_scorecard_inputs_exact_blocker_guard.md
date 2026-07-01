# Stock/ETF Scorecard Inputs Exact Blocker Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；scorecard inputs acceptance hardening

## 結論

已補強 `StockEtfScorecardInputBundleV1` 與 atomic scorecard input subcontract 的 aggregate fail-closed acceptance
coverage。這次只改 Rust acceptance 與 PM/Operator 記錄，不改 Rust production validator、IPC/API routes、IBKR
connector、secret、socket/client construction、broker fill import、paper order routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 subcontract contract/source drift、cash ledger environment/hash drift、shadow-fill broker/live
  linkage、storage forward-capacity policy、unbounded capacity limits、retention order 與 archive path safety 固定為
  exact blocker vectors。
- Rust acceptance 將 scorecard bundle derived-only/paper-shadow separation/live-fill/runtime side-effect cross-wire cases
  固定為 exact blocker vectors。
- Rust acceptance 移除 scorecard input blocker 的剩餘 loose `blockers.contains` checks；atomic 與 bundle fail-closed
  cases 改為完整 ordered-vector assertions。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_scorecard_inputs_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_inputs_source_static.py --tb=short`：`10 passed`。
- `cargo test -p openclaw_types --test stock_etf_scorecard_inputs_acceptance`：`14 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、socket/client construction。
- 無 broker fill import、paper order routing、broker session、DB/evidence writer、scorecard writer、evidence clock。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
