# AI 使用效果評估報告 / AI Usage Assessment Report

**角色**: AI-E (AI Engineer)
**日期**: 2026-04-12
**範圍**: OpenClaw/Bybit AI Agent 交易系統全部 AI/LLM 集成點

---

## 一、AI 集成點總覽 / AI Integration Points Overview

### 1.1 系統 AI 架構（設計 vs 實現）

設計架構宣稱 5 層 AI 治理（H0-H5）+ 5 Agent 系統 + Layer 2 深度推理 + ML/RL 學習管線。以下逐一評估真實狀態。

| 組件 | 狀態 | 說明 |
|------|------|------|
| H0 本地判斷（確定性） | ✅ Production | 純規則邏輯，無 AI 調用 |
| H1 ThoughtGate | ⚠️ Partial | 代碼完整但僅在 Python Agent 鏈中使用，未接入 Rust tick pipeline |
| H2 Budget Gate | ⚠️ Partial | Python Layer2CostTracker 完整；Rust ai_budget 完整但 teacher_loop 默認 OFF |
| H3 ModelRouter | ⚠️ Partial | 路由邏輯完整（l1_9b/l1_27b/l2 三層），但實際 LLM 調用依賴 Ollama 是否在線 |
| H4 Validator | ✅ Production | 純驗證邏輯，代碼完整且有測試覆蓋 |
| H5 Cost Logging | ✅ Production | Layer2CostTracker + Rust BudgetTracker 雙軌，代碼完整 |
| Layer 2 AI Engine | ⚠️ Partial | Claude API 集成代碼完整，但需 ANTHROPIC_API_KEY 才能運行 |
| 5 Agent 系統 | ⚠️ Partial | 框架完整但全部運行在 Shadow 模式 |
| ML 學習管線 | ⚠️ Partial | 代碼完整但缺數據，未投產 |
| 新聞管線 | ✅ Production | Rust 側 3 providers + 60s 排程，已接入 main.rs |

---

## 二、逐組件深度評估 / Detailed Component Assessment

### 2.1 LocalLLMClient 抽象層

**狀態**: ✅ Production — 接口設計完整

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/local_model_tools/local_llm_client.py`
- **ABC 接口**: `LocalLLMClient`（L59-116），定義 `generate()` / `is_available()` / `get_model_info()` / `provider_name`
- **兩個實現**:
  - `OllamaProvider`（L118-168）：包裝 `OllamaClient`，代理所有調用
  - `LMStudioProvider`（L170-252）：OpenAI 兼容 API，`localhost:1234`
- **評級理由**: ABC 清晰，兩個 provider 均可運行。但實際業務代碼大多直接用 `OllamaClient` 而非通過 `LocalLLMClient` 抽象層，使用率偏低。

### 2.2 OllamaClient（本地 LLM 推理）

**狀態**: ✅ Production — 唯一真實運行的 LLM 調用入口

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ollama_client.py`
- **配置**: 默認模型 `qwen3.5:9b-q4_K_M`（L48），27B 變體 `qwen3.5:27b-q4_K_M`（L497）
- **端點**: `http://127.0.0.1:11434`（Ollama REST API）
- **功能**:
  - `generate()`（L197-238）：單輪 `/api/generate`，支持 `think` 參數控制 CoT
  - `chat()`（L242-287）：多輪 `/api/chat`
  - `classify()`（L291-331）：文本分類（低溫度 0.1，短回答）
  - `judge_edge()`（L333-363）：交易邊際判斷（JSON 輸出）
  - `is_available()`（L126-170）：60s TTL 緩存，1s 超時健康檢查
- **安全**: `max_retries=0`（CLAUDE.md 硬邊界，L63），fail-closed
- **單例**: `get_ollama_client()` + `get_ollama_client_27b()`（L466-498），線程安全
- **評級理由**: 代碼品質高，生產就緒。前提是 Ollama 服務在線且模型已加載。

### 2.3 Layer 2 AI 推理引擎（Claude API 集成）

**狀態**: ⚠️ Partial — 代碼完整但需 API Key 才能運行

