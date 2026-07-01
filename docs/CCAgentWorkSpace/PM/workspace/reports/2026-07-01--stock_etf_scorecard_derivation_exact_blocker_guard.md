# Stock/ETF Scorecard Derivation Exact Blocker Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；scorecard derivation acceptance hardening

## 結論

已補強 `StockEtfScorecardDerivationV1` aggregate fail-closed acceptance coverage。這次只改 Rust acceptance 與
PM/Operator 記錄，不改 Rust production validator、IPC/API routes、IBKR connector、secret、socket/client
construction、paper order routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default 與 template scorecard derivation artifacts 固定為完整 ordered blocker vectors，覆蓋
  contract/source、StockEtfCash/IBKR lane、ID lineage、hash lineage、atomic/replay/separation、Bybit protection 與 sealed
  posture。
- Rust acceptance 將 ID/hash-lineage aggregate drift、runtime side-effect aggregate failures、writer/runtime aggregate
  failures 固定為 exact blocker vectors。
- Rust acceptance 移除 scorecard derivation blocker 的 loose `blockers.contains` helper checks；atomic/replay/separation/
  Bybit/writer cross-wire cases 改為 single-blocker 或 complete-vector assertions。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_scorecard_derivation_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_derivation_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_scorecard_derivation_acceptance`：`11 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、socket/client construction。
- 無 paper order routing、broker session、DB/evidence writer、scorecard writer、reconciliation writer、shadow-fill generation。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
