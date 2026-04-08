# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-08

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

> ARCH-RC1 Session 1A → 1C-3-E F-mini 詳細歷史（commits / 行數 / sub-batch）已歸檔到
> `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`。本節只記錄當前狀態。

### ★★★★ ARCH-RC1 1C-3 SHIPPED — Python 風控核心徹底退場（2026-04-08）

**契約終局**：所有交易/風控/學習/預算參數由 Rust 權威持有 = 3 個獨立熱重載 Config (Risk/Learning/Budget) + 既有 StrategyParams = **4 個 IPC 寫入面**。Python 完全廢掉風控核心，只剩 IPC 讀取 adapter。**禁止 restart-to-apply**。記憶：`project_arch_rc1_unified_config.md`。

**風控收編軌跡**：1A 前 7 套並行 → 1C-1 後 2 套 → 1C-2-F 後 1 Config 權威 + 5 engines 同步熱重載 → **1C-3-D 後 1 Rust ConfigStore 權威 + 53 行 Python RiskViewClient shim**。`risk_manager.py` 1633 → 53 行 (-97%)，刪 9 個純 Python 風控/H0/Engine 測試檔 ~6900 行（邏輯已 100% 在 Rust 748 tests 覆蓋）。

**5 engines 共飲一桶水**：`apply_risk_snapshot()` 單一傳播入口，每次 RiskConfig store 版本變化同步：
1. `intent_processor.risk_config`（Gate 0 + tick check 主引擎）
2. `intent_processor.guardian`（P0 trade intent modify verdict）
3. `paper_state.stop_config`（H0/pause 保護 fallback）
4. `h0_gate.config`（健康 + 風控欄位）
5. `governance.risk.thresholds`（6-tier 級聯狀態機）

**4 IPC 寫入面**：3 patch endpoints (`patch_{risk,learning,budget}_config`) 走 ConfigStore.replace() → version++ → tick-level hot-reload，成功時 V014 `engine_events` audit row（fail-soft）；StrategyParams 既有路徑不變。

**Operator manual governor override**（1C-3-B-2）：reason_code 白名單 / 單步 / 24h cooldown / CB&MR 鎖死 / 5min hold / V014 from-to 審計（含 rejected 分支）。Cooldown PG 持久化是 1C-4 留尾。

**1C-3-E F-mini SHIPPED**（2026-04-08 PM · `d8fb7f2` `cf3ff48`）：bridge_core.py 死引用清除 / paper_trading_routes 砍 4 dead imports / risk_routes::unhalt_session 砍 deprecated PAPER_STORE.mutate / `_h0_db_probe` 改 os.stat。

**1C-3-F SHIPPED**（2026-04-08 · `accf625` `8ff93e0` `de1ec69`）：Python `paper_trading_engine.py` 徹底退場，Rust openclaw_engine 成為 paper/demo/live 三模式唯一引擎。
- F-a Rust 補 paper-side `submit_paper_order` IPC RPC（`PaperSessionCommand::SubmitOrder` + `submit_external_order` 走 IntentProcessor 全 gate；4 個 e2e 測試）
- F-b `shadow_decision_builder.py` rewire 走 `EngineIPCClient`（async consume + Layer 2 routes lazy-build consumer）
- F-c/d 刪 `paper_trading_engine.py` 2248 行 + 13 依賴測試檔 + conftest fixtures 整塊；`paper_trading_routes.py` 內聯 `DEFAULT_INITIAL_BALANCE_USDT`；`paper_trading_wiring.py` PAPER_STORE/ENGINE 留 None stub（main.py / governance_routes / strategy_wiring 全部已 `is not None` 短路）

**1C-4 進度**：A1 ✅ (`03fee49`) · B1 Governor cooldown PG 持久化 ✅ (`e840003`，V014 replay) · **B2 Position Reconciler ✅** (`36335d7` + 降級 commit) — 30s Bybit 輪詢 + 5 級漂移分類 + warmup baseline + V014 audit。**audit-only**：QA+E2 審查發現原設計的自動 governor trigger 與 operator manual override 白名單 + B1 cooldown 語義雙重衝突，已降級為純 audit。自動收縮挪至 **Phase 6 自動收縮** 段（TODO.md 6-RC-1~8 目標規格已寫死）。**熱重載 e2e ✅** (`4780b04`，5 consumers 一次驗證)。留尾：A2 NewsPipeline scheduler（延後）/ E-Merge-4 / E2+E4+QA wrap。

