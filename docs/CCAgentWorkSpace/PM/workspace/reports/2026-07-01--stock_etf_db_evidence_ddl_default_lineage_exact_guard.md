# Stock/ETF DB Evidence DDL Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；DB evidence DDL source-only lineage hardening

## 結論

已補強 `stock_etf_db_evidence_ddl` 的 default contract、migration authority、DDL guard controls 與
source SQL auditor blocker ordering coverage。這次只改 acceptance 與 source-static guard，不改 Rust
production validator、SQL source draft、sqlx migrations、DB apply、runtime、IBKR connector、secret、paper
order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `StockEtfDbEvidenceDdlContractV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 contract id/source version drift、required schemas/tables/natural keys、migration/apply
  authority claims、guard/control gaps 固定為 exact vectors。
- Python source-static guard 新增 contract validator 與 source SQL auditor blocker ordering parser，鎖住
  exact acceptance vectors 背後的 source emit order。
- 移除 acceptance 中已不再使用的 `has` helper，避免留下 dead-code warning。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_db_evidence_ddl_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_db_evidence_ddl_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_db_evidence_ddl_acceptance`：`10 passed`。
- Full `cargo test -p openclaw_types`：`35` unit/golden + `337` integration/acceptance + `0` doc-tests。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 SQL source draft change、sqlx migration registration、DB migration/apply、PG write。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 audit writer、evidence writer、scorecard writer、paper order routing、broker session。
- 無 Linux runtime sync/restart、tiny-live/live authorization，也無 Bybit live/demo execution behavior change。
