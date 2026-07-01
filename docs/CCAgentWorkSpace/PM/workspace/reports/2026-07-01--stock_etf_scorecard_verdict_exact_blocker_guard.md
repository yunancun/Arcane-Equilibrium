# Stock/ETF Scorecard Verdict Exact Blocker Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；scorecard launch verdict acceptance hardening

## 結論

已補強 `StockEtfScorecardVerdictV1` aggregate fail-closed acceptance coverage。這次只改 Rust acceptance 與 PM/Operator
記錄，不改 Rust production validator、IPC/API routes、IBKR connector、secret、socket/client construction、paper order
routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default scorecard verdict artifact 固定為完整 ordered blocker vector，覆蓋 contract/source、
  StockEtfCash/IBKR lane、hash lineage、threshold shape、review/authority 與 sealed posture。
- Rust acceptance 將 hash-lineage aggregate drift、profitability/quality aggregate failures、execution-model-invalid
  rationale、runtime side-effect aggregate failures 固定為 exact blocker vectors。
- Rust acceptance 移除 scorecard verdict blocker 的 loose `blockers.contains` helper checks；evidence/live/Bybit/writer
  cross-wire cases 改為 single-blocker 或 complete-vector assertions。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_scorecard_verdict_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_verdict_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_scorecard_verdict_acceptance`：`14 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、socket/client construction。
- 無 paper order routing、broker session、DB/evidence writer、scorecard writer。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
