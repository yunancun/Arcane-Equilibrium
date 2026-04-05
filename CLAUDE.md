# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-05

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
測試：3,839 Py + 790 Rust = 4,629 tests 全綠
路由：131+（含 8 治理 + 5 Scout + 1 Kelly 端點）
治理：GovernanceHub 4 SM，fail-closed · Rust GovernanceCore 級聯 all-or-nothing
      ARCH-4：H0 Gate + Cost Gate 已 fail-closed 硬化（2026-04-05）
品類：linear + spot + inverse（option 未來）
Agent：5/6 運行（Scout/Strategist/Guardian/Analyst/Executor，Conductor 編排待完善）
      ARCH-1：ExecutorAgent intent_id 去重已就位（MessageBus 路徑待 Phase 3a 激活）
GUI：11-Tab 專業控制台 + Kelly 資本配置卡片
L1：Ollama Qwen 3.5 9B（~1.9s）/ 27B（~9.9s）
Rust 引擎：openclaw_core 24 模組 + openclaw_engine 34 模組 + openclaw_types 10 types
  RE-2：WS supervisor 包裝完成（公共+私有 WS 自動退避重啟）
PyO3 橋接：openclaw_pyo3 暴露 39 個 Python 方法（BybitClient · 增量編譯 3.7s）
告警：TelegramAlerter + WebhookAlerter + AlertRouter 多通道扇出（OC-1/OC-2）
代碼完成度：~90%（~69,000 行 Py+Rs）· 業務功能：~95%
總工時進度：~36%（已完成 ~68d / 新總計 ~189d，含融合方案 105d 新增）
已知問題：OPEN 8 / RESOLVED 7（docs/KNOWN_ISSUES.md）
關鍵路徑：Phase 1 進行中（Day 0 + G1 + G2 完成，G3 下一步）
★★★★ Rust 遷移 — Go/No-Go 7/7 PASS + 全面清理完成（2026-04-04）：
  R-CUT 全部完成（RC-01~RC-15）· R-IPC 完成（IPC-01~06）
  RC-10 PipelineBridge 停用 · RC-11 engine.tick() 停用 · RC-12 重複 WS 停用
  Rust 為唯一 tick 處理引擎 · 唯一 Bybit WS 連接 · 零重複系統
  10/13 策略讀路由 Rust-first（含 klines/indicators/signals/strategies）
  GovernanceHub 5 死方法標記 deprecated · 10 個 flaky test 修復
