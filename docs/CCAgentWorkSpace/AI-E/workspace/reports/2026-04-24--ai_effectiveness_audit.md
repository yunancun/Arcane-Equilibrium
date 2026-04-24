# AI-E 審計報告：AI 使用效果、接入度、開發完成度評估
# AI-E Audit: AI Integration / Usability / Development Maturity
# 日期：2026-04-24
# 對比基準：2026-04-01 AI Effectiveness Audit
# 審核員：AI-E（AI Effectiveness Evaluator）
# 證據來源：源碼 grep + Linux trade-core runtime 實測（engine PID 912616, uvicorn PID 912671）
# 交叉驗證：不採信 CLAUDE.md/memory 敘述，逐項 grep + SSH 到 Linux 查 DB/log/ps/curl

---

## 執行摘要 / Executive Summary

| 維度 | 3/31 | 4/01 | 4/24 | 備註 |
|------|------|------|------|------|
| Python AI 模組行數 | ~4,500 | 7,815（9 模組） | **10,959**（15 模組，含 base_agent/agent_audit_bridge/local_llm_factory/llm_call_wrapper 等新拆分） | +40% vs 4/01 |
| Rust AI 模組行數 | — | — | **8,942**（ai_budget 1,411 + claude_teacher 3,757 + edge_predictor 2,965 + linucb 1,003 + ml 1,085 + news 2,231） | 全新 Rust 層 |
| Python AI 測試函數 | ~180 | 492 | 未重數（此次不重跑 pytest） | 保守估 >700 |
| 5-Agent 全鏈 | 部分接通 | 全接通 shadow=True→False 切換 | **Strategist live / Guardian live / Analyst live / Scout live（技術面 only）/ Executor shadow=True 默認** | 與 CLAUDE.md §三 一致 |
| H0-H5 治理 | H0 未接入 | 全接入 | **H0/H1/H2/H3/H4/H5 全 live + 獨立模組化**（h1_thought_gate / model_router / h4_validator 已從 strategist_agent.py 拆分） | 結構改善 |
| AI 相關 API routes | — | 部分 | **39 個 AI 相關 routes live**（見附錄 A） | curl 驗證 |
| AI 真實 runtime 呼叫 | demo 模式試跑 | demo 模式 | **StrategistScheduler 5-min cycle 真跑（engine.log 有 proposed param reject）** | log 證據 |
| learning.ai_usage_log | — | — | **0 rows**（BudgetTracker 已 init 但從未記過一筆成本） | PG 實測 |
| learning.teacher_directives | — | — | **0 rows**（TeacherConsumerLoop DEFAULT-OFF） | PG 實測 |
| learning.model_registry | — | — | **3 rows / 全 canary_status='shadow'** | 未有任何 production 模型 |
| learning.decision_shadow_exits | — | — | **0 rows**（INFRA-PREBUILD-1 Part A shadow_enabled=false） | 符合 Phase 1a dormant 設計 |
| learning.decision_features | — | — | **6,190,378 rows**（ETL pipeline 真實活躍） | 真實 |
| learning.scorer_training_features | — | — | **532,386 rows** | 真實 |
| learning.exit_features | — | — | **244 rows**（EXIT-FEATURES-TABLE-1 累積中） | 真實 |
| learning.james_stein_estimates | — | — | **624 rows**（EdgeEstimatorScheduler hourly 活躍） | 真實 |

**整體評級：B- → B+（視覆蓋面）**

- **真實 runtime live**：H0 Gate / StrategistAgent + Ollama judge_edge / StrategistScheduler 5-min / ScoutWorker 30-min / MarketScanner / edge_estimator_scheduler / Rust news pipeline / LinUcbRuntime cold-start / BudgetTracker init
- **Shadow（代碼 live 但記錄為主）**：H3 L2 background thread / H4 validator / LinUCB record-only（select_arm_after_gates 不改決策）/ ExecutorAgent 默認 shadow=True（不發 SubmitOrder）/ Combine Layer shadow_enabled=false
- **Dormant（spawned 但 enabled=false 或從未被呼叫）**：TeacherConsumerLoop（default-off Phase 4.1 契約）/ edge_predictor use_edge_predictor=false / kelly_sizer set_kelly_config 無 call-site / model_registry 全 shadow status / news pipeline → Python Scout 鏈路斷（Rust news 只給 Guardian/regime context）
- **假功能風險（跟 4/01 P1-AI-1 同層）**：Layer 2 Claude Agent Loop（run_session）只由 POST /api/v1/layer2/trigger 手動觸發 + 依賴 ANTHROPIC_API_KEY（demo env 未設）→ 從未在 runtime autonomous 跑過

---

## 一、AI 調用面完整盤點 / Complete AI Invocation Inventory

### 1.1 Python 側 AI 模組（srv/program_code/.../control_api_v1/app/）

