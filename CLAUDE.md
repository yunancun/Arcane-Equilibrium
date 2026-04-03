# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-02

---

## 一、項目定位

長期進化型 AI Agent 自動交易系統。OpenClaw 為中樞、**Bybit 為唯一交易所**（專攻）。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**交易所決策（2026-04-03）：** 早期規劃含 Binance 雙平台，現已明確專攻 Bybit。Binance 僅作為超長期可能方向保留，當前開發、設計、架構決策均不需考慮 Binance 兼容性。

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
12. **持續進化** — 系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 3 放權框架）
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 編排，正式對象通信
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**實施準則（從根原則衍生，非憲法級但強制遵守）：**
- **認知調製 ≠ 能力限制** — Agent 壓力下更審慎的方式是提高決策門檻，不是關閉能力。虛擬稀缺性（能量/積分/內部貨幣）被明確否決。（衍生自原則 #11，見 `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`）

---

## 三、當前系統狀態摘要

```
測試：3,704 passed（23 failed + 17 errors pre-existing）
路由：127+（含 8 治理 + 5 Scout + 1 Kelly 端點）
治理：GovernanceHub 4 SM，fail-closed 已驗證
品類：linear + spot + inverse（option 未來）
Agent：5/6 運行（Scout/Strategist/Guardian/Analyst/Executor，Conductor 編排待完善）
GUI：11-Tab 專業控制台 + Kelly 資本配置卡片
L1：Ollama Qwen 3.5 9B（~1.9s）/ 27B（~9.9s）
代碼完成度：~82%（現有 ~58,000 行 Py+Rs / 最終 ~73,000 行）　業務功能能用：~93%
總工時進度：~31%（已完成 ~45d / 總計 ~147d）· Python-only 58%（45/77d）
關鍵路徑：Phase 0-3（32d）→ Phase R（70d）= 102d 壁鐘 ≈ 20 週
★ Batch 9A 確定性自適應風控（2026-04-02，QC 量化審查驅動）：
  ATR 雙窗口 + 成本感知入場門檻 + 追蹤止損成本約束 + round-trip 真實費用記錄
★★★ 認知自適應 SPEC V1.1+R1（2026-04-03，五角色交叉審查 + 兩輪審計通過）：
  三個新 L0 模組：CognitiveModulator（決策門檻調製）+ OpportunityTracker（遺憾追蹤）+ DreamEngine（閒置蒙特卡洛）
  開發位置：Phase 1 並行組 B（1.10/1.11/1.12），總計 3.5d，不影響關鍵路徑
  SPEC 文件：docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md
★★★★ Rust 遷移 V3-FINAL（2026-04-03，五角色三輪審查 + 21 項嚴格論證修正）：
  Rust 交易引擎 + Python AI/GUI 雙進程架構 · 32,500 行 Rust · 14 週主開發
  Single-owner actor 零鎖 · QC 分級浮點容差 · all-or-nothing 級聯事務
  Week 8 硬決策點（Go 繼續 / No-Go 降級 PyO3，50% 復用）
  源文件：docs/references/2026-04-03--rust_migration_v3_final.md
  階段執行：docs/rust_migration/（8 個階段文件，Phase R-00 ~ R-07）
  執行時機：Phase 0-3 完成後（R-00 提前並行可在 Phase 1 開始）
★★ 中期路線圖（2026-04-03，外部改善報告 V3 Final + 4-Agent 分析）：
  Phase 0（本週）：Batch 9B+9C+9D → 業務 52%→72%
  Phase 1（Week 2-3）：Agent 感知工具箱 + 認知三模組 + ★Rust R-00 提前並行
  Phase 2（Week 3-5）：策略 V2 + Agent 整合 + ★L1 接口凍結
  Phase 3（Week 5-7）：Claude API + 四階段放權 + ★L2 接口凍結
  Phase R（Week 8-21）：Rust 遷移 14 週主開發 + 灰度 + 穩定觀察
  ★ Alpha 基準測試從 Day 1 並行跑 Paper 2 週，Day 10 決策點
  主計劃文件：docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-03--unified_execution_roadmap.md
  改善報告原文：docs/references/2026-04-03--openclaw_improvement_report_v3_final.md

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

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止硬編碼 `/home/ncyu/`。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)` 或 `Path(__file__).parent` 相對路徑。
   E2 必查：grep `/home/ncyu` 新代碼 → 打回。

2. **LocalLLMClient 抽象乾淨** — 不洩漏 Ollama-specific 細節。
   所有 LLM 調用通過 `LocalLLMClient` ABC 接口（Phase 1 任務 1.8）。
   禁止在業務邏輯中直接調用 Ollama HTTP endpoint。