#### 2.3.1 Layer2Engine

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_engine.py`
- **L1 Triage**（L197-340）：
  - **首選**: Claude Haiku（`claude-haiku-4-5-20251001`，定義於 `layer2_types.py:L52`）經 Anthropic SDK 調用
  - **回退**: `_l1_triage_local()`（L259-340）通過 Ollama/Qwen 本地推理
  - 這是**真實的 Claude API 調用**（L219-228），不是 stub
- **L2 Agent Loop**（L344-558）：
  - 完整的 Claude messages API + tool_use 循環
  - 8 個工具定義（get_market_state, web_search, submit_recommendation 等）
  - 模型升級 triage（Sonnet → Opus，L562-605）
  - Shadow decision 提交到 paper trading（L609-678）
- **Anthropic Client**（L703-731）：
  - `_get_anthropic_client()` 讀取 `ANTHROPIC_API_KEY` 環境變量
  - **無 key 時返回 None**，L2 session 直接 fail-soft，不會崩潰
  - **真實 SDK 調用**：`import anthropic; anthropic.Anthropic(api_key=...)`（L718-719）

#### 2.3.2 Layer2CostTracker

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py`
- **硬上限**: `$2.00/天`（定義於 `layer2_types.py:L60`，DOC-08 §4）
- **自適應預算**: 7 日 ROI 驅動倍率（0.3x - 2.0x），5 個 tier（`layer2_types.py:L66-72`）
- **PnL 歸因回填**: `backfill_pnl_attribution()`（L363-375）
- **統一調用記錄**: `record_call()`（L532+）支持 Ollama/Claude/Perplexity 全 provider
- **持久化**: `runtime/layer2_cost_state.json`，原子寫入（tmp→replace）
- **狀態**: ✅ Production — 完全可用

#### 2.3.3 Layer2 工具系統

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_tools.py`
- **8 個工具 schema**（L67-286）：完整的 Anthropic tool_use JSON schema
- **4 層 SearchProvider 降級**:
  1. `PerplexitySearchProvider`（L293-382）：需 `PERPLEXITY_API_KEY`
  2. `LocalLLMWebSearchProvider`（L385-445）：Ollama + web-pilot 腳本
  3. `LocalLLMSearchProvider`（L448-491）：純 Ollama 知識
  4. `WebPilotSearchProvider`（L494-541）：DuckDuckGo (`duckduckgo-search` 庫)
- **SSRF 防護**: `_fetch_url()`（L800+）含 IP/域名黑名單（L808-826）
- **狀態**: ✅ Production（工具代碼完整，但 Perplexity 需 API key）

#### 2.3.4 Layer2 API 路由

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_routes.py`
- **11 條路由**（L57-435）：trigger / sessions / sessions/{id} / cost / cost/reset / cost/pricing (GET+POST) / cost/adaptive / config (GET+POST) / ollama/status
- **GUI**: `tab-ai.html` 完整的 AI Engine 控制台（成本儀表板 + 觸發按鈕 + session 列表）
- **狀態**: ✅ Production

#### 2.3.5 Layer2 類型系統

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_types.py`
- **定價表**: Haiku $0.80/$4.00、Sonnet $3.00/$15.00、Opus $15.00/$75.00（L334-353）
  - ✅ `last_verified_date: "2026-04-12"`，未過期
- **模型 ID**: 使用 `claude-haiku-4-5-20251001` / `claude-sonnet-4-6-20250326` / `claude-opus-4-6-20250326`（L51-55）
- **狀態**: ✅ Production

### 2.4 H1-H5 治理層

#### H1 ThoughtGate

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h1_thought_gate.py`
- **功能**: AI 調用前確定性閘門 — 預算檢查 + 複雜度評分（閾值 0.3）+ 冷卻期（30s 同 symbol 去重）
- **調用鏈**: `StrategistAgent._handle_intel()`（L261）→ `H1ThoughtGate.check()`（L342）→ 決定是否調用 Ollama
- **狀態**: ⚠️ Partial — 代碼完整且正確，但只在 Python multi-agent 框架中使用。**Rust tick pipeline 不經過 H1**。

