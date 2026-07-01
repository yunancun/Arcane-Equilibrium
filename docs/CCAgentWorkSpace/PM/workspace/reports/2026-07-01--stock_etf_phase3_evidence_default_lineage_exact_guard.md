# Stock/ETF Phase3 Evidence Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase 3 evidence default lineage hardening

## 結論

已補強 `stock_etf_phase3_evidence` 的 default market-data provenance、collector run、DQ manifest、
evidence-clock day exact-blocker coverage。這次只改 acceptance 與 source-static guard，不改 Rust production
validator、runtime、IBKR connector、secret、DB/evidence writer、scorecard writer、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `StockMarketDataProvenanceV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 default `StockEtfCollectorRunV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 default `StockEtfDailyDqManifestV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 default `StockEtfEvidenceClockDayV1` blocker 檢查提升為完整順序向量。
- Python source-static guard 新增四個 validator blocker ordering parser，鎖住 default exact blocker emit order。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_phase3_evidence_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_phase3_evidence_source_static.py --tb=short`：`16 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance`：`24 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 market data ingestion、evidence writer、DQ writer、evidence clock start、scorecard writer、DB apply。
- 無 paper order routing、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
