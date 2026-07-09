# Phase 0 任務計劃 — 接手與現狀研究
# Phase 0 Task Plan — Takeover & Discovery
**制定角色：** PM 項目經理
**日期：** 2026-03-29
**狀態：** 🟢 Active

---

## 0. 項目快照 / Project Snapshot

```
項目：       OpenClaw/Bybit AI Agent 自動交易系統
GitHub：     yunancun/BybitOpenClaw
代碼位置：   Ubuntu trade-core → SSHFS → Mac ~/RemoteServers/BybitOpenClaw/
治理文件：   22 份（20 正式 + 2 歷史），存放於 01_source_documents/
系統狀態：   432 tests pass | 113 routes | 10-Tab GUI | read_only/disabled/not_granted
Phase：      Phase 0（接手）— 尚無任何審核報告或修改產出
```

---

## 1. Phase 0 目標 / Objectives

Phase 0 的核心目標是**完全理解系統現狀**，為後續 Phase 1（差距分析）打下基礎。具體產出四份報告：

| # | 產出 | 負責角色 | 描述 |
|---|------|---------|------|
| O1 | 目錄結構與架構報告 | FA 框架師 | file tree 分析、模塊劃分、依賴圖、術語初稿 |
| O2 | 代碼架構報告 | E2 資深工程師 | 核心模塊解讀、數據流、技術債初步識別 |
| O3 | AI 集成報告 | AI-E AI基礎設施 | Ollama 部署狀態、L0-L2 路由、Prompt 管線、降級邏輯 |
| O4 | Phase 1 啟動計劃 | PM | 彙總 O1-O3 發現，制定 Phase 1 任務分配 |

---

## 2. 必讀資料優先級 / Required Reading

### P1 — 必讀（系統全貌）
所有 Phase 0 角色在開始任務前必須先讀完：

- `CLAUDE.md`（代碼庫根目錄 — 系統現狀、架構、Session 歷史摘要）
- `system_reference_handbook.md`（如存在 — 系統參考手冊）
- 22 份治理文件標題與結構（不需逐字讀，但需了解每份文件管什麼）

### P2 — 代碼（FA + E2 + AI-E 重點）
- `control_api_v1/` — 控制平面 API
- `paper_trading_engine/` — 模擬交易引擎
- `strategy/` — 策略模塊
- `risk_manager/` — 風控模塊
- `pipeline_bridge/` — 管線橋接
- `model_router.py` — AI 模型路由（AI-E 重點）
- `ai_reasoning_engine.py` — AI 推理引擎（AI-E 重點）

### P3 — 歷史（了解即可）
- `docs/worklogs/` — Session 1-12 工程日誌
- `docs/references/` — 參考資料

---

## 3. 任務分解 / Task Breakdown

### 任務 T0.1：FA — 目錄結構與架構審查
**角色：** FA Framework Architect（推薦 Opus）
**依賴：** 無（可立即啟動）
**輸入：** 代碼庫 file tree + CLAUDE.md
**指令：**
> 以 FA Framework Architect 角色，審查 BybitOpenClaw 代碼庫的完整目錄結構和模塊劃分。產出：
> 1. 完整目錄樹（標註每個目錄/文件的用途）
> 2. 模塊依賴圖（哪些模塊調用哪些模塊）
> 3. 目錄結構改進建議（如有）
> 4. 術語表初稿（代碼中出現的核心概念，中英對照）
>
> 報告輸出到 02_audit_reports/T0.1_FA_DIRECTORY_ARCHITECTURE.md

**預計產出：** `02_audit_reports/T0.1_FA_DIRECTORY_ARCHITECTURE.md`
**預計耗時：** 1 個 Cowork session

---

### 任務 T0.2：E2 — 代碼架構深度解讀
**角色：** E2 Senior Developer（推薦 Opus）
**依賴：** 無（可與 T0.1 並行）
**輸入：** 核心代碼模塊 + CLAUDE.md + 測試套件
**指令：**
> 以 E2 Senior Developer 角色，深度閱讀 BybitOpenClaw 代碼庫的核心模塊。產出：
> 1. 系統架構總覽（主要組件及其職責）
> 2. 核心數據流（從市場數據 → 信號 → 決策 → 執行 → 對帳的完整鏈路）
> 3. 風控管線解讀（H0→H5→I gate 的實際實現方式）
> 4. 狀態管理機制（系統用什麼方式持久化狀態？文件？數據庫？）
> 5. 技術債初步識別（明顯的代碼味道、TODO/FIXME、過時依賴）
> 6. 測試覆蓋率概覽（432 tests 覆蓋了哪些模塊，哪些沒覆蓋）
>
> 報告輸出到 02_audit_reports/T0.2_E2_CODE_ARCHITECTURE.md

**預計產出：** `02_audit_reports/T0.2_E2_CODE_ARCHITECTURE.md`
**預計耗時：** 1-2 個 Cowork session（代碼量大時可能需要分段）

---