#### H3 ModelRouter

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/model_router.py`
- **路由邏輯**: 4 級路由 — complexity < 0.5 → l1_9b / 0.5-0.8 → l1_27b / ≥ 0.8 → 根據 context（confidence/cusum/vol/new_symbol）升級至 l1_5 或 l2（後台線程），無 context 向後兼容直接 l2
- **L2 結果緩存**: TTL 1h / 容量 200 條
- **預算閘控**: 可注入 budget_checker callback
- **狀態**: ⚠️ Partial — 同上，僅在 Python Agent 框架中活躍。

#### H4 Validator

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h4_validator.py`
- **驗證項**: confidence 範圍 [0,1] / has_edge 布林 / reason 非空 / action 合法集合
- **狀態**: ✅ Production — 純邏輯驗證，代碼無依賴，完整測試覆蓋。

#### H5 Cost Logging

- **Python 側**: `Layer2CostTracker.record_call()`（詳見 §2.3.2）
- **Rust 側**: `ai_budget::BudgetTracker`（詳見 §2.6）
- **狀態**: ✅ Production — 雙語言雙軌道，代碼完整。

### 2.5 5 Agent 系統

| Agent | 文件 | 狀態 | 說明 |
|-------|------|------|------|
| ScoutAgent | `multi_agent_framework.py:376` | ⚠️ Partial | 產出 IntelObject，框架級消息傳遞正常；但依賴 Python 策略管線（已退場） |
| StrategistAgent | `strategist_agent.py` | ⚠️ Partial | 調用 Ollama `judge_edge()` 評估信號邊際；Shadow 模式下不產出下游 intent |
| GuardianAgent | `guardian_agent.py` | ⚠️ Partial | 5 項風控檢查（槓桿/回撤/相關性/Sharpe/方向衝突）；評估依賴 Qwen 3.5 |
| AnalystAgent | `analyst_agent.py` | ⚠️ Partial | L1 層指標計算正常；L2 層 `analyze_patterns()` 需 Qwen 27B |
| ExecutorAgent | `executor_agent.py:117` | ⚠️ Partial | 508 行完整實現（GovernanceHub 集成 / Decision Lease / intent 去重 / 執行報告），但 ARCH-RC1 後實際交易走 Rust 引擎，Python 側為 Shadow/advisory |
| Conductor | `multi_agent_framework.py:642` | ⚠️ Partial | 編排 5 Agent 的消息路由正常，但整體 Agent 系統處於 Shadow 模式 |

**關鍵事實**: 5 Agent 系統的代碼框架完整（MessageBus / AgentRole / IntelObject / TradeIntent / RiskVerdict 全部定義），但在 ARCH-RC1 後 Python 交易執行層已退場（DEAD-PY-2），**所有實際交易決策走 Rust tick pipeline**。Python Agent 系統目前的角色是：
1. StrategistAgent 可通過 Ollama 對信號做 AI 評估（judge_edge），但結果是 advisory 非 binding
2. GuardianAgent 的風控邏輯已被 Rust RiskConfig + Reconciler + ConfigStore 取代
3. AnalystAgent 的 L1 指標計算仍有價值（trade attribution），但 L2 pattern discovery 從未投產

### 2.6 Rust 側 AI 基礎設施

#### 2.6.1 AI Budget Tracker（Rust）

- **文件**: `rust/openclaw_engine/src/ai_budget/`（mod.rs + tracker.rs + config_io.rs + pricing.rs + usage_io.rs）
- **功能**: 月度 USD 預算強制（5 scope：local_total / platform_hard_cap / agent_teacher / agent_analyst / agent_reserve）
- **三段降級**: SoftWarn 80% / HardLimit 95% / Killswitch 100%（均為 `local_total` 的比率，默認 $100 時分別為 $80/$95/$100）
- **DB 表**: `learning.ai_budget_config` + `learning.ai_usage_log`（V010 遷移）
- **IPC**: `get_ai_budget_status` / `update_ai_budget_config` 兩個 handler
- **狀態**: ✅ Production — 代碼完整，DB schema 已部署，IPC 接線完成。定價表為硬編碼占位（4-17 子任務待換為 DB 表）。

