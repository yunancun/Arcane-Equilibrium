# AI-E 審計報告：AI 使用效果與開發情況評估
# AI-E Audit: AI Effectiveness and Development Assessment
# 日期：2026-04-01
# 對比基準：2026-03-31 全系統審計（PM_review 71 項問題清單）
# 審核員：AI-E（AI Effectiveness Evaluator）

---

## 執行摘要 / Executive Summary

| 指標 | 3/31 基準 | 4/01 當前 | 變化 |
|------|----------|----------|------|
| 測試總數 | 2,480 | 3,349 (3,310 passed) | +869 (+35%) |
| AI 相關代碼行數 | ~4,500 估計 | 7,815（9 核心模組） | +74% |
| AI 相關測試函數 | ~180 估計 | 492（13 測試文件） | +173% |
| H0-H5 治理層 | H0 未接入, H1-H5 部分 | H0 完整接入, H1-H5 全部運行 | 質變 |
| 學習管線模組 | TruthSourceRegistry 缺 | TSR + ExperimentLedger + EvolutionEngine + BacktestEngine | +4 模組 |
| Agent 系統 | 5 Agent 部分接通 | 5 Agent 全鏈路 + shadow=False 切換 | 質變 |
| Commits (3/31-4/01) | — | 109 | 高密度開發 |

**整體評級：B+（從 3/31 的 C+ 提升）**

主要進步：H0 Gate 完整實現 + H1-H5 全面接入 + 學習管線三層落地 + shadow=False 切換。
主要不足：AI 實際交易影響仍在 demo_only 模式，學習管線無真實數據驗證，L2 Claude 路徑依賴外部 API key。

---

## 一、March 31 問題修復進度核實 / Issue Fix Progress Verification

### 1.1 AI 相關 P0 問題（全部已修復 ✅）

| # | 問題 | 狀態 | 驗證方式 |
|---|------|------|---------|
| P0-7 | layer2_engine "not worth" 否定檢測誤判 | ✅ 已修復 | 代碼確認：`_NEGATION_RE` + `_POSITIVE_RE` 詞邊界正則（layer2_engine.py:74-78） |

### 1.2 AI 相關 P1 問題

| # | 問題 | 狀態 | 說明 |
|---|------|------|------|
| P1-4 | Decision Lease 閉環驗證 | ✅ Wave 3c | acquire_lease() 已補入 executor_agent + pipeline_bridge |
| P1-10 | Perception Plane register_data() 注入 | ✅ Wave 3c | 3 個測試確認 register_data 調用 |
| P1-11 | ollama_client max_retries=1 違反硬邊界 | ✅ Wave 0 | 代碼確認：max_retries=0（ollama_client.py:63），含中英雙語注釋 |
| P1-15 | layer2_tools subprocess 參數注入 | ✅ Wave 0 | -- 分隔符 + 截斷 + 剝離 |
| P1-16 | H0 Gate 確定性門控缺失 | ✅ Day 1+2+3 | 832 行 h0_gate.py，94 個測試，<1ms SLA 驗證，已 merge |
| P1-17 | GovernanceHub TTL 競態 | ✅ Wave 3c | 鎖外讀取修復 |

### 1.3 AI 相關 P2 問題

| # | 問題 | 狀態 | 說明 |
|---|------|------|------|
| P2-2 | strategist_agent 覆蓋率 ~40% | 部分改善 | 36 個測試函數（+H1/H3/H4/H5 相關測試），但 _ai_evaluate 超時/失敗回退仍需更多覆蓋 |
| P2-28 | layer2_route Daily Budget 超限路由層驗證 | ✅ | test_layer2.py 79 個測試，含預算路徑 |

### 1.4 修復進度總結

- **AI 相關 P0**：1/1 完成（100%）
- **AI 相關 P1**：6/6 完成（100%）
- **AI 相關 P2**：2/2 核心項完成，覆蓋率仍有提升空間

