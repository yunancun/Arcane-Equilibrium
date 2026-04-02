# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-02

---

## 一、項目定位

長期進化型 AI Agent 自動交易系統。OpenClaw 為中樞、Bybit 為主交易所。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**系統管線：** 市場數據 → H0 本地判斷 → H1-H5 AI 治理 → I Decision Lease → 執行適配層 → 學習/歸因

---

## 二、16 條根原則（DOC-01 項目憲法 §5.1–§5.16，不可違背）

1. **單一寫入口** — 所有訂單/執行動作通過唯一受控入口
2. **讀寫分離** — 研究/GUI/學習：只讀。寫入權限極度受限、可審計、可鎖定
3. **AI 輸出 ≠ 即時命令** — AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行
4. **策略不能繞過風控** — 所有交易意圖必須經 Guardian 審批
5. **生存 > 利潤** — 先判斷「不會螺旋崩潰」，再判斷「能否盈利」
6. **失敗默認收縮** — 不確定時默認保守：不開新倉、降頻率、降風險
7. **學習 ≠ 改寫 Live** — 學習平面與 Live 平面隔離
8. **交易可解釋** — 每筆交易必須可重建：為什麼、何時、風控審批、授權、執行、結果
9. **交易所災難保護** — 本地止損 + 交易所條件單雙重防線
10. **認知誠實** — 所有結論區分事實 / 推斷 / 假設
11. **Agent 最大自主權** — P0/P1 硬邊界內，Agent 完全自主決定：幣種、策略、參數、時機
12. **持續進化** — 系統必須從交易行為中自動學習
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — OpenClaw 指揮官 + 6 Agent，正式對象通信
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

---

## 三、當前系統狀態摘要

```
測試：3,703 passed（24 failed + 17 errors pre-existing）
路由：126+（含 8 治理 + 5 Scout 端點）
治理：GovernanceHub 4 SM，fail-closed 已驗證
品類：linear + spot + inverse（option 未來）
Agent：5/6 運行（Scout/Strategist/Guardian/Analyst/Executor，Conductor 編排待完善）
GUI：11-Tab 專業控制台
L1：Ollama Qwen 3.5 9B（~1.9s）/ 27B（~9.9s）
代碼完成度：~80%　業務功能能用：~52%
★ Batch 9A 確定性自適應風控（2026-04-02，QC 量化審查驅動）：
  ATR 雙窗口 + 成本感知入場門檻 + 追蹤止損成本約束 + round-trip 真實費用記錄

Runtime 硬狀態（不可改）：
  system_mode          = demo_only
  execution_state      = disabled
  execution_authority  = not_granted
  live_execution_allowed = false
```

> 詳細歷史 Wave/Sprint/Batch 記錄見：`docs/CLAUDE_CHANGELOG.md`

---

## 四、硬邊界（永遠不能違背）

```python
system_mode             = "demo_only"
execution_state         = "disabled"
execution_authority     = "not_granted"
decision_lease_emitted  = False
max_retries             = 0

# 硬錯誤：
# - should_call_ai=true 但 invocation 沒發生
# - Bybit API timeout / retCode != 0
# - execution authority 意外被授予
# - 偽造 AI 調用或交易活動
# - 自動改 live 配置 / 自動放開 execution authority
```

---

## 五、架構總覽

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 126+ 路由
[GUI + Learning]         11-Tab 控制台 + Learning Cockpit + Paper Trading Dashboard
[Paper Trading Engine]   7 狀態生命週期 / 成交模擬 / PnL / 治理 gate 接入
[Layer 2 AI 推理]        L0 確定性 → L1 Ollama → L2 Claude
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

---

## 六、路徑與啟動

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作樹:   /home/ncyu/BybitOpenClaw/srv（/home/ncyu/srv ← symlink）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 啟動檢查
```bash
git status && git log --oneline -5
```

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 `[ ]` 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md，不等會話結束。

**修復完成後：** `[ ]` → `[x]`，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### 雙語注釋（強制）
每個新建/修改的函數、類、模塊必須中英對照注釋（MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼）。E2 必查。

### Sprint/Wave 完成後強制同步
1. 更新 `CLAUDE.md` §三摘要 + §十一一句話狀態
2. 新 Wave 詳細記錄追加到 `docs/CLAUDE_CHANGELOG.md`
3. 更新 GitHub `README.md`
4. 生產代碼 + TODO.md + CLAUDE.md + README.md 放同一個 commit

### Commit 時自動追加 CHANGELOG（強制）
每次 commit 已完成的工作時，同步將完成摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部（最新在前）。
格式：`### 標題（YYYY-MM-DD · commit XXXXXXX）` + 要點列表。與生產代碼同一個 commit。