#### 2.6.2 Claude Teacher（Rust）

- **文件**: `rust/openclaw_engine/src/claude_teacher/`（9 個子模塊，含 applier_test_fixtures）
- **完整管線**:
  - `client.rs`：`LlmClient` trait（L78）+ `AnthropicClient`（reqwest HTTP）+ `MockClient`
  - `parser.rs`：嚴格 fail-closed JSON 解析（`adjust_param` / `recommend_action` 等 directive 類型）
  - `writer.rs`：寫入 `learning.teacher_directives` + `learning.experiment_ledger`
  - `consumer_loop.rs`：`TeacherConsumerLoop` 定時拉取 directive
  - `applier.rs`：`DirectiveApplier` 應用 directive（改參數/建議動作）
  - `governance_impl.rs`：治理核心包裝
  - `strategy_ipc_impl.rs`：通過 IPC 發送參數調整到策略
  - `outcome_tracker.rs`：Sharpe 追蹤，directive 執行結果回填
- **安全**:
  - `ANTHROPIC_API_KEY` 不存在 → `LlmClientError::MissingApiKey`（fail-closed）
  - BudgetTracker.record_usage 失敗 → 中止（TeacherError::Budget）
  - 測試覆蓋 mock client / budget failure abort / parser rejection
- **狀態**: ⚠️ Partial — 代碼完整且測試覆蓋良好，但：
  - `teacher_loop_enabled` 默認 OFF（L107, learning_config.rs）
  - 需 `ANTHROPIC_API_KEY` 才能發起真實 LLM 調用
  - Directive → 策略參數調整的完整鏈路需 operator IPC 啟用

#### 2.6.3 LinUCB 上下文 Bandit（Rust）

- **文件**: `rust/openclaw_engine/src/linucb/`（5 個子模塊）
- **功能**:
  - `inference.rs`：ridge-regression UCB 計算（theta = A^{-1}b, UCB = theta^T x + alpha * sqrt(x^T A^{-1} x)）
  - `arms_v1_15.rs`：v1_15 cold-start arm 列舉
  - `state_io.rs`：PG 讀寫 `learning.linucb_state`
  - `runtime.rs`：運行時 arm 選擇（`ArmSelection`）
  - `schema_hash.rs`：feature schema hash（fail-closed 版本校驗）
- **Rust tick pipeline 集成**: `on_tick.rs` 中調用 LinUCB `select_arm()` 進行策略選擇
- **Python 訓練對齊**: `ml_training/linucb_trainer.py` 與 Rust BYTEA 編碼逐 byte 對齊
- **狀態**: ⚠️ Partial — 推理代碼完整，但需要足夠的歷史決策數據填充 A/b 矩陣。Cold-start 狀態下等效隨機選擇。

#### 2.6.4 新聞管線（Rust）

- **文件**: `rust/openclaw_engine/src/news/`（pipeline.rs + mod.rs + 其他子模塊）
- **功能**: 3 providers（CryptoPanic + CoinTelegraph RSS + Google News RSS）→ 去重 → severity 評分 → DB 寫入 → 三路 fan-out（Guardian/Regime/Learning）
- **排程**: `main.rs` 中 60s 定時觸發，受 `LearningConfig.switches.news_pipeline_enabled`（Rust `MlSwitches` struct field）熱重載開關控制
- **狀態**: ✅ Production — 完整接入生產管線，熱重載 gate 控制。

### 2.7 ML/DL 學習管線

#### 2.7.1 Python ML Training 套件

- **目錄**: `/home/ncyu/BybitOpenClaw/srv/program_code/ml_training/`（21 個 .py 文件）
- **核心組件**:

| 文件 | 功能 | 狀態 |
|------|------|------|
| `scorer_trainer.py` | LightGBM CPCV 訓練 ATR-normalized PnL 預測器 | ⚠️ Partial（代碼完整，需數據） |
| `linucb_trainer.py` | LinUCB 批次重建 A/b 充分統計量 | ⚠️ Partial（需 decision_context_snapshots 數據） |
| `thompson_sampling.py` | NIG 後驗 Thompson Sampling（跨策略分配） | ⚠️ Partial（Phase 3b 僅 Python） |
| `cpcv_validator.py` | 組合清洗交叉驗證 | ⚠️ Partial |
| `label_generator.py` | ATR-normalized PnL 標籤生成 | ⚠️ Partial |
| `calibration.py` | 概率校準（Platt/isotonic placeholder） | ❌ Stub |
| `onnx_exporter.py` | ONNX 導出（ort integration 延後） | ❌ Stub |
| `run_training_pipeline.py` | 端到端管線編排 | ⚠️ Partial（skip_onnx=True 默認） |
| `parquet_etl.py` | Parquet ETL 載入 | ⚠️ Partial |
| `james_stein_estimator.py` | James-Stein 收縮估計（Phase 5 暫停） | ⚠️ Partial（Phase 5 PAUSED） |
| `optuna_optimizer.py` | Optuna 超參數搜索 | ⚠️ Partial |
| `dl3_foundation.py` | DL3 基礎模型框架 | ❌ Stub |
| `dl3_ab_runner.py` | DL3 A/B 測試 | ❌ Stub |
| `dl3_go_no_go.py` | DL3 Go/No-Go 決策 | ❌ Stub |
| `edge_cluster_analysis.py` | Edge 聚類分析 | ⚠️ Partial |
| `realized_edge_stats.py` | 實現 edge 統計 | ⚠️ Partial |
| `weekly_report_generator.py` | 周報生成 | ⚠️ Partial |
| `leakage_check.py` | 數據洩漏檢查 | ⚠️ Partial |
| `linucb_arm_migration.py` | LinUCB arm 遷移 | ⚠️ Partial |
| `linucb_shadow_compare.py` | LinUCB shadow 比較 | ⚠️ Partial |

#### 2.7.2 EvolutionEngine

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/local_model_tools/evolution_engine.py`
- **功能**: 策略參數網格搜索 + BacktestEngine 評估 + TruthSourceRegistry 注入
- **安全**: `is_simulated=True` 強制（docstring L36 + `__post_init__` L123），原則 7 隔離（不碰 live/paper 配置）
- **狀態**: ⚠️ Partial — 代碼完整，但 Phase 5 暫停後，策略 gross edge 為負，優化無意義。

#### 2.7.3 LearningTierGate（L1-L5 進化）

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_tier_gate.py`
- **5 級進化**:
  - L1 Post-Trade Review（被動記錄，零成本）— ⚠️ Partial
  - L2 Pattern Discovery（500+ 觀察 + 勝率 > 20%）— 🔲 Not Started（未達解鎖條件）
  - L3 Hypothesis & Experiment — 🔲 Not Started
  - L4 Strategy Evolution — 🔲 Not Started
  - L5 Meta-Learning — 🔲 Not Started（需 6+ 月數據 + operator 批准）
- **狀態**: ⚠️ Partial — 框架代碼完整（晉升邏輯 + 審計 + 線程安全），但只有 L1 在運行。

### 2.8 感知數據平面

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/perception_data_plane.py`
- **功能**: 統一數據註冊，強制認知層級標注（fact/inference/hypothesis）+ 新鮮度追蹤（FRESH→EXPIRED）
- **狀態**: ⚠️ Partial — 代碼完整，但主要被 Python Agent 系統使用；Rust tick pipeline 有自己的 freshness 檢查。

### 2.9 數據源強制器

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/data_source_enforcer.py`
- **功能**: 標注 AI 生成數據 vs 交易所原始數據，防止 AI 推斷被當事實使用
- **狀態**: ⚠️ Partial — 同上，主要在 Python Agent 框架中使用。

---

## 三、真實 AI 調用 vs Stub 判定 / Real AI Calls vs Stubs