### 任務 T0.3：AI-E — AI 集成現狀報告
**角色：** AI-E AI Infrastructure Engineer（推薦 Opus）
**依賴：** 無（可與 T0.1/T0.2 並行）
**輸入：** model_router.py, ai_reasoning_engine.py, 相關配置, DOC-08
**指令：**
> 以 AI-E AI Infrastructure Engineer 角色，審查 BybitOpenClaw 的 AI 子系統。產出：
> 1. Ollama 部署現狀（模型、配置、資源限制、健康度）
> 2. L0→L1→L1.5→L2 路由邏輯解讀（實際代碼 vs DOC-08 規範的初步比對）
> 3. Prompt 管線現狀（有哪些 prompt、用於什麼任務、格式如何）
> 4. 降級邏輯（超時/預算不足時的 fallback 路徑）
> 5. AI 預算管理現狀（$2/天上限是否已實現）
> 6. 初步建議（模型升級、Prompt 優化、性能瓶頸）
>
> 報告輸出到 02_audit_reports/T0.3_AIE_AI_INTEGRATION.md

**預計產出：** `02_audit_reports/T0.3_AIE_AI_INTEGRATION.md`
**預計耗時：** 1 個 Cowork session

---

### 任務 T0.4：PM — 彙總與 Phase 1 計劃
**角色：** PM 項目經理（Opus）
**依賴：** T0.1 + T0.2 + T0.3 全部完成
**輸入：** T0.1-T0.3 三份報告
**指令：**
> 以 PM 角色，閱讀 T0.1（FA 目錄架構）、T0.2（E2 代碼架構）、T0.3（AI-E AI 集成）三份報告。
> 產出：
> 1. Phase 0 發現摘要（關鍵事實、風險、驚喜）
> 2. Phase 1 任務分配計劃（誰做什麼、用什麼模型、預計耗時）
> 3. 初步風險登記表（已識別的阻塞項和風險）
> 4. 決策升級清單（需要 Operator 決定的事項）
>
> 報告輸出到 02_audit_reports/T0.4_PM_PHASE1_PLAN.md

**預計產出：** `02_audit_reports/T0.4_PM_PHASE1_PLAN.md`
**預計耗時：** 1 個 Cowork session

---

## 4. 執行時間線 / Execution Timeline

```
Session A（可並行）          Session B（可並行）          Session C（依賴 A+B）
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ T0.1 FA 目錄架構 │       │ T0.2 E2 代碼架構 │       │ T0.4 PM 彙總     │
│                 │       │ （可能需兩 session）│       │ + Phase 1 計劃   │
├─────────────────┤       └─────────────────┘       └─────────────────┘
│ T0.3 AI-E AI集成 │
│ （FA 做完後接著做）│
└─────────────────┘
```

**建議執行順序：**
1. **第一輪（並行）：** T0.1 + T0.2 同時啟動（不同 session 或同 session 分段）
2. **第一輪（同 session）：** T0.3 可在 T0.1 完成後、同一 session 中接著做
3. **第二輪（串行）：** T0.4 等三份報告齊全後啟動

**預估總耗時：** 3-4 個 Cowork session

---

## 5. 前置確認事項 / Prerequisites Checklist

在開始執行前，需確認以下事項：

- [ ] **SSHFS 掛載正常** — Mac 能讀寫 `~/RemoteServers/BybitOpenClaw/`
- [ ] **CLAUDE.md 存在且可讀** — 這是系統的核心文檔
- [ ] **22 份 .docx 均可用 pandoc 解析** — 測試至少一份能正常讀取
- [ ] **Git 狀態乾淨** — `git status` 無未提交的修改（避免干擾分析）

---

## 6. Phase 0 完成標準 / Exit Criteria

Phase 0 在以下條件全部滿足時結束：

1. ✅ T0.1 FA 目錄架構報告已完成並存檔
2. ✅ T0.2 E2 代碼架構報告已完成並存檔
3. ✅ T0.3 AI-E AI 集成報告已完成並存檔
4. ✅ T0.4 PM 彙總報告已完成，Phase 1 計劃已制定
5. ✅ Operator 審閱 T0.4 並批准進入 Phase 1

---

## 7. 風險與注意事項 / Risks & Notes

| 風險 | 影響 | 緩解措施 |
|------|------|---------|
| SSHFS 掛載斷開 | 無法讀代碼 | 每次 session 開始先驗證掛載 |
| 代碼庫過大，單 session 讀不完 | T0.2 延期 | 允許 E2 分 2 個 session 完成 |
| .docx 文件解析失敗 | 無法讀治理文件 | 備選：轉 PDF 後用 PDF skill 讀取 |
| 發現安全問題（密鑰洩露等） | P0 事件 | 立即停止，升級 Operator，不在報告中複製密鑰 |

---

## 8. 下一步 / Immediate Next Action

**Operator 請決定：**

1. **批准本計劃** → 我將按 T0.1 開始執行（以 FA 角色啟動目錄架構審查）
2. **調整優先級** → 告訴我您希望先做哪個任務
3. **補充信息** → 如有我遺漏的背景信息，請告知

---

*本計劃由 PM 角色制定。所有產出將存放於 `02_audit_reports/`。*
*Phase 0 不產出任何代碼修改——只有理解和記錄。*