---

## 二、AI 模型使用效率評估 / AI Model Usage Efficiency

### 2.1 三層架構分佈（L0 / L1 / L2）

| 層級 | 模型 | 用途 | 成本 | 延遲 | 評估 |
|------|------|------|------|------|------|
| **L0** | 確定性規則 | H0 Gate 5 檢查、啟發式評估、Regime 檢測 | $0 | <1ms | ✅ 優秀 — <1ms SLA 達成，5 個子檢查完全確定性 |
| **L1 9B** | Qwen 3.5 9B (q4_K_M) | judge_edge()、L1 triage、分類 | $0 | ~1.9s | ✅ 良好 — think=False 優化後延遲大幅改善（8.7s→1.9s） |
| **L1 27B** | Qwen 3.5 27B (q4_K_M) | 複雜信號評估、週報模式發現 | $0 | ~9.9s | ✅ 良好 — 按需使用（complexity ≥ 0.5 觸發），不佔用快速路徑 |
| **L2** | Claude Sonnet/Opus | 深度推理 Agent 循環 | $0.01-4.00/session | 30-120s | ⚠ 受限 — 依賴 ANTHROPIC_API_KEY，demo 環境未啟用 |

**架構評估：**
- L0→L1→L2 階梯式降級設計正確，符合原則 14（零外部成本可運行）
- L0 (H0 Gate) 完全不依賴 AI，純確定性判斷，是最關鍵的進步
- L1 Ollama 本地推理實現零成本 AI 評估，模型分配合理（9B 快速 / 27B 複雜）
- L2 Claude 路徑在缺少 API key 時正確降級到 L1 local triage

### 2.2 Ollama 集成質量

**優點：**
1. `think=False` 在頂層 JSON 正確放置（ollama_client.py:211），非 options 子級 -- 性能提升 4.5x
2. `max_tokens` 精簡到實際需要：judge_edge=100, triage=100, classify=32 -- 減少推理冗餘
3. 線程安全單例 + 連接池複用（ollama_client.py:97-114）
4. 可用性檢測有 TTL 緩存（60s，避免每次請求都 ping）
5. `max_retries=0` 嚴格遵守 CLAUDE.md 硬邊界，死代碼分支有明確注釋

**問題：**
1. **P2-NEW-AI-1**（NEW）：`is_available()` 使用 `urllib.request.urlopen` 同步阻塞（ollama_client.py:143）。在 async 上下文（如 `_l1_triage_local`）中已用 `asyncio.to_thread` 包裝，但在同步回調路徑（如 StrategistAgent._evaluate_edge → `self._ollama.is_available()`）中會阻塞 `on_tick` 主線程最多 5 秒。
2. **P3-AI-1**（NEW）：`chat()` 方法未傳遞 `think` 參數（ollama_client.py:255-265），只有 `generate()` 支持。若未來有多輪對話需求，需補充。

### 2.3 模型定價準確性

- Claude 模型 ID 已更新為最新版本（layer2_types.py:51-55）：
  - Haiku: `claude-haiku-4-5-20251001`
  - Sonnet: `claude-sonnet-4-6-20250326`
  - Opus: `claude-opus-4-6-20250326`
- 每日硬上限 $2.00（layer2_types.py:60），符合 DOC-08 §4
- Ollama 成本正確設為 $0.00（ollama_client.py:90），本地推理零成本
- PricingTable 有 30 天核實提醒機制（layer2_cost_tracker.py 設計）

---

## 三、H1-H5 治理層效果分析 / H1-H5 Governance Layer Effectiveness

### 3.1 H0 Gate（確定性門控）— 全新模組 ✅

**實現質量：優秀**

