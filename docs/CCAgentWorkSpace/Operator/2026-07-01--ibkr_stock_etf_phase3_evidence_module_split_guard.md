# Operator Brief — IBKR Stock/ETF Phase3 Evidence Module Split Guard

日期：2026-07-01
狀態：source-only maintainability checkpoint 完成

這次只做 Rust source 結構拆分：把 Phase3 market-data provenance 與 frozen-input
contract 從 `stock_etf_phase3_evidence.rs` 移到
`stock_etf_phase3_evidence/market_data.rs`，並保留原 public re-export。

結果：

- `stock_etf_phase3_evidence.rs`：982 行降到 742 行。
- 新子模組 `market_data.rs`：254 行。
- Contract 行為、fixtures、public API、FastAPI/GUI payload 都不變。

驗證已過：

- Scoped Rust `rustfmt --edition 2021 --check` PASS
- Phase3 evidence acceptance：`19 passed`
- Phase0 manifest acceptance：`6 passed`
- Full Stock/ETF FastAPI/static pytest：`120 passed`
- Full `cargo test -p openclaw_types` PASS
- Engine Stock/ETF focused test PASS
- Docs trace：`2 passed`
- `git diff --check` PASS

邊界不變：沒有 IBKR contact、SDK import、socket/HTTP、secret access、connector
runtime、read probe、collector、market-data ingestion、DQ writer、paper order、fill
import、DB/evidence/scorecard writer、evidence clock、tiny-live/live、Linux runtime
sync/restart，且沒有改動 Bybit behavior。