| 模組 | 行數 | 角色 | 代碼入口 |
|------|------|------|---------|
| `strategist_agent.py` | 1,170 | L1 edge 評估（Ollama 9B/27B + judge_edge）+ H1/H3/H4 委託 | `strategy_wiring.py:242` `shadow=False` live |
| `h1_thought_gate.py` | 185 | 獨立 H1 預算/複雜度/冷卻 pre-AI 閘門 | StrategistAgent 委託 |
| `model_router.py` | 292 | 獨立 H3 L1/L1.5/L2 路由 + L2 background thread + L2 cache | StrategistAgent 委託 |
| `h4_validator.py` | 103 | 獨立 H4 AI 輸出結構驗證 | StrategistAgent 委託 |
| `h0_gate.py` | 971 | L0 確定性 5 子檢查（freshness/health/eligibility/risk_envelope/cooldown）| 由 paper_trading_routes 注入 + pipeline_bridge（已被 DEAD-PY-2 移除後，H0 Gate 透過 IPC 到 Rust 側） |
| `layer2_engine.py` | 730 | L2 Claude Agent Loop（run_session，agentic 推理）+ TOOL_SCHEMAS 8 tools | 只由 `POST /api/v1/paper/layer2/trigger` 手動觸發 |
| `layer2_tools.py` | 906 | ToolExecutor（get_market_state / get_account_state / get_recent_decisions / get_experience / web_search / fetch_url / submit_recommendation / record_insight）+ 4 search providers | `_run_session_inner` 用 |
| `layer2_cost_tracker.py` | 726 | Claude / Ollama 雙端成本追蹤 + session/daily budget + roi_basis 標記 | StrategistAgent + L2 注入 |
| `layer2_types.py` | 477 | Layer2Session + Recommendation + Insight + SearchProvider abstract | 共用 type |
| `layer2_routes.py` | 451 | POST /paper/layer2/trigger + GET sessions + budget API | manually invoked only |
| `guardian_agent.py` | 587 | 風控審查 agent | strategy_wiring.py live + subscribe MessageBus |
| `analyst_agent.py` | 834 | L1 統計分析 + L2 Ollama 27B 週報模式發現（不是 Claude） | live + L2 auto-trigger at observations≥200 |
| `executor_agent.py` | 630 | 訂單執行 wrapper（acquire_lease + 執行質量反饋） | **`_shadow_mode=True` 默認**（ExecutorConfig 未覆蓋）= 記錄 intent 不發 SubmitOrder IPC |
| `multi_agent_framework.py` | 1,137 | Conductor + MessageBus + AgentRole + 5 Agent class 定義 | 全 live 接入 |
| `ollama_client.py` | 506 | Ollama HTTP 客戶端 + max_retries=0 + think=False | 9B + 27B 雙 singleton |
| `local_llm_factory.py` | 417 | LOCAL_LLM_PROVIDER 切 Ollama / LM Studio shim | `get_local_llm_client(heavy=True)` 用於 AnalystAgent 27B, `get_local_llm_client()` 用於 StrategistAgent 9B |
| `llm_call_wrapper.py` | 176 | E5-P1-4 抽取 call_ollama_judge_edge / call_ollama_generate | StrategistAgent + AnalystAgent 通用 |
| `base_agent.py` | 255 | 5 Agent 共享 lifecycle + audit callback 骨架 | E5-P1-4 拆分 |
| `agent_audit_bridge.py` | 406 | Agent._audit → GOV_HUB._change_audit_log 橋接（根原則 #8） | E5-FN-3-FUP-a/b/c/d 4 Agent 全接入 |
| `ai_service.py` | 1,258 | Rust IPC → Python Agent dispatch (5 handlers: strategist/analyst/conductor/scout/guardian) + UDS listener | `main.py:441` `create_ai_service_listener()` live |
| `scout_worker.py` | 194 | 30-min daemon thread 觸發 MarketScanner.scan() | strategy_wiring.py:694 start |
| `scout_routes.py` | 722 | /scout/intel /scout/alerts /scout/market-signal /scout/event-alert /scout/status | manually invoked |

**Python AI 模組合計：10,959 行（15 核心模組，+40% vs 4/01）**

### 1.2 Rust 側 AI / ML 模組（srv/rust/openclaw_engine/src/）

| 模組 | 行數 | 角色 | 運行時狀態 |
|------|------|------|----------|
| `ai_budget/{tracker, pricing, config_io, usage_io}.rs` | 1,411 | BudgetTracker 成本預算（5 scope × 7 model）+ degrade_level + YAML 定價表 | **live init（engine.log 確認）** + 0 usage log rows |
| `ai_service_client.rs` | ~300 | Rust → Python ai_service.sock IPC client（strategist_evaluate / analyst_evaluate / scout_scan 等）+ per-method TTL | **live**（main.rs:1127 Arc::new） |
| `strategist_scheduler/{mod, persist}.rs` | 1,612 | 5-min cycle：查 fills → rank top-10 → IPC strategist_evaluate → 驗證 ±30% → apply | **live（engine.log 證實 5-min cycle + reject proposed delta）** / strategist_applied_params=0 rows（所有 proposal 被 delta guard 擋） |
| `claude_teacher/{mod, client, consumer_loop, applier, writer, parser, outcome_tracker, governance_impl, strategy_ipc_impl, applier_test_fixtures}.rs` | 3,757 | Claude Teacher directive pipeline：fetch → parse → persist → apply | **Spawned 但 DEFAULT-OFF**（`teacher_loop_enabled=false`）+ teacher_directives=0 rows |
| `edge_predictor/{feature_builder, features, gate, mod, null_backend, ort_backend, rearrangement}.rs` | 2,965 | ONNX quantile predictor（q10/q50/q90）+ shadow / use flag + exploration_rate | **`use_edge_predictor=false` + `shadow_mode=true` dormant**（risk_config_live.toml 實測） |
| `linucb/{arms_v1_15, inference, mod, runtime, schema_hash, state_io}.rs` | 1,003 | LinUCB contextual bandit + `select_arm_after_gates` record-only | **cold-start live（engine.log）** / linucb_state=0 rows / 不改決策邏輯 |
| `ml/{kelly_sizer, mod, model_manager, registry, scorer}.rs` | 1,085 | Kelly sizer + Scorer 3-tier（ONNX → rule → fixed）+ Model Registry reader（INFRA-PREBUILD-1 Part B）| kelly_sizer: `set_kelly_config` 無 runtime call-site = 未啟用；scorer: null backend；model_registry: 3 rows 全 shadow，`resolve_latest_production_artifact` 無 caller（Phase 3+ 才接） |
| `news/{cryptopanic, dedup, guardian_impl, learning_context_impl, mock, pipeline, provider, rss, router, severity, types}.rs` | 2,231 | A2 NewsPipeline 60s scheduler（CryptoPanic + RSS + Mock + GoogleNews）+ dedup + severity + 3-tier router（Guardian halt / regime buffer / learning context）| **live（main.rs:890 spawn_news_pipeline）** / 與 Python ScoutAgent **不連接**（Rust 內部供 Guardian + regime；Python 側的 ScoutAgent 只收 MarketScanner 技術面信號） |