- 832 行代碼，5 個確定性子檢查（freshness/health/eligibility/risk_envelope/cooldown）
- 94 個測試（test_h0_gate.py）+ 5 個集成測試（test_h0_gate_cooldown_integration.py）
- SLA 壓測：1000 次 timeit 均 <1ms avg（實測 <0.5ms）
- 熱路徑零 I/O 設計正確：所有狀態通過外部線程非同步注入
- H0HealthWorker daemon 線程定期採樣 CPU/記憶體/DB 延遲
- pipeline_bridge.py 已接入：`_process_pending_intents()` 前置 H0 Gate 阻擋

**關鍵設計決策驗證：**
- fail-closed：H0 Gate check() 返回 False → intent 被拒絕（pipeline_bridge.py:568-578）
- H0 Gate 異常時 fail-open（pipeline_bridge.py:590）— 合理，因為異常可能是配置問題而非市場風險
- RiskManager cooldown 事件推送到 H0Gate.update_risk()（已接通）

### 3.2 H1 ThoughtGate（思考閘門）— ✅ 已接入

**實現：** 三條同步規則內嵌 StrategistAgent

| 規則 | 邏輯 | 觸發計數器 | 評估 |
|------|------|-----------|------|
| Budget | cost_tracker.check_daily_budget() | h1_budget_skip | ✅ fail-open 設計正確（tracker=None 時允許） |
| Complexity | relevance_score < 0.3 跳過 AI | h1_complexity_skip | ✅ 避免簡單信號浪費 AI 資源 |
| Cooldown | 同 symbol 30s 內重複跳過 | h1_cooldown_skip | ✅ TD-4 容量保護已實施（_H1_COOLDOWN_MAX_SIZE=1000） |

**問題：**
- H1 三條規則全部在 StrategistAgent 內部實現，未獨立為模組。架構上可接受（避免過度抽象），但不利於獨立測試和復用。

### 3.3 H2 預算門控 — ✅ 已接入

- Layer2CostTracker 注入 StrategistAgent（cost_tracker 參數）
- check_daily_budget() 返回 (allowed, remaining)
- 預算超限時降級到啟發式評估（原則 6 正確：不是 allow-all 也不是 hard block）

### 3.4 H3 ModelRouter（模型路由）— ✅ 已接入

**路由邏輯：**
```
complexity < 0.5  → l1_9b   (快速路徑，~1.9s)
0.5 ≤ complexity < 0.8 → l1_27b  (中等路徑，~9.9s)
complexity ≥ 0.8  → l2      (後台線程，30-120s)
```

**評估：**
- 複雜度計算基於 relevance_score + 多幣種加分 + 緊迫度加分（strategist_agent.py:315-335）
- L2 正確使用 daemon thread 避免阻塞 on_tick（strategist_agent.py:494-498）
- L2 結果僅記錄日誌，不影響已派出的啟發式 intent — 這是一個設計權衡

**問題：**
- **P2-AI-2**（NEW）：L2 後台線程的結果被完全丟棄（僅日誌記錄），沒有任何機制將高質量 L2 評估結果回注到決策流。L2 評估的 CPU/時間成本換來了零實際影響。

### 3.5 H4 輸出驗證（AI Output Validation）— ✅ 已接入

- `_validate_ai_output()` 驗證：dict 類型、confidence 存在、數值型、[0,1] 範圍
- 驗證失敗 → heuristic fallback（原則 6 正確：不是 allow-all）
- `h4_validation_fail` 計數器追蹤失敗次數

**評估：良好但有限**
- 僅驗證 confidence 字段。has_edge、reason 等字段缺少結構驗證
- JSON 解析前的 markdown code block 處理正確（strategist_agent.py:869-871）

### 3.6 H5 成本日誌（Cost Logging）— ✅ 已接入

**雙端追蹤實現：**
1. StrategistAgent L1 路徑：`cost_tracker.record_call(model="l1_9b", cost_usd=0.0)`（strategist_agent.py:528-530）
2. StrategistAgent AI 評估路徑：`cost_tracker.record_ollama_call()`（strategist_agent.py:893）
3. Layer2CostTracker：完整 Claude API 成本追蹤（record_claude_cost + record_search_cost）

