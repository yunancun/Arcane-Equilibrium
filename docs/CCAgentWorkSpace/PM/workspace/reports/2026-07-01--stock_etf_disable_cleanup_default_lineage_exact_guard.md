# Stock/ETF Disable Cleanup Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；disable-cleanup runbook fail-closed lineage hardening

## 結論

已補強 `stock_etf_disable_cleanup_runbook` 的 default runbook、env flag、proof、runtime/contact/secret/
launch authority blocker coverage。這次只改 acceptance 與 source-static guard，不改 Rust production
validator、runtime、service stop、secret lookup、DB cleanup、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `StockEtfDisableCleanupRunbookV1` blocker 檢查提升為完整順序向量，包含重複
  env/proof missing blockers。
- Rust acceptance 將 runbook identity drift、env flag gaps、proof gaps、contact/secret/destructive cleanup/
  launch authority claims 固定為 exact vectors。
- Python source-static guard 新增 runbook/env/proof validator blocker ordering parser，鎖住 exact acceptance
  vectors 背後的 source emit order。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_disable_cleanup_runbook_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_disable_cleanup_runbook_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_disable_cleanup_runbook_acceptance`：`7 passed`。
- Full `cargo test -p openclaw_types`：`35` unit/golden + `337` integration/acceptance + `0` doc-tests。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 service stop、runtime action、secret lookup、DB cleanup/delete/truncate。
- 無 IBKR contact、IBKR SDK import、connector runtime、paper order routing、broker session。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
