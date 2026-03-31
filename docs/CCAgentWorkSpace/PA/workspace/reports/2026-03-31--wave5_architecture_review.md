# PA 架構進度報告：Wave 5 完成後全鏈路評估
**日期**：2026-03-31
**作者**：PA（Project Architect）
**範圍**：Wave 5（Sprint 5a + 5b）完成後架構現狀 + 遺留技術債 + 下一步派發建議

---

## 一、執行摘要

Wave 5 成功完成了 H1-H5 AI 治理層接通與 Scout→Strategist 情報鏈路部署，系統完成度從 CLAUDE.md 上次評估的約 55%（AI 風險評估）進步至約 75%。測試通過數 2912（含 24 個 pre-existing failures + 17 errors）。

**主要架構成就**：
- H0 Gate 已從 warn-only 升為 blocking 模式
- H1（ThoughtGate）/ H2（BudgetCheck）/ H3（ModelRouter）/ H4（OutputValidation）/ H5（CostLogger）全部接入 StrategistAgent
- ScoutWorker 後台線程 30 分鐘定期掃描並注入 StrategistAgent
- ExecutorAgent 通過 MessageBus 訂閱 APPROVED_INTENT，acquire_lease → submit_order 路徑閉合

**主要架構風險（新發現）**：
- **雙執行路徑並存**：pipeline_bridge 直接路徑（缺少 acquire_lease）與 ExecutorAgent 路徑（含 acquire_lease）並存，Principle 3（AI 輸出≠即時命令）在 pipeline_bridge 路徑未完整實施

---

## 二、完整鏈路閉合狀態評估

### 2.1 H0→H1→H2→H3→H4→H5→acquire_lease→submit_order

```
實際代碼路徑 A（StrategistAgent → ExecutorAgent，推薦路徑）：

  MarketTick → on_tick() → H0Gate.check() [BLOCKING, <1ms]
        ↓ (allowed)
  pipeline_bridge._process_pending_intents()
        ↓
  StrategistAgent.collect_pending_intents()
        → StrategistAgent._handle_intel() 內已完成：
            H1: budget / complexity / cooldown 三門 → heuristic fallback
            H2: check_daily_budget() → tier 降級
            H3: ModelRouter → l1_9b / l1_27b / l2_sonnet
            [AI 調用: _ai_evaluate()]
            H4: _validate_ai_output() → heuristic fallback（fail-closed）
            H5: record_ollama_call() → cost tracker
        → TradeIntent（含 confidence, model_used, cost）
        ↓
  pipeline_bridge → Guardian.review_intent() [fail-closed]
        ↓ (APPROVED)
  StrategistAgent 內部：bus.send(APPROVED_INTENT) → ExecutorAgent.on_message()
        ↓
  ExecutorAgent._handle_approved_intent()
        → acquire_lease() [fail-closed：None → early return]
        → submit_order() → PaperTradingEngine
```

**結論：路徑 A 鏈路閉合。Principle 3 完整實施。**

---

```
路徑 B（pipeline_bridge 直接路徑，遺留路徑）：

  MarketTick → on_tick() → H0Gate.check() [BLOCKING]
        ↓
  _process_pending_intents()
  → collect from _orchestrator（傳統策略）
  → collect from _strategist_agent（非 shadow intents）
        ↓
  Guardian.review_intent() [fail-closed]
        ↓ (APPROVED)
  pipeline_bridge._engine.submit_order() ← ⚠️ 直接調用，無 acquire_lease
```

**⚠️ 關鍵發現：路徑 B 存在架構缺口**

pipeline_bridge 的直接提交路徑（約 line 701）跳過了 `acquire_lease()`。這意味著：
- 傳統策略（Orchestrator 產生的 intents）繞過了 Decision Lease 控制面
- StrategistAgent 的 `collect_pending_intents()` intents 也走這個路徑（而非 MessageBus 路徑）
- Principle 3 在此路徑未完整實施

**分析**：在 `demo_only` 模式下影響有限——PaperTradingEngine 有自己的 GovernanceHub gate。但架構層面存在不一致性，是需要修復的技術債。

---

### 2.2 ScoutWorker → produce_intel → Strategist 鏈路

