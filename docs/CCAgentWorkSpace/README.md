# CCAgentWorkSpace — Claude Code Agent 工作空間

本目錄是所有 Agent 角色的獨立工作空間。每個 Agent 擁有：

- `profile.md` — 角色定位、技能清單、激活條件（靜態，不常變動）
- `memory.md` — 工作記憶：學到的規則、偏好、過往決策的教訓（動態，持續更新）
- `workspace/` — 工作記錄區：存放每次任務的報告、草稿、分析輸出

## 使用規範（強制自動化協議，詳見 CLAUDE.md §13.5）

### Agent 啟動序列（強制，每次激活必須執行）
1. **讀 memory.md** — 了解自身工作狀態、已知問題、歷史決策
2. **讀最新 workspace report** — 讀 `workspace/reports/` 中按日期最新的一份；目錄為空則跳過
3. 完成以上兩步後，再執行分配的任務

### Agent 完成序列（強制，任務結束後必須執行）
1. **更新 memory.md** — 追加本次關鍵發現、重要決策、需記住的教訓（只追加，不刪除歷史）
2. **存檔報告** — 有輸出時存 `workspace/reports/YYYY-MM-DD--描述.md`；純輔助性工作（如代碼修復）可跳過
3. **Operator 報告** — 若是最終結論性報告，同時存一份到 `Operator/` 目錄

> 這兩個序列由主 Claude 在構造 Agent tool prompt 時強制注入，不依賴 sub-agent 自覺執行。

### 存檔命名格式
`YYYY-MM-DD--任務描述.md`

## Agent 目錄索引

| 目錄 | 角色 | 層次 |
|------|------|------|
| [PM/](PM/) | Project Manager — 優先級 + 批次計劃 | 管理層 |
| [FA/](FA/) | Functional Auditor — 功能規格驗收 | 管理層 |
| [PA/](PA/) | Project Architect — 技術方案設計 | 管理層 |
| [CC/](CC/) | Compliance Checker — 16 條根原則審查 | 質量保證層 |
| [E2/](E2/) | Code Reviewer — PR 審查 + 副作用識別 | 質量保證層 |
| [E3/](E3/) | Security Auditor — 安全審計 | 質量保證層 |
| [E4/](E4/) | Test Engineer — 測試覆蓋 + 回歸 | 質量保證層 |
| [E5/](E5/) | Optimization Engineer — 性能 + 可讀性 | 質量保證層 |
| [E1/](E1/) | Backend Developer — Python/FastAPI 實現 | 執行層 |
| [E1a/](E1a/) | Frontend Developer — HTML/JS/CSS | 執行層 |
| [A3/](A3/) | UX Auditor — GUI 可用性審查 | 專項審查層 |
| [R4/](R4/) | Document Auditor — 文檔質量審查 | 專項審查層 |
| [TW/](TW/) | Technical Writer — 雙語注釋 + 工程日誌 | 專項審查層 |
| [AI-E/](AI-E/) | AI Effectiveness Evaluator — AI 使用效果 | 分析層 |
| [QA/](QA/) | Quality Assurance — 端到端集成驗收 | 分析層 |
| [QC/](QC/) | Quantitative Consultant — 量化策略審計 | 顧問層 |

## 工作流程約束
- 所有 Agent 報告先存 workspace，再回報 PM/用戶
- E1/E1a 完成後必須走 E2 審查 → E4 回歸（任何情況不跳過）
- 複雜實現完成後，啟動獨立對抗性驗證 Agent