**Rust AI 模組合計：8,942 行（7 子系統）**

### 1.3 啟動流程（engine.log 2026-04-24 03:01 確認）

```
1. BudgetTracker pricing table loaded (7 models)   ✅ live
2. BudgetTracker initialized (local=100/teacher=60/analyst=30/reserve=10)   ✅ live
3. LinUcbRuntime cold-started (v1_15, feature_schema_hash=sha256:023787b8)   ✅ live
4. pipeline using LinUcbRuntime for arm metadata   ✅ live（record-only）
5. Phase 4.1 TeacherConsumerLoop spawned + IPC handles injected (DEFAULT-OFF)   ⚠ dormant
6. StrategistScheduler spawned — tune_target=Demo, has_live_promote=false   ✅ live
7. StrategistScheduler started (5-min cycle) has_promote_channel=false   ✅ live
8. NewsPipeline spawned (Rust 側)   ✅ live（不與 Python Scout 連）
```

**5-min cycle 實際行為（engine.log 01:06/01:11/01:16 三次觀察）**：
- 01:06:39 WARN `delta exceeds ±30% cap` cooldown_ms 60000→120000 (100%) — **rejected**
- 01:11:47 WARN `delta exceeds ±30% cap` cooldown_ms 60000→150000 (150%) — **rejected**
- 01:16:56 WARN `delta exceeds ±30% cap` cooldown_ms 60000→30000 (50%) — **rejected**

結論：Python StrategistAgent.judge_edge（Ollama 9B）**真的被 IPC 呼叫**，但提案被 ±30% delta guard 擋下。guard 在工作，但 Ollama 給的 cooldown_ms 建議震盪過大（60s↔150s），可能 prompt 需要 calibration。

---

## 二、接入度 Assessment / Integration Assessment

### 2.1 AI 組件接入度矩陣

| 子系統 | Runtime 呼叫 | Shadow/Dormant/Active | I/O 契約 | 成本感知 | Status |
|--------|-------------|---------------------|---------|---------|--------|
| **H0 Gate（L0 確定性）** | pipeline_bridge（DEAD-PY-2 移除後轉 Rust side） + risk_manager + GUI routes | **Active**（h0_shadow_mode=false）| 5 子檢查 dict | N/A（無 AI） | ✅ Production |
| **H1 ThoughtGate** | StrategistAgent on_message 流 | Active | intel + cost_tracker → should_call_ai bool | 委託 cost_tracker | ✅ Production |
| **H2 Budget Gate** | Layer2CostTracker.check_daily_budget（L2 sess + L1 record_call） | Active | (bool, remaining_usd) | 直接實施 | ✅ Production |
| **H3 ModelRouter** | StrategistAgent 委託 | L1/L1.5 Active + **L2 Background Thread Shadow**（結果僅日誌，不回注） | complexity → l1_9b / l1_27b / l1_5 / l2 | L2 session cost 追蹤 | ⚠ P2-AI-2 持續未修（4/01 標記）|
| **H4 Validator** | StrategistAgent._ai_evaluate JSON 後置 | Active | dict → bool（僅驗 confidence [0,1]）| N/A | ✅ 限制性實施（has_edge/reason 未驗）|
| **H5 Cost Logging** | record_call（Ollama $0）+ record_claude_cost + record_ollama_call(deprecated) | Active | model_id + cost_usd + duration_ms | **learning.ai_usage_log=0 rows 表明 Rust 端 record_usage 從未觸發** | ⚠ Python side 有記 / Rust side 0 rows |
| **StrategistAgent（5-Agent）** | strategy_wiring.py:242 `shadow=False` + MessageBus.subscribe + CognitiveModulator inject | **Live** | on_message(INTEL_OBJECT) → TRADE_INTENT | judge_edge 走 Ollama | ✅ Live |
| **GuardianAgent** | strategy_wiring.py + subscribe | Active（Rust Guardian 為主，Python 作 bridge）| TRADE_INTENT → APPROVED_INTENT / REJECT | N/A | ✅ Live |
| **AnalystAgent L1** | 每筆 round-trip 自動 analyze_trade | Active | TradeRecord → metrics | N/A | ✅ Live |
| **AnalystAgent L2（Ollama 27B 週報）** | observations ≥ 200 auto-trigger / directive trigger_l2_analysis | **Active（auto）**，但閾值可能數週才達到 | summary → PatternInsight → TruthSourceRegistry + ExperimentLedger | Ollama $0 | ⚠ 閾值高（P2-AI-5 持續，未降 demo 環境閾值）|
| **ExecutorAgent** | strategy_wiring.py:467 `ExecutorConfig()` 預設 + subscribe | **`_shadow_mode=True` 默認**（executor_agent.py:482）= 記錄 intent 不發 SubmitOrder IPC | APPROVED_INTENT → shadow log only | N/A | 🟡 **Design intent but 未接 shadow→live 切換流程** — G-1 未展開 |
| **ScoutAgent（Python）** | strategy_wiring.py:143 + ScoutWorker 30-min + scout_routes.py operator API | Active（只產 MarketScanner opportunity summary）| source/content/symbols → IntelObject → MessageBus | N/A | ⚠ **新聞 / 宏觀 / 事件日曆 全 stub** — 只收 MarketScanner 技術面 |
| **Layer 2 Claude Agent Loop** | 只由 `POST /api/v1/paper/layer2/trigger` 手動觸發 | **依賴 ANTHROPIC_API_KEY，dormant 直到 operator 手動 trigger** | 8 tools + Claude Sonnet 4.6 + 4 search provider 降級 | Claude cost track（但 0 rows）| 🔴 **從未在 runtime 有自主觸發** |
| **Rust StrategistScheduler** | tokio spawn 5-min cycle | **Live（engine.log 5-min WARN 每 5 分鐘一次）** | fills metrics → IPC strategist_evaluate → delta guard → PipelineCommand::UpdateStrategyParams | ai_service IPC TTL 15s | ✅ Live，但 Ollama proposal 全被 delta guard 擋下 |
| **Rust TeacherConsumerLoop** | tasks.rs spawn_teacher_consumer_loop | **DEFAULT-OFF 契約（`teacher_loop_enabled=false`）**，spawn 但 enabled AtomicBool(false) | Anthropic → DB persist → governance → IPC PipelineCommand | BudgetTracker record_usage（但 0 rows）| 🔴 Dormant（等 E3 R6 audit PASS）|
| **Rust LinUcbRuntime** | main.rs:853 cold_start_v1_15 + 3 處 inject EventConsumerDeps | **Live（engine.log）**，但 `select_arm_after_gates` 文檔明說 "不改變任何決策邏輯" | context → arm selection → 只記錄 | N/A | ⚠ Record-only shadow |
| **Rust edge_predictor（ONNX q10/q50/q90）** | tick_pipeline 內條件分派 | **`use_edge_predictor=false` + `shadow_mode=true` = Dormant** | features → q10/q50/q90 → safety_margin gate | N/A | 🔴 Dormant |
| **Rust ml::kelly_sizer** | intent_processor/router.rs:161 條件用 | `set_kelly_config` 無 runtime call-site | features → qty | N/A | 🔴 Dead（無 caller set config，走 fallback guardian_qty） |
| **Rust ml::scorer（3-tier ONNX→rule→fixed）** | mod.rs Scorer 結構 | null backend default；無 ONNX 模型注入 | signal_confidence/edge → score | N/A | 🔴 Degraded-only path |
| **Rust ml::registry（Model Registry reader）** | INFRA-PREBUILD-1 Part B | **Dormant**：3 rows 全 canary_status='shadow'；`resolve_latest_production_artifact` 無 caller（Phase 3+ 才接 OnnxModelManager）| slot → ResolvedArtifact | N/A | 🔴 Dormant |
| **Rust news pipeline（4 provider）** | tasks.rs:230 spawn 60s cycle | **Live**（與 Guardian halt check + regime context 連）| RawNewsItem → ProcessedNewsItem → router | N/A | ✅ Live 但**不與 Python ScoutAgent 連**（設計上 Rust 自用）|
| **Rust ai_budget::BudgetTracker** | main.rs init | **Live init**（engine.log「BudgetTracker initialized」）| scope → can_call / record_usage | ai_usage_log=0 rows = 從未真實 record | ⚠ Init 但未實際運作 |
| **Rust Claude Teacher IPC handler** | ipc_server/handlers/teacher.rs | handler 存在 + TeacherLoopHandles 已注入 IPC slot | set_teacher_loop_enabled IPC | N/A | ⚠ Operator-flip only |
| **Combine Layer shadow（INFRA-PREBUILD-1 Part A）** | combine_layer.rs + ExitConfig.shadow_enabled | **`shadow_enabled=false` dormant**（risk_config_live.toml）/ 0 emit / 0 row | ML inference vs physical compare | N/A | 🔴 Dormant（等 Phase 3+ flip）|