```
ScoutWorker（daemon thread, 30min interval）
    → _scout_scan_fn()
        → MARKET_SCANNER.scan() → top 5 opportunities
        → SCOUT_AGENT.produce_intel()
            → MessageBus.send(INTEL_REPORT, Strategist)
                → StrategistAgent.on_message() → _handle_intel()
                    → H1→H2→H3→H4→H5 chain
```

**結論：鏈路完整，三段均已實現。**

**細節確認**：
- `SCOUT_AGENT.produce_intel()` 在 `multi_agent_framework.py:396` 定義，調用 `bus.send()`
- `StrategistAgent` 訂閱 `SCOUT` → `STRATEGIST` 通道，INTEL_REPORT 消息類型
- `ScoutWorker` 在 `phase2_strategy_routes.py` 模塊加載時初始化（非 fatal 異常包裹）
- `ScoutWorker` 與 `MARKET_SCANNER` 雙軌並行：Scanner 5 分鐘循環饋送 AUTO_DEPLOYER；Worker 30 分鐘循環饋送 Strategist AI 分析

---

## 三、遺留技術債盤點

### 3.1 架構層面關鍵技術債（P1 級）

#### TD-1：雙執行路徑缺少 acquire_lease（P1）
**檔案**：`app/pipeline_bridge.py`，約 line 700-710
**問題**：`_process_pending_intents()` 中 Guardian 批准後直接調用 `submit_order()`，跳過 `acquire_lease()`
**影響**：Principle 3 部分不合規；但 demo_only 模式下 PaperTradingEngine 有 GovernanceHub gate 兜底
**修復方案**：在 pipeline_bridge 中注入 `_governance_hub`，Guardian APPROVED 後調用 `acquire_lease(intent.intent_id, scope="TRADE_ENTRY")` → fail-closed
**估時**：2h + E4

#### TD-2：StrategistAgent intents 雙路徑語義模糊（P2）
**問題**：StrategistAgent 有兩種 intent 輸出方式：
1. `collect_pending_intents()`（由 pipeline_bridge 輪詢）→ 走路徑 B（無 acquire_lease）
2. 內部 `_dispatch_trade_intent()` → `bus.send(APPROVED_INTENT)` → ExecutorAgent（走路徑 A，有 acquire_lease）
**影響**：同一 Agent 的 intent 走哪條路取決於內部邏輯，維護者難以推理
**修復方案**：廢棄路徑 B 的 StrategistAgent collect 路徑；所有 AI intent 強制走 MessageBus → ExecutorAgent
**估時**：3h + E2 + E4（副作用風險中等）

#### TD-3：E2 WARN — `cost_tracker.record_call()` except Exception: pass（P2）
**檔案**：`app/strategist_agent.py`，约 line 485
**問題**：記錄 AI 成本失敗時靜默吞異常，無 logger
**修復方案**：加 `logger.warning("H5 cost record failed: %s", e)`
**估時**：15m

#### TD-4：`_h1_cooldown` 字典無容量上限（P2）
**檔案**：`app/strategist_agent.py`
**問題**：650 個 symbol 場景當前安全，但長期運行後無清理機制（無 LRU）
**修復方案**：使用 `functools.lru_cache` 或手動 LRU dict（容量上限 1000）
**估時**：30m

#### TD-5：`_ollama_stats` 懶初始化在方法體（P3）
**檔案**：`app/layer2_cost_tracker.py`
**問題**：`_ollama_stats` dict 在首次調用 `record_ollama_call()` 時初始化，不在 `__init__` 中
**影響**：純可讀性問題，不影響功能
**修復方案**：遷移至 `__init__`
**估時**：15m

---

### 3.2 Phase 1 Batch 1B 可行性評估

**Batch 1B 目標**：Cooldown 聯動 + M-of-N 簽名驗證 + 數據品質→風控降級

#### Cooldown 聯動（H0Gate ↔ RiskManager）
**現狀**：已有 `risk_manager.set_h0_gate()` + `H0Gate.update_risk()` 接口（Wave 3c 完成）
**可行性**：高。接口已存在，主要工作是在 RiskManager 觸發冷卻事件（如連虧止損）時 push 到 H0Gate，並驗證 H0Gate 正確阻塞後續 intent
**估時**：1.5h + E4

#### M-of-N 簽名驗證
**現狀**：無任何基礎設施
**可行性**：中。需要設計多簽方案——最小化版本可以是 GovernanceHub 中的「double confirmation」：先通過 SM-01 授權，再通過 SM-04 風控，視為 2-of-2。形式化 M-of-N 需要更多設計
**建議**：先用「SM-01 + SM-04 雙重 gate 即視為 M-of-N 最小實現」，記錄於 GovernanceHub 日誌
**估時**：2h + PA 設計 + E1 實現

