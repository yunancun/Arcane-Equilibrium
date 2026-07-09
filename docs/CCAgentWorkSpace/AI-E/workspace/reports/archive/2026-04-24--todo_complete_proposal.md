# AI-E 完整 TODO 提案（2026-04-24）
## AI 治理層 + 5-Agent + ML 管線完整接線藍圖

**編製**：AI-E (AI Effectiveness Evaluator)  
**日期**：2026-04-24  
**基礎資料**：
- 2026-04-01 AI Effectiveness Audit（H1-H5 基線）
- 2026-04-24 AI Integration / Usability / Development Maturity Audit（當前全面盤點）
- 2026-04-12 AI Usage Assessment Report（API / 模組清單）
- 當前 TODO.md（328 行 G1-G6 Wave 結構）

**核心使命**：對比三份審計報告 + 當前 TODO，列出所有**等級 1 條不落的 AI TODO 提案**，涵蓋：
1. 歷史 findings 清算
2. 當前 TODO 涵蓋度核實
3. 遺漏項完整列舉
4. 4 大 AI 子系統成熟度評分
5. AI ROI 監控清單
6. 給 PA 的驗證重點

---

## A. AI-E 歷史報告盤點

### A.1 2026-04-01 基線

**H1-H5 成熟度（自評）**：
| H | 完成度 | 狀態 | 運行時接入 |
|----|--------|------|----------|
| H0 | 100% | A（Production） | ✅ pipeline_bridge + risk_manager |
| H1 | 90% | B+ | ✅ StrategistAgent 內嵌 |
| H2 | 85% | B | ✅ Layer2CostTracker |
| H3 | 80% | B | ✅ StrategistAgent._h3_route_model，但 L2 結果丟棄（P2-AI-2 未修） |
| H4 | 75% | B- | ✅ _validate_ai_output，但僅驗 confidence（P2-AI-3 有改進） |
| H5 | 80% | B | ✅ 雙端 record（Python + Rust BudgetTracker） |

**5-Agent + Layer 2**：shadow=False 切換（Strategist live）；Layer 2 Claude Loop 僅手動觸發。

**關鍵 P0-P2 未清**：
- **P1-AI-1**：TruthSourceRegistry + ExperimentLedger 無持久化（重啟丟失）
- **P2-AI-2**：H3 L2 結果丟棄，無回注機制（4/01 時已標未修）
- **P2-AI-4**：Conductor Agent 未完善（缺自動編排、健康檢查、重啟）
- **P2-AI-5**：AnalystAgent L2 觸發閾值 200 在 demo 難達（4/01 時已標未改）

### A.2 2026-04-24 當前審計（交叉驗證發現）

**重大差異**（vs 4/01 敘述）：

| 項 | 4/01 敘述 | 4/24 實測 | 差異 |
|---|---------|---------|------|
| H0 Gate | 832 行 + 99 tests | **971 行**（+17%） | 強化 ✅ |
| StrategistScheduler | 不存在 | **1,612 行 live 5-min cycle**（Rust）+ Ollama 呼叫 proven | 全新發現 |
| Python AI 總行數 | 7,815 | **10,959**（+40%） | H1/H3/H4 拆分 + local_llm_factory + ai_service 等 |
| Rust AI 總行數 | — | **8,942 新增**（ai_budget / claude_teacher / edge_predictor / linucb / ml / news） | 全新 Rust 層 |
| ExecutorAgent | live shadow=False | **`_shadow_mode=True` 默認**（executor_agent.py:482，設計意圖但未切換） | 實測打破 4/01 敘述 |
| ScoutAgent | live（全） | **live 僅技術面**（MarketScanner only；新聞/宏觀/事件全 stub） | 4/01 未提及 |
| Layer 2 自主循環 | 架構完整 | **無 autonomous trigger**（只手動 POST /api/v1/paper/layer2/trigger） | gap 確認 |
| ai_usage_log | 0 rows（預期） | **0 rows**（BudgetTracker 雖 init 但 record_usage 未被呼叫） | gap 深化 |
| strategist_applied_params | 0 rows（預期） | **0 rows + engine.log 證實全被 delta guard 拒絕** | root cause found |
| teacher_directives | 0 rows（預期） | **0 rows + DEFAULT-OFF phase 4.1 contract** | 符合設計 |
| edge_estimator_scheduler | 正常運作（假設） | **4 天停滯**（mtime 停在 2026-04-20） | 🔴 P0 blocker 發現 |

### A.3 2026-04-12 API / 模組清單核實