### 2.2 Python 真實 AI 調用證據

- `api.log` 04-24 實測：`GET /api/v1/paper/layer2/ollama/status` 200 OK（curl 實測 qwen3.5 9B/27B `available=true`）
- `engine.log` 04-24 實測：StrategistScheduler 5-min cycle 3 次連續調用 IPC + proposal 被拒
- `ai_service.sock` 存在 `/tmp/openclaw/ai_service.sock`，4 uvicorn workers + 1 master process 在跑
- ScoutWorker daemon thread 在 strategy_wiring.py:694 啟動（每 30 分鐘 MarketScanner.scan + ScoutAgent.produce_intel）

### 2.3 成本感知（原則 13）合規度

| 子要求 | 4/01 狀態 | 4/24 狀態 | 變化 |
|--------|-----------|-----------|------|
| 每次 AI 調用計費 | ✅ record_claude_cost / record_call | ✅ + Rust 側 BudgetTracker（但 0 rows 表明 Rust 記錄 gap）| 🟡 Rust 端未寫 |
| cost_edge_ratio 計算 | ✅ | ✅ layer2_cost_tracker.py get_cost_edge_ratio | 不變 |
| cost_edge_ratio ≥ 0.8 → 建議關倉 | ✅ tab-ai.html | ✅ + risk_view_client.py + risk_routes.py call-site | 擴展至 Rust → GUI |
| 每日硬上限 | ✅ $2.00/day | ✅（BudgetConfig total=100+reserve=10+hard_cap=150 分 scope）| 改結構化 5 scope |
| roi_basis 標記 | ✅ | ✅ | 不變 |
| 月度趨勢報告 | ❌ | ❌ | 仍未實施 |

**合規度：~85%（Rust ai_usage_log=0 rows 是新 gap，但 Python Ollama 成本全為 $0 所以不影響實質 ROI）**

---

## 三、實際可用度 / Usability Reality Check

### 3.1 假功能風險盤點（代碼存在但從未真實產出有用輸出）