### 3.1 真實 AI 調用（代碼路徑存在且可運行）

| 調用點 | Provider | 文件:行號 | 前提條件 |
|--------|----------|-----------|----------|
| L1 Triage (Claude) | Anthropic Haiku | `layer2_engine.py:218-228` | ANTHROPIC_API_KEY |
| L1 Triage (本地回退) | Ollama/Qwen 9B | `layer2_engine.py:277-287` | Ollama 在線 |
| L2 Agent Loop | Anthropic Sonnet/Opus | `layer2_engine.py:435-445` | ANTHROPIC_API_KEY |
| Model Upgrade Triage | Anthropic Haiku | `layer2_engine.py:576-585` | ANTHROPIC_API_KEY |
| StrategistAgent edge | Ollama/Qwen 9B | `ollama_client.py:333-363` (`judge_edge`) | Ollama 在線 |
| StrategistAgent classify | Ollama/Qwen 9B | `ollama_client.py:291-331` (`classify`) | Ollama 在線 |
| Perplexity Search | Perplexity API | `layer2_tools.py:306-382` | PERPLEXITY_API_KEY |
| Local LLM Search | Ollama/Qwen 9B | `layer2_tools.py:461-491` | Ollama 在線 |
| Claude Teacher (Rust) | Anthropic (reqwest) | `claude_teacher/client.rs:78-80` | ANTHROPIC_API_KEY |
| Ollama Status (GUI) | Ollama `/api/tags` | `layer2_routes.py:382-409` | Ollama 在線 |

### 3.2 Stub / 未實現 / 默認關閉

| 組件 | 狀態 | 原因 |
|------|------|------|
| ExecutorAgent | ⚠️ Partial | 代碼完整（508 行），但 ARCH-RC1 後實際交易走 Rust 引擎 |
| DL3 Foundation/AB/GoNoGo | ❌ Stub | Phase 4+ 計劃，代碼僅框架 |
| ONNX Export | ❌ Stub | ort 集成延後 |
| Calibration (Platt/isotonic) | ❌ Stub | 占位符 |
| Teacher Loop (Rust) | 默認 OFF | `teacher_loop_enabled: false`（learning_config.rs:107） |
| L2-L5 Learning Tiers | 🔲 未達解鎖條件 | 需 500+ 觀察 / 2+ 週 / 正 ROI |
| Strategist Agent (live) | Shadow 模式 | 不產出實際 intent |
| AI Consultation (strategy) | 未接線 | strategy_wiring.py 提到但未實現端到端 |

---

## 四、Agent Profiles（CCAgentWorkSpace）

- **目錄**: `/home/ncyu/BybitOpenClaw/srv/docs/CCAgentWorkSpace/`
- **16 個角色 profile**: PM, PA, FA, E1, E1a, E2, E3, E4, E5, QC, A3, R4, TW, AI-E, QA, CC
- **狀態**: ✅ — 這些是**開發流程角色**（Claude Code 對話中的虛擬角色），非交易 Agent。完整定義在各自的 `profile.md` 中。
- **注意**: 不要混淆這 16 個開發角色與系統內的 5 個交易 Agent（Scout/Strategist/Guardian/Analyst/Executor）。

---

## 五、可接入度分析 / Integration Readiness Assessment

### 5.1 使 H1-H5 完全運行所需的工作

| 層 | 當前差距 | 所需工作量 | 優先級 |
|----|---------|------------|--------|
| H0 | 無差距 | 0 | -- |
| H1 | 僅在 Python Agent 框架中使用 | 如果要在 Rust pipeline 中加入 AI 閘門，需在 `on_tick.rs` 添加 IPC 調用 H1 | P2 |
| H2 | Python 和 Rust 雙軌均工作 | 打通兩側 budget 同步（目前各自獨立） | P2 |
| H3 | 同 H1（Python 側 4 級路由 l1_9b/l1_27b/l1_5/l2 已完整） | Rust pipeline 加入模型選擇邏輯 | P3 |
| H4 | 完全可用 | 0 | -- |
| H5 | 完全可用 | 0 | -- |