**roi_basis 標記：**
- 所有 ROI 計算強制帶 `"roi_basis": "paper_simulation_only"` 標記（layer2_cost_tracker.py:477, 582）
- 符合原則 10（認知誠實）：明確區分模擬收益和真實收益

**問題：**
- **P2-AI-3**（NEW）：StrategistAgent 使用兩個不同的 cost_tracker 方法名（`record_call` vs `record_ollama_call`），使用 `getattr` 動態查找而非直接調用。如果 cost_tracker 實例更換，可能靜默失敗。應統一接口名。

### 3.7 H1-H5 綜合評估

| 層 | 完成度 | 運行時接入 | 測試覆蓋 | 評級 |
|----|--------|-----------|---------|------|
| H0 | 100% | ✅ pipeline_bridge + risk_manager + routes | 99 tests | A |
| H1 | 90% | ✅ StrategistAgent 內嵌 | 含在 strategist tests | B+ |
| H2 | 85% | ✅ Layer2CostTracker 注入 | 含在 layer2 tests | B |
| H3 | 80% | ✅ StrategistAgent._h3_route_model | 含在 strategist tests | B |
| H4 | 75% | ✅ _validate_ai_output | 含在 strategist tests | B- |
| H5 | 80% | ✅ 雙端 record | 含在 strategist + layer2 tests | B |

---

## 四、Agent 系統協作效果 / Agent System Collaboration Effectiveness

### 4.1 五 Agent 鏈路狀態

```
Scout(Worker) → [MessageBus] → Strategist → [MessageBus] → Guardian →
  PipelineBridge → Executor → [EXECUTION_REPORT] → Analyst → [ROUND_TRIP_COMPLETE]
```

**鏈路接通確認：**

| 環節 | 狀態 | 證據 |
|------|------|------|
| ScoutWorker → ScoutAgent | ✅ | daemon 線程 30min 週期掃描，scan_fn 可注入 |
| Scout → Strategist (MessageBus) | ✅ | INTEL_OBJECT 消息類型，intel_received stats 可觀察 |
| Strategist → Guardian (MessageBus) | ✅ | TRADE_INTENT 消息類型，bus.send() 確認（strategist_agent.py:649-653） |
| Guardian → PipelineBridge | ✅ | APPROVED_INTENT → submit_order()（executor_agent 已接入） |
| Executor → EXECUTION_REPORT | ✅ | Batch 11 實現 |
| PipelineBridge → Analyst | ✅ | ROUND_TRIP_COMPLETE + _emit_round_trip()（FA-7 止損路徑已補入） |

**shadow=False 切換：** ✅ Sprint 5a 正式切換（前置條件 G-05 + H0 blocking + Guardian 確認），Strategist 不再僅記錄日誌而是真正產出 intent。

### 4.2 Agent 設計質量評估

| Agent | 代碼行數 | 主要職責 | 質量評估 |
|-------|---------|---------|---------|
| ScoutWorker | 100+ | 30min 定時掃描觸發 | ✅ 簡潔、冪等 start、可中斷睡眠 |
| StrategistAgent | 994 | AI edge 評估 + TradeIntent 產出 | ✅ 完善：H1-H4 內嵌、fail-closed、權重系統 |
| GuardianAgent | — | 風控審查 | ✅ 已接入（pipeline_bridge 確認） |
| ExecutorAgent | — | 訂單執行 + acquire_lease | ✅ G-05 修復後具備 Decision Lease |
| AnalystAgent | 790 | 交易結果分析 + 模式發現 | ✅ L1 統計 + L2 AI 模式、TruthSourceRegistry 接入 |

### 4.3 MessageBus 健康度

- Sprint 1b 負載測試：11 個 MessageBus 測試確認基本功能
- 已知問題文件化：ISSUE-1 無界列表、ISSUE-2 鎖內 subscriber（Cleanup Sprint 記錄）
- subscribe() 3→2 參數 bug 已修復（Phase 0 Round 2.5）