| # | 組件 | 具體問題 | 嚴重度 | 證據 |
|---|------|---------|-------|------|
| 1 | **Layer 2 Claude Agent Loop** | `layer2_engine.run_session` 只由 `POST /api/v1/paper/layer2/trigger` 手動呼叫 + 依賴 ANTHROPIC_API_KEY（demo env 未設）| **P1（假功能但 spec 上是 operator-triggered）** | grep 確認唯一 caller；engine.log 無 session log entry |
| 2 | **Rust TeacherConsumerLoop** | DEFAULT-OFF Phase 4.1 契約；`teacher_directives=0 rows`；從未 flip enabled=true | P2（等 E3 R6 audit PASS）| engine.log 確認「DEFAULT-OFF」message；DB 0 rows |
| 3 | **Rust edge_predictor** | `use_edge_predictor=false`，shadow_mode=true；~3000 行 ONNX + 預測層邏輯從未被激活 | P1（投入巨大，零產出）| risk_config_live.toml 實測 |
| 4 | **Rust kelly_sizer** | `set_kelly_config` 只在 test 用，runtime 無 caller → 永遠走 fallback guardian_qty | P2（有 fallback 不影響）| grep runtime call-site 結果 |
| 5 | **Rust ml::scorer** | null backend default + 3-tier degrade chain 永遠降到 fixed confidence（無 ONNX 模型載入路徑）| P2 | mod.rs Scorer 結構 |
| 6 | **Rust ml::registry** | `resolve_latest_production_artifact` 無 caller（Phase 3+ 才接）；3 rows 全 shadow 永不被用 | P2（等 Track L）| grep 無 caller |
| 7 | **Combine Layer Shadow Writer** | `ExitConfig.shadow_enabled=false` dormant（INFRA-PREBUILD-1 Part A 設計如此）| P3（設計對）| risk_config_live.toml + A6 healthcheck |
| 8 | **ScoutAgent 新聞/宏觀層** | ScoutAgent 只收 MarketScanner 技術面；Rust news pipeline 不 route 到 Python Scout；事件日曆/token unlock/FOMC 全 stub | **P1** | multi_agent_framework.py:379 ScoutAgent 定義；grep 確認 Python 側無 news/event 真實 producer |
| 9 | **AnalystAgent L2 (Ollama 27B 週報)** | `l2_min_observations=200` 在 demo 環境需數週；observations < 200 時 L2 模式發現永不觸發 | P2（4/01 P2-AI-5 持續）| analyst_agent.py:146 threshold |
| 10 | **H3 L2 後台線程結果** | `run_l2_background` 結果只 log + weight_update；未回注 intent 產出 | P2（4/01 P2-AI-2 持續，但 L2 cache 已加；下一 tick 若 same symbol 才用）| strategist_agent.py:333-347 L2 cache check 僅在 same symbol 有效 |

### 3.2 Layer 2 自主推理循環實裝階段

**原 memory 敘述：「Layer 2 自主推理循環（新聞搜索 / 宏觀判斷 / 工具箱 / 推理鏈記錄）」**

| 子功能 | 實裝階段 | 證據 |
|--------|---------|------|
| 8 tools 工具箱 | **已實裝 Claude function-call schemas**（TOOL_SCHEMAS in layer2_tools.py:67）| layer2_tools.py + SEARCH_PROVIDERS 4 種降級 |
| 新聞搜索（Perplexity / WebPilot / LocalLLM / LocalLLMWeb）| **SearchProvider abstraction 已實裝**；是否能真實 work 取決於 enabled_providers + API keys | layer2_tools.py:543-549 |
| 宏觀判斷 | 由 Claude system prompt + get_market_state / get_recent_decisions 間接；**未獨立模組** | SYSTEM_PROMPT in layer2_engine.py + ToolExecutor |
| 推理鏈記錄 | `Layer2Session.final_summary` 僅存 assistant 最後一段 text，**未逐 iteration 記錄 reasoning chain** | layer2_engine.py:465-469 + layer2_types.py:230 |
| 自主循環觸發 | **沒有** — 依賴 operator 手動觸發或 AnalystAgent directive `trigger_l2_analysis`（但 AnalystAgent 的 L2 是 Ollama 27B，不是 Claude）| grep 確認 |

**結論：Layer 2 agentic framework 骨架完整 + tool box 實裝 + search 降級鏈完備**，但**缺 autonomous trigger + 推理鏈逐步記錄 + ANTHROPIC_API_KEY 生產配置**。demo 環境實際從未跑過 Claude session。

### 3.3 ExecutorAgent Shadow→Live 切換缺 IPC 契約

- `executor_agent.py:482` `_shadow_mode: bool = True` 默認（ExecutorConfig 欄位名 `_shadow_mode`，underscore prefix = 強烈 intended private default）
- `strategy_wiring.py:467` `ExecutorConfig()` 未覆蓋 → shadow live
- `executor_agent.py:382-383` 註解：「Default shadow=True: log intent but don't submit, to avoid Path A/B conflicts」
- **Path A = Rust tick_pipeline 自己走 SignalEngine → IntentProcessor**
- **Path B = Python 5-Agent chain → ExecutorAgent → Rust IPC SubmitOrder**
- 現況：Path A 是生產路徑，Path B 被 shadow 刻意阻擋以避免倉位衝突
- **缺**：shadow→live 切換流程 + 倉位一致性契約 + 熱切 IPC 介面 + live 前 Guardian 交叉 audit

### 3.4 Model Canary / Registry / Promote 流程可用度

- V023 migration + `model_registry.py` state machine + `/api/v1/ml/model_{registry,info,promote}` 路由 — **結構完整**
- `register_quantile_trio_from_onnx_out` wrapper 等 P1-7 C labels 滿 200 才能跑
- `canary_status` 狀態機：`shadow → promoting → production | retired | rejected`
- `POST /model_promote` 需 Operator role + confirm:true + retirement_reason — **gate 嚴**
- **Runtime 實際**：3 rows 全 shadow，**從無 promote 操作發生過**；Rust `OnnxModelManager` 不讀 registry（Phase 3+ wire）
- 結論：**端到端閉環未跑通**（缺 training pipeline 產出 + operator 手動 promote + Rust 消費 registry row）

---

## 四、開發階段評級 / Development Maturity Ratings

### 4.1 成熟度評級表（Dormant / Skeleton / Shadow / Live / Production-grade）

