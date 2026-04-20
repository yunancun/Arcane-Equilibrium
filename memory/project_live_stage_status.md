---
name: Live 階段狀態
description: 系統已進入 Live 階段（Demo API key），所有功能按 Live 標準完成
type: project
---

系統自 2026-04-10 起進入 **Live 階段**，使用 Bybit Demo API key 運行完整 Live 路徑。

**Why:** Operator 確認所有基礎設施已就緒，不再是 paper-only 開發。Demo key 作為 Live 路徑的完整測試，真實 Live 僅差換 key。

**How to apply:**
- 所有新功能/修復必須按 **Live 標準**完成（不可留 "paper-only workaround"）
- 風控、對帳、降級等安全機制必須假設真金白銀運行
- 測試覆蓋率、邊界條件、fail-closed 行為要求更嚴格
- 6-RC-6（多通道告警）是唯一未完成的安全功能，阻塞於 OC-3
