---
name: Agent 工作空間系統
description: CCAgentWorkSpace 的位置、用法和 Agent 啟動時必須讀取自身 memory 的規則
type: project
---

## 事實

2026-03-31 建立了 `docs/CCAgentWorkSpace/` 目錄，15 個 Agent 角色各自有獨立工作空間。

**Why:** 每個 Agent 啟動時需要對照自己的 workspace 工作記錄，避免重複工作或忘記上次決策。報告先存 workspace 再回報，形成可查閱的工作歷史。

**How to apply:**
- 啟動任何 Agent 時，prompt 必須包含：「啟動前讀取你的 memory.md 和 workspace 最新記錄」
- Agent 完成任務後，把報告存入 `docs/CCAgentWorkSpace/{角色}/workspace/reports/YYYY-MM-DD--描述.md`
- Agent 發現新教訓後，更新 `docs/CCAgentWorkSpace/{角色}/memory.md`
- Agent 可自行在 workspace/ 下創建新子目錄整理文件

## 目錄位置

`/home/ncyu/BybitOpenClaw/srv/docs/CCAgentWorkSpace/`

## 15 個 Agent 目錄

PM / FA / PA / CC / E1 / E1a / E2 / E3 / E4 / E5 / A3 / R4 / TW / AI-E / QA

每個目錄下有：
- `profile.md` — 角色定位、技能、激活條件（靜態）
- `memory.md` — 工作記憶、決策教訓（動態，持續更新）
- `workspace/` — 報告存檔，Agent 可自由組織子目錄