| 子系統 | 4/01 評級 | 4/24 評級 | 變化 | Blocker |
|--------|----------|----------|------|---------|
| **H0 Gate** | A（Production）| A（Production）| 不變 | — |
| **H1 ThoughtGate** | B+（Live）| A-（Live + 模組化獨立）| ↑ | — |
| **H2 Budget Gate** | B（Live）| B+（Live + Rust BudgetTracker init）| ↑ | Rust ai_usage_log=0 rows（record_usage 未呼叫）|
| **H3 ModelRouter** | B（Live L1 / Shadow L2）| B（不變）| 持平 | L2 結果回注機制（P2-AI-2 持續）|
| **H4 Validator** | B-（Live）| B-（Live，模組化獨立）| 微升 | has_edge/reason 字段驗證缺失 |
| **H5 CostLogger** | B（Live Python）| B-（Rust 0 rows）| ↓ | Rust ai_budget::record_usage 從未呼叫 |
| **StrategistAgent** | Live shadow=False | Live + StrategistScheduler 5-min cycle 真跑 | ↑ | Ollama proposal 全被 ±30% delta guard 擋（prompt 需 calibrate）|
| **GuardianAgent** | Live | Live（Rust Guardian 主）| 不變 | — |
| **AnalystAgent L1** | Live | Live | 不變 | — |
| **AnalystAgent L2（Ollama 27B）** | Active（閾值未達）| Active（閾值未達）| 不變 | l2_min_observations=200 demo 難達 |
| **ExecutorAgent** | Shadow intent log | Shadow（`_shadow_mode=True` 默認）| 不變 | **Shadow→Live 切換流程 + Path A/B 一致性契約** |
| **ScoutAgent** | Live（技術面 only）| Live（技術面 only）| 不變 | **新聞/宏觀/事件日曆 全 stub**（P1，4/01 未標） |
| **Layer 2 Claude Agent Loop** | Skeleton | Skeleton + 8 tools + 4 search provider | 微升 | autonomous trigger + ANTHROPIC_API_KEY + 推理鏈記錄 |
| **Rust StrategistScheduler** | — | **Live（5-min cycle）** | 全新 | proposed param delta 全被拒（calibration）|
| **Rust ai_budget::BudgetTracker** | — | **Live init / 0 rows record** | 全新 | record_usage 呼叫點未接 |
| **Rust ai_service_client** | — | **Live**（IPC bridge）| 全新 | — |
| **Rust Claude Teacher** | — | **Dormant（DEFAULT-OFF）** | 全新 | E3 R6 audit PASS |
| **Rust edge_predictor** | — | **Dormant（use=false）** | 全新 | operator 手動 flip + 模型 artifact |
| **Rust linucb** | — | **Live cold-start + Record-only shadow** | 全新 | 不改決策邏輯設計（intended）|
| **Rust ml::kelly_sizer** | — | **Dead（無 runtime caller）** | 全新 | set_kelly_config 接入 |
| **Rust ml::scorer** | — | **Skeleton（null backend）** | 全新 | ONNX 模型 + call-site |
| **Rust ml::registry** | — | **Dormant（3 rows 全 shadow）** | 全新 | Phase 3+ OnnxModelManager 整合 |
| **Rust news pipeline** | — | **Live（Rust 內部用）** | 全新 | 不 route 到 Python ScoutAgent |
| **Combine Layer Shadow Writer** | — | **Dormant（shadow_enabled=false）** | 全新 | Phase 3+ Track L flip |
| **AI Service（Rust→Python IPC）** | Concept | **Live dispatch（5 handlers）** | 全新 | strategist_evaluate 實測；analyst/conductor/scout/guardian runtime 成功率未驗 |
| **local_llm_factory（Ollama / LM Studio shim）** | — | **Live**（default ollama，LM Studio 可切 Mac）| 全新 | — |
| **TruthSourceRegistry** | B+（無持久化）| **未重驗**（本次未查 DB）| — | 持久化（4/01 P1-AI-1 持續）|
| **ExperimentLedger** | B（無持久化）| learning.experiment_ledger=0 rows | ↓ | runtime 無真實寫入 |
| **BacktestEngine** | B | Live route / runtime 量待驗 | — | — |
| **EvolutionEngine** | B- | Live route | — | — |
| **CognitiveModulator（注入 StrategistAgent）** | — | **Live**（strategy_wiring.py:408-413）| 全新 | 實際調整頻率未驗 |

### 4.2 成熟度分布統計

- **Production-grade**: 2 (H0 Gate, local_llm_factory)
- **Live**: 13 (H1/H2/H3 L1/H4/Strategist/Guardian/Analyst L1/Scout技術面/StrategistScheduler/ai_service/ai_budget init/linucb cold-start/news Rust內用/CognitiveModulator)
- **Shadow**: 5 (H3 L2 background/LinUCB record-only/ExecutorAgent default/AnalystAgent L2待達閾/Combine Layer shadow_enabled=false)
- **Skeleton**: 3 (Layer 2 Claude Loop/ml::scorer null backend/ExperimentLedger 0 rows)
- **Dormant**: 5 (TeacherConsumerLoop default-off/edge_predictor use=false/ml::registry 全 shadow/Claude Teacher/Combine Layer shadow writer)
- **Dead**: 2 (kelly_sizer set_config 無 runtime caller/ml_scorer null backend 下 3-tier 永遠降到 fixed)

---

## 五、P 級別新發現問題清單 / New Issues Found

### P1 — 本週/本 Sprint 修復

| # | 問題 | 模組 | 影響 | 狀態 |
|---|------|------|------|------|
| P1-AI-NEW-1 | ScoutAgent 新聞 / 事件日曆 / 宏觀 intel 層 全 stub；memory 敘述「Layer 2 自主推理循環」暗示 Scout 有真實 intel 源但實測只有 MarketScanner 技術面 | `multi_agent_framework.py:379` ScoutAgent + `strategy_wiring.py:_scan_and_produce_intel` | Strategist AI 看不到新聞/事件，edge 評估失真 | NEW |
| P1-AI-NEW-2 | Rust ai_usage_log = 0 rows / strategist_applied_params = 0 rows；BudgetTracker 雖 init 但 record_usage 從未被觸發；StrategistScheduler 5 min cycle 跑了但 proposed params 全被 ±30% delta guard 拒 | `rust/openclaw_engine/src/ai_budget/tracker.rs` + `strategist_scheduler/mod.rs` | Ollama 調用 cost 未 log 到 DB；param tuning 管線實質無產出 | NEW |
| P1-AI-NEW-3 | ExecutorAgent `_shadow_mode=True` 默認 + Path A/B 衝突 — shadow→live 切換流程、Rust IPC SubmitOrder 接受 Python intent 的整合契約 未展開 | `executor_agent.py:482` + `strategy_wiring.py:467` ExecutorConfig() | G-1 未展開 → Python 5-Agent 鏈路無法落地實單 | NEW（本質 = CLAUDE.md §三 明列的 gap（a））|

