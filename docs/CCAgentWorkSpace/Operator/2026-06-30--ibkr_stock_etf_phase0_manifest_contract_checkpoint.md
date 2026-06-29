# Operator 摘要 — IBKR Stock/ETF Phase 0 Manifest Contract

日期：2026-06-30
範圍：IBKR `stock_etf_cash` Phase 0 manifest source-only checkpoint

## 結論

已新增 `stock_etf_phase0_contract_packet_manifest_v1` source validator。

這讓 Phase 0 named contract packet 的 machine-readable manifest 不再只是 JSON
文件，而是會被 Rust acceptance test 驗證。

## 現在能檢查什麼

- manifest schema / status / scope
- ADR / AMD / contract packet 路徑
- IBKR API baseline 只能是 loopback paper Gateway/TWS API
- live ports denied
- `ibkr_call_performed=false`
- global denials 全部存在
- contract list 完整、唯一、沒有未知項
- Phase 2 contact / Phase 3 evidence clock / Phase 4 GUI runtime / Phase 5 online / tiny-live / live 都保持 blocked

## 仍然不授權

- 不接觸 IBKR
- 不建立 secret slot
- 不啟動 connector
- 不送 paper order
- 不 apply DB migration
- 不開始 evidence clock
- 不授權 GUI lane authority
- 不授權 release
- 不授權 tiny-live / live

第一個 IBKR contact 仍需要 real secret/topology evidence + immutable Phase 2 PASS artifact。