### 4.4 協作效果問題

- **P2-AI-4**（EXISTING-UNFIXED，原 P3-1）：Conductor Agent 仍未完善。5 個 Agent 已注冊但缺少自動編排（健康檢查循環、Agent 重啟、負載均衡）。當前靠各 Agent 獨立運行，無統一指揮。

---

## 五、學習管線成熟度 / Learning Pipeline Maturity

### 5.1 學習管線架構

```
[交易完成] → AnalystAgent L1 統計分析
                ↓ (observations ≥ 200)
           AnalystAgent L2 AI 模式發現 (Qwen 27B)
                ↓
           TruthSourceRegistry 聲明登記
                ↓
           StrategistAgent 策略偏好權重更新

[Operator API] → ExperimentLedger 假設生命週期
                     ↓ (65% 閾值)
                 CONFIRMED → TruthSourceRegistry

[Operator API] → BacktestEngine 回測驗證
                     ↓ (Sharpe > 1.0)
                 自動注入 TruthSourceRegistry

[Operator API] → EvolutionEngine 參數網格搜索
                     ↓ (最優結果)
                 注入 TruthSourceRegistry (confidence ≤ 0.75)
```

### 5.2 各模組評估

| 模組 | 行數 | 測試 | 運行時接入 | 成熟度 |
|------|------|------|-----------|--------|
| TruthSourceRegistry | 821 | 52 | ✅ Analyst + Strategist 雙向注入 | **B+** — 認知誠實約束完善（AI ≤ 0.85，FACT 僅 manual） |
| ExperimentLedger | 617 | 60 | ✅ Analyst 注入 + 4 API 端點 | **B** — PENDING→CONFIRMED/REFUTED/EXPIRED 生命週期完整，65% 閾值 |
| BacktestEngine | 531 | 57 | ✅ API 端點 POST /api/v1/backtest/run | **B** — 純函數指標 + 原則 7 隔離 + Sharpe 邊界保護 |
| EvolutionEngine | 280 | 31+10 | ✅ (via backtest_routes) | **B-** — 網格搜索 MVP，max_combinations=50 資源防護 |

### 5.3 學習管線關鍵突破（vs 3/31）

1. **Phase 2 Batch 2C 修復了雙重死代碼問題：**
   - `_register_pattern_claims()` 從「已定義但從未被調用」→ 現在在 AI + 統計兩條路徑的 bus.send() 前調用
   - BacktestEngine 從「無 API 路由」→ 現有 POST/GET 端點
   - 這是學習管線從「架構存在」到「運行時有效」的質變

2. **StrategistAgent 策略偏好權重在決策路徑中被讀取：**
   - `adjusted_confidence = min(1.0, evaluation.confidence * weight)`（strategist_agent.py:592）
   - 審計 metadata 保留 raw_confidence 和 strategy_weight（原則 8 可追溯）

3. **_extract_strategy_from_pattern() 永不返回 "all"：**
   - 解決了 StrategistAgent._apply_pattern_insight() 靜默跳過 "all" 聲明的問題

### 5.4 學習管線問題

- **P1-AI-1**（NEW）：TruthSourceRegistry 無持久化。服務重啟後所有已登記的 PatternClaim 全部丟失。代碼中有 `_TRUTH_REGISTRY_DEFAULT_PATH` 定義了 snapshot 路徑（truth_source_registry.py:69-74），但 **未找到 save/load 方法被調用的證據**。ExperimentLedger 同理——純記憶體狀態，重啟歸零。
  - 影響：Paper Trading 週期結束重啟後，所有學習成果消失
  - 優先級：P1（影響原則 12「持續進化」核心能力）

