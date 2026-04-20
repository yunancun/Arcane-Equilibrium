---
name: Batch 9 Operator 決策
description: 2026-04-02 四個架構決策：成本門檻可接受但不能零成交、paper/demo自動重部署免確認、H0 shadow先觀察、Kelly自動資本分配
type: project
---

Batch 9 四個 Operator 決策（2026-04-02）：

1. **成本入場門檻**：可以接受低波動幣種不開倉，但不能造成看盤一天沒有成交。需設安全閥。
   **Why:** Operator 希望系統始終活躍，零成交等於無法學習和觀察。
   **How to apply:** 成本門檻公式必須有上限 cap，確保每日至少有交易機會。

2. **進化參數自動重部署**：Paper/Demo 模式不需要人工確認，Agent 完全自主。人工只確認 demo→live 的跳轉。
   **Why:** 符合原則 11（Agent 最大自主權），paper/demo 本身就是安全沙箱。
   **How to apply:** GovernanceHub 審批 gate 在 paper/demo 模式下自動放行，僅 live 模式要求 Operator 確認。

3. **H0 Gate blocking**：先 shadow 模式觀察 1 週（記錄 would-have-blocked 但不攔截），確認誤殺率後再切 blocking。
   **Why:** 穩妥過渡，避免誤殺正常交易。
   **How to apply:** H0 Gate 增加 shadow 計數器，1 週後由 Operator 審查數據再決定切換。

4. **策略資本分配**：選項 C — 全部交給 Agent 根據 Kelly fraction 自動分配資本。
   **Why:** 完全符合原則 11，Agent 應自主決定哪個策略值得投入。
   **How to apply:** Kelly fraction < 0 的策略自動降低或停止資本分配，Kelly > 0 的策略按比例分配。Agent 在 P0/P1 硬邊界內完全自主。