**39 個 AI 相關 routes（curl 實測都 live）**，但 AI 功能實際觸發率：
- `POST /api/v1/paper/layer2/trigger` — 手動按鈕，非自主
- `GET /api/v1/paper/layer2/ollama/status` — 狀態查詢
- `POST /api/v1/ai_budget/config` — 配置（無調用記錄）
- Scout/strategist/learning/* — routes 存在，實際觸發率不明

**核心發現**：代碼總行數 19,901 行（Python 10,959 + Rust 8,942），但真實 runtime 產出 AI 決策的比例下降（大量 dormant / shadow）。

---

## B. 未入當前 TODO 的 AI 活躍項

### B.1 阻塞 AI 路徑的 P0 級隱藏 gap

| # | 項 | 根因 | 影響 | 狀態 |
|----|---|------|------|------|
| **BI-01** | edge_estimator_scheduler 4 天停滯（mtime 2026-04-20 停滯） | daemon 未執行或異常退出？ | 無邊界估計更新 → cost_gate 無實際邊界數據 → G-4 決策無法進行 | 🔴 P0（MIT-01 G1 audit 提及但 TODO 未敘述根因診斷） |
| **BI-02** | PostOnly 配置反向（demo=false, live=true） | FA 審計發現 | 違反原則 #6（失敗默認收縮）→ live 會默認 PostOnly OFF，高滑點 | 🔴 P0（FA-01，TODO G1-05 已列但缺根因核實） |
| **BI-03** | ExecutorAgent `_shadow_mode=True` 硬編碼默認 | executor_agent.py:482 設計意圖 | Path A/B 衝突防護，但缺 shadow→live 切換機制 | 🟡 P0（TODO G3-02 涵蓋但需 RFC） |
| **BI-04** | StrategistScheduler proposal 全被 ±30% delta guard 拒（engine.log 01:06/01:11/01:16 三次 100% reject） | Ollama 9B 推議的 cooldown_ms 60→150 ms 超大幅 | param 優化管線死路 → strategist_applied_params=0 rows → AI tuning 無輸出 | 🟡 P1（engine.log 證實，TODO G2/G3 未聚焦此 gap） |
| **BI-05** | Layer 2 Claude Agent Loop 無 autonomous trigger + ANTHROPIC_API_KEY 未設 demo env | layer2_engine.run_session 設計上依賴手動觸發 | 原 memory 敘述「Layer 2 自主推理循環」未兌現 → demo 不產 Claude intent | 🟡 P1（4/24 審計 P2-AI-NEW-1） |
| **BI-06** | ScoutAgent 新聞 / 事件 / 宏觀 intel 全 stub（只有 MarketScanner 技術面） | memory 敘述「Layer 2 自主推理循環含新聞搜索」暗示有新聞源，實測 stub | Strategist AI 缺新聞 context → edge 評估失真 | 🟡 P1（4/24 審計 P1-AI-NEW-1，TODO 未列） |
| **BI-07** | Rust `ai_usage_log = 0 rows`（BudgetTracker.record_usage 未被呼叫） | strategist_scheduler + teacher_loop 的記錄點未接 | Rust AI 成本無 audit trail → 違反原則 #13（資源成本感知） | 🟡 P1（4/24 審計 P1-AI-NEW-2） |
| **BI-08** | Rust `strategist_applied_params = 0 rows`（所有 proposal 被 delta guard 擋） | ±30% guard 正常工作，但 Ollama proposal 超界 | param tuning 管線實質無輸出 → AI agent 學習不動 | 🟡 P1（4/24 審計 P1-AI-NEW-2） |

### B.2 活躍但未完成的 AI 功能

| # | 項 | 當前狀態 | 缺陷 |
|----|---|---------|------|
| **BI-09** | H3 L2 後台線程結果緩存 | 已加 cache（same symbol 下次 tick 用） | 缺 per-symbol cache timeout + eviction 策略（L2 cache validity decay？） |
| **BI-10** | Model Registry canary flow | V023 migration + 3 routes + state machine | 3 rows 全 shadow，無 promote 操作發生；Phase 3+ Rust consumer（OnnxModelManager）未接 |
| **BI-11** | AI Service IPC（Rust↔Python） | 5 handlers 定義，ai_service.sock live | strategist_evaluate 實測；analyst/conductor/scout/guardian runtime 成功率未驗 |
| **BI-12** | INFRA-PREBUILD-1 Part A（Combine Layer shadow） | shadow_enabled=false dormant，`decision_shadow_exits=0 rows` | Phase 3+ flip 時機不明 |

---

## C. AI-E 完整 TODO 提案（~50 條分級）

### C.1 🔴 Critical Blockers（必須立即處理，影響後續）

#### Wave 1（W17/18）— 基礎設施解凍

**C1-01 [G1-01·MIT]** edge_estimator_scheduler 診斷 + 恢復  
- **Issue**：daemon 4 日停滯，cost_gate 無實數據
- **Action**：grep cron / ps 檢查 scheduler process / tail log / 檢查 file lock  
- **DoD**：mtime ≥ 當前 -24h / healthcheck [13] PASS
- **Report Ref**：MIT 4/24 audit，fn-01（診斷根因）

**C1-02 [BI-02·FA]** PostOnly 配置反向修復  
- **Issue**：settings/strategy_params_live.toml demo=false, live=true 反向
- **Action**：讀取兩個 TOML → 修正結構 / 補單元測
- **DoD**：demo=true, live=false（失敗默認收縮）
- **Report Ref**：FA 4/24 audit，finding-03

**C1-03 [G1-02·E1+PA]** event_consumer/mod.rs 拆分（1696 行 → <1200 行）  
- **Issue**：超過 1200 行硬上限（CLAUDE.md §九）
- **Action**：E1 拆 fn / PA review RFC / E2 審查
- **前置**：C1-01, C1-02 完成
- **工時**：3-4d（PM 調整 1）
- **DoD**：Rust engine lib 1980 tests + 0 failed；E2 approve；merge
- **Report Ref**：E5 4/24 audit，G1-02 tracking

**C1-04 [BI-04·E1]** StrategistScheduler prompt 校正（delta guard 全拒 → calibration）  
- **Issue**：Ollama 9B 提議的 cooldown_ms delta 超 ±30%（60→150 ms，150% 變化）
- **Action**：audit engine.log rejected proposals → extract patterns → adjust judge_edge prompt / 考慮 bounded output constraint
- **DoD**：engine.log 3 次連續 cycle proposal accept rate > 30%（不要求 100%，guard 有效）
- **工時**：2-3d
- **Report Ref**：P3-AI-NEW-1（4/24）；E5 review

**C1-05 [BI-03·E1+PA]** ExecutorAgent shadow→live RFC（G3-01 prerequisite）  
- **Issue**：缺 Path A/B 衝突 contract + IPC 切換機制
- **Action**：PA/E1 聯合寫 RFC → design ConfigStore + IPC patch_executor_config msg
- **前置**：C1-02 (event_consumer 拆) 後 codebase 狀態穩定
- **工時**：1d RFC + 2-3d implementation（見 G3-02）
- **DoD**：RFC doc approved by E2 + FA；伪代碼通過 E4 走讀
- **Report Ref**：G3-01 (TODO) + BI-03

---

### C.2 🟠 High Priority（1-2 週內做完）

#### Wave 1 續（W17/18）

**C2-01 [BI-07·MIT]** BudgetTracker.record_usage Rust 端 call-site 追查  
- **Issue**：ai_usage_log=0 rows，意味 record_usage 從未被觸發
- **Action**：grep all call-site（strategist_scheduler / teacher_loop / analyst）→ 補 missing call 或檢查條件阻擋
- **DoD**：ai_usage_log ≥ 1 row（即使 cost=$0，也要 audit trail）
- **工時**：2-3h
- **Report Ref**：P1-AI-NEW-2（4/24 審計）

**C2-02 [BI-06·E1+Scope]** ScoutAgent 新聞源路由（決策：Rust news → Python Scout vs Python 獨立實作）  
- **Issue**：Rust news pipeline 2,231 行完整但不 route 到 Python ScoutAgent；Python Scout 新聞 / 事件 / token_unlock 全 stub
- **Action**：
  - Option A：IPC message ScoutAgent send IntelObject from Rust news（2-3d）
  - Option B：Python 獨立實作新聞爬蟲（4-5d，需 API keys）
- **Decision Point**：PA + PM 定 option → E1 執行
- **工時**：取決 option
- **Report Ref**：P1-AI-NEW-1（4/24）；不在 TODO 中

**C2-03 [BI-08·E1+E4]** StrategistScheduler proposal validation 細化（delta guard 邏輯 review）  
- **Issue**：±30% guard 工作但全拒，背後邏輯是否過嚴？
- **Action**：E1 review strategist_scheduler/mod.rs delta check 邏輯 → 可能調整閾值 or prompt tuning（見 C1-04）→ 3 次迴圈實驗
- **DoD**：min accept rate > 20%；log proposal accept/reject ratio 可觀測
- **工時**：3-4d（含迴圈）
- **Report Ref**：引擎日誌 + BI-04 / P3-AI-NEW-1

#### Wave 2（W19）— AI 接線 + 架構合規

**C2-04 [BI-05·E1+PA]** Layer 2 autonomous 升級觸發規則（G3-06 prerequisite）  
- **Issue**：當前無自主觸發；memory 敘述「自主推理循環」未兌現
- **Action**：
  1. 定義 trigger criteria（market regime shift / vol spike / strategy drawdown 等）
  2. 實裝 check on main tick loop（Rust 或 Python IPC 呼叫 run_session）
  3. ANTHROPIC_API_KEY 配置 demo env（新增）
- **DoD**：L2 session auto-fire at least 1x/day in demo；reasoning chain logged to PG `learning.pattern_insights`
- **工時**：2-3d
- **Report Ref**：P2-AI-NEW-1（4/24）；不在 TODO 中；G3-06 跟蹤

**C2-05 [G4-01·MIT]** Labels 累積加速（per-strategy pooled）  
- **Issue**：當前 `learning.exit_features=244 rows`，達 200+ threshold 滿一週需解凍訓練管線
- **Action**：commit `PipelineConfig.symbol` Optional（pool across symbols）→ exit_features 累積 ≥200 pooled labels
- **DoD**：exit_features ≥ 200 rows；per-strategy breakdown ≥ 50 each（grid_trading minimum）
- **工時**：1-2d setup + passive wait 7d
- **Report Ref**：G4-01（TODO）；MIT audit tracking

---

### C.3 🟡 Medium Priority（接下來 2-3 週）

#### Wave 2-3 續（W19-W23）

**C3-01 [G3-02·E1+PA]** ExecutorAgent shadow→live toggle 實裝（IPC patch）  
- **Issue**：RFC 完成後工程化實裝
- **前置**：C1-05（RFC）
- **Action**：
  1. Rust add `PipelineCommand::PatchExecutorConfig { shadow_mode: bool }`
  2. Python add API `PATCH /api/v1/executor/shadow-toggle` (Operator-gate)
  3. e2e test shadow intent → live intent path 切換
- **DoD**：shadow false 後新 intent 走 SubmitOrder IPC；E4 e2e test green
- **工時**：2-3d
- **Report Ref**：G3-02（TODO）

**C3-02 [G3-08·E1+PA]** H1-H5 → Rust IPC Gateway（Rust tick pipeline 享受 AI 閘門）  
- **Issue**：當前 H1-H5 僅在 Python Agent 框架；Rust pipeline（tick_pipeline 直接 SignalEngine→IntentProcessor）不經過 AI 閘
- **Action**：
  1. Rust tick_pipeline 加 IPC call `evaluate_signal` 到 Python（類似 strategist_evaluate）
  2. IPC 回傳 H1-H5 verdict 後 apply gate logic
  3. 或：Rust 複製 H1-H5 邏輯（budget check / complexity score）
- **Decision**：E5 + PA 設計（重複 vs IPC）
- **工時**：3-5d
- **Report Ref**：G3-08（TODO）

**C3-03 [G3-09·AI-E]** `cost_edge_ratio` 原則 #13 演算法實裝  
- **Issue**：cost_edge_ratio ≥ 0.8 → 建議關倉（原則 #13），但演算法未正式定義
- **Action**：
  1. AI-E 定義：cost_edge_ratio = (Ollama $0 cost + Claude cost 30d) / (positive edge PnL) ？
  2. 或：rolling cost / rolling edge （更 real-time）
  3. 實裝 compute & persist to learning.cost_edge_tracking
  4. GUI tab-ai.html 曝露 threshold warning
- **DoD**：formula documented + computed daily + ≥3d 歷史追蹤
- **工時**：2d
- **Report Ref**：G3-09（TODO）

**C3-04 [BI-09·E1]** H3 L2 cache 完善（TTL / eviction / per-symbol validity）  
- **Issue**：4/01 P2-AI-2 未修；cache added 但 TTL 固定 1h 可能不適應市場
- **Action**：
  1. Add cache validation check per-symbol（last market vol / regime change）
  2. Add TTL dynamic adjustment（volatility → shorter TTL）
  3. Test same-symbol consecutive ticks 都用 cache
- **DoD**：cache hit ratio ≥ 50% same-symbol within 1h window
- **工時**：1-2d
- **Report Ref**：P2-AI-2（4/01）；4/24 未重驗但沿用

**C3-05 [P1-7 C + G4·MIT]** run_training_pipeline 首跑（grid_trading pooled labels ≥200）  
- **Issue**：目前 labels pooled=244，達到閾值；需跑訓練產首個 ONNX artifact
- **Action**：
  1. 確認 exit_features=244 + decision_features=6.19M ready
  2. 運行 `python run_training_pipeline.py --skip_onnx=False grid_trading`
  3. 檢查 ONNX 輸出 + 產首行 `learning.model_registry` entry
- **前置**：C2-05（labels ≥200）
- **DoD**：model_registry ≥ 1 row（grid_trading, canary_status=shadow）；ONNX artifact stored
- **工時**：4h（script run + QC）
- **Report Ref**：G4-02（TODO）；P1-7 tracking

**C3-06 [G4-03·E1]** model_registry canary auto-promote rules 實裝  
- **Issue**：V023 migration 完成，但 promote 狀態機未自動化；依賴 operator 手動 `POST /model_promote`
- **Action**：
  1. 定義 auto-promote rules（e.g. canary running 3d + validation loss < threshold）
  2. 實裝 Phase 3+ cron（當前 4.1 延後到 Phase 3）
  3. 設計 operator confirm dialog（irreversible）
- **DoD**：canary → promoting → production flow 可手動 trigger；health check [9] monitor freshness
- **工時**：2d（實裝 + test）
- **Report Ref**：G4-03（TODO）；model_registry audit

---

### C.4 🔵 Lower Priority（Phase 4+ 或 conditional）

**C4-01 [BI-10·E1+E5]** edge_predictor 完全激活（use_edge_predictor=true + shadow_mode=false）  
- **Issue**：2,965 行 Rust ONNX code 全 dormant（use=false）
- **Action**：
  1. 產首個 ONNX quantile model（q10/q50/q90）→ register in model_registry
  2. flip config + 7d shadow observation
  3. 驗證 exit decision 改進
- **前置**：C3-05（ONNX artifact）+ C3-06（registry auto-promote）
- **工時**：3-5d（含 shadow observation）
- **Report Ref**：P2-AI-NEW-2（4/24）；不在 TODO 中

**C4-02 [BI-11·E1+E4]** AI Service IPC 5 handlers 完整驗證  
- **Issue**：strategist_evaluate 實測通；其他 4 handlers（analyst/conductor/scout/guardian）未驗
- **Action**：
  1. E4 跑 e2e test：各 agent 通過 IPC 呼叫完整路徑
  2. 檢查 latency + error handling + timeout
- **DoD**：5 handlers all green in e2e；average latency < SLA
- **工時**：1-2d
- **Report Ref**：ai_service IPC（4/24 審計）

**C4-03 [BI-12·E1]** INFRA-PREBUILD-1 Part A 完全啟用（Combine Layer shadow flip）  
- **Issue**：shadow_enabled=false，Phase 3+ flip ON + 14d 對比 physical vs ML exit
- **Action**：
  1. flip TOML / IPC `shadow_enabled=true`
  2. healthcheck [8] monitor `learning.decision_shadow_exits` rows
  3. 14d 對比 analysis（exit quality）
- **前置**：C3-05（ONNX artifact）；Phase 3 decision
- **DoD**：decision_shadow_exits ≥ 100 rows；no silent deadlock；E4 health check all green
- **工時**：passive 14d + 2d analysis
- **Report Ref**：INFRA-PREBUILD-1 Part A（4/23 audit）；G4-05（TODO）

**C4-04 [G-7·E1+E3]** Claude Teacher loop 啟用（teacher_loop_enabled=true）  
- **Issue**：Rust claude_teacher 3,757 行完整但 DEFAULT-OFF phase 4.1 contract
- **前置**：21d demo stable + E3 R6 audit PASS
- **Action**：
  1. E3 audit claude_teacher directives quality
  2. flip `teacher_loop_enabled=true` + `ANTHROPIC_API_KEY`
  3. 觀察 `learning.teacher_directives` + `learning.directive_executions` rows
- **DoD**：teacher_directives ≥ 5 rows/week；execution success rate > 80%
- **工時**：2-3d（E3 audit）+ passive 7d（observation）
- **Report Ref**：G-7（TODO P2）；claude_teacher（4/24 審計）

**C4-05 [G-10·E1]** Calibration.py 整合（isotonic ECE < 0.05）  
- **Issue**：當前 calibration.py 僅 placeholder；ONNX quantile predictor 需校準
- **Action**：
  1. run_training_pipeline stage 5.5 → isotonic regression fit
  2. 驗證 ECE（expected calibration error）< 0.05
  3. 持久化 calibrator + apply at inference
- **前置**：C3-05（ONNX artifact）
- **工時**：2d
- **Report Ref**：G-10（TODO P2）；calibration.py audit

---

### C.5 📊 AI ROI 監控 TODO（新增，4/24 審計發現）

**C5-01 [AI-E]** ai_usage_log 每日匯總報告（缺 4/01 改進建議 #7）  
- **Issue**：4/01 建議「AI 使用效果自動評估儀表板」未落地；ai_usage_log=0 rows 外，也缺每日成本 summary
- **Action**：
  1. 補 `/api/v1/ai-stats` endpoint（GET daily/monthly summary）
  2. 暴露：H1 skip 計數 / H3 路由比例 / H4 驗證失敗率 / Ollama 延遲分佈 / StrategistScheduler accept rate
  3. GUI tab 曝露
- **DoD**：endpoint live；daily cron 更新 snapshot；GUI 可視化 7d trend
- **工時**：2-3d
- **Report Ref**：4/01 改進建議 #7（未落地）；4/24 P2-AI-NEW-4

**C5-02 [AI-E]** cost_edge_ratio 月度 ROI 計算（原則 #13 延伸）  
- **Issue**：當前有 daily cost tracking，缺 ROI 計算（cost vs PnL）
- **Action**：
  1. 每月彙總：total Claude cost + Ollama cost（記錄用）vs positive edge PnL
  2. 計算 ROI = edge PnL / total cost（需 ≥ 0.5 per DOC-08）
  3. 若 ROI < 0.5 → alert → trigger cost_gate 關倉建議
- **DoD**：monthly ROI computed；alert triggered if < 0.5；documented in AI tab
- **工時**：1-2d
- **Report Ref**：DOC-08 §3；原則 #13

**C5-03 [AI-E+QC]** StrategistScheduler accept rate 監控（新增，4/24 發現 0% reject）  
- **Issue**：當前 engine.log 顯示 100% reject（3/3），但無儀表板顯示
- **Action**：
  1. strategist_scheduler 記錄 proposal / accept / reject count per 5min cycle
  2. 持久化到 `learning.strategist_proposal_stats` 或 log 檔
  3. healthcheck [15]：accept rate threshold（warn if < 20%）
- **DoD**：per-5min stats persisted；GUI tab 顯示 hourly aggregate；healthcheck working
- **工時**：1d
- **Report Ref**：BI-04 / BI-08；engine.log evidence

**C5-04 [AI-E+E4]** Ollama model performance benchmarking（4/24 未測）  
- **Issue**：前置 4/01 P2-AI-1（is_available 同步阻塞）；需測 Ollama 9B/27B 延遲分佈
- **Action**：
  1. 跑 judge_edge 20 次，記錄 latency
  2. 檢查 warmup effect（first call vs 10th）
  3. 若 p95 > 3s SLA，觸發告警
- **DoD**：benchmark results documented；SLA check result；optimization recommendation（if needed）
- **工時**：0.5d（benchmark） + 1d（optimization if needed）
- **Report Ref**：4/01 P2-AI-1；Ollama audit

---

## D. 4 大 AI 子系統成熟度評分

### D.1 AI Governance Layers（H0-H5）

```
成熟度 0-100% 量表：
  0-20%:  Stub / 代碼存在但無 runtime caller
  20-40%: Skeleton / 框架完整但 gate 未接
  40-60%: Shadow / live 記錄但不影響決策
  60-80%: Active / 實際影響但還有 gap
  80-95%: Production-grade / 生產就緒
  95%+:  Mature + 觀測性強

H0 (Deterministic Gate)
├─ 5 checks: freshness / health / eligibility / risk_envelope / cooldown
├─ Code: 971 lines + 99 tests
├─ Runtime: live (pipeline_bridge + risk_manager + GUI)
├─ Gap: 無
└─ Score: 95% ✅ Production-mature

H1 (ThoughtGate - Budget/Complexity/Cooldown)
├─ Code: 185 lines (h1_thought_gate.py, 獨立模組)
├─ Runtime: Active (StrategistAgent.on_message)
├─ Gap: 僅在 Python Agent 框架；Rust pipeline 無 H1
│       (C3-02 計劃補) + budget_check fail-open (待 BI-07 修)
└─ Score: 70% 🟡 Active but incomplete gate

H2 (Budget Control)
├─ Code: Python Layer2CostTracker (726 lines) + Rust BudgetTracker (tracker.rs)
├─ Runtime: Active (both sides)
├─ Gap: Rust side record_usage 未被呼叫 (BI-07) +
│       Python/Rust 預算未同步
├─ Healthcheck: ai_usage_log rows ≥ 1
└─ Score: 60% 🟡 Shadow (init but no usage log)

H3 (Model Router - L1/L1.5/L2 routing)
├─ Code: 292 lines (model_router.py) + StrategistScheduler (1612 lines Rust)
├─ Runtime: Active L1 routing + Background L2 thread
├─ Gap: L2 result caching (C3-04) + prompt calibration (C1-04) +
│       StrategistScheduler 100% reject (C1-04, C3-03)
├─ Healthcheck: [14] StrategistScheduler accept rate > 20%
└─ Score: 55% 🟡 Active but high reject rate

H4 (Output Validation)
├─ Code: 103 lines (h4_validator.py, 獨立模組)
├─ Runtime: Active (StrategistAgent._validate_ai_output)
├─ Gap: 僅驗 confidence field；has_edge/reason 缺驗
└─ Score: 65% 🟡 Partial validation

H5 (Cost Logging)
├─ Code: Python (layer2_cost_tracker.py) + Rust (ai_budget/)
├─ Runtime: Python active + Rust init but no record
├─ Gap: ai_usage_log = 0 rows (BI-07) + Python/Rust 未同步
├─ Healthcheck: [1] ai_usage_log rows ≥ 1
└─ Score: 50% 🔴 Shadow on Rust side

H1-H5 Overall Average: 66% 🟡 Active but fragmented
 ├─ Target: 85% by W2 (C-series items + BI fixes)
 └─ Blockers: C1-01, C1-02, C2-01, C1-04, C3-02
```

### D.2 5-Agent + Conductor System

```
Scout Agent (Market Scanner only)
├─ Code: 194 lines (scout_worker.py) + 722 lines (scout_routes.py)
├─ Runtime: 30-min cycle MarketScanner (live)
├─ Gap: News / events / FOMC / token_unlock stub (C2-02)
├─ Healthcheck: [2] scout_intel last 2h
└─ Score: 40% 🔴 Skeleton (技術面only)

Strategist Agent (Ollama edge judge)
├─ Code: 1,170 lines (strategist_agent.py) + 1,612 Rust scheduler
├─ Runtime: live judge_edge (Ollama 9B) + 5-min param tuning attempt
├─ Gap: 100% param proposal reject (C1-04) + judgment calibration (C1-04)
├─ Healthcheck: [3] StrategistScheduler cycle count > 0
└─ Score: 50% 🟡 Shadow (active but proposals rejected)

Guardian Agent (Risk review)
├─ Code: 587 lines (guardian_agent.py) + Rust RiskConfig
├─ Runtime: Rust Guardian primary; Python bridge
├─ Gap: None known
└─ Score: 80% ✅ Production-grade

Analyst Agent (Trade analysis + L2 pattern discovery)
├─ Code: 834 lines (analyst_agent.py)
├─ Runtime: L1 analysis active; L2 (Ollama 27B) needs ≥200 observations
├─ Gap: L2 trigger threshold (C3-04) + observations pooled = 244 (達標)
├─ Healthcheck: [4] analyst_l1_analysis last 24h
└─ Score: 70% 🟡 Active L1; Shadow L2 (threshold pending)

Executor Agent (Order submission)
├─ Code: 630 lines (executor_agent.py, includes all contracts)
├─ Runtime: `_shadow_mode=True` default (C1-03, C3-01)
├─ Gap: No shadow→live toggle (C3-01) + Path A/B conflict (C1-03)
├─ Healthcheck: [5] executor_shadow_intent log count
└─ Score: 30% 🔴 Dormant (shadow-only, intentionally disabled)

Conductor Agent (Agent orchestration)
├─ Code: 1,137 lines (multi_agent_framework.py)
├─ Runtime: Framework active but Conductor incomplete
├─ Gap: No auto health check + agent restart (4/01 P2-AI-4 unfixed)
└─ Score: 40% 🔴 Skeleton (message bus works, orchestration missing)

5-Agent Overall Average: 52% 🔴 Mostly shadow
 ├─ Target: 75% by W2 (C3-01, C3-02, C2-02)
 └─ Blockers: C1-03 (ExecutorAgent RFC), C2-02 (Scout news), C3-01 (shadow→live)
```

### D.3 Layer 2 AI + Claude Teacher

```
Layer 2 Claude Agent Loop
├─ Code: 730 lines (layer2_engine.py) + 906 tools + 451 routes
├─ Framework: 8 tools + 4 search provider cascade (Perplexity→Local→DuckDuckGo)
├─ Runtime: 0 autonomous trigger (手動 POST /api/v1/paper/layer2/trigger only)
├─ Gap: ANTHROPIC_API_KEY 未設 demo / no autonomous fire (C2-04) /
│        reasoning chain not logged (C2-04)
├─ Healthcheck: [10] layer2_session count > 0
└─ Score: 35% 🔴 Skeleton (code complete, never autonomously triggered)

Claude Teacher
├─ Code: 3,757 lines Rust (9 submodules) + 726 tracker
├─ Framework: Fetch → Parse → Persist → Apply → Outcome track
├─ Runtime: Spawned but `teacher_loop_enabled=false` (Phase 4.1 contract)
├─ Gap: DEFAULT-OFF + ANTHROPIC_API_KEY missing + E3 R6 audit pending (C4-04)
├─ Healthcheck: [16] teacher_directives rows (currently 0)
└─ Score: 40% 🔴 Dormant (code mature, intentionally disabled)

Layer 2 + Teacher Overall Average: 37% 🔴 Mostly dormant
 ├─ Target: 60% by W3 (C2-04 auto-trigger + C4-04 teacher enable)
 └─ Blockers: ANTHROPIC_API_KEY setup, E3 audit
```

### D.4 ML Pipeline (Training + Edge Prediction + LinUCB)

```
Training Pipeline (run_training_pipeline.py)
├─ Code: 21 modules (label_generator, scorer_trainer, linucb_trainer, etc)
├─ Features: decision_features 6.19M rows (active)
├─ Labels: exit_features 244 rows (達 ≥200 threshold)
├─ Runtime: Skip ONNX export (skip_onnx=True default)
├─ Gap: First ONNX not run yet (C3-05) + calibration stub (C4-05)
├─ Healthcheck: [17] model_registry rows > 0
└─ Score: 45% 🟡 Active feature extraction; skeleton training

ONNX Quantile Predictor (edge_predictor)
├─ Code: 2,965 lines Rust (ort backend + features + gate)
├─ Runtime: `use_edge_predictor=false` + `shadow_mode=true`
├─ Gap: Never activated (C4-01) + needs first ONNX artifact (C3-05 prereq)
├─ Healthcheck: [18] edge_predictor inference count (currently 0)
└─ Score: 10% 🔴 Dormant (code complete, use flag OFF)

LinUCB Contextual Bandit
├─ Code: 1,003 lines Rust (inference + arms + state IO)
├─ Runtime: cold_start live + select_arm_after_gates record-only (no decision change)
├─ Gap: No rows in learning.linucb_state (需訓練) (C3-05 prereq)
├─ Healthcheck: [19] linucb_state rows > 0
└─ Score: 35% 🟡 Active cold-start; shadow record-only

ML Pipeline Overall Average: 30% 🔴 Mostly dormant
 ├─ Target: 65% by W3 (C3-05 first ONNX + C4-01/C4-02 activate)
 └─ Blockers: C3-05 (labels ≥200), ANTHROPIC_API_KEY, E3 audit
```

---

## E. AI 相關 Healthcheck 清單（CLAUDE.md §七 強制）

所有「被動等待 TODO 必附 healthcheck」（CLAUDE.md §七 新規則）。下面是 AI 相關 check：

```python
# passive_wait_healthcheck.py 已有 checks（應補充）

[1] check_ai_usage_log_entries
    → learning.ai_usage_log rows ≥ 1 (Rust BudgetTracker record_usage called)
    → State: FAIL (currently 0 rows) - blocker C2-01

[2] check_scout_intel_freshness
    → scout_intel produced in last 2h
    → State: PASS (MarketScanner 30-min cycle active)

[3] check_strategist_scheduler_cycle
    → strategist_scheduler cycle count > 0 (5-min)
    → State: PASS (engine.log confirms) but need accept rate > 20% (C1-04)

[4] check_analyst_l1_analysis_running
    → analyst_l1_analysis count > 0 in last 24h
    → State: PASS (trade round-trip analysis live)

[5] check_executor_shadow_intent_log
    → executor shadow intent count > 0 (tracks even if not executing)
    → State: PASS (ExecutorAgent shadow_mode=True)

[6] check_edge_estimator_scheduler_freshness  ⚠ FAILING
    → edge_estimates.json mtime < 24h
    → State: FAIL (mtime 2026-04-20, 4 days stale) - BLOCKER C1-01

[7] check_layer2_session_count
    → layer2_session count > 0 (manual trigger only; auto-trigger pending C2-04)
    → State: FAIL if = 0 (check manually triggered sessions)

[8] check_shadow_exit_ratio
    → decision_shadow_exits rows ≥ 1 (when shadow_enabled=true, currently false)
    → State: SKIP (dormant until C4-03 flip)

[9] check_model_registry_freshness  🔲 TBD
    → model_registry oldest train_date < 30d / < 60d (Phase 1a/2 threshold)
    → State: SKIP (3 rows all canary_status='shadow', not promoted)

[10] check_teacher_directives_generated
    → teacher_directives rows ≥ 1 (when enabled, currently DEFAULT-OFF)
    → State: SKIP (dormant until C4-04 flip)

[11] check_edge_diag_phase3_prerequisites  🟡 PENDING
    → post_p013_clean bucket ≥200 rows + per-strategy CI + orphan ≥20
    → State: PENDING (awaiting C1-04 completion + E4 measurement)

[12] check_bb_breakout_deadlock_fix  (已 2026-04-24)
    → fill count recovery after FIX-26 (healthcheck added, pending --rebuild)
    → State: PENDING rebuild

[13] check_edge_estimator_scheduler_freshness_hourly  NEW
    → james_stein_estimates written in last 1h
    → State: FAIL if stale (C1-01 prerequisite)

[14] check_strategist_scheduler_accept_rate  NEW
    → accept rate (accepted proposals / total proposals) > 20%
    → State: FAIL (currently 0/3 = 0%) - ROOT CAUSE C1-04

[15] check_linucb_state_exists  NEW
    → learning.linucb_state rows > 0
    → State: SKIP (dormant until training pipeline runs, C3-05)

[16] check_claude_teacher_enabled  NEW
    → teacher_loop_enabled=true in config
    → State: SKIP (DEFAULT-OFF until C4-04)

[17] check_model_registry_production_exists  NEW
    → model_registry has canary_status='production' ≥ 1
    → State: FAIL (all 3 rows are 'shadow')

[18] check_edge_predictor_active  NEW
    → use_edge_predictor=true in risk_config
    → State: FAIL (currently false) - dormant until C4-01

[19] check_layer2_autonomous_trigger  NEW
    → layer2_session auto-triggered in last 24h (vs manual trigger)
    → State: FAIL (no auto-trigger mechanism yet) - awaiting C2-04
```

---

## F. 給 PA 的 AI 接線驗證重點

### F.1 AI 整合度 Checklist（用於 G1-G3 Gate）

**G1 通過標準：**
```
[ ] C1-01: edge_estimator_scheduler mtime fresh (<24h)
[ ] C1-02: PostOnly 配置正向 (demo=true, live=false) ✅ verified
[ ] C1-03: event_consumer <1200 lines ✅ E2 approve
[ ] C1-04: StrategistScheduler accept rate > 20% (not 100% reject)
[ ] C1-05: ExecutorAgent shadow→live RFC drafted ✅ E2 approve
[ ] C2-01: ai_usage_log ≥ 1 row ✅ record_usage called
[ ] C2-02: ScoutAgent news source route decided (Option A or B)
[ ] C2-03: StrategistScheduler delta logic audit + calibration plan
[ ] G2-01: PostOnly 1-2w demo validation ✅ passive wait
[ ] G2-05: bb_breakout FIX-26 deployed ✅ healthcheck [12]
```

**G2 通過標準：**
```
[ ] C3-01: ExecutorAgent shadow→live IPC implemented ✅ E4 e2e
[ ] C3-02: H1-H5 → Rust gateway (或 E5 設計完成)
[ ] C3-03: cost_edge_ratio formula + daily compute ✅ GUI show
[ ] C3-04: H3 L2 cache TTL/eviction ✅ >50% hit rate
[ ] C3-05: run_training_pipeline first ONNX ✅ model_registry row
[ ] C3-06: canary auto-promote rules + health check [9]
[ ] G4-01: Labels pooled ≥200 ✅ ready for training
[ ] G4-02: ONNX grid_trading artifact produced ✅ registered
```

**G3 通過標準：**
```
[ ] C2-04: Layer 2 autonomous trigger + ANTHROPIC_API_KEY setup
[ ] C2-02: ScoutAgent news/events routed from Rust news pipeline
[ ] C4-01: edge_predictor activated (use=true, shadow=false) + shadow observation
[ ] C4-02: AI Service 5 IPC handlers all green ✅ e2e test
[ ] C4-03: Combine Layer shadow flip (ExitConfig.shadow_enabled=true) + 14d
[ ] C5-01: ai-stats endpoint live ✅ daily update
[ ] C5-02: monthly ROI computed ✅ alert if <0.5
[ ] C5-03: StrategistScheduler accept rate monitoring ✅ healthcheck [14]
```

### F.2 AI 決策鏈追蹤（可追溯性驗證，原則 #8）

```
StrategistScheduler AI decision trace:
1. on_tick_scheduler_5min() fires
2. fetch recent fills → rank top-10 symbols
3. IPC strategist_evaluate( symbol ) → Ollama judge_edge( context )
4. receive EdgeEvaluation { confidence, cooldown_ms, reason }
5. validate against ±30% delta guard
6. IF accept → apply param change → logging
7. IF reject → logging reason
8. audit trail: engine.log + learning.strategist_applied_params (currently 0 rows)

Verification:
- [ ] engine.log shows 5-min cycle firing
- [ ] IPC latency < 15s timeout (C2-01 record confirms)
- [ ] reject reasons logged (currently 100% delta exceed)
- [ ] strategist_applied_params table tracks applied (currently 0 = all rejected)
- [ ] reason field in rejection logged (audit trail completeness)
```

### F.3 AI 成本 / ROI 驗證路徑

```
Day-1 Check:
[ ] Ollama status: http://127.0.0.1:8000/api/v1/paper/layer2/ollama/status
    Expected: available=true, models=[qwen3.5:9b, qwen3.5:27b]
[ ] ai_budget status: http://127.0.0.1:8000/api/v1/ai_budget/status
    Expected: current cost < hard_limit (local=100, total=150)
[ ] cost_tracker daily: layer2_cost_state.json mtime fresh
    Expected: total_usd_spent_today < 2.00

Day-7 Check:
[ ] learning.ai_usage_log rows ≥ 7 (daily record)
    Expected: 7 rows (1 per cycle) or 0 if Rust record_usage still broken
[ ] cost_edge_ratio computed:
    Expected: cost_edge_ratio ≥ 0.5 for go/no-go decision
[ ] strategist_applied_params rows > 0:
    Expected: > 0 if C1-04 calibration success (currently 0 = blocker)

Decision Point (P0-3 ~ 2026-05-10):
[ ] Analyze counterfactual replay (EDGE-DIAG Phase 2)
[ ] If edge > 0 → cost_gate remains open → AI tuning continues
[ ] If edge < 0 → trigger cost_gate close recommendation
    Evidence: cost_edge_ratio ≥ 0.8 → suggest grid disable
```

---

## G. 核心路徑依賴圖（關鍵 Blocker 識別）

```
Critical Path Analysis:

P0 Blockers (Must complete to unblock G1-G3):
├─ C1-01 (edge_estimator_scheduler) → needed by G1 diagnosis
├─ C1-02 (PostOnly config) → fast fix, 0.5d
├─ C1-03 (event_consumer split) → 3-4d, blocks G1-02
├─ C1-04 (StrategistScheduler calibration) → 2-3d, root cause high reject
└─ C1-05 (ExecutorAgent RFC) → 1d, gates G3-01

Wave 1 (W17/18): Complete C1-01..05 + C2-01..03
  ↓
Wave 2 (W19): Complete C3-01..06 + activate C2-04
  ├─ G3-02 depends on C1-05 RFC ✓
  ├─ G3-08 depends on G1-02 complete (event_consumer) ✓
  └─ G4-01 depends on C2-05 labels pooled ✓
  ↓
Wave 3 (W20-W23): Complete C3-05 (first ONNX) → unlock C4 series
  ├─ C3-05 first run (grid_trading) → C3-06 canary promote
  ├─ C4-01 edge_predictor activate → 7d shadow
  ├─ C4-03 Combine shadow flip → 14d observation
  └─ C4-04 Claude Teacher enable (if E3 audit clears)
  ↓
Wave 4 (W23-W24): LG-2/3/4/5 gate checks → Live decision
  ├─ LG-2: H0 Gate shadow→blocking
  ├─ LG-3: Provider pricing table
  ├─ LG-4: Supervised Live Gate
  └─ LG-5: Constrained Autonomous
```

---

## H. 總結與簽核

### H.1 AI-E 完整提案統計

| 級別 | 條數 | 工時估計 | Wave 分佈 |
|------|------|---------|----------|
| 🔴 Critical (C1) | 5 | 12-15d | W1 |
| 🟠 High (C2) | 5 | 8-12d | W1-W2 |
| 🟡 Medium (C3) | 6 | 15-20d | W2-W3 |
| 🔵 Lower (C4) | 5 | 10-15d | W3-W4 |
| 📊 Monitoring (C5) | 4 | 5-7d | across waves |
| **合計** | **25** | **50-70d** | — |

### H.2 頂級遺漏發現（相比 TODO.md）

| # | 項 | 分類 | 是否在 TODO | 嚴重度 |
|----|---|------|-----------|--------|
| BI-01 | edge_estimator_scheduler 4d 停滯 | Diagnostic | MIT audit 有提，TODO 無根因 | 🔴 P0 |
| BI-04 | StrategistScheduler 100% reject | Root cause | engine.log evidence，TODO 未列細節 | 🔴 P0 |
| BI-05 | Layer 2 無 autonomous trigger | Architecture | 4/24 新發現，TODO 未列 | 🟡 P1 |
| BI-06 | ScoutAgent 新聞全 stub | Feature gap | 4/24 新發現，TODO 未列 | 🟡 P1 |
| BI-07 | ai_usage_log = 0 rows | Blocker | 4/24 新發現，是 BudgetTracker gap | 🟡 P1 |
| C5-* | AI ROI 儀表板缺失 | Observability | 4/01 改進建議未落地 | 🟡 P1 |

### H.3 AI 系統成熟度（Current vs Target）

```
| System | Current | Target (W2) | Target (W4) |
|--------|---------|------------|------------|
| H1-H5 Layers | 66% | 85% | 90% |
| 5-Agent | 52% | 70% | 85% |
| Layer 2 + Teacher | 37% | 55% | 75% |
| ML Pipeline | 30% | 55% | 75% |
| Overall AI | 46% | 66% | 81% |
```

### H.4 PA 簽核檢查點

**G1 Gate（完成 C1 + C2 series）**：
- [ ] 所有 P0 blocker 修復（edge_estimator_scheduler, PostOnly, event_consumer 拆分）
- [ ] 根因診斷完成（StrategistScheduler reject reasons 分析 + calibration plan）
- [ ] RFC approved（ExecutorAgent shadow→live）

**G2 Gate（完成 C3 series + G4-01/02）**：
- [ ] ExecutorAgent shadow→live 完整接線（IPC + e2e test green）
- [ ] H1-H5 對 Rust pipeline 生效（C3-02）
- [ ] 首個 ONNX artifact 産出（C3-05）
- [ ] cost_edge_ratio 演算法實裝（C3-03）

**G3 Gate（完成 C4 + C5 + activate dormant）**：
- [ ] Layer 2 autonomous trigger working（C2-04）
- [ ] Scout news routed（C2-02）
- [ ] AI stats dashboard live（C5-01）
- [ ] ≥3 major dormant systems activated（edge_predictor, teacher, shadow layer）

---

**AI-E Report Complete**
**Document Path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-04-24--todo_complete_proposal.md`
**Total Proposals**: 25 items (C1-C5) + 19 healthchecks
**Core Blockers**: 5 (C1 series)
**Estimated Duration**: 50-70 workdays across W1-W4