- **P2-AI-5**（NEW）：AnalystAgent L2 觸發條件 `observations ≥ 200` 在當前 Paper Trading 環境下可能需要數週才能達到。L2 模式發現可能長期處於「從未被觸發」狀態。
  - 建議：添加可觀測指標（觀察數 vs 觸發閾值），或降低 demo 環境閾值

- **P2-AI-6**（NEW）：EvolutionEngine 的 `is_simulated` 強制 True 使用 `object.__setattr__`（繞過 frozen dataclass）。雖然意圖正確（防止真實交易），但這種 hack 在代碼維護時容易被忽略或誤改。

---

## 六、開發速度與代碼質量趨勢 / Development Velocity and Code Quality Trends

### 6.1 開發速度（3/31 → 4/01）

| 指標 | 數值 |
|------|------|
| Commits | 109（單日，極高密度） |
| 新增模組 | h0_gate.py, truth_source_registry.py, experiment_ledger.py, evolution_engine.py, backtest_engine.py, symbol_category_registry.py |
| 新增測試 | +869（2,480 → 3,349） |
| 新增路由 | 8+ (backtest, experiment, evolution, governance/h0-gate) |
| 品類擴展 | +Spot (634 幣對) + Inverse (27 幣對) |

**評價：** 開發速度極高，單日 109 commits 涵蓋 H0 Gate 完整實現、學習管線三層落地、三品類支持。在高密度下代碼質量保持良好（3,310/3,349 tests passing = 98.8%）。

### 6.2 代碼質量趨勢

**正面趨勢：**
1. **雙語注釋全覆蓋**：所有新建模組（h0_gate, truth_source_registry, experiment_ledger, evolution_engine, backtest_engine）都有完整的 MODULE_NOTE 中英雙語注釋
2. **原則 7 隔離嚴格執行**：學習管線四個模組全部零 live 模組 import
3. **fail-closed / fail-open 決策有注釋**：每個 fallback 路徑都有明確的設計意圖說明
4. **認知誠實約束完善**：AI confidence 上限 0.85、roi_basis 標記、REFUTED 不注入
5. **測試密度**：AI 相關 492 個測試函數，覆蓋率大幅提升

**負面趨勢：**
1. 21 failed + 17 errors（部分 pre-existing，部分新增）
2. strategist_agent.py 已增長到 994 行（H1-H4 全部內嵌），接近需要拆分的閾值
3. `getattr` 動態方法查找用於 cost_tracker 接口，降低了類型安全

### 6.3 測試分佈（AI 模組）

| 測試文件 | 測試函數數 | 覆蓋範圍 |
|---------|-----------|---------|
| test_h0_gate.py | 94 | H0 Gate 5 子檢查 + SLA + Health Worker |
| test_layer2.py | 79 | L1 triage + L2 session + cost tracking |
| test_backtest_engine.py | 57 | 回測引擎全功能 |
| test_truth_source_registry.py | 52 | 聲明登記 + TTL + 認知級別 |
| test_strategist_agent.py | 36 | H1/H3/H4/shadow/intent 產出 |
| test_experiment_ledger.py | 35 | 假設生命週期 |
| test_evolution_engine.py | 31 | 網格搜索 + 資源防護 |
| test_ollama_integration.py | 28 | Ollama 客戶端 + 可用性 |
| test_experiment_routes.py | 25 | 4 API 端點 |
| test_analyst_agent_registry.py | 23 | TruthSourceRegistry 整合 |
| test_analyst_agent_unit.py | 17 | L1 統計分析 |
| test_evolution_routes.py | 10 | Evolution API 端點 |
| test_h0_gate_cooldown_integration.py | 5 | Cooldown 聯動 smoke |
| **合計** | **492** | — |

---

## 七、新發現問題清單 / New Issues Found

### P1 — 本週修復

| # | 問題 | 模組 | 影響 | 狀態 |
|---|------|------|------|------|
| P1-AI-1 | TruthSourceRegistry + ExperimentLedger 無持久化，重啟後學習成果全部丟失 | truth_source_registry.py, experiment_ledger.py | 原則 12（持續進化）核心能力無法跨重啟保留 | NEW |