#### 數據品質→風控降級
**現狀**：H0Gate 有 freshness check（price_ts），但沒有數據品質評分
**可行性**：中高。需要在 pipeline_bridge 的 tick 處理中評估數據品質（websocket 延遲/缺口/異常），並通過 `H0Gate.update_risk()` 降級風控等級
**估時**：3h（含設計）+ E1 + E4

---

## 四、下一步技術任務派發建議

### 最高優先級（P1，Wave 6 第一批）

| 任務 | 執行者 | 文件/位置 | 估時 | 可並行 |
|------|-------|---------|------|-------|
| TD-1：pipeline_bridge 注入 governance_hub + acquire_lease | E1-Alpha | `pipeline_bridge.py:700` | 2h | 是 |
| Batch 1B-1：Cooldown 聯動驗證測試 | E1-Beta | `risk_manager.py` + `h0_gate.py` | 1.5h | 是 |
| P3 GUI 術語友好化第一批（SM-01 等術語）| E1a | `tab-governance.html` | 3h | 是 |

**最大並行**：E1-Alpha / E1-Beta / E1a 三個 Agent 可完全並行。

### 中優先級（P2，Wave 6 第二批）

| 任務 | 執行者 | 文件/位置 | 估時 | 前置條件 |
|------|-------|---------|------|---------|
| TD-2：廢棄 StrategistAgent collect 路徑，強制走 MessageBus | E1 | `pipeline_bridge.py` + `strategist_agent.py` | 3h | TD-1 完成後 |
| TD-3：H5 cost_tracker except 加 logger | E1 | `strategist_agent.py:485` | 15m | 無 |
| TD-4：_h1_cooldown LRU cap | E1 | `strategist_agent.py` | 30m | 無 |
| Batch 1B-2：數據品質→風控降級 | E1 + PA | `pipeline_bridge.py` + `h0_gate.py` | 3h + 設計 | PA 先設計 |

---

## 五、架構健康度評分

**總分：7.2 / 10**

| 維度 | 評分 | 依據 |
|------|------|------|
| 治理閉環（GovernanceHub 4 SM）| 8.5 | fail-closed 一流，4 SM 接入，acquire_lease TTL 已修 |
| 執行路徑一致性 | 5.5 | 雙執行路徑並存，pipeline_bridge 直接路徑跳過 acquire_lease |
| AI 治理（H0-H5）| 8.0 | 全鏈路接通，fail-closed fallback 完整，無 allow-all |
| Scout→Strategist 鏈路 | 8.5 | ScoutWorker + produce_intel + H1-H5 全閉合 |
| 測試覆蓋 | 6.5 | 2912 passed，新核心功能有測試，但雙路徑交叉測試不足 |
| 技術債積累 | 6.0 | TD-1 是架構不一致，TD-2 是語義模糊，需要 Wave 6 清理 |
| 安全合規 | 8.0 | 4 CRITICAL 已修，0 CRITICAL 0 HIGH，中等 2 項 |

**評分理由**：Wave 5 顯著提升了 AI 治理鏈路的完整性，但雙執行路徑問題（TD-1/TD-2）帶來架構不一致性，是目前最值得立即處理的技術債。整體架構設計思路清晰，fail-closed 原則貫徹一致。

---

## 六、架構師建議

1. **Wave 6 第一優先**：修復 TD-1（pipeline_bridge acquire_lease），消除 Principle 3 的雙重標準
2. **Wave 6 第二優先**：廢棄 StrategistAgent collect 路徑（TD-2），讓所有 AI 驅動 intent 統一走 MessageBus → ExecutorAgent，使執行路徑從「兩條」收束為「一條」
3. **Phase 1 Batch 1B**：技術上可行，建議按難度排序：Cooldown 聯動（最快）→ 數據品質降級 → M-of-N 簽名（需 PA 設計）
4. **不要急於 shadow=True 回退**：Strategist shadow=False + H0 blocking + Guardian gate 已形成三重防護，目前 demo_only 模式下安全

---

*報告生成：2026-03-31 · PA（Project Architect）*
*下一份報告：Wave 6 TD-1/TD-2 修復驗收後更新*