### 5.2 ML 訓練數據管線就緒度

| 數據源 | 狀態 | 說明 |
|--------|------|------|
| K 線 / OHLCV | ✅ | Bybit WS/REST → Postgres，KlineManager 正常 |
| 交易記錄（fills） | ⚠️ | Paper engine 產生 fills，但 PNL-FIX-1/2 揭露歷史數據被污染 |
| 決策上下文快照 | ⚠️ | `decision_context_snapshots` 表已建，`context_writer.rs` 已接線，但需乾淨數據 |
| Feature 提取 | ⚠️ | `parquet_etl.py` 和 `label_generator.py` 代碼就緒，但需重跑 |
| LinUCB state | ⚠️ | PG schema + BYTEA IO 就緒，需批次訓練填充 |
| 新聞數據 | ✅ | 3 providers 已接入，60s 抓取 |

### 5.3 Feature 提取完整度

- **技術指標**: KlineManager → IndicatorEngine（MA/BB/ATR/RSI 等）✅
- **微結構**: observer verdict（資金費率 / 訂單簿深度 / 波動率）✅
- **LinUCB Context**: `FEATURE_NAMES_V1`（`linucb/runtime.rs`）定義了上下文特徵向量 ✅
- **缺失**: DL3 特徵工程（dl3_foundation.py 僅框架）❌

### 5.4 從 Shadow 到 Live AI 決策的路徑

1. **前置條件已滿足**:
   - Ollama 客戶端 ✅
   - Claude API 集成代碼 ✅
   - 成本追蹤與預算控制 ✅
   - AI 輸出驗證 ✅
   - 新聞管線 ✅

2. **需要完成的工作**（按優先級）:
   - **P0**: 策略重做（G-SR-1），當前所有策略 gross edge 為負，AI 優化無意義
   - **P1**: 積累 21+ 天乾淨 paper trading 數據（LG-1，05-01 到期）
   - **P1**: 啟用 `teacher_loop_enabled`，讓 Claude Teacher 開始產出 directive
   - **P2**: LinUCB 批次訓練（需 200+ 乾淨決策數據）
   - **P2**: LightGBM scorer 訓練 + 校準
   - **P3**: AI Agent（G-1 W22-W23）從 Shadow → Advisory → Binding

---

## 六、結論與建議 / Conclusions & Recommendations

### 6.1 整體評估

**AI 基礎設施建設量充足（~15,000 行 AI 相關代碼），但實際投入生產的 AI 功能有限。**

- **已投產**: Ollama 客戶端 + Layer2 API/GUI + 新聞管線 + 成本追蹤 + Rust BudgetTracker
- **代碼完整待啟用**: Claude Teacher + LinUCB + Layer2 Agent Loop + 5 Agent 框架
- **真正的瓶頸不是代碼而是數據**: PNL-FIX-1/2 後所有歷史數據被污染，需要乾淨的 21+ 天重跑

### 6.2 風險提醒

1. ~~**定價表過期**~~: ✅ 已更新至 2026-04-12，`is_stale()` 不會觸發（原報告誤判）
2. **Python Agent 系統的定位模糊**: ARCH-RC1 後 Python 交易邏輯全退場，但 5 Agent 框架代碼仍在（含 ExecutorAgent 508 行完整實現）。需明確其角色是 advisory 還是計劃重構為 Rust
3. **雙軌 AI 預算獨立運行**: Python Layer2CostTracker 和 Rust BudgetTracker 各自追蹤，無同步機制，可能導致預算感知不一致

### 6.3 優先行動建議

1. ~~更新 Layer2 定價表~~ ✅ 已是 2026-04-12（原報告誤判）
2. 等待策略重做（G-SR-1）完成後，再啟用 ML 訓練管線
3. W22 G-1 AI Agent 啟動時，建議先聚焦 StrategistAgent 的 Ollama judge_edge 接線（已有代碼），而非從零搭建

---

*報告生成工具: Claude Opus 4.6 AI-E 角色*
*代碼庫 commit: 基於 2026-04-12 main 分支*