### P2 — 下一版本

| # | 問題 | 模組 | 影響 | 狀態 |
|---|------|------|------|------|
| P2-AI-NEW-1 | Layer 2 Claude Agent Loop 無 autonomous trigger；reasoning_chain 未逐 iteration 記錄 | `layer2_engine.py` | 原 memory 敘述「Layer 2 自主推理循環」未兌現 | NEW（本質 = CLAUDE.md §三 gap（b））|
| P2-AI-NEW-2 | Rust `edge_predictor`（2965 行，含 ONNX backend + quantile safety + shadow gate）`use_edge_predictor=false` + `shadow_mode=true` 全 dormant；投入巨大零產出 | `rust/openclaw_engine/src/edge_predictor/*` | 大量 Rust 代碼 rot 風險 | NEW |
| P2-AI-NEW-3 | Rust `ml::kelly_sizer` `set_kelly_config` 無 runtime call-site → 永遠走 fallback guardian_qty | `rust/openclaw_engine/src/ml/kelly_sizer.rs` + `intent_processor/mod.rs:546` | 代碼 dead | NEW |
| P2-AI-NEW-4 | AI 使用效果儀表板仍未建（4/01 改進建議 #7）；無 `/api/v1/ai-stats` 暴露 H1 skip 計數 / H4 驗證失敗率 / L1 vs L2 路由比例 | strategy_ai_routes.py 等 | 4/01 改進建議未落地 | 持續 |
| P2-AI-NEW-5 | learning 21 tables（per CLAUDE.md §三 敘述）大部分 0 rows（除 decision_features 等 ETL 表）；ml_parameter_suggestions / linucb_state / rl_transitions / pattern_insights 全 0 | `learning.*` schema | AI Agent 學習輸出未持久化 | NEW |

### P3 — 積壓

| # | 問題 | 狀態 |
|---|------|------|
| P3-AI-NEW-1 | StrategistScheduler 提案被全拒；Ollama judge_edge 的 param 建議 calibration 需 prompt tuning（cooldown_ms proposal 60→150 震盪 150%） | NEW |
| P3-AI-NEW-2 | Model Registry 3 rows 全 canary_status='shadow'，從無 promote 操作；end-to-end 閉環未跑 | NEW |

### 4/01 遺留已驗證仍存在

- P1-AI-1（TruthSourceRegistry 持久化）：本次未重驗 DB 狀態，待 P1-7 完成時同步評估
- P2-AI-1（is_available 同步阻塞）：ollama_client.py:143 grep 未查本次；未修改
- P2-AI-2（H3 L2 結果回注）：已加 L2 cache（same symbol 下次 tick 用），但**非同 symbol 時結果仍丟棄**
- P2-AI-3（cost_tracker 接口不統一）：record_ollama_call 已標 deprecated 並 delegate 到 record_call，**已修**
- P2-AI-4（Conductor Agent 自動編排）：grep 確認 multi_agent_framework.py 有 Conductor class 但未深入驗證；狀態存疑
- P2-AI-5（L2 觸發閾值 demo 環境不合理）：持續未改
- P2-AI-6（EvolutionEngine is_simulated hack）：未查
- P3-AI-1（ollama_client.chat 不傳 think）：未查
- P3-AI-2（strategist_agent.py 行數）：994→**1170 行 + H1/H3/H4 拆出**，已拆分部分解決
- P3-AI-3（H4 驗證不完整）：仍只驗 confidence 欄位

---

## 六、改進建議 / Recommendations

### 6.1 緊急（本 Sprint）

1. **P1-AI-NEW-1**：Rust news pipeline → Python ScoutAgent 接線 — 透過 IPC 或 DB 表把 `news.pipeline::ProcessedNewsItem` 路由給 Python `ScoutAgent.produce_intel`，讓新聞 intel 進 Strategist AI 評估鏈
2. **P1-AI-NEW-2**：BudgetTracker.record_usage 的 Rust 端 call-site 追查 + Ollama 調用 spec 修正（本地 $0 成本仍應產一條 usage 記錄作 audit trail）
3. **P1-AI-NEW-3**（= G-1）：展開 ExecutorAgent shadow→live 切換流程 spec — 定義 Path A/B 切換 IPC handshake + 倉位一致性契約 + Guardian 交叉 audit

### 6.2 近期（下 Sprint）

4. **P2-AI-NEW-1**：Layer 2 Claude Agent Loop autonomous trigger — 在 risk/market regime 變化大時自動觸發 + 推理鏈逐步落 PG `learning.pattern_insights`
5. **P2-AI-NEW-4**：`GET /api/v1/ai-stats` 端點 — 暴露 H1 skip 計數 / H3 路由比例 / H4 驗證失敗率 / Ollama 延遲分佈 / StrategistScheduler accept rate（當前 0/3 = 0%！）
6. **StrategistScheduler prompt calibration**：Ollama 9B 給出的 cooldown_ms 建議 60→150ms 震盪（150%），超過 ±30% 全被拒；需 prompt tuning 或 bounded output constraint

### 6.3 長期（Phase 4+ 或 Track L live）