### P2 — 下一版本

| # | 問題 | 模組 | 影響 | 狀態 |
|---|------|------|------|------|
| P2-AI-1（P2-NEW） | ollama_client.is_available() 同步阻塞，在 StrategistAgent on_tick 路徑中可能阻塞主線程 5 秒 | ollama_client.py:143 | 止損路徑延遲（on_tick 被阻塞） | NEW |
| P2-AI-2（P2-NEW） | H3 L2 後台線程評估結果被完全丟棄，無回注機制 | strategist_agent.py:755-772 | L2 計算資源零回報 | NEW |
| P2-AI-3（P2-NEW） | StrategistAgent 使用兩個不同的 cost_tracker 方法名（record_call vs record_ollama_call），動態查找 | strategist_agent.py:528, 893 | 接口不統一，靜默失敗風險 | NEW |
| P2-AI-4（P2 原 P3-1） | Conductor Agent 未完善，5 Agent 缺少統一編排 | multi_agent_framework.py | Agent 健康檢查 + 重啟缺失 | EXISTING-UNFIXED |
| P2-AI-5（P2-NEW） | AnalystAgent L2 觸發閾值 200 觀察在 demo 環境可能數週達不到 | analyst_agent.py:321-324 | L2 模式發現長期不觸發 | NEW |
| P2-AI-6（P2-NEW） | EvolutionEngine is_simulated 使用 object.__setattr__ 繞過 frozen dataclass | evolution_engine.py | 維護風險 | NEW |

### P3 — 積壓

| # | 問題 | 模組 | 影響 | 狀態 |
|---|------|------|------|------|
| P3-AI-1（P3-NEW） | ollama_client.chat() 未支持 think 參數 | ollama_client.py:224-265 | 多輪對話無法控制 chain-of-thought | NEW |
| P3-AI-2（P3-NEW） | strategist_agent.py 已 994 行，H1-H4 全部內嵌，接近需要拆分閾值 | strategist_agent.py | 可維護性 | NEW |
| P3-AI-3（P3-NEW） | H4 驗證僅檢查 confidence 字段，has_edge 和 reason 缺少驗證 | strategist_agent.py:800-831 | 不完整的 AI 輸出驗證 | NEW |

---

## 八、改進建議 / Improvement Recommendations

### 8.1 緊急（本週）

1. **實施 TruthSourceRegistry 持久化（P1-AI-1）**
   - 路徑已定義（truth_source_registry.py:69-74），需補 save_snapshot() + load_snapshot()
   - 觸發時機：register_claim / record_falsification 後防抖寫入
   - ExperimentLedger 同理，建議用 JSON 快照

### 8.2 近期（下一 Sprint）

2. **L2 結果回注機制（P2-AI-2）**
   - 方案：L2 完成後將 EdgeEvaluation 存入共享隊列，PipelineBridge 下一輪 tick 時讀取
   - 或：L2 結果直接通過 MessageBus PATTERN_INSIGHT 通知 Strategist

3. **cost_tracker 接口統一（P2-AI-3）**
   - 定義抽象接口：record_call(model, cost_usd, latency_ms) 統一 L1/L2 路徑

4. **is_available() 異步化或緩存強化（P2-AI-1）**
   - 方案 A：增加更長 TTL（5min 而非 60s），減少同步阻塞頻率
   - 方案 B：Strategist 啟動時檢測一次，之後假設 available 直到失敗

5. **降低 demo 環境 L2 觸發閾值（P2-AI-5）**
   - 方案：`l2_min_observations` 在 demo_only 模式下自動降為 50

### 8.3 長期（Phase 4 前）

6. **StrategistAgent 模組拆分（P3-AI-2）**
   - 建議將 H1-H4 邏輯提取為獨立的 ThoughtGateManager 模組

