# Operator Brief - IBKR Phase 0 Contract Packet

日期：2026-06-29
結論：Phase 0 governance / named contracts 已落地。

## 已完成

- ADR-0048：接受 `stock_etf_cash` IBKR read-only / paper / shadow research lane。
- AMD-2026-06-29-01：把 Bybit-only wording 修正為 active live execution 邊界 + IBKR paper/shadow 例外。
- Phase 0 named contract packet：列出 broker capability、external-surface gate、session attestation、feature flag/secret/auth matrix、lane-scoped IPC、paper lifecycle、DDL/evidence、GUI、storage、kill/disable、release packet、tiny-live eligibility 等 v1 contract。

## 不代表

- 不代表現在可上線。
- 不代表可呼叫 IBKR API。
- 不代表可建立 IBKR secret slot。
- 不代表可寫 IBKR connector 或 paper order。
- 不代表 GUI runtime stock lane 可啟用。
- 不代表 evidence clock 開始。
- 不代表 IBKR live / tiny-live / margin / short / options / CFD / transfer 可做。

## 下一步

只允許 Phase 1 source foundation：

`type/config/schema/IPC + default-OFF flags + denial tests`

仍需保護現有 Bybit runtime，不得修改 Bybit execution path。
