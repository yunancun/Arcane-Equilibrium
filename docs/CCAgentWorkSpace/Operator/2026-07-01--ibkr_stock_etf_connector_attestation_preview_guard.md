# Operator Brief — IBKR Stock/ETF Connector Attestation Preview Guard

日期：2026-07-01
狀態：source-only connector checkpoint 完成

這次只在 inert IBKR connector skeleton 補上 blocked session attestation 與 paper
attestation preview payload，讓後續 Phase 2 gate 有 typed、secret-free shape 可以接。

結果：

- `IbkrReadOnlyClient.session_attestation_preview()` 回傳 blocked session attestation
  preview。
- `IbkrPaperClientBoundary.paper_attestation_preview()` 回傳 blocked paper attestation
  preview。
- Preview payload 固定 no network、no secret、no Bybit path、accepted false。

驗證已過：

- Python changed files `py_compile` PASS
- Connector skeleton focused test：`8 passed`
- Full Stock/ETF FastAPI/static pytest：`120 passed`
- Docs trace：`2 passed`
- `git diff --check` PASS

邊界不變：沒有 IBKR contact、SDK import、socket/HTTP、secret access、connector
runtime、read probe、collector、market-data ingestion、DQ writer、paper order、fill
import、DB/evidence/scorecard writer、evidence clock、tiny-live/live、Linux runtime
sync/restart，且沒有改動 Bybit behavior。