★★★★ PYO3-BYBIT 完成（2026-04-05）：
  PyO3 橋接 Bybit V5 API — Python 直接調用 Rust 模組（零 IPC 開銷）
  39 方法：Account 8 + Order 6 + Position 4 + MarketData 8 + Instrument 6 + Util 7
  GUI demo/* 4 端點 Rust-first（balance/positions/orders/fills · source=rust_engine）
  E2 PASS（0 FAIL）· E4 4609 全綠 · E5 PASS（0 OPTIMIZE）· FA 37/37 LIVE
★★★★ Session 6 基礎設施清理完成（2026-04-05）：
  4 項 KNOWN_ISSUES 修復：RE-1(memory) RE-2(WS supervisor) ARCH-1(dedup) ARCH-4(fail-closed)
  OC-1 WebhookAlerter + OC-2 AlertRouter 多通道告警
  Bybit API handbook §2.3 Shadow Order Sync Channel 文檔
  OPEN 11→8 · RESOLVED 3→7
★★★★ Phase 1 Day 0 + G1 + G2 完成（2026-04-05）：
  Day 0：event_consumer.rs 提取（main.rs 1123→783）+ sqlx 0.8 + database/ 模組 + Docker test PG
  G1：FeatureCollector 34-dim + market_writer(klines/tickers) + feature_writer(UPSERT) + pipeline channels
  G2：market_writer 全 10 表 + fallback.rs(JSONL) + rest_poller(funding/OI/LSR) + quality_writer
  六角色審計通過（2 FAIL 已修復：34-dim docs + KlineClose emission）
  Rust 790 tests（+20 new）· 0 failures · 0 warnings
★★★★ 融合方案 v0.5（DB + ML/DL + 新聞 Agent · 20 週）：
  兩輪審計 + DB 專題 + 四角色聯合驗證 = 67 項修正
  存儲精簡 97%：5.6→0.17 GB/day · PG+TimescaleDB 確認 · 砍 PgBouncer
  ML：LightGBM Scorer + Optuna TPE + Thompson Sampling + CPCV + 黑天鵝檢測
  DL：Symbol Embedding + Regime LSTM + 時序基礎模型（3 場景）
  語言：訓練 Python / 推理 Rust ONNX / 橋接 PyO3
  設計文件：docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md
  執行計劃：docs/references/2026-04-04--execution_plan_v1.md
  ML 架構：docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md
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

### ★ 灰度驗證檢查（每次啟動必做，直到 R-07 Go/No-Go 通過）
Rust 引擎灰度驗證正在後台運行。**每次 session 啟動時先跑以下命令確認引擎健康：**
```bash
# 引擎存活？+ canary 記錄數 + 崩潰數 + 最新狀態
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
wc -l /tmp/openclaw/engine_results.jsonl
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"
```
詳細操作指南見 TODO.md 頂部「灰度驗證檢查」段。如引擎掛了按 TODO.md 指引重啟。

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

### ★ Bybit API 相關開發強制規則

**所有涉及 Bybit API 的修改或新功能開發（含 REST、WebSocket、IPC），必須先查閱 Bybit API 字典手冊確認已有功能支持：**
- **字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`
- **審計報告**：`docs/audits/2026-04-04--bybit_api_infra_audit.md`
- **開發前**：確認目標功能在手冊中是否已有對應端點。已有的直接調用，不重複實現。
- **新增端點**：實現後必須同步更新字典手冊對應 Section，保持文檔與代碼一致。
- **E2 必查**：Bybit 相關 PR 的 E2 審查必須驗證字典手冊已同步更新。

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

**★★★ 當前焦點：TD-01~03 文件拆分 → Phase 1 (5/01) → 讀 TODO.md 開始執行**

**★★ 融合路線圖（DB + ML/DL + 新聞 Agent · 20 週 · 起算 4/11）：**
- **Phase 0a**（W1）：PG 8-Schema DDL + Grafana VIEW 橋接
- **Phase 0b**（W2-3）：TimescaleDB + 壓縮/retention + requirements-ml
- **Phase 1**（W4-5）：市場數據止血 + FeatureCollector + PSI 漂移
- **Phase 2**（W6-9）：交易鏈 + Decision Context + Scorer + ONNX [+buffer]
- **Phase 3a**（W9-10）：update_params() = AGT-1
- **Phase 3b**（W11-12）：Optuna TPE + Thompson Sampling + CPCV + 黑天鵝
- **Phase 4**（W13-15）：Claude Teacher + LinUCB + 新聞 + DL-3
- **Phase 5**（W16-18）：James-Stein + DL-1 + DL-2
- **Phase 6**（W19-20）：漸進放權 + 驗收

**前期路線圖（已完成）：** Phase 0-3 ✅ · Phase R R-00~R-06 ✅ · R-07 灰度中

**關鍵文件：**
- **★ Bybit API 字典手冊：`docs/references/2026-04-04--bybit_api_reference.md`**
- **★ Bybit API 審計報告：`docs/audits/2026-04-04--bybit_api_infra_audit.md`**
- 融合方案 v0.5：`docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md`
- 執行計劃 V1：`docs/references/2026-04-04--execution_plan_v1.md`
- ML 架構 v0.4：`docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md`
- DB 設計：`docs/references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md`
- Rust 遷移：`docs/rust_migration/README.md`

**Live 前置條件（M/N 章前必須核驗）：**
- Paper Trading 穩定運行至少 21 天
- 融合方案 Phase 6 完成（漸進放權 + 壓測通過）
- Rust R-07 灰度通過
- Alpha PnL > 0
- provider pricing table 正式綁定

**章節樹導航：**
A-L ✅ 全部完成 · M Supervised Live Gate ⬜ · N Constrained Autonomous Live ⬜
⚠️ 任何章節「完成」都不等於 live 放權。執行權限仍未授予。

> 參考資料（技術記錄、文檔指針、審計報告索引）見：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-05：4629 tests 全綠（Py 3839 + Rs 790）· 131+ routes · 5 Agent · demo_only · Rust 唯一 tick 引擎 · **Phase 1 進行中**（Day 0 + G1 + G2 完成）· sqlx 0.8 PG 層 · FeatureCollector 34-dim · market_writer 全 10 表 · JSONL fallback · REST poller · 下一步：G3（PSI/ADWIN drift）→ 讀 TODO.md。