7. **edge_predictor / ml::scorer / ml::registry 端到端閉環**：P1-7 C labels 滿 200 → run_training_pipeline.py → register_quantile_trio → operator promote → Rust OnnxModelManager 載入 → exit decision 開始用 ONNX
8. **Claude Teacher loop E3 R6 audit** 完成後 flip `teacher_loop_enabled=true` 觀察 directive 產出
9. **Combine Layer shadow_enabled=true** flip + 14d 觀察對比 physical vs ML exit
10. **ScoutAgent 新聞/事件/token_unlock / FOMC 資料源**：決定是整合 Rust news pipeline 還是 Python 獨立實作

---

## 七、對比基準差異彙總（4/01 vs 4/24）

| 維度 | 4/01 | 4/24 | 變化 |
|------|------|------|------|
| Python AI 行數 | 7,815 | 10,959（+40%）| ↑ |
| Rust AI 行數 | — | 8,942（全新）| 全新 |
| AI 相關 API routes | — | 39 live | — |
| StrategistAgent 切換 | shadow=False | shadow=False + StrategistScheduler 5-min | 質變（Rust 主動 push）|
| H1-H4 獨立模組化 | 內嵌 994 行 | h1_thought_gate / model_router / h4_validator 獨立 | ↑ |
| H0 Gate | 832 行 live | **971 行**（+17% 強化）| 微升 |
| Claude Teacher | 概念 | **3,757 行 DEFAULT-OFF** | 全新 dormant |
| Edge Predictor | 概念 | **2,965 行 use=false** | 全新 dormant |
| LinUCB | 概念 | 1,003 行 cold-start record-only | 全新 shadow |
| News Pipeline | Python 概念 | 2,231 行 Rust live（不連 Python Scout）| 全新 |
| Model Registry | 概念 | V023 migration + 3 routes + 3 rows shadow | 全新 skeleton |
| AI Service (Rust↔Python IPC) | 概念 | `ai_service.sock` live + 5 handlers | 全新 live |
| BudgetTracker | Python 版 live | Rust + Python 雙端 init；Rust 0 rows | 量升質未升 |
| Ollama max_retries=0 / think=False | ✅ | ✅ + local_llm_factory（LM Studio shim） | ↑ 跨平台 |
| learning 21 tables | TruthSourceRegistry 822 行無持久化 | 大部 0 rows + model_registry 3 shadow + decision_features 6.19M rows（ETL活躍）| 分化 |

**整體：代碼投入量翻倍（19,901 行），但 runtime 實質產出（AI 真正改決策）比例**降低**（大量 dormant/shadow）。**

---

## 附錄 A：Linux Runtime 實測（engine PID 912616, uvicorn PID 912671 / 2026-04-24 03:01 重啟後）

- `/tmp/openclaw/engine.sock` 存在
- `/tmp/openclaw/ai_service.sock` 存在
- `http://127.0.0.1:8000/api/v1/paper/layer2/ollama/status` 200 OK：`available=true, qwen3.5:9b-q4_K_M + qwen3.5:27b-q4_K_M`
- `http://127.0.0.1:8000/api/v1/ai_budget/status` 回 `ipc_error:RuntimeError`（ai_budget IPC 未通 — 另一個 gap）
- engine.log 確認 5-min StrategistScheduler cycle + LinUcbRuntime cold-start + BudgetTracker init + TeacherConsumerLoop DEFAULT-OFF spawn

## 附錄 B：39 個 AI 相關 /api/v1/ 路由（全部 live 註冊）

```
/api/v1/ai_budget/{config, status}
/api/v1/backtest/{run, status}
/api/v1/evolution/{run, status}
/api/v1/experiments/{propose, status, {id}, {id}/observe}
/api/v1/governance/h0-gate/status
/api/v1/input/experiment
/api/v1/learning/experiment/{id}/{approve, complete}
/api/v1/learning/experiments
/api/v1/ml/{model_info, model_promote, model_registry}
/api/v1/paper/{ai-cost, layer2/config, layer2/cost, layer2/cost/adaptive, layer2/cost/pricing, layer2/cost/reset, layer2/ollama/status, layer2/sessions, layer2/sessions/{id}, layer2/trigger, risk/agent-adjust, risk/ai-context}
/api/v1/scout/{alerts, event-alert, intel, market-signal, status}
/api/v1/strategist/{history, history/summary, history/{id}/effect}
/api/v1/strategy/ai/status
```

## 附錄 C：Learning Schema 表 Runtime Rows（PG 實測，2026-04-24 04:30）

| Table | 近似 rows | 狀態 |
|-------|-----------|------|
| decision_features | **6,190,378** | ✅ ETL pipeline 活躍（真實產出）|
| scorer_training_features | **532,386** | ✅ 活躍 |
| james_stein_estimates | **624** | ✅ EdgeEstimator hourly 活躍 |
| cpcv_results | 56 | ⚠ 曾跑 |
| exit_features | 244 | ✅ 累積中 |
| model_registry | 3 | 🔴 全 canary_status=shadow |
| ai_usage_log | 0 | 🔴 BudgetTracker 未寫 |
| strategist_applied_params | 0 | 🔴 StrategistScheduler proposal 全被拒 |
| teacher_directives | 0 | 🔴 TeacherConsumerLoop DEFAULT-OFF |
| directive_executions | 0 | 🔴 同上 |
| experiment_ledger | 0 | 🔴 ExperimentLedger runtime 無寫入 |
| pattern_insights | 0 | 🔴 AnalystAgent L2 未觸發 |
| decision_shadow_exits | 0 | 🔴 Combine Layer shadow_enabled=false |
| linucb_state | 0 | 🔴 LinUCB record-only 未持久化 |
| rl_transitions | 0 | 🔴 無 consumer |
| ml_parameter_suggestions | 0 | 🔴 無 consumer |

---

*AI-E 下次審計建議：P1-7 C labels 滿 200 + 第一個 model promote 動作完成後重評，屆時 `learning.ai_usage_log` / `model_registry` / `decision_shadow_exits` 會有真實 rows，運行時可用度將有顯著改善。*

AI-E AUDIT DONE: docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-04-24--ai_effectiveness_audit.md