### Context 接近上限時自動存檔（強制）
當檢測到會話即將觸發 compact（接近 90% context 使用量）時，**立即**將本次會話的工作進展寫入工作日誌：
- 存至 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`（N 為當日序號）
- 內容：已完成項 + 進行中項 + 未完成項 + 關鍵決策 + 下一步指引
- 目的：確保後續 session（無論是 compact 後的延續還是新 session）能無縫接手

### 每日工作日誌整合（強制）
每日最後一次 commit 前，或次日第一次接手時，將當天散落的工作日誌合併為一份整合日誌：
- 合併對象：`docs/worklogs/YYYY-MM-DD--session_progress_*.md`（同一天的所有碎片）
- 輸出：`docs/worklogs/YYYY-MM-DD--daily_summary.md`（結構化：完成項 / 關鍵決策 / 測試變化 / 遺留問題）
- 合併後刪除碎片文件，保持目錄整潔
- 如當天只有一份日誌，直接重命名為 daily_summary 即可

### 新腳本規範
MODULE_NOTE 雙語 / 輸出 latest + dated / contract check / 更新 SCRIPT_INDEX.md

### docs/ 規範
放對應分類目錄 / 命名 `YYYY-MM-DD--描述.md` / 每次更新 `docs/README.md` 索引

---

## 八、16 Agent 角色體系與強制工作鏈

> **強制規則：所有任務必須按角色分工派發，禁止 Claude 主會話身兼多職。**

### 8.1 角色定義

| 層次 | 角色 |
|------|------|
| 管理層 | **PM** 項目經理 · **FA** 功能審計師 · **PA** 項目架構師 |
| 質量保證層 | **CC** 合規檢查 · **E2** 代碼審查 · **E3** 安全審計 · **E4** 測試工程師 · **E5** 優化工程師 |
| 執行層 | **E1** 後端開發 · **E1a** 前端開發 |
| 專項審查層 | **A3** UX 審計 · **R4** 文檔審計 · **TW** 技術寫作 |
| 分析層 | **AI-E** AI 效果評估 · **QA** 最終驗收 |
| 顧問層 | **QC** 量化顧問（策略數學基礎、風控模型、回測方法論，不寫代碼） |

### 8.2 標準工作鏈

```
規劃：PM（優先級）+ FA（規格）並行 → PA（技術方案 + 派發）
執行：E1/E1a 最大並行
審查：E2 代碼審查（強制）→ E4 測試回歸（強制）
      E3/E5/CC/A3/R4/TW 按需並行
驗收：QA 端到端 → PM 最終確認
```

**E2 + E4 絕對不可跳過，任何情況均強制執行。**

### 8.3 P0 緊急快速通道

```
PA 派發 → E1 並行修復（最多 5 個）→ E2 review → E4 回歸 → PM 確認
```

> 角色激活矩陣、Workspace 規則等詳見：`docs/CLAUDE_REFERENCE.md`

---

## 九、代碼結構約定

### 文件大小限制
- **800 行** ⚠️ 警告線（E2 必須標記）
- **1200 行** 🛑 硬上限（不允許 merge）

### 模塊依賴方向（禁止循環 import）
```
state_models ← state_compiler ← state_store ← main_legacy ← main.py
其他 route 文件 ← main_legacy（通過 from . import main_legacy as base）
```

### Monkey-patch 安全
被 main.py patch 的函數（compile_state / STORE / envelope_response 等），新模塊必須通過 `main_legacy` 命名空間間接引用，不可直接 import 原始版本。

### Singleton 管理
| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `base.STORE` |
| `app` | main_legacy.py | `base.app` |
| `limiter` | main_legacy.py | `base.limiter` |

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。

### 其他
- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py

---

## 十、下一步工作指針

**當前焦點（讀 TODO.md 獲取具體任務）：**
- FA GAP 審核 7 項待修復 → `docs/governance_dev/audits/2026-04-01--fa_completion_gap_audit.md`
- C3 L5 元學習（需 FA 規格 → PA 方案 → 實現）
- 或 Phase 4 Paper Trading 21 天觀察期

**Live 前置條件（M/N 章前必須核驗）：**
- Paper Trading 穩定運行至少 21 天
- H0 Gate 確定性門控已實施並驗證 ✅
- 風控框架實測驗證 + 回測引擎驗證策略 alpha
- provider pricing table 正式綁定
- authority grant contract + execution adapter contract

**章節樹導航：**
A-L ✅ 全部完成 · M Supervised Live Gate ⬜ · N Constrained Autonomous Live ⬜
⚠️ 任何章節「完成」都不等於 live 放權。執行權限仍未授予。

> 參考資料（技術記錄、文檔指針、審計報告索引）見：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-02：3637+ tests · 126+ routes · 5 Agent · demo_only · 代碼 80% 業務 52% · 下一步讀 TODO.md。