7. **AI 使用效果自動評估儀表板**
   - 建議新增 `/api/v1/ai-stats` 端點，暴露：
     - H1 skip 計數（budget/complexity/cooldown）
     - H4 驗證失敗率
     - L1 vs L2 路由比例
     - Ollama 平均延遲
     - 策略偏好權重分佈

### 8.4 原則 13（AI 資源成本感知）合規評估

| 子要求 | 狀態 | 說明 |
|--------|------|------|
| 每次 AI 調用計費 | ✅ | Claude: record_claude_cost; Ollama: record_call/$0 |
| cost_edge_ratio 計算 | ✅ | get_cost_edge_ratio() 實現，7 日窗口 |
| cost_edge_ratio ≥ 0.8 → 建議關倉 | ✅ | tab-ai.html GUI 已實施閾值判斷 |
| 每日硬上限 | ✅ | $2.00/day，不可突破 |
| roi_basis 標記 | ✅ | "paper_simulation_only" 雙端標記 |

**原則 13 合規度：90%（缺少 Ollama 調用次數的月度趨勢報告）**

---

## 附錄 A：AI 模組代碼行數清單

| 模組 | 行數 | 用途 |
|------|------|------|
| pipeline_bridge.py | 1,937 | AI 集成主管線（H0 Gate + Ollama edge filter） |
| strategist_agent.py | 994 | AI edge 評估 + H1-H4 治理 + 策略偏好權重 |
| h0_gate.py | 832 | 確定性門控（<1ms SLA） |
| truth_source_registry.py | 821 | 模式聲明登記表 |
| analyst_agent.py | 790 | 交易結果分析 + L2 模式發現 |
| layer2_engine.py | 730 | L2 Claude Agent 循環 |
| experiment_ledger.py | 617 | 假設生命週期管理 |
| layer2_cost_tracker.py | 610 | AI 成本追蹤 + 自適應預算 |
| backtest_engine.py | 531 | 回測引擎 |
| ollama_client.py | 484 | Ollama HTTP 客戶端 |
| evolution_engine.py | 280 | 參數網格搜索 |
| scout_worker.py | 100+ | 定時掃描觸發器 |
| **合計** | **~7,726** | — |

## 附錄 B：對比基準差異彙總

| 維度 | 3/31 | 4/01 | 變化幅度 |
|------|------|------|---------|
| H0 Gate | 批處理腳本存在，未接入運行時 | 完整模組 + 運行時接入 + 99 tests | 從 0% → 100% |
| H1 ThoughtGate | 未實現 | 三條規則 + 容量保護 + 統計計數器 | 從 0% → 90% |
| H2 Budget Gate | 概念存在 | Layer2CostTracker 注入 + check_daily_budget | 從 20% → 85% |
| H3 ModelRouter | 未實現 | 三級路由 (9B/27B/L2) + 後台線程 | 從 0% → 80% |
| H4 Validation | 未實現 | _validate_ai_output + h4_validation_fail counter | 從 0% → 75% |
| H5 CostLogger | 概念存在 | 雙端 record + roi_basis marker | 從 20% → 80% |
| TruthSourceRegistry | 未存在 | 821 行 + 52 tests + 認知誠實約束 | 全新 |
| ExperimentLedger | 未存在 | 617 行 + 60 tests + 4 API 端點 | 全新 |
| BacktestEngine | 未存在 | 531 行 + 57 tests + API 端點 | 全新 |
| EvolutionEngine | 未存在 | 280 行 + 41 tests | 全新 |
| shadow=False | 未切換 | ✅ 已切換 | 功能激活 |
| Agent 鏈路 | 部分接通 | 全鏈路 Scout→Strategist→Guardian→Executor→Analyst | 質變 |

---

*報告結束。AI-E 建議下一次全面 AI 效果評估在 Phase 4 Paper Trading 觀察期開始後進行，屆時將有真實的 L1/L2 調用統計數據和策略偏好權重變化趨勢可供分析。*
