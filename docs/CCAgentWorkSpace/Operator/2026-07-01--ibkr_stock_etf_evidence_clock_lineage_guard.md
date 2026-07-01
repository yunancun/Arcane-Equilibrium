# Operator Brief — IBKR Stock/ETF Evidence Clock Lineage Guard

日期：2026-07-01
狀態：source-only checkpoint 完成

本輪把 `stock_etf_evidence_clock_v1` 補成必須帶 collector run 與 DQ manifest 的
contract id/hash lineage。現有 Evidence Status panel 會顯示這些 lineage/hash
presence；沒有新增 endpoint、IPC method 或 GUI fanout。

驗證已過：

- Python changed files `py_compile` PASS
- Stock/ETF evidence/fallback JS `node --check` PASS
- Scoped Rust `rustfmt --edition 2021 --check` PASS
- Phase3 evidence acceptance：`19 passed`
- Phase0 manifest acceptance：`6 passed`
- Focused evidence-status pytest：`4 passed`

邊界不變：沒有 IBKR contact、SDK import、socket/HTTP、secret access、connector
runtime、read probe、collector、market-data ingestion、DQ writer、paper order、fill
import、DB/evidence/scorecard writer、evidence clock、tiny-live/live、Linux runtime
sync/restart，且沒有改動 Bybit behavior。