**測試基準線**：engine lib **767** (+1 hot-reload e2e) · core 387 · types 27 · ml_training 35 · Python control_api **2694 passed** (21 pre-existing fail · 0 regression)。

### 歷史完成里程碑（完整細節見歸檔）

**ARCH-RC1 Session 1A → 1C-3-E F-mini**（2026-04-07~08）：詳見 `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`
- 1A 死代碼大屠殺 `7f59e9b` -270 行 · 1B Config 骨架 `0523f17` +2632/+58 tests · 1C-1 Rust call site 遷移 `2007b67` `6768381` `ef30bf1` -546 行 · 1C-2-A/B/F 熱重載 LIVE `581e1e2`..`91b5db8` 5 engines · 1C-2-C/D/E IPC+legacy migration+V014 audit `5f87bca` `de75191` `950f547` `b0fa2c6` · 1C-3-A/B/C/B-2/D/E F-mini Python 收編 `8447fbf` `c6fcd13` `9f46b06` `f8772c0` `a1cf772` `144f46f` `d8fb7f2` `cf3ff48`

**早期 Phase**：
- **Phase 0/0a/0b**: PG 8-schema + TimescaleDB + Grafana ✅
- **Phase 1**: FeatureCollector 34-dim + market_writer + drift detector ✅
- **Phase 2 (a/b/DE/FG)**: trading/context writers + ML model_manager + Scorer + Kelly Sizer + Parquet ETL ✅
- **Phase 3a**: 4 strategy StrategyParams + IPC update_params ✅
- **Phase 3b**: Optuna TPE + CPCV + Thompson Sampling + Black Swan detector ✅
- **Phase 4 + 4.1**: AI Budget + LinUCB + News + DL-3 + Claude API consumer loop ✅
- **Rust migration (R-CUT/R-IPC)**: Rust 唯一 tick/WS/account 引擎 · Python paper engine 全停 · PyO3 39 方法 ✅
- **EXT-1 Exchange-as-Truth** + **RRC-1 風控接線**（H0Gate/Cost Gate/PriceHistoryTracker 全進 Rust）✅
- **L3 12 路審計** 414 findings → R0/R1/R2/R3 全清完 ✅
- **Sessions 9-13**: PNL-1~7 + DB-RUN-1~7 + magic-number cleanup + Session 13 R3 收尾 ✅

詳細逐 Sprint/Wave 條目歸檔於 `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`，逐 commit 條目見 `docs/CLAUDE_CHANGELOG.md`。

### Runtime 硬狀態（不可改）
```
system_mode             = demo_only
execution_state         = disabled
execution_authority     = not_granted
live_execution_allowed  = false
```
**Live 前唯一 blocker**：7d paper trading 數據觀察期（calendar-time）。

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

**★★★ 當前焦點：L3 審計整改（63 issues · 11 WP · PA 報告）→ Phase 4 (7/03) → 讀 TODO.md 開始執行**

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

> 截至 2026-04-08：engine lib **767** · core 387 · types 27 · Python control_api **2694 passed** (21 pre-existing fail · 0 regression) · **ARCH-RC1 1C-3 全部 SHIPPED + 1C-4 A1/B1/B2 SHIPPED + hot-reload e2e SHIPPED** — Python 風控/紙盤雙退場 · Governor cooldown V014 replay (`e840003`) · **Position Reconciler audit-only**：30s Bybit 輪詢 + 5 級漂移分類 + warmup baseline + V014 audit (`36335d7` + 降級 commit)，原設計自動 governor 收縮經 QA+E2 審查降級移除，挪至 **Phase 6 自動收縮**（TODO.md 6-RC-1~8 規格已寫死）· **熱重載 e2e** (`4780b04`) 一次驗證 5 consumers · Rust openclaw_engine 為 paper/demo/live 唯一引擎 · 1 ConfigStore 權威 + 5 engines 熱重載 + 4 IPC 寫入面 + V014 audit · Live 前 blocker：**7d paper trading 數據觀察期** + **多通道告警上線**（B2 降級後 drift 只進 audit，需 operator 通知通道）· 下一步 1C-4 留尾：E-Merge-4 / A2 News scheduler（延後）/ E2+E4+QA wrap。詳細歷史見 `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`。
