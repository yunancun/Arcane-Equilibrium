# AI-E Memory — 工作記憶

## 項目上下文（2026-04-01）

- 當前 Phase：Phase 3 Batch 3A 完成
- 測試基準：3,349 collected / 3,310 passed / 21 failed / 17 errors
- 系統模式：demo_only
- AI 相關代碼：~7,726 行（9 核心模組）
- AI 相關測試：492 個測試函數（13 測試文件）

## 工作記憶

### 2026-04-01 審計關鍵發現

1. **H0-H5 治理層從概念到運行時的質變**：3/31 時 H0 未接入，H1-H5 部分存在；4/01 全部接入且有統計計數器
2. **學習管線最大風險：無持久化**（P1-AI-1）：TruthSourceRegistry + ExperimentLedger 重啟後全部丟失
3. **L2 後台線程結果被丟棄**（P2-AI-2）：H3 ModelRouter 把高複雜度信號路由到 L2，但結果僅日誌記錄，未回注決策
4. **shadow=False 已切換**：Strategist 真正產出 intent，不再是純日誌
5. **Ollama think=False 優化效果顯著**：9B 8.7s→1.9s（4.5x 提升）
6. **原則 13 合規度 90%**：缺少月度趨勢報告

### 架構決策記錄

- H1-H4 全部內嵌在 StrategistAgent（994 行），未獨立為模組。短期可接受，長期需拆分。
- cost_tracker 接口不統一（record_call vs record_ollama_call），使用 getattr 動態查找。

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-01 | AI 使用效果與開發情況評估 | docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-04-01--ai_effectiveness_audit.md |
| 2026-04-01 | (副本) | docs/audit/April01/AI-E_ai_effectiveness_audit_2026-04-01.md |