3. **服務部署可遷移** — systemd → launchd 遷移路徑清晰。
   服務配置邏輯寫成文檔或腳本（`helper_scripts/deploy/`）。
   不依賴 systemd-specific 特性（如 `sd_notify`）。

4. **依賴管理乾淨** — `requirements.txt` 保持更新，禁止隱式依賴。
   新增 `import` 時同步更新 requirements。E2 必查。
   避免 Linux-only 依賴（如 `psutil` 的 Linux 特定 API），需要時加平台守衛。

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
審查：E2 代碼審查（強制）→ E4 測試回歸（強制）→ E5 優化審查（大板塊強制）
      E3/CC/A3/R4/TW 按需並行
★ E5 規則：每完成一個 Phase / Wave / 大板塊（≥3 個 E1 任務），必須跑 E5 優化審查。
  E5 範圍：新增/修改的文件，檢查代碼精簡/性能/可讀性/重複消除。
  E5 發現的問題在同一 commit 中修復，不單獨開 Phase。
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

**★★★ 當前焦點：Phase 0（Batch 9B+9C+9D）→ 讀 TODO.md 開始執行**

**統一路線圖（5 Phase + Alpha 基準 + Rust 遷移）：**
- **Phase 0**（本週）：Batch 9B 學習閉環 + 9C 管線連通 + 9D 策略 Edge → 業務 52%→72%
- **Phase 1**（Week 2-3）：Agent 感知工具箱 + 認知三模組 + **★Rust R-00 提前並行**（Cargo workspace + types crate）
- **Phase 2**（Week 3-5）：策略 V2 + Agent 整合 + 認知閉環 + **★L1 接口凍結**
- **Phase 3**（Week 5-7）：Claude API L1.5 + 四階段放權 + **★L2 接口凍結**
- **Phase R**（Week 8-21）：**Rust 遷移 14 週主開發**（R-01~R-07） · Week 8 硬決策點 · 灰度 · 穩定觀察

**Alpha 基準測試**：Phase 0 第一天開始並行跑 Paper 2 週（不寫代碼），Day 10 決策點：
- PnL > 0 → 繼續 Phase 1-3
- PnL ≈ 0 → 繼續但 Phase 2 策略升級提升優先級
- PnL < -3% → 暫緩新模組，轉策略 Alpha 研究

**關鍵文件：**
- 主計劃：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-03--unified_execution_roadmap.md`
- 改善報告：`docs/references/2026-04-03--openclaw_improvement_report_v3_final.md`
- PA 映射：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-03--improvement_report_vs_existing_code_mapping.md`
- QC 數學：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-03--improvement_report_math_validation.md`
- FA 對比：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-03--improvement_report_gap_comparison.md`
- 認知自適應：`docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`（V1.1+R1 五角色審查通過）
- Rust 遷移源文件：`docs/references/2026-04-03--rust_migration_v3_final.md`（V3-FINAL）
- Rust 階段執行：`docs/rust_migration/README.md`（8 個階段文件索引，Agent 接手入口）

**每個 Phase 的 session 上下文設計已在主計劃文件中定義（§4.1/5/6 的 session 上下文段）。**

**Live 前置條件（M/N 章前必須核驗）：**
- Paper Trading 穩定運行至少 21 天
- H0 Gate blocking 驗證（Phase 0 啟動 shadow 觀察）
- 四階段放權框架完成（Phase 3）
- 策略 Alpha 基準 > 0
- provider pricing table 正式綁定
- Rust 遷移完成（Phase R-07 灰度通過 + 穩定觀察 2 週）或 PyO3 降級方案穩定

**章節樹導航：**
A-L ✅ 全部完成 · M Supervised Live Gate ⬜ · N Constrained Autonomous Live ⬜
⚠️ 任何章節「完成」都不等於 live 放權。執行權限仍未授予。

> 參考資料（技術記錄、文檔指針、審計報告索引）見：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-03：3703 Py tests + 468 Rust tests · 131+ routes · 5 Agent · demo_only · Phase R-03 完成 · openclaw_core 24 模組：R-02 原 10 + sm/(auth+lease+risk_gov+oms) + governance_core + guardian + execution + order_match + portfolio + stop_manager + message_bus + attribution + backtest · GovernanceCore 級聯 all-or-nothing · Golden Dataset 極端組 PASS · E2 PASS + E4 零回歸 · 下一步：R-04 engine 完整交易路徑 → 讀 TODO.md。
